"""Gestion de la CUENTA de Claude del servidor: estado de auth, uso de la suscripcion
y CAMBIO de cuenta (logout + login interactivo) sin reiniciar contenedores.

POR QUE EXISTE: la generacion corre `claude -p` (ADR 0001) con la cuenta de Claude de la
maquina. Esa cuenta se fija con `claude auth login` desde el panel; con `CLAUDE_CONFIG_DIR`
apuntando al volumen COMPARTIDO `/data` (`/data/claude-cfg`, ADR 0013), las credenciales
viven en un fichero que `claude` relee en cada invocacion y que worker + daemons comparten:
un login desde el panel cambia la cuenta EN CALIENTE para ambos, sin reinicio.

DONDE CORRE: SOLO en la imagen del worker (worker/daemons), que lleva Node + `claude`. El
`back` NO tiene `claude`: alcanza estas funciones por el listener de control del proceso
`daemons` (ver `control.py`). Por eso este modulo NO importa de `api/`.

QUE OFRECE EL CLI (verificado en claude 2.1.x):
  - `claude auth status --json`  -> {loggedIn, authMethod, apiProvider}. NO da email/cuenta.
  - `claude auth login [--claudeai|--console] [--email <e>] [--sso]` -> flujo interactivo:
    imprime una URL, el humano la abre, pega el codigo que le da el navegador y `claude`
    persiste las credenciales. Headless: la URL sale por stdout y el codigo se pega por
    stdin (lo conducimos por un PTY; ver `iniciar_login`/`enviar_codigo`).
  - `claude auth logout` -> borra las credenciales.
  - `claude -p /usage` -> el medidor de la suscripcion (sesion 5h / semana). OJO: el medidor
    DETALLADO solo aparece con auth por CREDENCIALES (login); con una API key solo sale la
    primera linea. Es una de las razones para fijar la cuenta por login.

SEPARACION testeable: los PARSERS (`parsear_estado`, `parsear_uso`) son puros (texto->dict)
y se testean sin subprocess; los RUNNERS (`estado`, `uso`, `logout`) y el gestor de login
por PTY tocan el sistema y se prueban con un `claude` falso / un PTY de juguete.
"""

from __future__ import annotations

import logging
import os
import re
import select
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field

_log = logging.getLogger("keni_consola.cuenta_claude")

# Binario del CLI (mismo nombre que usa el runner de generacion). PATH del contenedor.
_CLAUDE = "claude"

# Nombre del fichero donde se persiste el bearer del control (en el volumen COMPARTIDO /data,
# bajo `rutas.dir_config()`): back y daemons lo leen/crean ahi, asi que comparten el secreto
# sin que el operador configure nada. La gestion de cuenta esta ACTIVA por defecto.
_FICHERO_BEARER = "control-bearer.secret"

# Cache del ULTIMO medidor `/usage` bueno (en /data, compartido): para no mostrar nunca la
# frase pelada cuando una lectura puntual no trae medidor. Ver `uso()`.
_FICHERO_USO_CACHE = "usage-cache.json"


def bearer_efectivo() -> str:
    """Bearer del listener de control. SIEMPRE devuelve uno (gestion de cuenta activa por def).

    Precedencia: un `KENI_CONTROL_BEARER` explicito (override avanzado, opcional) gana; si no,
    un bearer AUTO-PERSISTIDO en el volumen compartido `/data` que back y daemons comparten.
    Asi la seccion funciona sin configurar nada y el secreto sigue protegiendo el listener.
    """
    from . import config, rutas

    explicito = config.control_bearer()
    if explicito:
        return explicito
    return _bearer_persistido(rutas.dir_config())


def _bearer_persistido(dir_base) -> str:
    """Lee (o crea atomicamente) el bearer compartido en `<dir_base>/control-bearer.secret`.

    Creacion ATOMICA por `os.link` (falla si el destino existe): si dos procesos arrancan a la
    vez, uno gana y el otro lee el token del ganador. 0600. Si `/data` no fuese escribible,
    cae a un token efimero del proceso (degrada: back y daemons no se entenderian, pero no
    casca; en hosted `/data` SIEMPRE es escribible y compartido)."""
    import secrets
    from pathlib import Path

    dir_base = Path(dir_base)
    ruta = dir_base / _FICHERO_BEARER
    if actual := _leer_bearer(ruta):
        return actual
    token = secrets.token_urlsafe(32)
    try:
        dir_base.mkdir(parents=True, exist_ok=True)
        tmp = dir_base / f".{_FICHERO_BEARER}.{os.getpid()}.tmp"
        tmp.write_text(token, encoding="utf-8")
        os.chmod(tmp, 0o600)
        try:
            os.link(tmp, ruta)  # atomico: falla si ya existe (otro proceso gano la carrera)
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    except OSError:
        _log.warning("no se pudo persistir el bearer de control en %s; uso uno efimero.", ruta)
        return token
    return _leer_bearer(ruta) or token


def _leer_bearer(ruta) -> str | None:
    try:
        return ruta.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None

# Wall-timeouts (s) de las operaciones no interactivas: cortas, el CLI responde rapido.
_TIMEOUT_ESTADO = 30
_TIMEOUT_USO = 120  # /usage hace un roundtrip a Anthropic; margen amplio.
_TIMEOUT_LOGOUT = 30

# Login interactivo: cuanto esperamos a que aparezca la URL tras lanzar `auth login`, y
# cuanto esperamos a que el proceso cierre tras pegar el codigo.
_TIMEOUT_URL = 45
_TIMEOUT_TRAS_CODIGO = 60
# Una sesion de login abandonada (URL emitida, nunca se pego el codigo) se mata pasado esto.
_TTL_SESION_LOGIN = 600.0

# URL de autorizacion que imprime `claude auth login` (la primera https que emita).
_RE_URL = re.compile(r"https://\S+")
# Para CORTAR la lectura: la URL SEGUIDA de un espacio/salto -> garantiza que llego ENTERA
# (no un trozo a medias por un chunk del PTY). Solo para el corte; la URL se extrae con _RE_URL.
_RE_URL_COMPLETA = re.compile(r"https://\S+\s")
# Secuencias ANSI (colores/posicion) que `claude` mete en una TTY: se quitan para parsear.
_RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# Medidor de `/usage`: "Current session: 26% used · resets Jun 15 at 7:39pm (America/...)".
# El separador puede ser "·" (U+00B7) o un guion; toleramos ambos y espacios variables.
_RE_MEDIDOR = re.compile(
    r"^(?P<etiqueta>.+?):\s*(?P<pct>\d+)%\s*used\s*[·\-]?\s*(?:resets\s*(?P<reset>.+))?$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Parsers PUROS (texto -> dict). Sin subprocess: testeables en aislamiento.    #
# --------------------------------------------------------------------------- #


def _limpiar(texto: str) -> str:
    """Quita secuencias ANSI y \\r (artefactos de la TTY) para parsear/mostrar limpio."""
    return _RE_ANSI.sub("", texto or "").replace("\r", "")


def parsear_estado(stdout: str) -> dict:
    """Parsea `claude auth status --json` -> {logueado, metodo, proveedor, email, plan, org, crudo}.

    Con login por credenciales, el CLI da bastante más que con un token: `email`, `orgName`
    y `subscriptionType` (p.ej. "max"). Tolerante: si el stdout no es el JSON esperado,
    devuelve `logueado=None` con el texto crudo, para que la UI muestre "desconocido".
    """
    import json

    base = {"logueado": None, "metodo": None, "proveedor": None,
            "email": None, "plan": None, "org": None}
    crudo = _limpiar(stdout).strip()
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return {**base, "crudo": crudo}
    if not isinstance(datos, dict):
        return {**base, "crudo": crudo}
    return {
        "logueado": bool(datos.get("loggedIn")) if datos.get("loggedIn") is not None else None,
        "metodo": datos.get("authMethod"),
        "proveedor": datos.get("apiProvider"),
        "email": datos.get("email"),
        "plan": datos.get("subscriptionType"),
        "org": datos.get("orgName"),
        "crudo": crudo,
    }


def parsear_uso(stdout: str) -> dict:
    """Parsea `claude -p /usage` -> {disponible, mensaje, medidores:[{etiqueta,pct,reset}], crudo}.

    `disponible` es False cuando el CLI solo devuelve la frase generica sin medidor (p.ej. con
    auth por API key). Cada medidor mantiene la etiqueta tal cual la da el CLI
    ("Current session", "Current week (all models)", ...): el front la traduce/pinta.
    """
    crudo = _limpiar(stdout).strip()
    medidores: list[dict] = []
    mensaje = ""
    for linea in crudo.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        m = _RE_MEDIDOR.match(linea)
        if m:
            medidores.append(
                {
                    "etiqueta": m.group("etiqueta").strip(),
                    "pct": int(m.group("pct")),
                    "reset": (m.group("reset") or "").strip() or None,
                }
            )
        elif not mensaje:
            # Primera linea no-medidor: la frase de cabecera ("You are currently using...").
            mensaje = linea
    return {
        "disponible": bool(medidores),
        "mensaje": mensaje,
        "medidores": medidores,
        "crudo": crudo,
    }


# --------------------------------------------------------------------------- #
# Runners NO interactivos (subprocess). Estado / uso / logout.                 #
# --------------------------------------------------------------------------- #


def _cwd_neutro() -> str:
    """Directorio NEUTRO para invocar `claude` (sin `.claude`/CLAUDE.md que contaminen)."""
    return tempfile.gettempdir()


def _ejecutar(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    """Corre `claude ...` heredando el entorno (CLAUDE_CONFIG_DIR, etc.), sin shell.

    No interactivo: stdin cerrado. Devuelve el CompletedProcess (rc/stdout/stderr). Un
    `claude` ausente (p.ej. en una imagen sin Node) sube FileNotFoundError, que el llamante
    traduce a un error legible.
    """
    return subprocess.run(  # noqa: S603 -- argv lista, sin shell
        argv,
        cwd=_cwd_neutro(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def estado() -> dict:
    """Estado de autenticacion (`claude auth status --json`) parseado."""
    try:
        cp = _ejecutar([_CLAUDE, "auth", "status", "--json"], timeout=_TIMEOUT_ESTADO)
    except FileNotFoundError:
        return {"logueado": None, "metodo": None, "proveedor": None, "crudo": "", "error": "claude no disponible"}
    except subprocess.TimeoutExpired:
        return {"logueado": None, "metodo": None, "proveedor": None, "crudo": "", "error": "timeout"}
    parsed = parsear_estado(cp.stdout)
    if cp.returncode != 0 and parsed["logueado"] is None:
        parsed["error"] = (_limpiar(cp.stderr).strip() or "estado no disponible")
    return parsed


def uso() -> dict:
    """Medidor de uso de la suscripcion (`claude -p /usage`) con CACHE del ultimo bueno.

    `claude -p /usage` a veces devuelve SOLO la frase generica (sin medidor): le pasa cuando
    se le aporrea (rate-limit del propio comando) o ante un bache puntual. Para no mostrar
    NUNCA esa frase pelada, persistimos el ultimo medidor bueno en `/data` y, cuando una
    lectura no trae medidor (o falla/timeout), devolvemos el ULTIMO bueno con `cacheado:true`
    y `actualizado` (epoch). El front pinta "actualizado hace X". Solo si NUNCA hubo un buen
    medidor cae a `disponible:false`.
    """
    try:
        cp = _ejecutar([_CLAUDE, "-p", "/usage"], timeout=_TIMEOUT_USO)
        parsed = parsear_uso(cp.stdout)
        if cp.returncode != 0 and not parsed["disponible"]:
            parsed["error"] = (_limpiar(cp.stderr).strip() or "uso no disponible")
    except FileNotFoundError:
        parsed = {"disponible": False, "mensaje": "", "medidores": [], "crudo": "", "error": "claude no disponible"}
    except subprocess.TimeoutExpired:
        parsed = {"disponible": False, "mensaje": "", "medidores": [], "crudo": "", "error": "timeout"}

    if parsed["disponible"]:
        ts = time.time()
        _guardar_cache_uso({"medidores": parsed["medidores"], "mensaje": parsed["mensaje"], "ts": ts})
        parsed["actualizado"] = ts
        parsed["cacheado"] = False
        return parsed

    # Lectura sin medidor: NO mostramos la frase pelada; servimos el ultimo bueno si lo hay.
    cache = _cargar_cache_uso()
    if cache and cache.get("medidores"):
        return {
            "disponible": True,
            "cacheado": True,
            "actualizado": cache.get("ts"),
            "mensaje": cache.get("mensaje", ""),
            "medidores": cache["medidores"],
            "crudo": parsed.get("crudo", ""),
        }
    return parsed


def _dir_cache():
    """Directorio del cache de uso (volumen compartido /data). Aislable en tests."""
    from . import rutas

    return rutas.dir_config()


def _guardar_cache_uso(datos: dict) -> None:
    """Persiste el ultimo medidor bueno (escritura atomica; best-effort, nunca propaga)."""
    import json
    from pathlib import Path

    try:
        base = Path(_dir_cache())
        base.mkdir(parents=True, exist_ok=True)
        ruta = base / _FICHERO_USO_CACHE
        tmp = base / f".{_FICHERO_USO_CACHE}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(datos), encoding="utf-8")
        os.replace(tmp, ruta)
    except (OSError, ValueError, TypeError):
        pass


def _cargar_cache_uso() -> dict | None:
    """Lee el ultimo medidor bueno cacheado (None si no hay/ilegible)."""
    import json
    from pathlib import Path

    try:
        datos = json.loads((Path(_dir_cache()) / _FICHERO_USO_CACHE).read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


def logout() -> dict:
    """Cierra la sesion de Claude (`claude auth logout`). {ok, mensaje}."""
    try:
        cp = _ejecutar([_CLAUDE, "auth", "logout"], timeout=_TIMEOUT_LOGOUT)
    except FileNotFoundError:
        return {"ok": False, "mensaje": "claude no disponible"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "mensaje": "timeout al cerrar sesion"}
    salida = (_limpiar(cp.stdout) + _limpiar(cp.stderr)).strip()
    return {"ok": cp.returncode == 0, "mensaje": salida or ("Sesion cerrada." if cp.returncode == 0 else "Fallo al cerrar sesion.")}


# --------------------------------------------------------------------------- #
# Login INTERACTIVO por PTY: iniciar (-> URL) / enviar_codigo / cancelar.      #
# --------------------------------------------------------------------------- #
#
# `claude auth login` es interactivo: necesita una TTY (de ahi el PTY), imprime una URL y
# luego espera el codigo por stdin. Lo modelamos como una SESION en memoria de vida corta:
#   iniciar_login()        lanza el proceso, lee hasta ver la URL y la devuelve (sesion viva)
#   enviar_codigo(sid,cod) escribe el codigo en el PTY y espera el cierre (exito/fallo)
#   cancelar_login(sid)    mata el proceso
# El proceso `daemons` es de INSTANCIA UNICA (no escala), asi que el registro en memoria es
# seguro. Un limpiador perezoso mata sesiones abandonadas (URL emitida, codigo nunca pegado).


@dataclass
class _SesionLogin:
    sid: str
    proc: subprocess.Popen
    master_fd: int
    creada: float
    buffer: str = ""  # todo lo leido del PTY (limpio de ANSI), para mostrar/depurar
    url: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_sesiones: dict[str, _SesionLogin] = {}
_sesiones_lock = threading.Lock()


def _leer_disponible(fd: int, *, deadline: float, hasta=None) -> str:
    """Lee del PTY (limpio ANSI) hasta `deadline`, EOF, o —si se da `hasta`— hasta que el
    texto acumulado case ese patron compilado.

    `hasta` es CLAVE para `iniciar_login`: `claude auth login` imprime la URL en <1s pero NO
    cierra (se queda esperando el codigo), asi que sin corte temprano leeriamos hasta el
    deadline entero. Con `hasta=<regex de URL>` devolvemos en cuanto aparece la URL.
    """
    trozos: list[str] = []
    while time.monotonic() < deadline:
        restante = max(0.0, deadline - time.monotonic())
        listos, _, _ = select.select([fd], [], [], min(0.5, restante))
        if not listos:
            continue
        try:
            datos = os.read(fd, 4096)
        except OSError:
            break  # el otro extremo (PTY) se cerro: el proceso termino.
        if not datos:
            break
        trozos.append(datos.decode("utf-8", errors="replace"))
        if hasta is not None and hasta.search(_limpiar("".join(trozos))):
            break  # ya tenemos lo que buscabamos (p.ej. la URL): no esperes mas
    return _limpiar("".join(trozos))


def _argv_login(*, console: bool, email: str | None, sso: bool) -> list[str]:
    argv = [_CLAUDE, "auth", "login", "--console" if console else "--claudeai"]
    if email:
        argv += ["--email", email]
    if sso:
        argv += ["--sso"]
    return argv


def _gc_sesiones() -> None:
    """Mata y olvida sesiones de login mas viejas que el TTL (abandonadas)."""
    ahora = time.monotonic()
    caducas: list[_SesionLogin] = []
    with _sesiones_lock:
        for sid, s in list(_sesiones.items()):
            if ahora - s.creada > _TTL_SESION_LOGIN:
                caducas.append(s)
                _sesiones.pop(sid, None)
    for s in caducas:
        _matar(s)


def iniciar_login(*, console: bool = False, email: str | None = None, sso: bool = False) -> dict:
    """Lanza `claude auth login` en un PTY y devuelve {sesion, url, salida}.

    Lee del PTY hasta ver la URL de autorizacion (o agotar `_TIMEOUT_URL`). La sesion queda
    VIVA esperando el codigo (`enviar_codigo`). Si no aparece URL, mata el proceso y reporta
    la salida capturada (para diagnosticar, p.ej. un `claude` que pide otra cosa).
    """
    import pty

    _gc_sesiones()
    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(  # noqa: S603 -- argv lista, sin shell
            _argv_login(console=console, email=email, sso=sso),
            cwd=_cwd_neutro(),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            text=False,
            start_new_session=True,  # grupo propio: matar_arbol al cancelar/timeout
        )
    except FileNotFoundError:
        os.close(master_fd)
        os.close(slave_fd)
        return {"error": "claude no disponible en este servidor"}
    os.close(slave_fd)  # el hijo ya tiene su copia; el padre lee/escribe por master_fd

    salida = _leer_disponible(master_fd, deadline=time.monotonic() + _TIMEOUT_URL, hasta=_RE_URL_COMPLETA)
    m = _RE_URL.search(salida)
    if not m:
        # Sin URL: aborta y reporta. (proc pudo morir o pedir algo inesperado.)
        s_tmp = _SesionLogin(sid="", proc=proc, master_fd=master_fd, creada=time.monotonic())
        _matar(s_tmp)
        return {"error": "no se obtuvo la URL de autorizacion", "salida": salida.strip()}

    sid = uuid.uuid4().hex
    sesion = _SesionLogin(
        sid=sid, proc=proc, master_fd=master_fd, creada=time.monotonic(), buffer=salida, url=m.group(0)
    )
    with _sesiones_lock:
        _sesiones[sid] = sesion
    return {"sesion": sid, "url": sesion.url, "salida": salida.strip()}


def enviar_codigo(sid: str, codigo: str) -> dict:
    """Pega el `codigo` en el PTY de la sesion y espera el cierre. {ok, mensaje, salida}.

    Exito = el proceso termina con returncode 0. Captura la cola de salida para el mensaje.
    La sesion se cierra y olvida pase lo que pase (no se reusa un login a medias).
    """
    with _sesiones_lock:
        sesion = _sesiones.pop(sid, None)
    if sesion is None:
        return {"ok": False, "mensaje": "sesion de login desconocida o expirada"}

    with sesion.lock:
        try:
            os.write(sesion.master_fd, (codigo.strip() + "\n").encode("utf-8"))
        except OSError:
            _matar(sesion)
            return {"ok": False, "mensaje": "no se pudo enviar el codigo (proceso cerrado)"}

        # Lee hasta que el proceso cierre o se agote el plazo.
        deadline = time.monotonic() + _TIMEOUT_TRAS_CODIGO
        cola = _leer_disponible(sesion.master_fd, deadline=deadline)
        sesion.buffer += cola
        try:
            rc = sesion.proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _matar(sesion)
            return {"ok": False, "mensaje": "timeout esperando a que termine el login", "salida": cola.strip()}
        finally:
            _cerrar_fd(sesion.master_fd)

        ok = rc == 0
        mensaje = cola.strip() or ("Cuenta cambiada." if ok else "El login termino con error.")
        return {"ok": ok, "mensaje": mensaje, "salida": cola.strip()}


def cancelar_login(sid: str) -> dict:
    """Cancela y olvida una sesion de login en curso. {ok}."""
    with _sesiones_lock:
        sesion = _sesiones.pop(sid, None)
    if sesion is None:
        return {"ok": True}  # idempotente: ya no existia
    _matar(sesion)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Limpieza de procesos / fds (best-effort, nunca propaga).                     #
# --------------------------------------------------------------------------- #


def _cerrar_fd(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def _matar(sesion: _SesionLogin) -> None:
    """Mata el GRUPO del proceso de login (lider de sesion) y cierra el PTY. Best-effort."""
    proc = sesion.proc
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 -- best-effort
            pass
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001 -- reapeo best-effort
        pass
    _cerrar_fd(sesion.master_fd)

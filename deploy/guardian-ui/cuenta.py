"""Gestión de la CUENTA de Claude del GUARDIÁN, desde guardian-ui.

Hermano stdlib-only de `keni_consola.cuenta_claude` (el de la consola, que vive en `daemons`).
guardian-ui DEBE seguir en pie cuando la consola/back está rota (es cuando el keeper la arregla),
así que NO importa de `keni_consola`: este módulo es autocontenido (subprocess + pty + stdlib).

QUÉ HACE: corre el CLI `claude` (que trae la imagen del worker) contra el `CLAUDE_CONFIG_DIR` del
guardián (`/claude-cfg`, su volumen propio), para ver el estado de auth, leer el medidor de uso y
CAMBIAR de cuenta (logout + login interactivo) sin reiniciar. El keeper lee ese mismo dir.

CLI (claude 2.1.x):
  - `claude auth status --json`  -> {loggedIn, authMethod, apiProvider, email, subscriptionType…}
  - `claude auth login [--claudeai|--console] [--email <e>] [--sso]` -> imprime una URL; el humano
    la abre, pega el código y `claude` persiste las credenciales. Lo conducimos por un PTY.
  - `claude auth logout` -> borra las credenciales.
  - `claude -p /usage` -> medidor de la suscripción (sesión 5h / semana).

Los PARSERS (`parsear_estado`, `parsear_uso`, `_reset_a_iso`) son puros (texto->dict) y se testean
sin subprocess.
"""

from __future__ import annotations

import json
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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_CLAUDE = "claude"

# Cache del último medidor `/usage` bueno, bajo CLAUDE_CONFIG_DIR: para no mostrar la frase pelada
# cuando una lectura puntual no trae medidor (p.ej. estando rate-limited). Ver `uso()`.
_FICHERO_USO_CACHE = "guardian-usage-cache.json"

# Wall-timeouts (s) de las operaciones no interactivas.
_TIMEOUT_ESTADO = 30
_TIMEOUT_USO = 120  # /usage hace un roundtrip a Anthropic; margen amplio.
_TIMEOUT_LOGOUT = 30
# Login interactivo: espera a la URL tras lanzar `auth login`, y al cierre tras pegar el código.
_TIMEOUT_URL = 45
_TIMEOUT_TRAS_CODIGO = 60
_TTL_SESION_LOGIN = 600.0

_RE_URL = re.compile(r"https://\S+")
_RE_URL_COMPLETA = re.compile(r"https://\S+\s")  # URL seguida de espacio: garantiza que llegó entera
_RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_RE_MEDIDOR = re.compile(
    r"^(?P<etiqueta>.+?):\s*(?P<pct>\d+)%\s*used\s*[·\-]?\s*(?:resets\s*(?P<reset>.+))?$",
    re.IGNORECASE,
)
_RE_RESET = re.compile(
    r"(?P<mes>[A-Za-z]{3,9})\s+(?P<dia>\d{1,2})(?:,|\s+at)?\s+"
    r"(?P<hora>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ampm>[ap]m)"
    r"(?:\s*\((?P<zona>[^)]+)\))?",
    re.IGNORECASE,
)
_MESES = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}


def _zona_de(nombre: str):
    n = (nombre or "").strip()
    if n.upper() in {"UTC", "GMT", "Z"}:
        return timezone.utc
    try:
        return ZoneInfo(n)
    except Exception:  # noqa: BLE001 -- zona desconocida: el front cae a la frase cruda
        return None


def _reset_a_iso(reset: str | None, ahora: datetime | None = None) -> str | None:
    """Frase de reset del CLI (sin año, en la zona del servidor) -> instante UTC ISO, o None."""
    if not reset:
        return None
    m = _RE_RESET.search(reset)
    if not m:
        return None
    mes = _MESES.get(m.group("mes")[:3].lower())
    if not mes:
        return None
    tz = _zona_de(m.group("zona") or "UTC")
    if tz is None:
        return None
    hora = int(m.group("hora")) % 12
    if m.group("ampm").lower() == "pm":
        hora += 12
    if ahora is None:
        ahora = datetime.now(timezone.utc)
    anio = ahora.astimezone(tz).year
    try:
        local = datetime(anio, mes, int(m.group("dia")), hora, int(m.group("min") or 0), tzinfo=tz)
        if local.astimezone(timezone.utc) < ahora - timedelta(days=2):
            local = local.replace(year=anio + 1)
    except ValueError:
        return None
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _limpiar(texto: str) -> str:
    """Quita secuencias ANSI y \\r (artefactos de la TTY) para parsear/mostrar limpio."""
    return _RE_ANSI.sub("", texto or "").replace("\r", "")


def parsear_estado(stdout: str) -> dict:
    """Parsea `claude auth status --json` -> {logueado, metodo, proveedor, email, plan, org, crudo}."""
    base = {"logueado": None, "metodo": None, "proveedor": None, "email": None, "plan": None, "org": None}
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


def parsear_uso(stdout: str, ahora: datetime | None = None) -> dict:
    """Parsea `claude -p /usage` -> {disponible, mensaje, medidores:[{etiqueta,pct,reset,reset_iso}], crudo}."""
    crudo = _limpiar(stdout).strip()
    medidores: list[dict] = []
    mensaje = ""
    for linea in crudo.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        m = _RE_MEDIDOR.match(linea)
        if m:
            reset = (m.group("reset") or "").strip() or None
            medidores.append(
                {
                    "etiqueta": m.group("etiqueta").strip(),
                    "pct": int(m.group("pct")),
                    "reset": reset,
                    "reset_iso": _reset_a_iso(reset, ahora),
                }
            )
        elif not mensaje:
            mensaje = linea
    return {"disponible": bool(medidores), "mensaje": mensaje, "medidores": medidores, "crudo": crudo}


# --------------------------------------------------------------------------- #
# Runners NO interactivos (subprocess). Estado / uso / logout.                 #
# --------------------------------------------------------------------------- #


def _cwd_neutro() -> str:
    """Directorio NEUTRO para invocar `claude` (sin `.claude`/CLAUDE.md que contaminen)."""
    return tempfile.gettempdir()


def _ejecutar(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    """Corre `claude ...` heredando el entorno (CLAUDE_CONFIG_DIR…), sin shell. No interactivo."""
    return subprocess.run(  # noqa: S603 -- argv lista, sin shell
        argv,
        cwd=_cwd_neutro(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def estado() -> dict:
    """Estado de autenticación (`claude auth status --json`) parseado."""
    try:
        cp = _ejecutar([_CLAUDE, "auth", "status", "--json"], timeout=_TIMEOUT_ESTADO)
    except FileNotFoundError:
        return {"logueado": None, "metodo": None, "proveedor": None, "crudo": "", "error": "claude no disponible"}
    except subprocess.TimeoutExpired:
        return {"logueado": None, "metodo": None, "proveedor": None, "crudo": "", "error": "timeout"}
    parsed = parsear_estado(cp.stdout)
    if cp.returncode != 0 and parsed["logueado"] is None:
        parsed["error"] = _limpiar(cp.stderr).strip() or "estado no disponible"
    return parsed


def _ruta_cache_uso():
    from pathlib import Path

    base = os.environ.get("CLAUDE_CONFIG_DIR") or _cwd_neutro()
    return Path(base) / _FICHERO_USO_CACHE


def _guardar_cache_uso(datos: dict) -> None:
    try:
        ruta = _ruta_cache_uso()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(datos), encoding="utf-8")
        os.replace(tmp, ruta)
    except (OSError, ValueError, TypeError):
        pass


def _cargar_cache_uso() -> dict | None:
    try:
        datos = json.loads(_ruta_cache_uso().read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


def uso() -> dict:
    """Medidor de uso de la suscripción (`claude -p /usage`) con CACHE del último bueno.

    `claude -p /usage` a veces devuelve solo la frase genérica (sin medidor): para no mostrarla
    pelada, persistimos el último medidor bueno en CLAUDE_CONFIG_DIR y, si una lectura no trae
    medidor (o falla/timeout), servimos el último bueno con `cacheado:true`.
    """
    try:
        cp = _ejecutar([_CLAUDE, "-p", "/usage"], timeout=_TIMEOUT_USO)
        parsed = parsear_uso(cp.stdout)
        if cp.returncode != 0 and not parsed["disponible"]:
            parsed["error"] = _limpiar(cp.stderr).strip() or "uso no disponible"
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


def logout() -> dict:
    """Cierra la sesión de Claude (`claude auth logout`). {ok, mensaje}."""
    try:
        cp = _ejecutar([_CLAUDE, "auth", "logout"], timeout=_TIMEOUT_LOGOUT)
    except FileNotFoundError:
        return {"ok": False, "mensaje": "claude no disponible"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "mensaje": "timeout al cerrar sesión"}
    salida = (_limpiar(cp.stdout) + _limpiar(cp.stderr)).strip()
    return {"ok": cp.returncode == 0, "mensaje": salida or ("Sesión cerrada." if cp.returncode == 0 else "Fallo al cerrar sesión.")}


# --------------------------------------------------------------------------- #
# Login INTERACTIVO por PTY: iniciar (-> URL) / enviar_codigo / cancelar.      #
# --------------------------------------------------------------------------- #


@dataclass
class _SesionLogin:
    sid: str
    proc: subprocess.Popen
    master_fd: int
    creada: float
    buffer: str = ""
    url: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_sesiones: dict[str, _SesionLogin] = {}
_sesiones_lock = threading.Lock()


def _leer_disponible(fd: int, *, deadline: float, hasta=None) -> str:
    """Lee del PTY (limpio ANSI) hasta `deadline`, EOF, o —si se da `hasta`— hasta que el texto
    acumulado case ese patrón (clave para cortar en cuanto aparece la URL del login)."""
    trozos: list[str] = []
    while time.monotonic() < deadline:
        restante = max(0.0, deadline - time.monotonic())
        listos, _, _ = select.select([fd], [], [], min(0.5, restante))
        if not listos:
            continue
        try:
            datos = os.read(fd, 4096)
        except OSError:
            break
        if not datos:
            break
        trozos.append(datos.decode("utf-8", errors="replace"))
        if hasta is not None and hasta.search(_limpiar("".join(trozos))):
            break
    return _limpiar("".join(trozos))


def _argv_login(*, console: bool, email: str | None, sso: bool) -> list[str]:
    argv = [_CLAUDE, "auth", "login", "--console" if console else "--claudeai"]
    if email:
        argv += ["--email", email]
    if sso:
        argv += ["--sso"]
    return argv


def _gc_sesiones() -> None:
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
    """Lanza `claude auth login` en un PTY y devuelve {sesion, url, salida} (o {error})."""
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
            start_new_session=True,
        )
    except FileNotFoundError:
        os.close(master_fd)
        os.close(slave_fd)
        return {"error": "claude no disponible en este servidor"}
    os.close(slave_fd)

    salida = _leer_disponible(master_fd, deadline=time.monotonic() + _TIMEOUT_URL, hasta=_RE_URL_COMPLETA)
    m = _RE_URL.search(salida)
    if not m:
        _matar(_SesionLogin(sid="", proc=proc, master_fd=master_fd, creada=time.monotonic()))
        return {"error": "no se obtuvo la URL de autorización", "salida": salida.strip()}

    sid = uuid.uuid4().hex
    sesion = _SesionLogin(sid=sid, proc=proc, master_fd=master_fd, creada=time.monotonic(), buffer=salida, url=m.group(0))
    with _sesiones_lock:
        _sesiones[sid] = sesion
    return {"sesion": sid, "url": sesion.url, "salida": salida.strip()}


def enviar_codigo(sid: str, codigo: str) -> dict:
    """Pega el `codigo` en el PTY de la sesión y espera el cierre. {ok, mensaje, salida}."""
    with _sesiones_lock:
        sesion = _sesiones.pop(sid, None)
    if sesion is None:
        return {"ok": False, "mensaje": "sesión de login desconocida o expirada"}

    with sesion.lock:
        try:
            os.write(sesion.master_fd, (codigo.strip() + "\n").encode("utf-8"))
        except OSError:
            _matar(sesion)
            return {"ok": False, "mensaje": "no se pudo enviar el código (proceso cerrado)"}

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
        mensaje = cola.strip() or ("Cuenta cambiada." if ok else "El login terminó con error.")
        return {"ok": ok, "mensaje": mensaje, "salida": cola.strip()}


def cancelar_login(sid: str) -> dict:
    """Cancela y olvida una sesión de login en curso. {ok}. Idempotente."""
    with _sesiones_lock:
        sesion = _sesiones.pop(sid, None)
    if sesion is None:
        return {"ok": True}
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
    """Mata el GRUPO del proceso de login (líder de sesión) y cierra el PTY. Best-effort."""
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

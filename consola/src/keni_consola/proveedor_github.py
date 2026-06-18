"""Gestion de la CUENTA de GitHub del servidor: estado de auth y CAMBIO de cuenta
(login por device flow + logout) sin reiniciar contenedores. Gemelo de `cuenta_claude.py`.

POR QUE EXISTE: el carril de auto-desarrollo necesita credenciales `gh` para clonar/empujar
en nombre de la cuenta de GitHub de la maquina. Esa cuenta se fija con `gh auth login` desde
el panel Sistema; con `XDG_CONFIG_HOME` apuntando al volumen COMPARTIDO `/data`, la credencial
vive bajo `$XDG_CONFIG_HOME/gh` = `/data/gh`, que `gh` relee en cada invocacion y que worker +
daemons comparten: un login desde el panel cambia la cuenta EN CALIENTE para ambos, sin reinicio.

DONDE CORRE: SOLO en la imagen del worker (worker/daemons), que lleva el binario `gh`. El
`back` NO tiene `gh`: alcanza estas funciones por el listener de control del proceso `daemons`
(ver `control.py`). Por eso este modulo NO importa de `api/`.

DEVICE FLOW: `gh auth login --hostname github.com --git-protocol https --web` lanza el flujo de
device de GitHub: imprime un one-time code y la url `https://github.com/login/device`, espera un
Enter para arrancar el sondeo y luego SONDEA solo hasta que el humano autoriza el code en el
navegador. NO hay que pegar nada de vuelta: `confirmar_login` solo espera a que el proceso `gh`
cierre con exito. Fallback aceptado: `gh auth login --with-token` si la sesion trae un PAT pegado.

SEPARACION testeable: los PARSERS (`parsear_estado`, `parsear_inicio`) son puros (texto->dict)
y se testean sin subprocess; los RUNNERS (`estado`, `logout`) y el gestor de login por PTY
tocan el sistema. Reusa los helpers genericos de PTY/proceso y el bearer de `cuenta_claude`
(un unico secreto de control para todo el listener).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field

from .cuenta_claude import (
    _cerrar_fd,
    _cwd_neutro,
    _ejecutar,
    _leer_disponible,
    _limpiar,
    _matar,
    bearer_efectivo,  # reexport: el listener de control usa un unico bearer compartido
)

_log = logging.getLogger("keni_consola.proveedor_github")

__all__ = [
    "bearer_efectivo",
    "parsear_estado",
    "parsear_inicio",
    "estado",
    "iniciar_login",
    "confirmar_login",
    "cancelar_login",
    "logout",
]

# Binario del CLI de GitHub. PATH del contenedor del worker/daemons.
_GH = "gh"

# Url de device flow de GitHub: constante conocida (gh no siempre la imprime entera).
_DEVICE_URL = "https://github.com/login/device"

# Wall-timeouts (s).
_TIMEOUT_ESTADO = 30
_TIMEOUT_LOGOUT = 30
# Login: cuanto esperamos a que `gh` emita el one-time code tras lanzar el flujo, y cuanto
# esperamos en `confirmar` a que el sondeo de gh cierre tras autorizar el code el humano.
_TIMEOUT_CODIGO = 45
_TIMEOUT_CONFIRMAR = 75
# Una sesion de login abandonada (code emitido, nunca autorizado) se mata pasado esto. El
# device code de GitHub caduca a ~15 min.
_TTL_SESION_LOGIN = 900.0

# One-time code: la etiqueta de gh ("First copy your one-time code: ABCD-1234") ancla la
# captura para no confundirlo con otro token de la salida.
_RE_CODIGO = re.compile(r"one-time code:\s*([A-Za-z0-9]{4}-[A-Za-z0-9]{4})", re.IGNORECASE)
# Para CORTAR la lectura: el code SEGUIDO de un espacio/salto garantiza que llego ENTERO.
_RE_CODIGO_COMPLETO = re.compile(
    r"one-time code:\s*[A-Za-z0-9]{4}-[A-Za-z0-9]{4}\s", re.IGNORECASE
)
# Url de device por si gh la imprime (algunas versiones solo dicen "github.com").
_RE_URL_DEVICE = re.compile(r"https://\S*github\.com/login/device\S*")

# `gh auth status` (texto): usuario y scopes del token.
_RE_USUARIO = re.compile(r"Logged in to \S+ (?:account|as) (\S+)", re.IGNORECASE)
_RE_SCOPES = re.compile(r"Token scopes:\s*(.+)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Parsers PUROS (texto -> dict). Sin subprocess: testeables en aislamiento.    #
# --------------------------------------------------------------------------- #


def parsear_estado(salida: str) -> dict:
    """Parsea el estado de auth de `gh` -> {logueado, usuario, scopes, crudo}.

    Acepta dos formas: el JSON de `gh api user` (el login viene en el cuerpo) o el texto de
    `gh auth status` (usuario y scopes en lineas legibles). Tolerante: si no reconoce nada,
    devuelve `logueado=None` con el texto crudo para que la UI muestre "desconocido".
    """
    base = {"logueado": None, "usuario": None, "scopes": []}
    crudo = _limpiar(salida).strip()
    if not crudo:
        return {**base, "crudo": crudo}

    # Forma JSON (`gh api user`): el login viene en el cuerpo.
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        datos = None
    if isinstance(datos, dict) and datos.get("login"):
        return {"logueado": True, "usuario": str(datos["login"]), "scopes": [], "crudo": crudo}

    # Forma texto (`gh auth status`).
    logueado: bool | None = None
    if re.search(r"logged in to", crudo, re.IGNORECASE):
        logueado = True
    elif re.search(r"not logged in", crudo, re.IGNORECASE):
        logueado = False
    mu = _RE_USUARIO.search(crudo)
    usuario = mu.group(1).strip("'\"") if mu else None
    scopes: list[str] = []
    ms = _RE_SCOPES.search(crudo)
    if ms:
        scopes = [s.strip().strip("'\"") for s in ms.group(1).split(",") if s.strip()]
    return {"logueado": logueado, "usuario": usuario, "scopes": scopes, "crudo": crudo}


def parsear_inicio(salida: str) -> dict:
    """Extrae el one-time code y la url de device del arranque de `gh auth login --web`.

    `codigo` es el code que el humano teclea en `https://github.com/login/device`. `url` se
    extrae si gh la imprime; si no, cae a la constante conocida del device flow.
    """
    texto = _limpiar(salida)
    mc = _RE_CODIGO.search(texto)
    mu = _RE_URL_DEVICE.search(texto)
    return {
        "codigo": mc.group(1) if mc else None,
        "url": mu.group(0) if mu else _DEVICE_URL,
    }


# --------------------------------------------------------------------------- #
# Runners NO interactivos (subprocess). Estado / logout.                       #
# --------------------------------------------------------------------------- #


def estado() -> dict:
    """Estado de autenticacion (`gh auth status`) parseado a {logueado, usuario, scopes}."""
    try:
        cp = _ejecutar([_GH, "auth", "status"], timeout=_TIMEOUT_ESTADO)
    except FileNotFoundError:
        return {"logueado": None, "usuario": None, "scopes": [], "crudo": "", "error": "gh no disponible"}
    except subprocess.TimeoutExpired:
        return {"logueado": None, "usuario": None, "scopes": [], "crudo": "", "error": "timeout"}
    # `gh auth status` escribe tanto en stdout como en stderr segun la version: combinamos.
    parsed = parsear_estado((cp.stdout or "") + "\n" + (cp.stderr or ""))
    if cp.returncode != 0 and parsed["logueado"] is None:
        parsed["logueado"] = False
    return parsed


def logout() -> dict:
    """Cierra la sesion de GitHub (`gh auth logout --hostname github.com`). {ok, mensaje}."""
    try:
        cp = _ejecutar([_GH, "auth", "logout", "--hostname", "github.com"], timeout=_TIMEOUT_LOGOUT)
    except FileNotFoundError:
        return {"ok": False, "mensaje": "gh no disponible"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "mensaje": "timeout al cerrar sesion"}
    salida = (_limpiar(cp.stdout) + _limpiar(cp.stderr)).strip()
    ok = cp.returncode == 0
    return {"ok": ok, "mensaje": salida or ("Sesion de GitHub cerrada." if ok else "Fallo al cerrar sesion.")}


# --------------------------------------------------------------------------- #
# Login por DEVICE FLOW (PTY): iniciar (-> code+url) / confirmar / cancelar.   #
# --------------------------------------------------------------------------- #
#
# `gh auth login --web` es interactivo: necesita una TTY (de ahi el PTY), imprime el one-time
# code, espera un Enter para arrancar y luego SONDEA solo hasta que el humano autoriza el code.
# Lo modelamos como una SESION en memoria de vida corta:
#   iniciar_login()      lanza gh, lee hasta ver el code, manda el Enter y devuelve {code,url}
#   confirmar_login(sid) espera a que el proceso gh cierre (el sondeo termino tras autorizar)
#   cancelar_login(sid)  mata el proceso
# El proceso `daemons` es de INSTANCIA UNICA, asi que el registro en memoria es seguro. Un
# limpiador perezoso mata sesiones abandonadas (code emitido, nunca autorizado).


@dataclass
class _SesionLogin:
    sid: str
    proc: subprocess.Popen
    master_fd: int
    creada: float
    buffer: str = ""  # todo lo leido del PTY (limpio de ANSI), para mostrar/depurar
    codigo: str | None = None
    url: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_sesiones: dict[str, _SesionLogin] = {}
_sesiones_lock = threading.Lock()


def _argv_login() -> list[str]:
    """argv del device flow de gh (hostname y protocolo fijados para evitar prompts extra)."""
    return [_GH, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web"]


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


def _login_con_token(token: str) -> dict:
    """Fallback no interactivo: `gh auth login --with-token` con un PAT por stdin. {ok, mensaje}."""
    argv = [_GH, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--with-token"]
    try:
        cp = subprocess.run(  # noqa: S603 -- argv lista, sin shell
            argv,
            cwd=_cwd_neutro(),
            input=token.strip() + "\n",
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_CONFIRMAR,
        )
    except FileNotFoundError:
        return {"error": "gh no disponible en este servidor"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "mensaje": "timeout al validar el token"}
    salida = (_limpiar(cp.stdout) + _limpiar(cp.stderr)).strip()
    ok = cp.returncode == 0
    return {"ok": ok, "mensaje": salida or ("Cuenta de GitHub conectada." if ok else "El token fue rechazado.")}


def iniciar_login(*, token: str | None = None) -> dict:
    """Arranca el login de GitHub. Con `token` usa el fallback `--with-token`; si no, device flow.

    Device flow: lanza `gh auth login --web` en un PTY, lee hasta ver el one-time code (o agotar
    `_TIMEOUT_CODIGO`), manda el Enter para que gh empiece a SONDEAR y devuelve
    {sesion, codigo, url, salida}. La sesion queda VIVA hasta `confirmar_login`/`cancelar_login`.
    Si no aparece el code, mata el proceso y reporta la salida capturada.
    """
    import pty

    if token and token.strip():
        return _login_con_token(token)

    _gc_sesiones()
    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(  # noqa: S603 -- argv lista, sin shell
            _argv_login(),
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
        return {"error": "gh no disponible en este servidor"}
    os.close(slave_fd)  # el hijo ya tiene su copia; el padre lee/escribe por master_fd

    salida = _leer_disponible(
        master_fd, deadline=time.monotonic() + _TIMEOUT_CODIGO, hasta=_RE_CODIGO_COMPLETO
    )
    inicio = parsear_inicio(salida)
    if not inicio["codigo"]:
        # Sin code: aborta y reporta. (gh pudo morir o pedir algo inesperado.)
        s_tmp = _SesionLogin(sid="", proc=proc, master_fd=master_fd, creada=time.monotonic())
        _matar(s_tmp)
        return {"error": "no se obtuvo el one-time code de GitHub", "salida": salida.strip()}

    # Manda el Enter: gh deja de esperar y arranca el sondeo del device flow mientras el humano
    # autoriza el code en el navegador.
    try:
        os.write(master_fd, b"\n")
    except OSError:
        pass

    sid = uuid.uuid4().hex
    sesion = _SesionLogin(
        sid=sid,
        proc=proc,
        master_fd=master_fd,
        creada=time.monotonic(),
        buffer=salida,
        codigo=inicio["codigo"],
        url=inicio["url"],
    )
    with _sesiones_lock:
        _sesiones[sid] = sesion
    return {"sesion": sid, "codigo": sesion.codigo, "url": sesion.url, "salida": salida.strip()}


def confirmar_login(sid: str) -> dict:
    """Espera a que el sondeo de `gh` cierre tras autorizar el code. {ok, mensaje, salida}.

    Exito = el proceso gh termina con returncode 0. Si aun esta sondeando (el humano no ha
    autorizado todavia), la sesion sigue VIVA y se puede reintentar; no se mata aqui.
    """
    with _sesiones_lock:
        sesion = _sesiones.get(sid)
    if sesion is None:
        return {"ok": False, "mensaje": "sesion de login desconocida o expirada"}

    with sesion.lock:
        deadline = time.monotonic() + _TIMEOUT_CONFIRMAR
        cola = _leer_disponible(sesion.master_fd, deadline=deadline)
        sesion.buffer += cola
        try:
            rc = sesion.proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            # gh sigue sondeando: deja la sesion viva para reintentar.
            return {
                "ok": False,
                "mensaje": "el login aun no se ha completado; autoriza el codigo y reintenta",
                "salida": cola.strip(),
            }

    with _sesiones_lock:
        _sesiones.pop(sid, None)
    _cerrar_fd(sesion.master_fd)
    ok = rc == 0
    mensaje = cola.strip() or ("Cuenta de GitHub conectada." if ok else "El login termino con error.")
    return {"ok": ok, "mensaje": mensaje, "salida": cola.strip()}


def cancelar_login(sid: str) -> dict:
    """Cancela y olvida una sesion de login en curso. {ok}."""
    with _sesiones_lock:
        sesion = _sesiones.pop(sid, None)
    if sesion is None:
        return {"ok": True}  # idempotente: ya no existia
    _matar(sesion)
    return {"ok": True}

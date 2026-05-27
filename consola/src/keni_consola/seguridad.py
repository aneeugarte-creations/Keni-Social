"""Autenticacion + proteccion CSRF de la Consola Keni (issue #134).

CONTEXTO DEL HALLAZGO
=====================
La Consola escucha en `127.0.0.1` (ver `__main__.py`), pero ESO NO ES CONTROL DE
ACCESO: cualquier pagina web abierta en el navegador del operador puede lanzar un
POST a `http://127.0.0.1:8765/api/...` (los POST "simples" no disparan preflight
CORS) y disparar acciones que GASTAN TOKENS, ESCRIBEN FICHEROS o PUBLICAN. Esto
anade una barrera minima (NO multiusuario, eso es #130):

  1) TOKEN DE SESION para la API. Se configura con la env var `KENI_CONSOLA_TOKEN`.
     Si no se define, se genera uno aleatorio al arrancar y se MUESTRA en el log
     (asi el modo local sigue siendo usable sin configurar nada). El token se
     acepta por cabecera (`Authorization: Bearer <t>` o `X-Keni-Token: <t>`) o por
     cookie `keni_consola_token` (que el propio servidor siembra al servir el SPA,
     para que las descargas por `window.open` y las `<img src>` —que NO pueden
     mandar cabeceras— sigan funcionando).

  2) PROTECCION CSRF en MUTACIONES (POST/PUT/PATCH/DELETE). Como el token tambien
     viaja por cookie (que el navegador envia automaticamente, incluso desde otro
     sitio), se verifica ADEMAS el `Origin`/`Referer` de la peticion contra el host
     esperado (el propio `127.0.0.1:PUERTO`). Una pagina atacante tendra un `Origin`
     ajeno -> 403. El SPA propio comparte origen -> pasa. Asi una cookie robada por
     CSRF no basta para mutar.

QUE SE PROTEGE Y QUE NO
=======================
  - Todo lo que empieza por `/api` exige token (lectura y mutacion). Las MUTACIONES
    exigen ademas Origin/Referer del mismo host.
  - El SPA y sus estaticos (`/`, `/assets/*`, favicons) NO exigen token: hay que
    poder cargar la pagina para luego autenticar las llamadas. El index del SPA
    siembra la cookie del token (modo local) para que la UI funcione sin pasos.

El SPA tambien manda el token por cabecera (`api.ts` lo lee de `window.__KENI_TOKEN__`,
inyectado en el index), de modo que la cookie es defensa en profundidad y no el unico
camino.

AUTH MULTIUSUARIO (#130)
========================
Sobre la barrera de token unico se monta el login user/pass + roles (ver `auth.py`).
El middleware ahora acepta para `/api` CUALQUIERA de estas dos credenciales:

  1) Una SESION valida: cookie `keni_consola_sesion` con un token de sesion vigente
     (tabla `sesiones`). Es el camino del multiusuario real.
  2) El TOKEN de bootstrap de #134 (cabecera Bearer/X-Keni-Token o cookie
     `keni_consola_token`). SIGUE VALIENDO para no romper clientes/tests existentes.

`/api/auth/login` es PUBLICO (no exige credencial previa) pero pasa por la verificacion
Origin/CSRF de las mutaciones. Las rutas `/api/usuarios/*` exigen ADEMAS rol admin (lo
comprueba el propio handler leyendo `request.state.usuario`, que este middleware fija).
"""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import urlsplit

from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from . import auth
from .observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Env var que fija el token de sesion. Si no esta, se genera uno al arrancar.
ENV_TOKEN = "KENI_CONSOLA_TOKEN"

# Nombre de la cookie en la que el servidor siembra el token (para GET por navegacion
# y `<img>`, que no pueden mandar cabeceras). NO es HttpOnly a proposito: el SPA podria
# necesitar leerla; la defensa CSRF no depende del secreto de la cookie sino del Origin.
COOKIE_TOKEN = "keni_consola_token"

# Cabeceras admitidas para el token (ademas de la cookie).
CABECERA_BEARER = "authorization"
CABECERA_TOKEN = "x-keni-token"

# Metodos que MUTAN estado: exigen verificacion CSRF (Origin/Referer del mismo host).
_METODOS_MUTANTES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Mensajes (en espanol, forma `{"error": ...}` del proyecto).
_MSG_NO_AUTORIZADO = "No autorizado: falta el token de la Consola o es incorrecto."
_MSG_CSRF = "Solicitud rechazada: origen no permitido (proteccion CSRF)."


def token_configurado() -> str | None:
    """Token fijado por `KENI_CONSOLA_TOKEN` (None si no esta). Vacio cuenta como no fijado."""
    crudo = os.environ.get(ENV_TOKEN, "").strip()
    return crudo or None


def generar_token() -> str:
    """Genera un token de sesion aleatorio (url-safe, ~256 bits)."""
    return secrets.token_urlsafe(32)


def _token_de_la_peticion(scope: Scope) -> str | None:
    """Extrae el token de la peticion: cabecera Bearer, X-Keni-Token o cookie."""
    cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

    autorizacion = cabeceras.get(CABECERA_BEARER, "")
    if autorizacion.lower().startswith("bearer "):
        valor = autorizacion[len("bearer "):].strip()
        if valor:
            return valor

    x_token = cabeceras.get(CABECERA_TOKEN, "").strip()
    if x_token:
        return x_token

    # Cookie (sembrada por el index del SPA). Parseo minimal sin dependencias.
    cookie = cabeceras.get("cookie", "")
    for parte in cookie.split(";"):
        nombre, _, valor = parte.strip().partition("=")
        if nombre == COOKIE_TOKEN and valor:
            return valor.strip()

    return None


def _cookie(scope: Scope, nombre: str) -> str | None:
    """Lee el valor de una cookie de la peticion por su `nombre` (None si no esta)."""
    cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    cookie = cabeceras.get("cookie", "")
    for parte in cookie.split(";"):
        clave, _, valor = parte.strip().partition("=")
        if clave == nombre and valor:
            return valor.strip()
    return None


def _host_esperado(scope: Scope) -> str | None:
    """Host:puerto al que se dirigio la peticion (cabecera Host)."""
    for k, v in scope.get("headers", []):
        if k.decode("latin-1").lower() == "host":
            return v.decode("latin-1").strip().lower()
    return None


def _origen_mismo_host(scope: Scope) -> bool:
    """True si `Origin`/`Referer` apuntan al MISMO host:puerto que la peticion.

    Defensa CSRF: una mutacion solo se acepta si su origen declarado coincide con el
    host de la Consola. Si NO hay ni `Origin` ni `Referer` (algunos clientes/curl), se
    deja pasar: la barrera CSRF protege contra el NAVEGADOR de un tercero, que SIEMPRE
    manda `Origin` en peticiones cross-site con cuerpo; un cliente sin navegador que ya
    tiene el token no es el modelo de amenaza de CSRF.
    """
    host = _host_esperado(scope)
    cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

    origen = cabeceras.get("origin", "").strip()
    if origen:
        return _host_de_url(origen) == host

    referer = cabeceras.get("referer", "").strip()
    if referer:
        return _host_de_url(referer) == host

    # Sin Origin ni Referer: no es una peticion de navegador cross-site. Pasa.
    return True


def _host_de_url(url: str) -> str | None:
    """Devuelve `host:puerto` (en minusculas) de una URL, o None si no parsea."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return None
    if not partes.netloc:
        return None
    # netloc incluye el puerto si lo hay; quitamos credenciales si las hubiera.
    netloc = partes.netloc.rsplit("@", 1)[-1]
    return netloc.lower()


# Rutas /api PUBLICAS (no exigen credencial previa). El login crea la sesion; aun
# asi pasa por la verificacion Origin/CSRF de las mutaciones (es un POST).
_RUTAS_API_PUBLICAS = frozenset({"/api/auth/login"})

# Si el usuario de la sesion tiene `debe_cambiar_password`, SOLO puede ver su sesion,
# cambiar la contrasena o salir. Cualquier otra ruta /api -> 403 (enforcement en el
# servidor, no solo en el frontend). El acceso por token de bootstrap no esta sujeto.
_RUTAS_API_CAMBIO_PASSWORD = frozenset(
    {"/api/auth/me", "/api/auth/cambiar-password", "/api/auth/logout"}
)
_MSG_DEBE_CAMBIAR = "Debes cambiar tu contraseña antes de usar la Consola."


class SeguridadConsola:
    """Middleware ASGI: sesion/token para `/api` + CSRF en mutaciones (#134 + #130).

    - Las rutas que NO empiezan por `/api` (SPA, assets, favicons) pasan SIN credencial:
      hay que poder cargar la pagina. El index siembra la cookie del token.
    - `/api/auth/login` es PUBLICO (crea la sesion) pero pasa por el chequeo CSRF.
    - El resto de `/api/...`: exige UNA sesion valida (cookie `keni_consola_sesion`) O
      el token de bootstrap (cabecera/cookie). Si falta o no vale -> 401.
    - Mutaciones (`POST/PUT/PATCH/DELETE`) sobre `/api`: exigen ADEMAS que el
      `Origin`/`Referer` sea del mismo host -> si no, 403 (CSRF).

    Cuando autentica por sesion, deja el usuario en `scope["state"]["usuario"]` (lo lee
    `request.state.usuario`) para que los handlers comprueben el rol. Si autentica por
    token de bootstrap, NO hay usuario asociado: cuenta como acceso de mantenimiento con
    plenos permisos (equivalente a admin para las rutas que solo miran el rol).

    El token se compara con `secrets.compare_digest` (tiempo constante). Solo actua
    sobre `scope["type"] == "http"`; el resto pasa intacto.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ruta = scope.get("path", "")
        if not ruta.startswith("/api"):
            # SPA / estaticos: sin credencial. (El index siembra la cookie aparte.)
            await self.app(scope, receive, send)
            return

        metodo = scope.get("method", "GET").upper()

        # Estado de la peticion: por defecto, sin usuario de sesion (acceso por token).
        estado = scope.setdefault("state", {})
        estado["usuario"] = None
        estado["auth_por_token"] = False

        publica = ruta in _RUTAS_API_PUBLICAS
        if not publica:
            # 1) Credencial: sesion valida (cookie) O token de bootstrap.
            usuario = self._usuario_de_sesion(scope)
            if usuario is not None:
                estado["usuario"] = usuario
            elif self._token_valido(scope):
                estado["auth_por_token"] = True
            else:
                await _rechazar(scope, receive, send, _MSG_NO_AUTORIZADO, 401)
                return

        # 1b) Si el usuario de la sesion debe cambiar su contrasena, solo le dejamos las
        # rutas para hacerlo (ver/cambiar/salir); cualquier otra /api -> 403. Asi el
        # "cambio forzado" se aplica en el SERVIDOR, no solo en el frontend. El acceso por
        # token de bootstrap (mantenimiento, sin usuario) no esta sujeto a esto.
        usuario_sesion = estado["usuario"]
        if (
            usuario_sesion is not None
            and usuario_sesion.get("debe_cambiar_password")
            and ruta not in _RUTAS_API_CAMBIO_PASSWORD
        ):
            await _rechazar(scope, receive, send, _MSG_DEBE_CAMBIAR, 403)
            return

        # 2) CSRF en mutaciones: Origin/Referer del mismo host (tambien en el login).
        if metodo in _METODOS_MUTANTES and not _origen_mismo_host(scope):
            await _rechazar(scope, receive, send, _MSG_CSRF, 403)
            return

        await self.app(scope, receive, send)

    def _token_valido(self, scope: Scope) -> bool:
        """True si la peticion trae el token de bootstrap correcto (tiempo constante)."""
        presentado = _token_de_la_peticion(scope)
        return presentado is not None and secrets.compare_digest(presentado, self._token)

    def _usuario_de_sesion(self, scope: Scope) -> dict | None:
        """Usuario (forma publica) si la cookie de sesion es valida y vigente; si no, None."""
        token_sesion = _cookie(scope, auth.COOKIE_SESION)
        if not token_sesion:
            return None
        return auth.sesion_valida(token_sesion)


async def _rechazar(scope: Scope, receive: Receive, send: Send, mensaje: str, status: int) -> None:
    """Envia una respuesta JSON de rechazo (`{"error": ...}`) con el status dado."""
    respuesta: Response = JSONResponse({"error": mensaje}, status_code=status)
    await respuesta(scope, receive, send)


def resolver_token() -> tuple[str, bool]:
    """Devuelve `(token, generado)`: el de la env var o uno nuevo si no estaba.

    `generado=True` indica que se creo uno aleatorio (hay que mostrarlo en el log).
    """
    fijo = token_configurado()
    if fijo is not None:
        return fijo, False
    return generar_token(), True


def inyectar_token_en_html(html: str, token: str) -> str:
    """Inyecta `window.__KENI_TOKEN__` en el `<head>` del index del SPA.

    Asi el cliente (`api.ts`) puede mandar el token por cabecera ademas de la cookie.
    Es best-effort: si no hay `<head>`, devuelve el HTML sin tocar (la cookie basta).
    """
    snippet = f'<script>window.__KENI_TOKEN__={_json_seguro(token)};</script>'
    marca = "<head>"
    idx = html.find(marca)
    if idx == -1:
        return html
    corte = idx + len(marca)
    return html[:corte] + snippet + html[corte:]


def _json_seguro(valor: str) -> str:
    """Serializa una cadena para incrustar en `<script>` sin romper el HTML."""
    import json

    # Escapamos `<` para que un `</script>` accidental no cierre el bloque.
    return json.dumps(valor).replace("<", "\\u003c")

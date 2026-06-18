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
     cookie `keni_consola_token` (que el propio servidor escribe al servir el SPA,
     para que las descargas por `window.open` y las `<img src>` —que NO pueden
     mandar cabeceras— sigan funcionando).

  2) PROTECCION CSRF en MUTACIONES (POST/PUT/PATCH/DELETE). Como las credenciales
     tambien viajan por cookie (que el navegador envia automaticamente, incluso desde
     otro sitio), se verifica ADEMAS el `Origin`/`Referer` de la peticion contra el host
     esperado. En LOCAL (127.0.0.1, sin proxy) el host esperado es el propio `Host` de la
     peticion (`127.0.0.1:PUERTO`). Detras de un reverse-proxy (Traefik) el host publico
     es otro (`social.kenitech.io`) y el back ve cabeceras reenviadas; por eso se admite
     ademas una ALLOWLIST configurable de hosts externos (`KENI_CONSOLA_ORIGENES`): una
     mutacion pasa si su `Origin`/`Referer` coincide con el `Host` de la peticion O con
     uno de los hosts permitidos. Una pagina atacante tendra un `Origin` ajeno -> 403. El
     SPA propio comparte origen -> pasa. Asi una cookie robada por CSRF no basta para mutar.

QUE SE PROTEGE Y QUE NO
=======================
  - Todo lo que empieza por `/api` exige token (lectura y mutacion). Las MUTACIONES
    exigen ademas Origin/Referer del mismo host.
  - El SPA y sus estaticos (`/`, `/assets/*`, favicons) NO exigen token: hay que
    poder cargar la pagina para luego autenticar las llamadas. El index del SPA
    escribe la cookie del token (modo local) para que la UI funcione sin pasos.

El SPA tambien manda el token por cabecera (`api.ts` lo lee de `window.__KENI_TOKEN__`,
inyectado en el index), de modo que la cookie es defensa en profundidad y no el unico
camino.

AUTH MULTIUSUARIO (#130) — Y EL TOKEN AHORA ES OPCIONAL
=======================================================
Sobre la barrera de token unico se monta el login user/pass + roles (ver `auth.py`).
El middleware acepta para `/api` CUALQUIERA de estas credenciales:

  1) Una SESION valida: cookie `keni_consola_sesion` con un token de sesion vigente
     (tabla `sesiones`). Es el camino del multiusuario real y la barrera PRINCIPAL.
  2) El TOKEN interino de #134 (cabecera Bearer/X-Keni-Token o cookie
     `keni_consola_token`), SI ESTA CONFIGURADO. Es un gate EXTRA opcional: sigue
     valiendo para clientes de mantenimiento/tests, pero el despliegue YA NO depende de
     el. Si no se fija (`token=None`), esa via simplemente NO existe y la unica credencial
     valida es la sesion: una peticion sin sesion -> 401 igualmente. NO se debilita nada.

`/api/auth/login` es PUBLICO (no exige credencial previa) pero pasa por la verificacion
Origin/CSRF de las mutaciones. Las rutas `/api/usuarios/*` exigen ADEMAS rol admin de un
usuario REAL (lo comprueba el propio handler leyendo `request.state.usuario`, que este
middleware fija). El TOKEN de mantenimiento NO es admin (#150): pasa la barrera de `/api`
(es una credencial de mantenimiento), pero NO otorga poder admin sobre `/api/usuarios/*`;
la unica excepcion es el bootstrap del primer admin con la BD vacia (ver `api/usuarios`).
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlsplit

from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from . import auth, config
from .observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Nombres de las env vars de auth/cookies. Canonicos en `config` (fuente unica);
# re-exportados aqui porque los tests y otros call sites referencian `seguridad.ENV_*`.
# Env var del token INTERINO opcional. Si no esta, la Consola se protege con sesion + CSRF.
ENV_TOKEN = config.ENV_TOKEN
# Env var de la allowlist de hosts externos para el chequeo CSRF detras de un proxy.
ENV_ORIGENES = config.ENV_ORIGENES
# Flags (env) que marcan la cookie de sesion y la del token como `Secure` (solo viajan
# por HTTPS). Default OFF: el modo local es HTTP plano y debe seguir funcionando (y los
# tests no lo activan). En contenedor detras de un proxy TLS se pone a "1" para que el
# navegador no mande las cookies por HTTP. `KENI_CONSOLA_COOKIE_SECURE` manda; si no se
# fija, se deriva de `KENI_CONSOLA_HTTPS` (el mismo flag que dice "vamos detras de TLS").
ENV_COOKIE_SECURE = config.ENV_COOKIE_SECURE
ENV_HTTPS = config.ENV_HTTPS

# Nombre de la cookie en la que el servidor escribe el token (para GET por navegacion
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
    return config.token()


def cookie_secure() -> bool:
    """¿Marcar las cookies como `Secure`? (solo viajan por HTTPS).

    Lo manda `KENI_CONSOLA_COOKIE_SECURE`; si no se fija, se deriva de `KENI_CONSOLA_HTTPS`.
    Default `False`: el modo local (HTTP plano) sigue funcionando y los tests no lo activan.
    En contenedor detras de un proxy TLS se pone a "1". Logica centralizada en `config`.
    """
    return config.cookie_secure()


def origenes_permitidos() -> frozenset[str]:
    """Hosts externos permitidos para el chequeo CSRF (`KENI_CONSOLA_ORIGENES`).

    Vacio (def) en local: el chequeo compara solo contra el `Host` de la peticion. Detras
    de un proxy se fija al host publico (`social.kenitech.io`). Logica/parseo en `config`.
    """
    return config.origenes_permitidos()


def mfa_habilitado() -> bool:
    """¿El segundo factor es OBLIGATORIO PARA TODOS? (`KENI_CONSOLA_MFA`, def OFF).

    Wrapper sobre `config.mfa_habilitado()` (fuente unica). Matiz tras el rediseño de opt-in:
    este flag YA NO decide si el MFA "existe" (eso lo decide la clave; ver
    `mfa_maquinaria_activa`), sino si se FUERZA a TODO el equipo a tener passkey. Con el flag
    OFF el MFA sigue disponible como OPT-IN por usuario (y obligatorio para admins por
    `mfa_obligatorio_admin`); con el flag ON ademas se obliga a los editores.
    """
    return config.mfa_habilitado()


def mfa_obligatorio_admin() -> bool:
    """¿El segundo factor es OBLIGATORIO para los admins? (`KENI_CONSOLA_MFA_ADMIN`, def ON).

    Wrapper sobre `config.mfa_obligatorio_admin()`. A diferencia del flag global (OFF), aqui el
    default es ON: un admin que publica en canales de marca sin passkey es riesgo de
    account-takeover. La ejecucion real (exigir ceremonia / forzar inscripcion) la decide
    `api/auth`, y SOLO cuando hay clave de firma (`mfa_key_presente`), para no dejar a nadie fuera.
    """
    return config.mfa_obligatorio_admin()


def mfa_key_presente() -> bool:
    """True si hay clave de firma WebAuthn (`KENI_CONSOLA_MFA_KEY`). Wrapper sobre `config`.

    `api/auth` lo usa para NO forzar el MFA de admin sin clave (evita lockout): sin clave no se
    puede firmar la cookie de challenge/pre-auth ni completar la inscripcion.
    """
    return config.mfa_key_presente()


def mfa_maquinaria_activa() -> bool:
    """¿Está OPERATIVA la maquinaria MFA (ceremonias + enrolamiento)? Fuente única de la UI/API.

    El MFA es OPT-IN POR USUARIO: la maquinaria está activa cuando hay clave de firma
    (`KENI_CONSOLA_MFA_KEY`), con eso CUALQUIER usuario puede inscribir su passkey desde "Mi
    cuenta" y, si la tiene, su login la exige. El flag global solo añade obligación para
    todos (no cambia la disponibilidad). Sin clave NO está activa (no se puede firmar nada):
    ni se ofrece enrolar ni se eleva el login. Lo consultan los endpoints de enrolamiento, la
    elevación del login y `me.mfa_habilitado` (visibilidad de la sección de llaves).
    """
    return config.mfa_habilitado() or config.mfa_key_presente()


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

    # Cookie (inicializada por el index del SPA). Parseo minimal sin dependencias.
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
    """True si `Origin`/`Referer` apuntan a un host PERMITIDO para esta peticion.

    Defensa CSRF: una mutacion solo se acepta si su origen declarado coincide con un host
    de confianza. Hosts de confianza =
      - el `Host` de la propia peticion (caso LOCAL 127.0.0.1, sin proxy: el SPA comparte
        origen con el back), y
      - la ALLOWLIST `KENI_CONSOLA_ORIGENES` (caso DETRAS DE PROXY: Traefik termina TLS en
        `social.kenitech.io` y el `Origin` del navegador es ese host publico; el `Host`
        que el back ve puede no coincidir byte a byte con el publico, asi que NO basta con
        compararlo solo contra el `Host`).
    En local la allowlist esta vacia y solo cuenta el `Host`: comportamiento INTACTO.

    Si NO hay ni `Origin` ni `Referer` (algunos clientes/curl), se deja pasar: la barrera
    CSRF protege contra el NAVEGADOR de un tercero, que SIEMPRE manda `Origin` en peticiones
    cross-site con cuerpo; un cliente sin navegador que ya tiene credencial no es el modelo
    de amenaza de CSRF.
    """
    host = _host_esperado(scope)
    permitidos = origenes_permitidos()
    cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

    origen = cabeceras.get("origin", "").strip()
    if origen:
        return _host_de_confianza(_host_de_url(origen), host, permitidos)

    referer = cabeceras.get("referer", "").strip()
    if referer:
        return _host_de_confianza(_host_de_url(referer), host, permitidos)

    # Sin Origin ni Referer: no es una peticion de navegador cross-site. Pasa.
    return True


def _host_de_confianza(host_declarado: str | None, host_peticion: str | None, permitidos: frozenset[str]) -> bool:
    """True si `host_declarado` (del Origin/Referer) coincide con el Host o la allowlist.

    `permitidos` ya viene normalizado a `host[:puerto]` en minusculas (ver `config`). Si
    el origen no parsea (`host_declarado is None`) -> False: un Origin presente pero ilegible
    se rechaza (no se confunde con "sin Origin", que es otra rama y SI pasa).
    """
    if host_declarado is None:
        return False
    if host_peticion is not None and host_declarado == host_peticion:
        return True
    return host_declarado in permitidos


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


# Rutas /api PUBLICAS (no exigen credencial previa / sesion COMPLETA). El login crea la
# sesion; aun asi pasan por la verificacion Origin/CSRF de las mutaciones (son POST).
#   - `/api/auth/mfa/login/opciones` y `/api/auth/mfa/verify`: SEGUNDO PASO del login con MFA
#     (passkeys). Solo se alcanzan con la cookie PRE-AUTH de corta vida (factor-1 superado, sin
#     sesion real). NO son una sesion: `login/opciones` arma las opciones WebAuthn y escribe la
#     cookie de challenge; `verify` valida la assertion (o un recovery) antes de emitir la sesion
#     real. Que sean publicas NO debilita nada: un estado factor-1-only NUNCA alcanza otro `/api`
#     (esos siguen exigiendo sesion COMPLETA). El enrolamiento (`/api/auth/mfa/registro/*`,
#     `/api/auth/mfa/credenciales`, `/api/auth/mfa/disable`) NO es publico: exige sesion completa.
#   - `/api/auth/passkey/opciones` y `/api/auth/passkey/verify`: login PASSWORDLESS (la passkey
#     es la unica prueba, sin usuario/contrasena previos). `verify` exige user-verification y solo
#     emite la sesion si la assertion cuadra criptograficamente contra la clave publica guardada.
_RUTAS_API_PUBLICAS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/mfa/login/opciones",
        "/api/auth/mfa/verify",
        "/api/auth/passkey/opciones",
        "/api/auth/passkey/verify",
    }
)

# GET de un objeto de media (`/api/media/<nombre>`) SIN credencial: los schedulers externos
# (Metricool) ingieren la imagen/video del post por esta URL y no tienen sesion. Es una
# CAPABILITY URL: el nombre es content-addressed/uuid (indescifrable sin conocerlo) y el
# contenido es media DESTINADA A PUBLICARSE en redes. Solo lectura de objeto: el resto del
# arbol /api/media (subidas, generacion, listados) sigue exigiendo credencial, igual que
# cualquier GET de coleccion. El handler ya es anti-traversal (nombre plano).
_PREFIJO_MEDIA_PUBLICA = "/api/media/"
# Sub-rutas de /api/media/ que NO son objetos (acciones POST con su propio path): nunca
# publicas, aunque alguien las pida con GET.
_MEDIA_NO_PUBLICA = frozenset({"/api/media/video", "/api/media/desde-url", "/api/media/generar"})


def _es_media_publica(metodo: str, ruta: str) -> bool:
    """True si la peticion es el GET publico de un objeto de media (ver nota de arriba)."""
    return (
        metodo == "GET"
        and ruta.startswith(_PREFIJO_MEDIA_PUBLICA)
        and len(ruta) > len(_PREFIJO_MEDIA_PUBLICA)
        and ruta not in _MEDIA_NO_PUBLICA
    )

# Si el usuario de la sesion tiene `debe_cambiar_password`, SOLO puede ver su sesion,
# cambiar la contrasena o salir. Cualquier otra ruta /api -> 403 (enforcement en el
# servidor, no solo en el frontend). El token de mantenimiento NO tiene usuario asociado,
# asi que NO es una via para saltarse este gate de un usuario: si una cuenta debe cambiar
# su contrasena, debe hacerlo por su sesion (no hay "admin fantasma" por token, #150).
_RUTAS_API_CAMBIO_PASSWORD = frozenset(
    {"/api/auth/me", "/api/auth/cambiar-password", "/api/auth/logout"}
)
_MSG_DEBE_CAMBIAR = "Debes cambiar tu contraseña antes de usar la Consola."


class SeguridadConsola:
    """Middleware ASGI: sesion (+ token interino opcional) para `/api` + CSRF (#134 + #130).

    - Las rutas que NO empiezan por `/api` (SPA, assets, favicons) pasan SIN credencial:
      hay que poder cargar la pagina. El index escribe la cookie del token (si lo hay).
    - `/api/auth/login` es PUBLICO (crea la sesion) pero pasa por el chequeo CSRF.
    - El resto de `/api/...`: exige UNA sesion valida (cookie `keni_consola_sesion`) O,
      SI HAY token interino configurado, el token (cabecera/cookie). Si falta o no vale ->
      401. La barrera PRINCIPAL es la sesion: si `token is None` (interino no configurado),
      la unica credencial valida es la sesion y una peticion sin sesion -> 401 igualmente.
    - Mutaciones (`POST/PUT/PATCH/DELETE`) sobre `/api`: exigen ADEMAS que el
      `Origin`/`Referer` sea de un host de confianza (Host de la peticion o allowlist) ->
      si no, 403 (CSRF).

    Cuando autentica por sesion, deja el usuario en `scope["state"]["usuario"]` (lo lee
    `request.state.usuario`) para que los handlers comprueben el rol. Si autentica por
    token de mantenimiento, NO hay usuario asociado (`auth_por_token=True`): es una
    credencial de mantenimiento que pasa la barrera de `/api`, pero NO es admin (#150). Las
    rutas que exigen rol admin (`/api/usuarios/*`) la rechazan, salvo el bootstrap del
    primer admin con la BD vacia (acotado en `api/usuarios`).

    El token se compara con `secrets.compare_digest` (tiempo constante). Solo actua
    sobre `scope["type"] == "http"`; el resto pasa intacto.
    """

    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        # Token interino OPCIONAL (#130): None/"" => esa via no existe (solo sesion).
        self._token = token or None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ruta = scope.get("path", "")
        if not ruta.startswith("/api"):
            # SPA / estaticos: sin credencial. (El index escribe la cookie aparte.)
            await self.app(scope, receive, send)
            return

        metodo = scope.get("method", "GET").upper()

        # Estado de la peticion: por defecto, sin usuario de sesion (acceso por token).
        estado = scope.setdefault("state", {})
        estado["usuario"] = None
        estado["auth_por_token"] = False

        publica = ruta in _RUTAS_API_PUBLICAS or _es_media_publica(metodo, ruta)
        if not publica:
            # 1) Credencial: sesion valida (cookie) O token interino (si esta configurado).
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
        # "cambio forzado" se aplica en el SERVIDOR, no solo en el frontend. El token de
        # mantenimiento NO tiene usuario, asi que este gate (de un usuario) no le aplica:
        # tampoco es una via para que un usuario se lo salte (no hay sesion via token).
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
        """True si HAY token interino configurado y la peticion trae el correcto.

        Si el token interino no esta configurado (`self._token is None`), esta via NO
        existe: devuelve False sin comparar nada (la unica credencial valida es la sesion).
        La comparacion es en tiempo constante (`secrets.compare_digest`).
        """
        if self._token is None:
            return False
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


def autor_de_peticion(request: object) -> dict[str, str] | None:
    """Autor (forma de atribucion) de una peticion autenticada, o None (#130 Fase 1).

    Devuelve `{"id": <id estable>, "usuario": <nombre>}` cuando la peticion se autentico
    con una SESION de usuario (el middleware deja el usuario en `request.state.usuario`);
    `None` cuando se entro por el TOKEN interino (mantenimiento, sin usuario) o no hay
    sesion. Ese `None` se persiste como atribucion vacia: el registro queda "sin autor"
    (legado / anonimo), nunca rompe la creacion.

    Se queda con SOLO el id (estable) y el nombre (para mostrar), espejo del modelo de
    usuario (`auth._fila_a_usuario_publico`); no arrastra rol ni mas estado mutable.
    Es el UNICO accesor de atribucion: los handlers no leen `request.state` a mano.
    """
    usuario = getattr(getattr(request, "state", None), "usuario", None)
    if not isinstance(usuario, dict):
        return None
    uid = usuario.get("id")
    nombre = usuario.get("usuario")
    if not isinstance(uid, str) or not uid:
        return None
    return {"id": uid, "usuario": nombre if isinstance(nombre, str) else ""}


def resolver_token() -> tuple[str, bool]:
    """Devuelve `(token, generado)` para el token INTERINO: el de la env var o uno nuevo.

    `generado=True` indica que se creo uno aleatorio. El token de mantenimiento es un gate
    EXTRA opcional (#130) y NO es admin (#150): aunque se genere uno, la barrera PRINCIPAL
    es la sesion + CSRF. Su VALOR NO se loguea ni viaja en la URL (#150). Para correr
    EXPRESAMENTE sin token, se pasa `crear_app(token=None)` (no se llama aqui); este
    resolver genera uno cuando no se fijo `KENI_CONSOLA_TOKEN`.
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

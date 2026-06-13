"""Config — accesores del dominio auth. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _FALSOS,
    _VERDADEROS,
    ADMIN_USER_DEF,
    ENV_ADMIN_PASS,
    ENV_ADMIN_USER,
    ENV_COOKIE_SECURE,
    ENV_HTTPS,
    ENV_MCP_BEARER,
    ENV_MCP_USUARIO,
    ENV_MFA,
    ENV_MFA_ADMIN,
    ENV_MFA_KEY,
    ENV_ORIGENES,
    ENV_RP_ID,
    ENV_RP_NOMBRE,
    ENV_RP_ORIGIN,
    ENV_SESION_HORAS,
    ENV_SESION_MAX_HORAS,
    ENV_TOKEN,
    SESION_HORAS_DEF,
    SESION_MAX_HORAS_DEF,
    _crudo,
    _entero,
    _leer_secreto_fichero,
    os,
)

# --------------------------------------------------------------------------- #
# Accesores: auth / sesion / CSRF                                              #
# --------------------------------------------------------------------------- #


def token() -> str | None:
    """Token interino OPCIONAL fijado por `KENI_CONSOLA_TOKEN` (None si no esta; vacio = no fijado).

    Tras la auth multiusuario (#130) este token es un gate EXTRA, no la barrera principal:
    la Consola queda protegida por sesion + CSRF aunque no se fije. Si esta presente, sigue
    valiendo como credencial adicional (cabecera/cookie) para clientes de mantenimiento.
    """
    return _crudo(ENV_TOKEN) or None


def origenes_permitidos() -> frozenset[str]:
    """Hosts externos permitidos para la verificacion CSRF (`KENI_CONSOLA_ORIGENES`).

    Lista separada por comas. Cada item se NORMALIZA a `host[:puerto]` en minusculas: se
    acepta tanto un origen completo (`https://social.kenitech.io`) como solo el host
    (`social.kenitech.io`). Vacio (def) => conjunto vacio: el chequeo CSRF compara contra
    el `Host` de la peticion, como en local (127.0.0.1). Detras de un proxy (Traefik) se
    fija al host publico para que las mutaciones del SPA legitimo (cuyo `Origin` es el host
    externo) pasen, sin depender de que el `Host` reenviado coincida byte a byte.
    """
    crudo = _crudo(ENV_ORIGENES)
    if not crudo:
        return frozenset()
    hosts: set[str] = set()
    for parte in crudo.split(","):
        item = parte.strip()
        if not item:
            continue
        host = _host_de_origen(item)
        if host:
            hosts.add(host)
    return frozenset(hosts)


def _host_de_origen(valor: str) -> str | None:
    """Normaliza un item de `KENI_CONSOLA_ORIGENES` a `host[:puerto]` en minusculas.

    Acepta un origen con esquema (`https://host:puerto`) o solo el host (`host:puerto`).
    Devuelve None si no se puede extraer un host (entrada vacia/invalida).
    """
    from urllib.parse import urlsplit

    item = valor.strip().lower()
    if not item:
        return None
    # Con esquema: parsea el netloc. Sin esquema, `urlsplit` no separa el host, asi que
    # lo tratamos como host[:puerto] directo (quitando una posible barra/ruta final).
    if "://" in item:
        try:
            netloc = urlsplit(item).netloc
        except ValueError:
            return None
        netloc = netloc.rsplit("@", 1)[-1]
        return netloc or None
    return item.split("/", 1)[0] or None


def flag_https() -> bool:
    """True si `KENI_CONSOLA_HTTPS` esta a un valor afirmativo (estamos tras TLS)."""
    return _crudo(ENV_HTTPS).lower() in _VERDADEROS


def cookie_secure() -> bool:
    """¿Cookies `Secure`? `KENI_CONSOLA_COOKIE_SECURE` manda; si no se fija, deriva de HTTPS."""
    crudo = _crudo(ENV_COOKIE_SECURE)
    if crudo:
        return crudo.lower() in _VERDADEROS
    return flag_https()


def mcp_bearer() -> str | None:
    """Bearer que protege el endpoint `/mcp` (`KENI_MCP_BEARER`; None si no esta).

    None/vacio => el servidor MCP NO se monta (apagado por defecto). Cuando esta, el
    middleware del MCP exige `Authorization: Bearer <este valor>` en cada peticion a
    `/mcp` (comparacion en tiempo constante). Es la barrera del MCP frente al exterior;
    por dentro el MCP opera la API con una sesion del usuario `mcp_usuario()`.
    """
    return _crudo(ENV_MCP_BEARER) or None


def mcp_usuario() -> str | None:
    """Usuario al que se atribuyen las acciones del MCP (`KENI_MCP_USUARIO`).

    Si no se fija, cae al admin de bootstrap (`KENI_CONSOLA_ADMIN_USER`): el dueño. None
    solo si tampoco hay admin configurado (el MCP resolvera entonces el primer admin).
    """
    return _crudo(ENV_MCP_USUARIO) or _crudo(ENV_ADMIN_USER) or None


def sesion_horas() -> int:
    """Duracion de la sesion en horas (`KENI_CONSOLA_SESION_HORAS`, def 12; >0)."""
    horas = _entero(ENV_SESION_HORAS, SESION_HORAS_DEF)
    return horas if horas > 0 else SESION_HORAS_DEF


def sesion_max_horas() -> int:
    """Tope ABSOLUTO de vida de sesion en horas (`KENI_CONSOLA_SESION_MAX_HORAS`, def 720; >0).

    A diferencia de `sesion_horas()` (ventana DESLIZANTE que se renueva en cada uso), este es
    un tope DURO medido contra `creada`: pasado el cap la sesion se rechaza y borra AUNQUE se
    haya usado hace un segundo. Default GENEROSO (30 d) para no afectar el uso normal del
    piloto; solo acota sesiones renovadas indefinidamente (token vivo o robado-y-usado)."""
    horas = _entero(ENV_SESION_MAX_HORAS, SESION_MAX_HORAS_DEF)
    return horas if horas > 0 else SESION_MAX_HORAS_DEF


def admin_user() -> str:
    """Usuario del admin de bootstrap (`KENI_CONSOLA_ADMIN_USER`, def "admin")."""
    return _crudo(ENV_ADMIN_USER) or ADMIN_USER_DEF


def admin_pass() -> str:
    """Contrasena del admin de bootstrap (`KENI_CONSOLA_ADMIN_PASS`, "" si no esta)."""
    # SIN strip: una contrasena puede llevar espacios significativos a proposito.
    valor = os.environ.get(ENV_ADMIN_PASS)
    if valor is None:
        valor = _leer_secreto_fichero(ENV_ADMIN_PASS)
    return valor if valor is not None else ""


def mfa_habilitado() -> bool:
    """True si el segundo factor (passkeys/WebAuthn) esta ACTIVO (`KENI_CONSOLA_MFA` afirmativo).

    Default OFF (mismo espiritu CONSERVADOR que el resto de gates): con el flag apagado, el
    login NO pide nunca un segundo factor y se comporta EXACTAMENTE como hoy. Encenderlo solo
    afecta a usuarios que YA tengan >=1 passkey (`mfa_activo`); el resto sigue entrando con
    usuario+contrasena hasta que enrolen una.
    """
    return _crudo(ENV_MFA).lower() in _VERDADEROS


def mfa_obligatorio_admin() -> bool:
    """¿El segundo factor es OBLIGATORIO para los admins? (`KENI_CONSOLA_MFA_ADMIN`, def ON).

    Default ON (a diferencia del flag global `mfa_habilitado`, que es OFF): un admin publica en
    canales de marca, así que un password robado SIN segundo factor es account-takeover. Con
    esto activo y SI la maquinaria puede operar (hay `mfa_key()`), los admins quedan sujetos al
    factor: con passkey, el login la EXIGE; sin passkey, se les marca para inscribirla (gracia,
    sin lockout). Se apaga con un valor falsy (`0/false/no/off`) como válvula de escape operativa.
    NO afecta a editores. Sin clave de firma NO se fuerza nada (lo decide `api/auth`): no hay
    lockout. Default ON = ausente o cualquier valor no-falsy.
    """
    return _crudo(ENV_MFA_ADMIN).lower() not in _FALSOS


def mfa_key_presente() -> bool:
    """True si hay clave de firma WebAuthn configurada (`KENI_CONSOLA_MFA_KEY` no vacía).

    Atajo barato para decidir si la maquinaria MFA puede operar SIN construir el cifrador (eso
    valida el formato Fernet y lo hace `auth.mfa`). Lo usa `api/auth` para NO forzar el MFA de
    admin cuando no hay clave (evita lockout): sin clave no se puede firmar la cookie de
    challenge/pre-auth ni completar una ceremonia/inscripción.
    """
    return mfa_key() is not None


def mfa_key() -> str | None:
    """Clave Fernet que firma/fecha la cookie de challenge + pre-auth WebAuthn (`KENI_CONSOLA_MFA_KEY`).

    None si no esta (vacio cuenta como no fijada). NO se valida aqui que sea una clave Fernet
    bien formada: eso lo comprueba `auth.mfa` al construir el cifrador, para REHUSAR (fail-safe)
    la ceremonia si la clave falta o es invalida, en vez de media-autenticar. SIN normalizar mas
    alla del strip: una clave Fernet es base64 url-safe sin espacios.
    """
    return _crudo(ENV_MFA_KEY) or None


def rp_id() -> str:
    """WebAuthn Relying Party ID (`KENI_CONSOLA_RP_ID`, def `localhost`).

    Es el dominio efectivo SIN esquema ni puerto. En prod debe ser `social.kenitech.io`. El
    defecto `localhost` cubre el desarrollo (`python -m keni_consola` en 127.0.0.1:8765).
    """
    return _crudo(ENV_RP_ID) or "localhost"


def rp_origenes() -> list[str]:
    """Origen(es) esperado(s) de la ceremonia WebAuthn (`KENI_CONSOLA_RP_ORIGIN`, def dev).

    Con esquema y puerto. Admite una lista separada por comas (varios origenes permitidos). El
    defecto `http://localhost:8765` cubre el desarrollo; en prod: `https://social.kenitech.io`.
    """
    crudo = _crudo(ENV_RP_ORIGIN) or "http://localhost:8765"
    return [o.strip() for o in crudo.split(",") if o.strip()]


def rp_nombre() -> str:
    """Nombre legible de la Relying Party (`KENI_CONSOLA_RP_NOMBRE`, def "Keni Social").

    Es lo que el sistema operativo muestra al crear/usar una passkey.
    """
    return _crudo(ENV_RP_NOMBRE) or "Keni Social"

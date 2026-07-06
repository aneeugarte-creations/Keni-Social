"""Configuracion local por persona: que cuentas gestiona y sus credenciales.

El archivo vive en `~/.config/keni-metricas/config.toml` (o la ruta de
`KENI_METRICAS_CONFIG`). Las credenciales NUNCA salen de la maquina.
Por defecto la fuente es `metricool` (la FUENTE ÚNICA de pago); sin credenciales
degrada con honestidad a estado vacío, nunca a datos inventados. Para demo offline
sin red, declara `fuente = "muestra"`. Ver `credenciales.ejemplo.toml`.
"""

from __future__ import annotations

import os
import re
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .fuentes.base import CuentaNoEncontrada, FuenteMetricas
from .schema import Cuenta, Pieza, Plataforma, ResumenMetricas

# Valores aceptados para `fuente`:
#   - `metricool`= FUENTE ÚNICA de métricas (B es consumidor, no motor de ingesta;
# ADR 0005). Consumidor de la API REST de Metricool (plan pagado).
#                  Lee TODO desde Metricool —dashboard por marca/cuenta Y rendimiento
#                  por pieza— por el MISMO camino, así no hay desfase entre fuentes.
#                  Sin credenciales degrada con honestidad a estado vacío (no inventa).
#   - `muestra`  = datos offline deterministas (demo / sin red). Implementa el mismo
#                  contrato completo que Metricool (resumen + piezas + serie + por-post),
#                  así que la Consola se ve igual en demo sin desfase.
#   - `real`     = FALLBACK EXPLÍCITO y DESACTIVADO por defecto: adaptadores propios por
#                  plataforma (Meta/YouTube/X/TikTok). Capacidad HISTÓRICA que NO se usa
# para B (ADR 0005). Solo cubre el dashboard agregado: NO expone
#                  rendimiento por pieza (`metricas_de_post`) ni serie diaria, así que
#                  conviviría con el tablero leyendo cero —el desfase que esta
#                  consolidación elimina—. Por eso queda detrás de un flag opt-in
#                  (`KENI_METRICAS_PERMITIR_REAL=1`); sin el flag, seleccionarla falla
#                  con un mensaje que remite a `metricool`. Ver `agregador.py`.
FUENTES_VALIDAS: frozenset[str] = frozenset({"muestra", "metricool", "real"})

# Fuente por defecto cuando el config no declara `fuente`: Metricool (la fuente única
# de pago). La Consola arranca apuntando a la fuente real y degrada con honestidad a
# estado vacío si faltan credenciales (no a datos de demo).
FUENTE_DEFECTO: str = "metricool"

# Env var que habilita la fuente `real` (adaptadores por plataforma) como fallback
# explícito. Sin ella, `real` se rechaza (ver `_verificar_real_permitida`). Existe
# para no perder la capacidad histórica de los adaptadores, pero evitando que vuelva
# a ser un camino silencioso que devuelva números distintos a los del tablero.
ENV_PERMITIR_REAL: str = "KENI_METRICAS_PERMITIR_REAL"


def _real_permitida() -> bool:
    """True si la fuente `real` (adaptadores) está habilitada por flag opt-in."""
    return os.environ.get(ENV_PERMITIR_REAL, "").strip().lower() in {"1", "true", "yes", "si"}


class ConfigInvalida(ValueError):
    """El config.toml existe pero no se puede usar (sintaxis o contenido invalido).

    Hereda de `ValueError` para que los CLIs que ya capturan `ValueError` la
    traten como un error de dominio (mensaje en espanol, sin traceback de
    `tomllib` ni KeyError crudos). El `doctor` la reporta como ❌.
    """


def ruta_config() -> Path:
    if (p := os.environ.get("KENI_METRICAS_CONFIG")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-metricas" / "config.toml"


def _parsear_marcas(valor: str | list | None) -> list[str]:
    """Normaliza la lista de marcas (de env var coma-separada o de la lista TOML)."""
    if not valor:
        return []
    crudas = valor.split(",") if isinstance(valor, str) else valor
    # preserva el orden declarado y descarta duplicados/vacios
    vistas: list[str] = []
    for m in crudas:
        m = str(m).strip()
        if m and m not in vistas:
            vistas.append(m)
    return vistas


@dataclass
class CuentaConfig:
    id: str
    nombre: str
    plataformas: dict[Plataforma, str]  # plataforma -> handle / id en esa plataforma


@dataclass
class MetricoolConfig:
    """Credenciales POR MARCA para la fuente `metricool` (API REST).

    El modelo PRIMARIO es per-marca: en el cliente cada marca es de hecho una cuenta
    Metricool distinta, con su PROPIO `user_token` (cabecera `X-Mc-Auth`),
    `user_id` y `blog_id` (ambos query params). Cada marca vive en
    `[metricool.marcas.<id>]` con esos tres campos (y opcional `nombre`,
    `plataformas`, `ads_proveedores`).

    `user_token`/`user_id` de nivel `[metricool]` (o las env
    `METRICOOL_USER_TOKEN`/`METRICOOL_USER_ID`) son solo un DEFAULT de
    compatibilidad: una marca que no fije el suyo los hereda. El blog_id NUNCA
    se hereda (es propio de cada marca).

    Una marca está CONFIGURADA si resuelve los tres: token + user_id + blog_id.
    """

    # Defaults de compatibilidad (nivel `[metricool]` / env). NO son el modelo
    # primario: solo rellenan las marcas que no traigan su propio token/user_id.
    user_token: str = ""
    user_id: str = ""
    # id_marca_keni -> {"blog_id": str, "user_token": str?, "user_id": str?,
    #                   "nombre": str?, "plataformas": [str|Plataforma]?,
    #                   "ads_proveedores": [str]?}
    marcas: dict[str, dict] = field(default_factory=dict)

    def token_de(self, marca: dict) -> str:
        """Token de una marca: el propio, o el default `[metricool]`/env."""
        return str(marca.get("user_token") or self.user_token or "")

    def user_id_de(self, marca: dict) -> str:
        """user_id de una marca: el propio, o el default `[metricool]`/env."""
        return str(marca.get("user_id") or self.user_id or "")

    def marca_configurada(self, marca: dict) -> bool:
        """True si la marca resuelve token + user_id + blog_id (los tres)."""
        return bool(self.token_de(marca) and self.user_id_de(marca) and marca.get("blog_id"))

    def marcas_configuradas(self) -> dict[str, dict]:
        """Subconjunto de `marcas` que tiene credenciales completas (resueltas).

        Cada entrada se devuelve con `user_token`/`user_id` YA RESUELTOS (propios o
        heredados del default), de modo que `FuenteMetricool` no vuelve a mirar el
        default: cada marca lleva sus tres credenciales explícitas.
        """
        salida: dict[str, dict] = {}
        for mid, m in self.marcas.items():
            if not self.marca_configurada(m):
                continue
            resuelta = dict(m)
            resuelta["user_token"] = self.token_de(m)
            resuelta["user_id"] = self.user_id_de(m)
            resuelta["blog_id"] = str(m["blog_id"])
            salida[mid] = resuelta
        return salida

    @property
    def configurada(self) -> bool:
        """True si AL MENOS UNA marca tiene credenciales completas."""
        return bool(self.marcas_configuradas())


# Canales de publicación por marca. Metricool es el DEFAULT (cero cambio de
# comportamiento histórico); Postproxy es el canal alternativo opt-in por marca.
CANAL_METRICOOL: str = "metricool"
CANAL_POSTPROXY: str = "postproxy"
CANALES_PUBLICACION: frozenset[str] = frozenset({CANAL_METRICOOL, CANAL_POSTPROXY})
CANAL_DEFECTO: str = CANAL_METRICOOL


def normalizar_canal(valor: object) -> str:
    """Canal válido a partir de un valor crudo: default `metricool` ante cualquier otro.

    Fuente ÚNICA de la validación del canal: un valor desconocido (o vacío, o no-str) cae
    a `metricool` — el default que NO cambia el comportamiento histórico.
    """
    canal = str(valor or "").strip().lower()
    return canal if canal in CANALES_PUBLICACION else CANAL_DEFECTO


@dataclass
class PostproxyConfig:
    """Credenciales para PUBLICAR via **Postproxy** (canal alternativo a Metricool).

    Espejo de `MetricoolConfig` pero con un modelo de secreto distinto: Postproxy usa
    UNA sola `api_key` GLOBAL (header `Authorization: Bearer <api_key>`), no un token por
    marca. Lo que varía por marca es a qué GRUPO DE PERFILES (`profile_group_id`) se
    publica. Por eso:

    - `api_key`: secreto GLOBAL (`[postproxy] api_key`, o env `POSTPROXY_API_KEY` con
      prioridad — igual que Metricool con `METRICOOL_USER_TOKEN`).
    - `marcas`: id_metricas -> {"profile_group_id": str, "canal": str}
      (`[postproxy.marcas.<id>]`).

    Cada marca elige su CANAL de publicación (`canal` ∈ {metricool, postproxy}, default
    `metricool`): es el selector que decide a qué adaptador entrega el programador. El
    grupo/credenciales de Postproxy se quedan guardados aunque el canal sea metricool,
    para poder alternar sin reconfigurar.

    Una marca está CONFIGURADA (publicable VIA Postproxy) si tiene `profile_group_id` Y
    hay `api_key` global (el secreto es compartido; sin él ninguna marca puede publicar).
    El `canal` es ortogonal a "configurada": una marca puede tener canal=postproxy sin
    grupo aún (no publicará hasta tenerlo) o canal=metricool con grupo guardado.
    """

    # Secreto GLOBAL (header Bearer). Compartido por todas las marcas.
    api_key: str = ""
    # id_marca_keni -> {"profile_group_id": str, "canal": str}
    marcas: dict[str, dict] = field(default_factory=dict)

    def grupo_de(self, marca: dict) -> str:
        """profile_group_id de una marca ('' si no lo tiene)."""
        return str(marca.get("profile_group_id") or "")

    def canal_de(self, marca: dict) -> str:
        """Canal de publicación de una marca (validado): default `metricool`."""
        return normalizar_canal(marca.get("canal"))

    def canal_marca(self, id_metricas: str) -> str:
        """Canal de publicación de la marca por su `id_metricas`: default `metricool`.

        Una marca no declarada (o sin `canal`) usa `metricool` — el default que preserva
        el comportamiento histórico (cero regresión cuando no se ha tocado nada).
        """
        return self.canal_de(self.marcas.get(id_metricas) or {})

    def marca_configurada(self, marca: dict) -> bool:
        """True si la marca tiene profile_group_id Y hay api_key global."""
        return bool(self.api_key and self.grupo_de(marca))

    def marcas_configuradas(self) -> dict[str, dict]:
        """Subconjunto de `marcas` con grupo asignado (y api_key global presente).

        Cada entrada se devuelve con `profile_group_id` ya resuelto (str). Si no hay
        api_key global, devuelve vacío (ninguna marca puede publicar sin el secreto).
        """
        if not self.api_key:
            return {}
        salida: dict[str, dict] = {}
        for mid, m in self.marcas.items():
            if not self.marca_configurada(m):
                continue
            resuelta = dict(m)
            resuelta["profile_group_id"] = self.grupo_de(m)
            salida[mid] = resuelta
        return salida

    @property
    def configurada(self) -> bool:
        """True si AL MENOS UNA marca tiene grupo (y hay api_key global)."""
        return bool(self.marcas_configuradas())


@dataclass
class GoogleAnalyticsConfig:
    """Conexión a Google Analytics 4 por OAuth de usuario + property_id POR MARCA.

    Modelo de auth (ver `ga4.py`): la app OAuth (client_id/client_secret) es NUESTRA y
    se configura una vez; el `refresh_token` es de la cuenta de la persona que conectó
    su Google con acceso de lectura a las propiedades GA4 (no necesita ser admin). Por
    eso client_id/client_secret/refresh_token son GLOBALES (una conexión sirve a todas
    las marcas), igual que la api_key de Postproxy.

    Lo que varía por marca es a qué PROPIEDAD GA4 (`property_id`, el id numérico) se lee.
    Cada `[google_analytics.marcas.<id>]` trae su `property_id` (y opcional `dominio`).

    Las env `GA_OAUTH_CLIENT_ID`/`GA_OAUTH_CLIENT_SECRET`/`GA_OAUTH_REFRESH_TOKEN`
    tienen prioridad sobre el TOML (igual que `METRICOOL_USER_TOKEN`).

    Estados:
    - `app_configurada`: hay client_id + client_secret (se puede iniciar el flujo OAuth).
    - `conectada`: además hay refresh_token (se puede leer GA4).
    - una MARCA está configurada si la conexión está y la marca tiene property_id.
    """

    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    # id_marca_keni -> {"property_id": str, "dominio": str?}
    marcas: dict[str, dict] = field(default_factory=dict)

    @property
    def app_configurada(self) -> bool:
        """True si hay client_id + client_secret (se puede iniciar el flujo OAuth)."""
        return bool(self.client_id and self.client_secret)

    @property
    def conectada(self) -> bool:
        """True si la app está configurada Y hay refresh_token (se puede leer GA4)."""
        return bool(self.app_configurada and self.refresh_token)

    def property_de(self, marca: dict) -> str:
        """property_id de una marca ('' si no lo tiene)."""
        return str(marca.get("property_id") or "")

    def marca_configurada(self, marca: dict) -> bool:
        """True si la conexión está y la marca tiene property_id."""
        return bool(self.conectada and self.property_de(marca))

    def marcas_configuradas(self) -> dict[str, dict]:
        """Subconjunto de `marcas` con property_id (y conexión presente)."""
        if not self.conectada:
            return {}
        salida: dict[str, dict] = {}
        for mid, m in self.marcas.items():
            if not self.marca_configurada(m):
                continue
            resuelta = dict(m)
            resuelta["property_id"] = self.property_de(m)
            salida[mid] = resuelta
        return salida

    @property
    def configurada(self) -> bool:
        """True si AL MENOS UNA marca tiene property_id (y hay conexión)."""
        return bool(self.marcas_configuradas())


@dataclass
class Config:
    fuente: str = FUENTE_DEFECTO  # "metricool" (única) | "muestra" (demo) | "real" (fallback)
    cuentas: list[CuentaConfig] = field(default_factory=list)
    credenciales: dict[str, dict] = field(default_factory=dict)  # plataforma -> {clave: valor}
    # marcas (ids) que gestiona esta persona. Vacio = todas (compatibilidad).
    marcas: list[str] = field(default_factory=list)
    # Identidad + mapeo de marcas para la fuente `metricool`.
    metricool: MetricoolConfig = field(default_factory=MetricoolConfig)
    # Credenciales para PUBLICAR via Postproxy (canal alternativo a Metricool).
    postproxy: PostproxyConfig = field(default_factory=PostproxyConfig)
    # Conexión a Google Analytics 4 (métricas web por marca, OAuth de usuario).
    google_analytics: GoogleAnalyticsConfig = field(default_factory=GoogleAnalyticsConfig)


def _parsear_cuenta(idx: int, c: object) -> CuentaConfig:
    """Valida una entrada `[[cuenta]]` del TOML y la materializa (B4).

    Exige `id` y `nombre`, y que cada plataforma declarada sea valida; ante
    cualquier fallo lanza `ConfigInvalida` con un mensaje en espanol que indica
    QUE cuenta (por posicion e id si lo hay) y QUE campo esta mal.
    """
    # `n` identifica la cuenta para el humano: 1-based, mas el id si lo trae.
    n = f"#{idx + 1}"
    if not isinstance(c, dict):
        raise ConfigInvalida(
            f"La cuenta {n} del config no es una tabla [[cuenta]] valida."
        )
    etiqueta = f"{n} (id={c['id']!r})" if c.get("id") else n
    for campo in ("id", "nombre"):
        valor = c.get(campo)
        if not (isinstance(valor, str) and valor.strip()):
            raise ConfigInvalida(
                f"La cuenta {etiqueta} no tiene un campo {campo!r} valido "
                "(es obligatorio y no puede estar vacio)."
            )

    plataformas_crudas = c.get("plataformas") or {}
    if not isinstance(plataformas_crudas, dict):
        raise ConfigInvalida(
            f"El campo 'plataformas' de la cuenta {etiqueta} debe ser una tabla "
            "plataforma -> handle/id."
        )
    plataformas: dict[Plataforma, str] = {}
    validas = ", ".join(sorted(p.value for p in Plataforma))
    for k, v in plataformas_crudas.items():
        try:
            plataforma = Plataforma(k)
        except ValueError as e:
            raise ConfigInvalida(
                f"La cuenta {etiqueta} declara una plataforma invalida {k!r}. "
                f"Validas: {validas}."
            ) from e
        plataformas[plataforma] = str(v)

    return CuentaConfig(id=c["id"], nombre=c["nombre"], plataformas=plataformas)


def _parsear_metricool(datos: dict) -> MetricoolConfig:
    """Lee la sección `[metricool]` del config: credenciales POR MARCA.

    Modelo PRIMARIO (per-marca): cada `[metricool.marcas.<id>]` trae su propio
    `user_token`, `user_id` y `blog_id` (y opcional `nombre`, `plataformas`,
    `ads_proveedores`).

    Compatibilidad: `user_token`/`user_id` de nivel `[metricool]` —o las env
    `METRICOOL_USER_TOKEN`/`METRICOOL_USER_ID` (con prioridad sobre el TOML)— se
    usan como DEFAULT para marcas que no fijen el suyo. El `blog_id` no se hereda.

    NO valida agresivamente: si ninguna marca queda configurada,
    `MetricoolConfig.configurada` será False y `construir_fuente` degrada a
    `muestra` (degradación honesta, sin romper).
    """
    seccion = datos.get("metricool", {}) if isinstance(datos.get("metricool"), dict) else {}
    user_token = os.environ.get("METRICOOL_USER_TOKEN") or seccion.get("user_token", "")
    user_id = os.environ.get("METRICOOL_USER_ID") or str(seccion.get("user_id", "") or "")

    marcas: dict[str, dict] = {}
    crudas = seccion.get("marcas", {})
    if isinstance(crudas, dict):
        for mid, m in crudas.items():
            if not isinstance(m, dict):
                continue
            entrada: dict = {}
            blog_id = m.get("blog_id") or m.get("blogId")
            if blog_id:
                entrada["blog_id"] = str(blog_id)
            # Credenciales propias de la marca (el modelo primario). Si faltan, la
            # marca heredará el default `[metricool]`/env vía MetricoolConfig.
            if m.get("user_token"):
                entrada["user_token"] = str(m["user_token"])
            if m.get("user_id") not in (None, ""):
                entrada["user_id"] = str(m["user_id"])
            if m.get("nombre"):
                entrada["nombre"] = str(m["nombre"])
            plats = m.get("plataformas")
            if isinstance(plats, list):
                entrada["plataformas"] = [str(p) for p in plats]
            # Providers de Ads CON licencia en Metricool (p.ej. solo facebookads): acota
            # las consultas de campañas; sin la clave se consultan todos los conocidos.
            provs = m.get("ads_proveedores")
            if isinstance(provs, list):
                entrada["ads_proveedores"] = [str(p) for p in provs]
            # Conserva la marca aunque le falten credenciales: así el estado per-marca
            # (consola GET) sabe que existe pero está "sin conectar". La omisión real
            # la hace `marcas_configuradas()` al construir la fuente.
            marcas[str(mid)] = entrada

    return MetricoolConfig(user_token=str(user_token or ""), user_id=user_id, marcas=marcas)


def _parsear_postproxy(datos: dict) -> PostproxyConfig:
    """Lee la sección `[postproxy]` del config: api_key GLOBAL + grupo POR MARCA.

    Modelo de secreto (espejo NO idéntico de Metricool): Postproxy usa UNA `api_key`
    global (header Bearer), no un token por marca. La env `POSTPROXY_API_KEY` tiene
    PRIORIDAD sobre el TOML (igual que `METRICOOL_USER_TOKEN`).

    Cada `[postproxy.marcas.<id>]` trae su `profile_group_id` (el grupo de perfiles de
    Postproxy donde publica esa marca) y su `canal` ∈ {metricool, postproxy} (default
    `metricool`; cualquier valor desconocido cae a `metricool`). Se conservan TODAS las
    marcas declaradas aunque les falte el grupo, así el estado per-marca (consola GET)
    sabe que existen pero están "sin grupo"; la omisión real la hace `marcas_configuradas()`.
    El `canal` se NORMALIZA siempre (la entrada lleva un `canal` válido garantizado).
    """
    seccion = datos.get("postproxy", {}) if isinstance(datos.get("postproxy"), dict) else {}
    api_key = os.environ.get("POSTPROXY_API_KEY") or seccion.get("api_key", "")

    marcas: dict[str, dict] = {}
    crudas = seccion.get("marcas", {})
    if isinstance(crudas, dict):
        for mid, m in crudas.items():
            if not isinstance(m, dict):
                continue
            entrada: dict = {}
            grupo = m.get("profile_group_id") or m.get("profileGroupId") or m.get("grupo")
            if grupo not in (None, ""):
                entrada["profile_group_id"] = str(grupo)
            # Canal SIEMPRE presente y validado (default metricool): facilita el estado
            # per-marca y el despacho del programador sin re-validar aguas abajo.
            entrada["canal"] = normalizar_canal(m.get("canal"))
            marcas[str(mid)] = entrada

    return PostproxyConfig(api_key=str(api_key or ""), marcas=marcas)


def _parsear_google_analytics(datos: dict) -> GoogleAnalyticsConfig:
    """Lee `[google_analytics]`: app OAuth GLOBAL + property_id POR MARCA.

    `client_id`/`client_secret`/`refresh_token` son globales (una conexión sirve a todas
    las marcas); las env `GA_OAUTH_CLIENT_ID`/`GA_OAUTH_CLIENT_SECRET`/
    `GA_OAUTH_REFRESH_TOKEN` ganan al TOML. Cada `[google_analytics.marcas.<id>]` trae su
    `property_id` (id numérico) y opcional `dominio`. Se conservan TODAS las marcas
    declaradas aunque les falte property_id, así el estado per-marca (consola GET) sabe
    que existen pero están "sin propiedad"; la omisión real la hace `marcas_configuradas()`.
    """
    seccion = (
        datos.get("google_analytics", {})
        if isinstance(datos.get("google_analytics"), dict)
        else {}
    )
    client_id = os.environ.get("GA_OAUTH_CLIENT_ID") or seccion.get("client_id", "")
    client_secret = os.environ.get("GA_OAUTH_CLIENT_SECRET") or seccion.get("client_secret", "")
    refresh_token = os.environ.get("GA_OAUTH_REFRESH_TOKEN") or seccion.get("refresh_token", "")

    marcas: dict[str, dict] = {}
    crudas = seccion.get("marcas", {})
    if isinstance(crudas, dict):
        for mid, m in crudas.items():
            if not isinstance(m, dict):
                continue
            entrada: dict = {}
            pid = m.get("property_id") or m.get("propertyId")
            if pid not in (None, ""):
                entrada["property_id"] = str(pid)
            if m.get("dominio"):
                entrada["dominio"] = str(m["dominio"])
            marcas[str(mid)] = entrada

    return GoogleAnalyticsConfig(
        client_id=str(client_id or ""),
        client_secret=str(client_secret or ""),
        refresh_token=str(refresh_token or ""),
        marcas=marcas,
    )


# Env vars que cambian el RESULTADO de `cargar_config` sin tocar el mtime del fichero.
# Forman parte de la clave de cache: si cualquiera cambia, re-parseamos. (En proceso
# raramente cambian, pero los tests las monkeypatchean entre llamadas.)
_ENV_RELEVANTES: tuple[str, ...] = (
    "KENI_METRICAS_CONFIG",
    "KENI_METRICAS_FUENTE",
    "KENI_METRICAS_MARCAS",
    "METRICOOL_USER_TOKEN",
    "METRICOOL_USER_ID",
    "POSTPROXY_API_KEY",
    "GA_OAUTH_CLIENT_ID",
    "GA_OAUTH_CLIENT_SECRET",
    "GA_OAUTH_REFRESH_TOKEN",
    ENV_PERMITIR_REAL,
    "XDG_CONFIG_HOME",
)

# Memoización de `cargar_config`: re-parsea SOLO cuando cambia la clave (ruta + mtime
# del fichero + huella de las env relevantes). Evita re-leer y re-parsear el TOML en
# cada llamada por-pieza (N+1 de config en el tablero). El lock protege el llenado para
# que dos hilos no parseen a la vez ni se pisen la entrada cacheada.
_cache_lock = threading.Lock()
_cache_config: tuple[object, Config] | None = None


def _clave_cache_config() -> tuple:
    """Huella que invalida la cache: ruta + mtime del fichero + env relevantes.

    `mtime` es `None` si el fichero no existe (caso muestra/sin config); así pasar de
    'no existe' a 'existe' (o un guardado posterior) invalida la entrada. Cualquier
    cambio en una env relevante también la invalida (los tests cambian env entre
    llamadas; un token nuevo en disco lo capta el mtime).
    """
    ruta = ruta_config()
    try:
        mtime = ruta.stat().st_mtime_ns
    except OSError:
        mtime = None
    env = tuple(os.environ.get(k) for k in _ENV_RELEVANTES)
    return (str(ruta), mtime, env)


def cargar_config() -> Config:
    """Config memoizada: re-lee del disco solo si cambia su mtime o una env relevante.

    Antes cada llamada por-pieza re-parseaba el TOML; ahora se reusa la última `Config`
    mientras la clave (`_clave_cache_config`) no cambie. Un cambio de token en disco
    (mtime distinto) se sigue captando sin reiniciar el proceso. El `Config` es
    efectivamente inmutable después (en el flujo) (los consumidores no lo mutan), por lo que es
    seguro compartir la misma instancia entre llamadas/hilos.
    """
    global _cache_config
    clave = _clave_cache_config()
    cacheada = _cache_config
    if cacheada is not None and cacheada[0] == clave:
        return cacheada[1]
    with _cache_lock:
        # Re-chequea bajo el lock: otro hilo pudo llenarla mientras esperábamos.
        cacheada = _cache_config
        if cacheada is not None and cacheada[0] == clave:
            return cacheada[1]
        cfg = _cargar_config_desde_disco()
        _cache_config = (clave, cfg)
        return cfg


def reset_cache_config() -> None:
    """Vacía la memoización de `cargar_config` (la próxima llamada re-lee del disco).

    Para tests o tras un cambio de config que deba reflejarse sin esperar al mtime. No
    es necesario en operación normal (el mtime ya invalida), pero da un seam explícito.
    """
    global _cache_config
    with _cache_lock:
        _cache_config = None


def _cargar_config_desde_disco() -> Config:
    datos: dict = {}
    ruta = ruta_config()
    if ruta.exists():
        try:
            datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            # B1: un TOML mal formado no debe tumbar los comandos con un
            # traceback de tomllib. Lo convertimos en un error de dominio en
            # espanol con la ruta y, si esta disponible, la linea del fallo.
            # `TOMLDecodeError.lineno` solo existe desde Python 3.14; en 3.11-3.13
            # extraemos la linea del propio mensaje ("... at line N, column M").
            linea = getattr(e, "lineno", None)
            if linea is None:
                m = re.search(r"at line (\d+)", str(e))
                linea = int(m.group(1)) if m else None
            ubicacion = f" (linea {linea})" if linea else ""
            raise ConfigInvalida(
                f"El config en {ruta} tiene un error de sintaxis TOML{ubicacion}: {e}"
            ) from e
        except OSError as e:
            raise ConfigInvalida(
                f"No se pudo leer el config en {ruta}: {e}"
            ) from e

    fuente = os.environ.get("KENI_METRICAS_FUENTE") or datos.get("fuente", FUENTE_DEFECTO)
    # B5: una `fuente` desconocida hoy caia en silencio (ceros). La rechazamos.
    if fuente not in FUENTES_VALIDAS:
        validas = ", ".join(sorted(FUENTES_VALIDAS))
        raise ConfigInvalida(
            f"Fuente invalida {fuente!r}. Usa una de: {validas}."
        )
    # `real` (adaptadores por plataforma) es un fallback histórico DESACTIVADO por
    # defecto: solo cubre el dashboard agregado y dejaría el rendimiento por pieza en
    # cero (el desfase que la consolidación a Metricool elimina). Sin el flag opt-in,
    # se rechaza con un mensaje que remite a la fuente única.
    if fuente == "real" and not _real_permitida():
        raise ConfigInvalida(
            "La fuente 'real' (adaptadores por plataforma) está desactivada: solo cubre "
            "el dashboard agregado y dejaría el rendimiento por pieza sin datos. Usa "
            "'metricool' (fuente única de pago) o 'muestra' (demo). Si necesitas los "
            f"adaptadores históricos, exporta {ENV_PERMITIR_REAL}=1 a propósito."
        )

    cuentas = [_parsear_cuenta(i, c) for i, c in enumerate(datos.get("cuenta", []))]

    # La env var tiene prioridad sobre el campo `marcas` del config.toml.
    marcas = _parsear_marcas(os.environ.get("KENI_METRICAS_MARCAS") or datos.get("marcas"))

    return Config(
        fuente=fuente,
        cuentas=cuentas,
        credenciales=datos.get("credenciales", {}),
        marcas=marcas,
        metricool=_parsear_metricool(datos),
        postproxy=_parsear_postproxy(datos),
        google_analytics=_parsear_google_analytics(datos),
    )


class FuenteScoped:
    """Envoltorio que limita una FuenteMetricas a un subconjunto de marcas.

    `cuentas()` solo lista las marcas en alcance; `resumen`/`mejores_piezas`
    rechazan ids fuera de alcance con `CuentaNoEncontrada` (incluso si existen en
    la fuente subyacente). Aplica a CUALQUIER fuente (muestra o real), por lo que
    todo lo después (en el flujo) —reporte_consolidado, picos, etc.— queda acotado.
    """

    def __init__(self, fuente: FuenteMetricas, marcas: list[str]):
        self._fuente = fuente
        self._marcas = list(marcas)
        self._permitidas = set(marcas)

    @property
    def nombre(self) -> str:
        return self._fuente.nombre

    def _verificar(self, cuenta_id: str) -> None:
        if cuenta_id not in self._permitidas:
            disponibles = ", ".join(self._marcas) or "(ninguna en tu alcance)"
            raise CuentaNoEncontrada(
                f"Cuenta {cuenta_id!r} fuera de tu alcance. Disponibles: {disponibles}."
            )

    def cuentas(self) -> list[Cuenta]:
        return [c for c in self._fuente.cuentas() if c.id in self._permitidas]

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:
        self._verificar(cuenta_id)
        return self._fuente.resumen(cuenta_id, rango)

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        self._verificar(cuenta_id)
        return self._fuente.mejores_piezas(cuenta_id, rango, n)

    def cobertura_piezas(self):
        """Delega la cobertura de la ultima `mejores_piezas` si la envuelta la expone.

        Capacidad OPCIONAL (la implementan FuenteCompuesta y Metricool): devuelve None
        si la fuente envuelta no la tiene, igual que hace la tool al leerla por getattr.
        """
        fn = getattr(self._fuente, "cobertura_piezas", None)
        return fn() if callable(fn) else None

    def serie_diaria(self, cuenta_id: str, rango: str):
        """Delega la serie diaria si la fuente envuelta la expone (dispatch opcional).

        No todas las fuentes la implementan (las 'real' compuestas no). Si la envuelta
        no la tiene, propaga `AttributeError` para que el llamante (`servicio`) degrade a
        serie vacia — igual que si la fuente no tuviera el metodo (no la enmascara el wrap).
        """
        if not hasattr(self._fuente, "serie_diaria"):
            raise AttributeError("la fuente envuelta no expone serie_diaria")
        self._verificar(cuenta_id)
        return self._fuente.serie_diaria(cuenta_id, rango)

    def serie_seguidores(self, cuenta_id: str, rango: str):
        """Delega la serie de seguidores si la fuente envuelta la expone (dispatch opcional).

        Solo muestra/Metricool la implementan (las 'real' compuestas no). Si la
        envuelta no la tiene, propaga `AttributeError` para que el llamante
        (`servicio`) degrade a serie vacía — igual que `serie_diaria`.
        """
        if not hasattr(self._fuente, "serie_seguidores"):
            raise AttributeError("la fuente envuelta no expone serie_seguidores")
        self._verificar(cuenta_id)
        return self._fuente.serie_seguidores(cuenta_id, rango)

    def serie_alcance(self, cuenta_id: str, rango: str):
        """Delega la serie de alcance de cuenta si la fuente envuelta la expone.

        Solo Metricool la implementa (muestra/compuesta no). Si la envuelta no la tiene,
        propaga `AttributeError` para que el llamante (`servicio`) degrade a serie vacía —
        igual que `serie_seguidores`. SIN esto, el alcance por-marca (siempre envuelto en
        `FuenteScoped`) salía siempre vacío.
        """
        if not hasattr(self._fuente, "serie_alcance"):
            raise AttributeError("la fuente envuelta no expone serie_alcance")
        self._verificar(cuenta_id)
        return self._fuente.serie_alcance(cuenta_id, rango)

    def flujo_audiencia(self, cuenta_id: str, rango: str):
        """Delega el flujo de audiencia (altas/bajas de seguidores) si la fuente lo expone.

        Solo Metricool lo implementa (muestra/compuesta no). Si la envuelta no lo tiene, propaga
        `AttributeError` para que el llamante degrade a vacío — igual que `serie_seguidores`.
        """
        if not hasattr(self._fuente, "flujo_audiencia"):
            raise AttributeError("la fuente envuelta no expone flujo_audiencia")
        self._verificar(cuenta_id)
        return self._fuente.flujo_audiencia(cuenta_id, rango)

    def demografia(self, cuenta_id: str, red):
        """Delega las distribuciones demográficas de la cuenta si la fuente envuelta las expone.

        Solo Metricool las implementa (muestra/compuesta no). Si la envuelta no las tiene,
        propaga `AttributeError` para que el llamante degrade a {} — igual que `serie_seguidores`.
        """
        if not hasattr(self._fuente, "demografia"):
            raise AttributeError("la fuente envuelta no expone demografia")
        self._verificar(cuenta_id)
        return self._fuente.demografia(cuenta_id, red)

    def mejores_horas(self, cuenta_id: str, red):
        """Delega la matriz de mejores horas (besttimes) si la fuente envuelta la expone.

        Solo Metricool la implementa (muestra/compuesta no). Si la envuelta no la tiene,
        propaga `AttributeError` para que el llamante (`servicio.mejor_hora`) degrade a None —
        igual que `serie_seguidores`. SIN esto, la mejor hora por-marca (siempre envuelta en
        `FuenteScoped`) no se calcularía.
        """
        if not hasattr(self._fuente, "mejores_horas"):
            raise AttributeError("la fuente envuelta no expone mejores_horas")
        self._verificar(cuenta_id)
        return self._fuente.mejores_horas(cuenta_id, red)

    def conversaciones(self, cuenta_id: str):
        """Delega las conversaciones (DMs) del inbox si la fuente envuelta las expone.

        Solo Metricool lo implementa (muestra/compuesta no). Si la envuelta no lo tiene,
        propaga `AttributeError` para que el llamante degrade a vacío — igual que `demografia`.
        """
        if not hasattr(self._fuente, "conversaciones"):
            raise AttributeError("la fuente envuelta no expone conversaciones")
        self._verificar(cuenta_id)
        return self._fuente.conversaciones(cuenta_id)

    def comentarios(self, cuenta_id: str, dias: int = 7):
        """Delega los comentarios del inbox si la fuente envuelta los expone.

        Solo Metricool lo implementa (muestra/compuesta no). Si la envuelta no lo tiene,
        propaga `AttributeError` para que el llamante degrade a vacío — igual que `demografia`.
        """
        if not hasattr(self._fuente, "comentarios"):
            raise AttributeError("la fuente envuelta no expone comentarios")
        self._verificar(cuenta_id)
        return self._fuente.comentarios(cuenta_id, dias)

    def metricas_de_post(self, cuenta_id: str, plat, id_post: str, **kw):
        """Delega el rendimiento de un post si la fuente envuelta lo expone (dispatch opcional).

        Solo muestra/Metricool lo implementan (las 'real' compuestas no). Si la envuelta
        no la tiene, propaga `AttributeError` para que el llamante (`servicio`) degrade a
        "sin datos" — igual que `serie_diaria` (no se enmascara el wrap).
        """
        if not hasattr(self._fuente, "metricas_de_post"):
            raise AttributeError("la fuente envuelta no expone metricas_de_post")
        self._verificar(cuenta_id)
        return self._fuente.metricas_de_post(cuenta_id, plat, id_post, **kw)

    def campanias_ads(self, cuenta_id: str, rango: str):
        """Delega las campañas de Ads (inorgánico) si la fuente envuelta las expone.

        Solo Metricool las implementa (muestra/compuesta no). Si la envuelta no la tiene,
        propaga `AttributeError` para que el llamante (`servicio.construir_ads`) degrade a
        inorgánico vacío — igual que `serie_diaria`. SIN esto, una campaña (siempre por-marca,
        y por tanto envuelta en `FuenteScoped`) nunca veía sus Ads."""
        if not hasattr(self._fuente, "campanias_ads"):
            raise AttributeError("la fuente envuelta no expone campanias_ads")
        self._verificar(cuenta_id)
        return self._fuente.campanias_ads(cuenta_id, rango)

    def campanias_ads_desglose(self, cuenta_id: str, provider_campaign_id: str, rango: str = "mes"):
        """Delega el drill-down de una campaña (adgroups+ads) si la fuente envuelta lo expone.

        Solo Metricool lo implementa (muestra/compuesta no). Si la envuelta no lo tiene, propaga
        `AttributeError` para que el llamante degrade a un desglose vacío — igual que
        `campanias_ads`.
        """
        if not hasattr(self._fuente, "campanias_ads_desglose"):
            raise AttributeError("la fuente envuelta no expone campanias_ads_desglose")
        self._verificar(cuenta_id)
        return self._fuente.campanias_ads_desglose(cuenta_id, provider_campaign_id, rango)


class FuenteRed:
    """Envoltorio que limita una FuenteMetricas a un subconjunto de REDES (plataformas).

    Espejo por-red de `FuenteScoped` (que acota por marca): cada `resumen` queda con las
    métricas RE-SUMADAS solo de las redes en foco (su `por_plataforma` reducido a esas
    redes; los totales de cuenta re-sumados sobre ellas), `mejores_piezas` reducido a las
    piezas de esas redes y `serie_seguidores` reducida a esas redes en `por_red`. Se aplica
    a CUALQUIER fuente, así que todo lo que va después (reporte, análisis) queda acotado a la
    red. NO se toca `variacion_vs_anterior`: es una variación de CUENTA (el histórico no la
    guarda por red), así que con foco de red se OMITE del resumen filtrado (no se inventa una
    variación por red que no existe). El resto de capacidades opcionales se delegan tal cual.
    """

    def __init__(self, fuente: FuenteMetricas, redes: "set[str] | frozenset[str]"):
        self._fuente = fuente
        self._redes = {str(r) for r in redes}

    @property
    def nombre(self) -> str:
        return self._fuente.nombre

    def cuentas(self) -> list[Cuenta]:
        return self._fuente.cuentas()

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:
        r = self._fuente.resumen(cuenta_id, rango)
        de_red = [m for m in r.por_plataforma if m.plataforma.value in self._redes]
        vis = sum(m.visualizaciones for m in de_red)
        impr = sum(m.impresiones for m in de_red)
        inter = sum(m.interacciones for m in de_red)
        alcs = [m.alcance for m in de_red if m.alcance is not None]
        alc = sum(alcs) if alcs else None
        # engagement de una sola red = el de esa red; con varias en foco queda None (bases
        # heterogéneas), igual que el agregado del esquema.
        eng = de_red[0].engagement_pct if len(de_red) == 1 else None
        return r.model_copy(
            update={
                "visualizaciones": vis,
                "impresiones": impr,
                "interacciones": inter,
                "alcance": alc,
                "engagement_pct": eng,
                "por_plataforma": de_red,
                # Sin variación por red (el histórico es por cuenta): se omite en foco de red.
                "variacion_vs_anterior": {},
            }
        )

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        piezas = self._fuente.mejores_piezas(cuenta_id, rango, n)
        return [p for p in piezas if p.plataforma.value in self._redes]

    def serie_seguidores(self, cuenta_id: str, rango: str):
        if not hasattr(self._fuente, "serie_seguidores"):
            raise AttributeError("la fuente envuelta no expone serie_seguidores")
        puntos = self._fuente.serie_seguidores(cuenta_id, rango)
        recortados = []
        for punto in puntos:
            por_red = {
                red: v for red, v in (punto.get("por_red") or {}).items() if red in self._redes
            }
            recortados.append({**punto, "por_red": por_red})
        return recortados

    def __getattr__(self, nombre: str):
        # Capacidades opcionales no acotadas por red (serie_diaria, demografia, inbox, ads…):
        # se delegan tal cual a la fuente envuelta. El análisis por red que las necesita
        # (serie diaria) las obtiene ya filtradas por otro camino (`construir_tendencia_diaria`).
        return getattr(self._fuente, nombre)


def _fuente_metricool(cfg: Config) -> FuenteMetricas:
    """Construye `FuenteMetricool` o, sin credenciales, una fuente Metricool VACÍA.

    Si no hay `user_token`/`user_id`/marcas mapeadas NO se inventan datos NI se cae a
    la fuente de muestra: se devuelve una `FuenteMetricool` sin marcas, que no lista
    cuentas ni produce cifras (la UI muestra un estado vacío honesto). El producto no
    debe mostrar datos falsos: con credenciales faltantes se ve "sin datos", no demo.
    Se deja un aviso en el log; el `doctor` reporta la fuente efectiva por `fuente.nombre`
    (sigue siendo "metricool").
    """
    from .fuentes.metricool import FuenteMetricool

    mc = cfg.metricool
    configuradas = mc.marcas_configuradas()
    if not configuradas:
        import logging

        logging.getLogger("keni_metricas").warning(
            "fuente 'metricool' seleccionada pero ninguna marca tiene credenciales "
            "completas (cada [metricool.marcas.<id>] necesita user_token + user_id + "
            "blog_id; admite default [metricool]/METRICOOL_USER_TOKEN/USER_ID); "
            "no se muestran datos (estado vacío, sin inventar cifras de demo)."
        )
        return FuenteMetricool(marcas={})

    # Las marcas SIN credenciales completas se OMITEN honestamente: solo pasan las
    # configuradas, cada una con su token/user_id/blog_id YA resueltos.
    return FuenteMetricool(marcas=configuradas)


def construir_fuente(cfg: Config | None = None) -> FuenteMetricas:
    """Crea la fuente activa segun la configuracion.

    Si la persona declaro marcas (env `KENI_METRICAS_MARCAS` o campo `marcas` del
    config), envuelve la fuente para limitarla a esas marcas. Sin marcas, la
    fuente se devuelve tal cual (comportamiento historico: todas las marcas).
    """
    cfg = cfg or cargar_config()
    if cfg.fuente == "metricool":
        fuente: FuenteMetricas = _fuente_metricool(cfg)
    elif cfg.fuente == "muestra":
        from .fuentes.muestra import FuenteMuestra

        fuente = FuenteMuestra()
    else:  # cfg.fuente == "real" — fallback histórico, solo con el flag opt-in.
        if not _real_permitida():
            raise ConfigInvalida(
                "La fuente 'real' (adaptadores por plataforma) está desactivada. Usa "
                f"'metricool' o 'muestra', o exporta {ENV_PERMITIR_REAL}=1 a propósito."
            )
        from .agregador import FuenteCompuesta

        fuente = FuenteCompuesta.desde_config(cfg)

    if cfg.marcas:
        return FuenteScoped(fuente, cfg.marcas)
    return fuente

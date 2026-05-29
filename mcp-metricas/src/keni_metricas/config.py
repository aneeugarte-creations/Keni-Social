"""Configuracion local por persona: que cuentas gestiona y sus credenciales.

El archivo vive en `~/.config/keni-metricas/config.toml` (o la ruta de
`KENI_METRICAS_CONFIG`). Las credenciales NUNCA salen de la maquina.
Por defecto la fuente es `muestra` (datos offline), asi que el MCP funciona
sin configurar nada. Ver `credenciales.ejemplo.toml`.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .fuentes.base import CuentaNoEncontrada, FuenteMetricas
from .schema import Cuenta, Pieza, Plataforma, ResumenMetricas

# Valores aceptados para `fuente`:
#   - `muestra`  = datos offline (defecto), sin red.
#   - `metricool`= consumidor de la API REST de Metricool (B es consumidor, no
#                  motor de ingesta; ADR 0005 §B). Requiere API token (plan
#                  Advanced). Sin credenciales, degrada con honestidad a `muestra`.
#   - `real`     = adaptadores propios por plataforma (Meta/YouTube/X/TikTok). NO se
#                  usa para B (queda como capacidad histórica; ver ADR 0005 §B).
FUENTES_VALIDAS: frozenset[str] = frozenset({"muestra", "metricool", "real"})


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

    El modelo PRIMARIO es per-marca: en AMX cada marca es de hecho una cuenta
    Metricool distinta, con su PROPIO `user_token` (cabecera `X-Mc-Auth`),
    `user_id` y `blog_id` (ambos query params). Cada marca vive en
    `[metricool.marcas.<id>]` con esos tres campos (y opcional `nombre`,
    `plataformas`).

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
    #                   "nombre": str?, "plataformas": [str|Plataforma]?}
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
        heredados del default), de modo que `FuenteMetricol` no vuelve a mirar el
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


@dataclass
class Config:
    fuente: str = "muestra"  # "muestra" | "metricool" | "real"
    cuentas: list[CuentaConfig] = field(default_factory=list)
    credenciales: dict[str, dict] = field(default_factory=dict)  # plataforma -> {clave: valor}
    # marcas (ids) que gestiona esta persona. Vacio = todas (compatibilidad).
    marcas: list[str] = field(default_factory=list)
    # Identidad + mapeo de marcas para la fuente `metricool`.
    metricool: MetricoolConfig = field(default_factory=MetricoolConfig)


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
    `user_token`, `user_id` y `blog_id` (y opcional `nombre`, `plataformas`).

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
            # Conserva la marca aunque le falten credenciales: así el estado per-marca
            # (consola GET) sabe que existe pero está "sin conectar". La omisión real
            # la hace `marcas_configuradas()` al construir la fuente.
            marcas[str(mid)] = entrada

    return MetricoolConfig(user_token=str(user_token or ""), user_id=user_id, marcas=marcas)


def cargar_config() -> Config:
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

    fuente = os.environ.get("KENI_METRICAS_FUENTE") or datos.get("fuente", "muestra")
    # B5: una `fuente` desconocida hoy caia en silencio (ceros). La rechazamos.
    if fuente not in FUENTES_VALIDAS:
        validas = ", ".join(sorted(FUENTES_VALIDAS))
        raise ConfigInvalida(
            f"Fuente invalida {fuente!r}. Usa una de: {validas}."
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
    )


class FuenteScoped:
    """Envoltorio que limita una FuenteMetricas a un subconjunto de marcas.

    `cuentas()` solo lista las marcas en alcance; `resumen`/`mejores_piezas`
    rechazan ids fuera de alcance con `CuentaNoEncontrada` (incluso si existen en
    la fuente subyacente). Aplica a CUALQUIER fuente (muestra o real), por lo que
    todo lo aguas abajo —reporte_consolidado, picos, etc.— queda acotado.
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


def _fuente_metricool(cfg: Config) -> FuenteMetricas:
    """Construye `FuenteMetricol` o, sin credenciales, DEGRADA con honestidad.

    Si no hay `user_token`/`user_id`/marcas mapeadas, no se inventan datos: se
    devuelve la fuente `muestra` y se deja un aviso en el log (degradación honesta,
    ADR 0005 §B / aceptación T2.B). El `doctor` reporta la fuente efectiva por
    `fuente.nombre`, así que el aviso "sin credenciales" es visible.
    """
    from .fuentes.muestra import FuenteMuestra

    mc = cfg.metricool
    configuradas = mc.marcas_configuradas()
    if not configuradas:
        import logging

        logging.getLogger("keni_metricas").warning(
            "fuente 'metricool' seleccionada pero ninguna marca tiene credenciales "
            "completas (cada [metricool.marcas.<id>] necesita user_token + user_id + "
            "blog_id; admite default [metricool]/METRICOOL_USER_TOKEN/USER_ID); "
            "se usa la fuente 'muestra' (datos de demo, sin inventar dato real)."
        )
        return FuenteMuestra()

    # Las marcas SIN credenciales completas se OMITEN honestamente: solo pasan las
    # configuradas, cada una con su token/user_id/blog_id YA resueltos.
    from .fuentes.metricol import FuenteMetricol

    return FuenteMetricol(marcas=configuradas)


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
    else:
        from .agregador import FuenteCompuesta

        fuente = FuenteCompuesta.desde_config(cfg)

    if cfg.marcas:
        return FuenteScoped(fuente, cfg.marcas)
    return fuente

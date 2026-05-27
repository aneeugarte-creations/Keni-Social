"""Fachada estable de keni-metricas para consumidores en proceso (la Consola).

`docs/arquitectura.md` declara la frontera "MCP / stdio", pero la Consola corre en
el mismo proceso y necesita los datos de metricas sin levantar el servidor MCP.
Este modulo es el CONTRATO ESTABLE que la Consola consume: un refactor interno de
`config`/`reporte`/`reporte_deck`/`fuentes` no debe romper a la Consola mientras
esta fachada mantenga su firma.

REGLA DE ORO — la sección «Lectura de métricas» es de SOLO LECTURA: nunca escribe a
disco ni muta el config. La sección «Gestión de configuración» es la unica que
toca el config.toml (cambiar la fuente activa y el alcance de marcas); es frontera
de gestion, no de datos. La escritura de CREDENCIALES (tokens de redes, claves de
imagen) NO vive aqui: la gestiona `keni_metricas.asistente` directamente desde
`api/conexiones.py` (ver hallazgo N4 de la re-auditoria).

Resuelve el hallazgo H1: la Consola deja de importar internals profundos
(`config.construir_fuente`, `config.FuenteScoped`, `reporte.construir_reporte`,
`reporte_deck.*`, `schema.RANGOS_DIAS`, ...).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from . import asistente
from . import config as _config
from . import reporte as _reporte
from . import reporte_deck as _deck
from .config import FUENTES_VALIDAS, ConfigInvalida
from .fuentes.base import CuentaNoEncontrada
from .schema import RANGO_SEMANA_CERRADA, RANGOS_DIAS

# --------------------------------------------------------------------------- #
# Constantes re-exportadas (única fuente de verdad para la Consola)            #
# --------------------------------------------------------------------------- #

# Rangos validos para las metricas generales (rodantes: terminan hoy). La Consola
# no debe importar el schema: este es el contrato.
RANGOS_VALIDOS: tuple[str, ...] = tuple(RANGOS_DIAS.keys())

# Rango anclado que el reporte del lunes usa por defecto: la ultima semana natural
# cerrada (lunes->domingo, domingo incluido), independiente del dia (issue #141).
RANGO_DEPORTES_DEFECTO: str = RANGO_SEMANA_CERRADA

# Rangos que ofrece el deck de deportes: la semana cerrada (por defecto) + los
# rodantes habituales, por si el equipo quiere una ventana distinta.
RANGOS_DEPORTES: tuple[str, ...] = (RANGO_SEMANA_CERRADA, *RANGOS_VALIDOS)

# Fuentes validas ("muestra" | "real"). Re-export para la pantalla de configuracion.
FUENTES_DISPONIBLES: tuple[str, ...] = tuple(sorted(FUENTES_VALIDAS))

# Cuenta principal y hermanas del deck de deportes (Claro Sports).
CUENTA_DEPORTES_PRINCIPAL: str = _deck.CUENTA_PRINCIPAL
CUENTAS_DEPORTES_HERMANAS: tuple[str, ...] = tuple(_deck.CUENTAS_HERMANAS)

# Excepciones de dominio que la Consola captura (re-export para no importar internals).
__all__ = [
    "RANGOS_VALIDOS",
    "RANGOS_DEPORTES",
    "RANGO_DEPORTES_DEFECTO",
    "FUENTES_DISPONIBLES",
    "CUENTA_DEPORTES_PRINCIPAL",
    "CUENTAS_DEPORTES_HERMANAS",
    "ConfigInvalida",
    "CuentaNoEncontrada",
    "nombre_fuente",
    "cuentas_disponibles",
    "construir_reporte",
    "reporte_csv",
    "reporte_markdown",
    "reporte_json",
    "construir_reporte_deportes",
    "render_reporte_deportes_pptx",
    "render_reporte_deportes_pdf",
    "instantanea_config",
    "guardar_fuente_y_alcance",
]


# --------------------------------------------------------------------------- #
# Lectura de métricas — SOLO LECTURA                                          #
# --------------------------------------------------------------------------- #


def _fuente(marca: str | None = None):
    """Fuente activa segun el config, opcionalmente acotada a UNA marca.

    El acotado por marca se delega en la propia fuente (FuenteScoped es interno):
    la Consola pasa el id en forma `id_metricas` (guion_bajo) y la fuente filtra.
    """
    fuente = _config.construir_fuente(_config.cargar_config())
    if marca:
        return _config.FuenteScoped(fuente, [marca])
    return fuente


def nombre_fuente() -> str:
    """Nombre de la fuente de datos activa: "muestra" o "real".

    Para que la UI distinga datos ficticios de reales (riesgo operativo del piloto).
    """
    return _config.construir_fuente(_config.cargar_config()).nombre


def cuentas_disponibles(marca: str | None = None) -> list[tuple[str, str]]:
    """Pares (id_metricas, nombre) de las cuentas en la fuente activa.

    Devuelve `[]` si la fuente no puede listar cuentas (config incompleto).
    """
    try:
        return [(c.id, c.nombre) for c in _fuente(marca).cuentas()]
    except Exception:  # noqa: BLE001 -- sin fuente valida: la UI usa lo que ya tiene
        return []


def construir_reporte(rango: str = "mes", marca: str | None = None) -> dict:
    """Reporte consolidado (total + por cuenta) como dict JSON-serializable.

    Incluye el campo `fuente` ("muestra"|"real"). Propaga `ValueError` (rango
    invalido) y `CuentaNoEncontrada` (marca fuera de alcance).
    """
    return _reporte.construir_reporte(_fuente(marca), rango)


def reporte_csv(rango: str = "mes", marca: str | None = None) -> str:
    """Reporte consolidado renderizado a CSV (misma serializacion que el CLI)."""
    return _reporte.render_csv(construir_reporte(rango, marca))


def reporte_markdown(rango: str = "mes", marca: str | None = None) -> str:
    """Reporte consolidado renderizado a Markdown (misma serializacion que el CLI)."""
    return _reporte.render_markdown(construir_reporte(rango, marca))


def reporte_json(rango: str = "mes", marca: str | None = None) -> str:
    """Reporte consolidado serializado a JSON indentado (crudo, sin reformatear)."""
    return json.dumps(construir_reporte(rango, marca), ensure_ascii=False, indent=2)


def construir_reporte_deportes(
    *,
    rango: str = RANGO_DEPORTES_DEFECTO,
    top: int = 3,
    agenda: dict | None = None,
) -> dict:
    """Deck semanal de Claro Sports como dict JSON-serializable.

    Por defecto cubre la ultima semana natural CERRADA (lunes->domingo, domingo
    incluido); es el rango del reporte del lunes (#141). Incluye el campo `fuente`.
    Propaga `CuentaNoEncontrada` (Claro Sports no esta en la fuente) y `ValueError`
    (rango invalido).
    """
    return _deck.construir_reporte_deportes(
        _fuente(), rango=rango, n_por_plataforma=top, agenda=agenda
    )


def render_reporte_deportes_pptx(rep: dict, ruta: str | Path) -> Path:
    """Renderiza un reporte de deportes a .pptx en `ruta`. Devuelve la ruta escrita.

    Lanza `RuntimeError` si falta el extra `python-pptx`. (No lee la fuente: opera
    sobre el dict ya construido, por eso es seguro exponerlo en la fachada.)
    """
    return _deck.render_pptx(rep, ruta)


def render_reporte_deportes_pdf(rep: dict, ruta: str | Path) -> Path:
    """Renderiza un reporte de deportes a PDF NATIVO en `ruta` (sin LibreOffice).

    Usa reportlab (Python puro, portable). Lanza `RuntimeError` si falta el extra
    `reportlab`. (No lee la fuente: opera sobre el dict ya construido.)
    """
    return _deck.render_pdf(rep, ruta)


# --------------------------------------------------------------------------- #
# Gestión de configuración — lee y cambia fuente/alcance (NO credenciales)     #
# --------------------------------------------------------------------------- #


def instantanea_config() -> dict:
    """Estado del config para la pantalla de configuracion (SIN credenciales).

    Devuelve `{fuente, marcas, marcas_disponibles, credenciales_presentes}`:
      - `marcas_disponibles`: pares (id, nombre) elegibles para el alcance (las del
        config + las de la fuente sin acotar), orden estable y sin duplicados.
      - `credenciales_presentes`: por bloque conocido (meta/youtube/x/tiktok), True
        si trae un token real (nunca el valor, solo presencia).

    Lanza `ConfigInvalida` si el config.toml existe pero no se puede leer.
    """
    cfg = _config.cargar_config()
    return {
        "fuente": cfg.fuente,
        "marcas": list(cfg.marcas),
        "marcas_disponibles": _marcas_disponibles(cfg),
        "credenciales_presentes": _presencia_credenciales(cfg),
    }


def _marcas_disponibles(cfg: _config.Config) -> list[tuple[str, str]]:
    """Marcas elegibles para el alcance: las del config + las de la fuente sin acotar."""
    pares: list[tuple[str, str]] = []
    vistos: set[str] = set()

    for c in cfg.cuentas:
        if c.id not in vistos:
            vistos.add(c.id)
            pares.append((c.id, c.nombre))

    # Sin alcance (marcas=[]) listamos TODAS las marcas de la fuente, asi el usuario
    # puede ampliar su alcance aunque ya lo tenga acotado.
    try:
        cfg_sin_alcance = dataclasses.replace(cfg, marcas=[])
        for c in _config.construir_fuente(cfg_sin_alcance).cuentas():
            if c.id not in vistos:
                vistos.add(c.id)
                pares.append((c.id, c.nombre))
    except Exception:  # noqa: BLE001 -- sin fuente valida seguimos con lo del config
        pass

    return pares


# Bloques de credenciales reconocidos, en orden estable (derivado del asistente).
_BLOQUES_CREDENCIALES: tuple[str, ...] = ("meta", "youtube", "x", "tiktok")


def _presencia_credenciales(cfg: _config.Config) -> dict[str, bool]:
    """Por cada bloque conocido: True si trae un token real (no vacio ni placeholder)."""
    creds = cfg.credenciales if isinstance(cfg.credenciales, dict) else {}
    salida: dict[str, bool] = {}
    for bloque in _BLOQUES_CREDENCIALES:
        valores = creds.get(bloque) if isinstance(creds.get(bloque), dict) else {}
        campo = asistente.CAMPO_TOKEN.get(bloque)
        token = valores.get(campo) if campo else None
        salida[bloque] = bool(token) and token != asistente.PLACEHOLDER_TOKEN
    return salida


def normalizar_alcance(marcas: list[str], ids_validos: list[str]) -> list[str]:
    """Normaliza la lista de marcas del alcance contra los ids validos (re-export)."""
    return asistente.normalizar_alcance(marcas, ids_validos=ids_validos)


def guardar_fuente_y_alcance(fuente: str, marcas: list[str]) -> None:
    """Escribe SOLO `fuente` y `marcas` en el config.toml preservando el resto.

    Merge no destructivo + escritura atomica (delega en `asistente`). NO toca
    credenciales. Frontera de GESTION (no de datos de metricas); por eso vive en
    esta fachada y no obliga a `api/config.py` a importar internals.

    Lanza `ValueError` si la fuente no es valida; `OSError` si falla la escritura.
    """
    if fuente not in FUENTES_VALIDAS:
        validas = ", ".join(FUENTES_DISPONIBLES)
        raise ValueError(f"Fuente invalida {fuente!r}. Usa una de: {validas}.")
    ruta = _config.ruta_config()
    existente = asistente.leer_config_existente(ruta)
    nuevo: dict = {"fuente": fuente}
    if marcas:
        nuevo["marcas"] = list(marcas)
    fusionado = asistente.fusionar_config(existente, nuevo)
    if not marcas:
        fusionado.pop("marcas", None)
    asistente.escribir_config_atomico(ruta, fusionado)

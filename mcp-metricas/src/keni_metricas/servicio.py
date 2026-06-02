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

from . import analisis_diario as _analisis
from . import asistente
from . import config as _config
from . import estadisticas as _estadisticas
from . import reporte as _reporte
from . import reporte_deck as _deck
from .config import FUENTES_VALIDAS, ConfigInvalida
from .fuentes.base import CuentaNoEncontrada
from .schema import (
    RANGO_SEMANA_CERRADA,
    RANGOS_DIAS,
    AnaliticaPiezas,
    MetricaPieza,
    Periodo,
    Plataforma,
    PuntoSerie,
    SerieDiaria,
    etiqueta_rango,
    resolver_rango,
)

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
    "construir_analisis_diario",
    "analisis_diario_markdown",
    "construir_analitica_piezas",
    "construir_listado_piezas",
    "construir_tendencia_diaria",
    "construir_metricas_pieza",
    "etiqueta_rango",
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


def _historico_lectura():
    """Histórico SOLO LECTURA si está activado, o None.

    El análisis diario usa el histórico para leer la variación REAL vs. el periodo
    anterior cuando hay datos previos. Es best-effort: si no se puede abrir (disco,
    permisos), seguimos sin él en vez de romper la lectura.
    """
    from .historico import Historico, historico_activo

    if not historico_activo():
        return None
    try:
        return Historico()
    except Exception:  # noqa: BLE001 -- el histórico es complementario, nunca obligatorio
        return None


def construir_analisis_diario(rango: str = "semana", marca: str | None = None) -> dict:
    """Análisis diario con narrativa (F6/#146) como dict JSON-serializable.

    Lectura accionable del periodo: qué se movió, la(s) pieza(s) que lo explican y
    el siguiente paso. Incluye `fuente`/`es_muestra` para que la UI marque cuando
    los datos son de muestra (issue #131). Propaga `ValueError` (rango inválido) y
    `CuentaNoEncontrada` (marca fuera de alcance).
    """
    return _analisis.construir_analisis(_fuente(marca), rango, marca, _historico_lectura())


def analisis_diario_markdown(rango: str = "semana", marca: str | None = None) -> str:
    """Análisis diario renderizado a Markdown (misma narrativa que el MCP/CLI)."""
    return _analisis.render_markdown(construir_analisis_diario(rango, marca))


# Tope de piezas a descargar por cuenta para las estadísticas. `mejores_piezas` ya
# trae TODAS las del periodo y recorta; con un tope alto cubrimos top/peores y la
# distribución sin coste extra de API (la fuente de muestra crece su pool hasta n).
_TOPE_PIEZAS = 100


def construir_analitica_piezas(rango: str = "mes", marca: str | None = None) -> dict:
    """Analítica de piezas del periodo: estadísticas + top 5 + peores 5 + distribución.

    Coste 0 de API: reúsa las piezas que `mejores_piezas` ya descarga del periodo.
    `marca=None` agrega todas las cuentas en alcance (tab "Todas"); con marca, esa
    cuenta. Propaga `ValueError` (rango inválido) y `CuentaNoEncontrada` (marca fuera
    de alcance). Devuelve un dict JSON-serializable (`AnaliticaPiezas`).
    """
    fuente = _fuente(marca)
    desde, hasta, _ = resolver_rango(rango)
    piezas = []
    for c in fuente.cuentas():
        piezas.extend(fuente.mejores_piezas(c.id, rango, _TOPE_PIEZAS))

    top, peores = _estadisticas.top_y_peores(piezas, n=5)
    analitica = AnaliticaPiezas(
        cuenta=marca,
        rango=rango,
        periodo=Periodo(desde=desde, hasta=hasta),
        total=len(piezas),
        fuente=nombre_fuente(),
        engagement=_estadisticas.resumen_numerico(p.engagement_pct for p in piezas),
        visualizaciones=_estadisticas.resumen_numerico(p.visualizaciones for p in piezas),
        top=top,
        peores=peores,
        distribucion=_estadisticas.buckets_engagement(piezas),
    )
    return analitica.model_dump(mode="json")


def construir_listado_piezas(rango: str = "mes", marca: str | None = None) -> list[dict]:
    """Lista los posts YA PUBLICADOS del periodo, para SELECCIONARLOS (no para rankear).

    A diferencia de `construir_analitica_piezas` (top/peores + distribucion), esto
    devuelve el listado COMPLETO de piezas de la(s) cuenta(s) en alcance, ordenado por
    fecha de publicacion descendente (lo mas reciente primero), pensado para un selector:
    el apartado Comercial lo usa para elegir QUE pieza monitorizar por su `id` de
    Metricool, sin que nadie pegue enlaces a mano.

    Cada elemento trae lo necesario para identificar y previsualizar el post: `id`
    (id de Metricool), `red`, `titulo`, `publicado` (ISO), `visualizaciones`,
    `interacciones`, `engagement_pct` y `url`. Reusa `mejores_piezas` (coste de API ya
    pagado por el dashboard). `marca=None` agrega todas las cuentas en alcance.
    Propaga `ValueError` (rango invalido) y `CuentaNoEncontrada` (marca fuera de alcance).
    """
    fuente = _fuente(marca)
    piezas = []
    for c in fuente.cuentas():
        piezas.extend(fuente.mejores_piezas(c.id, rango, _TOPE_PIEZAS))
    # Orden estable: mas recientes primero; a igualdad de fecha, mayor engagement antes.
    piezas.sort(key=lambda p: (p.publicado.isoformat(), p.engagement_pct), reverse=True)
    return [
        {
            "id": p.id,
            "red": p.plataforma.value,
            "titulo": p.titulo,
            "publicado": p.publicado.isoformat(),
            "visualizaciones": p.visualizaciones,
            "interacciones": p.interacciones,
            "engagement_pct": p.engagement_pct,
            "url": p.url,
            # Métricas granulares (None cuando la fuente no las trae; ver schema).
            "likes": p.likes,
            "comentarios": p.comentarios,
            "compartidos": p.compartidos,
            "guardados": p.guardados,
            "video_views": p.video_views,
            "tiempo_medio_vis_s": p.tiempo_medio_vis_s,
            "clics_enlace": p.clics_enlace,
            "formato": p.formato,
        }
        for p in piezas
    ]


def construir_tendencia_diaria(rango: str = "mes", marca: str | None = None) -> dict:
    """Serie diaria del periodo (visualizaciones + interacciones) sumada por cuenta.

    Dispatch por capacidad: usa `fuente.serie_diaria` si la fuente activa la expone
    (muestra/Metricool); si no (fuentes 'real' compuestas), degrada a serie vacía sin
    romper. Devuelve un dict JSON-serializable (`SerieDiaria`).
    """
    fuente = _fuente(marca)
    desde, hasta, _ = resolver_rango(rango)
    serie_fn = getattr(fuente, "serie_diaria", None)
    vis: dict = {}
    inter: dict = {}
    if serie_fn is not None:
        for c in fuente.cuentas():
            try:
                puntos = serie_fn(c.id, rango)
            except AttributeError:
                # La fuente envuelta no la implementa (FuenteScoped lo propaga): degrada.
                puntos = []
            for p in puntos:
                vis[p.fecha] = vis.get(p.fecha, 0) + p.visualizaciones
                inter[p.fecha] = inter.get(p.fecha, 0) + p.interacciones

    fechas = sorted(set(vis) | set(inter))
    puntos = [
        PuntoSerie(fecha=f, visualizaciones=vis.get(f, 0), interacciones=inter.get(f, 0))
        for f in fechas
    ]
    serie = SerieDiaria(
        cuenta=marca,
        rango=rango,
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=nombre_fuente(),
        puntos=puntos,
    )
    return serie.model_dump(mode="json")


def construir_metricas_pieza(marca: str, red: str, id_post: str) -> dict:
    """Rendimiento REAL de UNA pieza ya publicada (por su `id_post` de Metricool).

    `marca` es el id_metricas (guion_bajo) de la cuenta; `red` la plataforma keni
    ('facebook'|'instagram'|'x'|'tiktok'|'youtube'); `id_post` el id que devolvio el
    scheduler de Metricool al programar (lo guarda la Consola en
    `contenido_plataforma.id_post_metricool`). Lo consume el tablero para pintar el
    rendimiento en cada tarjeta SIN adaptadores por red: una sola lectura sobre la
    fuente activa (Metricool de pago en prod; muestra en demo).

    Devuelve un dict JSON-serializable (`MetricaPieza`). Si la red no es valida, la
    fuente no expone la lectura por post (fuentes 'real' compuestas), o Metricool aun
    no tiene datos del post, devuelve `encontrado=False` (la UI muestra "sin datos
    todavia", nunca ceros falsos). Propaga `CuentaNoEncontrada` (marca fuera de alcance).
    """
    try:
        plat = Plataforma(red)
    except ValueError:
        return _pieza_sin_datos(id_post, red).model_dump(mode="json")

    fuente = _fuente(marca)
    leer = getattr(fuente, "metricas_de_post", None)
    if leer is None:
        return _pieza_sin_datos(id_post, plat.value).model_dump(mode="json")
    try:
        metrica = leer(marca, plat, id_post)
    except AttributeError:
        # La fuente envuelta no lo implementa (FuenteScoped lo propaga): degrada.
        metrica = None
    if metrica is None:
        metrica = _pieza_sin_datos(id_post, plat.value)
    return metrica.model_dump(mode="json")


def _pieza_sin_datos(id_post: str, red: str) -> MetricaPieza:
    """`MetricaPieza` vacia (encontrado=False) para 'sin datos todavia' sin romper.

    Usa una plataforma valida si `red` lo es; si no, cae a facebook como placeholder
    (el campo `encontrado=False` ya le dice a la UI que no hay rendimiento real).
    """
    try:
        plat = Plataforma(red)
    except ValueError:
        plat = Plataforma.facebook
    return MetricaPieza(
        id_post=str(id_post), plataforma=plat, encontrado=False, fuente=nombre_fuente()
    )


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
    # `real` es un fallback histórico desactivado por defecto (ver config): no se
    # persiste desde la fachada sin el flag opt-in, para no dejar el config apuntando a
    # una fuente que rompería la lectura del tablero. La fuente única es `metricool`.
    if fuente == "real" and not _config._real_permitida():
        raise ValueError(
            "La fuente 'real' está desactivada (dejaría el rendimiento por pieza sin "
            f"datos). Usa 'metricool' o 'muestra', o exporta {_config.ENV_PERMITIR_REAL}=1."
        )
    ruta = _config.ruta_config()
    existente = asistente.leer_config_existente(ruta)
    nuevo: dict = {"fuente": fuente}
    if marcas:
        nuevo["marcas"] = list(marcas)
    fusionado = asistente.fusionar_config(existente, nuevo)
    if not marcas:
        fusionado.pop("marcas", None)
    asistente.escribir_config_atomico(ruta, fusionado)

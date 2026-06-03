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
    CeldaCrosstab,
    CeldaDesglose,
    CeldaHorario,
    CorrelacionSeguidores,
    Crosstab,
    DesgloseInteracciones,
    Horarios,
    ItemCorrelacion,
    MetricaPieza,
    Periodo,
    Plataforma,
    PostEstrella,
    PuntoSeguidores,
    PuntoSerie,
    SerieDiaria,
    SerieSeguidores,
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
    "construir_serie_seguidores",
    "construir_desglose_interacciones",
    "construir_crosstab",
    "construir_horarios",
    "construir_correlacion_seguidores",
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


# Tope de piezas por cuenta para las ESTADÍSTICAS del periodo. Debe cubrir TODAS las
# piezas del rango: si se trunca, la mediana/percentiles/distribución/`total` se calculan
# sobre un subconjunto SESGADO (mejores_piezas ordena por engagement antes de recortar) y
# no reflejan el periodo real (una marca puede tener cientos de posts/mes). El coste extra
# es nulo en API (la llamada a /posts ya devuelve todo el periodo; esto solo evita el
# recorte en memoria).
_TOPE_PIEZAS = 100_000


def construir_analitica_piezas(rango: str = "mes", marca: str | None = None) -> dict:
    """Analítica de piezas del periodo: estadísticas + top 10 + peores 10 + distribución.

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

    top, peores = _estadisticas.top_y_peores(piezas, n=10)
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
            # cuenta (id_metricas) y rendimiento_relativo (vs la mediana del grupo):
            # None cuando la fuente no los aporta. Mismos campos que `Pieza`/`PiezaMetrica`.
            "cuenta": p.cuenta,
            "rendimiento_relativo": p.rendimiento_relativo,
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


# --------------------------------------------------------------------------- #
# Análisis de estrategia digital — REUSAN serie de followers + piezas          #
# --------------------------------------------------------------------------- #
#
# Cuatro lecturas ricas de la estrategia digital, todas a COSTE 0 de API extra:
# reúsan la serie de followers que ya consulta `seguidores_netos` (vía la nueva
# `fuente.serie_seguidores`) y las piezas granulares que ya descarga el dashboard
# (`mejores_piezas`). Filosofía: degradación honesta — si un dato no está, None/0/
# vacío, nunca inventado.


def _piezas_periodo(fuente, rango: str) -> list:
    """Reúne las piezas del periodo de TODAS las cuentas en alcance de `fuente`.

    Mismo camino que `construir_analitica_piezas`/`construir_listado_piezas`: itera
    las cuentas y acumula `mejores_piezas` con un tope alto para cubrir el periodo.
    Coste 0 de API extra (las piezas ya las descarga el dashboard).
    """
    piezas = []
    for c in fuente.cuentas():
        piezas.extend(fuente.mejores_piezas(c.id, rango, _TOPE_PIEZAS))
    return piezas


def _serie_seguidores_cuentas(fuente, rango: str) -> dict[str, list[dict]]:
    """Serie de followers por cuenta: `{cuenta_id: [{"fecha", "por_red"}, ...]}`.

    Dispatch por capacidad: usa `fuente.serie_seguidores` si la fuente la expone
    (muestra/Metricool); si no (fuentes 'real' compuestas) o si la cuenta no trae
    serie, esa cuenta se omite. Devuelve `{}` cuando NINGUNA cuenta aporta serie
    (la fuente no soporta followers) — degradación honesta.
    """
    serie_fn = getattr(fuente, "serie_seguidores", None)
    if serie_fn is None:
        return {}
    out: dict[str, list[dict]] = {}
    for c in fuente.cuentas():
        try:
            puntos = serie_fn(c.id, rango)
        except AttributeError:
            # La fuente envuelta no la implementa (FuenteScoped lo propaga): degrada.
            return {}
        if puntos:
            out[c.id] = puntos
    return out


def construir_serie_seguidores(rango: str = "mes", marca: str | None = None) -> dict:
    """Crecimiento de seguidores POR DÍA y por red (suma de las cuentas en alcance).

    REÚSA la serie de followers que ya consulta `seguidores_netos` (la misma de
    `/v2/analytics/timelines`), expuesta ahora como `fuente.serie_seguidores`. Por
    cada día: `total` = suma del stock de followers de cada red ese día; `neto` =
    último − primer total. Una red que no expone followers se OMITE (no 0 falso).
    Si la fuente no soporta followers, `puntos=[]` y `neto=0` (degradación honesta).
    Devuelve un dict JSON-serializable (`SerieSeguidores`).
    """
    return serie_seguidores_desde_fuente(_fuente(marca), rango, marca)


def serie_seguidores_desde_fuente(fuente, rango: str, marca: str | None = None) -> dict:
    """Worker de `construir_serie_seguidores` sobre una `fuente` explícita (lo usa el MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    series = _serie_seguidores_cuentas(fuente, rango)

    # Suma el stock por (fecha, red) sobre todas las cuentas en alcance.
    por_dia: dict[str, dict[str, int]] = {}
    for puntos in series.values():
        for punto in puntos:
            fecha = punto["fecha"]
            dest = por_dia.setdefault(fecha, {})
            for red, valor in (punto.get("por_red") or {}).items():
                dest[red] = dest.get(red, 0) + int(valor)

    puntos_out: list[PuntoSeguidores] = []
    for fecha in sorted(por_dia):
        por_red = por_dia[fecha]
        puntos_out.append(
            PuntoSeguidores(fecha=fecha, total=sum(por_red.values()), por_red=por_red)
        )

    # Neto del periodo: último − primero (la serie de followers es un STOCK).
    neto = 0
    neto_por_red: dict[str, int] = {}
    if len(puntos_out) >= 2:
        primero, ultimo = puntos_out[0], puntos_out[-1]
        neto = ultimo.total - primero.total
        for red in set(primero.por_red) | set(ultimo.por_red):
            neto_por_red[red] = ultimo.por_red.get(red, 0) - primero.por_red.get(red, 0)

    serie = SerieSeguidores(
        cuenta=marca,
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
        puntos=puntos_out,
        neto=neto,
        neto_por_red=neto_por_red,
    )
    return serie.model_dump(mode="json")


def construir_desglose_interacciones(rango: str = "mes", marca: str | None = None) -> dict:
    """Desglose de engagement (likes/comentarios/compartidos/guardados/video_views)
    agregado por MARCA×RED.

    AGREGA desde las piezas del periodo (que ya traen los campos granulares). Los
    campos granulares ausentes (None) cuentan como 0 SOLO en la suma; `n_piezas`
    cuenta TODAS las piezas del grupo. `engagement_pct` de la celda =
    interacciones/visualizaciones*100 (0 si no hay visualizaciones). Devuelve un
    dict JSON-serializable (`DesgloseInteracciones`).
    """
    return desglose_interacciones_desde_fuente(_fuente(marca), rango)


def desglose_interacciones_desde_fuente(fuente, rango: str) -> dict:
    """Worker de `construir_desglose_interacciones` sobre una `fuente` explícita (MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    piezas = _piezas_periodo(fuente, rango)

    _campos = ("likes", "comentarios", "compartidos", "guardados", "video_views")
    # Acumula por (marca, red). marca None -> "" (sin marca) para que la clave sea str.
    acc: dict[tuple[str, str], dict] = {}
    for p in piezas:
        clave = (p.cuenta or "", p.plataforma.value)
        celda = acc.setdefault(
            clave,
            {
                "likes": 0, "comentarios": 0, "compartidos": 0, "guardados": 0,
                "video_views": 0, "interacciones": 0, "visualizaciones": 0, "n_piezas": 0,
            },
        )
        for campo in _campos:
            celda[campo] += getattr(p, campo) or 0  # None -> 0 solo en la suma
        celda["interacciones"] += p.interacciones or 0
        celda["visualizaciones"] += p.visualizaciones or 0
        celda["n_piezas"] += 1

    celdas: list[CeldaDesglose] = []
    totales = {c: 0 for c in (*_campos, "interacciones", "visualizaciones")}
    for (marca_k, red), c in sorted(acc.items()):
        vis = c["visualizaciones"]
        celdas.append(
            CeldaDesglose(
                marca=marca_k,
                red=red,
                likes=c["likes"],
                comentarios=c["comentarios"],
                compartidos=c["compartidos"],
                guardados=c["guardados"],
                video_views=c["video_views"],
                interacciones=c["interacciones"],
                visualizaciones=vis,
                engagement_pct=round(c["interacciones"] / vis * 100, 2) if vis else 0.0,
                n_piezas=c["n_piezas"],
            )
        )
        for campo in totales:
            totales[campo] += c[campo]

    desglose = DesgloseInteracciones(
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
        celdas=celdas,
        totales=totales,
    )
    return desglose.model_dump(mode="json")


def construir_crosstab(rango: str = "mes", marca: str | None = None) -> dict:
    """Cruce MARCA×RED×FORMATO de las piezas del periodo.

    Agrupa las piezas por (marca, red, formato). `rendimiento_relativo_medio` = media
    del `rendimiento_relativo` (no-None) del grupo, computado con
    `estadisticas.anotar_rendimiento_relativo` sobre TODAS las piezas antes de agrupar
    (normaliza contra el baseline marca×red). None si ninguna pieza del grupo lo tiene.
    Devuelve un dict JSON-serializable (`Crosstab`).
    """
    return crosstab_desde_fuente(_fuente(marca), rango)


def crosstab_desde_fuente(fuente, rango: str) -> dict:
    """Worker de `construir_crosstab` sobre una `fuente` explícita (lo usa el MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    piezas = _piezas_periodo(fuente, rango)
    # Anota el rendimiento relativo (vs. la mediana del grupo marca×red) ANTES de
    # agrupar por formato: así el score por pieza ya está disponible al promediar.
    _estadisticas.anotar_rendimiento_relativo(piezas)

    acc: dict[tuple[str, str, str | None], dict] = {}
    for p in piezas:
        clave = (p.cuenta or "", p.plataforma.value, p.formato)
        grupo = acc.setdefault(
            clave, {"n_piezas": 0, "visualizaciones": 0, "interacciones": 0, "rr": []}
        )
        grupo["n_piezas"] += 1
        grupo["visualizaciones"] += p.visualizaciones or 0
        grupo["interacciones"] += p.interacciones or 0
        if p.rendimiento_relativo is not None:
            grupo["rr"].append(p.rendimiento_relativo)

    celdas: list[CeldaCrosstab] = []
    # Orden estable: marca, red, formato (None al final).
    for (marca_k, red, formato) in sorted(acc, key=lambda k: (k[0], k[1], k[2] is None, k[2] or "")):
        g = acc[(marca_k, red, formato)]
        vis = g["visualizaciones"]
        rr = g["rr"]
        celdas.append(
            CeldaCrosstab(
                marca=marca_k,
                red=red,
                formato=formato,
                n_piezas=g["n_piezas"],
                visualizaciones=vis,
                interacciones=g["interacciones"],
                engagement_pct=round(g["interacciones"] / vis * 100, 2) if vis else 0.0,
                rendimiento_relativo_medio=round(sum(rr) / len(rr), 3) if rr else None,
            )
        )

    crosstab = Crosstab(
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
        celdas=celdas,
    )
    return crosstab.model_dump(mode="json")


# Mínimo de piezas para que una celda del heatmap sea candidata a "mejor": evita que
# una franja con 1 sola pieza de engagement atípico se proclame la mejor hora.
_MIN_PIEZAS_MEJOR_HORARIO = 3


def construir_horarios(rango: str = "mes", marca: str | None = None) -> dict:
    """Heatmap día-de-la-semana × hora del rendimiento de las piezas del periodo.

    Responde "¿cuándo conviene publicar?": agrupa las piezas del periodo por
    (día_semana, hora_de_publicación) y suma visualizaciones/interacciones. Reúsa el
    mismo camino que `construir_analitica_piezas`/`construir_crosstab` (coste 0 de API:
    las piezas ya las descarga el dashboard). Las piezas SIN hora conocida
    (`publicado_hora is None`) se OMITEN del heatmap (degradación honesta: no se
    fabrica la medianoche). `mejor` = la celda con mayor engagement entre las que
    superan `_MIN_PIEZAS_MEJOR_HORARIO`. Devuelve un dict JSON-serializable (`Horarios`).
    """
    return horarios_desde_fuente(_fuente(marca), rango, marca)


def horarios_desde_fuente(fuente, rango: str, marca: str | None = None) -> dict:
    """Worker de `construir_horarios` sobre una `fuente` explícita (lo usa el MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    piezas = _piezas_periodo(fuente, rango)

    acc: dict[tuple[int, int], dict] = {}
    for p in piezas:
        if p.publicado_hora is None:
            continue  # sin hora no entra al heatmap (no se inventa la medianoche)
        clave = (p.publicado.weekday(), p.publicado_hora)
        grupo = acc.setdefault(clave, {"n_piezas": 0, "visualizaciones": 0, "interacciones": 0})
        grupo["n_piezas"] += 1
        grupo["visualizaciones"] += p.visualizaciones or 0
        grupo["interacciones"] += p.interacciones or 0

    celdas: list[CeldaHorario] = []
    for (dia, hora) in sorted(acc):
        g = acc[(dia, hora)]
        vis = g["visualizaciones"]
        celdas.append(
            CeldaHorario(
                dia_semana=dia,
                hora=hora,
                n_piezas=g["n_piezas"],
                visualizaciones=vis,
                interacciones=g["interacciones"],
                engagement_pct=round(g["interacciones"] / vis * 100, 2) if vis else 0.0,
            )
        )

    candidatas = [c for c in celdas if c.n_piezas >= _MIN_PIEZAS_MEJOR_HORARIO]
    mejor = max(candidatas, key=lambda c: c.engagement_pct, default=None)

    horarios = Horarios(
        cuenta=marca,
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
        celdas=celdas,
        mejor=mejor,
    )
    return horarios.model_dump(mode="json")


# Caveat de atribución para la correlación seguidores↔posts. Honesto a propósito:
# el delta diario de followers NO es atribuible 1:1 a un post.
_NOTA_CORRELACION = (
    "Correlación, no causalidad: el crecimiento diario de seguidores no es atribuible "
    "1:1 a las publicaciones de ese día (influyen campañas, tendencias, recomendación "
    "del algoritmo y arrastre de días previos). 'seguidores_por_post' es un reparto "
    "indicativo, no una métrica de atribución."
)
_NOTA_SIN_SERIE = (
    "La fuente activa no expone serie de seguidores, así que no se puede correlacionar "
    "crecimiento de comunidad con publicaciones."
)


def construir_correlacion_seguidores(rango: str = "mes", marca: str | None = None) -> dict:
    """Correlación (NO causalidad) crecimiento de seguidores ↔ publicaciones.

    Por (marca, red, día): `seguidores_ganados` = delta diario de la serie de
    followers (punto N − N-1); `n_posts` = piezas publicadas ese día;
    `seguidores_por_post` = ganados/n_posts si n_posts>0 (None si 0); `post_estrella`
    = la pieza de mayor engagement ese día. Si no hay serie de followers, `items=[]`
    y `nota` lo explica. Devuelve un dict JSON-serializable (`CorrelacionSeguidores`).
    """
    return correlacion_seguidores_desde_fuente(_fuente(marca), rango)


def correlacion_seguidores_desde_fuente(fuente, rango: str) -> dict:
    """Worker de `construir_correlacion_seguidores` sobre una `fuente` explícita (MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    series = _serie_seguidores_cuentas(fuente, rango)
    base = dict(
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
    )
    if not series:
        return CorrelacionSeguidores(**base, items=[], nota=_NOTA_SIN_SERIE).model_dump(mode="json")

    # Piezas indexadas por (marca, red, fecha) para contar posts y hallar la estrella.
    piezas = _piezas_periodo(fuente, rango)
    por_dia: dict[tuple[str, str, str], list] = {}
    for p in piezas:
        clave = (p.cuenta or "", p.plataforma.value, p.publicado.isoformat())
        por_dia.setdefault(clave, []).append(p)

    items: list[ItemCorrelacion] = []
    for cuenta_id, puntos in series.items():
        # delta diario de followers por red: punto N − N-1 (la serie es un STOCK).
        anterior: dict[str, int] = {}
        for idx, punto in enumerate(puntos):
            fecha = punto["fecha"]
            por_red = punto.get("por_red") or {}
            for red, stock in por_red.items():
                if idx == 0 or red not in anterior:
                    # Primer punto (o primera vez que vemos esa red): no hay delta previo.
                    anterior[red] = stock
                    continue
                ganados = int(stock) - anterior[red]
                anterior[red] = stock
                piezas_dia = por_dia.get((cuenta_id, red, fecha), [])
                n_posts = len(piezas_dia)
                estrella = None
                if piezas_dia:
                    mejor = max(piezas_dia, key=lambda x: x.engagement_pct)
                    estrella = PostEstrella(
                        id=mejor.id,
                        titulo=mejor.titulo,
                        engagement_pct=mejor.engagement_pct,
                        url=mejor.url,
                    )
                items.append(
                    ItemCorrelacion(
                        marca=cuenta_id,
                        red=red,
                        fecha=fecha,
                        seguidores_ganados=ganados,
                        n_posts=n_posts,
                        seguidores_por_post=(
                            round(ganados / n_posts, 2) if n_posts > 0 else None
                        ),
                        post_estrella=estrella,
                    )
                )

    items.sort(key=lambda it: (it.fecha.isoformat(), it.marca, it.red))
    return CorrelacionSeguidores(**base, items=items, nota=_NOTA_CORRELACION).model_dump(
        mode="json"
    )


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

"""Rendimiento REAL del periodo AGRUPADO por LÍNEA de contenido y por ORIGEN.

PROBLEMA QUE RESUELVE
=====================
Las analíticas saben qué pieza rinde (`metricas_pieza`) y qué tipo/etiqueta rinde
(`metricas_pieza.analitica_por_etiqueta`), pero el equipo razona en términos de LÍNEAS
editoriales (futbol, presidencia, virales…) y de ORIGEN (interno vs petición externa).
Estos dos ejes son etiquetas N:M de la pieza, de las clases `vertical` (= LÍNEA) y
`origen`. Aquí cerramos "qué LÍNEA funciona" y el dual editorial-vs-impuesto.

CÓMO
====
Reusa EXACTAMENTE el mismo cruce pieza↔contenido que `analitica_por_etiqueta`
(`metricas_pieza`): toma las piezas del periodo de la fuente única de métricas
(`servicio.construir_listado_piezas`, el mismo coste de API ya pagado por el dashboard),
las enlaza a su `contenido` de la BD por `id_post_metricool` (fallback fuzzy por título)
y lee sus etiquetas por clase. NO duplica la conexión a Metricool ni toca `repos`/`db`.

La agregación es PURA y separada de la lectura de BD (`agregar_por_eje` /
`agregar_lineas_y_origenes`): recibe datos en memoria y es testeable sin BD, igual que el
resto de agregaciones del módulo. El orquestador `lineas_y_origenes` hace las lecturas
(repos + fachada de métricas) y delega en la función pura.

Por cada LÍNEA definida de la marca (etiqueta clase `vertical`) y por cada ORIGEN
(clase `origen`) devuelve: nº de piezas, suma de visualizaciones, suma de interacciones y
engagement medio. Las piezas sin valor en el eje caen en el cubo "Sin línea" / "Sin
origen". Solo LECTURA; no muta nada.
"""

from __future__ import annotations

import logging
from typing import Any

from keni_metricas import servicio

from . import repos
from .metricas_pieza import _indice_contenido_por_post, _normalizar_titulo

_log = logging.getLogger("keni_consola.metricas_linea")

# Clases de etiqueta de cada eje de agrupación (etiquetas.clase).
CLASE_VERTICAL = "vertical"
CLASE_ORIGEN = "origen"

# Cubos por defecto para las piezas sin valor en el eje (honesto: no se inventa una línea).
SIN_LINEA = "Sin línea"
SIN_ORIGEN = "Sin origen"


def agregar_por_eje(
    piezas: list[dict[str, Any]],
    *,
    valor_por_contenido: dict[str, str],
    enlace_por_id: dict[str, str],
    enlace_por_titulo: dict[str, str],
    etiquetas_definidas: list[dict[str, str]],
    sin_valor: str,
) -> list[dict[str, Any]]:
    """Agrega el rendimiento de las piezas del periodo por UN eje de etiqueta. PURA (sin BD).

    Parámetros (todo en memoria, para ser testeable sin Postgres):
      - `piezas`: lista de piezas del periodo (forma de `servicio.construir_listado_piezas`,
        cada una con `id`, `titulo`, `visualizaciones`, `interacciones`, `engagement_pct`).
      - `valor_por_contenido`: `contenido_id -> nombre de la etiqueta de ESTE eje` (vacío o
        ausente = la pieza no tiene valor en el eje).
      - `enlace_por_id` / `enlace_por_titulo`: índices de enlace pieza→contenido
        (`id_post_metricool -> contenido_id` y `titulo_normalizado -> contenido_id`),
        idénticos a los de `metricas_pieza` (enlace fuerte por id; fallback fuzzy por título).
      - `etiquetas_definidas`: las etiquetas del eje de la marca (`[{"id","nombre"}, …]`),
        para que una LÍNEA definida SIN piezas en el periodo aparezca igualmente con ceros.
      - `sin_valor`: nombre del cubo de las piezas sin valor en el eje ("Sin línea"/…).

    Devuelve la lista de cubos `[{id, nombre, piezas, visualizaciones, interacciones,
    engagement_pct}]` ordenada por nº de piezas desc y luego visualizaciones desc. El cubo
    "Sin …" siempre va al final (`id=""`). El engagement es la MEDIA de los engagement de
    las piezas del cubo (mismo criterio que `analitica_por_etiqueta`), 0.0 si no hay piezas.
    """
    # Cubos sembrados con las etiquetas DEFINIDAS de la marca (aparecen aunque tengan 0
    # piezas) + el cubo "Sin …". Clave del acumulador = nombre del cubo.
    acum: dict[str, dict[str, Any]] = {}
    nombre_a_id: dict[str, str] = {}
    for et in etiquetas_definidas:
        nombre = et.get("nombre") or ""
        if not nombre:
            continue
        nombre_a_id.setdefault(nombre, et.get("id") or "")
        acum.setdefault(
            nombre, {"n": 0, "visualizaciones": 0, "interacciones": 0, "_eng_sum": 0.0}
        )
    acum.setdefault(sin_valor, {"n": 0, "visualizaciones": 0, "interacciones": 0, "_eng_sum": 0.0})

    for p in piezas:
        cid = enlace_por_id.get(str(p.get("id") or ""))
        if not cid:
            cid = enlace_por_titulo.get(_normalizar_titulo(p.get("titulo", "")))
        valor = (valor_por_contenido.get(cid or "") or "").strip() or sin_valor
        cubo = acum.setdefault(
            valor, {"n": 0, "visualizaciones": 0, "interacciones": 0, "_eng_sum": 0.0}
        )
        cubo["n"] += 1
        cubo["visualizaciones"] += int(p.get("visualizaciones", 0) or 0)
        cubo["interacciones"] += int(p.get("interacciones", 0) or 0)
        cubo["_eng_sum"] += float(p.get("engagement_pct", 0.0) or 0.0)

    salida: list[dict[str, Any]] = []
    for nombre, c in acum.items():
        n = c["n"]
        salida.append(
            {
                "id": "" if nombre == sin_valor else nombre_a_id.get(nombre, ""),
                "nombre": nombre,
                "piezas": n,
                "visualizaciones": c["visualizaciones"],
                "interacciones": c["interacciones"],
                "engagement_pct": round(c["_eng_sum"] / n, 2) if n else 0.0,
            }
        )
    # Orden: el cubo "Sin …" siempre al final; el resto por nº de piezas desc, luego
    # visualizaciones desc (lo más usado/visto arriba).
    salida.sort(
        key=lambda x: (x["nombre"] == sin_valor, -x["piezas"], -x["visualizaciones"])
    )
    return salida


def agregar_lineas_y_origenes(
    piezas: list[dict[str, Any]],
    *,
    linea_por_contenido: dict[str, str],
    origen_por_contenido: dict[str, str],
    enlace_por_id: dict[str, str],
    enlace_por_titulo: dict[str, str],
    lineas_definidas: list[dict[str, str]],
    origenes_definidos: list[dict[str, str]],
) -> dict[str, Any]:
    """Agrega el periodo por LÍNEA y por ORIGEN a la vez. PURA (sin BD).

    Combina dos llamadas a `agregar_por_eje` (una por eje) sobre el MISMO listado de piezas.
    Devuelve `{"lineas": [...], "origenes": [...]}` con la forma del contrato del endpoint.
    """
    lineas = agregar_por_eje(
        piezas,
        valor_por_contenido=linea_por_contenido,
        enlace_por_id=enlace_por_id,
        enlace_por_titulo=enlace_por_titulo,
        etiquetas_definidas=lineas_definidas,
        sin_valor=SIN_LINEA,
    )
    origenes = agregar_por_eje(
        piezas,
        valor_por_contenido=origen_por_contenido,
        enlace_por_id=enlace_por_id,
        enlace_por_titulo=enlace_por_titulo,
        etiquetas_definidas=origenes_definidos,
        sin_valor=SIN_ORIGEN,
    )
    return {"lineas": lineas, "origenes": origenes}


def _valor_por_contenido(
    asignaciones: dict[str, list[str]],
    etiquetas_de_clase: dict[str, str],
) -> dict[str, str]:
    """`contenido_id -> nombre de la etiqueta de ESA clase` (la primera asignada que sea de la clase).

    `asignaciones` es `contenido_id -> [etiqueta_id…]` (`repos.etiquetas_por_contenido`);
    `etiquetas_de_clase` es `etiqueta_id -> nombre` SOLO de las etiquetas de la clase del eje.
    El modelo garantiza nombre único por clase, así que basta con la primera coincidencia.
    """
    salida: dict[str, str] = {}
    for cid, ids in asignaciones.items():
        for eid in ids:
            nombre = etiquetas_de_clase.get(eid)
            if nombre:
                salida.setdefault(cid, nombre)
                break
    return salida


def lineas_y_origenes(
    rango: str, marca_consola: str | None, marca_metricas: str | None
) -> dict[str, Any]:
    """Rendimiento del periodo por LÍNEA (clase `vertical`) y por ORIGEN (clase `origen`).

    Orquesta las lecturas (BD via `repos` + piezas del periodo via la fachada única de
    métricas) y delega la agregación en la función PURA `agregar_lineas_y_origenes`. Reusa
    el MISMO cruce pieza↔contenido que `analitica_por_etiqueta` (enlace por
    `id_post_metricool`; fallback fuzzy por título). No duplica la conexión a Metricool.

    Devuelve `{"lineas": [...], "origenes": [...], "total": <piezas del periodo>,
    "fuente": <muestra|real|…>}`. Best-effort/honesto: si nada enlaza, todas las piezas
    caen en "Sin línea"/"Sin origen".
    """
    piezas = servicio.construir_listado_piezas(rango, marca_metricas)
    fuente = servicio.nombre_fuente()

    contenidos = repos.listar_contenido(marca=marca_consola)
    plataformas = repos.listar_contenido_plataforma()
    enlace_por_id, enlace_por_titulo = _indice_contenido_por_post(contenidos, plataformas)

    # Etiquetas DEFINIDAS de la marca por eje (incluye globales; `listar_etiquetas` ya las
    # mezcla con marca=''). Filtra por clase en la BD para no traer de más.
    lineas_def = [
        {"id": e.get("id", ""), "nombre": e.get("nombre", "")}
        for e in repos.listar_etiquetas(marca=marca_consola, clase=CLASE_VERTICAL)
    ]
    origenes_def = [
        {"id": e.get("id", ""), "nombre": e.get("nombre", "")}
        for e in repos.listar_etiquetas(marca=marca_consola, clase=CLASE_ORIGEN)
    ]
    # `etiqueta_id -> nombre` por clase, para resolver la etiqueta de cada contenido.
    vertical_por_id = {e["id"]: e["nombre"] for e in lineas_def if e.get("id")}
    origen_por_id = {e["id"]: e["nombre"] for e in origenes_def if e.get("id")}

    asignaciones = repos.etiquetas_por_contenido()
    linea_por_contenido = _valor_por_contenido(asignaciones, vertical_por_id)
    origen_por_contenido = _valor_por_contenido(asignaciones, origen_por_id)

    agregados = agregar_lineas_y_origenes(
        piezas,
        linea_por_contenido=linea_por_contenido,
        origen_por_contenido=origen_por_contenido,
        enlace_por_id=enlace_por_id,
        enlace_por_titulo=enlace_por_titulo,
        lineas_definidas=lineas_def,
        origenes_definidos=origenes_def,
    )
    return {**agregados, "total": len(piezas), "fuente": fuente}

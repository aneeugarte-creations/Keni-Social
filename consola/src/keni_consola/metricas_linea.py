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

La agregación es PURA y separada de la lectura de BD (`agrupar_por_eje` /
`agrupar_lineas_y_origenes`): recibe datos en memoria y es testeable sin BD, igual que el
resto de agregaciones del módulo. El orquestador `lineas_y_origenes` hace las lecturas
(repos + fachada de métricas) y delega en la función pura.

La LÍNEA agrupa por la `categoria` de PLAN del contenido (la misma del monitor de
Producción): incluye la línea reutilizable EVERGREEN (que no es una etiqueta `vertical`)
además de las verticales activas; `breaking` (Última hora) es una SEÑAL, no una línea, así
que cae a la vertical de la pieza, igual que las altas manuales sin categoría. El ORIGEN sí
es la etiqueta de clase `origen`. Por cada cubo devuelve:
nº de piezas, suma de visualizaciones, suma de interacciones y engagement medio; las piezas
sin valor caen en "Sin línea" / "Sin origen". Solo LECTURA; no muta nada.
"""

from __future__ import annotations

import logging
from typing import Any

from keni_metricas import servicio

from . import bootstrap_lineas, repos
from .metricas_pieza import (
    _indice_contenido_por_post,
    _normalizar_titulo,
    filtrar_piezas_periodo,
)

_log = logging.getLogger("keni_consola.metricas_linea")

# Clases de etiqueta de cada eje de agrupación (etiquetas.clase).
CLASE_VERTICAL = "vertical"
CLASE_ORIGEN = "origen"

# Cubos por defecto para las piezas sin valor en el eje (honesto: no se inventa una línea).
SIN_LINEA = "Sin línea"
SIN_ORIGEN = "Sin origen"


def agrupar_por_eje(
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
      - `valor_por_contenido`: `publicacion_id -> nombre de la etiqueta de ESTE eje` (vacío o
        ausente = la pieza no tiene valor en el eje).
      - `enlace_por_id` / `enlace_por_titulo`: índices de enlace pieza→contenido
        (`id_post_metricool -> publicacion_id` y `titulo_normalizado -> publicacion_id`),
        idénticos a los de `metricas_pieza` (enlace fuerte por id; fallback fuzzy por título).
      - `etiquetas_definidas`: las etiquetas del eje de la marca (`[{"id","nombre"}, …]`),
        para que una LÍNEA definida SIN piezas en el periodo aparezca igualmente con ceros.
      - `sin_valor`: nombre del cubo de las piezas sin valor en el eje ("Sin línea"/…).

    Devuelve la lista de cubos `[{id, nombre, piezas, visualizaciones, interacciones,
    engagement_pct}]` ordenada por nº de piezas desc y luego visualizaciones desc. El cubo
    "Sin …" siempre va al final (`id=""`). El engagement es la MEDIA de los engagement de
    las piezas del cubo (mismo criterio que `analitica_por_etiqueta`), 0.0 si no hay piezas.
    """
    # Cubos inicializados con las etiquetas DEFINIDAS de la marca (aparecen aunque tengan 0
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


def agrupar_lineas_y_origenes(
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

    Combina dos llamadas a `agrupar_por_eje` (una por eje) sobre el MISMO listado de piezas.
    Devuelve `{"lineas": [...], "origenes": [...]}` con la forma del contrato del endpoint.
    """
    lineas = agrupar_por_eje(
        piezas,
        valor_por_contenido=linea_por_contenido,
        enlace_por_id=enlace_por_id,
        enlace_por_titulo=enlace_por_titulo,
        etiquetas_definidas=lineas_definidas,
        sin_valor=SIN_LINEA,
    )
    origenes = agrupar_por_eje(
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
    """`publicacion_id -> nombre de la etiqueta de ESA clase` (la primera asignada que sea de la clase).

    `asignaciones` es `publicacion_id -> [etiqueta_id…]` (`repos.etiquetas_por_contenido`);
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


def linea_de_categoria(
    categoria: str,
    *,
    vertical_por_id: dict[str, str],
    etiqueta_vertical: str,
) -> str:
    """Nombre de la LÍNEA de plan de un contenido a partir de su `categoria` persistida.

    `Evergreen` SÍ es una línea del plan; `breaking` (Última hora) es una SEÑAL del motor, NO
    una línea. Resolución:
      - `evergreen` → "Evergreen" (línea reutilizable del plan);
      - `breaking` o `categoria` vacía (alta manual) → la etiqueta `vertical` asignada (o "Sin
        línea" si no tiene): la señal de última hora no define la línea editorial;
      - id de vertical ACTIVA → su nombre (`vertical_por_id`);
      - id de vertical retirada/desconocida → "" (cae en "Sin línea").
    """
    if categoria == "evergreen":
        return bootstrap_lineas.ETIQUETAS_CLAVE_NO_LINEA.get("evergreen", "Evergreen")
    if not categoria or categoria == "breaking":
        return etiqueta_vertical
    return vertical_por_id.get(categoria, "")


def _lineas_por_contenido_plan(
    contenidos: list[dict[str, Any]],
    asignaciones: dict[str, list[str]],
    vertical_por_id: dict[str, str],
) -> dict[str, str]:
    """`publicacion_id -> nombre de su LÍNEA de plan` (señales del motor incluidas).

    Combina la `categoria` persistida de cada contenido (Evergreen o vertical) con, como
    respaldo para altas manuales o señales (breaking), la etiqueta `vertical` asignada.
    """
    etiqueta_vertical = _valor_por_contenido(asignaciones, vertical_por_id)
    salida: dict[str, str] = {}
    for c in contenidos:
        cid = c.get("id") or ""
        if not cid:
            continue
        salida[cid] = linea_de_categoria(
            (c.get("categoria") or "").strip(),
            vertical_por_id=vertical_por_id,
            etiqueta_vertical=etiqueta_vertical.get(cid, ""),
        )
    # Contenidos sin fila propia aquí pero con etiqueta vertical: respáldalos también.
    for cid, nombre in etiqueta_vertical.items():
        salida.setdefault(cid, nombre)
    return salida


def lineas_por_pieza(
    marca_consola: str | None, piezas: list[dict[str, Any]]
) -> dict[str, str]:
    """Mapa `id de pieza -> nombre de su LÍNEA editorial` (clase `vertical`), best-effort.

    Cruza cada pieza con su `contenido` de la Consola por el MISMO criterio que
    `lineas_y_origenes` (enlace fuerte por `id_post_metricool`; fallback fuzzy por
    título) y devuelve la línea de ESE contenido. Recibe las `piezas` ya leídas (de
    `servicio.construir_listado_piezas`), así que NO vuelve a golpear Metricool: solo
    lee la BD (contenidos, plataformas, etiquetas) para resolver la línea.

    Las piezas SIN línea atribuible NO aparecen en el mapa (el llamante usa "Sin
    línea"): honesto, no se inventa una línea. La clave es el `id` de la pieza.
    """
    contenidos = repos.listar_publicacion(marca=marca_consola)
    plataformas = repos.listar_piezas_fila()
    enlace_por_id, enlace_por_titulo = _indice_contenido_por_post(contenidos, plataformas)
    vertical_por_id = {
        e.get("id", ""): e.get("nombre", "")
        for e in repos.listar_etiquetas(marca=marca_consola, clase=CLASE_VERTICAL, solo_activas=True)
        if e.get("id")
    }
    # Línea de PLAN por contenido (Evergreen incluida), no solo la etiqueta vertical.
    linea_por_contenido = _lineas_por_contenido_plan(
        contenidos, repos.etiquetas_por_contenido(), vertical_por_id
    )
    salida: dict[str, str] = {}
    for p in piezas:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        cid = enlace_por_id.get(pid) or enlace_por_titulo.get(_normalizar_titulo(p.get("titulo", "")))
        nombre = (linea_por_contenido.get(cid or "") or "").strip()
        if nombre:
            salida[pid] = nombre
    return salida


def lineas_y_origenes(
    rango: str,
    marca_consola: str | None,
    marca_metricas: str | None,
    redes: tuple[str, ...] = (),
    formatos: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Rendimiento del periodo por LÍNEA (clase `vertical`) y por ORIGEN (clase `origen`).

    Orquesta las lecturas (BD via `repos` + piezas del periodo via la fachada única de
    métricas) y delega la agregación en la función PURA `agrupar_lineas_y_origenes`. Reusa
    el MISMO cruce pieza↔contenido que `analitica_por_etiqueta` (enlace por
    `id_post_metricool`; fallback fuzzy por título). No duplica la conexión a Metricool.

    `redes` acota a esas redes y `formatos` a esos formatos canónicos ANTES de agregar
    (vacío = todas/todos), igual que el resto del dashboard.

    Devuelve `{"lineas": [...], "origenes": [...], "total": <piezas del periodo>,
    "fuente": <muestra|real|…>}`. Best-effort/honesto: si nada enlaza, todas las piezas
    caen en "Sin línea"/"Sin origen".
    """
    piezas = filtrar_piezas_periodo(
        servicio.construir_listado_piezas(rango, marca_metricas), redes, formatos
    )
    fuente = servicio.nombre_fuente()

    contenidos = repos.listar_publicacion(marca=marca_consola)
    plataformas = repos.listar_piezas_fila()
    enlace_por_id, enlace_por_titulo = _indice_contenido_por_post(contenidos, plataformas)

    # Etiquetas ACTIVAS de la marca por eje (incluye globales; `listar_etiquetas` ya las
    # mezcla con marca=''). Filtra por clase en la BD para no traer de más, y SOLO activas:
    # una línea/origen retirado del plan no debe aparecer como cubo (las piezas antiguas que
    # lo tuvieran caen en "Sin línea"/"Sin origen").
    lineas_def = [
        {"id": e.get("id", ""), "nombre": e.get("nombre", "")}
        for e in repos.listar_etiquetas(marca=marca_consola, clase=CLASE_VERTICAL, solo_activas=True)
    ]
    origenes_def = [
        {"id": e.get("id", ""), "nombre": e.get("nombre", "")}
        for e in repos.listar_etiquetas(marca=marca_consola, clase=CLASE_ORIGEN, solo_activas=True)
    ]
    # `etiqueta_id -> nombre` por clase, para resolver la etiqueta de cada contenido.
    vertical_por_id = {e["id"]: e["nombre"] for e in lineas_def if e.get("id")}
    origen_por_id = {e["id"]: e["nombre"] for e in origenes_def if e.get("id")}

    asignaciones = repos.etiquetas_por_contenido()
    # La LÍNEA agrupa por la `categoria` de PLAN del contenido (incluye EVERGREEN, que no es una
    # etiqueta `vertical`); `breaking` es señal, no línea, y cae a la vertical, igual que las
    # altas manuales. El ORIGEN sí es una etiqueta de su clase.
    linea_por_contenido = _lineas_por_contenido_plan(contenidos, asignaciones, vertical_por_id)
    origen_por_contenido = _valor_por_contenido(asignaciones, origen_por_id)

    agregados = agrupar_lineas_y_origenes(
        piezas,
        linea_por_contenido=linea_por_contenido,
        origen_por_contenido=origen_por_contenido,
        enlace_por_id=enlace_por_id,
        enlace_por_titulo=enlace_por_titulo,
        lineas_definidas=lineas_def,
        origenes_definidos=origenes_def,
    )
    return {**agregados, "total": len(piezas), "fuente": fuente}

"""API PIPELINES: vista estilo GitLab CI/CD de las RUNS del pipeline de contenido.

Cada `contenido` con `origen='pipeline'` (los que produce el daemon
`pipeline_contenido`) es una RUN: el recorrido de UNA pieza por las etapas
CI (Ingesta) → CD (Copy + placa) → QA (Validación) → Aprobación, con un estado por
etapa derivado del ESTADO REAL de la pieza y sus publicaciones por plataforma (no solo
de los logs: robusto y auto-curativo). El detalle por run añade el LOG de actividad de
las etapas (las generaciones-marcador `tipo='pipeline'` correlacionadas por `contenido_id`).

Endpoints (solo lectura):
  - `GET /api/pipelines?marca=&limite=50` -> `{"pipelines": [run, ...]}`
  - `GET /api/pipelines/{pipeline_id}` -> `{"pipeline": run, "actividad": [evento, ...]}`

Errores en español como `{"error": "..."}`; sin tracebacks crudos.
"""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, redes, repos
from .._http_json import _entero_query
from ..pipeline_contenido import (
    ORIGEN_PIPELINE,
    TIPO_ACTIVIDAD,
    VERDICTO_NO_VERIFICADO,
    VERDICTO_PROBLEMA,
    qa_lexico,
)

# Tope por defecto de runs por página (alineado con el resto de la consola).
_LIMITE_DEF = 50
_LIMITE_MAX = 200

# Etapas FIJAS del pipeline (en orden de flujo). La derivación de cada estado vive en
# `_etapas_de_run`. El orden importa: `estado_global` toma la primera no-ok.
# ORDEN NUEVO (rediseño QPC): la criba de la fuente (QA) va ANTES del copy (CD).
_ETAPAS = (
    ("ci", "Ingesta"),
    ("qa", "Criba de la fuente"),
    ("cd", "Copy + placa"),
    ("aprobacion", "Aprobación"),
)

# Estados de plataforma que cuentan como "aprobado" para la etapa de Aprobación.
_ESTADOS_APROBADOS = frozenset({"aprobado", "programado", "publicado"})
# Estados de plataforma "en curso" de revisión humana (aún no aprobados).
_ESTADOS_EN_CURSO = frozenset({"en_curso", "en_revision"})


def _red_nombre(red: str) -> str:
    return "Web" if red == "web" else redes.nombre_por_id(red)


def _marca_nombre(marca: str) -> str:
    return marcas.etiqueta_de(marca) if marca else ""


def _pieza_de(plat: dict) -> dict:
    """Forma reducida de una fila por plataforma (lista + derivación de etapas)."""
    return {
        "red": plat.get("red", ""),
        "red_nombre": _red_nombre(plat.get("red", "")),
        "estado": plat.get("estado", "") or "pendiente",
        "veredicto": plat.get("veredicto", "") or "",
        "falta_copy": bool(plat.get("falta_copy", True)),
        "falta_imagen": bool(plat.get("falta_imagen", True)),
    }


def _pieza_detalle(plat: dict) -> dict:
    """Forma COMPLETA de una pieza para el detalle: lo que ocurrió de verdad en cada etapa.

    Sobre la forma reducida añade el COPY generado (texto por red + copy-in), la imagen de
    la placa, las OBSERVACIONES de la validación (recalculadas con la misma QA léxica, para
    mostrar el "por qué" del veredicto) y la traza de revisión humana (revisor + fechas).
    """
    base = _pieza_de(plat)
    copy = plat.get("copy", "") or ""
    imagen = plat.get("imagen", "") or ""
    qa = qa_lexico({"red": base["red"], "contenido": copy})
    return {
        **base,
        "copy": copy,
        "copy_in": plat.get("copy_in", "") or "",
        "imagen_url": f"/api/media/{imagen}" if imagen else "",
        "observaciones": qa["observaciones"],
        "revisor_nombre": plat.get("revisor_nombre", "") or "",
        "revisado_en": plat.get("revisado_en", "") or "",
        "enviado_a_revision_en": plat.get("enviado_a_revision_en", "") or "",
        "creado": plat.get("creado", "") or "",
    }


def _etapas_de_run(item: dict, piezas: list[dict]) -> list[dict]:
    """Deriva las 4 etapas de una run desde el ESTADO REAL del tema, su QA y sus piezas.

    Robusto/auto-curativo (no depende de los logs): se mira el estado actual del tema
    (`qa_veredicto`) y de las publicaciones por plataforma. ORDEN NUEVO (rediseño QPC): la QA
    de la FUENTE (criba pre-copy, por tema) va ANTES que el copy; un `problema` NO genera copy.
    Cada etapa es `{clave, nombre, estado, detalle, ts}`.
    """
    creado = item.get("creado", "") or ""
    actualizado = item.get("actualizado", "") or ""
    total = len(piezas)
    qa_veredicto = (item.get("qa_veredicto", "") or "").strip()
    es_problema = qa_veredicto == VERDICTO_PROBLEMA

    # --- CI · Ingesta: siempre ok (el tema fue ingerido por el daemon). ----------------
    ci = {
        "clave": "ci",
        "nombre": "Ingesta",
        "estado": "ok",
        "detalle": "Nota de origen ingerida de las fuentes.",
        "ts": creado,
    }

    # --- QA · Criba de la fuente (PRE-copy): por el veredicto persistido en el TEMA. -----
    # 'en_curso' = la criba (claude -p) está en vuelo; 'no_verificado' (⚠️) = apta, sigue;
    # 'problema' (❗) = algo de peso, NO se genera copy.
    if qa_veredicto == VERDICTO_PROBLEMA:
        qa_estado = "revisar"
        qa_detalle = "La criba encontró un problema de peso: no se generó copy (revisa los hallazgos)."
    elif qa_veredicto == "en_curso":
        qa_estado = "en_curso"
        qa_detalle = "Criba de la fuente en curso (el agente está revisando la nota de origen)."
    elif qa_veredicto == VERDICTO_NO_VERIFICADO:
        qa_estado = "ok"
        qa_detalle = "Fuente apta (no verificada a fondo): el copy llevará un aviso de no verificado."
    else:
        qa_estado = "pendiente"
        qa_detalle = "Sin cribar todavía."
    qa = {
        "clave": "qa",
        "nombre": "Criba de la fuente",
        "estado": qa_estado,
        "detalle": qa_detalle,
        "ts": "",
    }

    # --- CD · Copy + placa: ok si ≥1 pieza tiene copy. Saltada si la QA dio 'problema'. --
    con_copy = sum(1 for p in piezas if not p["falta_copy"])
    if es_problema:
        cd_estado = "pendiente"
        cd_detalle = "Copy omitido: la criba marcó un problema de peso en la fuente."
    elif con_copy:
        cd_estado = "ok"
        cd_detalle = f"Copy generado en {con_copy}/{total} red(es)."
    else:
        # "pendiente": el job de copy puede seguir en cola o aún no haberse lanzado (la QA
        # debe pasar antes). Heurística por copy presente, conservadora.
        cd_estado = "pendiente"
        cd_detalle = "Copy aún sin generar."
    cd = {
        "clave": "cd",
        "nombre": "Copy + placa",
        "estado": cd_estado,
        "detalle": cd_detalle,
        "ts": "",
    }

    # --- Aprobación: del estado de las piezas (revisión humana en la parrilla). ---------
    aprobadas = sum(1 for p in piezas if p["estado"] in _ESTADOS_APROBADOS)
    en_curso = any(p["estado"] in _ESTADOS_EN_CURSO for p in piezas)
    if total and aprobadas == total:
        ap_estado = "ok"
        ap_detalle = "Todas las piezas aprobadas."
    elif aprobadas:
        ap_estado = "en_curso"
        ap_detalle = f"{aprobadas}/{total} pieza(s) aprobada(s)."
    elif en_curso:
        ap_estado = "en_curso"
        ap_detalle = "En revisión por el equipo."
    else:
        ap_estado = "pendiente"
        ap_detalle = "Pendiente de aprobación humana."
    aprobacion = {
        "clave": "aprobacion",
        "nombre": "Aprobación",
        "estado": ap_estado,
        "detalle": ap_detalle,
        "ts": actualizado if ap_estado == "ok" else "",
    }

    return [ci, qa, cd, aprobacion]


def _estado_global(etapas: list[dict]) -> str:
    """Estado global de la run: 'fallo' si alguna etapa falló; si no, la primera no-ok."""
    for etapa in etapas:
        if etapa["estado"] == "fallo":
            return "fallo"
    for etapa in etapas:
        if etapa["estado"] != "ok":
            return etapa["estado"]
    return "ok"


def _qa_fuente_de(item: dict) -> dict:
    """Veredicto ESTRUCTURADO de la criba de la fuente (rediseño QPC), para la UI.

    Lee el veredicto persistido en el TEMA (`qa_veredicto`/`qa_hallazgos`):
      - `no_verificado` (⚠️): apta, no verificada a fondo; las piezas llevan el aviso.
      - `problema` (❗): algo de peso; NO se generó copy. `hallazgos` trae el detalle.
    `hallazgos` se parsea del JSON guardado (`{resumen, hallazgos:[...]}`); [] si vacío/ilegible.
    """
    veredicto = (item.get("qa_veredicto", "") or "").strip()
    resumen = ""
    hallazgos: list[dict] = []
    crudo = (item.get("qa_hallazgos", "") or "").strip()
    if crudo:
        try:
            datos = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            datos = None
        if isinstance(datos, dict):
            resumen = str(datos.get("resumen", "") or "")
            h = datos.get("hallazgos")
            if isinstance(h, list):
                hallazgos = [x for x in h if isinstance(x, dict)]
    return {
        "veredicto": veredicto,
        "no_verificado": veredicto == VERDICTO_NO_VERIFICADO,
        "problema": veredicto == VERDICTO_PROBLEMA,
        "copy_omitido": veredicto == VERDICTO_PROBLEMA,
        "resumen": resumen,
        "hallazgos": hallazgos,
    }


def _run_de(item: dict, piezas_plat: list[dict], *, completo: bool = False) -> dict:
    """Construye el objeto `run` de un contenido del pipeline y sus piezas por plataforma.

    `completo`: en el DETALLE, las piezas llevan la forma COMPLETA (`_pieza_detalle`: copy,
    placa, observaciones, traza de revisión) para mostrar todo lo ocurrido por etapa. En la
    LISTA basta la reducida. Las ETAPAS se derivan SIEMPRE de la forma reducida (mismos campos).
    """
    base = [_pieza_de(p) for p in piezas_plat]
    etapas = _etapas_de_run(item, base)
    marca = item.get("marca", "") or ""
    # `origen` real de la pieza padre (la fuente RSS que la ingirió): contexto de la etapa CI.
    return {
        "id": item.get("id", ""),
        "titulo": item.get("titulo", "") or "",
        "marca": marca,
        "marca_nombre": _marca_nombre(marca),
        "origen": item.get("origen", "") or "",
        "descripcion": item.get("descripcion", "") or "",
        "creado": item.get("creado", "") or "",
        "actualizado": item.get("actualizado", "") or "",
        "estado_global": _estado_global(etapas),
        "etapas": etapas,
        # Criba de la fuente (⚠️/❗ + hallazgos): la señal de QA pre-copy del tema.
        "qa_fuente": _qa_fuente_de(item),
        "piezas": [_pieza_detalle(p) for p in piezas_plat] if completo else base,
    }


def _runs_del_pipeline(marca: str | None, limite: int) -> list[dict]:
    """Contenidos `origen='pipeline'`, más recientes primero, recortados a `limite`.

    `listar_contenido` no filtra por `origen`, así que filtramos en memoria. El listado
    de contenido ya viene acotado al tablero del equipo; recortamos a `limite` tras
    reordenar por recencia (`creado` desc) para no servir un histórico enorme.
    """
    items = repos.listar_contenido(marca=marca or None)
    pipeline = [it for it in items if (it.get("origen") or "") == ORIGEN_PIPELINE]
    pipeline.sort(key=lambda it: (it.get("creado", "") or "", it.get("id", "")), reverse=True)
    return pipeline[:limite]


async def listar(request: Request) -> Response:
    """GET /api/pipelines?marca=&limite=50: runs del pipeline (recientes primero)."""
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    limite = _entero_query(qp.get("limite"), minimo=1)
    if limite is None:
        limite = _LIMITE_DEF
    limite = min(limite, _LIMITE_MAX)

    runs_items = _runs_del_pipeline(marca or None, limite)
    # Una sola lectura de TODAS las plataformas, agrupadas por contenido (evita N consultas).
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma():
        por_contenido.setdefault(plat.get("contenido_id", ""), []).append(plat)
    pipelines = [
        _run_de(it, por_contenido.get(it.get("id", ""), [])) for it in runs_items
    ]
    return JSONResponse({"pipelines": pipelines})


def _generacion_publica(gen_id: str) -> dict | None:
    """Resuelve una generación REAL (`claude -p`) por id y devuelve su STREAM + estado.

    Solo los campos que la vista necesita para pintar el proceso del agente: `salida` es el
    stream token a token (el "proceso de pensamiento"); `fase`/`estado` dicen en qué punto va
    (Razonando/Escribiendo/Completado). None si el id no resuelve (best-effort, no rompe).
    """
    if not gen_id:
        return None
    gen = generaciones.obtener(gen_id)
    if gen is None:
        return None
    return {
        "id": gen.get("id", "") or "",
        "estado": gen.get("estado", "") or "",
        "fase": gen.get("fase", "") or "",
        "salida": gen.get("salida", "") or "",
        "metricas": gen.get("metricas"),
    }


def _actividad_y_generaciones(contenido_id: str) -> tuple[list[dict], dict[str, dict]]:
    """Log de etapas (`tipo='pipeline'`) de un contenido + sus generaciones por etapa.

    Lee TODAS las generaciones-marcador del pipeline y filtra por el `contenido_id` que
    sella `pipeline_contenido.registrar_etapa` (CD/QA lo llevan; CI es brand-level y no
    queda atado a un contenido). Recientes primero. Cada evento normaliza la etiqueta
    ("CI · ..."/"CD · ..."/"QA · ...") a `{etapa, etiqueta, estado, fecha}`.

    Además devuelve `generaciones_por_etapa`: un mapa código-de-etapa (CI/CD/QA) -> la
    generación REAL de `claude -p` (resuelta por el `gen_id` del marcador) con su STREAM, para
    que el detalle muestre el proceso del agente por etapa. Solo se incluye la etapa cuyo
    marcador trae `gen_id` resoluble; si una etapa tiene varios (raro), gana el más reciente.
    """
    eventos: list[dict] = []
    # Recolectamos (etapa, fecha, gen_pub) para quedarnos con la generación más reciente por
    # etapa (los eventos vienen recientes-primero tras ordenar; iteramos sobre esa lista).
    gens_por_etapa: dict[str, dict] = {}
    for gen in generaciones.listar(limite=None):
        if gen.get("tipo") != TIPO_ACTIVIDAD:
            continue
        if (gen.get("contenido_id") or "") != contenido_id:
            continue
        etiqueta = gen.get("etiqueta", "") or ""
        etapa = etiqueta.split(" · ", 1)[0].strip() if " · " in etiqueta else ""
        fecha = gen.get("fecha_fin") or gen.get("fecha_inicio") or ""
        eventos.append(
            {
                "etapa": etapa,
                "etiqueta": etiqueta,
                "estado": gen.get("estado", "") or "",
                "fecha": fecha,
            }
        )
        gen_real = _generacion_publica(gen.get("gen_id", "") or "")
        if gen_real is not None and etapa:
            # Nos quedamos con la generación de marcador MÁS RECIENTE por etapa.
            previa = gens_por_etapa.get(etapa)
            if previa is None or fecha >= previa[0]:
                gens_por_etapa[etapa] = (fecha, gen_real)
    eventos.sort(key=lambda e: e["fecha"], reverse=True)
    generaciones_por_etapa = {etapa: par[1] for etapa, par in gens_por_etapa.items()}
    return eventos, generaciones_por_etapa


async def detalle(request: Request) -> Response:
    """GET /api/pipelines/{pipeline_id}: una run + su log de actividad por etapas."""
    pipeline_id = request.path_params["pipeline_id"]
    item = repos.obtener_contenido(pipeline_id)
    if item is None or (item.get("origen") or "") != ORIGEN_PIPELINE:
        return JSONResponse({"error": "Ese pipeline ya no existe."}, status_code=404)
    piezas = repos.listar_contenido_plataforma(pipeline_id)
    actividad, generaciones_por_etapa = _actividad_y_generaciones(pipeline_id)
    return JSONResponse(
        {
            "pipeline": _run_de(item, piezas, completo=True),
            "actividad": actividad,
            # Stream del agente (`claude -p`) por código de etapa (CI/CD/QA). Aditivo y
            # back-compat: vacío si ninguna etapa tiene una generación correlacionada.
            "generaciones_por_etapa": generaciones_por_etapa,
        }
    )


RUTAS = [
    Route("/api/pipelines", listar, methods=["GET"]),
    Route("/api/pipelines/{pipeline_id}", detalle, methods=["GET"]),
]

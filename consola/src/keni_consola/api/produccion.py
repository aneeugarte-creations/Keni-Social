"""API Producción del día: el admision de los N contenidos diarios de una marca, en un sitio.

PROBLEMA QUE RESUELVE
=====================
El objetivo editorial es un puñado de contenidos AL DÍA por marca (p.ej. 13 de UnoTV),
pero su seguimiento estaba repartido: la cola de generación en Actividad, las runs en
Pipelines, la cola de aprobación en el feed y lo programado en el calendario. Nadie veía
de un vistazo "¿cómo van los 13 de hoy?". Este endpoint junta las CUATRO vistas para la
ventana de producción (las mismas 24 h móviles del cupo de Admitir):

  GET /api/produccion/dia?marca=unotv ->
    {
      "marca", "ventana": {desde, hasta},
      "objetivo": {"dia": cupo_dia|None, "plan": plan_dia|None},
      "admision": {"total", "generando", "en_borrador", "en_revision",
                  "aprobado", "programado", "publicado"},
      "por_vertical": [{"vertical", "total", "en_revision", "programado", "publicado"}],
      "por_origen": {"pipeline": n, "historia": n, ...},
      "cola_generacion": {"pendientes", "en_curso"},
      "programacion": {"programadas": [{id, titulo, red, fecha_programada}],
                        "proximos_huecos": [{"red", "hueco"}]},
      "piezas": [{"id", "titulo", "vertical", "estado", "redes", "creado"}],
    }

El ADMISION cuenta TEMAS (contenido padre), no filas por red: el objetivo diario se mide en
contenidos, y cada tema se clasifica por su pieza MÁS AVANZADA (publicado > programado >
aprobado > en_revision > borrador con copy > generando). `objetivo.dia` es el MISMO
`KENI_CUPO_DIA` que regula Admitir: una sola fuente de verdad para "cuántos al día".

Lo consumen la UI (panel de producción) y el MCP operativo (`keni_produccion_dia`), para
que tanto el equipo como los agentes monitoricen la generación del día sin sumar a mano.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, marcas, redes, repos
from ..tiempo import ahora_iso, inicio_dia_cdmx_iso_utc

_log = logging.getLogger("keni_consola.api.produccion")

# Escalera de estados de plataforma, de menos a más avanzado: el tema se clasifica por el
# MÁXIMO que alcanza cualquiera de sus redes (una pieza publicada en X ya "cuenta" aunque
# la de Instagram siga en revisión).
_ESCALERA = ("pendiente", "en_curso", "en_revision", "aprobado", "programado", "publicado")
_RANGO = {e: i for i, e in enumerate(_ESCALERA)}

# Redes sociales candidatas para el cálculo de próximos huecos de programación.
_REDES_HUECO = ("x", "instagram", "facebook", "tiktok", "youtube")


def _estado_max(filas: list[dict[str, Any]]) -> str:
    """Estado de plataforma MÁS AVANZADO de un tema ('' si no tiene filas)."""
    mejor = -1
    for f in filas:
        mejor = max(mejor, _RANGO.get(str(f.get("estado") or ""), -1))
    return _ESCALERA[mejor] if mejor >= 0 else ""


def _peldano_admision(filas: list[dict[str, Any]]) -> str:
    """Peldaño del admision de un tema: estados editoriales o 'generando'/'en_borrador'.

    'generando' = tiene redes pero NINGUNA con copy todavía (la IA trabaja);
    'en_borrador' = hay copy pero ninguna red pasó de pendiente/en_curso (reposo del
    avance o pieza incompleta de asset).
    """
    estado = _estado_max(filas)
    if estado in ("", "pendiente", "en_curso"):
        con_copy = any(str(f.get("copy") or "").strip() for f in filas)
        return "en_borrador" if con_copy else "generando"
    return estado


def _vertical_de(etiquetas: list[str], verticales: set[str]) -> str:
    """Primera etiqueta del tema que sea una vertical de la marca ('' si ninguna)."""
    for nombre in etiquetas:
        if nombre in verticales:
            return nombre
    return ""


async def dia(request: Request) -> Response:
    """GET /api/produccion/dia?marca=: producción de la JORNADA MX (parrilla del día) de una marca."""
    marca = (request.query_params.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    ahora = datetime.fromisoformat(ahora_iso())
    # JORNADA MX (la parrilla del día), no ventana móvil de 24 h: a medianoche de México
    # el monitor vuelve a 0, igual que el contador del plan de la Mesa y Admitir.
    desde_iso = inicio_dia_cdmx_iso_utc(ahora)

    # Temas (contenido padre) CREADOS en la ventana + sus filas por red.
    items = [
        it
        for it in repos.listar_contenido(clase="contenido", marca=marca or None)
        if str(it.get("creado") or "") >= desde_iso
    ]
    filas = repos.listar_contenido_plataforma(marca=marca or None)
    filas_por_item: dict[str, list[dict[str, Any]]] = {}
    for f in filas:
        filas_por_item.setdefault(str(f.get("contenido_id") or ""), []).append(f)

    etiquetas_por_item = repos.etiquetas_por_contenido()
    verticales = {
        e.get("nombre", "")
        for e in repos.listar_etiquetas(marca=marca or None, clase="vertical")
        if e.get("nombre")
    }

    # Admisión + detalle por tema.
    admision = {
        "total": len(items),
        "generando": 0,
        "en_borrador": 0,
        "en_revision": 0,
        "aprobado": 0,
        "programado": 0,
        "publicado": 0,
    }
    por_vertical: dict[str, dict[str, int]] = {}
    por_origen: dict[str, int] = {}
    piezas: list[dict[str, Any]] = []
    for it in items:
        iid = str(it.get("id") or "")
        sus_filas = filas_por_item.get(iid, [])
        peldano = _peldano_admision(sus_filas)
        admision[peldano] = admision.get(peldano, 0) + 1
        origen = str(it.get("origen") or "") or "manual"
        por_origen[origen] = por_origen.get(origen, 0) + 1
        vertical = _vertical_de(etiquetas_por_item.get(iid, []), verticales)
        v = por_vertical.setdefault(
            vertical or "(sin vertical)",
            {"total": 0, "en_revision": 0, "programado": 0, "publicado": 0},
        )
        v["total"] += 1
        if peldano in ("en_revision", "programado", "publicado"):
            v[peldano] = v.get(peldano, 0) + 1
        piezas.append(
            {
                "id": iid,
                "titulo": it.get("titulo") or "",
                "vertical": vertical,
                "estado": peldano,
                "redes": sorted({str(f.get("red") or "") for f in sus_filas if f.get("red")}),
                "creado": it.get("creado") or "",
            }
        )
    piezas.sort(key=lambda p: p["creado"], reverse=True)

    # Objetivo: el MISMO cupo que regula Admitir (0/{} = sin cupo configurado -> None).
    objetivo = {
        "dia": config.cupo_dia(marca) or None,
        "plan": config.plan_dia(marca) or None,
    }

    # CANTIDADES POR LÍNEA del plan (monitor): GENERADOS y PUBLICADOS en la ventana vs
    # OBJETIVO, por categoría — el MISMO conteo que usa Admitir (contenido.categoria).
    # Incluye las categorías del plan aunque vayan a 0 y las generadas fuera de plan.
    por_categoria: list[dict[str, Any]] = []
    if marca:
        plan = config.plan_dia(marca)
        try:
            resumen = repos.resumen_plan_por_categoria(marca, desde_iso)
        except Exception:  # noqa: BLE001 -- el panel no falla por un contador
            _log.exception("produccion: fallo el conteo por categoría (%s).", marca)
            resumen = {}
        categorias = sorted(set(plan) | set(resumen))
        por_categoria = [
            {
                "categoria": cat,
                "generados": resumen.get(cat, {}).get("generados", 0),
                "publicados": resumen.get(cat, {}).get("publicados", 0),
                "objetivo": plan.get(cat) or None,
            }
            for cat in categorias
            if cat  # sin categoría ('') no es una línea del plan
        ]

    # Cola de generación (conteo global; el detalle vive en /api/actividad/cola).
    estados_jobs = repos.contar_jobs_por_estado()
    cola = {
        "pendientes": estados_jobs.get(repos.JOB_PENDIENTE, 0),
        "en_curso": estados_jobs.get(repos.JOB_RECLAMADO, 0),
    }

    # Cola de programación: lo programado (futuro primero) + el próximo hueco por red.
    programadas = [
        {
            "id": p["id"],
            "titulo": p.get("titulo") or "",
            "red": p.get("red") or "",
            "fecha_programada": p.get("fecha_programada") or "",
        }
        for p in repos.listar_publicaciones(marca=marca or None, estado="programado")
    ]
    programadas.sort(key=lambda p: p["fecha_programada"])
    proximos_huecos: list[dict[str, str]] = []
    if marca:
        # Import perezoso: reusa el cálculo del encolado manual (franjas de horario).
        from .publicaciones import calcular_hueco_para

        for red in _REDES_HUECO:
            if not redes.es_red(red):
                continue
            try:
                hueco = calcular_hueco_para({"id": "", "marca": marca, "red": red}, ahora)
            except Exception:  # noqa: BLE001 -- un fallo de franjas no tumba el panel
                _log.exception("produccion: fallo el cálculo de hueco (%s/%s).", marca, red)
                hueco = None
            if hueco:
                proximos_huecos.append({"red": red, "hueco": hueco})

    return JSONResponse(
        {
            "marca": marca,
            "ventana": {"desde": desde_iso, "hasta": ahora.isoformat(timespec="seconds")},
            "objetivo": objetivo,
            "por_categoria": por_categoria,
            "admision": admision,
            "por_vertical": [
                {"vertical": k, **v}
                for k, v in sorted(por_vertical.items(), key=lambda kv: -kv[1]["total"])
            ],
            "por_origen": por_origen,
            "cola_generacion": cola,
            "programacion": {
                "programadas": programadas,
                "proximos_huecos": proximos_huecos,
            },
            "piezas": piezas,
        }
    )


RUTAS = [Route("/api/produccion/dia", dia, methods=["GET"])]

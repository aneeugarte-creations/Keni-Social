"""API Rota · eventos/transmisiones: equipo + CRUD de eventos + duplicar."""
from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import marcas, repos
from ... import rota as dominio
from ..._http_json import leer_json
from ...estados import (
    PRIORIDADES_EVENTO,
    TIPOS_COBERTURA,
)
from ._comun import _equipo_dict, _evento_a_dict


async def equipo(request: Request) -> Response:
    """GET /api/rota/equipo: miembros asignables a la rota (cobertura=True).

    Cada miembro incluye `marcas` (organigrama del cliente) para que el frontend pueda filtrar
    por vertical: hoy la rota cubre solo ClaroSports y solo deben aparecer quienes la
    tengan en `marcas`. `?todos=1` devuelve el equipo COMPLETO (incluido el personal sin
    cobertura), util para casos excepcionales donde el admin quiere asignar a alguien que
    normalmente no cubre.
    """
    todos = (request.query_params.get("todos") or "").strip().lower() in {"1", "true", "yes"}
    miembros = _equipo_dict(solo_cobertura=not todos)
    return JSONResponse({"equipo": miembros})


def _error_cobertura() -> Response:
    validos = " o ".join(f'"{t}"' for t in TIPOS_COBERTURA)
    return JSONResponse({"error": f"Tipo de cobertura inválido. Usa {validos}."}, status_code=400)


def _error_prioridad() -> Response:
    validos = " o ".join(f'"{p}"' for p in PRIORIDADES_EVENTO)
    return JSONResponse({"error": f"Prioridad inválida. Usa {validos}."}, status_code=400)


async def listar_eventos(request: Request) -> Response:
    """GET /api/rota/eventos: calendario de eventos con filtros opcionales.

    Filtros (todos opcionales, combinables):
      - `desde`, `hasta`              acotan por fecha (ISO AAAA-MM-DD).
      - `cambiados=true`              deja solo los REPROGRAMADOS sin avisar.
      - `tipo_cobertura=...` (multi)  filtra por tipo (repetir param para multi-select).
      - `prioridad=...` (multi)       filtra por prioridad (repetir param para multi).
      - `cambiado=true|false`         tri-estado: presente -> filtra, ausente -> todos.
      - `q=...`                       substring case-insensitive sobre `titulo` y `contenido`.
      - `marca=...`                   id canonico de marca; ausente/vacio -> todos.

    Compatibilidad: `cambiados=true` (legado, plural) se mantiene como atajo equivalente
    a `cambiado=true`. Si ambos llegan, gana `cambiado` (más explícito).
    """
    desde = (request.query_params.get("desde") or "").strip() or None
    hasta = (request.query_params.get("hasta") or "").strip() or None
    solo_cambiados = (request.query_params.get("cambiados") or "").strip().lower() in (
        "1",
        "true",
        "sí",
        "si",
    )

    # Multi-select: `getlist` recoge `tipo_cobertura=a&tipo_cobertura=b`. Filtramos vacíos
    # y validamos contra el catálogo (UX honesta: tipo inválido -> 400, no silencio).
    tipos_cob = [t.strip() for t in request.query_params.getlist("tipo_cobertura") if t.strip()]
    if any(t not in TIPOS_COBERTURA for t in tipos_cob):
        return _error_cobertura()

    prioridades = [p.strip() for p in request.query_params.getlist("prioridad") if p.strip()]
    if any(p not in PRIORIDADES_EVENTO for p in prioridades):
        return _error_prioridad()

    # `cambiado` tri-estado: presente y parseable -> filtra; ausente -> no filtra.
    cambiado_crudo = (request.query_params.get("cambiado") or "").strip().lower()
    cambiado_filtro: bool | None = None
    if cambiado_crudo in ("1", "true", "sí", "si"):
        cambiado_filtro = True
    elif cambiado_crudo in ("0", "false", "no"):
        cambiado_filtro = False

    q = (request.query_params.get("q") or "").strip().lower()

    # Filtro de marca: id canonico valido o None (sin filtro).
    marca_filtro = (request.query_params.get("marca") or "").strip() or None
    if marca_filtro and not marcas.es_marca(marca_filtro):
        return JSONResponse({"error": "Marca no reconocida."}, status_code=400)

    # El repo solo soporta filtro mono `tipo_cobertura`; multi/prioridad/q los aplicamos
    # en Python sobre el resultado bruto (orden lineal, dataset pequeño en operación real).
    eventos = repos.listar_eventos_rota(
        desde=desde,
        hasta=hasta,
        solo_cambiados=solo_cambiados,
        tipo_cobertura=tipos_cob[0] if len(tipos_cob) == 1 else None,
        marca=marca_filtro,
    )

    if len(tipos_cob) > 1:
        eventos = [e for e in eventos if e.get("tipo_cobertura", "transmision") in tipos_cob]
    if prioridades:
        eventos = [e for e in eventos if e.get("prioridad", "media") in prioridades]
    if cambiado_filtro is not None:
        eventos = [e for e in eventos if bool(e.get("cambiado")) is cambiado_filtro]
    if q:
        eventos = [
            e
            for e in eventos
            if q in (e.get("titulo") or "").lower() or q in (e.get("contenido") or "").lower()
        ]

    return JSONResponse({"eventos": [_evento_a_dict(e) for e in eventos]})


async def crear_evento(request: Request) -> Response:
    """POST /api/rota/eventos: alta de un evento/transmision a cubrir."""
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El evento necesita un título."}, status_code=400)
    fecha = datos.get("fecha", "")
    if not isinstance(fecha, str) or not fecha.strip():
        return JSONResponse({"error": "El evento necesita una fecha."}, status_code=400)
    if dominio.lunes_de_semana_iso(fecha) == "":
        return JSONResponse(
            {"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400
        )
    tipo_cobertura = str(datos.get("tipo_cobertura", "transmision")).strip() or "transmision"
    if tipo_cobertura not in TIPOS_COBERTURA:
        return _error_cobertura()
    prioridad = str(datos.get("prioridad", "media")).strip() or "media"
    if prioridad not in PRIORIDADES_EVENTO:
        return _error_prioridad()
    marca_val = str(datos.get("marca") or "").strip()
    if marca_val and not marcas.es_marca(marca_val):
        return JSONResponse({"error": "Marca no reconocida."}, status_code=400)
    evento = repos.crear_evento_rota(
        titulo.strip(),
        fecha=fecha.strip(),
        hora=str(datos.get("hora", "")).strip(),
        contenido=str(datos.get("contenido", "")).strip(),
        nota=str(datos.get("nota", "")).strip(),
        tipo_cobertura=tipo_cobertura,
        prioridad=prioridad,
        marca=marca_val,
    )
    return JSONResponse({"evento": _evento_a_dict(evento)}, status_code=201)


async def actualizar_evento(request: Request) -> Response:
    """PATCH /api/rota/eventos/{id}: edita un evento.

    Editar `fecha`/`hora`/`tipo_cobertura` lo marca como REPROGRAMADO (`cambiado=1`); el
    request puede enviar `cambiado:false` para la acción "marcar avisado" (limpiar el aviso),
    que gana incluso si en el mismo PATCH se reprogramó.
    """
    evento_id = request.path_params["evento_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    for clave in ("titulo", "fecha", "hora", "contenido", "nota"):
        if clave in datos and isinstance(datos[clave], str):
            campos[clave] = datos[clave].strip()
    if "titulo" in campos and not campos["titulo"]:
        return JSONResponse({"error": "El evento necesita un título."}, status_code=400)
    if "fecha" in campos and campos["fecha"] and dominio.lunes_de_semana_iso(campos["fecha"]) == "":
        return JSONResponse({"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400)
    if "tipo_cobertura" in datos:
        tipo_cobertura = str(datos["tipo_cobertura"]).strip()
        if tipo_cobertura not in TIPOS_COBERTURA:
            return _error_cobertura()
        campos["tipo_cobertura"] = tipo_cobertura
    if "prioridad" in datos:
        prioridad = str(datos["prioridad"]).strip()
        if prioridad not in PRIORIDADES_EVENTO:
            return _error_prioridad()
        campos["prioridad"] = prioridad
    if "marca" in datos:
        marca_val = str(datos["marca"] or "").strip()
        if marca_val and not marcas.es_marca(marca_val):
            return JSONResponse({"error": "Marca no reconocida."}, status_code=400)
        campos["marca"] = marca_val
    # `cambiado` no es un campo editable de texto: lo derivamos en db.py, pero el request
    # puede enviarlo (típicamente `false`) como acción "ya avisé / visto" del coordinador de la rota.
    if "cambiado" in datos:
        campos["cambiado"] = bool(datos["cambiado"])
    evento = repos.actualizar_evento_rota(evento_id, campos)
    if evento is None:
        return JSONResponse({"error": "El evento ya no existe."}, status_code=404)
    return JSONResponse({"evento": _evento_a_dict(evento)})


async def borrar_evento(request: Request) -> Response:
    """DELETE /api/rota/eventos/{id}: borra el evento y los turnos que lo referencian."""
    evento_id = request.path_params["evento_id"]
    if not repos.borrar_evento_rota(evento_id):
        return JSONResponse({"error": "El evento ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Evento eliminado."})


async def duplicar_evento(request: Request) -> Response:
    """POST /api/rota/eventos/{id}/duplicar: clona un evento (sin turnos, `cambiado` reset).

    Cuerpo opcional `{fecha?, hora?, titulo?}`. NO clona los turnos (la cobertura es de la
    SEMANA, no del partido). El clon nace con `cambiado=0` (es un evento RECIÉN creado).
    """
    evento_id = request.path_params["evento_id"]
    datos = await leer_json(request) or {}
    fecha: str | None = None
    hora: str | None = None
    titulo: str | None = None
    if "fecha" in datos:
        fecha = str(datos.get("fecha", "")).strip()
        if fecha and dominio.lunes_de_semana_iso(fecha) == "":
            return JSONResponse(
                {"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400
            )
    if "hora" in datos:
        hora = str(datos.get("hora", "")).strip()
    if "titulo" in datos:
        titulo = str(datos.get("titulo", "")).strip()
        if not titulo:
            return JSONResponse(
                {"error": "El título no puede estar vacío."}, status_code=400
            )
    evento = repos.duplicar_evento_rota(evento_id, fecha=fecha, hora=hora, titulo=titulo)
    if evento is None:
        return JSONResponse({"error": "El evento ya no existe."}, status_code=404)
    return JSONResponse({"evento": _evento_a_dict(evento)}, status_code=201)

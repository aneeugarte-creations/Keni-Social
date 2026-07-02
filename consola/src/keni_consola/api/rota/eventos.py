"""API Rota · eventos/transmisiones: equipo + CRUD de eventos + duplicar."""
from __future__ import annotations

from typing import Any

from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ... import rota as dominio
from ..._http_json import leer_json
from ...dominio import recurrencia
from ...estados import (
    PRIORIDADES_EVENTO,
    TIPOS_COBERTURA,
)
from ._comun import _equipo_dict, _evento_a_dict

# Alcance de una edición/borrado sobre una serie recurrente.
_ALCANCES_SERIE = ("este", "siguientes", "serie")


async def equipo(request: Request) -> Response:
    """GET /api/rota/equipo: miembros asignables a la rota (cobertura=True).

    Cada miembro incluye `marcas` (organigrama del cliente) para que el frontend pueda filtrar
    por vertical: hoy la rota cubre solo ClaroSports y solo deben aparecer quienes la
    tengan en `marcas`. `?todos=1` devuelve el equipo COMPLETO (incluido el personal sin
    cobertura), util para casos excepcionales donde el admin quiere asignar a alguien que
    normalmente no cubre.
    """
    todos = (request.query_params.get("todos") or "").strip().lower() in {"1", "true", "yes"}
    miembros = await run_in_threadpool(_equipo_dict, solo_cobertura=not todos)
    return JSONResponse({"equipo": miembros})


def _error_cobertura() -> Response:
    validos = " o ".join(f'"{t}"' for t in TIPOS_COBERTURA)
    return JSONResponse({"error": f"Tipo de cobertura inválido. Usa {validos}."}, status_code=400)


def _error_prioridad() -> Response:
    validos = " o ".join(f'"{p}"' for p in PRIORIDADES_EVENTO)
    return JSONResponse({"error": f"Prioridad inválida. Usa {validos}."}, status_code=400)


def _listar_eventos(
    *,
    desde: str | None,
    hasta: str | None,
    solo_cambiados: bool,
    tipos_cob: list[str],
    prioridades: list[str],
    cambiado_filtro: bool | None,
    q: str,
    marca_filtro: str | None,
) -> dict[str, Any]:
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

    return {"eventos": [_evento_a_dict(e) for e in eventos]}


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

    cuerpo = await run_in_threadpool(
        _listar_eventos,
        desde=desde,
        hasta=hasta,
        solo_cambiados=solo_cambiados,
        tipos_cob=tipos_cob,
        prioridades=prioridades,
        cambiado_filtro=cambiado_filtro,
        q=q,
        marca_filtro=marca_filtro,
    )
    return JSONResponse(cuerpo)


def _crear_evento(
    titulo: str,
    fecha: str,
    comunes: dict[str, Any],
    dias: list[int],
    fechas: list[str],
    repetir_hasta: str,
) -> tuple[int, dict[str, Any]]:
    if dias:
        serie = repos.crear_serie_eventos(
            titulo,
            fechas=fechas,
            dias_semana_csv=recurrencia.dias_semana_a_csv(dias),
            repetir_hasta=repetir_hasta,
            **comunes,
        )
        return 201, {
            "eventos": [_evento_a_dict(e) for e in serie["eventos"]],
            "serie_id": serie["serie_id"],
            "total": len(serie["eventos"]),
        }
    evento = repos.crear_evento_rota(titulo, fecha=fecha, **comunes)
    return 201, {"evento": _evento_a_dict(evento)}


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

    comunes = {
        "hora": str(datos.get("hora", "")).strip(),
        "contenido": str(datos.get("contenido", "")).strip(),
        "nota": str(datos.get("nota", "")).strip(),
        "tipo_cobertura": tipo_cobertura,
        "prioridad": prioridad,
        "marca": marca_val,
    }

    # Recurrencia (opcional): `dias_semana` (0=lun..6=dom) + `repetir_hasta` (ISO, inclusive).
    # Con días válidos se MATERIALIZA una serie (un evento por ocurrencia); sin ellos, evento suelto.
    dias = recurrencia.normalizar_dias_semana(datos.get("dias_semana"))
    pidio_recurrencia = isinstance(datos.get("dias_semana"), list) and len(datos["dias_semana"]) > 0
    if pidio_recurrencia and not dias:
        return JSONResponse(
            {"error": "Días de la semana inválidos (usa 0=lunes … 6=domingo)."}, status_code=400
        )
    fechas: list[str] = []
    repetir_hasta = ""
    if dias:
        repetir_hasta = str(datos.get("repetir_hasta", "")).strip()
        if not repetir_hasta:
            return JSONResponse(
                {"error": "Indica hasta cuándo se repite el evento."}, status_code=400
            )
        if dominio.lunes_de_semana_iso(repetir_hasta) == "":
            return JSONResponse(
                {"error": "La fecha de fin no es válida (usa AAAA-MM-DD)."}, status_code=400
            )
        if repetir_hasta < fecha.strip():
            return JSONResponse(
                {"error": "La fecha de fin debe ser igual o posterior a la del evento."},
                status_code=400,
            )
        fechas = recurrencia.fechas_recurrencia(fecha.strip(), dias, repetir_hasta)

    status, cuerpo = await run_in_threadpool(
        _crear_evento, titulo.strip(), fecha.strip(), comunes, dias, fechas, repetir_hasta
    )
    return JSONResponse(cuerpo, status_code=status)


def _actualizar_evento(
    evento_id: str, campos: dict[str, Any], alcance: str
) -> tuple[int, dict[str, Any]]:
    evento = repos.actualizar_evento_rota(evento_id, campos)
    if evento is None:
        return 404, {"error": "El evento ya no existe."}

    # Alcance de serie: tras editar ESTE evento, propaga los campos (sin la fecha) al resto de la
    # serie. "siguientes" = desde su fecha en adelante; "serie" = toda. El propio evento se excluye.
    propagados = 0
    serie_id = evento.get("serie_id") or ""
    if alcance != "este" and serie_id:
        desde = evento["fecha"] if alcance == "siguientes" else None
        propagados = repos.actualizar_serie_eventos(
            serie_id, campos, desde=desde, excluir_id=evento_id
        )
    return 200, {"evento": _evento_a_dict(evento), "propagados": propagados}


async def actualizar_evento(request: Request) -> Response:
    """PATCH /api/rota/eventos/{id}: edita un evento.

    Editar `fecha`/`hora`/`tipo_cobertura` lo marca como REPROGRAMADO (`cambiado=1`); el
    request puede enviar `cambiado:false` para la acción "marcar avisado" (limpiar el aviso),
    que gana incluso si en el mismo PATCH se reprogramó.

    `?alcance=este` (def.) edita solo este evento. En una serie recurrente, `?alcance=siguientes`
    propaga los campos editados (NUNCA la fecha) a este y los posteriores de la serie, y
    `?alcance=serie` a toda ella. Un evento sin serie ignora el alcance.
    """
    evento_id = request.path_params["evento_id"]
    alcance = (request.query_params.get("alcance") or "este").strip().lower()
    if alcance not in _ALCANCES_SERIE:
        return JSONResponse(
            {"error": 'Alcance inválido. Usa "este", "siguientes" o "serie".'}, status_code=400
        )
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

    status, cuerpo = await run_in_threadpool(_actualizar_evento, evento_id, campos, alcance)
    return JSONResponse(cuerpo, status_code=status)


def _borrar_evento(evento_id: str, alcance: str) -> tuple[int, dict[str, Any]]:
    if alcance != "este":
        evento = repos.obtener_evento_rota(evento_id)
        if evento is None:
            return 404, {"error": "El evento ya no existe."}
        serie_id = evento.get("serie_id") or ""
        if serie_id:
            desde = evento["fecha"] if alcance == "siguientes" else None
            n = repos.borrar_serie_eventos(serie_id, desde=desde)
            return 200, {"mensaje": f"{n} eventos eliminados.", "eliminados": n}

    if not repos.borrar_evento_rota(evento_id):
        return 404, {"error": "El evento ya no existe."}
    return 200, {"mensaje": "Evento eliminado.", "eliminados": 1}


async def borrar_evento(request: Request) -> Response:
    """DELETE /api/rota/eventos/{id}: borra un evento.

    `?alcance=este` (por defecto) borra solo este evento. En una serie recurrente,
    `?alcance=siguientes` borra este y los posteriores de la serie, y `?alcance=serie`
    la borra entera. Un evento sin serie ignora el alcance (siempre borra solo ese).
    """
    evento_id = request.path_params["evento_id"]
    alcance = (request.query_params.get("alcance") or "este").strip().lower()
    if alcance not in _ALCANCES_SERIE:
        return JSONResponse(
            {"error": 'Alcance inválido. Usa "este", "siguientes" o "serie".'}, status_code=400
        )

    status, cuerpo = await run_in_threadpool(_borrar_evento, evento_id, alcance)
    return JSONResponse(cuerpo, status_code=status)


def _duplicar_evento(
    evento_id: str, fecha: str | None, hora: str | None, titulo: str | None
) -> tuple[int, dict[str, Any]]:
    evento = repos.duplicar_evento_rota(evento_id, fecha=fecha, hora=hora, titulo=titulo)
    if evento is None:
        return 404, {"error": "El evento ya no existe."}
    return 201, {"evento": _evento_a_dict(evento)}


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
    status, cuerpo = await run_in_threadpool(_duplicar_evento, evento_id, fecha, hora, titulo)
    return JSONResponse(cuerpo, status_code=status)


def _repetir_evento(evento_id: str, datos: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    evento = repos.obtener_evento_rota(evento_id)
    if evento is None:
        return 404, {"error": "El evento ya no existe."}
    if evento.get("serie_id"):
        return 400, {"error": "El evento ya es recurrente."}
    dias = recurrencia.normalizar_dias_semana(datos.get("dias_semana"))
    if not dias:
        return 400, {"error": "Días de la semana inválidos (usa 0=lunes … 6=domingo)."}
    repetir_hasta = str(datos.get("repetir_hasta", "")).strip()
    if not repetir_hasta:
        return 400, {"error": "Indica hasta cuándo se repite el evento."}
    if dominio.lunes_de_semana_iso(repetir_hasta) == "":
        return 400, {"error": "La fecha de fin no es válida (usa AAAA-MM-DD)."}
    if repetir_hasta < evento["fecha"]:
        return 400, {"error": "La fecha de fin debe ser igual o posterior a la del evento."}
    fechas = recurrencia.fechas_recurrencia(evento["fecha"], dias, repetir_hasta)
    serie = repos.convertir_evento_en_serie(
        evento_id,
        fechas=fechas,
        dias_semana_csv=recurrencia.dias_semana_a_csv(dias),
        repetir_hasta=repetir_hasta,
    )
    if serie is None:
        return 404, {"error": "El evento ya no existe."}
    return 201, serie


async def repetir_evento(request: Request) -> Response:
    """POST /api/rota/eventos/{id}/repetir: convierte un evento SUELTO en una serie recurrente.

    Cuerpo: `dias_semana` (0=lun..6=dom) + `repetir_hasta` (ISO inclusive). Materializa, desde la
    fecha del evento, las ocurrencias que falten (clonando sus campos). 400 si ya es recurrente.
    Devuelve `{serie_id, total, creados}`.
    """
    evento_id = request.path_params["evento_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_repetir_evento, evento_id, datos)
    return JSONResponse(cuerpo, status_code=status)

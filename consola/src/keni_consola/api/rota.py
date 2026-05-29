"""API Rota: parrilla y horarios del equipo (F4 · #144, modelo ola back3).

Sustituye el Excel manual de Elias por una vista de equipo donde EL ADMIN asigna a
mano los TURNOS (horarios de cada miembro por dia y franja) y la hace visible con
anticipacion. La consola muestra huecos, repeticiones de sabado y carga por persona;
Elias decide y APRUEBA antes de publicar al equipo. Nada se publica hasta aprobar.

MODELO (cambio post-ola2 por feedback usuario):
  - **TURNO** = horario de un miembro en (fecha, franja). NO va atado a un evento.
  - **EVENTO** = transmision/partido con fecha+hora. Existe SIN relacion con miembros.
  - **COBERTURA** = vista DERIVADA, no persistida: para un evento, sus cubridores son
    los miembros cuyo turno coincide con la franja+fecha del evento (mapear_franja).
    Puede haber turnos sin eventos y eventos sin turnos.

Eventos (CRUD + duplicar):
  - `GET    /api/rota/equipo`                 -> miembros del equipo (usuarios #130).
  - `GET    /api/rota/eventos[?desde&hasta&cambiados&tipo_cobertura]` -> eventos/transmisiones.
  - `POST   /api/rota/eventos`                {titulo, fecha, hora, contenido, nota, tipo_cobertura, prioridad}
  - `PATCH  /api/rota/eventos/{id}`           edita un evento (reprograma -> cambiado=1; cambiado:false lo limpia).
  - `DELETE /api/rota/eventos/{id}`           borra el evento.
  - `POST   /api/rota/eventos/{id}/duplicar`  clona un evento.

Turnos (CRUD completo + lote + duplicar):
  - `GET    /api/rota/turnos[?lunes]`         -> los turnos de la semana (persona×dia×franja).
  - `POST   /api/rota/turnos`                 {lunes?, fecha, miembro_id, franja, motivo?, nota_relevo?, override?}
  - `PATCH  /api/rota/turnos/{id}`            edita un turno (franja/miembro/override/motivo/nota_relevo/estado).
  - `DELETE /api/rota/turnos/{id}`            borra un turno individual.
  - `POST   /api/rota/turnos/lote`            {turnos: [{lunes?, fecha, miembro_id, franja, ...}, ...]} crea varios.
  - `PATCH  /api/rota/turnos/lote`            {ids, miembro_id, franja?, override?, motivo?} edita en lote.
  - `POST   /api/rota/turnos/lote/borrar`     {ids} borra en lote.
  - `POST   /api/rota/turnos/{id}/duplicar`   {fecha?, miembro_id?, franja?} clona con overrides.
  - `POST   /api/rota/turnos/aprobar`         {lunes} -> Elias APRUEBA (publica) los turnos.
  - `POST   /api/rota/turnos/despublicar`     {lunes} -> Elias REVIERTE la semana a borrador.
  - `GET    /api/rota/mis-turnos[?lunes]`     -> los turnos del usuario autenticado.

Cobertura DERIVADA (sin persistencia):
  - `GET    /api/rota/cobertura[?lunes]`      -> para cada evento de la semana, sus cubridores.
  - `GET    /api/rota/cobertura/evento/{id}`  -> los cubridores de un evento concreto.

Ausencias (CRUD):
  - `GET/POST/PATCH/DELETE /api/rota/ausencias[/{id}]` -> vacaciones/ausencias por miembro.

Otros (mantenidos): piezas, programas, swaps, config/franjas, carga, copiar-semana,
exports.csv/.xlsx.

ROTACION DE SABADOS (criterio de aceptacion): la edicion manual no pone a la misma
persona a TRABAJAR dos sabados seguidos salvo override explicito (`viola_rotacion_sabado_trabajo`
en `rota.py`). Aplica a PATCH y POST de turnos cuando la franja es de trabajo.

IDENTIDAD (#130): el equipo son los USUARIOS de la consola (solo lectura desde `auth`).
El usuario autenticado de la peticion (`request.state.usuario`) alimenta "mis-turnos".
La APROBACION (publicar al equipo) exige rol admin: la frontera dice que Elias aprueba.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, permisos, repos
from .. import rota as dominio
from .._http_json import leer_json
from ..estados import (
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_ACEPTADO,
    ESTADO_SWAP_CANCELADO,
    ESTADO_SWAP_PROPUESTO,
    ESTADO_SWAP_RECHAZADO,
    ESTADO_SWAP_RECHAZADO_ADMIN,
    ESTADOS_PIEZA,
    ESTADOS_ROTA,
    PRIORIDADES_EVENTO,
    TIPO_COBERTURA_NO_CUBRIR,
    TIPOS_AUSENCIA,
    TIPOS_COBERTURA,
)

# Longitud maxima del enlace de una pieza (defensa: evita strings absurdos en la BD).
_MAX_ENLACE_PIEZA = 2000

# Media types oficiales de un .xlsx (Open XML) y un CSV.
_MEDIA_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEDIA_CSV = "text/csv; charset=utf-8"

_MSG_SOLO_ADMIN = "Solo Elías (administrador) puede aprobar y publicar los turnos al equipo."


# --------------------------------------------------------------------------- #
# Helpers de identidad / equipo                                                #
# --------------------------------------------------------------------------- #


def _equipo(solo_cobertura: bool = True) -> list[dominio.Miembro]:
    """Equipo asignable a la rota: usuarios con `cobertura=True` por defecto.

    El frontend solo deberia ofrecer estos como opciones al asignar turnos. Pasar
    `solo_cobertura=False` devuelve el equipo COMPLETO (todos los usuarios), util para
    resolver nombres legibles de turnos historicos asignados antes de marcar a alguien
    como `cobertura=False` (no perder el nombre en la UI).
    """
    usuarios = auth.listar_usuarios()
    if solo_cobertura:
        usuarios = [u for u in usuarios if u.get("cobertura")]
    return [dominio.Miembro(id=u["id"], nombre=u["usuario"]) for u in usuarios]


def _equipo_dict(solo_cobertura: bool = True) -> list[dict[str, Any]]:
    """Como `_equipo`, pero con marcas N:M, `cargo` y `cobertura` para que el frontend
    pueda filtrar por vertical y por funcion en el organigrama.

    Hoy la rota solo cubre Claro Sports; con `marcas` el front puede limitar el equipo a
    los que pertenecen a esa marca (Daiana ya sale por `cobertura=False`, pero Jonathan
    cubre nacion-gamer y NO debe aparecer en la rota de ClaroSports). `cargo` permite
    ademas restringir la rejilla de Turnos a community managers (los coordinadores
    siguen en el equipo, pero no aparecen en la grilla de asignacion por franja).
    """
    usuarios = auth.listar_usuarios()
    if solo_cobertura:
        usuarios = [u for u in usuarios if u.get("cobertura")]
    return [
        {
            "id": u["id"],
            "nombre": u["usuario"],
            "marcas": list(u.get("marcas") or []),
            "cargo": u.get("cargo") or "",
            "cobertura": bool(u.get("cobertura")),
        }
        for u in usuarios
    ]


def _nombres_equipo() -> dict[str, str]:
    """Mapa id->nombre del equipo COMPLETO (todos los usuarios).

    No filtra por cobertura: un turno asignado a alguien que despues queda fuera de la
    rota sigue mostrando su nombre, no un id huerfano.
    """
    return {m.id: m.nombre for m in _equipo(solo_cobertura=False)}


def _usuario_actual(request: Request) -> dict[str, Any] | None:
    """Usuario de la sesion (None si se entro por el token de mantenimiento)."""
    usuario = getattr(request.state, "usuario", None)
    return usuario if isinstance(usuario, dict) else None


def _es_admin(request: Request) -> bool:
    """True si la peticion la hace un admin o entro por el token de bootstrap.

    Delega en el helper unico de rol (`keni_consola.permisos.es_admin`), compartido
    con `/api/conexiones` y `/api/usuarios` (#153). Mismo contrato que antes.
    """
    return permisos.es_admin(request)


def _lunes_param(request: Request) -> str:
    """Lunes (ISO) de la semana pedida (`?lunes=`); normaliza a lunes. "" si falta/invalido."""
    crudo = (request.query_params.get("lunes") or "").strip()
    return dominio.lunes_de_semana_iso(crudo) if crudo else ""


# --------------------------------------------------------------------------- #
# Serializacion                                                                #
# --------------------------------------------------------------------------- #


def _evento_a_dict(evento: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": evento["id"],
        "titulo": evento["titulo"],
        "fecha": evento["fecha"],
        "hora": evento["hora"],
        "contenido": evento["contenido"],
        "nota": evento["nota"],
        # Ola B (#144): cobertura, prioridad y seguimiento de reprogramaciones.
        "tipo_cobertura": evento.get("tipo_cobertura", "transmision"),
        "prioridad": evento.get("prioridad", "media"),
        "cambiado": bool(evento.get("cambiado")),
        "actualizado": evento.get("actualizado", ""),
        "es_sabado": dominio.es_sabado(evento["fecha"]),
    }


def _turno_a_dict(
    turno: dict[str, Any],
    nombres: dict[str, str],
    franjas_por_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Serializa un turno (horario `(fecha, franja_id)` para `miembro_id`).

    Si se pasa `franjas_por_id`, anade `franja_nombre` resuelto (para que el front no
    tenga que cruzarlo con la lista de franjas). Sin el mapa, `franja_nombre` queda "".

    Retrocompat: `franja` (literal 'matutino'/'vespertino'/'descanso') se calcula a partir
    del NOMBRE de la franja para tests legados y clientes pre-"franjas por semana". Es
    derivado: codigo nuevo debe leer `franja_id`/`franja_nombre`.
    """
    franja_def = (franjas_por_id or {}).get(turno.get("franja_id", "") or "")
    nombre = franja_def["nombre"] if franja_def else ""
    es_descanso = bool(franja_def.get("es_descanso", False)) if franja_def else False
    # Mapeo retrocompat: nombre conocido -> literal viejo.
    if es_descanso:
        franja_legacy = "descanso"
    elif nombre == "Mañana":
        franja_legacy = "matutino"
    elif nombre == "Tarde":
        franja_legacy = "vespertino"
    else:
        franja_legacy = nombre.lower() if nombre else ""
    return {
        "id": turno["id"],
        "semana": turno["semana"],
        "fecha": turno["fecha"],
        "miembro_id": turno["miembro_id"],
        # El nombre vivo del equipo manda sobre el snapshot guardado (renombres).
        "miembro_nombre": nombres.get(
            turno["miembro_id"], turno.get("miembro_nombre", "")
        ),
        "franja_id": turno.get("franja_id", "") or "",
        "franja_nombre": nombre,
        "franja": franja_legacy,  # retrocompat: derivado del nombre de la franja.
        "estado": turno["estado"],
        "override": bool(turno["override"]),
        "motivo": turno["motivo"],
        "nota_relevo": turno["nota_relevo"],
        "es_sabado": dominio.es_sabado(turno["fecha"]),
    }


def _franja_semana_a_dict(franja: dict[str, Any]) -> dict[str, Any]:
    """Serializa una `FranjaDef` al contrato HTTP."""
    return {
        "id": franja["id"],
        "lunes": franja["lunes"],
        "nombre": franja["nombre"],
        "inicio": franja["inicio"],
        "fin": franja["fin"],
        "orden": int(franja.get("orden", 0)),
        "es_descanso": bool(franja.get("es_descanso", False)),
    }


# Patron HH:MM con 00:00..24:00 (24:00 valido como FIN exclusivo de franja).
import re as _re  # noqa: E402 -- import local al modulo, evita cambiar la cabecera

_PATRON_HHMM = _re.compile(r"^([01]?\d|2[0-4]):([0-5]\d)$")


def _hhmm_valido(valor: Any) -> bool:
    """True si `valor` es 'HH:MM' (24h, con 24:00 permitido como fin exclusivo)."""
    if not isinstance(valor, str):
        return False
    m = _PATRON_HHMM.match(valor.strip())
    if not m:
        return False
    h, mm = int(m.group(1)), int(m.group(2))
    if h == 24 and mm != 0:
        return False
    return True


def _franjas_de_semana(lunes_iso: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Devuelve `(franjas_lista, franjas_por_id)` de la semana. Siembra por defecto si vacio."""
    franjas = repos.listar_franjas_semana(lunes_iso) if lunes_iso else []
    if not franjas and lunes_iso:
        franjas = repos.sembrar_franjas_por_defecto(lunes_iso)
    return franjas, {f["id"]: f for f in franjas}


# --------------------------------------------------------------------------- #
# Endpoints: equipo                                                            #
# --------------------------------------------------------------------------- #


async def equipo(request: Request) -> Response:
    """GET /api/rota/equipo: miembros asignables a la rota (cobertura=True).

    Cada miembro incluye `marcas` (organigrama AMX) para que el frontend pueda filtrar
    por vertical: hoy la rota cubre solo ClaroSports y solo deben aparecer quienes la
    tengan en `marcas`. `?todos=1` devuelve el equipo COMPLETO (incluido el personal sin
    cobertura), util para casos excepcionales donde el admin quiere asignar a alguien que
    normalmente no cubre.
    """
    todos = (request.query_params.get("todos") or "").strip().lower() in {"1", "true", "yes"}
    miembros = _equipo_dict(solo_cobertura=not todos)
    return JSONResponse({"equipo": miembros})


# --------------------------------------------------------------------------- #
# Endpoints: eventos / transmisiones                                           #
# --------------------------------------------------------------------------- #


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

    # El repo solo soporta filtro mono `tipo_cobertura`; multi/prioridad/q los aplicamos
    # en Python sobre el resultado bruto (orden lineal, dataset pequeño en operación real).
    eventos = repos.listar_eventos_rota(
        desde=desde,
        hasta=hasta,
        solo_cambiados=solo_cambiados,
        tipo_cobertura=tipos_cob[0] if len(tipos_cob) == 1 else None,
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
    evento = repos.crear_evento_rota(
        titulo.strip(),
        fecha=fecha.strip(),
        hora=str(datos.get("hora", "")).strip(),
        contenido=str(datos.get("contenido", "")).strip(),
        nota=str(datos.get("nota", "")).strip(),
        tipo_cobertura=tipo_cobertura,
        prioridad=prioridad,
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
    # `cambiado` no es un campo editable de texto: lo derivamos en db.py, pero el request
    # puede enviarlo (típicamente `false`) como acción "ya avisé / visto" de Elías.
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


# --------------------------------------------------------------------------- #
# Gestion de turnos: ausencias / vacaciones                                    #
# --------------------------------------------------------------------------- #


def _ausencia_a_dict(ausencia: dict[str, Any], nombres: dict[str, str]) -> dict[str, Any]:
    return {
        "id": ausencia["id"],
        "miembro_id": ausencia["miembro_id"],
        # El nombre vivo del equipo manda sobre el snapshot guardado (renombres).
        "miembro_nombre": nombres.get(
            ausencia["miembro_id"], ausencia.get("miembro_nombre", "")
        ),
        "tipo": ausencia["tipo"],
        "desde": ausencia["desde"],
        "hasta": ausencia["hasta"],
        "motivo": ausencia["motivo"],
    }


def _ausencias_dominio() -> list[dominio.Ausencia]:
    """Todas las ausencias como objetos de DOMINIO (para alimentar al proponedor)."""
    return [
        dominio.Ausencia(
            miembro_id=a["miembro_id"], desde=a["desde"], hasta=a["hasta"], tipo=a["tipo"]
        )
        for a in repos.listar_ausencias_rota()
    ]


def _ausencia_que_cubre(miembro_id: str, fecha_iso: str) -> dict[str, Any] | None:
    """Devuelve la 1ª ausencia REGISTRADA de `miembro_id` que cubre `fecha_iso`, o None.

    Se usa para la validacion cruzada en `actualizar_turno_trabajo` (no asignar a alguien
    que esta de vacaciones/baja sin override explicito). El cuerpo del 409 incluye este
    diccionario para que la UI muestre "tiene vacaciones del X al Y" sin tener que recargar.
    """
    if not miembro_id or not fecha_iso:
        return None
    candidatos = repos.listar_ausencias_rota(
        miembro_id=miembro_id, desde=fecha_iso, hasta=fecha_iso
    )
    return candidatos[0] if candidatos else None


def _fecha_valida(iso: str) -> bool:
    """True si `iso` es una fecha AAAA-MM-DD valida (reutiliza el parser del dominio)."""
    return bool(iso) and dominio.lunes_de_semana_iso(iso) != ""


async def listar_ausencias(request: Request) -> Response:
    """GET /api/rota/ausencias[?miembro_id]: vacaciones/ausencias registradas."""
    miembro_id = (request.query_params.get("miembro_id") or "").strip() or None
    nombres = _nombres_equipo()
    ausencias = repos.listar_ausencias_rota(miembro_id=miembro_id)
    return JSONResponse(
        {"ausencias": [_ausencia_a_dict(a, nombres) for a in ausencias]}
    )


async def crear_ausencia(request: Request) -> Response:
    """POST /api/rota/ausencias: registra una vacacion/ausencia (rango inclusivo)."""
    datos = await leer_json(request)
    nombres = _nombres_equipo()
    miembro_id = datos.get("miembro_id")
    if not isinstance(miembro_id, str) or miembro_id not in nombres:
        return JSONResponse(
            {"error": "Indica un miembro del equipo válido."}, status_code=400
        )
    desde = str(datos.get("desde", "")).strip()
    hasta = str(datos.get("hasta", "")).strip()
    if not _fecha_valida(desde) or not _fecha_valida(hasta):
        return JSONResponse(
            {"error": "Las fechas no son válidas (usa AAAA-MM-DD)."}, status_code=400
        )
    if hasta < desde:
        return JSONResponse(
            {"error": "La fecha de fin no puede ser anterior a la de inicio."},
            status_code=400,
        )
    tipo = str(datos.get("tipo", "otro")).strip() or "otro"
    if tipo not in TIPOS_AUSENCIA:
        validos = " o ".join(f'"{t}"' for t in TIPOS_AUSENCIA)
        return JSONResponse({"error": f"Tipo inválido. Usa {validos}."}, status_code=400)
    ausencia = repos.crear_ausencia_rota(
        miembro_id,
        desde,
        hasta,
        miembro_nombre=nombres.get(miembro_id, ""),
        tipo=tipo,
        motivo=str(datos.get("motivo", "")).strip(),
    )
    return JSONResponse(
        {"ausencia": _ausencia_a_dict(ausencia, nombres)}, status_code=201
    )


async def actualizar_ausencia(request: Request) -> Response:
    """PATCH /api/rota/ausencias/{id}: edita una ausencia (tipo/fechas/motivo)."""
    ausencia_id = request.path_params["ausencia_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "tipo" in datos:
        tipo = str(datos["tipo"]).strip()
        if tipo not in TIPOS_AUSENCIA:
            validos = " o ".join(f'"{t}"' for t in TIPOS_AUSENCIA)
            return JSONResponse({"error": f"Tipo inválido. Usa {validos}."}, status_code=400)
        campos["tipo"] = tipo
    for clave in ("desde", "hasta"):
        if clave in datos:
            valor = str(datos[clave]).strip()
            if not _fecha_valida(valor):
                return JSONResponse(
                    {"error": "Las fechas no son válidas (usa AAAA-MM-DD)."},
                    status_code=400,
                )
            campos[clave] = valor
    if "motivo" in datos and isinstance(datos["motivo"], str):
        campos["motivo"] = datos["motivo"].strip()
    # Coherencia del rango si se tocó alguno de los dos extremos.
    actual = repos.obtener_ausencia_rota(ausencia_id)
    if actual is None:
        return JSONResponse({"error": "La ausencia ya no existe."}, status_code=404)
    desde = campos.get("desde", actual["desde"])
    hasta = campos.get("hasta", actual["hasta"])
    if desde and hasta and hasta < desde:
        return JSONResponse(
            {"error": "La fecha de fin no puede ser anterior a la de inicio."},
            status_code=400,
        )
    ausencia = repos.actualizar_ausencia_rota(ausencia_id, campos)
    if ausencia is None:
        return JSONResponse({"error": "La ausencia ya no existe."}, status_code=404)
    return JSONResponse({"ausencia": _ausencia_a_dict(ausencia, _nombres_equipo())})


async def borrar_ausencia(request: Request) -> Response:
    """DELETE /api/rota/ausencias/{id}: borra una ausencia."""
    ausencia_id = request.path_params["ausencia_id"]
    if not repos.borrar_ausencia_rota(ausencia_id):
        return JSONResponse({"error": "La ausencia ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Ausencia eliminada."})


# --------------------------------------------------------------------------- #
# Turnos (horario persona×dia×franja): CRUD + lote + duplicar + aprobar         #
# --------------------------------------------------------------------------- #
#
# Modelo NUEVO (ola back3): un turno NO esta asociado a un evento. Es el horario que un
# miembro tiene en (fecha, franja). Pueden existir turnos sin eventos y eventos sin turnos.
# La cobertura es derivada (ver seccion "cobertura derivada"). Elias asigna a mano.


def _sabados_previos_trabajo(lunes_iso: str) -> set[str]:
    """Ids que TRABAJARON el sábado de la semana ANTERIOR a `lunes_iso`.

    Sirve para que la edicion manual del PATCH detecte la repeticion de sabado de
    trabajo consecutivo y exija un override explicito (`viola_rotacion_sabado_trabajo`).
    Tras "franjas por semana": un turno cuenta como jornada SALVO si su franja tiene
    `es_descanso=true`. Se filtran las franjas de descanso usando la lista viva de la
    semana previa.
    """
    if not lunes_iso:
        return set()
    from datetime import date, timedelta

    try:
        previo = (date.fromisoformat(lunes_iso) - timedelta(days=7)).isoformat()
    except ValueError:
        return set()
    # Indexamos las franjas de la semana previa para excluir las de descanso.
    franjas_previas = repos.listar_franjas_semana(previo)
    franjas_descanso = {
        f["id"] for f in franjas_previas if f.get("es_descanso")
    }
    ids: set[str] = set()
    for turno in repos.listar_turnos_rota(semana=previo):
        if not dominio.es_sabado(turno["fecha"]):
            continue
        if turno.get("franja_id", "") in franjas_descanso:
            continue
        ids.add(turno["miembro_id"])
    return ids


def _semana_de_turno(lunes_param: str, fecha: str) -> str:
    """Resuelve la `semana` (lunes ISO) del turno. Prefiere el `lunes_param` si es valido.

    El cliente puede pasar el `lunes` explicitamente (caso comun: viene del calendario y ya
    sabe la semana); si no, derivamos del lunes que contiene `fecha`. Devuelve "" si nada
    funciona (la API responde 400 entonces).
    """
    if lunes_param:
        normal = dominio.lunes_de_semana_iso(lunes_param)
        if normal:
            return normal
    return dominio.lunes_de_semana_iso(fecha)


def _turnos_semana(lunes_iso: str) -> dict[str, Any]:
    """Construye el payload de los turnos de una semana (incluye las franjas vivas).

    Las franjas viajan en la respuesta (`franjas`) para que el frontend renderice la
    rejilla NxDIAS sin un fetch extra. Si la semana no tiene franjas todavia, las
    siembra por defecto (Mañana, Tarde) y las devuelve.
    """
    nombres = _nombres_equipo()
    franjas_lista, franjas_por_id = _franjas_de_semana(lunes_iso)
    turnos = [
        _turno_a_dict(t, nombres, franjas_por_id)
        for t in repos.listar_turnos_rota(semana=lunes_iso)
    ]
    inicio, fin = dominio.rango_semana(lunes_iso) if lunes_iso else ("", "")
    aprobada = bool(turnos) and all(t["estado"] == "aprobado" for t in turnos)
    return {
        "lunes": lunes_iso,
        "inicio": inicio,
        "fin": fin,
        "dias": dominio.dias_de_semana(lunes_iso) if lunes_iso else [],
        "turnos": turnos,
        "franjas": [_franja_semana_a_dict(f) for f in franjas_lista],
        "aprobada": aprobada,
        "total": len(turnos),
    }


async def turnos_semana(request: Request) -> Response:
    """GET /api/rota/turnos[?lunes]: los turnos (horario) de una semana."""
    lunes = _lunes_param(request)
    return JSONResponse(_turnos_semana(lunes))


def _validar_y_resolver_turno(
    datos: dict[str, Any],
    nombres: dict[str, str],
    *,
    actual: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Response | None]:
    """Helper compartido por POST/PATCH: valida `datos` y devuelve `(campos, error?)`.

    Si `actual` es un turno existente, los campos no enviados se toman de ahi (PATCH parcial);
    si es None, exige los obligatorios (POST). En el primer error devuelve el `Response` ya
    construido. `campos` siempre incluye los keys validados (fecha, miembro_id+nombre,
    franja_id, override, motivo, nota_relevo, estado), listos para pasarse a
    `actualizar_turno_rota` o a `crear_turno_rota` segun la operacion.

    Valida ademas que `franja_id` (si viene) referencia una franja real de la semana del
    turno (cohesion: una franja `(lunes)` solo cubre turnos cuya fecha cae en esa semana).
    """
    campos: dict[str, Any] = {}

    if "fecha" in datos:
        fecha = str(datos["fecha"] or "").strip()
        if not _fecha_valida(fecha):
            return campos, JSONResponse(
                {"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400
            )
        campos["fecha"] = fecha
    elif actual is None:
        return campos, JSONResponse({"error": "Indica una fecha (AAAA-MM-DD)."}, status_code=400)

    if "miembro_id" in datos:
        miembro_id = datos["miembro_id"]
        if not isinstance(miembro_id, str):
            return campos, JSONResponse({"error": "miembro_id inválido."}, status_code=400)
        miembro_id = miembro_id.strip()
        if miembro_id and miembro_id not in nombres:
            return campos, JSONResponse(
                {"error": "Ese miembro no existe en el equipo."}, status_code=400
            )
        campos["miembro_id"] = miembro_id
        campos["miembro_nombre"] = nombres.get(miembro_id, "")
    elif actual is None:
        return campos, JSONResponse(
            {"error": "Indica el miembro del equipo (`miembro_id`)."}, status_code=400
        )

    # Validacion de `franja_id`: debe existir y pertenecer a la semana de la fecha del
    # turno. La fecha final puede venir de `datos` o de `actual` (PATCH parcial).
    #
    # RETROCOMPAT: tests legados envian `franja: "matutino"|"vespertino"|"descanso"`. Lo
    # aceptamos traduciendo al `franja_id` de la franja por defecto de la semana (Mañana,
    # Tarde, Descanso). Esto permite que tests pre-"franjas por semana" sigan ejerciendo
    # las reglas de POST/PATCH; codigo nuevo debe pasar `franja_id` directo.
    legacy_franja: str | None = None
    if "franja" in datos and "franja_id" not in datos:
        bruto = datos.get("franja")
        if not isinstance(bruto, str) or bruto.strip().lower() not in (
            "matutino",
            "vespertino",
            "descanso",
        ):
            return campos, JSONResponse(
                {
                    "error": (
                        "Franja inválida. Usa \"matutino\" o \"vespertino\" o \"descanso\" "
                        "(o pasa `franja_id`)."
                    )
                },
                status_code=400,
            )
        legacy_franja = bruto.strip().lower()
        fecha_final = campos.get("fecha", (actual or {}).get("fecha", ""))
        semana_legacy = dominio.lunes_de_semana_iso(fecha_final) if fecha_final else ""
        if semana_legacy:
            defaults = repos.sembrar_franjas_por_defecto(semana_legacy)
            nombre_buscado = ""
            if legacy_franja == "matutino":
                nombre_buscado = "Mañana"
            elif legacy_franja == "vespertino":
                nombre_buscado = "Tarde"
            elif legacy_franja == "descanso":
                # Buscamos por el flag `es_descanso=true` para no depender del literal.
                desc = next((f for f in defaults if f.get("es_descanso")), None)
                nombre_buscado = desc["nombre"] if desc else ""
            match = next((f for f in defaults if f["nombre"] == nombre_buscado), None)
            if match is not None:
                campos["franja_id"] = match["id"]
    if "franja_id" in datos:
        franja_id = datos["franja_id"]
        if not isinstance(franja_id, str) or not franja_id.strip():
            return campos, JSONResponse(
                {"error": "Indica la franja del turno (`franja_id`)."}, status_code=400
            )
        franja_id = franja_id.strip()
        franja_def = repos.obtener_franja_semana(franja_id)
        if franja_def is None:
            return campos, JSONResponse(
                {"error": "La franja indicada no existe."}, status_code=400
            )
        fecha_final = campos.get("fecha", (actual or {}).get("fecha", ""))
        lunes_fecha = dominio.lunes_de_semana_iso(fecha_final) if fecha_final else ""
        if lunes_fecha and franja_def["lunes"] != lunes_fecha:
            return campos, JSONResponse(
                {
                    "error": (
                        "La franja pertenece a otra semana. Crea/usa una franja de la "
                        "semana del turno."
                    )
                },
                status_code=400,
            )
        campos["franja_id"] = franja_id
    elif legacy_franja is not None and "franja_id" in campos:
        # ya resuelto via legacy; nada que hacer.
        pass
    elif actual is None:
        return campos, JSONResponse(
            {"error": "Indica la franja del turno (`franja_id` o `franja`)."},
            status_code=400,
        )

    if "override" in datos:
        campos["override"] = bool(datos["override"])
    if "motivo" in datos and isinstance(datos["motivo"], str):
        campos["motivo"] = datos["motivo"].strip()
    if "nota_relevo" in datos and isinstance(datos["nota_relevo"], str):
        campos["nota_relevo"] = datos["nota_relevo"].strip()
    if "estado" in datos:
        estado = datos["estado"]
        if estado not in ESTADOS_ROTA:
            validos = " o ".join(f'"{e}"' for e in ESTADOS_ROTA)
            return campos, JSONResponse(
                {"error": f"Estado inválido. Usa {validos}."}, status_code=400
            )
        campos["estado"] = estado

    return campos, None


def _violacion_sabado(
    fecha: str,
    semana: str,
    miembro_id: str,
    *,
    override: bool,
    franja_id: str = "",
) -> Response | None:
    """Si la fecha cae en sabado y repite al miembro del sabado previo sin override,
    devuelve la respuesta 409 ya construida. Si no aplica, devuelve None.

    Tras "franjas por semana": un turno cuenta como jornada laboral SALVO si su franja
    tiene `es_descanso=true`. Asignar a alguien la franja Descanso del sabado no rompe la
    rotacion (no esta trabajando ese dia).
    """
    if not dominio.es_sabado(fecha):
        return None
    if franja_id:
        franja_def = repos.obtener_franja_semana(franja_id)
        if franja_def and franja_def.get("es_descanso"):
            return None
    previos = _sabados_previos_trabajo(semana)
    if dominio.viola_rotacion_sabado_trabajo(previos, miembro_id, override=override):
        return JSONResponse(
            {
                "error": (
                    "Esa persona ya trabajó el sábado anterior. Marca un override "
                    "explícito si es una cobertura estratégica intencional."
                ),
                "requiere_override": True,
            },
            status_code=409,
        )
    return None


def _violacion_ausencia(
    miembro_id: str, fecha: str, *, override: bool, franja_id: str = ""
) -> Response | None:
    """Si `miembro_id` esta de ausencia ese dia sin override, devuelve 409 (con dict de
    la ausencia). Si no aplica, None.

    Una franja con `es_descanso=true` ES legal aunque la persona este ausente: el descanso
    no es jornada laboral, asi que no choca con una vacacion/baja.
    """
    if not miembro_id or override:
        return None
    if franja_id:
        franja_def = repos.obtener_franja_semana(franja_id)
        if franja_def and franja_def.get("es_descanso"):
            return None
    ausencia = _ausencia_que_cubre(miembro_id, fecha)
    if ausencia is None:
        return None
    return JSONResponse(
        {
            "error": (
                f"Esa persona tiene «{ausencia['tipo']}» del "
                f"{ausencia['desde']} al {ausencia['hasta']}. Marca un override "
                "explícito si es una cobertura excepcional."
            ),
            "requiere_override": True,
            "ausencia": ausencia,
        },
        status_code=409,
    )


async def crear_turno(request: Request) -> Response:
    """POST /api/rota/turnos: crea un turno (horario `(fecha, franja_id)` para un miembro).

    Cuerpo: `{lunes?, fecha, miembro_id, franja_id, motivo?, nota_relevo?, override?, estado?}`.
    La `semana` se deriva del `lunes` enviado, o del lunes que contiene `fecha`. La
    `franja_id` debe pertenecer a la misma semana. Devuelve 409 si ya existe un turno para
    `(miembro_id, fecha, franja_id)` (el cliente debe editar el existente, no duplicar).
    Tambien aplica la regla de sabado y la cruzada de ausencias.
    """
    datos = await leer_json(request)
    nombres = _nombres_equipo()
    campos, err = _validar_y_resolver_turno(datos, nombres, actual=None)
    if err is not None:
        return err

    fecha = campos["fecha"]
    miembro_id = campos["miembro_id"]
    franja_id = campos["franja_id"]
    override = bool(campos.get("override", False))
    lunes_param = str(datos.get("lunes", "")).strip()
    semana = _semana_de_turno(lunes_param, fecha)
    if not semana:
        return JSONResponse(
            {"error": "No se puede derivar la semana de la fecha."}, status_code=400
        )

    _franjas_lista, franjas_por_id = _franjas_de_semana(semana)

    # Unicidad: si ya existe un turno para (miembro, fecha, franja_id) -> 409 con el id.
    if miembro_id:
        existente = repos.existe_turno_para(miembro_id, fecha, franja_id)
        if existente is not None:
            return JSONResponse(
                {
                    "error": (
                        "Ya hay un turno para ese miembro en esa fecha y franja. Edita el "
                        "existente o duplicalo."
                    ),
                    "turno_existente": _turno_a_dict(existente, nombres, franjas_por_id),
                },
                status_code=409,
            )

    err = _violacion_sabado(fecha, semana, miembro_id, override=override, franja_id=franja_id)
    if err is not None:
        return err
    err = _violacion_ausencia(miembro_id, fecha, override=override, franja_id=franja_id)
    if err is not None:
        return err

    turno = repos.crear_turno_rota(
        semana,
        fecha,
        miembro_id=miembro_id,
        miembro_nombre=nombres.get(miembro_id, ""),
        franja_id=franja_id,
        estado=campos.get("estado", ESTADO_ROTA_PROPUESTO),
        override=override,
        motivo=campos.get("motivo", ""),
        nota_relevo=campos.get("nota_relevo", ""),
    )
    return JSONResponse({"turno": _turno_a_dict(turno, nombres, franjas_por_id)}, status_code=201)


async def actualizar_turno(request: Request) -> Response:
    """PATCH /api/rota/turnos/{id}: edita un turno (franja_id/miembro/override/motivo/...).

    Si la edicion pone a TRABAJAR el sabado a quien trabajó el sabado previo SIN override,
    devuelve 409. Si la persona esta de ausencia sin override, 409.
    """
    turno_id = request.path_params["turno_id"]
    actual = repos.obtener_turno_rota(turno_id)
    if actual is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)

    datos = await leer_json(request)
    nombres = _nombres_equipo()
    campos, err = _validar_y_resolver_turno(datos, nombres, actual=actual)
    if err is not None:
        return err

    # Resuelve los valores finales (PATCH parcial: defaults desde `actual`).
    fecha = campos.get("fecha", actual["fecha"])
    miembro_id = campos.get("miembro_id", actual["miembro_id"])
    franja_id_final = campos.get("franja_id", actual.get("franja_id", ""))
    override = bool(campos.get("override", actual["override"]))

    err = _violacion_sabado(
        fecha, actual["semana"], miembro_id, override=override, franja_id=franja_id_final
    )
    if err is not None:
        return err
    err = _violacion_ausencia(
        miembro_id, fecha, override=override, franja_id=franja_id_final
    )
    if err is not None:
        return err

    turno = repos.actualizar_turno_rota(turno_id, campos)
    if turno is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    _franjas_lista, franjas_por_id = _franjas_de_semana(actual["semana"])
    return JSONResponse({"turno": _turno_a_dict(turno, nombres, franjas_por_id)})


async def borrar_turno(request: Request) -> Response:
    """DELETE /api/rota/turnos/{id}: borra un turno individual."""
    turno_id = request.path_params["turno_id"]
    if not repos.borrar_turno_rota(turno_id):
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Turno eliminado."})


async def borrar_turnos_lote(request: Request) -> Response:
    """POST /api/rota/turnos/lote/borrar {ids}: borra varios turnos a la vez.

    Devuelve `{borrados: N, no_encontrados: [ids]}`. Tolerante con ids inexistentes.
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) and x for x in ids) or not ids:
        return JSONResponse(
            {"error": "Indica al menos un turno (`ids`)."}, status_code=400
        )
    existentes = {t["id"] for t in repos.listar_turnos_rota() if t["id"] in ids}
    no_encontrados = [i for i in ids if i not in existentes]
    n = repos.borrar_turnos_rota_lote(list(existentes))
    return JSONResponse({"borrados": n, "no_encontrados": no_encontrados})


async def crear_turnos_lote(request: Request) -> Response:
    """POST /api/rota/turnos/lote {turnos: [...]}: crea varios turnos en una sola peticion.

    Cuerpo: `{turnos: [{lunes?, fecha, miembro_id, franja_id, motivo?, nota_relevo?, override?, estado?}, ...]}`.
    Si ALGUNA entrada falla la validacion (fecha invalida, miembro no existe, franja
    invalida) o ya existe un turno para `(miembro, fecha, franja_id)`, devuelve 409 con el
    indice y el motivo SIN tocar BD. Caso comun: "Mañana lun-vie para Luis".
    """
    datos = await leer_json(request)
    entradas = datos.get("turnos")
    if not isinstance(entradas, list) or not entradas:
        return JSONResponse(
            {"error": "Indica al menos un turno (`turnos`)."}, status_code=400
        )
    nombres = _nombres_equipo()
    preparados: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = []

    # Pre-indice de turnos ya existentes en BD para detectar choques sin recargar uno a uno.
    turnos_existentes_por_clave: set[tuple[str, str, str]] = {
        (t["miembro_id"], t["fecha"], t["franja_id"]) for t in repos.listar_turnos_rota()
    }
    # Tambien evita duplicados DENTRO del propio lote.
    claves_pendientes: set[tuple[str, str, str]] = set()
    # Cache de franjas por semana para serializar la respuesta final.
    franjas_cache: dict[str, dict[str, dict[str, Any]]] = {}

    for i, entrada in enumerate(entradas):
        if not isinstance(entrada, dict):
            errores.append({"indice": i, "error": "Entrada inválida."})
            continue
        campos, err = _validar_y_resolver_turno(entrada, nombres, actual=None)
        if err is not None:
            cuerpo = err.body.decode("utf-8") if isinstance(err.body, bytes) else str(err.body)
            errores.append({"indice": i, "error": cuerpo})
            continue
        fecha = campos["fecha"]
        miembro_id = campos["miembro_id"]
        franja_id = campos["franja_id"]
        override = bool(campos.get("override", False))
        lunes_param = str(entrada.get("lunes", "")).strip()
        semana = _semana_de_turno(lunes_param, fecha)
        if not semana:
            errores.append({"indice": i, "error": "No se puede derivar la semana de la fecha."})
            continue
        if semana not in franjas_cache:
            _lista, por_id = _franjas_de_semana(semana)
            franjas_cache[semana] = por_id
        clave = (miembro_id, fecha, franja_id)
        if miembro_id and clave in (turnos_existentes_por_clave | claves_pendientes):
            errores.append(
                {
                    "indice": i,
                    "error": "Ya hay un turno para ese miembro en esa fecha y franja.",
                    "clave": {"miembro_id": miembro_id, "fecha": fecha, "franja_id": franja_id},
                }
            )
            continue
        # Sabado: regla de rotacion.
        sab = _violacion_sabado(
            fecha, semana, miembro_id, override=override, franja_id=franja_id
        )
        if sab is not None:
            errores.append(
                {
                    "indice": i,
                    "error": "Esa persona ya trabajó el sábado anterior; usa override.",
                    "requiere_override": True,
                }
            )
            continue
        # Ausencia: regla cruzada.
        aus = _violacion_ausencia(miembro_id, fecha, override=override, franja_id=franja_id)
        if aus is not None:
            errores.append(
                {
                    "indice": i,
                    "error": "La persona tiene una ausencia ese día; usa override.",
                    "requiere_override": True,
                }
            )
            continue
        claves_pendientes.add(clave)
        preparados.append(
            {
                "semana": semana,
                "fecha": fecha,
                "miembro_id": miembro_id,
                "miembro_nombre": nombres.get(miembro_id, ""),
                "franja_id": franja_id,
                "estado": campos.get("estado", ESTADO_ROTA_PROPUESTO),
                "override": override,
                "motivo": campos.get("motivo", ""),
                "nota_relevo": campos.get("nota_relevo", ""),
            }
        )

    if errores:
        return JSONResponse(
            {
                "error": "Hay entradas que no se pueden crear.",
                "errores": errores,
                "creados": 0,
            },
            status_code=409,
        )

    creados = repos.crear_turnos_rota_lote(preparados)
    # Componer el mapa global de franjas (uniendo todas las semanas tocadas) para
    # serializar `franja_nombre` en cada turno devuelto.
    franjas_global: dict[str, dict[str, Any]] = {}
    for por_id in franjas_cache.values():
        franjas_global.update(por_id)
    return JSONResponse(
        {
            "creados": len(creados),
            "turnos": [_turno_a_dict(t, nombres, franjas_global) for t in creados],
        },
        status_code=201,
    )


async def actualizar_turnos_lote(request: Request) -> Response:
    """PATCH /api/rota/turnos/lote: edita en lote varios turnos.

    Cuerpo: `{ids: [...], miembro_id?, franja_id?, override?: bool, motivo?: str, nota_relevo?: str}`.
    Si algun turno requiere override (sabado consecutivo con el mismo miembro) y no se
    mando `override:true`, devuelve 409 con la lista de ids problematicos sin tocar BD.
    `miembro_id=""` vacia la asignacion (alineado con el PATCH 1:1).
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) and x for x in ids) or not ids:
        return JSONResponse(
            {"error": "Indica al menos un turno (`ids`)."}, status_code=400
        )
    nombres = _nombres_equipo()
    override = bool(datos.get("override", False))

    # Construye los campos a aplicar. `miembro_id` requiere validacion contra el equipo;
    # `franja_id` requiere que la franja exista en BD. Los demas se pasan tal cual.
    campos: dict[str, Any] = {}
    miembro_id_final: str | None = None
    if "miembro_id" in datos:
        miembro_id = datos["miembro_id"]
        if not isinstance(miembro_id, str) or (miembro_id and miembro_id not in nombres):
            return JSONResponse(
                {"error": "Indica un miembro del equipo válido."}, status_code=400
            )
        campos["miembro_id"] = miembro_id
        campos["miembro_nombre"] = nombres.get(miembro_id, "")
        miembro_id_final = miembro_id
    if "franja_id" in datos:
        franja_id = datos["franja_id"]
        if not isinstance(franja_id, str) or not franja_id.strip():
            return JSONResponse(
                {"error": "Indica la franja (`franja_id`)."}, status_code=400
            )
        franja_id = franja_id.strip()
        if repos.obtener_franja_semana(franja_id) is None:
            return JSONResponse(
                {"error": "La franja indicada no existe."}, status_code=400
            )
        campos["franja_id"] = franja_id
    if "override" in datos:
        campos["override"] = override
    if "motivo" in datos and isinstance(datos["motivo"], str):
        campos["motivo"] = datos["motivo"].strip()
    if "nota_relevo" in datos and isinstance(datos["nota_relevo"], str):
        campos["nota_relevo"] = datos["nota_relevo"].strip()
    if not campos:
        return JSONResponse(
            {"error": "Indica al menos un campo a editar."}, status_code=400
        )

    # Carga los turnos pedidos y verifica que todos existan.
    turnos_objetivo: list[dict[str, Any]] = []
    for tid in ids:
        t = repos.obtener_turno_rota(tid)
        if t is None:
            return JSONResponse(
                {"error": f"El turno {tid} ya no existe."}, status_code=404
            )
        turnos_objetivo.append(t)

    # Atomico frente a la regla de rotacion: si miembro_id viene en el cambio, comprueba
    # sabados por semana. Una franja `es_descanso=true` queda fuera (no es jornada).
    if miembro_id_final and not override:
        sabados_previos_por_semana: dict[str, set[str]] = {}
        ids_que_requieren_override: list[str] = []
        for t in turnos_objetivo:
            if not dominio.es_sabado(t["fecha"]):
                continue
            # Excluye los turnos cuya franja es de descanso (no cuenta como jornada).
            franja_efectiva = campos.get("franja_id", t.get("franja_id", ""))
            if franja_efectiva:
                franja_def = repos.obtener_franja_semana(franja_efectiva)
                if franja_def and franja_def.get("es_descanso"):
                    continue
            semana = t["semana"]
            if semana not in sabados_previos_por_semana:
                sabados_previos_por_semana[semana] = _sabados_previos_trabajo(semana)
            if dominio.viola_rotacion_sabado_trabajo(
                sabados_previos_por_semana[semana],
                miembro_id_final,
                override=False,
            ):
                ids_que_requieren_override.append(t["id"])
        if ids_que_requieren_override:
            return JSONResponse(
                {
                    "error": (
                        "Hay turnos de sábado que repetirían la persona del sábado anterior; "
                        "marca override si es una cobertura estratégica intencional."
                    ),
                    "requiere_override": True,
                    "ids_que_requieren_override": ids_que_requieren_override,
                },
                status_code=409,
            )

    n, turnos = repos.actualizar_turnos_rota_lote(ids, campos)
    # Componer franjas de las semanas afectadas para serializar `franja_nombre`.
    semanas_tocadas = {t["semana"] for t in turnos}
    franjas_global: dict[str, dict[str, Any]] = {}
    for semana in semanas_tocadas:
        _lista, por_id = _franjas_de_semana(semana)
        franjas_global.update(por_id)
    return JSONResponse(
        {
            "actualizados": n,
            "turnos": [_turno_a_dict(t, nombres, franjas_global) for t in turnos],
        }
    )


async def duplicar_turno(request: Request) -> Response:
    """POST /api/rota/turnos/{id}/duplicar: clona un turno con overrides opcionales.

    Cuerpo opcional `{fecha?, miembro_id?, franja_id?}`. Caso comun: copiar el turno del
    lunes al martes con el mismo miembro y franja. Aplica las mismas reglas que la creacion
    (sabado, ausencia, choque `(miembro, fecha, franja_id)`).

    Si la `fecha` cambia a otra semana, el `franja_id` del original NO es valido en la
    semana destino (las franjas son por semana). En ese caso devolvemos 400: el cliente
    debe pasar un `franja_id` de la semana destino, o crear la franja antes.
    """
    turno_id = request.path_params["turno_id"]
    original = repos.obtener_turno_rota(turno_id)
    if original is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    datos = await leer_json(request) or {}
    nombres = _nombres_equipo()

    fecha = original["fecha"]
    if "fecha" in datos:
        f = str(datos.get("fecha", "")).strip()
        if not _fecha_valida(f):
            return JSONResponse(
                {"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400
            )
        fecha = f
    miembro_id = original["miembro_id"]
    if "miembro_id" in datos:
        m = datos["miembro_id"]
        if not isinstance(m, str) or (m and m not in nombres):
            return JSONResponse(
                {"error": "Indica un miembro del equipo válido."}, status_code=400
            )
        miembro_id = m
    franja_id = original["franja_id"]
    if "franja_id" in datos:
        f = datos["franja_id"]
        if not isinstance(f, str) or not f.strip():
            return JSONResponse(
                {"error": "Indica la franja del turno (`franja_id`)."}, status_code=400
            )
        franja_id = f.strip()
        if repos.obtener_franja_semana(franja_id) is None:
            return JSONResponse(
                {"error": "La franja indicada no existe."}, status_code=400
            )

    semana = dominio.lunes_de_semana_iso(fecha)
    if not semana:
        return JSONResponse(
            {"error": "No se puede derivar la semana de la fecha."}, status_code=400
        )

    # La franja del clon debe pertenecer a la semana destino.
    franja_def = repos.obtener_franja_semana(franja_id)
    if franja_def is None or franja_def["lunes"] != semana:
        return JSONResponse(
            {
                "error": (
                    "La franja del turno original es de otra semana. Pasa un `franja_id` "
                    "que exista en la semana destino."
                )
            },
            status_code=400,
        )

    _lista, franjas_por_id = _franjas_de_semana(semana)

    # Choque (miembro, fecha, franja_id) -> 409.
    if miembro_id:
        existente = repos.existe_turno_para(miembro_id, fecha, franja_id)
        if existente is not None:
            return JSONResponse(
                {
                    "error": (
                        "Ya hay un turno para ese miembro en esa fecha y franja. Edita el "
                        "existente o cambia uno de los tres campos."
                    ),
                    "turno_existente": _turno_a_dict(existente, nombres, franjas_por_id),
                },
                status_code=409,
            )
    override = bool(original.get("override", False))
    err = _violacion_sabado(
        fecha, semana, miembro_id, override=override, franja_id=franja_id
    )
    if err is not None:
        return err
    err = _violacion_ausencia(miembro_id, fecha, override=override, franja_id=franja_id)
    if err is not None:
        return err

    clon = repos.duplicar_turno_rota(
        turno_id,
        fecha=fecha,
        miembro_id=miembro_id,
        miembro_nombre=nombres.get(miembro_id, ""),
        franja_id=franja_id,
        semana=semana,
    )
    if clon is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    return JSONResponse(
        {"turno": _turno_a_dict(clon, nombres, franjas_por_id)}, status_code=201
    )


async def aprobar_turnos(request: Request) -> Response:
    """POST /api/rota/turnos/aprobar {lunes}: Elias APRUEBA (publica) los turnos al equipo.

    Solo admin: la frontera dice que Elias aprueba los turnos finales antes de publicarlos
    al equipo. Marca todos los turnos de la semana como `aprobado`.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN}, status_code=403)
    datos = await leer_json(request)
    lunes = dominio.lunes_de_semana_iso(str(datos.get("lunes", "")).strip())
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana a aprobar (AAAA-MM-DD)."},
            status_code=400,
        )
    n = repos.aprobar_semana_rota(lunes)
    if n == 0:
        return JSONResponse(
            {"error": "No hay turnos en esa semana para aprobar. Asigna los turnos primero."},
            status_code=400,
        )
    payload = _turnos_semana(lunes)
    payload["mensaje"] = f"Turnos aprobados y publicados al equipo ({n} turnos)."
    return JSONResponse(payload)


async def despublicar_turnos(request: Request) -> Response:
    """POST /api/rota/turnos/despublicar {lunes}: revierte la semana publicada a borrador.

    Solo admin (mismo guard que aprobar). Inverso de `aprobar_turnos`: marca todos los
    turnos de la semana como `propuesto` para volver a editarlos. Util cuando se publico
    una semana con error o cambian las cosas tras publicar.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN}, status_code=403)
    datos = await leer_json(request)
    lunes = dominio.lunes_de_semana_iso(str(datos.get("lunes", "")).strip())
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana a despublicar (AAAA-MM-DD)."},
            status_code=400,
        )
    n = repos.desaprobar_semana_rota(lunes)
    if n == 0:
        return JSONResponse(
            {"error": "No hay turnos en esa semana para despublicar."},
            status_code=400,
        )
    payload = _turnos_semana(lunes)
    payload["mensaje"] = f"Semana despublicada: vuelve a borrador ({n} turnos editables)."
    return JSONResponse(payload)


async def mis_turnos(request: Request) -> Response:
    """GET /api/rota/mis-turnos[?lunes]: los turnos del USUARIO actual en esa semana."""
    lunes = _lunes_param(request)
    usuario = _usuario_actual(request)
    base = _turnos_semana(lunes)
    if usuario is None:
        return JSONResponse(
            {
                **base,
                "miembro_id": "",
                "miembro_nombre": "",
                "mis_turnos": [],
                "aviso": "Inicia sesión para ver tus próximos turnos.",
            }
        )
    mios = [t for t in base["turnos"] if t["miembro_id"] == usuario["id"]]
    return JSONResponse(
        {
            **base,
            "miembro_id": usuario["id"],
            "miembro_nombre": usuario["usuario"],
            "mis_turnos": mios,
        }
    )


# --------------------------------------------------------------------------- #
# Cobertura DERIVADA: para un evento, quien lo cubre via turnos en su franja+fecha #
# --------------------------------------------------------------------------- #
#
# NO persistida. Cada llamada cruza eventos x turnos x franjas vigentes. Si hay turnos sin
# evento o eventos sin turno, la vista lo refleja sin error.


def _cobertura_para_evento(
    evento: dict[str, Any],
    turnos: list[dict[str, Any]],
    nombres: dict[str, str],
    franjas_semana: list[dict[str, Any]],
    franjas_por_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calcula la cobertura derivada de UN evento usando `dominio.cobertura_de_evento`."""
    cubridores = dominio.cobertura_de_evento(evento, turnos, franjas_semana)
    franjas_por_id = franjas_por_id or {f["id"]: f for f in franjas_semana}
    return {
        **_evento_a_dict(evento),
        "cobertura": [
            {
                "turno_id": t["id"],
                "miembro_id": t["miembro_id"],
                "miembro_nombre": nombres.get(
                    t["miembro_id"], t.get("miembro_nombre", "")
                ),
                "franja_id": t.get("franja_id", "") or "",
                "franja_nombre": (
                    franjas_por_id.get(t.get("franja_id", "") or "", {}).get("nombre", "")
                ),
                "override": bool(t.get("override", False)),
            }
            for t in cubridores
        ],
    }


async def cobertura_semana(request: Request) -> Response:
    """GET /api/rota/cobertura[?lunes]: cobertura derivada de los eventos de la semana.

    Devuelve `{lunes, eventos: [{...evento, cobertura: [{miembro_id, miembro_nombre,
    franja_id, franja_nombre, turno_id, override}, ...]}], franjas}`. NO persiste nada;
    cruza turnos x eventos x franjas vivas de la semana. Sin `lunes` valido -> 400.
    """
    lunes = _lunes_param(request)
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana (AAAA-MM-DD)."}, status_code=400
        )
    inicio, fin = dominio.rango_semana(lunes)
    eventos = repos.listar_eventos_rota(desde=inicio, hasta=fin)
    # Filtra los `no_cubrir` por defecto (no se cubren por convencion editorial).
    eventos = [e for e in eventos if (e.get("tipo_cobertura") or "transmision") != TIPO_COBERTURA_NO_CUBRIR]
    turnos = repos.listar_turnos_rota(semana=lunes)
    nombres = _nombres_equipo()
    franjas_cfg = repos.obtener_franjas_config()
    franjas_lista, franjas_por_id = _franjas_de_semana(lunes)
    return JSONResponse(
        {
            "lunes": lunes,
            "inicio": inicio,
            "fin": fin,
            "franjas_config": franjas_cfg,
            "franjas": [_franja_semana_a_dict(f) for f in franjas_lista],
            "eventos": [
                _cobertura_para_evento(e, turnos, nombres, franjas_lista, franjas_por_id)
                for e in eventos
            ],
        }
    )


async def cobertura_evento(request: Request) -> Response:
    """GET /api/rota/cobertura/evento/{evento_id}: cobertura derivada de UN evento."""
    evento_id = request.path_params["evento_id"]
    evento = repos.obtener_evento_rota(evento_id)
    if evento is None:
        return JSONResponse({"error": "El evento no existe."}, status_code=404)
    semana = dominio.lunes_de_semana_iso(evento.get("fecha", ""))
    turnos = repos.listar_turnos_rota(semana=semana) if semana else []
    nombres = _nombres_equipo()
    franjas_cfg = repos.obtener_franjas_config()
    franjas_lista, franjas_por_id = _franjas_de_semana(semana) if semana else ([], {})
    return JSONResponse(
        {
            "evento": _cobertura_para_evento(
                evento, turnos, nombres, franjas_lista, franjas_por_id
            ),
            "franjas_config": franjas_cfg,
            "franjas": [_franja_semana_a_dict(f) for f in franjas_lista],
        }
    )


# --------------------------------------------------------------------------- #
# Copia de semana + panel de carga                                              #
# --------------------------------------------------------------------------- #


async def copiar_semana(request: Request) -> Response:
    """POST /api/rota/copiar-semana: replica los turnos de una semana a otra (offset +N dias).

    Cuerpo: `{de_lunes, a_lunes, reemplazar?: bool}`. NO copia eventos (cada semana tiene los
    suyos); copia EXCLUSIVAMENTE turnos del horario. Con `reemplazar=true`, primero borra los
    turnos existentes de `a_lunes`. Devuelve `{copiados: N}`.
    """
    datos = await leer_json(request)
    de_lunes = dominio.lunes_de_semana_iso(str(datos.get("de_lunes", "")).strip())
    a_lunes = dominio.lunes_de_semana_iso(str(datos.get("a_lunes", "")).strip())
    reemplazar = bool(datos.get("reemplazar", False))

    if not de_lunes or not a_lunes:
        return JSONResponse(
            {"error": "Indica los lunes origen y destino (AAAA-MM-DD)."}, status_code=400
        )
    if de_lunes == a_lunes:
        return JSONResponse(
            {"error": "La semana origen y la destino no pueden ser la misma."},
            status_code=400,
        )

    n = repos.copiar_turnos_rota(de_lunes, a_lunes, reemplazar=reemplazar)
    return JSONResponse({"copiados": n})


async def carga_semana(request: Request) -> Response:
    """GET /api/rota/carga?lunes=AAAA-MM-DD: panel de carga por miembro.

    Devuelve `{miembros: [...]}` con el resumen de carga: eventos cubiertos (DERIVADO de
    turnos × eventos), dias trabajados, si toca sabado, descansos. Ordenado por el mas
    cargado primero. Datos puros del dominio (`dominio.resumen_carga`).
    """
    lunes = _lunes_param(request)
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana (AAAA-MM-DD)."}, status_code=400
        )
    equipo = _equipo()
    turnos = repos.listar_turnos_rota(semana=lunes)
    inicio, fin = dominio.rango_semana(lunes)
    eventos = repos.listar_eventos_rota(desde=inicio, hasta=fin)
    franjas_lista, _por_id = _franjas_de_semana(lunes)
    cargas = dominio.resumen_carga(
        equipo,
        turnos,
        eventos,
        franjas_lista,
        lunes_iso=lunes,
    )
    return JSONResponse(
        {
            "lunes": lunes,
            "miembros": [
                {
                    "miembro_id": c.miembro_id,
                    "nombre": c.nombre,
                    "eventos": c.eventos,
                    "dias_trabajados": c.dias_trabajados,
                    "sabado": c.sabado,
                    "descansos": c.descansos,
                }
                for c in cargas
            ],
        }
    )


# --------------------------------------------------------------------------- #
# Export .xlsx / CSV (transicion desde el Excel actual)                        #
# --------------------------------------------------------------------------- #

# Cabeceras de la parrilla exportada: mismas columnas que el Excel de Elías.
_CABECERAS_EXPORT = ("Fecha", "Día", "Hora", "Evento / transmisión", "Qué sacar", "Persona", "Estado")
_DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def _filas_export(lunes_iso: str) -> tuple[list[str], list[list[str]]]:
    """Devuelve `(titulo, filas)` de la cobertura DERIVADA de la semana, lista para xlsx/CSV.

    Una fila por (evento, miembro cubridor). Eventos sin cubridores aparecen con `Persona`
    vacia (Elias detecta huecos al exportar). Cobertura DERIVADA: cruza eventos × turnos ×
    franjas vivas de la semana.
    """
    if not lunes_iso:
        return "Rota", []
    inicio, fin = dominio.rango_semana(lunes_iso)
    eventos = repos.listar_eventos_rota(desde=inicio, hasta=fin)
    eventos = [
        e for e in eventos
        if (e.get("tipo_cobertura") or "transmision") != TIPO_COBERTURA_NO_CUBRIR
    ]
    turnos = repos.listar_turnos_rota(semana=lunes_iso)
    nombres = _nombres_equipo()
    franjas_lista, _por_id = _franjas_de_semana(lunes_iso)
    filas: list[list[str]] = []
    from datetime import date as _date

    for e in eventos:
        fecha = e.get("fecha", "") or ""
        try:
            dia = _DIAS[_date.fromisoformat(fecha).weekday()] if fecha else ""
        except ValueError:
            dia = ""
        cubridores = dominio.cobertura_de_evento(e, turnos, franjas_lista)
        if not cubridores:
            filas.append(
                [
                    fecha,
                    dia,
                    e.get("hora", "") or "",
                    e.get("titulo", "") or "",
                    e.get("contenido", "") or "",
                    "",  # sin cubridor
                    "sin cubrir",
                ]
            )
            continue
        for t in cubridores:
            override = " (override)" if t.get("override") else ""
            filas.append(
                [
                    fecha,
                    dia,
                    e.get("hora", "") or "",
                    e.get("titulo", "") or "",
                    e.get("contenido", "") or "",
                    nombres.get(t["miembro_id"], t.get("miembro_nombre", "")),
                    f"{t['estado']}{override}",
                ]
            )
    titulo = f"Rota {inicio} a {fin}" if inicio else "Rota"
    return titulo, filas


def _nombre_descarga(lunes_iso: str, ext: str) -> str:
    sufijo = lunes_iso or "semana"
    return f"rota-{sufijo}.{ext}"


def _grid_horario(lunes_iso: str) -> tuple[str, list[str], list[list[str]]]:
    """Construye `(titulo, cabeceras, filas)` del horario persona×día de la semana.

    Cabeceras = ["Persona", Lun..Dom]; cada fila es un miembro con su franja por día
    (el `nombre` de la franja viva, "Ausente" si una ausencia cubre ese día, "—" si no
    hay turno asignado). Reutiliza `_turnos_semana` y las ausencias para marcar la
    indisponibilidad.
    """
    turnos_payload = _turnos_semana(lunes_iso)
    dias = turnos_payload["dias"]
    equipo = _equipo()
    ausencias = _ausencias_dominio()
    # Indexa el turno por (miembro, fecha) para llenar el grid.
    por_celda: dict[tuple[str, str], dict[str, Any]] = {
        (t["miembro_id"], t["fecha"]): t for t in turnos_payload["turnos"]
    }
    cabeceras = ["Persona", *(_DIAS[i] for i in range(len(dias)))]
    filas: list[list[str]] = []
    for m in sorted(equipo, key=lambda x: x.nombre.lower()):
        fila = [m.nombre]
        for fecha in dias:
            if dominio.miembro_ausente(ausencias, m.id, fecha):
                fila.append("Ausente")
                continue
            turno = por_celda.get((m.id, fecha))
            if turno is None:
                fila.append("—")
            else:
                etiqueta = turno.get("franja_nombre") or "Turno"
                if turno["override"]:
                    etiqueta += " (override)"
                fila.append(etiqueta)
        filas.append(fila)
    titulo = (
        f"Horario equipo {turnos_payload['inicio']} a {turnos_payload['fin']}"
        if turnos_payload["inicio"]
        else "Horario equipo"
    )
    return titulo, cabeceras, filas


async def export_csv(request: Request) -> Response:
    """GET /api/rota/export.csv[?lunes]: descarga la rota de la semana en CSV."""
    lunes = _lunes_param(request)
    _, filas = _filas_export(lunes)
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(_CABECERAS_EXPORT)
    escritor.writerows(filas)
    cabecera = f'attachment; filename="{_nombre_descarga(lunes, "csv")}"'
    # BOM para que Excel abra el UTF-8 con acentos correctamente.
    return Response(
        "﻿" + buffer.getvalue(),
        media_type=_MEDIA_CSV,
        headers={"Content-Disposition": cabecera},
    )


async def export_xlsx(request: Request) -> Response:
    """GET /api/rota/export.xlsx[?lunes]: descarga la rota de la semana en .xlsx.

    Usa `xlsxwriter` (ya presente vía python-pptx; no añade dependencia). Si no
    estuviera disponible, degrada con un 500 accionable (sin traceback crudo).
    """
    lunes = _lunes_param(request)
    titulo, filas = _filas_export(lunes)
    try:
        import xlsxwriter
    except ImportError:
        return JSONResponse(
            {"error": "Falta xlsxwriter para el .xlsx. Usa la exportación CSV mientras tanto."},
            status_code=500,
        )

    buffer = io.BytesIO()
    libro = xlsxwriter.Workbook(buffer, {"in_memory": True})
    fmt_titulo = libro.add_format({"bold": True, "font_size": 14})
    fmt_cabecera = libro.add_format({"bold": True, "bg_color": "#EEEEEE", "border": 1})

    # Hoja 1: cobertura de eventos (la parrilla histórica; columnas del Excel de Elías).
    hoja = libro.add_worksheet("Rota")
    hoja.write(0, 0, titulo, fmt_titulo)
    for col, encabezado in enumerate(_CABECERAS_EXPORT):
        hoja.write(2, col, encabezado, fmt_cabecera)
    for i, fila in enumerate(filas, start=3):
        for col, valor in enumerate(fila):
            hoja.write(i, col, valor)
    anchos = (12, 11, 12, 30, 40, 18, 16)
    for col, ancho in enumerate(anchos):
        hoja.set_column(col, col, ancho)

    # Hoja 2: horario de trabajo del equipo (grid persona×día) — gestión de turnos.
    titulo_h, cabeceras_h, filas_h = _grid_horario(lunes)
    hoja_h = libro.add_worksheet("Horario equipo")
    hoja_h.write(0, 0, titulo_h, fmt_titulo)
    for col, encabezado in enumerate(cabeceras_h):
        hoja_h.write(2, col, encabezado, fmt_cabecera)
    for i, fila in enumerate(filas_h, start=3):
        for col, valor in enumerate(fila):
            hoja_h.write(i, col, valor)
    hoja_h.set_column(0, 0, 18)
    hoja_h.set_column(1, max(len(cabeceras_h) - 1, 1), 12)

    libro.close()

    cabecera = f'attachment; filename="{_nombre_descarga(lunes, "xlsx")}"'
    return Response(
        buffer.getvalue(),
        media_type=_MEDIA_XLSX,
        headers={"Content-Disposition": cabecera},
    )


# --------------------------------------------------------------------------- #
# Piezas de la parrilla (#150 PARRILLA 2026.xlsx)                              #
# --------------------------------------------------------------------------- #
#
# Una pieza = un POST individual (no un evento). Un evento puede generar varias piezas;
# tambien hay piezas SUELTAS (campanas evergreen sin evento). El workflow del Excel
# (material/contenido/publicado/enlace) se persiste tal cual. Los campos de texto libre
# (red_social, tipo_pieza, programa) NO van por allowlist: Tescu usa cadenas como
# "FB, IG, X" / "HISTORIA" / "IG, TK (REEL)" / "WEB" / "IMAGEN" / "REEL" / "FIJAR" que
# todavia no encajan en un set cerrado; nos quedamos con el texto bruto.


def _pieza_a_dict(pieza: dict[str, Any], nombres: dict[str, str]) -> dict[str, Any]:
    """Serializa una pieza, resolviendo el nombre vivo del responsable (renombres)."""
    return {
        "id": pieza["id"],
        "evento_id": pieza.get("evento_id", "") or "",
        "programa": pieza.get("programa", "") or "",
        "red_social": pieza.get("red_social", "") or "",
        "tipo_pieza": pieza.get("tipo_pieza", "") or "",
        "contenido_sugerido": pieza.get("contenido_sugerido", "") or "",
        "dia": pieza.get("dia", "") or "",
        "hora_post": pieza.get("hora_post", "") or "",
        "estado": pieza.get("estado", "pendiente") or "pendiente",
        "material_entregado": bool(pieza.get("material_entregado")),
        "contenido_entregado": bool(pieza.get("contenido_entregado")),
        "publicado": bool(pieza.get("publicado")),
        "enlace": pieza.get("enlace", "") or "",
        "responsable_id": pieza.get("responsable_id", "") or "",
        # El nombre vivo del equipo manda sobre el snapshot guardado (renombres),
        # mismo patron que `_turno_a_dict` / `_ausencia_a_dict`.
        "responsable_nombre": nombres.get(
            pieza.get("responsable_id", ""), pieza.get("responsable_nombre", "")
        ),
        "notas": pieza.get("notas", "") or "",
        # Ampliaciones del Excel real (auditoria): canal amplio, comentarios de coordinacion,
        # deadline interno de material y flag "siempre activo" (campanas evergreen sin fecha).
        "salida": pieza.get("salida", "") or "",
        "comentarios": pieza.get("comentarios", "") or "",
        "fecha_entrega_material": pieza.get("fecha_entrega_material", "") or "",
        "always_on": bool(pieza.get("always_on")),
    }


def _resolver_responsable_pieza(
    responsable_id: object, nombres: dict[str, str]
) -> tuple[str, str, bool]:
    """Resuelve un `responsable_id` del cliente a `(id, nombre, valido)`.

      - `("" / None)` -> `("", "", True)`: sin asignar (se permite explicitamente).
      - id de un usuario REAL -> `(id, nombre, True)`.
      - cualquier otra cosa (id inexistente / tipo raro) -> `("", "", False)`.
    """
    if responsable_id in (None, ""):
        return "", "", True
    if not isinstance(responsable_id, str):
        return "", "", False
    usuario = auth.obtener_usuario_por_id(responsable_id)
    if usuario is None:
        return "", "", False
    return usuario["id"], usuario["usuario"], True


def _evento_existe(evento_id: str) -> bool:
    """True si el `evento_id` referencia un evento real de `rota_eventos`."""
    if not evento_id:
        return False
    return repos.obtener_evento_rota(evento_id) is not None


def _fecha_iso_valida_o_vacia(valor: str) -> bool:
    """True si `valor` es "" (sin fechar) o un AAAA-MM-DD valido."""
    if not valor:
        return True
    return dominio.lunes_de_semana_iso(valor) != ""


async def listar_piezas(request: Request) -> Response:
    """GET /api/rota/piezas[?filtros]: piezas de la parrilla, con filtros combinables.

    Filtros opcionales (query): `evento_id` ("" para piezas SUELTAS), `desde`/`hasta`
    (rango de `dia` ISO), `red`, `tipo`, `estado`, `responsable_id`, `programa`.
    """
    qp = request.query_params
    evento_id = qp.get("evento_id")  # None / "" / id
    # `evento_id=""` (cadena vacia explicita) significa "piezas sueltas, sin evento"; sin
    # el parametro (None) significa "no filtrar por evento".
    if "evento_id" not in qp:
        evento_id = None
    desde = (qp.get("desde") or "").strip() or None
    hasta = (qp.get("hasta") or "").strip() or None
    red = (qp.get("red") or "").strip() or None
    tipo = (qp.get("tipo") or "").strip() or None
    estado = (qp.get("estado") or "").strip() or None
    responsable_id = qp.get("responsable_id")
    if "responsable_id" not in qp:
        responsable_id = None
    programa = qp.get("programa")
    if "programa" not in qp:
        programa = None

    if estado is not None and estado not in ESTADOS_PIEZA:
        validos = " o ".join(f'"{e}"' for e in ESTADOS_PIEZA)
        return JSONResponse({"error": f"Estado inválido. Usa {validos}."}, status_code=400)
    if desde is not None and not _fecha_iso_valida_o_vacia(desde):
        return JSONResponse({"error": "La fecha 'desde' no es válida (usa AAAA-MM-DD)."}, status_code=400)
    if hasta is not None and not _fecha_iso_valida_o_vacia(hasta):
        return JSONResponse({"error": "La fecha 'hasta' no es válida (usa AAAA-MM-DD)."}, status_code=400)

    piezas = repos.listar_piezas_rota(
        evento_id=evento_id,
        desde=desde,
        hasta=hasta,
        red=red,
        tipo=tipo,
        estado=estado,
        responsable_id=responsable_id,
        programa=programa,
    )
    nombres = _nombres_equipo()
    return JSONResponse({"piezas": [_pieza_a_dict(p, nombres) for p in piezas]})


async def crear_pieza(request: Request) -> Response:
    """POST /api/rota/piezas: alta de una pieza (post individual de la parrilla).

    Al menos uno entre `evento_id`, `programa` o `contenido_sugerido` debe estar relleno
    (sin esto la pieza no representa nada). Valida que `evento_id` (si se manda) referencie
    un evento real y `responsable_id` (si se manda) un usuario real.
    """
    datos = await leer_json(request)
    nombres = _nombres_equipo()

    evento_id = str(datos.get("evento_id", "")).strip()
    programa = str(datos.get("programa", "")).strip()
    contenido_sugerido = str(datos.get("contenido_sugerido", "")).strip()
    if not evento_id and not programa and not contenido_sugerido:
        return JSONResponse(
            {
                "error": (
                    "La pieza necesita al menos un evento, un programa o un contenido "
                    "sugerido."
                )
            },
            status_code=400,
        )
    if evento_id and not _evento_existe(evento_id):
        return JSONResponse({"error": "Ese evento no existe."}, status_code=400)

    estado = str(datos.get("estado", "pendiente")).strip() or "pendiente"
    if estado not in ESTADOS_PIEZA:
        validos = " o ".join(f'"{e}"' for e in ESTADOS_PIEZA)
        return JSONResponse({"error": f"Estado inválido. Usa {validos}."}, status_code=400)

    dia = str(datos.get("dia", "")).strip()
    if dia and not _fecha_iso_valida_o_vacia(dia):
        return JSONResponse({"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400)

    fecha_entrega_material = str(datos.get("fecha_entrega_material", "")).strip()
    if fecha_entrega_material and not _fecha_iso_valida_o_vacia(fecha_entrega_material):
        return JSONResponse(
            {"error": "La fecha de entrega de material no es válida (usa AAAA-MM-DD)."},
            status_code=400,
        )

    enlace = str(datos.get("enlace", "")).strip()
    if len(enlace) > _MAX_ENLACE_PIEZA:
        return JSONResponse({"error": "El enlace es demasiado largo."}, status_code=400)

    resp_id, resp_nombre, valido = _resolver_responsable_pieza(
        datos.get("responsable_id"), nombres
    )
    if not valido:
        return JSONResponse({"error": "El responsable no es un usuario válido."}, status_code=400)

    pieza = repos.crear_pieza_rota(
        evento_id=evento_id,
        programa=programa,
        red_social=str(datos.get("red_social", "")).strip(),
        tipo_pieza=str(datos.get("tipo_pieza", "")).strip(),
        contenido_sugerido=contenido_sugerido,
        dia=dia,
        hora_post=str(datos.get("hora_post", "")).strip(),
        estado=estado,
        material_entregado=bool(datos.get("material_entregado", False)),
        contenido_entregado=bool(datos.get("contenido_entregado", False)),
        publicado=bool(datos.get("publicado", False)),
        enlace=enlace,
        responsable_id=resp_id,
        responsable_nombre=resp_nombre,
        notas=str(datos.get("notas", "")).strip(),
        # Ampliaciones del Excel real (auditoria): salida (canal amplio), comentarios
        # (coordinacion pre/durante), fecha_entrega_material (deadline interno) y always_on
        # (flag de pieza siempre activa, p. ej. "ALWAYS ON" de PATY CANTU).
        salida=str(datos.get("salida", "")).strip(),
        comentarios=str(datos.get("comentarios", "")).strip(),
        fecha_entrega_material=fecha_entrega_material,
        always_on=bool(datos.get("always_on", False)),
    )
    return JSONResponse({"pieza": _pieza_a_dict(pieza, nombres)}, status_code=201)


async def actualizar_pieza(request: Request) -> Response:
    """PATCH /api/rota/piezas/{id}: edicion parcial de una pieza.

    Cualquier subconjunto de campos editables. Las mismas validaciones que en `crear_pieza`
    aplican a los campos presentes: `evento_id` (si no vacio) debe existir, `responsable_id`
    (si no vacio) debe ser usuario real, `estado` debe ser de `ESTADOS_PIEZA`, `enlace` <=
    `_MAX_ENLACE_PIEZA`, `dia` debe ser AAAA-MM-DD o "".
    """
    pieza_id = request.path_params["pieza_id"]
    actual = repos.obtener_pieza_rota(pieza_id)
    if actual is None:
        return JSONResponse({"error": "La pieza ya no existe."}, status_code=404)

    datos = await leer_json(request)
    nombres = _nombres_equipo()
    campos: dict[str, Any] = {}

    if "evento_id" in datos:
        evento_id = str(datos.get("evento_id", "")).strip()
        if evento_id and not _evento_existe(evento_id):
            return JSONResponse({"error": "Ese evento no existe."}, status_code=400)
        campos["evento_id"] = evento_id

    for clave in (
        "programa",
        "red_social",
        "tipo_pieza",
        "contenido_sugerido",
        "hora_post",
        "notas",
        "salida",
        "comentarios",
    ):
        if clave in datos:
            valor = datos[clave]
            campos[clave] = str(valor).strip() if isinstance(valor, str) else ""

    if "dia" in datos:
        dia = str(datos.get("dia", "")).strip()
        if dia and not _fecha_iso_valida_o_vacia(dia):
            return JSONResponse({"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400)
        campos["dia"] = dia

    if "fecha_entrega_material" in datos:
        fem = str(datos.get("fecha_entrega_material", "")).strip()
        if fem and not _fecha_iso_valida_o_vacia(fem):
            return JSONResponse(
                {"error": "La fecha de entrega de material no es válida (usa AAAA-MM-DD)."},
                status_code=400,
            )
        campos["fecha_entrega_material"] = fem

    if "estado" in datos:
        estado = str(datos.get("estado", "")).strip()
        if estado not in ESTADOS_PIEZA:
            validos = " o ".join(f'"{e}"' for e in ESTADOS_PIEZA)
            return JSONResponse({"error": f"Estado inválido. Usa {validos}."}, status_code=400)
        campos["estado"] = estado

    if "enlace" in datos:
        enlace = str(datos.get("enlace", "")).strip()
        if len(enlace) > _MAX_ENLACE_PIEZA:
            return JSONResponse({"error": "El enlace es demasiado largo."}, status_code=400)
        campos["enlace"] = enlace

    for bool_col in ("material_entregado", "contenido_entregado", "publicado", "always_on"):
        if bool_col in datos:
            campos[bool_col] = bool(datos[bool_col])

    if "responsable_id" in datos:
        resp_id, resp_nombre, valido = _resolver_responsable_pieza(
            datos.get("responsable_id"), nombres
        )
        if not valido:
            return JSONResponse({"error": "El responsable no es un usuario válido."}, status_code=400)
        # Sin asignar limpia ambas columnas; asignado las fija a la par (mismo patron que
        # las tareas del tablero).
        campos["responsable_id"] = resp_id
        campos["responsable_nombre"] = resp_nombre

    pieza = repos.actualizar_pieza_rota(pieza_id, campos)
    if pieza is None:
        return JSONResponse({"error": "La pieza ya no existe."}, status_code=404)
    return JSONResponse({"pieza": _pieza_a_dict(pieza, nombres)})


async def borrar_pieza(request: Request) -> Response:
    """DELETE /api/rota/piezas/{id}: borra la pieza. 200 si existia, 404 si no."""
    pieza_id = request.path_params["pieza_id"]
    if not repos.borrar_pieza_rota(pieza_id):
        return JSONResponse({"error": "La pieza ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Pieza eliminada."})


# --------------------------------------------------------------------------- #
# Solicitudes de cambio de turno entre companeros (#175)                       #
# --------------------------------------------------------------------------- #
#
# Flujo: A (solicitante) crea -> B (destinatario) acepta/rechaza -> admin aprueba
# (ejecuta el swap sobre rota_turnos_trabajo) o rechaza. A puede cancelar mientras
# no sea terminal. Las ausencias REALES (vacaciones/baja) viven en SAP.
#
# Estados validos: estados.ESTADOS_SWAP. Cualquier transicion no contemplada -> 409.

_MSG_SOLO_ADMIN_SWAP = (
    "Solo Elías (administrador) puede aprobar/rechazar un cambio de turno."
)


def _swap_a_dict(swap: dict[str, Any], nombres: dict[str, str]) -> dict[str, Any]:
    """Serializa un swap (resolviendo el nombre vivo de cada miembro)."""
    return {
        "id": swap["id"],
        "solicitante_id": swap["solicitante_id"],
        # Nombre vivo del equipo > snapshot (un usuario puede renombrarse).
        "solicitante_nombre": nombres.get(
            swap["solicitante_id"], swap.get("solicitante_nombre", "")
        ),
        "destinatario_id": swap["destinatario_id"],
        "destinatario_nombre": nombres.get(
            swap["destinatario_id"], swap.get("destinatario_nombre", "")
        ),
        "fecha_a": swap["fecha_a"],
        "franja_a": swap["franja_a"],
        "fecha_b": swap["fecha_b"],
        "franja_b": swap["franja_b"],
        "motivo": swap["motivo"],
        "estado": swap["estado"],
        "respuesta_destinatario": swap["respuesta_destinatario"],
        "respuesta_admin": swap["respuesta_admin"],
        "creado": swap["creado"],
        "actualizado": swap["actualizado"],
        "decidido_destinatario": swap["decidido_destinatario"],
        "decidido_admin": swap["decidido_admin"],
        "aplicado": swap["aplicado"],
    }


def _existe_turno(miembro_id: str, fecha: str, franja_id: str) -> bool:
    """True si EXISTE un turno en `rota_turnos` con `(miembro_id, fecha, franja_id)`.

    Delega en `repos.existe_turno_para` (un solo SELECT directo en BD).
    """
    return repos.existe_turno_para(miembro_id, fecha, franja_id) is not None


def _mio_param(request: Request) -> bool:
    """¿La query trae `mio=true` (filtrar a swaps que me involucran)?"""
    return (request.query_params.get("mio") or "").strip().lower() in (
        "1",
        "true",
        "sí",
        "si",
    )


def _estado_param(request: Request) -> str | None:
    """Estado pedido en `?estado=`, validando contra la allowlist. None si no se pidio.

    Si el cliente pasa un estado fuera de la allowlist devolvemos None (el handler trata
    eso como "filtro invalido" via la propia validacion del estado al construir la consulta:
    aqui simplemente lo ignoramos). Es defensivo: el DB solo devuelve filas reales.
    """
    crudo = (request.query_params.get("estado") or "").strip()
    return crudo or None


async def listar_swaps(request: Request) -> Response:
    """GET /api/rota/swaps[?estado&solicitante_id&destinatario_id&mio=true]: solicitudes de swap.

    Si `mio=true` y hay sesion, filtra a swaps donde el usuario actual sea solicitante o
    destinatario. Devuelve `{swaps: [...]}` ordenado por mas reciente primero.
    """
    estado = _estado_param(request)
    solicitante_id = (request.query_params.get("solicitante_id") or "").strip() or None
    destinatario_id = (request.query_params.get("destinatario_id") or "").strip() or None
    mio_id: str | None = None
    if _mio_param(request):
        usuario = _usuario_actual(request)
        if usuario is not None:
            mio_id = usuario["id"]
        else:
            # Sin sesion no hay "mio": devolvemos lista vacia (es semantica honesta).
            return JSONResponse({"swaps": []})
    swaps = repos.listar_swaps_turno(
        estado=estado,
        solicitante_id=solicitante_id,
        destinatario_id=destinatario_id,
        mio_id=mio_id,
    )
    nombres = _nombres_equipo()
    return JSONResponse({"swaps": [_swap_a_dict(s, nombres) for s in swaps]})


async def crear_swap(request: Request) -> Response:
    """POST /api/rota/swaps: A (sesion) crea una solicitud de cambio de turno con B.

    Cuerpo: `{destinatario_id, fecha_a, franja_a, fecha_b, franja_b, motivo?}`. El
    solicitante se toma de `request.state.usuario` (NUNCA del cliente). Valida que los
    turnos existan en `rota_turnos_trabajo`; si no, 400 con motivo accionable.
    """
    usuario = _usuario_actual(request)
    if usuario is None:
        return JSONResponse(
            {"error": "Inicia sesión para solicitar un cambio de turno."}, status_code=401
        )
    datos = await leer_json(request)
    nombres = _nombres_equipo()

    destinatario_id = datos.get("destinatario_id")
    if not isinstance(destinatario_id, str) or not destinatario_id:
        return JSONResponse(
            {"error": "Indica al compañero al que pides el cambio."}, status_code=400
        )
    if destinatario_id == usuario["id"]:
        return JSONResponse(
            {"error": "No puedes cambiarte el turno contigo mismo/a."}, status_code=400
        )
    # `destinatario_id` debe ser un usuario REAL (no un id arbitrario del cliente).
    if auth.obtener_usuario_por_id(destinatario_id) is None or destinatario_id not in nombres:
        return JSONResponse(
            {"error": "Ese compañero no existe en el equipo."}, status_code=400
        )

    fecha_a = str(datos.get("fecha_a", "")).strip()
    fecha_b = str(datos.get("fecha_b", "")).strip()
    if not _fecha_valida(fecha_a) or not _fecha_valida(fecha_b):
        return JSONResponse(
            {"error": "Las fechas no son válidas (usa AAAA-MM-DD)."}, status_code=400
        )
    # `franja_a`/`franja_b` ahora son `franja_id` reales (la columna en BD conserva el
    # nombre `franja_a/_b` por inercia: cambio de SEMANTICA del dato, no de columna).
    franja_a = str(datos.get("franja_a", "")).strip()
    franja_b = str(datos.get("franja_b", "")).strip()
    if not franja_a or not franja_b:
        return JSONResponse(
            {"error": "Indica `franja_a` y `franja_b` (franja_id de la semana de cada turno)."},
            status_code=400,
        )
    if (
        repos.obtener_franja_semana(franja_a) is None
        or repos.obtener_franja_semana(franja_b) is None
    ):
        return JSONResponse(
            {"error": "Alguna de las franjas indicadas no existe."}, status_code=400
        )

    # Los turnos DEBEN existir en el horario: si no, no hay nada que cambiar.
    if not _existe_turno(usuario["id"], fecha_a, franja_a):
        return JSONResponse(
            {
                "error": (
                    "No encuentro tu turno en el horario para esa fecha y franja. "
                    "Pide a Elías que proponga/apruebe el horario antes."
                )
            },
            status_code=400,
        )
    if not _existe_turno(destinatario_id, fecha_b, franja_b):
        return JSONResponse(
            {
                "error": (
                    "No encuentro el turno de tu compañero en el horario para esa "
                    "fecha y franja."
                )
            },
            status_code=400,
        )

    motivo = str(datos.get("motivo", "")).strip()

    swap = repos.crear_swap_turno(
        usuario["id"],
        destinatario_id,
        fecha_a,
        franja_a,
        fecha_b,
        franja_b,
        solicitante_nombre=nombres.get(usuario["id"], usuario.get("usuario", "")),
        destinatario_nombre=nombres.get(destinatario_id, ""),
        motivo=motivo,
    )
    return JSONResponse({"swap": _swap_a_dict(swap, nombres)}, status_code=201)


def _error_transicion(estado_actual: str, accion: str) -> Response:
    """Respuesta 409 estandar cuando el swap no admite esa transicion ahora mismo."""
    return JSONResponse(
        {
            "error": (
                f"No se puede {accion} ahora: el cambio está en estado «{estado_actual}»."
            ),
            "estado_actual": estado_actual,
        },
        status_code=409,
    )


async def _ahora_yo_soy(request: Request, swap_id: str) -> tuple[Response | None, dict | None, dict | None]:
    """Helper: carga el swap y el usuario actual; 401/404 si fallan.

    Devuelve `(respuesta_error, swap, usuario)`. Si `respuesta_error` no es None, el
    handler debe retornarlo directamente.
    """
    usuario = _usuario_actual(request)
    if usuario is None:
        return (
            JSONResponse({"error": "Inicia sesión para responder al cambio."}, status_code=401),
            None,
            None,
        )
    swap = repos.obtener_swap_turno(swap_id)
    if swap is None:
        return (
            JSONResponse({"error": "La solicitud de cambio ya no existe."}, status_code=404),
            None,
            None,
        )
    return None, swap, usuario


async def aceptar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/aceptar: el DESTINATARIO acepta el cambio.

    Solo si el estado actual es `propuesto` y el usuario es el destinatario. Cuerpo
    opcional `{respuesta}` para dejar una nota a A/Elías.
    """
    swap_id = request.path_params["swap_id"]
    err, swap, usuario = await _ahora_yo_soy(request, swap_id)
    if err is not None:
        return err
    assert swap is not None and usuario is not None
    if swap["destinatario_id"] != usuario["id"]:
        return JSONResponse(
            {"error": "Solo el compañero al que se le pide el cambio puede aceptarlo."},
            status_code=403,
        )
    if swap["estado"] != ESTADO_SWAP_PROPUESTO:
        return _error_transicion(swap["estado"], "aceptar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    ahora = _ahora_iso()
    actualizado = repos.actualizar_swap_turno(
        swap_id,
        {
            "estado": "aceptado",
            "respuesta_destinatario": respuesta,
            "decidido_destinatario": ahora,
        },
    )
    if actualizado is None:  # carrera: lo borraron entre medias
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    return JSONResponse({"swap": _swap_a_dict(actualizado, _nombres_equipo())})


async def rechazar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/rechazar: el DESTINATARIO rechaza el cambio.

    Solo si `propuesto` y el usuario es el destinatario. Cuerpo opcional con `respuesta`.
    """
    swap_id = request.path_params["swap_id"]
    err, swap, usuario = await _ahora_yo_soy(request, swap_id)
    if err is not None:
        return err
    assert swap is not None and usuario is not None
    if swap["destinatario_id"] != usuario["id"]:
        return JSONResponse(
            {"error": "Solo el compañero al que se le pide el cambio puede rechazarlo."},
            status_code=403,
        )
    if swap["estado"] != ESTADO_SWAP_PROPUESTO:
        return _error_transicion(swap["estado"], "rechazar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    ahora = _ahora_iso()
    actualizado = repos.actualizar_swap_turno(
        swap_id,
        {
            "estado": ESTADO_SWAP_RECHAZADO,
            "respuesta_destinatario": respuesta,
            "decidido_destinatario": ahora,
        },
    )
    if actualizado is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    return JSONResponse({"swap": _swap_a_dict(actualizado, _nombres_equipo())})


async def aprobar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/aprobar: admin APRUEBA y EJECUTA el swap.

    Solo `aceptado` -> `aplicado`. Re-valida en el momento que las franjas actuales en
    `rota_turnos_trabajo` siguen siendo las del swap. Si NO coinciden (alguien las
    cambio a mano), devuelve 409 con detalle y NO toca nada. Si todo cuadra, intercambia
    los `miembro_id` y marca la solicitud como `aplicado` en una transaccion.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN_SWAP}, status_code=403)
    swap_id = request.path_params["swap_id"]
    swap = repos.obtener_swap_turno(swap_id)
    if swap is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    if swap["estado"] != ESTADO_SWAP_ACEPTADO:
        return _error_transicion(swap["estado"], "aprobar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    nombres = _nombres_equipo()
    resultado = repos.aplicar_swap_turno(
        swap_id,
        solicitante_id=swap["solicitante_id"],
        solicitante_nombre=nombres.get(swap["solicitante_id"], swap["solicitante_nombre"]),
        destinatario_id=swap["destinatario_id"],
        destinatario_nombre=nombres.get(swap["destinatario_id"], swap["destinatario_nombre"]),
        fecha_a=swap["fecha_a"],
        franja_a=swap["franja_a"],
        fecha_b=swap["fecha_b"],
        franja_b=swap["franja_b"],
        respuesta_admin=respuesta,
    )
    if resultado is None:  # carrera: el swap se borro
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    if "error" in resultado and resultado["error"] == "no_coinciden":
        return JSONResponse(
            {
                "error": "Los turnos ya no son los del cambio original.",
                "detalle": {
                    "esperado": resultado["esperado"],
                    "actual": resultado["actual"],
                },
            },
            status_code=409,
        )
    return JSONResponse({"swap": _swap_a_dict(resultado, nombres)})


async def rechazar_swap_admin(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/rechazar-admin: admin rechaza tras la aceptacion de B.

    Solo si `aceptado` -> `rechazado_admin`. Cuerpo opcional con `respuesta`.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN_SWAP}, status_code=403)
    swap_id = request.path_params["swap_id"]
    swap = repos.obtener_swap_turno(swap_id)
    if swap is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    if swap["estado"] != ESTADO_SWAP_ACEPTADO:
        return _error_transicion(swap["estado"], "rechazar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    ahora = _ahora_iso()
    actualizado = repos.actualizar_swap_turno(
        swap_id,
        {
            "estado": ESTADO_SWAP_RECHAZADO_ADMIN,
            "respuesta_admin": respuesta,
            "decidido_admin": ahora,
        },
    )
    if actualizado is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    return JSONResponse({"swap": _swap_a_dict(actualizado, _nombres_equipo())})


async def cancelar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/cancelar: el SOLICITANTE cancela su solicitud.

    Solo si el estado no es terminal (`propuesto` o `aceptado`) y el usuario es A.
    """
    swap_id = request.path_params["swap_id"]
    err, swap, usuario = await _ahora_yo_soy(request, swap_id)
    if err is not None:
        return err
    assert swap is not None and usuario is not None
    if swap["solicitante_id"] != usuario["id"]:
        return JSONResponse(
            {"error": "Solo quien solicitó el cambio puede cancelarlo."},
            status_code=403,
        )
    if swap["estado"] not in (ESTADO_SWAP_PROPUESTO, ESTADO_SWAP_ACEPTADO):
        return _error_transicion(swap["estado"], "cancelar")
    actualizado = repos.actualizar_swap_turno(swap_id, {"estado": ESTADO_SWAP_CANCELADO})
    if actualizado is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    return JSONResponse({"swap": _swap_a_dict(actualizado, _nombres_equipo())})


def _ahora_iso() -> str:
    """Timestamp ISO con segundos (mismo formato que el resto del modulo)."""
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Piezas: duplicar + borrar en lote                                            #
# --------------------------------------------------------------------------- #


async def duplicar_pieza(request: Request) -> Response:
    """POST /api/rota/piezas/{id}/duplicar: clona una pieza (workflow reset).

    Cuerpo opcional `{dia?, evento_id?}`. El clon RESETEA material/contenido/publicado/
    enlace/notas/comentarios y vuelve a `estado="pendiente"`: duplicar una pieza es repetir
    el TRABAJO de producción. `dia`/`evento_id` se pueden sobrescribir desde el cuerpo
    (caso típico: "Pumas vs América Jornada 17 -> Jornada 18").
    """
    pieza_id = request.path_params["pieza_id"]
    datos = await leer_json(request) or {}
    dia: str | None = None
    evento_id: str | None = None
    if "dia" in datos:
        dia = str(datos.get("dia", "")).strip()
        if dia and not _fecha_iso_valida_o_vacia(dia):
            return JSONResponse(
                {"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400
            )
    if "evento_id" in datos:
        evento_id = str(datos.get("evento_id", "")).strip()
        if evento_id and not _evento_existe(evento_id):
            return JSONResponse({"error": "Ese evento no existe."}, status_code=400)
    pieza = repos.duplicar_pieza_rota(pieza_id, dia=dia, evento_id=evento_id)
    if pieza is None:
        return JSONResponse({"error": "La pieza ya no existe."}, status_code=404)
    return JSONResponse({"pieza": _pieza_a_dict(pieza, _nombres_equipo())}, status_code=201)


async def borrar_piezas_lote(request: Request) -> Response:
    """POST /api/rota/piezas/lote/borrar: borra varias piezas a la vez.

    Cuerpo: `{ids: [pieza_id, ...]}`. Mismo contrato que `/api/rota/turnos/lote/borrar`:
    `{borrados: N, no_encontrados: [ids]}`.
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) and x for x in ids) or not ids:
        return JSONResponse(
            {"error": "Indica al menos una pieza (`ids`)."}, status_code=400
        )
    # Pre-comprobamos cuales existen (para reportar los no encontrados sin falsear la cuenta).
    todas = {p["id"] for p in repos.listar_piezas_rota()}
    existentes = [i for i in ids if i in todas]
    no_encontrados = [i for i in ids if i not in todas]
    n = repos.borrar_piezas_rota_lote(existentes)
    return JSONResponse({"borrados": n, "no_encontrados": no_encontrados})


# --------------------------------------------------------------------------- #
# Eventos: duplicar                                                            #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Catálogo de programas (#150, PARRILLA 2026.xlsx)                              #
# --------------------------------------------------------------------------- #
#
# Cada hoja EVERGREEN del Excel es un PROGRAMA ("Álvaro Fidalgo", "Real Oviedo",
# "Anfitriones", "PATY CANTU", "MUNDIAL", "LA SELECCIÓN EN TUS MANOS", "IDEAS SIN
# DERECHOS"). Se cataloga con color y fechas; las piezas referencian POR NOMBRE (no por
# id) para que una pieza huérfana de un programa borrado siga apareciendo con su texto.
# Renombrar un programa hace cascada sobre `rota_piezas.programa` (transaccional, vive en
# `db.py`).
#
# Color: texto libre (la UI usa hex `#RRGGBB`); no se valida la sintaxis para no atar la API
# al esquema de colores del front. La UI decide si lo respeta o lo limpia.


_MAX_NOMBRE_PROGRAMA = 200


def _programa_a_dict(programa: dict[str, Any]) -> dict[str, Any]:
    """Serializa un programa al contrato HTTP (booleano explícito, defaults sanos)."""
    return {
        "id": programa["id"],
        "nombre": programa.get("nombre", "") or "",
        "descripcion": programa.get("descripcion", "") or "",
        "color": programa.get("color", "") or "",
        "inicio": programa.get("inicio", "") or "",
        "fin": programa.get("fin", "") or "",
        "activo": bool(programa.get("activo", True)),
        "creado": programa.get("creado", "") or "",
        "actualizado": programa.get("actualizado", "") or "",
    }


def _activo_param(crudo: str | None) -> bool | None:
    """Convierte un query-param string a tri-estado (None / True / False)."""
    if crudo is None:
        return None
    valor = crudo.strip().lower()
    if valor in ("1", "true", "sí", "si"):
        return True
    if valor in ("0", "false", "no"):
        return False
    return None


async def listar_programas(request: Request) -> Response:
    """GET /api/rota/programas[?activo=true|false]: programas del catálogo."""
    activo = _activo_param(request.query_params.get("activo"))
    programas = repos.listar_programas_rota(activo=activo)
    return JSONResponse({"programas": [_programa_a_dict(p) for p in programas]})


async def crear_programa(request: Request) -> Response:
    """POST /api/rota/programas: alta de un programa.

    Cuerpo: `{nombre, descripcion?, color?, inicio?, fin?, activo?}`. `nombre` es único
    case-insensitive (si ya existe, 409 con `programa_existente`).
    """
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El programa necesita un nombre."}, status_code=400)
    nombre = nombre.strip()
    if len(nombre) > _MAX_NOMBRE_PROGRAMA:
        return JSONResponse(
            {"error": f"El nombre no puede tener más de {_MAX_NOMBRE_PROGRAMA} caracteres."},
            status_code=400,
        )
    # Unicidad case-insensitive: defensa en profundidad (el UNIQUE del DDL es el ultimo cerrojo).
    if repos.existe_programa_por_nombre(nombre):
        return JSONResponse(
            {"error": "Ya existe un programa con ese nombre.", "programa_existente": True},
            status_code=409,
        )
    inicio = str(datos.get("inicio", "")).strip()
    fin = str(datos.get("fin", "")).strip()
    if inicio and not _fecha_iso_valida_o_vacia(inicio):
        return JSONResponse(
            {"error": "La fecha de inicio no es válida (usa AAAA-MM-DD)."}, status_code=400
        )
    if fin and not _fecha_iso_valida_o_vacia(fin):
        return JSONResponse(
            {"error": "La fecha de fin no es válida (usa AAAA-MM-DD)."}, status_code=400
        )
    if inicio and fin and fin < inicio:
        return JSONResponse(
            {"error": "La fecha de fin no puede ser anterior a la de inicio."},
            status_code=400,
        )
    programa = repos.crear_programa_rota(
        nombre,
        descripcion=str(datos.get("descripcion", "")).strip(),
        color=str(datos.get("color", "")).strip(),
        inicio=inicio,
        fin=fin,
        activo=bool(datos.get("activo", True)),
    )
    return JSONResponse({"programa": _programa_a_dict(programa)}, status_code=201)


async def actualizar_programa(request: Request) -> Response:
    """PATCH /api/rota/programas/{id}: edita un programa.

    Si cambia `nombre`, hace CASCADA sobre `rota_piezas.programa` (transaccional). El nuevo
    nombre debe ser único case-insensitive (si otro programa ya lo usa, 409).
    """
    programa_id = request.path_params["programa_id"]
    actual = repos.obtener_programa_rota(programa_id)
    if actual is None:
        return JSONResponse({"error": "El programa ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nuevo = datos["nombre"]
        if not isinstance(nuevo, str) or not nuevo.strip():
            return JSONResponse(
                {"error": "El programa necesita un nombre."}, status_code=400
            )
        nuevo = nuevo.strip()
        if len(nuevo) > _MAX_NOMBRE_PROGRAMA:
            return JSONResponse(
                {"error": f"El nombre no puede tener más de {_MAX_NOMBRE_PROGRAMA} caracteres."},
                status_code=400,
            )
        # Si el nuevo nombre (case-insensitive) ya existe en OTRO programa -> 409.
        if nuevo.lower() != (actual.get("nombre") or "").lower() and repos.existe_programa_por_nombre(nuevo):
            return JSONResponse(
                {
                    "error": "Ya existe un programa con ese nombre.",
                    "programa_existente": True,
                },
                status_code=409,
            )
        campos["nombre"] = nuevo
    for clave in ("descripcion", "color"):
        if clave in datos:
            valor = datos[clave]
            campos[clave] = str(valor).strip() if isinstance(valor, str) else ""
    for fecha_col in ("inicio", "fin"):
        if fecha_col in datos:
            valor = str(datos.get(fecha_col, "")).strip()
            if valor and not _fecha_iso_valida_o_vacia(valor):
                return JSONResponse(
                    {"error": f"La fecha de {fecha_col} no es válida (usa AAAA-MM-DD)."},
                    status_code=400,
                )
            campos[fecha_col] = valor
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])
    # Coherencia del rango si quedan ambos extremos.
    nuevo_inicio = campos.get("inicio", actual.get("inicio", ""))
    nuevo_fin = campos.get("fin", actual.get("fin", ""))
    if nuevo_inicio and nuevo_fin and nuevo_fin < nuevo_inicio:
        return JSONResponse(
            {"error": "La fecha de fin no puede ser anterior a la de inicio."},
            status_code=400,
        )
    programa = repos.actualizar_programa_rota(programa_id, campos)
    if programa is None:
        return JSONResponse({"error": "El programa ya no existe."}, status_code=404)
    return JSONResponse({"programa": _programa_a_dict(programa)})


async def borrar_programa(request: Request) -> Response:
    """DELETE /api/rota/programas/{id}[?forzar=true]: borra un programa.

    Si HAY piezas referenciando el programa (por nombre), devuelve 409 con
    `{en_uso: True, piezas_afectadas: N}` salvo que el cliente pase `?forzar=true` (lo
    típico de Elías: "ya sé que hay piezas y aun así quiero borrar el catálogo; las
    piezas huérfanas seguirán mostrando el nombre textual").
    """
    programa_id = request.path_params["programa_id"]
    actual = repos.obtener_programa_rota(programa_id)
    if actual is None:
        return JSONResponse({"error": "El programa ya no existe."}, status_code=404)
    forzar = (request.query_params.get("forzar") or "").strip().lower() in (
        "1",
        "true",
        "sí",
        "si",
    )
    en_uso = repos.contar_piezas_por_programa(actual["nombre"])
    if en_uso and not forzar:
        return JSONResponse(
            {
                "error": (
                    f"El programa «{actual['nombre']}» está en uso por {en_uso} piezas. "
                    "Llama con `?forzar=true` para borrarlo igualmente."
                ),
                "en_uso": True,
                "piezas_afectadas": en_uso,
            },
            status_code=409,
        )
    if not repos.borrar_programa_rota(programa_id):
        return JSONResponse({"error": "El programa ya no existe."}, status_code=404)
    return JSONResponse(
        {"mensaje": "Programa eliminado.", "piezas_afectadas": en_uso}
    )


# --------------------------------------------------------------------------- #
# Config de franjas (#185)                                                     #
# --------------------------------------------------------------------------- #


_PATRON_HORA = re.compile(r"^([01]?\d|2[0-4]):([0-5]\d)$")


def _hora_valida(valor: Any) -> bool:
    """`HH:MM` con 00:00..24:00 (24:00 valido como FIN exclusivo de franja)."""
    if not isinstance(valor, str):
        return False
    m = _PATRON_HORA.match(valor.strip())
    if not m:
        return False
    h, mm = int(m.group(1)), int(m.group(2))
    if h == 24 and mm != 0:
        return False
    return True


def _minutos_de(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


async def obtener_config_franjas(request: Request) -> Response:
    """GET /api/rota/config/franjas: devuelve los rangos vigentes (defaults si no hay)."""
    del request
    return JSONResponse({"franjas": repos.obtener_franjas_config()})


async def guardar_config_franjas(request: Request) -> Response:
    """PATCH /api/rota/config/franjas: cambia los rangos vigentes (solo admin).

    Cuerpo: `{matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin}` en
    `HH:MM`. Reglas: `inicio < fin` en cada franja; matutino y vespertino no se
    solapan internamente, pero `matutino_fin == vespertino_inicio` SI esta permitido
    (intencional: las franjas se tocan en el limite). Aplica solo a `asignar-franja`
    (cobertura de eventos por hora), no toca los turnos de trabajo del horario.
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un admin puede editar la configuración de franjas."},
            status_code=403,
        )
    datos = await leer_json(request)
    campos = (
        "matutino_inicio",
        "matutino_fin",
        "vespertino_inicio",
        "vespertino_fin",
    )
    for c in campos:
        if not _hora_valida(datos.get(c)):
            return JSONResponse(
                {"error": f"`{c}` debe ser HH:MM (00:00..24:00)."}, status_code=400
            )
    m_ini = _minutos_de(datos["matutino_inicio"])
    m_fin = _minutos_de(datos["matutino_fin"])
    v_ini = _minutos_de(datos["vespertino_inicio"])
    v_fin = _minutos_de(datos["vespertino_fin"])
    if not (m_ini < m_fin):
        return JSONResponse(
            {"error": "El matutino tiene que terminar después de empezar."},
            status_code=400,
        )
    if not (v_ini < v_fin):
        return JSONResponse(
            {"error": "El vespertino tiene que terminar después de empezar."},
            status_code=400,
        )
    if m_fin > v_ini:
        return JSONResponse(
            {"error": "El matutino se solapa con el vespertino."}, status_code=400
        )
    franjas = repos.guardar_franjas_config(
        datos["matutino_inicio"],
        datos["matutino_fin"],
        datos["vespertino_inicio"],
        datos["vespertino_fin"],
    )
    return JSONResponse({"franjas": franjas})


# --------------------------------------------------------------------------- #
# Franjas POR SEMANA (#XYZ "Mundial"): CRUD de `rota_franjas` por `lunes`        #
# --------------------------------------------------------------------------- #


async def listar_franjas_de_semana(request: Request) -> Response:
    """GET /api/rota/semana/{lunes}/franjas: las franjas vivas de esa semana.

    Siembra por defecto (Mañana, Tarde, Descanso) si la semana aun no tiene franjas.
    """
    lunes = dominio.lunes_de_semana_iso(request.path_params["lunes"])
    if not lunes:
        return JSONResponse(
            {"error": "Indica un lunes válido (AAAA-MM-DD)."}, status_code=400
        )
    franjas, _por_id = _franjas_de_semana(lunes)
    return JSONResponse({"franjas": [_franja_semana_a_dict(f) for f in franjas]})


async def crear_franja_de_semana(request: Request) -> Response:
    """POST /api/rota/semana/{lunes}/franjas: anade una franja extra a la semana.

    Cuerpo: `{nombre, inicio, fin, orden?, es_descanso?}`. Solo admin (la rejilla es
    editorial). Devuelve 409 si ya existe una franja con el mismo nombre en esa semana
    (UNIQUE `(lunes, nombre)`).
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un admin puede crear franjas de la semana."}, status_code=403
        )
    lunes = dominio.lunes_de_semana_iso(request.path_params["lunes"])
    if not lunes:
        return JSONResponse(
            {"error": "Indica un lunes válido (AAAA-MM-DD)."}, status_code=400
        )
    datos = await leer_json(request)
    nombre = str(datos.get("nombre", "")).strip()
    inicio = str(datos.get("inicio", "")).strip()
    fin = str(datos.get("fin", "")).strip()
    orden = datos.get("orden", 0)
    es_descanso = bool(datos.get("es_descanso", False))
    if not nombre:
        return JSONResponse(
            {"error": "Indica el `nombre` de la franja."}, status_code=400
        )
    if not _hhmm_valido(inicio) or not _hhmm_valido(fin):
        return JSONResponse(
            {"error": "`inicio` y `fin` deben ser HH:MM (00:00..24:00)."},
            status_code=400,
        )
    try:
        orden_int = int(orden)
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "`orden` debe ser un entero."}, status_code=400
        )
    creada = repos.crear_franja_semana(
        lunes, nombre, inicio, fin, orden=orden_int, es_descanso=es_descanso
    )
    if creada is None:
        return JSONResponse(
            {"error": f"Ya hay una franja llamada «{nombre}» en esa semana."},
            status_code=409,
        )
    return JSONResponse(_franja_semana_a_dict(creada), status_code=201)


async def actualizar_franja_de_semana(request: Request) -> Response:
    """PATCH /api/rota/franjas/{franja_id}: edita nombre/rangos/orden de una franja.

    Solo admin. `es_descanso` NO se edita despues de crear (cambio de semantica del dato
    en turnos existentes; si quieres una franja de descanso, borra y crea una nueva).
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un admin puede editar franjas de la semana."}, status_code=403
        )
    franja_id = request.path_params["franja_id"]
    datos = await leer_json(request) or {}
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nombre = str(datos.get("nombre", "")).strip()
        if not nombre:
            return JSONResponse(
                {"error": "`nombre` no puede estar vacío."}, status_code=400
            )
        campos["nombre"] = nombre
    for clave in ("inicio", "fin"):
        if clave in datos:
            valor = str(datos.get(clave, "")).strip()
            if not _hhmm_valido(valor):
                return JSONResponse(
                    {"error": f"`{clave}` debe ser HH:MM (00:00..24:00)."},
                    status_code=400,
                )
            campos[clave] = valor
    if "orden" in datos:
        try:
            campos["orden"] = int(datos["orden"])
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "`orden` debe ser un entero."}, status_code=400
            )
    if not campos:
        return JSONResponse(
            {"error": "Indica al menos un campo a editar."}, status_code=400
        )
    actualizada = repos.actualizar_franja_semana(franja_id, campos)
    if actualizada is None:
        return JSONResponse(
            {"error": "La franja no existe o el cambio rompe la unicidad por nombre."},
            status_code=404,
        )
    return JSONResponse(_franja_semana_a_dict(actualizada))


# --------------------------------------------------------------------------- #
# Coordinador por turno (ola "coord")                                          #
# --------------------------------------------------------------------------- #
#
# Cada celda (fecha, franja_id) puede tener UN coordinador asignado entre los usuarios
# con `puede_coordinar=true`. La coordinacion es INDEPENDIENTE de los turnos de CM:
# borrar un turno o cambiar franja no la afecta. Si la semana esta aprobada, los CMs
# siguen viendo el badge (read-only); solo el admin puede editar.


async def listar_coordinacion_de_semana(request: Request) -> Response:
    """GET /api/rota/semana/{lunes}/coordinacion: coordinador por celda de la semana.

    Devuelve `{coordinacion: [{fecha, franja_id, coordinador_id, coordinador_nombre}]}`.
    El nombre se resuelve por lookup contra el equipo COMPLETO (no solo `cobertura`):
    asi un coordinador asignado que luego pierde el flag `puede_coordinar` sigue
    saliendo con su nombre (el front lo muestra; el admin decide si cambiarlo).
    """
    lunes = dominio.lunes_de_semana_iso(request.path_params["lunes"])
    if not lunes:
        return JSONResponse(
            {"error": "Indica un lunes válido (AAAA-MM-DD)."}, status_code=400
        )
    nombres = _nombres_equipo()
    coordinacion = repos.listar_coordinacion_semana(lunes)
    return JSONResponse(
        {
            "lunes": lunes,
            "coordinacion": [
                {
                    "fecha": c["fecha"],
                    "franja_id": c["franja_id"],
                    "coordinador_id": c["coordinador_id"],
                    "coordinador_nombre": nombres.get(c["coordinador_id"], ""),
                }
                for c in coordinacion
            ],
        }
    )


def _candidato_a_coordinador(usuario_id: str) -> bool:
    """True si el usuario existe y tiene `puede_coordinar=true`."""
    u = auth.obtener_usuario_por_id(usuario_id)
    return bool(u and u.get("puede_coordinar"))


async def set_coordinador_de_celda(request: Request) -> Response:
    """PUT /api/rota/coordinacion: asigna un coordinador a (fecha, franja_id).

    Cuerpo: `{lunes, fecha, franja_id, coordinador_id}`. Solo admin. Valida que el
    coordinador tenga `puede_coordinar=true`. Devuelve el registro upsertado con
    `coordinador_nombre` resuelto.
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un admin puede asignar el coordinador."}, status_code=403
        )
    datos = await leer_json(request)
    lunes_crudo = str(datos.get("lunes", "")).strip()
    fecha = str(datos.get("fecha", "")).strip()
    franja_id = str(datos.get("franja_id", "")).strip()
    coordinador_id = str(datos.get("coordinador_id", "")).strip()
    lunes = dominio.lunes_de_semana_iso(lunes_crudo) if lunes_crudo else ""
    if not lunes:
        return JSONResponse(
            {"error": "Indica el `lunes` de la semana (AAAA-MM-DD)."}, status_code=400
        )
    if not _fecha_valida(fecha):
        return JSONResponse(
            {"error": "Indica una `fecha` válida (AAAA-MM-DD)."}, status_code=400
        )
    if not franja_id:
        return JSONResponse(
            {"error": "Indica la `franja_id`."}, status_code=400
        )
    if not coordinador_id:
        return JSONResponse(
            {"error": "Indica el `coordinador_id`."}, status_code=400
        )
    if not _candidato_a_coordinador(coordinador_id):
        return JSONResponse(
            {
                "error": (
                    "El usuario indicado no es candidato a coordinador "
                    "(necesita `puede_coordinar=true`)."
                )
            },
            status_code=400,
        )
    registro = repos.set_coordinador_rota(lunes, fecha, franja_id, coordinador_id)
    nombres = _nombres_equipo()
    return JSONResponse(
        {
            "fecha": registro["fecha"],
            "franja_id": registro["franja_id"],
            "coordinador_id": registro["coordinador_id"],
            "coordinador_nombre": nombres.get(registro["coordinador_id"], ""),
        }
    )


async def quitar_coordinador_de_celda(request: Request) -> Response:
    """DELETE /api/rota/coordinacion: borra el coordinador de (fecha, franja_id).

    Cuerpo: `{fecha, franja_id}`. Solo admin. Idempotente: 200 incluso si no habia.
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un admin puede quitar el coordinador."}, status_code=403
        )
    datos = await leer_json(request) or {}
    fecha = str(datos.get("fecha", "")).strip()
    franja_id = str(datos.get("franja_id", "")).strip()
    if not _fecha_valida(fecha):
        return JSONResponse(
            {"error": "Indica una `fecha` válida (AAAA-MM-DD)."}, status_code=400
        )
    if not franja_id:
        return JSONResponse(
            {"error": "Indica la `franja_id`."}, status_code=400
        )
    borrado = repos.quitar_coordinador_rota(fecha, franja_id)
    return JSONResponse({"ok": True, "borrado": borrado})


async def borrar_franja_de_semana(request: Request) -> Response:
    """DELETE /api/rota/franjas/{franja_id}[?forzar=true]: borra una franja.

    Si hay turnos asociados y no se pasa `?forzar=true`, devuelve 409 con el conteo. Con
    `?forzar=true`, borra los turnos en cascada y la franja despues. Solo admin.
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un admin puede borrar franjas de la semana."}, status_code=403
        )
    franja_id = request.path_params["franja_id"]
    forzar = (request.query_params.get("forzar") or "").strip().lower() in (
        "1",
        "true",
        "sí",
        "si",
    )
    resultado = repos.borrar_franja_semana(franja_id, forzar=forzar)
    if not resultado["borrada"] and resultado["turnos_asociados"] > 0:
        return JSONResponse(
            {
                "error": (
                    f"Tiene {resultado['turnos_asociados']} turnos asociados. "
                    "Repite con `?forzar=true` para borrar la franja y sus turnos."
                ),
                "turnos_asociados": resultado["turnos_asociados"],
            },
            status_code=409,
        )
    if not resultado["borrada"]:
        return JSONResponse({"error": "La franja no existe."}, status_code=404)
    return JSONResponse(
        {"ok": True, "turnos_borrados": resultado["turnos_borrados"]}
    )


RUTAS = [
    Route("/api/rota/equipo", equipo, methods=["GET"]),
    # Eventos / transmisiones.
    Route("/api/rota/eventos", listar_eventos, methods=["GET"]),
    Route("/api/rota/eventos", crear_evento, methods=["POST"]),
    Route("/api/rota/eventos/{evento_id}", actualizar_evento, methods=["PATCH"]),
    Route("/api/rota/eventos/{evento_id}", borrar_evento, methods=["DELETE"]),
    Route("/api/rota/eventos/{evento_id}/duplicar", duplicar_evento, methods=["POST"]),
    # Turnos (horario persona×dia×franja). OJO: las rutas de lote DEBEN ir ANTES que las
    # paramétricas `{turno_id}`, si no Starlette captura "lote"/"lote/borrar"/"aprobar" como
    # id de turno y devuelve 404/405.
    Route("/api/rota/turnos/lote", crear_turnos_lote, methods=["POST"]),
    Route("/api/rota/turnos/lote", actualizar_turnos_lote, methods=["PATCH"]),
    Route("/api/rota/turnos/lote/borrar", borrar_turnos_lote, methods=["POST"]),
    Route("/api/rota/turnos/aprobar", aprobar_turnos, methods=["POST"]),
    Route("/api/rota/turnos/despublicar", despublicar_turnos, methods=["POST"]),
    Route("/api/rota/turnos", turnos_semana, methods=["GET"]),
    Route("/api/rota/turnos", crear_turno, methods=["POST"]),
    Route("/api/rota/turnos/{turno_id}/duplicar", duplicar_turno, methods=["POST"]),
    Route("/api/rota/turnos/{turno_id}", actualizar_turno, methods=["PATCH"]),
    Route("/api/rota/turnos/{turno_id}", borrar_turno, methods=["DELETE"]),
    Route("/api/rota/mis-turnos", mis_turnos, methods=["GET"]),
    # Franjas POR SEMANA ("Mundial"): cada lunes tiene sus franjas (Mañana/Tarde/Descanso
    # por defecto, configurables con N franjas y solapes permitidos).
    Route("/api/rota/semana/{lunes}/franjas", listar_franjas_de_semana, methods=["GET"]),
    Route("/api/rota/semana/{lunes}/franjas", crear_franja_de_semana, methods=["POST"]),
    Route("/api/rota/franjas/{franja_id}", actualizar_franja_de_semana, methods=["PATCH"]),
    Route("/api/rota/franjas/{franja_id}", borrar_franja_de_semana, methods=["DELETE"]),
    # Coordinador por turno (ola "coord"): cada celda (fecha, franja_id) puede tener UN
    # coordinador asignado entre usuarios con `puede_coordinar=true`.
    Route("/api/rota/semana/{lunes}/coordinacion", listar_coordinacion_de_semana, methods=["GET"]),
    Route("/api/rota/coordinacion", set_coordinador_de_celda, methods=["PUT"]),
    Route("/api/rota/coordinacion", quitar_coordinador_de_celda, methods=["DELETE"]),
    # Cobertura DERIVADA (vista, sin persistencia).
    Route("/api/rota/cobertura", cobertura_semana, methods=["GET"]),
    Route("/api/rota/cobertura/evento/{evento_id}", cobertura_evento, methods=["GET"]),
    # Ausencias / vacaciones.
    Route("/api/rota/ausencias", listar_ausencias, methods=["GET"]),
    Route("/api/rota/ausencias", crear_ausencia, methods=["POST"]),
    Route("/api/rota/ausencias/{ausencia_id}", actualizar_ausencia, methods=["PATCH"]),
    Route("/api/rota/ausencias/{ausencia_id}", borrar_ausencia, methods=["DELETE"]),
    # Copia de semana + panel de carga.
    Route("/api/rota/copiar-semana", copiar_semana, methods=["POST"]),
    Route("/api/rota/carga", carga_semana, methods=["GET"]),
    # Exports.
    Route("/api/rota/export.csv", export_csv, methods=["GET"]),
    Route("/api/rota/export.xlsx", export_xlsx, methods=["GET"]),
    # Piezas de la parrilla (#150 PARRILLA 2026.xlsx): un POST individual por fila.
    Route("/api/rota/piezas", listar_piezas, methods=["GET"]),
    Route("/api/rota/piezas", crear_pieza, methods=["POST"]),
    # OJO: borrado en lote ANTES que las paramétricas `{pieza_id}` (Starlette captura
    # "lote/borrar" antes de la regex de id si va arriba).
    Route("/api/rota/piezas/lote/borrar", borrar_piezas_lote, methods=["POST"]),
    Route("/api/rota/piezas/{pieza_id}", actualizar_pieza, methods=["PATCH"]),
    Route("/api/rota/piezas/{pieza_id}", borrar_pieza, methods=["DELETE"]),
    # Duplicar una pieza (workflow reset; ver `duplicar_pieza_rota` en db.py).
    Route("/api/rota/piezas/{pieza_id}/duplicar", duplicar_pieza, methods=["POST"]),
    # Catálogo de programas evergreen (#150). Renombrar hace cascada sobre rota_piezas.
    Route("/api/rota/programas", listar_programas, methods=["GET"]),
    Route("/api/rota/programas", crear_programa, methods=["POST"]),
    Route("/api/rota/programas/{programa_id}", actualizar_programa, methods=["PATCH"]),
    Route("/api/rota/programas/{programa_id}", borrar_programa, methods=["DELETE"]),
    # Solicitudes de cambio de turno entre companeros (#175).
    Route("/api/rota/swaps", listar_swaps, methods=["GET"]),
    Route("/api/rota/swaps", crear_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/aceptar", aceptar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/rechazar", rechazar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/aprobar", aprobar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/rechazar-admin", rechazar_swap_admin, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/cancelar", cancelar_swap, methods=["POST"]),
    # Configuración editorial de FRANJAS de cobertura (#185). GET libre; PATCH solo admin.
    Route("/api/rota/config/franjas", obtener_config_franjas, methods=["GET"]),
    Route("/api/rota/config/franjas", guardar_config_franjas, methods=["PATCH"]),
]

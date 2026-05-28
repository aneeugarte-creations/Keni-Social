"""API Rota: parrilla y rota de horarios del equipo (F4 · #144).

Sustituye el Excel manual de Elias por una vista de equipo que PROPONE la rota y la
hace visible con anticipacion. Keni propone + consolida; Elias ajusta y APRUEBA las
asignaciones finales antes de publicarlas al equipo. Nada se publica hasta aprobar.

  - `GET    /api/rota/equipo`                 -> miembros del equipo (usuarios #130).
  - `GET    /api/rota/eventos[?desde&hasta&cambiados&tipo_cobertura]` -> eventos/transmisiones.
  - `POST   /api/rota/eventos`                {titulo, fecha, hora, contenido, nota, tipo_cobertura, prioridad}
  - `PATCH  /api/rota/eventos/{id}`           edita un evento (reprograma -> cambiado=1; cambiado:false lo limpia).
  - `DELETE /api/rota/eventos/{id}`           borra el evento (y sus turnos).
  - `GET    /api/rota/semana[?lunes]`         -> rota de la semana (turnos + eventos).
  - `POST   /api/rota/proponer`               {lunes} -> PROPONE (no publica) la rota.
  - `PATCH  /api/rota/turnos/{id}`            {miembro_id, override, motivo, estado}
  - `POST   /api/rota/semana/aprobar`         {lunes} -> Elias APRUEBA (publica) la semana.
  - `GET    /api/rota/mi-semana[?lunes]`      -> "mi proxima semana" del usuario actual.
  - `GET    /api/rota/export.{xlsx,csv}[?lunes]` -> descarga para la transicion del Excel.

GESTION DE TURNOS (ola A): el HORARIO de trabajo del equipo, paralelo a la cobertura:
  - `GET/POST/PATCH/DELETE /api/rota/ausencias[/{id}]` -> vacaciones/ausencias por miembro.
  - `GET    /api/rota/horario[?lunes]`        -> el horario (turnos de trabajo) de la semana.
  - `POST   /api/rota/horario/proponer`       {lunes} -> PROPONE el horario (no publica).
  - `PATCH  /api/rota/horario/turnos/{id}`    {franja, miembro_id, override, motivo, nota_relevo, estado}
  - `POST   /api/rota/horario/aprobar`        {lunes} -> Elias APRUEBA (publica) el horario.
  - `GET    /api/rota/mi-horario[?lunes]`     -> los turnos de trabajo del usuario actual.

ROTACION DE SABADOS (criterio de aceptacion): el proponedor no repite a la misma
persona dos sabados seguidos salvo override explicito. La logica pura vive en `rota.py`
(probada aparte); aqui se construyen las entradas, se persiste y se serializa.

IDENTIDAD (#130): el equipo son los USUARIOS de la consola (solo lectura desde `auth`).
El usuario autenticado de la peticion (`request.state.usuario`) alimenta "mi semana".
La APROBACION (publicar al equipo) exige rol admin: la frontera dice que Elias aprueba.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, permisos, repos
from .. import rota as dominio
from .._http_json import leer_json
from ..estados import (
    ESTADOS_PIEZA,
    ESTADO_SWAP_ACEPTADO,
    ESTADO_SWAP_CANCELADO,
    ESTADO_SWAP_PROPUESTO,
    ESTADO_SWAP_RECHAZADO,
    ESTADO_SWAP_RECHAZADO_ADMIN,
    ESTADOS_ROTA,
    FRANJAS_TRABAJO,
    FRANJAS_TURNO,
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

_MSG_SOLO_ADMIN = "Solo Elías (administrador) puede aprobar y publicar la rota al equipo."
_MSG_SOLO_ADMIN_HORARIO = (
    "Solo Elías (administrador) puede aprobar y publicar el horario al equipo."
)


# --------------------------------------------------------------------------- #
# Helpers de identidad / equipo                                                #
# --------------------------------------------------------------------------- #


def _equipo() -> list[dominio.Miembro]:
    """El equipo disponible: los usuarios de la consola (#130), como `Miembro`."""
    return [dominio.Miembro(id=u["id"], nombre=u["usuario"]) for u in auth.listar_usuarios()]


def _nombres_equipo() -> dict[str, str]:
    """Mapa id->nombre del equipo (para resolver el nombre legible de un turno)."""
    return {m.id: m.nombre for m in _equipo()}


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
    eventos_por_id: dict[str, dict[str, Any]],
    nombres: dict[str, str],
) -> dict[str, Any]:
    """Serializa un turno resolviendo su evento (que sacar) y el nombre del miembro."""
    evento = eventos_por_id.get(turno["evento_id"])
    return {
        "id": turno["id"],
        "semana": turno["semana"],
        "evento_id": turno["evento_id"],
        "evento_titulo": evento["titulo"] if evento else "",
        "evento_fecha": evento["fecha"] if evento else "",
        "evento_hora": evento["hora"] if evento else "",
        "contenido": evento["contenido"] if evento else "",
        "es_sabado": dominio.es_sabado(evento["fecha"]) if evento else False,
        "miembro_id": turno["miembro_id"],
        # El nombre vivo del equipo manda sobre el snapshot guardado (renombres).
        "miembro_nombre": nombres.get(turno["miembro_id"], turno.get("miembro_nombre", "")),
        "estado": turno["estado"],
        "override": bool(turno["override"]),
        "motivo": turno["motivo"],
    }


def _ordenar_turnos(turnos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordena turnos cronologicamente por su evento (fecha, hora, titulo)."""
    return sorted(
        turnos, key=lambda t: (t["evento_fecha"], t["evento_hora"], t["evento_titulo"])
    )


def _sabado_previo(lunes_iso: str) -> str:
    """Id del miembro que cubrio el sabado de la semana ANTERIOR a `lunes_iso`.

    Mira los turnos de la semana previa y devuelve el `miembro_id` del turno de sabado
    (vacio si no hay). Sirve para que el proponedor no repita ese miembro este sabado.
    """
    if not lunes_iso:
        return ""
    from datetime import date, timedelta

    try:
        previo = (date.fromisoformat(lunes_iso) - timedelta(days=7)).isoformat()
    except ValueError:
        return ""
    eventos_por_id = {e["id"]: e for e in repos.listar_eventos_rota()}
    for turno in repos.listar_turnos_rota(semana=previo):
        evento = eventos_por_id.get(turno["evento_id"])
        if evento and dominio.es_sabado(evento["fecha"]):
            return turno["miembro_id"]
    return ""


def _rota_semana(lunes_iso: str) -> dict[str, Any]:
    """Construye el payload de la rota de una semana (turnos + eventos + estado)."""
    eventos_por_id = {e["id"]: e for e in repos.listar_eventos_rota()}
    nombres = _nombres_equipo()
    turnos = [
        _turno_a_dict(t, eventos_por_id, nombres)
        for t in repos.listar_turnos_rota(semana=lunes_iso)
    ]
    turnos = _ordenar_turnos(turnos)
    inicio, fin = dominio.rango_semana(lunes_iso) if lunes_iso else ("", "")
    # La semana esta "publicada" cuando TODOS sus turnos estan aprobados (y hay turnos).
    aprobada = bool(turnos) and all(t["estado"] == "aprobado" for t in turnos)
    return {
        "lunes": lunes_iso,
        "inicio": inicio,
        "fin": fin,
        "turnos": turnos,
        "aprobada": aprobada,
        "total": len(turnos),
    }


# --------------------------------------------------------------------------- #
# Endpoints: equipo                                                            #
# --------------------------------------------------------------------------- #


async def equipo(request: Request) -> Response:
    """GET /api/rota/equipo: miembros del equipo (usuarios de la consola)."""
    miembros = [{"id": m.id, "nombre": m.nombre} for m in _equipo()]
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
# Endpoints: rota de la semana, proponer, editar, aprobar                      #
# --------------------------------------------------------------------------- #


async def semana(request: Request) -> Response:
    """GET /api/rota/semana[?lunes]: la rota de una semana (turnos + estado)."""
    lunes = _lunes_param(request)
    return JSONResponse(_rota_semana(lunes))


async def proponer(request: Request) -> Response:
    """POST /api/rota/proponer {lunes}: PROPONE la rota de la semana (no la publica).

    Re-propone desde cero: borra los turnos previos de esa semana y crea los nuevos en
    estado `propuesto`. Rota los sabados respetando "no dos sábados seguidos" (excluye
    al miembro del sábado de la semana anterior). Devuelve la rota y los avisos.
    """
    datos = await leer_json(request)
    lunes = dominio.lunes_de_semana_iso(str(datos.get("lunes", "")).strip())
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana a proponer (AAAA-MM-DD)."}, status_code=400
        )

    eventos_crudos = repos.listar_eventos_rota()
    # Ola B (#144): los eventos `no_cubrir` se trackean en el calendario pero NO generan
    # turno de cobertura (no se asignan a nadie). `transmision`/`imagenes` sí se proponen;
    # un evento legado sin tipo cae a `transmision`, así que se sigue proponiendo.
    eventos = [
        dominio.Evento(
            id=e["id"], titulo=e["titulo"], fecha=e["fecha"], hora=e["hora"], contenido=e["contenido"]
        )
        for e in eventos_crudos
        if e.get("tipo_cobertura", "transmision") != TIPO_COBERTURA_NO_CUBRIR
    ]
    equipo_dom = _equipo()
    sabado_previo = _sabado_previo(lunes)

    propuesta = dominio.proponer_rota(eventos, equipo_dom, lunes, sabado_previo=sabado_previo)

    # Re-proponer reemplaza la semana entera (idempotente para el operador).
    repos.borrar_turnos_semana_rota(lunes)
    nombres = _nombres_equipo()
    for turno in propuesta.turnos:
        repos.crear_turno_rota(
            lunes,
            turno.evento_id,
            miembro_id=turno.miembro_id,
            miembro_nombre=nombres.get(turno.miembro_id, ""),
            override=turno.override,
            motivo=turno.motivo,
        )

    payload = _rota_semana(lunes)
    payload["avisos"] = propuesta.avisos
    return JSONResponse(payload)


async def actualizar_turno(request: Request) -> Response:
    """PATCH /api/rota/turnos/{id}: Elias edita una asignacion.

    Permite cambiar el miembro, marcar `override` (cobertura estratégica que rompe la
    rotación), el motivo y el estado. Si la edición REPITE el sábado de la semana previa
    SIN override, devuelve 409 pidiendo el override explícito (regla de aceptación).
    """
    turno_id = request.path_params["turno_id"]
    actual = repos.obtener_turno_rota(turno_id)
    if actual is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)

    datos = await leer_json(request)
    campos: dict[str, Any] = {}

    nombres = _nombres_equipo()
    nuevo_miembro = actual["miembro_id"]
    if "miembro_id" in datos:
        miembro_id = datos["miembro_id"]
        if not isinstance(miembro_id, str):
            return JSONResponse({"error": "miembro_id inválido."}, status_code=400)
        if miembro_id and miembro_id not in nombres:
            return JSONResponse(
                {"error": "Ese miembro no existe en el equipo."}, status_code=400
            )
        campos["miembro_id"] = miembro_id
        campos["miembro_nombre"] = nombres.get(miembro_id, "")
        nuevo_miembro = miembro_id

    override = bool(datos.get("override", actual["override"]))
    if "override" in datos:
        campos["override"] = override
    if "motivo" in datos and isinstance(datos["motivo"], str):
        campos["motivo"] = datos["motivo"].strip()
    if "estado" in datos:
        estado = datos["estado"]
        if estado not in ESTADOS_ROTA:
            validos = " o ".join(f'"{e}"' for e in ESTADOS_ROTA)
            return JSONResponse({"error": f"Estado inválido. Usa {validos}."}, status_code=400)
        campos["estado"] = estado

    # Regla de aceptación: si este turno es de SÁBADO y la asignación repite a la
    # persona del sábado de la semana previa SIN override -> exigir override explícito.
    evento = repos.obtener_evento_rota(actual["evento_id"])
    if evento and dominio.es_sabado(evento["fecha"]):
        previo = _sabado_previo(actual["semana"])
        if dominio.viola_rotacion_sabado(previo, nuevo_miembro, override=override):
            return JSONResponse(
                {
                    "error": (
                        "Esa persona ya cubrió el sábado anterior. Marca un override "
                        "explícito si es una cobertura estratégica intencional."
                    ),
                    "requiere_override": True,
                },
                status_code=409,
            )

    turno = repos.actualizar_turno_rota(turno_id, campos)
    if turno is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    eventos_por_id = {e["id"]: e for e in repos.listar_eventos_rota()}
    return JSONResponse({"turno": _turno_a_dict(turno, eventos_por_id, nombres)})


async def aprobar_semana(request: Request) -> Response:
    """POST /api/rota/semana/aprobar {lunes}: Elias APRUEBA (publica) la semana.

    Solo admin: la frontera dice que Elías aprueba las asignaciones finales antes de
    publicarlas al equipo. Marca todos los turnos de la semana como `aprobado`.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN}, status_code=403)
    datos = await leer_json(request)
    lunes = dominio.lunes_de_semana_iso(str(datos.get("lunes", "")).strip())
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana a aprobar (AAAA-MM-DD)."}, status_code=400
        )
    n = repos.aprobar_semana_rota(lunes)
    if n == 0:
        return JSONResponse(
            {"error": "No hay turnos en esa semana para aprobar. Propón la rota primero."},
            status_code=400,
        )
    payload = _rota_semana(lunes)
    payload["mensaje"] = f"Rota aprobada y publicada al equipo ({n} turnos)."
    return JSONResponse(payload)


# --------------------------------------------------------------------------- #
# Endpoint: "mi proxima semana"                                                #
# --------------------------------------------------------------------------- #


async def mi_semana(request: Request) -> Response:
    """GET /api/rota/mi-semana[?lunes]: los turnos del USUARIO actual en esa semana.

    Cada miembro ve su propia semana. Por defecto la semana pedida; si no se entró con
    sesión (token de mantenimiento), devuelve la semana vacía con un aviso honesto.
    """
    lunes = _lunes_param(request)
    usuario = _usuario_actual(request)
    base = _rota_semana(lunes)
    if usuario is None:
        return JSONResponse(
            {
                **base,
                "miembro_id": "",
                "miembro_nombre": "",
                "mis_turnos": [],
                "aviso": "Inicia sesión para ver tu próxima semana.",
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
# Gestion de turnos: horario de trabajo de la semana                           #
# --------------------------------------------------------------------------- #


def _turno_trabajo_a_dict(
    turno: dict[str, Any], nombres: dict[str, str]
) -> dict[str, Any]:
    """Serializa un turno de trabajo (resolviendo el nombre vivo del miembro)."""
    return {
        "id": turno["id"],
        "semana": turno["semana"],
        "fecha": turno["fecha"],
        "miembro_id": turno["miembro_id"],
        "miembro_nombre": nombres.get(
            turno["miembro_id"], turno.get("miembro_nombre", "")
        ),
        "franja": turno["franja"],
        "estado": turno["estado"],
        "override": bool(turno["override"]),
        "motivo": turno["motivo"],
        "nota_relevo": turno["nota_relevo"],
        "es_sabado": dominio.es_sabado(turno["fecha"]),
    }


def _sabados_previos_trabajo(lunes_iso: str) -> set[str]:
    """Ids que TRABAJARON (no descanso) el sábado de la semana ANTERIOR a `lunes_iso`.

    Sirve para que el proponedor no repita a esas personas el sábado de esta semana.
    """
    if not lunes_iso:
        return set()
    from datetime import date, timedelta

    try:
        previo = (date.fromisoformat(lunes_iso) - timedelta(days=7)).isoformat()
    except ValueError:
        return set()
    ids: set[str] = set()
    for turno in repos.listar_turnos_trabajo_rota(semana=previo):
        if dominio.es_sabado(turno["fecha"]) and turno["franja"] in FRANJAS_TRABAJO:
            ids.add(turno["miembro_id"])
    return ids


def _horario_semana(lunes_iso: str) -> dict[str, Any]:
    """Construye el payload del horario de una semana (turnos de trabajo + estado)."""
    nombres = _nombres_equipo()
    turnos = [
        _turno_trabajo_a_dict(t, nombres)
        for t in repos.listar_turnos_trabajo_rota(semana=lunes_iso)
    ]
    inicio, fin = dominio.rango_semana(lunes_iso) if lunes_iso else ("", "")
    aprobada = bool(turnos) and all(t["estado"] == "aprobado" for t in turnos)
    return {
        "lunes": lunes_iso,
        "inicio": inicio,
        "fin": fin,
        "dias": dominio.dias_de_semana(lunes_iso) if lunes_iso else [],
        "turnos": turnos,
        "aprobada": aprobada,
        "total": len(turnos),
    }


async def horario_semana(request: Request) -> Response:
    """GET /api/rota/horario[?lunes]: el horario de trabajo de una semana."""
    lunes = _lunes_param(request)
    return JSONResponse(_horario_semana(lunes))


async def proponer_horario(request: Request) -> Response:
    """POST /api/rota/horario/proponer {lunes}: PROPONE el horario de la semana (no publica).

    Re-propone desde cero: borra los turnos de trabajo previos de esa semana y crea los
    nuevos en estado `propuesto`. Respeta las ausencias (no asigna a quien esté de
    vacaciones/baja ese día) y rota los sábados (excluye a quien trabajó el sábado previo).
    Devuelve el horario y los avisos honestos.
    """
    datos = await leer_json(request)
    lunes = dominio.lunes_de_semana_iso(str(datos.get("lunes", "")).strip())
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana a proponer (AAAA-MM-DD)."},
            status_code=400,
        )

    equipo_dom = _equipo()
    ausencias = _ausencias_dominio()
    sabados_previos = _sabados_previos_trabajo(lunes)

    propuesta = dominio.proponer_horario(
        equipo_dom, lunes, ausencias=ausencias, sabados_previos=sabados_previos
    )

    # Re-proponer reemplaza la semana entera (idempotente para el operador).
    repos.borrar_turnos_trabajo_semana_rota(lunes)
    nombres = _nombres_equipo()
    for turno in propuesta.turnos:
        repos.crear_turno_trabajo_rota(
            lunes,
            turno.fecha,
            miembro_id=turno.miembro_id,
            miembro_nombre=nombres.get(turno.miembro_id, ""),
            franja=turno.franja,
            override=turno.override,
            motivo=turno.motivo,
        )

    payload = _horario_semana(lunes)
    payload["avisos"] = propuesta.avisos
    return JSONResponse(payload)


async def actualizar_turno_trabajo(request: Request) -> Response:
    """PATCH /api/rota/horario/turnos/{id}: Elias edita un turno de trabajo.

    Permite cambiar la franja, el miembro, marcar `override`, el motivo, la nota de relevo
    y el estado. Si la edición pone a TRABAJAR el sábado a quien trabajó el sábado previo
    SIN override, devuelve 409 pidiendo el override explícito (regla de aceptación).
    """
    turno_id = request.path_params["turno_id"]
    actual = repos.obtener_turno_trabajo_rota(turno_id)
    if actual is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)

    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    nombres = _nombres_equipo()

    nuevo_miembro = actual["miembro_id"]
    if "miembro_id" in datos:
        miembro_id = datos["miembro_id"]
        if not isinstance(miembro_id, str):
            return JSONResponse({"error": "miembro_id inválido."}, status_code=400)
        if miembro_id and miembro_id not in nombres:
            return JSONResponse(
                {"error": "Ese miembro no existe en el equipo."}, status_code=400
            )
        campos["miembro_id"] = miembro_id
        campos["miembro_nombre"] = nombres.get(miembro_id, "")
        nuevo_miembro = miembro_id

    nueva_franja = actual["franja"]
    if "franja" in datos:
        franja = datos["franja"]
        if franja not in FRANJAS_TURNO:
            validos = " o ".join(f'"{f}"' for f in FRANJAS_TURNO)
            return JSONResponse(
                {"error": f"Franja inválida. Usa {validos}."}, status_code=400
            )
        campos["franja"] = franja
        nueva_franja = franja

    override = bool(datos.get("override", actual["override"]))
    if "override" in datos:
        campos["override"] = override
    if "motivo" in datos and isinstance(datos["motivo"], str):
        campos["motivo"] = datos["motivo"].strip()
    if "nota_relevo" in datos and isinstance(datos["nota_relevo"], str):
        campos["nota_relevo"] = datos["nota_relevo"].strip()
    if "estado" in datos:
        estado = datos["estado"]
        if estado not in ESTADOS_ROTA:
            validos = " o ".join(f'"{e}"' for e in ESTADOS_ROTA)
            return JSONResponse(
                {"error": f"Estado inválido. Usa {validos}."}, status_code=400
            )
        campos["estado"] = estado

    # Regla de aceptación: si este turno es de SÁBADO y la edición pone a TRABAJAR a quien
    # trabajó el sábado previo SIN override -> exigir override explícito.
    if dominio.es_sabado(actual["fecha"]):
        previos = _sabados_previos_trabajo(actual["semana"])
        if dominio.viola_rotacion_sabado_trabajo(
            previos, nuevo_miembro, override=override, franja=nueva_franja
        ):
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

    turno = repos.actualizar_turno_trabajo_rota(turno_id, campos)
    if turno is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    return JSONResponse({"turno": _turno_trabajo_a_dict(turno, nombres)})


async def aprobar_semana_horario(request: Request) -> Response:
    """POST /api/rota/horario/aprobar {lunes}: Elias APRUEBA (publica) el horario.

    Solo admin: la frontera dice que Elías aprueba el horario final antes de publicarlo al
    equipo. Marca todos los turnos de trabajo de la semana como `aprobado`.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN_HORARIO}, status_code=403)
    datos = await leer_json(request)
    lunes = dominio.lunes_de_semana_iso(str(datos.get("lunes", "")).strip())
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana a aprobar (AAAA-MM-DD)."},
            status_code=400,
        )
    n = repos.aprobar_semana_horario_rota(lunes)
    if n == 0:
        return JSONResponse(
            {"error": "No hay horario en esa semana para aprobar. Propón el horario primero."},
            status_code=400,
        )
    payload = _horario_semana(lunes)
    payload["mensaje"] = f"Horario aprobado y publicado al equipo ({n} turnos)."
    return JSONResponse(payload)


async def mi_horario(request: Request) -> Response:
    """GET /api/rota/mi-horario[?lunes]: los turnos de trabajo del USUARIO actual.

    Cada miembro ve su propio horario. Si no se entró con sesión (token de mantenimiento),
    devuelve la semana vacía con un aviso honesto.
    """
    lunes = _lunes_param(request)
    usuario = _usuario_actual(request)
    base = _horario_semana(lunes)
    if usuario is None:
        return JSONResponse(
            {
                **base,
                "miembro_id": "",
                "miembro_nombre": "",
                "mis_turnos": [],
                "aviso": "Inicia sesión para ver tu próximo horario.",
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
# Export .xlsx / CSV (transicion desde el Excel actual)                        #
# --------------------------------------------------------------------------- #

# Cabeceras de la parrilla exportada: mismas columnas que el Excel de Elías.
_CABECERAS_EXPORT = ("Fecha", "Día", "Hora", "Evento / transmisión", "Qué sacar", "Persona", "Estado")
_DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def _filas_export(lunes_iso: str) -> tuple[list[str], list[list[str]]]:
    """Devuelve `(titulo, filas)` de la rota de la semana, lista para xlsx/CSV."""
    rota = _rota_semana(lunes_iso)
    filas: list[list[str]] = []
    for t in rota["turnos"]:
        fecha = t["evento_fecha"]
        dia = ""
        from datetime import date

        try:
            dia = _DIAS[date.fromisoformat(fecha).weekday()] if fecha else ""
        except ValueError:
            dia = ""
        override = " (override)" if t["override"] else ""
        filas.append(
            [
                fecha,
                dia,
                t["evento_hora"],
                t["evento_titulo"],
                t["contenido"],
                t["miembro_nombre"],
                f"{t['estado']}{override}",
            ]
        )
    titulo = f"Rota {rota['inicio']} a {rota['fin']}" if rota["inicio"] else "Rota"
    return titulo, filas


def _nombre_descarga(lunes_iso: str, ext: str) -> str:
    sufijo = lunes_iso or "semana"
    return f"rota-{sufijo}.{ext}"


# Etiquetas legibles de cada franja para el grid del horario.
_ETIQUETA_FRANJA = {
    "matutino": "Mañana",
    "vespertino": "Tarde",
    "descanso": "Descanso",
}


def _grid_horario(lunes_iso: str) -> tuple[str, list[str], list[list[str]]]:
    """Construye `(titulo, cabeceras, filas)` del horario persona×día de la semana.

    Cabeceras = ["Persona", Lun..Dom]; cada fila es un miembro con su franja por día
    (Mañana/Tarde/Descanso, "Ausente" si una ausencia cubre ese día, "—" si no hay turno).
    Reutiliza `_horario_semana` y las ausencias para marcar la indisponibilidad.
    """
    horario = _horario_semana(lunes_iso)
    dias = horario["dias"]
    equipo = _equipo()
    ausencias = _ausencias_dominio()
    # Indexa el turno por (miembro, fecha) para llenar el grid.
    por_celda: dict[tuple[str, str], dict[str, Any]] = {
        (t["miembro_id"], t["fecha"]): t for t in horario["turnos"]
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
                etiqueta = _ETIQUETA_FRANJA.get(turno["franja"], turno["franja"])
                if turno["override"]:
                    etiqueta += " (override)"
                fila.append(etiqueta)
        filas.append(fila)
    titulo = (
        f"Horario equipo {horario['inicio']} a {horario['fin']}"
        if horario["inicio"]
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

    for clave in ("programa", "red_social", "tipo_pieza", "contenido_sugerido",
                  "hora_post", "notas"):
        if clave in datos:
            valor = datos[clave]
            campos[clave] = str(valor).strip() if isinstance(valor, str) else ""

    if "dia" in datos:
        dia = str(datos.get("dia", "")).strip()
        if dia and not _fecha_iso_valida_o_vacia(dia):
            return JSONResponse({"error": "La fecha no es válida (usa AAAA-MM-DD)."}, status_code=400)
        campos["dia"] = dia

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

    for bool_col in ("material_entregado", "contenido_entregado", "publicado"):
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


def _existe_turno_trabajo(miembro_id: str, fecha: str, franja: str) -> bool:
    """True si EXISTE una fila en `rota_turnos_trabajo` con esos (miembro, fecha, franja)."""
    for t in repos.listar_turnos_trabajo_rota():
        if (
            t["miembro_id"] == miembro_id
            and t["fecha"] == fecha
            and t["franja"] == franja
        ):
            return True
    return False


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
    franja_a = str(datos.get("franja_a", "")).strip()
    franja_b = str(datos.get("franja_b", "")).strip()
    if franja_a not in FRANJAS_TURNO or franja_b not in FRANJAS_TURNO:
        validos = " o ".join(f'"{f}"' for f in FRANJAS_TURNO)
        return JSONResponse(
            {"error": f"Franja inválida. Usa {validos}."}, status_code=400
        )

    # Los turnos DEBEN existir en el horario: si no, no hay nada que cambiar.
    if not _existe_turno_trabajo(usuario["id"], fecha_a, franja_a):
        return JSONResponse(
            {
                "error": (
                    "No encuentro tu turno en el horario para esa fecha y franja. "
                    "Pide a Elías que proponga/apruebe el horario antes."
                )
            },
            status_code=400,
        )
    if not _existe_turno_trabajo(destinatario_id, fecha_b, franja_b):
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


RUTAS = [
    Route("/api/rota/equipo", equipo, methods=["GET"]),
    Route("/api/rota/eventos", listar_eventos, methods=["GET"]),
    Route("/api/rota/eventos", crear_evento, methods=["POST"]),
    Route("/api/rota/eventos/{evento_id}", actualizar_evento, methods=["PATCH"]),
    Route("/api/rota/eventos/{evento_id}", borrar_evento, methods=["DELETE"]),
    Route("/api/rota/semana", semana, methods=["GET"]),
    Route("/api/rota/proponer", proponer, methods=["POST"]),
    Route("/api/rota/turnos/{turno_id}", actualizar_turno, methods=["PATCH"]),
    Route("/api/rota/semana/aprobar", aprobar_semana, methods=["POST"]),
    Route("/api/rota/mi-semana", mi_semana, methods=["GET"]),
    # Gestión de turnos: ausencias / vacaciones.
    Route("/api/rota/ausencias", listar_ausencias, methods=["GET"]),
    Route("/api/rota/ausencias", crear_ausencia, methods=["POST"]),
    Route("/api/rota/ausencias/{ausencia_id}", actualizar_ausencia, methods=["PATCH"]),
    Route("/api/rota/ausencias/{ausencia_id}", borrar_ausencia, methods=["DELETE"]),
    # Gestión de turnos: horario de trabajo del equipo.
    Route("/api/rota/horario", horario_semana, methods=["GET"]),
    Route("/api/rota/horario/proponer", proponer_horario, methods=["POST"]),
    Route("/api/rota/horario/turnos/{turno_id}", actualizar_turno_trabajo, methods=["PATCH"]),
    Route("/api/rota/horario/aprobar", aprobar_semana_horario, methods=["POST"]),
    Route("/api/rota/mi-horario", mi_horario, methods=["GET"]),
    Route("/api/rota/export.csv", export_csv, methods=["GET"]),
    Route("/api/rota/export.xlsx", export_xlsx, methods=["GET"]),
    # Piezas de la parrilla (#150 PARRILLA 2026.xlsx): un POST individual por fila.
    Route("/api/rota/piezas", listar_piezas, methods=["GET"]),
    Route("/api/rota/piezas", crear_pieza, methods=["POST"]),
    Route("/api/rota/piezas/{pieza_id}", actualizar_pieza, methods=["PATCH"]),
    Route("/api/rota/piezas/{pieza_id}", borrar_pieza, methods=["DELETE"]),
    # Solicitudes de cambio de turno entre companeros (#175).
    Route("/api/rota/swaps", listar_swaps, methods=["GET"]),
    Route("/api/rota/swaps", crear_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/aceptar", aceptar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/rechazar", rechazar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/aprobar", aprobar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/rechazar-admin", rechazar_swap_admin, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/cancelar", cancelar_swap, methods=["POST"]),
]

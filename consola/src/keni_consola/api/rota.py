"""API Rota: parrilla y rota de horarios del equipo (F4 · #144).

Sustituye el Excel manual de Elias por una vista de equipo que PROPONE la rota y la
hace visible con anticipacion. Keni propone + consolida; Elias ajusta y APRUEBA las
asignaciones finales antes de publicarlas al equipo. Nada se publica hasta aprobar.

  - `GET    /api/rota/equipo`                 -> miembros del equipo (usuarios #130).
  - `GET    /api/rota/eventos[?desde&hasta]`  -> eventos/transmisiones.
  - `POST   /api/rota/eventos`                {titulo, fecha, hora, contenido, nota}
  - `PATCH  /api/rota/eventos/{id}`           edita un evento.
  - `DELETE /api/rota/eventos/{id}`           borra el evento (y sus turnos).
  - `GET    /api/rota/semana[?lunes]`         -> rota de la semana (turnos + eventos).
  - `POST   /api/rota/proponer`               {lunes} -> PROPONE (no publica) la rota.
  - `PATCH  /api/rota/turnos/{id}`            {miembro_id, override, motivo, estado}
  - `POST   /api/rota/semana/aprobar`         {lunes} -> Elias APRUEBA (publica) la semana.
  - `GET    /api/rota/mi-semana[?lunes]`      -> "mi proxima semana" del usuario actual.
  - `GET    /api/rota/export.{xlsx,csv}[?lunes]` -> descarga para la transicion del Excel.

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
from ..estados import ESTADOS_ROTA

# Media types oficiales de un .xlsx (Open XML) y un CSV.
_MEDIA_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEDIA_CSV = "text/csv; charset=utf-8"

_MSG_SOLO_ADMIN = "Solo Elías (administrador) puede aprobar y publicar la rota al equipo."


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


async def listar_eventos(request: Request) -> Response:
    """GET /api/rota/eventos[?desde&hasta]: calendario de eventos/transmisiones."""
    desde = (request.query_params.get("desde") or "").strip() or None
    hasta = (request.query_params.get("hasta") or "").strip() or None
    eventos = repos.listar_eventos_rota(desde=desde, hasta=hasta)
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
    evento = repos.crear_evento_rota(
        titulo.strip(),
        fecha=fecha.strip(),
        hora=str(datos.get("hora", "")).strip(),
        contenido=str(datos.get("contenido", "")).strip(),
        nota=str(datos.get("nota", "")).strip(),
    )
    return JSONResponse({"evento": _evento_a_dict(evento)}, status_code=201)


async def actualizar_evento(request: Request) -> Response:
    """PATCH /api/rota/eventos/{id}: edita un evento."""
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
    eventos = [
        dominio.Evento(
            id=e["id"], titulo=e["titulo"], fecha=e["fecha"], hora=e["hora"], contenido=e["contenido"]
        )
        for e in eventos_crudos
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
    hoja = libro.add_worksheet("Rota")
    fmt_titulo = libro.add_format({"bold": True, "font_size": 14})
    fmt_cabecera = libro.add_format({"bold": True, "bg_color": "#EEEEEE", "border": 1})
    hoja.write(0, 0, titulo, fmt_titulo)
    for col, encabezado in enumerate(_CABECERAS_EXPORT):
        hoja.write(2, col, encabezado, fmt_cabecera)
    for i, fila in enumerate(filas, start=3):
        for col, valor in enumerate(fila):
            hoja.write(i, col, valor)
    anchos = (12, 11, 12, 30, 40, 18, 16)
    for col, ancho in enumerate(anchos):
        hoja.set_column(col, col, ancho)
    libro.close()

    cabecera = f'attachment; filename="{_nombre_descarga(lunes, "xlsx")}"'
    return Response(
        buffer.getvalue(),
        media_type=_MEDIA_XLSX,
        headers={"Content-Disposition": cabecera},
    )


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
    Route("/api/rota/export.csv", export_csv, methods=["GET"]),
    Route("/api/rota/export.xlsx", export_xlsx, methods=["GET"]),
]

"""API Rota · ausencias/vacaciones del equipo (CRUD)."""
from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ... import rota as dominio
from ..._http_json import leer_json
from ...estados import (
    TIPOS_AUSENCIA,
)
from ._comun import _es_admin, _fecha_valida, _nombres_equipo, _usuario_actual

_MSG_SOLO_DUENO = (
    "Solo puedes gestionar tus propias ausencias (o un administrador la de cualquiera)."
)


def _puede_gestionar_ausencia(request: Request, miembro_id: str) -> bool:
    """¿La petición puede crear/editar/borrar una ausencia de `miembro_id`?

    Frontera de permisos (auditoría Turnos jun-2026): el agujero era que cualquier editor
    autenticado mutaba la ausencia de OTRO por API directa. Modelo dueño-o-admin:
      - Con SESIÓN, solo el DUEÑO de la ausencia (su `miembro_id`) o un ADMIN.
      - El token de mantenimiento (operador de confianza, sin usuario de sesión) conserva
        acceso pleno —no es un usuario del equipo, es la credencial de operación—.
    Honra "capacidad, no dependencia": cada quien gestiona LO SUYO sin pedir permiso, y el
    admin/coordinador la de cualquiera; nadie toca la de otro.
    """
    usuario = _usuario_actual(request)
    if usuario is None:  # entró por el token de mantenimiento
        return True
    return usuario["id"] == miembro_id or _es_admin(request)


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
    if not _puede_gestionar_ausencia(request, miembro_id):
        return JSONResponse({"error": _MSG_SOLO_DUENO}, status_code=403)
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
    actual = repos.obtener_ausencia_rota(ausencia_id)
    if actual is None:
        return JSONResponse({"error": "La ausencia ya no existe."}, status_code=404)
    if not _puede_gestionar_ausencia(request, actual["miembro_id"]):
        return JSONResponse({"error": _MSG_SOLO_DUENO}, status_code=403)
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
    """DELETE /api/rota/ausencias/{id}: borra una ausencia (solo su dueño o un admin)."""
    ausencia_id = request.path_params["ausencia_id"]
    actual = repos.obtener_ausencia_rota(ausencia_id)
    if actual is None:
        return JSONResponse({"error": "La ausencia ya no existe."}, status_code=404)
    if not _puede_gestionar_ausencia(request, actual["miembro_id"]):
        return JSONResponse({"error": _MSG_SOLO_DUENO}, status_code=403)
    if not repos.borrar_ausencia_rota(ausencia_id):
        return JSONResponse({"error": "La ausencia ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Ausencia eliminada."})

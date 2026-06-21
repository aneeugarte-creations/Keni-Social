"""API Rota · catálogo de programas evergreen (PARRILLA 2026.xlsx)."""
from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ... import rota as dominio
from ..._http_json import leer_json

_MAX_NOMBRE_PROGRAMA = 200


def _fecha_iso_valida_o_vacia(valor: str) -> bool:
    """True si `valor` es "" (sin fechar) o un AAAA-MM-DD valido."""
    if not valor:
        return True
    return dominio.lunes_de_semana_iso(valor) != ""


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


def _listar_programas(activo: bool | None) -> dict[str, Any]:
    programas = repos.listar_programas_rota(activo=activo)
    return {"programas": [_programa_a_dict(p) for p in programas]}


async def listar_programas(request: Request) -> Response:
    """GET /api/rota/programas[?activo=true|false]: programas del catálogo."""
    activo = _activo_param(request.query_params.get("activo"))
    cuerpo = await run_in_threadpool(_listar_programas, activo)
    return JSONResponse(cuerpo)


def _crear_programa(nombre: str, datos: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    # Unicidad case-insensitive: defensa en profundidad (el UNIQUE del DDL es el ultimo bloqueo).
    if repos.existe_programa_por_nombre(nombre):
        return 409, {"error": "Ya existe un programa con ese nombre.", "programa_existente": True}
    inicio = str(datos.get("inicio", "")).strip()
    fin = str(datos.get("fin", "")).strip()
    if inicio and not _fecha_iso_valida_o_vacia(inicio):
        return 400, {"error": "La fecha de inicio no es válida (usa AAAA-MM-DD)."}
    if fin and not _fecha_iso_valida_o_vacia(fin):
        return 400, {"error": "La fecha de fin no es válida (usa AAAA-MM-DD)."}
    if inicio and fin and fin < inicio:
        return 400, {"error": "La fecha de fin no puede ser anterior a la de inicio."}
    programa = repos.crear_programa_rota(
        nombre,
        descripcion=str(datos.get("descripcion", "")).strip(),
        color=str(datos.get("color", "")).strip(),
        inicio=inicio,
        fin=fin,
        activo=bool(datos.get("activo", True)),
    )
    return 201, {"programa": _programa_a_dict(programa)}


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
    status, cuerpo = await run_in_threadpool(_crear_programa, nombre, datos)
    return JSONResponse(cuerpo, status_code=status)


def _actualizar_programa(programa_id: str, datos: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    actual = repos.obtener_programa_rota(programa_id)
    if actual is None:
        return 404, {"error": "El programa ya no existe."}
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nuevo = datos["nombre"]
        if not isinstance(nuevo, str) or not nuevo.strip():
            return 400, {"error": "El programa necesita un nombre."}
        nuevo = nuevo.strip()
        if len(nuevo) > _MAX_NOMBRE_PROGRAMA:
            return 400, {
                "error": f"El nombre no puede tener más de {_MAX_NOMBRE_PROGRAMA} caracteres."
            }
        # Si el nuevo nombre (case-insensitive) ya existe en OTRO programa -> 409.
        if nuevo.lower() != (actual.get("nombre") or "").lower() and repos.existe_programa_por_nombre(nuevo):
            return 409, {
                "error": "Ya existe un programa con ese nombre.",
                "programa_existente": True,
            }
        campos["nombre"] = nuevo
    for clave in ("descripcion", "color"):
        if clave in datos:
            valor = datos[clave]
            campos[clave] = str(valor).strip() if isinstance(valor, str) else ""
    for fecha_col in ("inicio", "fin"):
        if fecha_col in datos:
            valor = str(datos.get(fecha_col, "")).strip()
            if valor and not _fecha_iso_valida_o_vacia(valor):
                return 400, {"error": f"La fecha de {fecha_col} no es válida (usa AAAA-MM-DD)."}
            campos[fecha_col] = valor
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])
    # Coherencia del rango si quedan ambos extremos.
    nuevo_inicio = campos.get("inicio", actual.get("inicio", ""))
    nuevo_fin = campos.get("fin", actual.get("fin", ""))
    if nuevo_inicio and nuevo_fin and nuevo_fin < nuevo_inicio:
        return 400, {"error": "La fecha de fin no puede ser anterior a la de inicio."}
    programa = repos.actualizar_programa_rota(programa_id, campos)
    if programa is None:
        return 404, {"error": "El programa ya no existe."}
    return 200, {"programa": _programa_a_dict(programa)}


async def actualizar_programa(request: Request) -> Response:
    """PATCH /api/rota/programas/{id}: edita un programa.

    Si cambia `nombre`, hace CASCADA sobre `rota_piezas.programa` (transaccional). El nuevo
    nombre debe ser único case-insensitive (si otro programa ya lo usa, 409).
    """
    programa_id = request.path_params["programa_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_actualizar_programa, programa_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _borrar_programa(programa_id: str, forzar: bool) -> tuple[int, dict[str, Any]]:
    actual = repos.obtener_programa_rota(programa_id)
    if actual is None:
        return 404, {"error": "El programa ya no existe."}
    en_uso = repos.contar_piezas_por_programa(actual["nombre"])
    if en_uso and not forzar:
        return 409, {
            "error": (
                f"El programa «{actual['nombre']}» está en uso por {en_uso} piezas. "
                "Llama con `?forzar=true` para borrarlo igualmente."
            ),
            "en_uso": True,
            "piezas_afectadas": en_uso,
        }
    if not repos.borrar_programa_rota(programa_id):
        return 404, {"error": "El programa ya no existe."}
    return 200, {"mensaje": "Programa eliminado.", "piezas_afectadas": en_uso}


async def borrar_programa(request: Request) -> Response:
    """DELETE /api/rota/programas/{id}[?forzar=true]: borra un programa.

    Si HAY piezas referenciando el programa (por nombre), devuelve 409 con
    `{en_uso: True, piezas_afectadas: N}` salvo que el cliente pase `?forzar=true` (lo
    típico del coordinador de la rota: "ya sé que hay piezas y aun así quiero borrar el catálogo; las
    piezas sueltas seguirán mostrando el nombre textual").
    """
    programa_id = request.path_params["programa_id"]
    forzar = (request.query_params.get("forzar") or "").strip().lower() in (
        "1",
        "true",
        "sí",
        "si",
    )
    status, cuerpo = await run_in_threadpool(_borrar_programa, programa_id, forzar)
    return JSONResponse(cuerpo, status_code=status)

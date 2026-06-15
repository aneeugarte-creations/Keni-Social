"""API Rota · catálogo de programas evergreen (#150, PARRILLA 2026.xlsx)."""
from __future__ import annotations

from typing import Any

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
    # Unicidad case-insensitive: defensa en profundidad (el UNIQUE del DDL es el ultimo bloqueo).
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
    típico del coordinador de la rota: "ya sé que hay piezas y aun así quiero borrar el catálogo; las
    piezas sueltas seguirán mostrando el nombre textual").
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

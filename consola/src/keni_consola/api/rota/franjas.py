"""API Rota · config de franjas, franjas por semana y coordinacion por celda."""
from __future__ import annotations

import re
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import auth, marcas, repos
from ... import rota as dominio
from ..._http_json import leer_json
from ._comun import (
    _es_admin,
    _fecha_valida,
    _franja_semana_a_dict,
    _franjas_de_semana,
    _hhmm_valido,
    _marca_param,
    _nombres_equipo,
)

_PATRON_HORA = re.compile(r"^([01]?\d|2[0-4]):([0-5]\d)$")

# Nombre RESERVADO: "Descanso" lo añade siempre la siembra de la semana (es estructural, con
# `es_descanso=true`), así que no puede formar parte de la plantilla editable. Coincide con
# `migraciones_modelo._NOMBRE_FRANJA_DESCANSO`.
_NOMBRE_FRANJA_DESCANSO = "Descanso"


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
    """GET /api/rota/config/franjas[?marca]: PLANTILLA de franjas de la marca (lista flexible).

    GRID POR MARCA: la plantilla es por marca; `?marca=` elige cuál. En "Todas" (sin marca)
    devuelve la plantilla por defecto del dominio. Forma:
    `{franjas: [{nombre, inicio, fin}, ...], mostrar_horas_equipo: bool, actualizado}` — con
    la lista se siembra cada semana NUEVA (la franja "Descanso" la añade aparte la siembra);
    `mostrar_horas_equipo` (default false) decide si el calendario de Turnos pinta el rango
    horario junto a la franja en la vista "Equipo".
    """
    marca, error = _marca_param(request)
    if error is not None:
        return error
    plantilla = await run_in_threadpool(repos.obtener_plantilla_franjas, marca or "")
    return JSONResponse(plantilla)


async def guardar_config_franjas(request: Request) -> Response:
    """PATCH /api/rota/config/franjas: actualiza la PLANTILLA de franjas y/o sus ajustes (admin).

    Cuerpo PARCIAL — `franjas` y `mostrar_horas_equipo` son ambos OPCIONALES (debe llegar al
    menos uno):
      - `franjas: [{nombre, inicio, fin}, ...]` en `HH:MM`. Lista flexible (2, 3 o N franjas:
        p. ej. añadir "Nocturna"); con ella se siembra cada semana NUEVA. Reglas: al menos una
        franja; cada una con nombre, `inicio` y `fin` válidos e `inicio < fin`; nombres únicos
        (la siembra usa el nombre como clave); "Descanso" NO se admite (lo añade la siembra).
        Los rangos PUEDEN solaparse: la cobertura (`franjas_activas_en`) hace UNION.
      - `mostrar_horas_equipo: bool`: si el calendario de Turnos pinta el rango horario junto a
        la franja en la vista "Equipo".
    Solo se toca lo que llega: con solo el toggle, las franjas guardadas se conservan; con solo
    `franjas`, el toggle no cambia. Devuelve la forma del GET.
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un admin puede editar la plantilla de franjas."},
            status_code=403,
        )
    # GRID POR MARCA: la plantilla es por marca; editar exige una marca concreta (no "Todas").
    marca, error = _marca_param(request)
    if error is not None:
        return error
    if not marca:
        return JSONResponse(
            {"error": "Elige una marca concreta para editar su plantilla de franjas."},
            status_code=400,
        )
    datos = await leer_json(request) or {}
    tiene_franjas = "franjas" in datos
    tiene_toggle = "mostrar_horas_equipo" in datos
    tiene_tiempo_libre = "tiempo_libre_activo" in datos
    if not tiene_franjas and not tiene_toggle and not tiene_tiempo_libre:
        return JSONResponse(
            {
                "error": "Indica `franjas` (lista), `mostrar_horas_equipo` (bool) "
                "y/o `tiempo_libre_activo` (bool) a editar."
            },
            status_code=400,
        )
    limpias: list[dict[str, str]] | None = None
    if tiene_franjas:
        crudo = datos.get("franjas")
        if not isinstance(crudo, list) or not crudo:
            return JSONResponse(
                {"error": "`franjas` debe ser una lista con al menos una franja."},
                status_code=400,
            )
        limpias = []
        vistos: set[str] = set()
        for i, item in enumerate(crudo):
            if not isinstance(item, dict):
                return JSONResponse(
                    {"error": f"La franja #{i + 1} no es válida."}, status_code=400
                )
            nombre = str(item.get("nombre", "")).strip()
            inicio = str(item.get("inicio", "")).strip()
            fin = str(item.get("fin", "")).strip()
            if not nombre:
                return JSONResponse(
                    {"error": f"La franja #{i + 1} necesita un nombre."}, status_code=400
                )
            if nombre.casefold() == _NOMBRE_FRANJA_DESCANSO.casefold():
                return JSONResponse(
                    {
                        "error": f"«{_NOMBRE_FRANJA_DESCANSO}» se añade sola; "
                        "no la pongas en la plantilla."
                    },
                    status_code=400,
                )
            clave = nombre.casefold()
            if clave in vistos:
                return JSONResponse(
                    {"error": f"Hay dos franjas llamadas «{nombre}»; los nombres deben ser únicos."},
                    status_code=400,
                )
            vistos.add(clave)
            if not _hora_valida(inicio) or not _hora_valida(fin):
                return JSONResponse(
                    {"error": f"«{nombre}»: las horas deben ser HH:MM (00:00..24:00)."},
                    status_code=400,
                )
            if not (_minutos_de(inicio) < _minutos_de(fin)):
                return JSONResponse(
                    {"error": f"«{nombre}» tiene que terminar después de empezar."},
                    status_code=400,
                )
            limpias.append({"nombre": nombre, "inicio": inicio, "fin": fin})
    mostrar: bool | None = None
    if tiene_toggle:
        bruto = datos.get("mostrar_horas_equipo")
        if not isinstance(bruto, bool):
            return JSONResponse(
                {"error": "`mostrar_horas_equipo` debe ser un booleano."},
                status_code=400,
            )
        mostrar = bruto
    tiempo_libre: bool | None = None
    if tiene_tiempo_libre:
        bruto_tl = datos.get("tiempo_libre_activo")
        if not isinstance(bruto_tl, bool):
            return JSONResponse(
                {"error": "`tiempo_libre_activo` debe ser un booleano."},
                status_code=400,
            )
        tiempo_libre = bruto_tl
    plantilla = await run_in_threadpool(
        repos.guardar_plantilla_franjas,
        limpias,
        marca,
        mostrar_horas_equipo=mostrar,
        tiempo_libre_activo=tiempo_libre,
    )
    return JSONResponse(plantilla)


async def listar_franjas_de_semana(request: Request) -> Response:
    """GET /api/rota/semana/{lunes}/franjas[?marca]: las franjas vivas de esa semana.

    GRID POR MARCA: `?marca=` acota a la rejilla de esa marca (y siembra por defecto si vacía).
    En "Todas" (sin marca) devuelve las franjas de TODAS las marcas (no siembra).
    """
    lunes = dominio.lunes_de_semana_iso(request.path_params["lunes"])
    if not lunes:
        return JSONResponse(
            {"error": "Indica un lunes válido (AAAA-MM-DD)."}, status_code=400
        )
    marca, error = _marca_param(request)
    if error is not None:
        return error
    cuerpo = await run_in_threadpool(_listar_franjas_de_semana, lunes, marca)
    return JSONResponse(cuerpo)


def _listar_franjas_de_semana(lunes: str, marca: str | None) -> dict[str, Any]:
    franjas, _por_id = _franjas_de_semana(lunes, marca)
    return {"franjas": [_franja_semana_a_dict(f) for f in franjas]}


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
    # GRID POR MARCA: crear una franja (columna) exige una marca concreta (no "Todas").
    marca, error = _marca_param(request)
    if error is not None:
        return error
    if not marca:
        return JSONResponse(
            {"error": "Elige una marca concreta para crear su franja."}, status_code=400
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
    creada = await run_in_threadpool(
        repos.crear_franja_semana,
        lunes,
        nombre,
        inicio,
        fin,
        orden=orden_int,
        es_descanso=es_descanso,
        marca=marca,
    )
    if creada is None:
        return JSONResponse(
            {"error": f"Ya hay una franja llamada «{nombre}» en esa marca esa semana."},
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
    actualizada = await run_in_threadpool(repos.actualizar_franja_semana, franja_id, campos)
    if actualizada is None:
        return JSONResponse(
            {"error": "La franja no existe o el cambio rompe la unicidad por nombre."},
            status_code=404,
        )
    return JSONResponse(_franja_semana_a_dict(actualizada))


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
    marca, error = _marca_param(request)
    if error is not None:
        return error
    cuerpo = await run_in_threadpool(_listar_coordinacion_de_semana, lunes, marca)
    return JSONResponse(cuerpo)


def _listar_coordinacion_de_semana(lunes: str, marca: str | None) -> dict[str, Any]:
    nombres = _nombres_equipo()
    coordinacion = repos.listar_coordinacion_semana(lunes, marca)
    return {
        "lunes": lunes,
        "coordinacion": [
            {
                "fecha": c["fecha"],
                "franja_id": c["franja_id"],
                "coordinador_id": c["coordinador_id"],
                "coordinador_nombre": nombres.get(c["coordinador_id"], ""),
                # GRID POR MARCA: la rejilla de la celda (la UI etiqueta en "Todas").
                "marca": c.get("marca", "") or "",
                "marca_nombre": (
                    marcas.etiqueta_de(c["marca"]) if c.get("marca") else ""
                ),
            }
            for c in coordinacion
        ],
    }


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
    status, cuerpo = await run_in_threadpool(
        _set_coordinador_de_celda, lunes, fecha, franja_id, coordinador_id
    )
    return JSONResponse(cuerpo, status_code=status)


def _set_coordinador_de_celda(
    lunes: str, fecha: str, franja_id: str, coordinador_id: str
) -> tuple[int, dict[str, Any]]:
    if not _candidato_a_coordinador(coordinador_id):
        return 400, {
            "error": (
                "El usuario indicado no es candidato a coordinador "
                "(necesita `puede_coordinar=true`)."
            )
        }
    # GRID POR MARCA: la celda hereda la marca de su franja (fuente de verdad de la rejilla).
    franja_def = repos.obtener_franja_semana(franja_id)
    if franja_def is None:
        return 400, {"error": "La franja indicada no existe."}
    marca_celda = franja_def.get("marca", "") or ""
    registro = repos.actualizar_coordinador_rota(
        lunes, fecha, franja_id, coordinador_id, marca_celda
    )
    nombres = _nombres_equipo()
    return 200, {
        "fecha": registro["fecha"],
        "franja_id": registro["franja_id"],
        "coordinador_id": registro["coordinador_id"],
        "coordinador_nombre": nombres.get(registro["coordinador_id"], ""),
        "marca": registro.get("marca", "") or "",
        "marca_nombre": (
            marcas.etiqueta_de(registro["marca"]) if registro.get("marca") else ""
        ),
    }


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
    borrado = await run_in_threadpool(repos.quitar_coordinador_rota, fecha, franja_id)
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
    resultado = await run_in_threadpool(repos.borrar_franja_semana, franja_id, forzar=forzar)
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

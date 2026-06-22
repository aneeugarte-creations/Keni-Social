"""API Rota · turnos (horario persona×dia×franja): CRUD + lote + duplicar + aprobar."""
from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ... import rota as dominio
from ..._http_json import leer_json
from ...estados import (
    ESTADO_ROTA_PROPUESTO,
    ESTADOS_ROTA,
)
from ...motor_db import IntegrityError
from ._comun import (
    _es_admin,
    _fecha_valida,
    _franja_semana_a_dict,
    _franjas_de_semana,
    _hhmm_valido,
    _lunes_param,
    _marca_cuerpo,
    _marca_param,
    _nombres_equipo,
    _turno_a_dict,
    _usuario_actual,
)
from .ausencias import _ausencia_que_cubre

_MSG_SOLO_ADMIN = "Solo Elías (administrador) puede aprobar y publicar los turnos al equipo."


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


def _turnos_semana(lunes_iso: str, marca: str | None = None) -> dict[str, Any]:
    """Construye el payload de los turnos de una semana (incluye las franjas vivas).

    Las franjas viajan en la respuesta (`franjas`) para que el frontend renderice la
    rejilla NxDIAS sin un fetch extra. Si la semana no tiene franjas todavia, las
    siembra por defecto (Mañana, Tarde) y las devuelve.

    GRID POR MARCA: `marca` acota turnos y franjas a la rejilla de esa marca; en "Todas"
    (`marca` None) devuelve los de TODAS las marcas (la UI los apila etiquetados). `aprobada`
    se calcula sobre lo devuelto (en "Todas" exige que TODO lo apilado este aprobado).
    """
    nombres = _nombres_equipo()
    franjas_lista, franjas_por_id = _franjas_de_semana(lunes_iso, marca)
    turnos = [
        _turno_a_dict(t, nombres, franjas_por_id)
        for t in repos.listar_turnos_rota(semana=lunes_iso, marca=marca)
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


def _autoprellenar_semana_nueva(lunes_iso: str, marca: str) -> None:
    """Prellena una semana VIRGEN copiando los turnos de la anterior como borrador.

    «Virgen» = aún no tiene franjas (la primera apertura las siembra) ni turnos. Por eso el
    prellenado ocurre UNA sola vez —al abrir la semana por primera vez—: una vez tiene
    franjas ya no es virgen, así que reabrirla, o borrarle los turnos, no la vuelve a
    rellenar. La rotación de sábados es manual: la copia replica tal cual (estado
    `propuesto`) y el coordinador la ajusta antes de aprobar. Sin semana anterior con turnos,
    no hace nada.
    """
    if not lunes_iso or not marca:
        return
    if repos.listar_franjas_semana(lunes_iso, marca):
        return
    if repos.listar_turnos_rota(semana=lunes_iso, marca=marca):
        return
    from datetime import date, timedelta

    try:
        previo = (date.fromisoformat(lunes_iso) - timedelta(days=7)).isoformat()
    except ValueError:
        return
    if not repos.listar_turnos_rota(semana=previo, marca=marca):
        return
    repos.copiar_turnos_rota(previo, lunes_iso, reemplazar=False, marca=marca)


def _turnos_semana_resp(lunes: str, marca: str | None, es_admin: bool) -> Response:
    if marca and es_admin:
        _autoprellenar_semana_nueva(lunes, marca)
    return JSONResponse(_turnos_semana(lunes, marca))


async def turnos_semana(request: Request) -> Response:
    """GET /api/rota/turnos[?lunes&marca]: los turnos (horario) de una semana.

    GRID POR MARCA: `?marca=` acota a la rejilla de esa marca; ausente = "Todas" (apila todas).
    Al abrir por primera vez una semana nueva (admin + marca concreta), se prellena con los
    turnos de la anterior como borrador para no repartir desde cero.
    """
    lunes = _lunes_param(request)
    marca, error = _marca_param(request)
    if error is not None:
        return error
    es_admin = _es_admin(request)
    return await run_in_threadpool(_turnos_semana_resp, lunes, marca, es_admin)


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
            defaults = repos.inicializar_franjas_por_defecto(semana_legacy)
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
        # GRID POR MARCA: el turno hereda la marca de su franja (la rejilla a la que pertenece).
        # Es la fuente de verdad de la marca del turno (no un campo de body aparte), asi nunca
        # cae un turno en una rejilla que no es la de su columna.
        campos["marca"] = franja_def.get("marca", "") or ""
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

    # Horario A MEDIDA del turno: sobrescribe las horas de la franja SOLO para este turno
    # (persona con horas distintas ese dia). Cada campo es "HH:MM" valido o "" (vuelve a
    # heredar de la franja). NO se exige inicio<fin: un turno cruza medianoche igual que una
    # franja (p. ej. 17:00–01:00, cobertura nocturna).
    for clave in ("inicio", "fin"):
        if clave in datos:
            bruto = datos[clave]
            if bruto in (None, ""):
                campos[clave] = ""
            elif _hhmm_valido(bruto):
                campos[clave] = str(bruto).strip()
            else:
                return campos, JSONResponse(
                    {"error": f"Hora «{clave}» inválida (usa HH:MM)."}, status_code=400
                )

    return campos, None


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


def _crear_turno(datos: dict[str, Any]) -> Response:
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

    err = _violacion_ausencia(miembro_id, fecha, override=override, franja_id=franja_id)
    if err is not None:
        return err

    try:
        turno = repos.crear_turno_rota(
            semana,
            fecha,
            miembro_id=miembro_id,
            miembro_nombre=nombres.get(miembro_id, ""),
            franja_id=franja_id,
            inicio=campos.get("inicio", ""),
            fin=campos.get("fin", ""),
            estado=campos.get("estado", ESTADO_ROTA_PROPUESTO),
            override=override,
            motivo=campos.get("motivo", ""),
            nota_relevo=campos.get("nota_relevo", ""),
            # GRID POR MARCA: la marca la fija la franja elegida (ver `_validar_y_resolver_turno`).
            marca=campos.get("marca", ""),
        )
    except IntegrityError:
        # Carrera del check-then-insert: dos peticiones simultaneas pasaron ambas el
        # pre-check de arriba; el indice unico `idx_rota_turnos_uniq` para a la segunda.
        return JSONResponse(
            {"error": "Ya hay un turno para ese miembro en esa fecha y franja."},
            status_code=409,
        )
    return JSONResponse({"turno": _turno_a_dict(turno, nombres, franjas_por_id)}, status_code=201)


async def crear_turno(request: Request) -> Response:
    """POST /api/rota/turnos: crea un turno (horario `(fecha, franja_id)` para un miembro).

    Cuerpo: `{lunes?, fecha, miembro_id, franja_id, motivo?, nota_relevo?, override?, estado?}`.
    La `semana` se deriva del `lunes` enviado, o del lunes que contiene `fecha`. La
    `franja_id` debe pertenecer a la misma semana. Devuelve 409 si ya existe un turno para
    `(miembro_id, fecha, franja_id)` (el cliente debe editar el existente, no duplicar).
    Tambien aplica la regla de sabado y la cruzada de ausencias.
    """
    datos = await leer_json(request)
    return await run_in_threadpool(_crear_turno, datos)


def _actualizar_turno(turno_id: str, datos: dict[str, Any]) -> Response:
    actual = repos.obtener_turno_rota(turno_id)
    if actual is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)

    nombres = _nombres_equipo()
    campos, err = _validar_y_resolver_turno(datos, nombres, actual=actual)
    if err is not None:
        return err

    # Resuelve los valores finales (PATCH parcial: defaults desde `actual`).
    fecha = campos.get("fecha", actual["fecha"])
    miembro_id = campos.get("miembro_id", actual["miembro_id"])
    franja_id_final = campos.get("franja_id", actual.get("franja_id", ""))
    override = bool(campos.get("override", actual["override"]))

    err = _violacion_ausencia(
        miembro_id, fecha, override=override, franja_id=franja_id_final
    )
    if err is not None:
        return err

    try:
        turno = repos.actualizar_turno_rota(turno_id, campos)
    except IntegrityError:
        # El cambio mueve el turno a un `(miembro, fecha, franja)` ya ocupado; el indice
        # unico `idx_rota_turnos_uniq` lo corta -> 409 accionable (no 500).
        return JSONResponse(
            {"error": "Ya hay un turno para ese miembro en esa fecha y franja."},
            status_code=409,
        )
    if turno is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    _franjas_lista, franjas_por_id = _franjas_de_semana(actual["semana"])
    return JSONResponse({"turno": _turno_a_dict(turno, nombres, franjas_por_id)})


async def actualizar_turno(request: Request) -> Response:
    """PATCH /api/rota/turnos/{id}: edita un turno (franja_id/miembro/override/motivo/...).

    Si la edicion pone a TRABAJAR a una persona que esta de ausencia ese dia SIN override,
    devuelve 409.
    """
    turno_id = request.path_params["turno_id"]
    datos = await leer_json(request)
    return await run_in_threadpool(_actualizar_turno, turno_id, datos)


def _borrar_turno(turno_id: str) -> Response:
    if not repos.borrar_turno_rota(turno_id):
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Turno eliminado."})


async def borrar_turno(request: Request) -> Response:
    """DELETE /api/rota/turnos/{id}: borra un turno individual."""
    turno_id = request.path_params["turno_id"]
    return await run_in_threadpool(_borrar_turno, turno_id)


def _borrar_turnos_lote(ids: list[str]) -> Response:
    existentes = {t["id"] for t in repos.listar_turnos_rota() if t["id"] in ids}
    no_encontrados = [i for i in ids if i not in existentes]
    n = repos.borrar_turnos_rota_lote(list(existentes))
    return JSONResponse({"borrados": n, "no_encontrados": no_encontrados})


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
    return await run_in_threadpool(_borrar_turnos_lote, ids)


def _crear_turnos_lote(entradas: list[Any]) -> Response:
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
                "inicio": campos.get("inicio", ""),
                "fin": campos.get("fin", ""),
                "estado": campos.get("estado", ESTADO_ROTA_PROPUESTO),
                "override": override,
                "motivo": campos.get("motivo", ""),
                "nota_relevo": campos.get("nota_relevo", ""),
                # GRID POR MARCA: cada turno hereda la marca de su franja (ver validacion).
                "marca": campos.get("marca", ""),
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

    try:
        creados = repos.crear_turnos_rota_lote(preparados)
    except IntegrityError:
        # Carrera del pre-indice: otro cliente inserto uno de estos turnos entre el chequeo
        # y el INSERT; el indice unico `idx_rota_turnos_uniq` corta el lote (sin medias).
        return JSONResponse(
            {
                "error": "Alguno de los turnos ya existe (lo creó otra petición); recarga la semana.",
                "creados": 0,
            },
            status_code=409,
        )
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


async def crear_turnos_lote(request: Request) -> Response:
    """POST /api/rota/turnos/lote {turnos: [...]}: crea varios turnos en una sola peticion.

    Cuerpo: `{turnos: [{lunes?, fecha, miembro_id, franja_id, motivo?, nota_relevo?, override?, estado?}, ...]}`.
    Si ALGUNA entrada falla la validacion (fecha invalida, miembro no existe, franja
    invalida) o ya existe un turno para `(miembro, fecha, franja_id)`, devuelve 409 con el
    indice y el motivo SIN tocar BD. Caso comun: "Mañana lun-vie para un community manager".
    """
    datos = await leer_json(request)
    entradas = datos.get("turnos")
    if not isinstance(entradas, list) or not entradas:
        return JSONResponse(
            {"error": "Indica al menos un turno (`turnos`)."}, status_code=400
        )
    return await run_in_threadpool(_crear_turnos_lote, entradas)


def _actualizar_turnos_lote(datos: dict[str, Any], ids: list[str]) -> Response:
    nombres = _nombres_equipo()
    override = bool(datos.get("override", False))

    # Construye los campos a aplicar. `miembro_id` requiere validacion contra el equipo;
    # `franja_id` requiere que la franja exista en BD. Los demas se pasan tal cual.
    campos: dict[str, Any] = {}
    if "miembro_id" in datos:
        miembro_id = datos["miembro_id"]
        if not isinstance(miembro_id, str) or (miembro_id and miembro_id not in nombres):
            return JSONResponse(
                {"error": "Indica un miembro del equipo válido."}, status_code=400
            )
        campos["miembro_id"] = miembro_id
        campos["miembro_nombre"] = nombres.get(miembro_id, "")
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

    # Verifica que todos los turnos pedidos existan (404 si alguno ya no está).
    actuales: list[dict[str, Any]] = []
    for tid in ids:
        actual = repos.obtener_turno_rota(tid)
        if actual is None:
            return JSONResponse(
                {"error": f"El turno {tid} ya no existe."}, status_code=404
            )
        actuales.append(actual)

    # Ausencia (misma regla que el PATCH 1:1): si la edicion cambia miembro o franja, valida
    # que el `(miembro, fecha, override, franja)` final de cada turno no ponga a trabajar a una
    # persona ausente sin override. La fecha no es editable en lote, asi que se toma de cada
    # turno. Reune los conflictos y devuelve 409 sin tocar BD (estilo `_crear_turnos_lote`).
    if "miembro_id" in campos or "franja_id" in campos:
        conflictos: list[dict[str, Any]] = []
        for actual in actuales:
            miembro_final = campos.get("miembro_id", actual["miembro_id"])
            franja_final = campos.get("franja_id", actual.get("franja_id", ""))
            override_final = bool(campos.get("override", actual["override"]))
            if _violacion_ausencia(
                miembro_final, actual["fecha"], override=override_final, franja_id=franja_final
            ) is not None:
                conflictos.append({"id": actual["id"], "fecha": actual["fecha"]})
        if conflictos:
            return JSONResponse(
                {
                    "error": "Algún turno deja a una persona ausente ese día sin override.",
                    "requiere_override": True,
                    "conflictos": conflictos,
                    "actualizados": 0,
                },
                status_code=409,
            )

    try:
        n, turnos = repos.actualizar_turnos_rota_lote(ids, campos)
    except IntegrityError:
        # El cambio mueve algún turno a un `(miembro, fecha, franja)` ya ocupado; el indice
        # unico `idx_rota_turnos_uniq` corta el lote -> 409 accionable (no 500).
        return JSONResponse(
            {
                "error": "Algún turno choca con otro para ese miembro en esa fecha y franja.",
                "actualizados": 0,
            },
            status_code=409,
        )
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


async def actualizar_turnos_lote(request: Request) -> Response:
    """PATCH /api/rota/turnos/lote: edita en lote varios turnos.

    Cuerpo: `{ids: [...], miembro_id?, franja_id?, override?: bool, motivo?: str, nota_relevo?: str}`.
    `miembro_id=""` vacia la asignacion (alineado con el PATCH 1:1).
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) and x for x in ids) or not ids:
        return JSONResponse(
            {"error": "Indica al menos un turno (`ids`)."}, status_code=400
        )
    return await run_in_threadpool(_actualizar_turnos_lote, datos, ids)


def _duplicar_turno(turno_id: str, datos: dict[str, Any]) -> Response:
    original = repos.obtener_turno_rota(turno_id)
    if original is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
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
    franja_explicita = "franja_id" in datos
    if franja_explicita:
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

    # La franja del clon debe pertenecer a la semana destino. Si el clon cae en otra semana
    # (caso «rellena la semana siguiente») y el cliente no pidió una franja concreta, mapeamos
    # la franja del original a la de la semana destino con el MISMO nombre (sembrando las
    # franjas por defecto de esa semana si aún no las tiene).
    franja_def = repos.obtener_franja_semana(franja_id)
    if franja_def is not None and franja_def["lunes"] != semana and not franja_explicita:
        marca_franja = franja_def.get("marca") or ""
        destino = repos.inicializar_franjas_por_defecto(semana, marca_franja)
        equivalente = next(
            (d for d in destino if d["nombre"] == franja_def["nombre"]), None
        )
        if equivalente is not None:
            franja_id = equivalente["id"]
            franja_def = equivalente
    if franja_def is None or franja_def["lunes"] != semana:
        return JSONResponse(
            {
                "error": (
                    "La franja del turno original no existe en la semana destino. Crea esa "
                    "franja en la semana destino o pasa un `franja_id` que ya exista en ella."
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
    err = _violacion_ausencia(miembro_id, fecha, override=override, franja_id=franja_id)
    if err is not None:
        return err

    try:
        clon = repos.duplicar_turno_rota(
            turno_id,
            fecha=fecha,
            miembro_id=miembro_id,
            miembro_nombre=nombres.get(miembro_id, ""),
            franja_id=franja_id,
            semana=semana,
        )
    except IntegrityError:
        # Carrera del check-then-insert (mismo backstop que crear_turno): 409 accionable.
        return JSONResponse(
            {"error": "Ya hay un turno para ese miembro en esa fecha y franja."},
            status_code=409,
        )
    if clon is None:
        return JSONResponse({"error": "El turno ya no existe."}, status_code=404)
    return JSONResponse(
        {"turno": _turno_a_dict(clon, nombres, franjas_por_id)}, status_code=201
    )


async def duplicar_turno(request: Request) -> Response:
    """POST /api/rota/turnos/{id}/duplicar: clona un turno con overrides opcionales.

    Cuerpo opcional `{fecha?, miembro_id?, franja_id?}`. Caso comun: copiar el turno a la
    semana siguiente con el mismo miembro y franja. Aplica las mismas reglas que la creacion
    (sabado, ausencia, choque `(miembro, fecha, franja_id)`).

    Si la `fecha` cae en otra semana y el cliente NO pasa `franja_id`, mapeamos la franja del
    original a la de la semana destino con el mismo nombre (sembrando las franjas por defecto
    si la semana destino aun esta vacia). Si esa franja no existe en la semana destino y no es
    sembrable, devolvemos 400: el cliente debe crear la franja o pasar un `franja_id` valido.
    """
    turno_id = request.path_params["turno_id"]
    datos = await leer_json(request) or {}
    return await run_in_threadpool(_duplicar_turno, turno_id, datos)


def _aprobar_turnos(lunes: str, marca: str) -> Response:
    n = repos.aprobar_semana_rota(lunes, marca)
    if n == 0:
        return JSONResponse(
            {"error": "No hay turnos en esa semana para aprobar. Asigna los turnos primero."},
            status_code=400,
        )
    payload = _turnos_semana(lunes, marca)
    payload["mensaje"] = f"Turnos aprobados y publicados al equipo ({n} turnos)."
    return JSONResponse(payload)


async def aprobar_turnos(request: Request) -> Response:
    """POST /api/rota/turnos/aprobar {lunes}: el coordinador de la rota APRUEBA (publica) los turnos al equipo.

    Solo admin: la frontera dice que el coordinador de la rota aprueba los turnos finales antes de publicarlos
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
    # GRID POR MARCA: aprobar una rejilla exige una marca concreta (no "Todas").
    marca, error = _marca_cuerpo(datos)
    if error is not None:
        return error
    return await run_in_threadpool(_aprobar_turnos, lunes, marca)


def _despublicar_turnos(lunes: str, marca: str) -> Response:
    n = repos.desaprobar_semana_rota(lunes, marca)
    if n == 0:
        return JSONResponse(
            {"error": "No hay turnos en esa semana para despublicar."},
            status_code=400,
        )
    payload = _turnos_semana(lunes, marca)
    payload["mensaje"] = f"Semana despublicada: vuelve a borrador ({n} turnos editables)."
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
    # GRID POR MARCA: despublicar una rejilla exige una marca concreta (no "Todas").
    marca, error = _marca_cuerpo(datos)
    if error is not None:
        return error
    return await run_in_threadpool(_despublicar_turnos, lunes, marca)


def _mis_turnos(lunes: str, marca: str | None, usuario: dict[str, Any] | None) -> Response:
    base = _turnos_semana(lunes, marca)
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


async def mis_turnos(request: Request) -> Response:
    """GET /api/rota/mis-turnos[?lunes&marca]: los turnos del USUARIO actual en esa semana.

    GRID POR MARCA: `?marca=` acota a la rejilla de esa marca; ausente = todas las marcas.
    """
    lunes = _lunes_param(request)
    marca, error = _marca_param(request)
    if error is not None:
        return error
    usuario = _usuario_actual(request)
    return await run_in_threadpool(_mis_turnos, lunes, marca, usuario)


def _mes_param(request: Request) -> tuple[str, str, str] | tuple[None, None, None]:
    """`(mes, desde, hasta)` ISO del mes pedido (`?mes=AAAA-MM`); por defecto el mes de hoy.

    `desde`/`hasta` son el primer y último día del mes (ISO, inclusive). Devuelve
    `(None, None, None)` si el formato es inválido (el handler responde 400).
    """
    import calendar
    from datetime import date

    crudo = (request.query_params.get("mes") or "").strip()
    if not crudo:
        hoy = date.today()
        anio, mes = hoy.year, hoy.month
    else:
        partes = crudo.split("-")
        if len(partes) != 2:
            return None, None, None
        try:
            anio, mes = int(partes[0]), int(partes[1])
            date(anio, mes, 1)  # valida año/mes (1..12) reales
        except (ValueError, TypeError):
            return None, None, None
    ultimo = calendar.monthrange(anio, mes)[1]
    return (
        f"{anio:04d}-{mes:02d}",
        f"{anio:04d}-{mes:02d}-01",
        f"{anio:04d}-{mes:02d}-{ultimo:02d}",
    )


def _franjas_por_id_de(turnos_crudos: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Mapa `franja_id -> FranjaDef` de las franjas referenciadas por `turnos_crudos`.

    Lectura PURA (no siembra): un turno existente siempre apunta a una franja real, así que
    basta buscarla por id. Resuelve nombre/horario para las vistas mensuales (propia y equipo).
    """
    franjas_por_id: dict[str, dict[str, Any]] = {}
    for t in turnos_crudos:
        fid = t.get("franja_id", "") or ""
        if fid and fid not in franjas_por_id:
            franja = repos.obtener_franja_semana(fid)
            if franja is not None:
                franjas_por_id[fid] = franja
    return franjas_por_id


async def mis_turnos_mes(request: Request) -> Response:
    """GET /api/rota/mis-turnos/mes[?mes=AAAA-MM&marca]: los turnos del USUARIO en el mes.

    Calendario MENSUAL de «Mis turnos»: solo el horario propio (turnos), SIN eventos ni
    cobertura. Lectura PURA sobre `rota_turnos` por rango de fecha — a diferencia de la
    vista semanal NO siembra franjas ni prellena semanas (abrir el mes no materializa nada).
    GRID POR MARCA: `?marca=` acota a esa rejilla; ausente = todas las marcas.
    """
    mes, desde, hasta = _mes_param(request)
    if mes is None:
        return JSONResponse({"error": "Mes inválido (usa AAAA-MM)."}, status_code=400)
    marca, error = _marca_param(request)
    if error is not None:
        return error
    usuario = _usuario_actual(request)
    if usuario is None:
        return JSONResponse(
            {
                "mes": mes,
                "desde": desde,
                "hasta": hasta,
                "miembro_id": "",
                "miembro_nombre": "",
                "mis_turnos": [],
                "total": 0,
                "aviso": "Inicia sesión para ver tu calendario de turnos.",
            }
        )
    return await run_in_threadpool(_mis_turnos_mes, mes, desde, hasta, marca, usuario)


def _mis_turnos_mes(
    mes: str, desde: str, hasta: str, marca: str | None, usuario: dict[str, Any]
) -> Response:
    nombres = _nombres_equipo()
    crudos = repos.listar_turnos_rota_rango(
        desde, hasta, miembro_id=usuario["id"], marca=marca
    )
    franjas_por_id = _franjas_por_id_de(crudos)
    mios = [_turno_a_dict(t, nombres, franjas_por_id) for t in crudos]
    return JSONResponse(
        {
            "mes": mes,
            "desde": desde,
            "hasta": hasta,
            "miembro_id": usuario["id"],
            "miembro_nombre": usuario["usuario"],
            "mis_turnos": mios,
            "total": len(mios),
        }
    )


def _turnos_mes(mes: str, desde: str, hasta: str, marca: str | None) -> Response:
    nombres = _nombres_equipo()
    crudos = repos.listar_turnos_rota_rango(desde, hasta, marca=marca)
    franjas_por_id = _franjas_por_id_de(crudos)
    turnos = [_turno_a_dict(t, nombres, franjas_por_id) for t in crudos]
    return JSONResponse(
        {
            "mes": mes,
            "desde": desde,
            "hasta": hasta,
            "turnos": turnos,
            "total": len(turnos),
        }
    )


async def turnos_mes(request: Request) -> Response:
    """GET /api/rota/turnos/mes[?mes=AAAA-MM&marca]: los turnos de TODO el equipo en el mes.

    Calendario MENSUAL del EQUIPO en «Mis turnos»: solo el horario (turnos) de todos, SIN
    eventos ni cobertura. Lectura PURA por rango de fecha (no siembra franjas ni prellena).
    No requiere sesión (mismo dato que el Calendario semanal). GRID POR MARCA: `?marca=` acota.
    """
    mes, desde, hasta = _mes_param(request)
    if mes is None:
        return JSONResponse({"error": "Mes inválido (usa AAAA-MM)."}, status_code=400)
    marca, error = _marca_param(request)
    if error is not None:
        return error
    return await run_in_threadpool(_turnos_mes, mes, desde, hasta, marca)

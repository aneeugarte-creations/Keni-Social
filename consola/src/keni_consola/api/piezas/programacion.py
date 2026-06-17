"""Programacion de piezas: calculo de HUECOS (franjas) y encolado.

Reune la categoria de plan de una pieza, el calculo del proximo hueco futuro respetando la
unicidad de slot, el endpoint `encolar` y el helper de encolado con backstop de unicidad +
reintento. Extraido TAL CUAL del modulo `piezas.py` original (refactor de pura
reubicacion, sin cambio de comportamiento).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ...estados import ESTADO_PUBLICADO
from ...motor_db import IntegrityError
from .. import franjas as api_franjas
from ._comun import _publicacion_a_dict


def categoria_de_pieza(pub: dict[str, Any]) -> str:
    """Categoría del PLAN con la que programa una pieza. Best-effort ('' si no aplica).

    - 'evergreen' si su tema es de flujo evergreen (reciclaje),
    - la categoría de la HISTORIA de la que nació ('breaking' si lo era) en el resto,
    - '' para piezas manuales sin historia: usan las franjas genéricas.
    """
    try:
        plat = repos.obtener_pieza_fila(pub.get("id") or "") or {}
        cid = str(plat.get("publicacion_id") or "")
        if not cid:
            return ""
        item = repos.obtener_publicacion(cid) or {}
        # La categoría vive EN el contenido desde que se persiste al crear (promoción,
        # usar historia, reciclaje). Los fallbacks cubren filas anteriores a la columna.
        propia = str(item.get("categoria") or "").strip().lower()
        if propia:
            return propia
        if (item.get("flujo") or "") == "evergreen":
            return "evergreen"
        return repos.categoria_promovida_de_contenido(cid)
    except Exception:  # noqa: BLE001 -- la categoría es refinamiento; sin ella, genéricas
        return ""


# Margen MÍNIMO (min) entre "ahora" y la hora que se programa: aire para el último vistazo
# humano en la parrilla y, sobre todo, para que la publicación NUNCA salga con la hora ya
# vencida. Rige dos cosas: el adelanto de un BREAKING (sale ya, pero a ahora+margen) y el PISO
# de cualquier hueco de franja (un slot a menos de ese margen se considera demasiado pronto y
# se salta al siguiente). Búsqueda acotada de minuto libre por la unicidad de slot.
_MARGEN_MINIMO_MIN = 5
_BREAKING_BUSQUEDA_MIN = 240


def calcular_hueco_para(
    pub: dict[str, Any], ahora: datetime | None = None
) -> str | None:
    """Calcula el proximo hueco futuro para `pub` segun las franjas configuradas.

    Devuelve el datetime ISO ('YYYY-MM-DDTHH:MM') del hueco, o None si no hay NINGUNA
    franja aplicable a la (marca, red) de la pieza. `ahora` se puede inyectar
    para tests; por defecto es `datetime.now(UTC)` (naive, canon del sistema). Los huecos ya
    ocupados por OTRAS piezas `programado` de la MISMA (marca, red) se evitan — espejo del
    indice de unicidad de slot (`idx_parrilla_slot_uniq`, por marca+red+fecha): las piezas de
    un MISMO tema en redes distintas salen a la MISMA hora.

    CATEGORÍA del plan: una pieza BREAKING no espera franja (se programa a ahora+margen, en
    el primer minuto libre); el resto usa PRIMERO los horarios de SU línea (franjas con su
    categoría) y, si no tiene franja propia, las franjas genéricas. En todos los casos se
    respeta el PISO `ahora + _MARGEN_MINIMO_MIN`: nunca se devuelve un hueco ya vencido o
    demasiado próximo para publicar.
    """
    if ahora is None:
        # Naive en UTC (canon del sistema, ver `tiempo.ahora_iso`): así coincide con las
        # `fecha_programada` almacenadas y no depende de la zona del host.
        ahora = datetime.now(UTC).replace(tzinfo=None)
    # PISO anti-"tiempo vencido": nada se programa antes de ahora+margen. Suelo para CUALQUIER
    # categoría; un hueco de franja por debajo de él se descarta y se cae al siguiente.
    piso = ahora + timedelta(minutes=_MARGEN_MINIMO_MIN)
    programadas = repos.listar_piezas(estado="programado")
    ocupados_mr = {
        otra["fecha_programada"]
        for otra in programadas
        if otra["id"] != pub["id"]
        and otra["fecha_programada"]
        and otra["marca"] == pub["marca"]
        and otra["red"] == pub["red"]
    }
    # DEFENSA en profundidad: el índice de unicidad de slot es PARCIAL (solo `estado='programado'`),
    # así que una pieza marcada `publicado` con fecha FUTURA libera su hueco a ojos del cálculo y
    # otra caería en el mismo minuto (así dos historias acabaron a la misma hora). Una pieza
    # publicada cuya fecha sigue en el futuro AÚN reserva ese hueco: lo tratamos como ocupado.
    clave_ahora = ahora.strftime("%Y-%m-%dT%H:%M")
    for otra in repos.listar_piezas(estado="publicado", desde=clave_ahora):
        fecha = otra.get("fecha_programada") or ""
        if (
            otra.get("id") != pub["id"]
            and fecha > clave_ahora
            and otra.get("marca") == pub["marca"]
            and otra.get("red") == pub["red"]
        ):
            ocupados_mr.add(fecha)
    categoria = categoria_de_pieza(pub)
    # 0) BREAKING: la última hora no espera al siguiente hueco del plan — sale YA (con un
    # margen corto), en el primer minuto libre de su (marca, red).
    if categoria == "breaking":
        cand = piso.replace(second=0, microsecond=0)
        for _ in range(_BREAKING_BUSQUEDA_MIN):
            clave = cand.strftime("%Y-%m-%dT%H:%M")
            if clave not in ocupados_mr:
                return clave
            cand += timedelta(minutes=1)
        return None  # parrilla patológicamente saturada
    # 1) HORARIOS DE LA LÍNEA (preferentes): si la pieza tiene categoría y su línea tiene
    # franjas propias, ESOS son sus horarios.
    aplican = api_franjas.franjas_aplicables(
        repos.listar_franjas(), pub["marca"], pub["red"], categoria
    )
    de_linea = bool(categoria) and any(
        (f.get("categoria") or "") == categoria for f in aplican
    )
    if de_linea:
        return api_franjas.proximo_hueco(aplican, piso, ocupados_mr)
    # 2) Franjas-caja genéricas.
    if not aplican:
        return None
    return api_franjas.proximo_hueco(aplican, piso, ocupados_mr)


async def encolar(request: Request) -> Response:
    """Programa la pieza en el proximo hueco futuro de sus franjas.

    `POST /api/piezas/{id}/encolar` -> `{pieza}` (estado=programado y
    fecha_programada puesta al hueco). 404 si no existe; 400 si no hay franjas
    aplicables a su (marca, red).
    """
    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    # PUBLICADO ES TERMINAL: una pieza cuyo post YA salió no se re-encola. Reprogramarla
    # revierte publicado->programado y, peor, `_encolar_en_hueco_libre` resetea `preparado_en`
    # (el claim que el barrido usa para no re-publicar): con KENI_PUBLICAR_REAL on eso abre la
    # puerta a un DOBLE-POST. Guard en profundidad (la UI ya oculta la acción, ver VistaLista).
    if (pub.get("estado") or "") == ESTADO_PUBLICADO:
        return JSONResponse(
            {"error": "Una pieza ya publicada no se re-encola."},
            status_code=409,
        )
    actualizada, hubo_hueco = _encolar_en_hueco_libre(pub)
    if not hubo_hueco:
        return JSONResponse(
            {"error": "No hay franjas de horario configuradas para esta marca/red."},
            status_code=400,
        )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"pieza": _publicacion_a_dict(actualizada)})


# Tope de reintentos al programar en un hueco: cada choque significa que OTRA pieza tomo ese
# slot entre el calculo y la escritura; recalculamos el siguiente hueco libre y reintentamos.
_MAX_REINTENTOS_HUECO = 8


def _encolar_en_hueco_libre(
    pub: dict[str, Any],
    ahora: datetime | None = None,
    *,
    estado_esperado: str | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Programa `pub` en el próximo hueco libre, con BACKSTOP de unicidad + reintento.

    Devuelve `(publicacion_actualizada | None, hubo_hueco)`. El índice único parcial
    `idx_parrilla_slot_uniq` impide que dos piezas queden programadas en el mismo (red, fecha):
    si entre el cálculo del hueco y la escritura otra pieza ya tomó ese slot, el UPDATE lanza
    una IntegrityError (carrera de doble-reserva); aquí RECALCULAMOS el siguiente hueco y
    reintentamos (bucle acotado). `hubo_hueco=False` => no hay franja aplicable (None,
    sin tocar nada). `None` con `hubo_hueco=True` => la pieza se borró en la carrera (o el CAS de
    `estado_esperado` no aplicó: ver abajo).

    `estado_esperado` (opcional): CAS sobre el `estado` actual de la pieza. El encolado MANUAL lo
    deja en None (override deliberado: re-encola venga del estado del que venga). La
    AUTO-programación pasa `ESTADO_EN_REVISION`: si entre que leyó la pieza `en_revision` y esta
    escritura otro flujo la movió (edición que la resetea a borrador, reprograma manual), el
    UPDATE condicional NO aplica y `actualizar_pieza` devuelve None; devolvemos
    `(None, True)` SIN reintentar (la pieza dejó de ser candidata; reintentar volvería a fallar).
    Así la auto-programación no RESUCITA a `programado` algo que el humano ya movió.
    """
    for _ in range(_MAX_REINTENTOS_HUECO):
        hueco = calcular_hueco_para(pub, ahora)
        if hueco is None:
            return None, False
        try:
            # `preparado_en=""`: una pieza recién (re)programada aún no se ha publicado; resetearlo
            # la deja lista para publicarse de nuevo. Inocuo en el encolado manual.
            actualizada = repos.actualizar_pieza(
                pub["id"],
                {"estado": "programado", "fecha_programada": hueco, "preparado_en": ""},
                estado_esperado=estado_esperado,
            )
        except IntegrityError:
            # Otra pieza reservó este slot antes que nosotros: recalcula y reintenta.
            continue
        return actualizada, True
    # Contención patológica: tras varios choques no se consiguió un slot libre estable.
    return None, True

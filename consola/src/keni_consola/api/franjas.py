"""API Franjas: colas de publicacion (franjas horarias) CRUD + calculo de hueco.

Una FRANJA es una plantilla de hueco recurrente: (marca?, red?, dia_semana, hora).
Las publicaciones se ENCOLAN buscando el proximo hueco futuro de las franjas que
apliquen a su (marca, red). El calculo del hueco es una funcion PURA y DETERMINISTA
(`proximo_hueco`) que recibe "ahora" inyectado para poder testearla sin reloj real.

dia_semana: 0=lunes .. 6=domingo (igual que `datetime.weekday()`).
hora:       "HH:MM" en 24h.

SEGURIDAD / VALIDACION:
  - `marca` (si viene) SOLO de la allowlist de Skills (con slug); `red` (si viene)
    SOLO una red canonica. dia_semana 0..6; hora "HH:MM" valida.
  - SQL parametrizado en `consola.db`; errores en espanol, sin tracebacks.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, marcas, redes
from .._http_json import leer_json

# Marcas validas: las de Skills (con slug). Mismo criterio que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones_por_slug())
_MARCAS_IDS = {m[0] for m in _MARCAS}

# "HH:MM" 24h: 00:00..23:59.
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Horizonte de busqueda del proximo hueco (dias). Con franjas validas siempre se
# encuentra hueco dentro de una semana, salvo que TODOS esten ocupados; este tope
# evita un bucle infinito teorico (defensa en profundidad).
_HORIZONTE_DIAS = 366


def hora_valida(hora: Any) -> bool:
    """True si `hora` es un string 'HH:MM' 24h valido."""
    return isinstance(hora, str) and _RE_HORA.match(hora) is not None


def _franja_a_dict(franja: dict[str, Any]) -> dict[str, Any]:
    """Serializa una franja resolviendo nombres legibles de marca y red."""
    return {
        "id": franja["id"],
        "marca": franja["marca"],
        "marca_nombre": marcas.etiqueta_por_slug(franja["marca"]) if franja["marca"] else "",
        "red": franja["red"],
        "red_nombre": redes.nombre_por_id(franja["red"]) if franja["red"] else "",
        "dia_semana": franja["dia_semana"],
        "hora": franja["hora"],
    }


# --------------------------------------------------------------------------- #
# Logica de aplicacion + calculo del proximo hueco (PURA y testeable)          #
# --------------------------------------------------------------------------- #


def franjas_aplicables(
    franjas: list[dict[str, Any]], marca: str, red: str
) -> list[dict[str, Any]]:
    """Franjas que aplican a una (marca, red), con prioridad por especificidad.

    Prioridad (la primera con resultados gana, no se mezclan niveles):
      1. franjas con ESA marca Y ESA red,
      2. si no hay, franjas que coincidan en marca (red='') o en red (marca=''),
         o generales (ambas ''),
    Devuelve la lista del nivel ganador (puede estar vacia si no aplica ninguna).
    """
    especificas = [f for f in franjas if f["marca"] == marca and f["red"] == red]
    if especificas:
        return especificas
    parciales = [
        f
        for f in franjas
        if (f["marca"] == marca and f["red"] == "")
        or (f["red"] == red and f["marca"] == "")
        or (f["marca"] == "" and f["red"] == "")
    ]
    return parciales


def _candidato(ahora: datetime, dia_semana: int, hora: str) -> datetime:
    """Primer datetime >= `ahora` que cae en `dia_semana` a la `hora` ('HH:MM')."""
    hh, mm = (int(p) for p in hora.split(":"))
    # Dias hasta el proximo `dia_semana` (0..6) a partir de hoy.
    delta_dias = (dia_semana - ahora.weekday()) % 7
    candidato = (ahora + timedelta(days=delta_dias)).replace(
        hour=hh, minute=mm, second=0, microsecond=0
    )
    if candidato <= ahora:
        # Ese hueco ya paso hoy: salta a la proxima semana.
        candidato += timedelta(days=7)
    return candidato


def proximo_hueco(
    franjas_aplican: list[dict[str, Any]],
    ahora: datetime,
    ocupados: set[str],
) -> str | None:
    """Proximo hueco FUTURO (ISO 'YYYY-MM-DDTHH:MM') de las franjas dadas, libre.

    - Considera SOLO las `franjas_aplican` (ya filtradas por aplicabilidad).
    - Estrictamente FUTURO respecto a `ahora` (los huecos <= ahora se descartan).
    - Evita los datetimes en `ocupados` (ISO 'YYYY-MM-DDTHH:MM' de otras publicaciones
      ya `programado`): avanza a la siguiente repeticion semanal de esa misma franja.
    - Devuelve el datetime mas temprano disponible, o None si no aplica ninguna franja.

    Determinista: depende solo de sus argumentos (no del reloj real).
    """
    if not franjas_aplican:
        return None
    mejor: datetime | None = None
    for franja in franjas_aplican:
        candidato = _candidato(ahora, franja["dia_semana"], franja["hora"])
        # Avanza semana a semana hasta encontrar un hueco no ocupado (con tope).
        limite = ahora + timedelta(days=_HORIZONTE_DIAS)
        while candidato.strftime("%Y-%m-%dT%H:%M") in ocupados and candidato <= limite:
            candidato += timedelta(days=7)
        if candidato > limite:
            continue
        if mejor is None or candidato < mejor:
            mejor = candidato
    return mejor.strftime("%Y-%m-%dT%H:%M") if mejor is not None else None


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de franjas."""
    franjas = db.listar_franjas()
    return JSONResponse({"franjas": [_franja_a_dict(f) for f in franjas]})


async def crear(request: Request) -> Response:
    """Crea una franja `{dia_semana, hora, marca?, red?}` -> `{franja}`."""
    datos = await leer_json(request)
    dia = datos.get("dia_semana")
    if not isinstance(dia, int) or isinstance(dia, bool) or not (0 <= dia <= 6):
        return JSONResponse(
            {"error": "El día de la semana debe ser un número de 0 (lunes) a 6 (domingo)."},
            status_code=400,
        )
    hora = datos.get("hora")
    if not hora_valida(hora):
        return JSONResponse(
            {"error": "La hora debe tener el formato HH:MM (24 horas)."}, status_code=400
        )
    marca = datos.get("marca", "")
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return JSONResponse({"error": "La marca debe ser texto."}, status_code=400)
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    red = datos.get("red", "")
    if red is None:
        red = ""
    if not isinstance(red, str):
        return JSONResponse({"error": "La red debe ser texto."}, status_code=400)
    if red and not redes.es_red(red):
        return JSONResponse({"error": "Red no permitida."}, status_code=400)

    franja = db.crear_franja(dia, hora, marca=marca, red=red)
    return JSONResponse({"franja": _franja_a_dict(franja)})


async def borrar(request: Request) -> Response:
    franja_id = request.path_params["franja_id"]
    if not db.borrar_franja(franja_id):
        return JSONResponse({"error": "Esa franja ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Franja borrada."})


RUTAS = [
    Route("/api/franjas", listar, methods=["GET"]),
    Route("/api/franjas", crear, methods=["POST"]),
    Route("/api/franjas/{franja_id}", borrar, methods=["DELETE"]),
]

"""API Parrilla del dia: clasificacion 13+6 y jerarquizacion de temas del Radar.

Convierte los temas del Radar (Google Trends + RSS) en la parrilla editorial del dia:
  - 13 posteos (clip / galeria / infografia / normal), jerarquizados por importancia.
  - 6 videos editoriales (con "carnita": contexto, seguimiento, analisis).

Endpoints:
  - `POST /api/parrilla-dia`
      Body: `{ "temas": [...], "geo": "MX" }`  (opcional: pasa temas directamente)
      Si no se pasan `temas`, los obtiene del Radar en vivo (misma logica que
      `GET /api/radar`). `geo` controla el geo del Radar y el contexto del scoring.

  - `GET  /api/parrilla-dia?geo=MX`
      Atajo de solo lectura: obtiene temas del Radar y devuelve la parrilla.
      Util para pintar la parrilla sin interaccion del usuario.

Respuesta comun:
  ```json
  {
    "geo": "MX",
    "posteos":   [ { "titulo", "tipo", "subtipo", "score", "orden", "razon", ... } ],
    "editorial": [ { ... } ],
    "sobrantes": [ { ... } ],
    "total_entrada": 22,
    "total_posteos": 13,
    "total_editorial": 6,
    "total_sobrantes": 3,
    "cuota_posteos": 13,
    "cuota_editorial": 6,
    "contexto": "MX"
  }
  ```

DEGRADACION HONESTA: si el Radar falla (Trends caido, sin feeds), la parrilla puede
resultar vacia. No se inventan temas. Se indica `total_entrada: 0`.

SEGURIDAD: el `geo` se valida contra la allowlist del Radar. Los temas que llegan
por body se validan (son dicts; campos desconocidos se ignoran con gracia). Errores
en espanol, sin tracebacks.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import parrilla, radar
from .._http_json import leer_json

# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _geo_valido(request: Request) -> str:
    """Lee y valida el parametro `geo`; cae a GEO_DEFECTO si es invalido."""
    crudo = (request.query_params.get("geo") or radar.GEO_DEFECTO).strip().upper()
    return crudo if radar.es_geo(crudo) else radar.GEO_DEFECTO


def _tema_desde_dict(d: Any) -> radar.Tema | None:
    """Convierte un dict en un `Tema` del Radar. Devuelve None si falta el titulo."""
    if not isinstance(d, dict):
        return None
    titulo = str(d.get("titulo", "")).strip()
    if not titulo:
        return None

    # Campos opcionales con coercion segura
    senal_raw = d.get("senal", 0)
    try:
        senal = int(senal_raw)
    except (TypeError, ValueError):
        senal = 0

    redes_raw = d.get("redes", [])
    fuentes_raw = d.get("fuentes", [])
    redes = set(redes_raw) if isinstance(redes_raw, (list, set)) else set()
    fuentes = set(fuentes_raw) if isinstance(fuentes_raw, (list, set)) else set()

    # Reconstruir enlaces opcionales
    enlaces_raw = d.get("enlaces", [])
    from ..radar import Enlace
    enlaces: list[Enlace] = []
    if isinstance(enlaces_raw, list):
        for e in enlaces_raw:
            if isinstance(e, dict) and (e.get("titulo") or e.get("url")):
                enlaces.append(
                    Enlace(
                        titulo=str(e.get("titulo", "")),
                        url=str(e.get("url", "")),
                        fuente=str(e.get("fuente", "")),
                    )
                )

    return radar.Tema(
        titulo=titulo,
        redes=redes or {"radar"},
        fuentes=fuentes or {"externo"},
        por_que=str(d.get("por_que", "")).strip(),
        senal=senal,
        senal_texto=str(d.get("senal_texto", "")).strip(),
        enlaces=enlaces,
        _claves_enlace={(e.url or e.titulo).strip().lower() for e in enlaces},
    )


def _obtener_temas_radar(geo: str) -> list[radar.Tema]:
    """Trae temas del Radar (Trends + feeds RSS activos). Degrada honestamente si falla."""
    from . import radar as api_radar

    grupos: list[list[radar.Tema]] = []
    temas_trends, _ = api_radar._radar_trends(geo)
    grupos.append(temas_trends)

    try:
        temas_feeds, _ = api_radar._radar_feeds()
        grupos.append(temas_feeds)
    except Exception:  # noqa: BLE001 -- feeds opcionales; si fallan, seguimos sin ellos
        pass

    return radar.consolidar(*grupos)


def _construir_respuesta(parrilla_dia: parrilla.ParrillaDia, geo: str) -> dict[str, Any]:
    datos = parrilla_dia.a_dict()
    datos["geo"] = geo
    return datos


# --------------------------------------------------------------------------- #
# Handlers                                                                      #
# --------------------------------------------------------------------------- #

async def obtener(request: Request) -> Response:
    """`GET /api/parrilla-dia?geo=MX` -> parrilla del dia a partir del Radar en vivo."""
    geo = _geo_valido(request)
    temas = _obtener_temas_radar(geo)
    resultado = parrilla.armar_parrilla(temas, contexto=geo)
    return JSONResponse(_construir_respuesta(resultado, geo))


async def calcular(request: Request) -> Response:
    """`POST /api/parrilla-dia` -> parrilla a partir de temas pasados en el body.

    Body JSON (todos opcionales):
      `{
        "temas": [ { "titulo", "senal", "por_que", "redes", "fuentes", "enlaces",
                     "senal_texto" } ],   // si ausente o vacio, trae del Radar
        "geo": "MX"                        // contexto de scoring y fuente del Radar
      }`
    """
    try:
        datos = await leer_json(request)
    except Exception:  # noqa: BLE001 -- body vacio o no-JSON: tratamos como {}
        datos = {}
    if not isinstance(datos, dict):
        return JSONResponse({"error": "El cuerpo debe ser un objeto JSON."}, status_code=400)

    # geo
    geo_raw = datos.get("geo", request.query_params.get("geo", radar.GEO_DEFECTO))
    geo = geo_raw.strip().upper() if isinstance(geo_raw, str) else radar.GEO_DEFECTO
    if not radar.es_geo(geo):
        geo = radar.GEO_DEFECTO

    # temas: si vienen en el body, los usamos; si no, traemos del Radar
    temas_raw = datos.get("temas")
    if isinstance(temas_raw, list) and temas_raw:
        temas_obj: list[radar.Tema] = []
        for d in temas_raw:
            t = _tema_desde_dict(d)
            if t is not None:
                temas_obj.append(t)
        if not temas_obj:
            return JSONResponse(
                {"error": "Ninguno de los temas enviados tiene titulo valido."},
                status_code=400,
            )
        temas = temas_obj
    else:
        # Sin temas en el body: traemos del Radar
        temas = _obtener_temas_radar(geo)

    resultado = parrilla.armar_parrilla(temas, contexto=geo)
    return JSONResponse(_construir_respuesta(resultado, geo))


# --------------------------------------------------------------------------- #
# Endpoint de scoring individual (util para debug / transparencia)             #
# --------------------------------------------------------------------------- #

async def puntuar(request: Request) -> Response:
    """`POST /api/parrilla-dia/puntuar` -> score + razon para un unico tema.

    Body: `{ "titulo", "senal", "por_que", "redes", "fuentes", "enlaces", "geo" }`.
    """
    try:
        datos = await leer_json(request)
    except Exception:  # noqa: BLE001
        datos = {}
    if not isinstance(datos, dict):
        return JSONResponse({"error": "El cuerpo debe ser un objeto JSON."}, status_code=400)

    tema = _tema_desde_dict(datos)
    if tema is None:
        return JSONResponse({"error": "El campo 'titulo' es obligatorio."}, status_code=400)

    geo_raw = datos.get("geo", "MX")
    geo = geo_raw.strip().upper() if isinstance(geo_raw, str) else "MX"
    if not radar.es_geo(geo):
        geo = "MX"

    score, razon = parrilla.puntuar_tema(tema, contexto=geo)
    tipo, subtipo = parrilla._clasificar_tipo(tema)
    return JSONResponse({
        "titulo": tema.titulo,
        "tipo": tipo,
        "subtipo": subtipo,
        "score": round(score, 4),
        "razon": razon,
        "geo": geo,
    })


# --------------------------------------------------------------------------- #
# Rutas                                                                         #
# --------------------------------------------------------------------------- #

RUTAS = [
    Route("/api/parrilla-dia", obtener, methods=["GET"]),
    Route("/api/parrilla-dia", calcular, methods=["POST"]),
    Route("/api/parrilla-dia/puntuar", puntuar, methods=["POST"]),
]

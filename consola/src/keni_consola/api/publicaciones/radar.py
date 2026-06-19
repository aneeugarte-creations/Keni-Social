"""Handler de promoción de un tema del Radar/Parrilla al tablero (`desde-radar`)."""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...tiempo import hoy_utc
from ._comun import (
    _MAX_TEXTO,
    _MAX_TITULO,
    PRIORIDADES_CONTENIDO,
    _contenido_a_dict,
    _red_valida,
    _validar_marca,
    autogen_redactar,
    autor_de_peticion,
    leer_json,
    repos,
)


async def desde_radar(request: Request) -> Response:
    """POST /api/publicaciones/desde-radar: promueve un tema del Radar/Parrilla al tablero.

    El Radar es efimero (no persiste): el cliente manda el tema elegido. Se crea un
    contenido `flujo='importante'` con `origen='radar'`, prioridad opcional y, si se indican,
    sus filas por plataforma.
    """
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El tema necesita un título."}, status_code=400)

    prioridad = datos.get("prioridad", "media") or "media"
    if prioridad not in PRIORIDADES_CONTENIDO:
        prioridad = "media"

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    redes_iniciales = datos.get("redes", [])
    if not isinstance(redes_iniciales, list):
        redes_iniciales = []
    redes_iniciales = [r for r in redes_iniciales if isinstance(r, str) and _red_valida(r)]

    descripcion = datos.get("descripcion", "")
    if not isinstance(descripcion, str):
        descripcion = ""

    # Señal de viralidad del tema del Radar (Fase 5): se PERSISTE para que el score la use.
    # El cliente la manda tal cual la trae el Radar (`Tema.a_dict()["senal"]`); defensivo.
    try:
        senal_viralidad = int(datos.get("senal", 0) or 0)
    except (TypeError, ValueError):
        senal_viralidad = 0

    generar_copy = datos.get("generar", True)
    autor = autor_de_peticion(request)
    status, cuerpo = await run_in_threadpool(
        _desde_radar,
        titulo=titulo,
        descripcion=descripcion,
        marca=marca,
        prioridad=prioridad,
        redes_iniciales=redes_iniciales,
        senal_viralidad=senal_viralidad,
        generar_copy=generar_copy,
        autor=autor,
    )
    return JSONResponse(cuerpo, status_code=status)


def _desde_radar(
    *,
    titulo: str,
    descripcion: str,
    marca: str,
    prioridad: str,
    redes_iniciales: list[str],
    senal_viralidad: int,
    generar_copy: object,
    autor: dict | None,
) -> tuple[int, dict]:
    item = repos.crear_publicacion(
        clase="contenido",
        flujo="importante",
        titulo=titulo.strip()[:_MAX_TITULO],
        descripcion=descripcion.strip()[:_MAX_TEXTO],
        marca=marca,
        prioridad=prioridad,
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor,
        origen="radar",
        # El tema viene de una FUENTE (Radar), no de arte propio: tipo "fuente" (item E).
        tipo_contenido="fuente",
        senal_viralidad=senal_viralidad,
    )
    # Checklist "pendientes" (item E): cada plataforma nace con copy e imagen por hacer. Si
    # luego lanzamos generacion de copy en background, su borrador rellenara el copy (y la UI
    # marcara falta_copy=0); la imagen sigue manual (falta_imagen=1).
    for red in dict.fromkeys(redes_iniciales):
        repos.crear_pieza_fila(
            publicacion_id=item["id"], red=red, falta_copy=True, falta_imagen=True
        )

    # Generacion de copy en SEGUNDO PLANO (item E), reusando el flujo del asistente/RSS
    # (`autogen_redactar.lanzar_para_topic`): compone la nota desde el tema, infiere redes y
    # encola un `claude -p` cuyo borrador cuelga del tema. GATEADO por marca (sin marca no
    # hay voz) y por el flag `generar` del cuerpo (def True). Es BEST-EFFORT: si la skill o
    # la cola fallan, NO rompe la promocion (queda el copy manual como fallback).
    genero = False
    if marca and generar_copy:
        try:
            genero = autogen_redactar.lanzar_para_topic(item) is not None
        except Exception:  # noqa: BLE001 -- la generacion es opcional; nunca tumba la promocion
            genero = False

    plataformas = repos.listar_piezas_fila(item["id"])
    return 200, {"contenido": _contenido_a_dict(item, plataformas), "copy_en_proceso": genero}

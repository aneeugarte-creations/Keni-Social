"""Invariantes ESTRUCTURALES del montaje de la API (`api.descubrir`).

Dos roturas que en runtime son INVISIBLES:
  1. Dos modulos exportando el mismo (path, metodo): Starlette monta la primera ruta
     y la segunda queda muerta en silencio (first-wins).
  2. Un modulo con `RUTAS` ausente de todos los manifests (`apps/<app>.toml`): queda
     fuera del catalogo y del lint de fronteras (ADR 0005).

Politica de dureza: en produccion `descubrir` LOGUEA cada problema como ERROR (no
tumba un deploy en marcha por una ruta sombreada que ya venia sirviendo); el fallo
DURO lo da este test exigiendo la lista vacia sobre el repo real.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from keni_consola import api


async def _ep(request):  # pragma: no cover -- handler de juguete, nunca se sirve
    return JSONResponse({"ok": True})


async def _ws(websocket):  # pragma: no cover -- handler de juguete, nunca se sirve
    await websocket.close()


def test_repo_real_sin_problemas_de_invariantes():
    """El repo de HOY no tiene rutas duplicadas ni modulos sin manifest."""
    assert api.problemas_invariantes(refresco=True) == []


def test_detecta_path_y_metodo_duplicados():
    """El mismo (path, metodo) en dos modulos es un problema (la segunda ruta muere)."""
    pares = [
        ("aaa", Route("/api/x", _ep, methods=["GET"])),
        ("bbb", Route("/api/x", _ep, methods=["GET"])),
    ]
    problemas = [p for p in api._problemas_invariantes(pares) if "duplicada" in p]
    assert len(problemas) == 1
    assert "GET /api/x" in problemas[0]
    assert "'aaa'" in problemas[0] and "'bbb'" in problemas[0]


def test_mismo_path_con_metodos_distintos_no_es_duplicado():
    """La division legitima del path por metodos (GET vs POST) no se marca."""
    pares = [
        ("aaa", Route("/api/x", _ep, methods=["GET"])),
        ("bbb", Route("/api/x", _ep, methods=["POST"])),
    ]
    assert not [p for p in api._problemas_invariantes(pares) if "duplicada" in p]


def test_head_implicito_no_duplica_el_reporte():
    """Dos GET (cada uno con su HEAD implicito de Starlette) reportan UN problema."""
    pares = [
        ("aaa", Route("/api/x", _ep, methods=["GET", "HEAD"])),
        ("bbb", Route("/api/x", _ep, methods=["GET", "HEAD"])),
    ]
    assert len([p for p in api._problemas_invariantes(pares) if "duplicada" in p]) == 1


def test_detecta_websocket_duplicado():
    pares = [
        ("aaa", WebSocketRoute("/api/ws", _ws)),
        ("bbb", WebSocketRoute("/api/ws", _ws)),
    ]
    problemas = [p for p in api._problemas_invariantes(pares) if "duplicada" in p]
    assert len(problemas) == 1
    assert "WEBSOCKET /api/ws" in problemas[0]


def test_detecta_modulo_sin_manifest():
    """Un modulo con RUTAS que no figura en ningun apps/<app>.toml es un problema."""
    pares = [("zz_sin_manifest", Route("/api/zz", _ep, methods=["GET"]))]
    problemas = api._problemas_invariantes(pares)
    assert any("api/zz_sin_manifest" in p and "manifest" in p for p in problemas)


def test_modulo_declarado_en_manifest_no_se_marca():
    """`estado` esta declarado en shell.toml: no debe aparecer como suelto."""
    pares = [("estado", Route("/api/zz-unico", _ep, methods=["GET"]))]
    assert not [p for p in api._problemas_invariantes(pares) if "manifest" in p]

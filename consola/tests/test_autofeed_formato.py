"""El auto-feed crea piezas de FOTO explícitas (3 redes), no sabe si serán foto o video.

No toca Postgres: se monkeypatchean los `repos.*` y los helpers que tocan estado, para
ejercitar SOLO el alta de la pieza (`llevar_al_feed`) y verificar `formato='foto'` + las 3
redes de foto (instagram, x, facebook), espejo de la regla del dueño.
"""

from __future__ import annotations

from keni_consola import autofeed_daemon as af
from keni_consola import redes


def _cluster() -> dict:
    return {
        "id": "cl1",
        "marca": "claro-sports",
        "titulo": "Historia de prueba",
        "resumen": "Resumen.",
        "primer_visto": "2026-06-05T00:00:00+00:00",
    }


def test_llevar_al_feed_crea_pieza_foto_en_tres_redes(monkeypatch):
    capturado: dict = {}
    plataformas: list[str] = []

    def _crear_contenido(**kw):
        capturado.update(kw)
        return {"id": "c1", **kw}

    monkeypatch.setattr(af.repos, "items_de_cluster", lambda *a, **k: [])
    monkeypatch.setattr(af.repos, "crear_contenido", _crear_contenido)
    monkeypatch.setattr(
        af.repos,
        "crear_contenido_plataforma",
        lambda **kw: plataformas.append(kw["red"]),
    )
    monkeypatch.setattr(af.repos, "actualizar_noticia_cluster", lambda *a, **k: None)
    monkeypatch.setattr(af.repos, "marcar_items_cluster_usados", lambda *a, **k: None)
    # Sin lanzar copy real: la marca existe pero cortamos el lanzamiento (no toca IA).
    monkeypatch.setattr(af.marcas, "es_marca", lambda m: False)

    pieza = af.llevar_al_feed(_cluster())
    assert pieza is not None
    # La pieza nace como FOTO explícito.
    assert capturado["formato"] == redes.FORMATO_FOTO
    # Y crea exactamente las 3 redes de FOTO (instagram, x, facebook), en orden de catálogo.
    assert plataformas == list(redes.redes_de_formato(redes.FORMATO_FOTO))
    assert set(plataformas) == {"instagram", "x", "facebook"}

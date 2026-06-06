"""Dedup del pipeline en `crear_tema_de`: no crea un tema duplicado y registra el nuevo título.

No toca Postgres: se monkeypatchean los `repos.*` y los helpers internos que tocan estado, para
ejercitar SOLO la rama de dedup (saltar duplicado / crear y registrar la clave intra-barrido).
"""

from __future__ import annotations

from keni_consola import pipeline_contenido as pc
from keni_consola import redes
from keni_consola.dominio import dedup


def _trabajo(titulo: str, *, marca: str = "unotv", clave: str = "k1") -> dict:
    return {"item": {"titulo": titulo, "clave": clave}, "fuente": {"id": "f1", "marca": marca}}


def test_salta_duplicado_y_marca_item_usado(monkeypatch):
    marcadas: list[tuple] = []
    monkeypatch.setattr(pc.repos, "marcar_item", lambda fid, k, v: marcadas.append((fid, k, v)))
    # `crear_contenido` NO debe llamarse para un duplicado.
    monkeypatch.setattr(
        pc.repos, "crear_contenido",
        lambda **kw: (_ for _ in ()).throw(AssertionError("no debe crear un duplicado")),
    )
    vistas = {dedup.clave("Gol de último minuto")}
    tema = pc.crear_tema_de(_trabajo("¡Gol de último minuto!"), claves_vistas=vistas)
    assert tema is None
    assert marcadas == [("f1", "k1", True)]  # el item se marca usado para no re-evaluarlo


def test_crea_si_no_es_duplicado_y_registra_la_clave(monkeypatch):
    monkeypatch.setattr(pc.repos, "crear_contenido", lambda **kw: {"id": "t1", "titulo": kw["titulo"]})
    monkeypatch.setattr(pc.repos, "marcar_item", lambda *a: None)
    monkeypatch.setattr(pc, "_auto_etiquetar_linea", lambda *a, **k: None)
    monkeypatch.setattr(pc, "_redes_de_fuente", lambda f: ["x"])
    monkeypatch.setattr(pc, "_copy_pendiente_de", lambda *a, **k: "{}")
    vistas: set[str] = set()
    tema = pc.crear_tema_de(_trabajo("Noticia totalmente nueva"), claves_vistas=vistas)
    assert tema and tema["id"] == "t1"
    # La clave del título recién creado queda registrada (dedup dentro del mismo barrido).
    assert dedup.clave("Noticia totalmente nueva") in vistas


def test_crear_tema_marca_formato_foto(monkeypatch):
    """El pipeline crea el tema como FOTO explícito (3 redes: el flujo automático no sabe si será video)."""
    capturado: dict = {}

    def _crear(**kw):
        capturado.update(kw)
        return {"id": "t9", "titulo": kw["titulo"]}

    monkeypatch.setattr(pc.repos, "crear_contenido", _crear)
    monkeypatch.setattr(pc.repos, "marcar_item", lambda *a: None)
    monkeypatch.setattr(pc, "_auto_etiquetar_linea", lambda *a, **k: None)
    monkeypatch.setattr(pc, "_copy_pendiente_de", lambda *a, **k: "{}")
    tema = pc.crear_tema_de(_trabajo("Noticia foto"))
    assert tema and tema["id"] == "t9"
    assert capturado["formato"] == redes.FORMATO_FOTO


def test_redes_de_fuente_por_defecto_son_las_de_foto():
    """Sin `redes_def` en la fuente, el pipeline cae a las 3 redes de FOTO (instagram, x, facebook)."""
    assert pc._redes_de_fuente({}) == list(redes.redes_de_formato(redes.FORMATO_FOTO))


def test_sin_claves_vistas_no_deduplica(monkeypatch):
    # Sin el conjunto, `crear_tema_de` no aplica dedup (crea siempre): compat con llamantes/tests.
    monkeypatch.setattr(pc.repos, "crear_contenido", lambda **kw: {"id": "t2", "titulo": kw["titulo"]})
    monkeypatch.setattr(pc.repos, "marcar_item", lambda *a: None)
    monkeypatch.setattr(pc, "_auto_etiquetar_linea", lambda *a, **k: None)
    monkeypatch.setattr(pc, "_redes_de_fuente", lambda f: ["x"])
    monkeypatch.setattr(pc, "_copy_pendiente_de", lambda *a, **k: "{}")
    tema = pc.crear_tema_de(_trabajo("Cualquier título"))
    assert tema and tema["id"] == "t2"

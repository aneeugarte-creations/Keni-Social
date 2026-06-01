"""Tests del digest de sugerencias editoriales. OFFLINE: no hay claude ni red.

La logica PURA (seleccion, parseo, composicion del prompt) se prueba directa. El barrido
end-to-end (encolar -> sondear -> persistir) se prueba mockeando el SEAM de generacion
(`generar.lanzar` + `generaciones.obtener`), de modo que no se toca el worker ni claude.
"""

from __future__ import annotations

import keni_consola.generaciones as generaciones
from keni_consola import repos, sugerencias_algoritmo as sa

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)


# --------------------------------------------------------------------------- #
# Logica pura                                                                   #
# --------------------------------------------------------------------------- #


def _noticia(plataforma="instagram", nivel="alta", es_cambio=True, nid="n1", titulo="t"):
    return {
        "id": nid, "plataforma": plataforma, "nivel": nivel, "es_cambio": es_cambio,
        "titulo": titulo, "resumen": "r", "enlace": "https://e/x",
    }


def test_es_importante_por_nivel_o_cambio():
    assert sa.es_importante(_noticia(nivel="alta", es_cambio=False))
    assert sa.es_importante(_noticia(nivel="baja", es_cambio=True))
    assert not sa.es_importante(_noticia(nivel="baja", es_cambio=False))


def test_seleccionar_agrupa_filtra_y_limita():
    noticias = [
        _noticia(plataforma="instagram", nid="a"),
        _noticia(plataforma="instagram", nid="b"),
        _noticia(plataforma="tiktok", nid="c"),
        _noticia(plataforma="general", nid="d"),          # sin ficha: se omite
        _noticia(plataforma="youtube", nivel="baja", es_cambio=False, nid="e"),  # no importante
    ]
    grupos = sa.seleccionar(noticias, maximo=5)
    assert "general" not in grupos
    assert "youtube" not in grupos
    assert {n["id"] for n in grupos["instagram"]} == {"a", "b"}
    assert "tiktok" in grupos
    # Tope de plataformas: la de mas noticias (instagram) entra primero.
    grupos1 = sa.seleccionar(noticias, maximo=1)
    assert list(grupos1) == ["instagram"]


def test_parsear_sugerencias_bloque_json():
    salida = """Aquí van:
```json
[{"tipo": "editorial", "titulo": "Priorizar Reels", "detalle": "Subir watch time."},
 {"tipo": "limite", "titulo": "Subir a 4000", "detalle": "TikTok amplió el caption."}]
```
Fin."""
    sugs = sa.parsear_sugerencias(salida)
    assert len(sugs) == 2
    assert sugs[0]["tipo"] == "editorial"
    assert sugs[1]["tipo"] == "limite"
    assert sugs[0]["titulo"] == "Priorizar Reels"


def test_parsear_sugerencias_lista_vacia_y_basura():
    assert sa.parsear_sugerencias("```json\n[]\n```") == []
    assert sa.parsear_sugerencias("no hay json aquí") == []
    assert sa.parsear_sugerencias("") == []
    # tipo desconocido cae a 'editorial'; entradas sin texto se descartan.
    sugs = sa.parsear_sugerencias('[{"tipo":"x","titulo":"T","detalle":"D"},{"titulo":"","detalle":""}]')
    assert len(sugs) == 1
    assert sugs[0]["tipo"] == "editorial"


def test_componer_prompt_incluye_ficha_limite_y_noticias():
    prompt = sa.componer_prompt(
        "instagram", [_noticia(titulo="Cambio de feed")], ficha="Voz cercana.", limite=2200,
    )
    assert "Instagram" in prompt
    assert "Voz cercana." in prompt
    assert "2200" in prompt
    assert "Cambio de feed" in prompt
    assert "json" in prompt.lower()


# --------------------------------------------------------------------------- #
# Barrido end-to-end (DB real via `cliente`; generacion MOCKEADA)               #
# --------------------------------------------------------------------------- #

_SALIDA_CLAUDE = """```json
[{"tipo": "editorial", "titulo": "Priorizar contenido nativo",
  "detalle": "El feed premia watch time: empujar Reels verticales."}]
```"""


def _sembrar_noticia_importante(plataforma="instagram", nid_titulo="Cambio algoritmo IG"):
    """Inserta una noticia importante (alta + cambio) lista para el digest."""
    repos.guardar_noticia_algoritmo({
        "fuente_id": "f1", "fuente_nombre": "Fuente", "plataforma": plataforma,
        "tipo": "oficial", "titulo": nid_titulo, "resumen": "resumen", "enlace": "https://e/x",
        "fecha": "2026-05-01", "clave": f"k-{plataforma}-{nid_titulo}",
        "importancia": 20, "nivel": "alta", "senales": ["feed"], "es_cambio": True,
    })


def _mock_generacion(monkeypatch, salida=_SALIDA_CLAUDE):
    """Mockea el seam de generacion: `generar.lanzar` no encola; `obtener` da salida canned."""
    monkeypatch.setattr(sa.generar, "lanzar", lambda **kw: {"id": "gen-test"})
    monkeypatch.setattr(
        generaciones, "obtener",
        lambda gid: {"id": gid, "estado": generaciones.ESTADO_COMPLETADO, "salida": salida},
    )


def test_barrido_genera_y_persiste_sugerencias(cliente, monkeypatch):
    _sembrar_noticia_importante()
    _mock_generacion(monkeypatch)

    resumen = sa.ejecutar_barrido()
    assert resumen["plataformas"] == 1
    assert resumen["sugerencias"] == 1

    sugs = repos.listar_sugerencias_editoriales(estado="nueva")
    assert len(sugs) == 1
    assert sugs[0]["plataforma"] == "instagram"
    assert sugs[0]["tipo"] == "editorial"
    assert sugs[0]["ficha_id"] == "editorial/plataformas/instagram"

    # La noticia queda marcada como sugerida: un segundo barrido no la reprocesa.
    resumen2 = sa.ejecutar_barrido()
    assert resumen2["plataformas"] == 0


def test_barrido_sin_noticias_importantes_no_genera(cliente, monkeypatch):
    # Noticia NO importante (baja, sin cambio): el barrido no llama a la generacion.
    repos.guardar_noticia_algoritmo({
        "fuente_id": "f1", "fuente_nombre": "F", "plataforma": "tiktok", "tipo": "agregador",
        "titulo": "Nota menor", "resumen": "", "enlace": "", "fecha": "", "clave": "k-menor",
        "importancia": 1, "nivel": "baja", "senales": [], "es_cambio": False,
    })
    _mock_generacion(monkeypatch)
    resumen = sa.ejecutar_barrido()
    assert resumen == {"plataformas": 0, "sugerencias": 0}


def test_api_listar_aplicar_descartar(cliente, monkeypatch):
    _sembrar_noticia_importante(plataforma="tiktok", nid_titulo="TikTok cambia ranking")
    _mock_generacion(monkeypatch)
    sa.ejecutar_barrido()

    # Listar via API.
    datos = cliente.get("/api/algoritmos/sugerencias?estado=nueva").json()
    assert datos["nuevas"] >= 1
    sug = datos["sugerencias"][0]
    assert sug["plataforma_nombre"]  # etiqueta humana resuelta

    # Aplicar -> escribe/crea la ficha editorial y marca aplicada.
    r = cliente.post(f"/api/algoritmos/sugerencias/{sug['id']}/aplicar", json={}).json()
    assert r["sugerencia"]["estado"] == "aplicada"
    assert r["ficha_id"] == "editorial/plataformas/tiktok"

    # Re-aplicar una ya resuelta -> 400.
    assert cliente.post(f"/api/algoritmos/sugerencias/{sug['id']}/aplicar", json={}).status_code == 400

    # Descartar otra (genera una segunda plataforma).
    _sembrar_noticia_importante(plataforma="youtube", nid_titulo="YouTube Shorts feed")
    sa.ejecutar_barrido()
    nuevas = cliente.get("/api/algoritmos/sugerencias?estado=nueva").json()["sugerencias"]
    yt = next(s for s in nuevas if s["plataforma"] == "youtube")
    desc = cliente.post(f"/api/algoritmos/sugerencias/{yt['id']}/descartar", json={}).json()
    assert desc["sugerencia"]["estado"] == "descartada"

"""Tests del auto-avance "dale el OK" (`auto_avance`), con dependencias monkeypatcheadas.

No tocan Postgres ni el almacén de media ni `claude -p`: parchean `repos`, `montar_cadena`,
la lectura de dimensiones y el lanzamiento de QA para ejercitar SOLO la lógica de decisión
(qué pieza avanza, cuál lanza QA, cuál se bloquea por 🔴).
"""

from __future__ import annotations

from keni_consola import auto_avance
from keni_consola.dominio import qa_editorial as dom_qa


def _pub(**over):
    base = {
        "id": "p1",
        "contenido_id": "c1",
        "marca": "unotv",
        "red": "instagram",
        "estado": "borrador",
        "falta_copy": False,
        "contenido": "copy out",
        "copy_in": "copy in",
        "copy_in_exento": False,
        "falta_imagen": False,
        "imagen": "img.png",
        "qa_auto_hash": "",
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# base_lista: copy out + copy in (o exención) + imagen con formato correcto     #
# --------------------------------------------------------------------------- #


def test_base_lista_pieza_completa(monkeypatch):
    monkeypatch.setattr(auto_avance, "_dimensiones", lambda _n: (1080, 1350))  # 4:5 IG
    assert auto_avance.base_lista(_pub()) is True


def test_base_lista_sin_copy_out(monkeypatch):
    monkeypatch.setattr(auto_avance, "_dimensiones", lambda _n: (1080, 1350))
    assert auto_avance.base_lista(_pub(falta_copy=True)) is False
    assert auto_avance.base_lista(_pub(contenido="")) is False


def test_copy_in_obligatorio_salvo_exencion(monkeypatch):
    monkeypatch.setattr(auto_avance, "_dimensiones", lambda _n: (1080, 1350))
    assert auto_avance.base_lista(_pub(copy_in="")) is False
    assert auto_avance.base_lista(_pub(copy_in="", copy_in_exento=True)) is True


def test_base_lista_formato_de_imagen_incorrecto(monkeypatch):
    # 1:1 no es un lienzo de instagram (solo feed 4:5 / vertical 9:16).
    monkeypatch.setattr(auto_avance, "_dimensiones", lambda _n: (1080, 1080))
    assert auto_avance.base_lista(_pub()) is False


def test_base_lista_sin_imagen():
    assert auto_avance.base_lista(_pub(falta_imagen=True)) is False
    assert auto_avance.base_lista(_pub(imagen="")) is False


# --------------------------------------------------------------------------- #
# ejecutar_barrido: avanzar / lanzar QA / bloquear                             #
# --------------------------------------------------------------------------- #


def _stub_listas(monkeypatch, pubs, veredicto):
    monkeypatch.setattr(auto_avance, "_dimensiones", lambda _n: (1080, 1350))
    monkeypatch.setattr(auto_avance.repos, "listar_publicaciones", lambda **_k: list(pubs))
    monkeypatch.setattr(auto_avance.repos, "ultimo_veredicto_qa", lambda *_a, **_k: veredicto)
    monkeypatch.setattr(auto_avance.repos, "obtener_contenido_plataforma", lambda _id: {})


def test_barrido_avanza_con_qa_listo(monkeypatch):
    _stub_listas(monkeypatch, [_pub()], {"verdicto": "listo"})
    montadas: list[str] = []
    avanzadas: list[dict] = []
    monkeypatch.setattr(
        auto_avance, "montar_cadena_aprobacion",
        lambda pid, plat, etiquetas, *, con_cargos: montadas.append(pid),
    )
    monkeypatch.setattr(
        auto_avance.repos, "actualizar_publicacion",
        lambda pid, campos: avanzadas.append(campos) or {},
    )
    res = auto_avance.ejecutar_barrido()
    assert res["avanzadas"] == 1 and res["qa_lanzadas"] == 0 and res["bloqueadas"] == 0
    assert montadas == ["p1"]
    assert avanzadas[0]["estado"] == "en_revision"
    assert avanzadas[0]["veredicto"] == "listo"


def test_barrido_avanza_tambien_con_revisar(monkeypatch):
    _stub_listas(monkeypatch, [_pub()], {"verdicto": "revisar"})
    monkeypatch.setattr(auto_avance, "montar_cadena_aprobacion", lambda *a, **k: None)
    monkeypatch.setattr(auto_avance.repos, "actualizar_publicacion", lambda *a, **k: {})
    res = auto_avance.ejecutar_barrido()
    assert res["avanzadas"] == 1 and res["bloqueadas"] == 0


def test_barrido_bloquea_no_publicar(monkeypatch):
    _stub_listas(monkeypatch, [_pub()], {"verdicto": "no_publicar"})
    montadas: list[str] = []
    monkeypatch.setattr(auto_avance, "montar_cadena_aprobacion", lambda pid, *a, **k: montadas.append(pid))
    monkeypatch.setattr(auto_avance.repos, "actualizar_publicacion", lambda *a, **k: {})
    res = auto_avance.ejecutar_barrido()
    assert res["avanzadas"] == 0 and res["bloqueadas"] == 1
    assert montadas == []  # 🔴 no se monta cadena ni avanza


def test_barrido_lanza_qa_si_falta_veredicto(monkeypatch):
    _stub_listas(monkeypatch, [_pub()], None)  # sin veredicto fresco
    lanzadas: list[str] = []
    monkeypatch.setattr(auto_avance, "_lanzar_qa", lambda pub: lanzadas.append(pub["id"]) or True)
    res = auto_avance.ejecutar_barrido()
    assert res["qa_lanzadas"] == 1 and res["avanzadas"] == 0
    assert lanzadas == ["p1"]


def test_barrido_no_relanza_qa_si_ya_lanzada_para_este_copy(monkeypatch):
    # qa_auto_hash == hash del copy actual => QA ya en vuelo: no se relanza.
    pub = _pub(qa_auto_hash=dom_qa.hash_copy("copy out"))
    _stub_listas(monkeypatch, [pub], None)
    lanzadas: list[str] = []
    monkeypatch.setattr(auto_avance, "_lanzar_qa", lambda p: lanzadas.append(p["id"]) or True)
    res = auto_avance.ejecutar_barrido()
    assert res["qa_lanzadas"] == 0 and lanzadas == []


def test_barrido_ignora_piezas_no_listas(monkeypatch):
    _stub_listas(monkeypatch, [_pub(falta_copy=True)], {"verdicto": "listo"})
    monkeypatch.setattr(auto_avance, "montar_cadena_aprobacion", lambda *a, **k: None)
    monkeypatch.setattr(auto_avance.repos, "actualizar_publicacion", lambda *a, **k: {})
    res = auto_avance.ejecutar_barrido()
    assert res == {"avanzadas": 0, "qa_lanzadas": 0, "bloqueadas": 0}

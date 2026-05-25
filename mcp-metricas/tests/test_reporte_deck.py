"""Reporte semanal de deportes (deck): query top-N por plataforma, ensamblado,
carga de agenda, render PPTX y CLI.

Todo sobre la fuente `muestra` (offline, determinista). El render PPTX usa
python-pptx, que en CI viene con el extra `dev`; si no esta, esos tests se saltan.
"""

from __future__ import annotations

import json

import pytest

from keni_metricas import reporte_deck
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.schema import Plataforma


@pytest.fixture
def fuente() -> FuenteMuestra:
    return FuenteMuestra()


# --- mejores_por_plataforma (fuente muestra) --------------------------------


def test_mejores_por_plataforma_n_por_cada_plataforma(fuente: FuenteMuestra):
    plats = (Plataforma.instagram, Plataforma.tiktok, Plataforma.facebook)
    res = fuente.mejores_por_plataforma("claro_sports", "semana", list(plats), 3)
    assert set(res) == set(plats)
    for p in plats:
        piezas = res[p]
        assert len(piezas) == 3
        assert all(x.plataforma == p for x in piezas)  # cada pieza es de SU plataforma
        # ordenadas por visualizaciones + interacciones (criterio del reporte)
        scores = [x.visualizaciones + x.interacciones for x in piezas]
        assert scores == sorted(scores, reverse=True)


def test_mejores_por_plataforma_no_configurada_da_vacio(fuente: FuenteMuestra):
    # fundacion no tiene TikTok configurado -> lista vacia para esa plataforma
    res = fuente.mejores_por_plataforma("fundacion", "semana", [Plataforma.tiktok], 3)
    assert res[Plataforma.tiktok] == []


def test_mejores_por_plataforma_determinista(fuente: FuenteMuestra):
    a = fuente.mejores_por_plataforma("claro_sports", "semana", [Plataforma.instagram], 3)
    b = fuente.mejores_por_plataforma("claro_sports", "semana", [Plataforma.instagram], 3)
    assert a == b


# --- construir_reporte_deportes ---------------------------------------------


def test_estructura_del_reporte(fuente: FuenteMuestra):
    rep = reporte_deck.construir_reporte_deportes(fuente, rango="semana", n_por_plataforma=3)
    assert rep["tipo"] == "reporte_deportes"
    assert rep["cuenta"]["id"] == "claro_sports"
    assert rep["cuenta"]["nombre"] == "Claro Sports"

    # mejores por plataforma: IG, TikTok, FB en ese orden, con 3 piezas cada una
    plats = [b["plataforma"] for b in rep["mejores_por_plataforma"]]
    assert plats == ["instagram", "tiktok", "facebook"]
    for bloque in rep["mejores_por_plataforma"]:
        assert len(bloque["piezas"]) == 3
        for pz in bloque["piezas"]:
            assert pz["plataforma"] == bloque["plataforma"]
            for clave in ("titulo", "visualizaciones", "interacciones", "url"):
                assert clave in pz


def test_promocion_de_cuentas_hermanas(fuente: FuenteMuestra):
    rep = reporte_deck.construir_reporte_deportes(fuente, rango="semana", n_hermanas=3)
    ids = [h["cuenta"] for h in rep["promocion_hermanas"]]
    assert ids == ["claro_sports_tv", "csport_golf"]
    for herm in rep["promocion_hermanas"]:
        assert herm["nombre"]  # nombre legible
        assert len(herm["piezas"]) == 3


def test_agenda_por_defecto_es_placeholder(fuente: FuenteMuestra):
    rep = reporte_deck.construir_reporte_deportes(fuente)
    assert rep["agenda"]["principales"] == []
    assert rep["agenda"]["propios"] == []
    assert "nota" in rep["agenda"]


def test_agenda_pasada_se_refleja(fuente: FuenteMuestra):
    agenda = {"principales": [{"nombre": "Champions", "plan": "en vivo"}], "propios": []}
    rep = reporte_deck.construir_reporte_deportes(fuente, agenda=agenda)
    assert rep["agenda"]["principales"][0]["nombre"] == "Champions"


def test_cuenta_principal_inexistente_propaga_error():
    from keni_metricas.config import FuenteScoped
    from keni_metricas.fuentes.base import CuentaNoEncontrada

    # alcance que NO incluye claro_sports
    scoped = FuenteScoped(FuenteMuestra(), ["unotv"])
    with pytest.raises(CuentaNoEncontrada):
        reporte_deck.construir_reporte_deportes(scoped, rango="semana")


# --- cargar_agenda ----------------------------------------------------------


def test_cargar_agenda_agrupa_por_tipo(tmp_path):
    ruta = tmp_path / "agenda.toml"
    ruta.write_text(
        "\n".join(
            [
                '[[evento]]',
                'nombre = "Champions"',
                'plan = "en vivo"',
                'tipo = "principal"',
                '[[evento]]',
                'nombre = "Camino al Mundial"',
                'plan = "capsulas"',
                'tipo = "propio"',
            ]
        ),
        encoding="utf-8",
    )
    ag = reporte_deck.cargar_agenda(ruta)
    assert [e["nombre"] for e in ag["principales"]] == ["Champions"]
    assert [e["nombre"] for e in ag["propios"]] == ["Camino al Mundial"]
    assert ag["principales"][0]["plan"] == "en vivo"


def test_cargar_agenda_archivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        reporte_deck.cargar_agenda(tmp_path / "no_existe.toml")


def test_cargar_agenda_tipo_invalido(tmp_path):
    ruta = tmp_path / "agenda.toml"
    ruta.write_text('[[evento]]\nnombre = "X"\ntipo = "raro"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="tipo"):
        reporte_deck.cargar_agenda(ruta)


def test_cargar_agenda_sin_nombre(tmp_path):
    ruta = tmp_path / "agenda.toml"
    ruta.write_text('[[evento]]\nplan = "algo"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="nombre"):
        reporte_deck.cargar_agenda(ruta)


# --- render PPTX ------------------------------------------------------------


def test_render_pptx_genera_deck(fuente: FuenteMuestra, tmp_path):
    pytest.importorskip("pptx")
    from pptx import Presentation

    rep = reporte_deck.construir_reporte_deportes(fuente, rango="semana")
    destino = reporte_deck.render_pptx(rep, tmp_path / "reporte.pptx")
    assert destino.exists() and destino.stat().st_size > 0
    prs = Presentation(str(destino))
    # portada + 3 plataformas + hermanas + 2 de agenda = 7 laminas
    assert len(prs.slides) == 7


# --- CLI (keni-reporte-deck) ------------------------------------------------


@pytest.fixture(autouse=True)
def _entorno_offline(monkeypatch, tmp_path):
    # fuente de muestra (config inexistente) e historico apagado => determinista, sin red
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")


def test_cli_json_imprime_estructura(capsys):
    rc = reporte_deck.main(["--formato", "json", "--rango", "semana"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tipo"] == "reporte_deportes"
    assert data["cuenta"]["id"] == "claro_sports"
    assert len(data["mejores_por_plataforma"]) == 3


def test_cli_pptx_escribe_archivo(capsys, tmp_path):
    pytest.importorskip("pptx")
    destino = tmp_path / "deck.pptx"
    rc = reporte_deck.main(["--rango", "semana", "--salida", str(destino)])
    assert rc == 0
    assert destino.exists()
    assert str(destino) in capsys.readouterr().out


def test_cli_rango_invalido_rc2(capsys):
    rc = reporte_deck.main(["--formato", "json", "--rango", "trimestre"])
    assert rc == 2
    assert "trimestre" in capsys.readouterr().err


def test_cli_agenda_inexistente_rc2(capsys, tmp_path):
    rc = reporte_deck.main(["--formato", "json", "--agenda", str(tmp_path / "nope.toml")])
    assert rc == 2
    assert capsys.readouterr().err.strip()


def test_cli_con_agenda_se_refleja_en_json(capsys, tmp_path):
    ruta = tmp_path / "agenda.toml"
    ruta.write_text('[[evento]]\nnombre = "Champions"\nplan = "en vivo"\ntipo = "principal"\n', encoding="utf-8")
    rc = reporte_deck.main(["--formato", "json", "--agenda", str(ruta)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["agenda"]["principales"][0]["nombre"] == "Champions"

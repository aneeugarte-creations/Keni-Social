"""Tests de `patrones_marca` (rasgos, derivación, carga, verificador) y de la
re-derivación offline (`patrones_derivar --jsonl`). Puros: sin Postgres ni red."""

from __future__ import annotations

import json

from keni_consola.produccion import patrones_derivar
from keni_consola import patrones_marca


# --------------------------------------------------------------------------- #
# Rasgos medibles                                                              #
# --------------------------------------------------------------------------- #


def test_rasgos_texto_basicos():
    r = patrones_marca.rasgos_texto("¡CHIVAS RECUPERÓ LA IDENTIDAD! 🔥⚽ Gran noche.")
    assert r["emojis"] == 2
    assert r["hashtags"] == 0
    assert r["gancho_mayusculas"] is True
    assert r["pregunta"] is False


def test_rasgos_emojis_banderas_y_modificadores():
    # Una bandera (par de regional indicators) cuenta 1; FE0F/ZWJ/tonos no cuentan.
    assert patrones_marca.contar_emojis("🇲🇽") == 1
    assert patrones_marca.contar_emojis("🇲🇽🇲🇽") == 2
    assert patrones_marca.contar_emojis("☝️") == 1  # con variation selector
    assert patrones_marca.contar_emojis("sin emojis, ¿ok?") == 0


def test_rasgos_hashtags_con_acentos():
    assert patrones_marca.contar_hashtags("#Querétaro y #LigaMX van. #año2026") == 3


def test_gancho_mayusculas_corta_en_minuscula():
    assert patrones_marca.tiene_gancho_mayusculas("LA JEFA HA HABLADO | el resto en minúsculas")
    assert not patrones_marca.tiene_gancho_mayusculas("NASA anunció el hallazgo")  # sigla suelta
    assert not patrones_marca.tiene_gancho_mayusculas("")


def test_pregunta_abre_o_cierra():
    assert patrones_marca.tiene_pregunta("¿Ya lo jugaste?")
    assert patrones_marca.tiene_pregunta("te lo perdiste?")
    assert not patrones_marca.tiene_pregunta("Nada que preguntar.")


# --------------------------------------------------------------------------- #
# Derivación del perfil                                                        #
# --------------------------------------------------------------------------- #


def _pieza(texto: str, eng: float, *, red: str = "facebook", vis: int = 1000) -> dict:
    return {"red": red, "texto": texto, "engagement_pct": eng, "visualizaciones": vis}


def _lote_contraste() -> list[dict]:
    """200 piezas: el top es corto, con gancho en MAYÚSCULAS y sin pregunta; el fondo
    es un parrafón con pregunta y sin gancho. Señales nítidas para las reglas."""
    piezas = []
    for i in range(100):
        piezas.append(_pieza(f"¡GOLAZO HISTÓRICO! 🔥⚽ La crónica del triunfo {i}.", 5.0 + i / 100))
    for i in range(100):
        piezas.append(
            _pieza("¿Lo viste venir? " + ("Mucho contexto de relleno que no aporta. " * 12) + str(i), 0.1)
        )
    return piezas


def test_derivar_perfil_separa_top_de_fondo():
    perfil = patrones_marca.derivar_perfil(
        _lote_contraste(), "marca-test", desde="2025-06-01", hasta="2026-06-01", generado="t"
    )
    fb = perfil["redes"]["facebook"]
    assert fb["muestras"] == 200
    # El top es el lote corto con gancho; el fondo, el parrafón con pregunta.
    assert fb["top"]["longitud"]["p50"] < 100 < fb["fondo"]["longitud"]["p50"]
    assert fb["top"]["pct_gancho_mayusculas"] == 100.0
    assert fb["fondo"]["pct_pregunta"] == 100.0
    lint = fb["lint"]
    assert lint["gancho_mayusculas"] == "esperado"
    assert lint["pregunta"] == "evitar"
    # Firma "el parrafón muere": el tope se ciñe al p90 del top, no al 1.5x genérico.
    assert lint["longitud_max"] <= int(fb["top"]["longitud"]["p90"] * 1.2)


def test_derivar_perfil_omite_red_sin_muestra():
    perfil = patrones_marca.derivar_perfil([_pieza("hola", 1.0)] * 10, "m", generado="t")
    assert perfil["redes"] == {}


def test_derivar_perfil_descarta_sin_texto_o_sin_visualizaciones():
    piezas = [_pieza("", 9.9)] * 200 + [_pieza("con texto", 1.0, vis=3)] * 200
    perfil = patrones_marca.derivar_perfil(piezas, "m", generado="t")
    assert perfil["redes"] == {}


# --------------------------------------------------------------------------- #
# Carga de perfiles (runtime > inicial)                                        #
# --------------------------------------------------------------------------- #


def test_cargar_perfil_inicial_del_paquete():
    # Las 3 marcas del piloto viajan con perfil inicial derivado de Metricool.
    for marca in ("unotv", "claro-sports", "nacion-gamer"):
        perfil = patrones_marca.cargar_perfil(marca)
        assert perfil is not None, marca
        assert perfil["redes"], marca


def test_cargar_perfil_runtime_gana_a_inicial(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path))
    propio = {"version": 1, "marca": "unotv", "redes": {"x": {"lint": {"emojis_max": 0}}}}
    (tmp_path / "unotv.json").write_text(json.dumps(propio), encoding="utf-8")
    perfil = patrones_marca.cargar_perfil("unotv")
    assert perfil is not None and "x" in perfil["redes"]


def test_cargar_perfil_invalido_cae_a_inicial(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path))
    (tmp_path / "unotv.json").write_text("{json roto", encoding="utf-8")
    perfil = patrones_marca.cargar_perfil("unotv")
    assert perfil is not None and perfil["marca"] == "unotv"  # la inicial del paquete


def test_cargar_perfil_marca_desconocida_o_invalida():
    assert patrones_marca.cargar_perfil("no-existe-tal-marca") is None
    assert patrones_marca.cargar_perfil("../../etc/passwd") is None
    assert patrones_marca.cargar_perfil("") is None


# --------------------------------------------------------------------------- #
# Verificador de voz                                                           #
# --------------------------------------------------------------------------- #


def _perfil_estricto(tmp_path, monkeypatch, *, marca: str = "marca-test") -> None:
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path))
    perfil = {
        "version": 1,
        "marca": marca,
        "redes": {
            "facebook": {
                "lint": {
                    "longitud_max": 300,
                    "longitud_min": 50,
                    "emojis_max": 0,
                    "hashtags_max": 2,
                    "gancho_mayusculas": "evitar",
                    "pregunta": "evitar",
                }
            },
            "instagram": {
                "lint": {
                    "longitud_max": None,
                    "longitud_min": None,
                    "emojis_max": 7,
                    "hashtags_max": 8,
                    "gancho_mayusculas": "esperado",
                    "pregunta": None,
                }
            },
        },
    }
    (tmp_path / f"{marca}.json").write_text(json.dumps(perfil), encoding="utf-8")


def test_verificar_pieza_dentro_de_patron(tmp_path, monkeypatch):
    _perfil_estricto(tmp_path, monkeypatch)
    texto = "El estudio confirmó el dato y la fuente lo respalda con cifras oficiales."
    assert patrones_marca.verificar_pieza("marca-test", "facebook", texto) == []


def test_verificar_pieza_fuera_de_patron(tmp_path, monkeypatch):
    _perfil_estricto(tmp_path, monkeypatch)
    avisos = patrones_marca.verificar_pieza(
        "marca-test", "facebook", "¿VISTE ESTO? 🔥🔥 " + "relleno " * 60
    )
    texto_avisos = "\n".join(avisos)
    assert "emoji" in texto_avisos
    assert "caracteres" in texto_avisos  # parrafón sobre longitud_max
    assert "MAYÚSCULAS" in texto_avisos
    assert "pregunta" in texto_avisos


def test_verificar_pieza_telegrama(tmp_path, monkeypatch):
    _perfil_estricto(tmp_path, monkeypatch)
    avisos = patrones_marca.verificar_pieza("marca-test", "facebook", "Pasó algo.")
    assert any("telegrama" in a for a in avisos)


def test_verificar_pieza_gancho_esperado(tmp_path, monkeypatch):
    _perfil_estricto(tmp_path, monkeypatch)
    avisos = patrones_marca.verificar_pieza(
        "marca-test", "instagram", "Una jornada para recordar en el Akron."
    )
    assert any("falta el gancho" in a for a in avisos)


def test_verificar_pieza_hashtags_en_copy_unico(tmp_path, monkeypatch):
    _perfil_estricto(tmp_path, monkeypatch)
    texto = "El dato manda en #LigaMX hoy mismo en la cancha y el equipo lo confirma."
    avisos = patrones_marca.verificar_pieza("marca-test", "facebook", texto)
    assert any("copy unificado va sin hashtags" in a for a in avisos)
    # En modo por-red (galería/manual) los hashtags dentro del patrón NO avisan.
    avisos_red = patrones_marca.verificar_pieza(
        "marca-test", "facebook", texto, copy_unico=False,
    )
    assert avisos_red == []


def test_verificar_pieza_sin_perfil_no_inventa():
    # Marca sin perfil: solo aplican las reglas de contrato (hashtags en copy único).
    assert patrones_marca.verificar_pieza("sin-perfil", "facebook", "Texto normal.") == []
    avisos = patrones_marca.verificar_pieza("sin-perfil", "facebook", "Con #hashtag.")
    assert len(avisos) == 1 and "hashtags" in avisos[0]


def test_avisos_de_piezas_deduplica_en_copy_unico(tmp_path, monkeypatch):
    _perfil_estricto(tmp_path, monkeypatch)
    texto = "¿VISTE? 🔥 " + "relleno " * 60
    piezas = [
        {"red": "facebook", "contenido": texto},
        {"red": "instagram", "contenido": texto},
    ]
    avisos = patrones_marca.avisos_de_piezas("marca-test", piezas)
    # El mismo texto en dos redes no duplica el aviso de emojis (cuerpo idéntico).
    assert len([a for a in avisos if "emoji" in a]) == 1


# --------------------------------------------------------------------------- #
# Render del doc y re-derivación offline                                       #
# --------------------------------------------------------------------------- #


def test_renderizar_doc_contiene_bandas():
    perfil = patrones_marca.derivar_perfil(_lote_contraste(), "marca-test", generado="t")
    doc = patrones_marca.renderizar_doc(perfil, "Marca Test")
    assert "# Patrones medidos · Marca Test" in doc
    assert "## Facebook" in doc
    assert "TOP" in doc and "FONDO" in doc


def test_derivar_cli_desde_jsonl(tmp_path):
    jsonl = tmp_path / "posts.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for p in _lote_contraste():
            f.write(json.dumps({**p, "marca": "unotv", "publicado": "2026-01-15"}) + "\n")
    salida = tmp_path / "perfiles"
    codigo = patrones_derivar.main(
        ["--jsonl", str(jsonl), "--marca", "unotv", "--salida", str(salida)]
    )
    assert codigo == 0
    perfil = json.loads((salida / "unotv.json").read_text(encoding="utf-8"))
    assert perfil["redes"]["facebook"]["muestras"] == 200
    assert perfil["ventana"] == {"desde": "2026-01-15", "hasta": "2026-01-15"}


def test_aplicar_store_crea_y_actualiza_doc(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path / "patrones"))
    perfil = patrones_marca.derivar_perfil(_lote_contraste(), "unotv", generado="t")
    doc_id = patrones_derivar.aplicar_store(perfil, "unotv", ahora="2026-06-10T00:00:00+00:00")
    assert doc_id == "editorial/rrss/unotv/patrones"
    from keni_consola import libprompts

    doc = libprompts.obtener(doc_id)
    assert doc is not None and "Patrones medidos" in doc.cuerpo
    assert doc.pipelines == ["redactar"]
    # Segunda aplicación: ACTUALIZA el cuerpo sin mover el documento (id estable).
    perfil2 = dict(perfil, piezas=999)
    assert patrones_derivar.aplicar_store(perfil2, "unotv", ahora="t2") == doc_id
    assert "999" in libprompts.obtener(doc_id).cuerpo
    assert (tmp_path / "patrones" / "unotv.json").is_file()

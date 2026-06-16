"""Encaje de MARCA con IA (`dominio.clasificador_marca`) + su cableado en la ingesta. OFFLINE.

El clasificador es best-effort: ante cualquier duda (la IA no devuelve una candidata válida)
o fallo (subproceso/JSON) cae al `fallback` (marca de noticias), para que ningún breaking
quede varado sin marca. El ejecutor de `claude -p` se inyecta (nunca se llama de verdad).
"""

from __future__ import annotations

import pytest

from keni_consola.dominio import clasificador_marca

_CANDIDATAS = [("unotv", "UnoTV"), ("claro-sports", "Claro Sports"), ("nacion-gamer", "Nación Gamer")]


@pytest.fixture(autouse=True)
def _texto_tmp(monkeypatch, tmp_path):
    # El prompt sale ahora de la Prompts de Texto: aislar el store en tmp para que ningún
    # test lea el store REAL (sin store, `cuerpo_efectivo` cae a la inicial del paquete).
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    return tmp_path


def _ejecutor_que_devuelve(salida: str):
    llamadas: list[str] = []

    def _ej(prompt: str, carpeta: str) -> str:
        llamadas.append(prompt)
        return salida

    _ej.llamadas = llamadas  # type: ignore[attr-defined]
    return _ej


def test_clasifica_a_la_marca_que_devuelve_la_ia():
    ej = _ejecutor_que_devuelve('{"marca": "claro-sports", "confianza": 0.9}')
    marca = clasificador_marca.clasificar_marca(
        "Resultado del partido de la Liga MX", "Goleada en la jornada", _CANDIDATAS,
        fallback="unotv", ejecutor=ej,
    )
    assert marca == "claro-sports"
    # El prompt incluyó las candidatas y el fallback.
    assert "claro-sports" in ej.llamadas[0] and "unotv" in ej.llamadas[0]


def test_extrae_json_aunque_venga_envuelto_en_texto():
    ej = _ejecutor_que_devuelve('Claro:\n```json\n{"marca": "nacion-gamer"}\n```\nlisto')
    marca = clasificador_marca.clasificar_marca(
        "Nuevo lanzamiento de videojuego", "", _CANDIDATAS, fallback="unotv", ejecutor=ej,
    )
    assert marca == "nacion-gamer"


def test_marca_invalida_cae_al_fallback():
    ej = _ejecutor_que_devuelve('{"marca": "fundacion"}')  # no es candidata
    marca = clasificador_marca.clasificar_marca(
        "Una nota cualquiera", "", _CANDIDATAS, fallback="unotv", ejecutor=ej,
    )
    assert marca == "unotv"


def test_json_basura_cae_al_fallback():
    ej = _ejecutor_que_devuelve("no soy json, lo siento")
    marca = clasificador_marca.clasificar_marca(
        "Una nota", "resumen", _CANDIDATAS, fallback="unotv", ejecutor=ej,
    )
    assert marca == "unotv"


def test_ejecutor_que_explota_cae_al_fallback():
    def _ej(prompt: str, carpeta: str) -> str:
        raise RuntimeError("claude no disponible")

    marca = clasificador_marca.clasificar_marca(
        "Una nota", "resumen", _CANDIDATAS, fallback="unotv", ejecutor=_ej,
    )
    assert marca == "unotv"


def test_sin_candidatas_devuelve_fallback_sin_llamar():
    ej = _ejecutor_que_devuelve('{"marca": "unotv"}')
    marca = clasificador_marca.clasificar_marca(
        "Algo", "", [], fallback="unotv", ejecutor=ej,
    )
    assert marca == "unotv"
    assert ej.llamadas == []  # no se llama a la IA si no hay entre qué elegir


def test_sin_texto_no_llama_a_la_ia():
    ej = _ejecutor_que_devuelve('{"marca": "claro-sports"}')
    marca = clasificador_marca.clasificar_marca(
        "  ", "", _CANDIDATAS, fallback="unotv", ejecutor=ej,
    )
    assert marca == "unotv"
    assert ej.llamadas == []


# --------------------------------------------------------------------------- #
# Config: flag + candidatas + fallback                                        #
# --------------------------------------------------------------------------- #


def test_config_clasificar_marca_ia_def_off(monkeypatch):
    from keni_consola import config

    monkeypatch.delenv("KENI_CLASIFICAR_MARCA_IA", raising=False)
    assert config.clasificar_marca_ia() is False
    monkeypatch.setenv("KENI_CLASIFICAR_MARCA_IA", "1")
    assert config.clasificar_marca_ia() is True


def test_config_marcas_activas_def_piloto(monkeypatch):
    from keni_consola import config

    monkeypatch.delenv("KENI_MARCAS_ACTIVAS", raising=False)
    assert config.marcas_activas() == ["unotv", "claro-sports", "nacion-gamer"]
    assert config.marca_noticias() == "unotv"
    # CSV configurable, sin duplicados y con orden estable.
    monkeypatch.setenv("KENI_MARCAS_ACTIVAS", "claro-sports, unotv , claro-sports")
    assert config.marcas_activas() == ["claro-sports", "unotv"]


# --------------------------------------------------------------------------- #
# Cableado en la ingesta: candidatas válidas + fallback                       #
# --------------------------------------------------------------------------- #


def test_clasificar_marca_ia_wiring_usa_candidatas_validas(monkeypatch):
    from keni_consola import recolectar_daemon

    capturado: dict[str, object] = {}

    def _fake(titulo, resumen, candidatas, *, fallback, ejecutor=None):
        capturado["candidatas"] = list(candidatas)
        capturado["fallback"] = fallback
        return "claro-sports"

    monkeypatch.setattr(
        "keni_consola.dominio.clasificador_marca.clasificar_marca", _fake
    )
    monkeypatch.setattr(recolectar_daemon, "_registrar_actividad_ia", lambda *a, **k: None)

    marca = recolectar_daemon._clasificar_marca_ia(
        {"titulo": "Gol de último minuto", "resumen": "", "breaking": 1}
    )
    assert marca == "claro-sports"
    ids = {c[0] for c in capturado["candidatas"]}  # type: ignore[index]
    assert ids == {"unotv", "claro-sports", "nacion-gamer"}
    assert capturado["fallback"] == "unotv"


# --------------------------------------------------------------------------- #
# El prompt vive en la Prompts (prompt/clasificar-marca)                 #
# --------------------------------------------------------------------------- #


def test_prompt_sale_de_la_prompts_y_sustituye_variables():
    # Sin store, el cuerpo EFECTIVO es la inicial del paquete: las variables {{MARCAS}},
    # {{MARCA_FALLBACK}} y {{NOTICIA}} no pueden quedar crudas en la llamada a la IA.
    ej = _ejecutor_que_devuelve('{"marca": "unotv"}')
    clasificador_marca.clasificar_marca(
        "Titular X", "Resumen Y", _CANDIDATAS, fallback="unotv", ejecutor=ej,
    )
    p = ej.llamadas[0]
    for marcador in ("{{MARCAS}}", "{{MARCA_FALLBACK}}", "{{NOTICIA}}"):
        assert marcador not in p
    assert "- claro-sports — Claro Sports" in p  # candidatas (id — nombre)
    assert "«unotv»" in p                        # marca de noticias generales
    assert "Titular X" in p and "Resumen Y" in p  # la noticia (JSON)


def test_prompt_editado_en_la_prompts_gana():
    # El equipo edita el doc en el store: la siguiente clasificación usa SU texto.
    from keni_consola import libprompts

    libprompts.importar_inicial()
    libprompts.guardar(
        "prompt/clasificar-marca",
        cuerpo="PERSONALIZADO\n{{MARCAS}}\nfallback={{MARCA_FALLBACK}}\n{{NOTICIA}}",
    )
    ej = _ejecutor_que_devuelve('{"marca": "unotv"}')
    clasificador_marca.clasificar_marca(
        "Titular", "", _CANDIDATAS, fallback="unotv", ejecutor=ej,
    )
    p = ej.llamadas[0]
    assert p.startswith("PERSONALIZADO")
    assert "fallback=unotv" in p and "{{MARCAS}}" not in p


def test_sin_doc_ni_inicial_degrada_pero_sigue_clasificando(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_INICIAL", str(tmp_path / "inicial-vacia"))
    ej = _ejecutor_que_devuelve('{"marca": "claro-sports"}')
    marca = clasificador_marca.clasificar_marca(
        "Gol agónico", "", _CANDIDATAS, fallback="unotv", ejecutor=ej,
    )
    assert marca == "claro-sports"
    p = ej.llamadas[0]
    assert p == ""  # sin plantilla no hay prompt; nunca quedan marcadores crudos

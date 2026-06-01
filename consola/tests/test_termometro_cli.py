"""Tests del CLI `keni-termometro` (cron 07:00). OFFLINE: nunca se llama a claude ni a la red.

Cubre:
  - reunir_noticias_rss: formatea items de feeds activos (descargador mockeado).
  - generar_termometro: corre la skill (runner mockeado), registra el historial.
  - main: dry-run imprime el prompt; con noticias-file genera y guarda; errores claros.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from keni_consola import repos, termometro, termometro_cli
from keni_consola.api import rss

from .conftest import sembrar_skills

# Reutilizamos la skill sembrada del test de la API.
from .test_api_termometro import _SKILL_TERMOMETRO

# IP publica literal (pasa el guard SSRF sin DNS), igual que en test_api_rss.
_URL_OK = "https://93.184.216.34/feed.xml"

_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Cumbre en Asia</title>
      <link>https://example.com/asia</link>
      <description>Líderes se reúnen en Tokio.</description>
    </item>
    <item>
      <title>Elecciones en Europa</title>
      <link>https://example.com/eu</link>
      <description>Resultados ajustados.</description>
    </item>
  </channel>
</rss>
"""

# Salida canned de claude (--output-format json): objeto result con el documento.
_DOC = "✅ Termómetro listo.\n\nPORTADA\nTermómetro mundial · 2026-05-25\n"
_STDOUT_CLAUDE = json.dumps(
    {"type": "result", "subtype": "success", "is_error": False, "result": _DOC,
     "num_turns": 1, "total_cost_usd": 0.02}
)


def _sembrar_termometro() -> None:
    sembrar_skills(Path(os.environ["KENI_SKILLS_DIR"]), _SKILL_TERMOMETRO)


def _claude_fake(salida: str):
    def fake(prompt, *, cwd, timeout):  # noqa: ANN001
        return salida
    return fake


# --------------------------------------------------------------------------- #
# reunir_noticias_rss                                                          #
# --------------------------------------------------------------------------- #


def test_reunir_noticias_rss_formatea(entorno, monkeypatch):
    repos.crear_fuente_rss("Internacional", _URL_OK, marca="")
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_XML)
    texto = termometro_cli.reunir_noticias_rss(limite=10)
    assert "- Cumbre en Asia (Internacional)" in texto
    assert "https://example.com/asia" in texto
    assert "Elecciones en Europa" in texto


def test_reunir_noticias_rss_respeta_limite(entorno, monkeypatch):
    repos.crear_fuente_rss("Internacional", _URL_OK)
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_XML)
    texto = termometro_cli.reunir_noticias_rss(limite=1)
    assert texto.count("\n- ") == 0  # una sola linea
    assert texto.startswith("- ")


def test_reunir_noticias_rss_sin_feeds_vacio(entorno):
    assert termometro_cli.reunir_noticias_rss() == ""


# --------------------------------------------------------------------------- #
# generar_termometro                                                          #
# --------------------------------------------------------------------------- #


def test_generar_dry_run_no_llama_claude(entorno, monkeypatch):
    _sembrar_termometro()
    # Si llamara a claude, esto reventaria el test.
    monkeypatch.setattr(termometro_cli, "_ejecutar_claude", _claude_fake("NO DEBERIA LLAMARSE"))
    res = termometro_cli.generar_termometro(
        marca="unotv", noticias="Asia: algo.", numero="5", dry_run=True
    )
    assert res["dry_run"] is True
    assert "Termómetro" in res["prompt"]
    assert "Asia: algo." in res["prompt"]


def test_generar_registra_historial(entorno, monkeypatch):
    _sembrar_termometro()
    monkeypatch.setattr(termometro_cli, "_ejecutar_claude", _claude_fake(_STDOUT_CLAUDE))
    res = termometro_cli.generar_termometro(marca="unotv", noticias="Asia: algo.\nEuropa: otra.")
    assert "documento" in res
    assert res["verdicto"] == "listo"
    assert res["historial_id"]
    entradas = repos.listar_historial_skills()
    assert any(e["skill"] == "termometro-mundial" for e in entradas)


def test_generar_funciona_sin_catalogo_de_skills(entorno):
    # El prompt del termometro viaja en la semilla del paquete: se arma sin catalogo de skills.
    res = termometro_cli.generar_termometro(marca="unotv", noticias="algo", dry_run=True)
    assert res["dry_run"] is True
    assert "Termómetro" in res["prompt"]


# --------------------------------------------------------------------------- #
# main (CLI)                                                                   #
# --------------------------------------------------------------------------- #


def test_main_dry_run_imprime_prompt(entorno, monkeypatch, capsys, tmp_path):
    _sembrar_termometro()
    noticias = tmp_path / "hoy.txt"
    noticias.write_text("China: algo grande.\nEEUU: otra cosa.", encoding="utf-8")
    rc = termometro_cli.main(["--marca", "unotv", "--noticias-file", str(noticias), "--dry-run"])
    assert rc == 0
    salida = capsys.readouterr().out
    assert "Termómetro" in salida
    assert "China: algo grande." in salida


def test_main_genera_desde_archivo(entorno, monkeypatch, capsys, tmp_path):
    _sembrar_termometro()
    monkeypatch.setattr(termometro_cli, "_ejecutar_claude", _claude_fake(_STDOUT_CLAUDE))
    noticias = tmp_path / "hoy.txt"
    noticias.write_text("China: algo grande.", encoding="utf-8")
    rc = termometro_cli.main(["--marca", "unotv", "--noticias-file", str(noticias)])
    assert rc == 0
    assert "Termómetro generado para unotv" in capsys.readouterr().out
    assert any(e["skill"] == "termometro-mundial" for e in repos.listar_historial_skills())


def test_main_sin_marca_error(entorno, capsys):
    _sembrar_termometro()
    # Sin marca en config ni en flag -> error claro, rc=1.
    rc = termometro_cli.main(["--noticias-file", "/tmp/no-importa.txt"])
    assert rc == 1
    assert "marca" in capsys.readouterr().err.lower()


def test_main_usa_marca_de_la_config(entorno, monkeypatch, capsys, tmp_path):
    _sembrar_termometro()
    termometro.guardar({"marca": "claro-sports"})
    monkeypatch.setattr(termometro_cli, "_ejecutar_claude", _claude_fake(_STDOUT_CLAUDE))
    noticias = tmp_path / "hoy.txt"
    noticias.write_text("Asia: algo.", encoding="utf-8")
    rc = termometro_cli.main(["--noticias-file", str(noticias)])
    assert rc == 0
    assert "claro-sports" in capsys.readouterr().out


def test_main_sin_noticias_error(entorno, capsys):
    _sembrar_termometro()
    # marca por flag, pero sin feeds RSS ni archivo -> sin noticias -> rc=1.
    rc = termometro_cli.main(["--marca", "unotv"])
    assert rc == 1
    assert "noticias" in capsys.readouterr().err.lower()

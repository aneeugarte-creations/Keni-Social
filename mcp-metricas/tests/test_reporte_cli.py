"""CLI de reporte (`keni-reporte` / `keni_metricas.reporte.main`).

Ejercita la CLI end-to-end sobre la fuente `muestra` (offline, sin red): apunta
el config a un archivo inexistente para forzar la fuente de muestra y desactiva
el historico para que el resultado sea determinista. Verificamos estructura y
secciones, no textos exactos fragiles.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from keni_metricas import reporte

# Nº esperado de filas marca x plataforma en la fuente de muestra. Cada marca
# aporta tantas filas como plataformas tenga configuradas (5+5+4+5+4+3 = 26).
FILAS_PLATAFORMA_MUESTRA = 5 + 5 + 4 + 5 + 4 + 3
MARCAS_MUESTRA = 6


@pytest.fixture(autouse=True)
def _entorno_offline(monkeypatch, tmp_path):
    # fuente de muestra (config inexistente) e historico apagado => determinista, sin red
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")


def test_formato_json_imprime_json_valido(capsys):
    rc = reporte.main(["--formato", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)  # parsea o falla
    assert isinstance(data, dict)
    # estructura minima del reporte consolidado
    for clave in ("rango", "fuente", "total", "cuentas"):
        assert clave in data
    assert data["rango"] == "mes"  # rango por defecto
    assert isinstance(data["cuentas"], list) and data["cuentas"]
    assert data["total"]["cuentas"] == len(data["cuentas"])
    # sin --picos no debe aparecer la seccion de picos
    assert "picos" not in data


def test_formato_md_imprime_markdown(capsys):
    rc = reporte.main(["--formato", "md"])
    assert rc == 0
    salida = capsys.readouterr().out
    # encabezados Markdown esperados (estructura, no texto literal completo)
    assert salida.lstrip().startswith("#")
    assert "## Total" in salida
    assert "**Visualizaciones:**" in salida


def test_md_es_el_formato_por_defecto(capsys):
    # sin --formato debe rendir Markdown, no JSON
    rc = reporte.main([])
    assert rc == 0
    salida = capsys.readouterr().out
    assert "## Total" in salida
    with pytest.raises(json.JSONDecodeError):
        json.loads(salida)


def test_rango_invalido_rc2_y_stderr(capsys):
    rc = reporte.main(["--rango", "trimestre"])
    assert rc == 2
    cap = capsys.readouterr()
    assert cap.err.strip()  # hay mensaje de error en stderr
    assert "trimestre" in cap.err
    assert cap.out == ""  # no se imprime reporte


def test_salida_escribe_archivo(capsys, tmp_path):
    destino = tmp_path / "reporte.md"
    rc = reporte.main(["--salida", str(destino)])
    assert rc == 0
    assert destino.exists()
    contenido = destino.read_text(encoding="utf-8")
    assert "## Total" in contenido
    # al escribir a archivo, stdout NO contiene el reporte (solo un aviso con la ruta)
    out = capsys.readouterr().out
    assert "## Total" not in out
    assert str(destino) in out


def test_salida_json_archivo_parseable(capsys, tmp_path):
    destino = tmp_path / "reporte.json"
    rc = reporte.main(["--formato", "json", "--salida", str(destino)])
    assert rc == 0
    data = json.loads(destino.read_text(encoding="utf-8"))
    assert data["total"]["cuentas"] == len(data["cuentas"])


def test_picos_anade_seccion_json(capsys):
    rc = reporte.main(["--formato", "json", "--picos"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "picos" in data
    picos = data["picos"]
    assert "alertas" in picos and isinstance(picos["alertas"], list)
    assert "umbral_pct" in picos


def test_picos_anade_seccion_markdown(capsys):
    rc = reporte.main(["--formato", "md", "--picos"])
    assert rc == 0
    salida = capsys.readouterr().out
    assert "## Total" in salida
    # la seccion de alertas se concatena al final del Markdown
    assert "Alertas" in salida


def test_sin_picos_no_hay_seccion_markdown(capsys):
    rc = reporte.main(["--formato", "md"])
    assert rc == 0
    assert "Alertas" not in capsys.readouterr().out


def test_md_muestra_nombre_legible_no_id(capsys):
    # el CLI de reporte debe imprimir el NOMBRE legible de la marca, no el id
    # crudo (alineado con el dashboard).
    rc = reporte.main(["--formato", "md"])
    assert rc == 0
    salida = capsys.readouterr().out
    assert "## Claro Sports" in salida
    assert "## claro_sports" not in salida


def test_md_picos_acotados_a_top_n(capsys):
    # con --picos, el reporte no debe volcar todas las alertas planas: se acota
    # a un top-N y se resume el resto en una linea.
    from keni_metricas.formato import PICOS_VISIBLES

    rc = reporte.main(["--formato", "md", "--picos"])
    assert rc == 0
    salida = capsys.readouterr().out
    seccion = salida[salida.index("## Alertas") :]
    lineas_alerta = [ln for ln in seccion.splitlines() if ln.startswith(("- 🔼", "- 📈", "- 📉"))]
    assert lineas_alerta, "la muestra deberia producir alertas"
    assert len(lineas_alerta) <= PICOS_VISIBLES
    # las alertas tambien usan el nombre legible
    assert "claro_sports" not in seccion


def test_formato_csv_es_parseable_con_encabezados_y_filas(capsys):
    # --formato csv debe emitir un CSV bien formado: encabezados en español y el
    # nº de filas esperado (marcas x plataformas + un TOTAL por marca + 1 global).
    rc = reporte.main(["--formato", "csv"])
    assert rc == 0
    salida = capsys.readouterr().out
    filas = list(csv.reader(io.StringIO(salida)))
    assert filas[0] == [
        "marca",
        "plataforma",
        "visualizaciones",
        "alcance",
        "interacciones",
        "engagement_pct",
    ]
    cuerpo = filas[1:]
    esperadas = FILAS_PLATAFORMA_MUESTRA + MARCAS_MUESTRA + 1  # +totales por marca +global
    assert len(cuerpo) == esperadas
    # una fila TOTAL por marca + el total global => MARCAS + 1
    totales = [f for f in cuerpo if f[1] == "TOTAL"]
    assert len(totales) == MARCAS_MUESTRA + 1
    # la ultima fila es el total global (marca y plataforma = TOTAL)
    assert cuerpo[-1][0] == "TOTAL" and cuerpo[-1][1] == "TOTAL"


def test_formato_csv_usa_nombre_legible_no_id(capsys):
    # el CSV debe traer el NOMBRE legible de la marca, no el id crudo.
    rc = reporte.main(["--formato", "csv"])
    assert rc == 0
    salida = capsys.readouterr().out
    marcas = {f[0] for f in csv.reader(io.StringIO(salida))}
    assert "Claro Sports" in marcas
    assert "claro_sports" not in marcas


def test_formato_csv_salida_escribe_archivo_parseable(capsys, tmp_path):
    destino = tmp_path / "reporte.csv"
    rc = reporte.main(["--formato", "csv", "--salida", str(destino)])
    assert rc == 0
    assert destino.exists()
    # el archivo debe ser CSV parseable con los mismos encabezados
    with destino.open(encoding="utf-8", newline="") as fh:
        filas = list(csv.reader(fh))
    assert filas[0][0] == "marca" and filas[0][1] == "plataforma"
    assert len(filas) - 1 == FILAS_PLATAFORMA_MUESTRA + MARCAS_MUESTRA + 1
    # al escribir a archivo, stdout solo lleva el aviso de ruta (no el CSV)
    out = capsys.readouterr().out
    assert "marca,plataforma" not in out
    assert str(destino) in out


def test_csv_es_el_formato_csv_no_otro(capsys):
    # csv no debe colarse como json ni markdown.
    rc = reporte.main(["--formato", "csv"])
    assert rc == 0
    salida = capsys.readouterr().out
    assert "## Total" not in salida
    with pytest.raises(json.JSONDecodeError):
        json.loads(salida)

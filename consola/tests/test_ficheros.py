"""Tests de historial de prompts: layout, round-trip, orden, validación, atomicidad e índice."""

from __future__ import annotations

import time

import pytest
import yaml

from keni_consola import ficheros, indice, repos


@pytest.fixture
def base(monkeypatch, tmp_path):
    """Aisla la raiz de datos de ficheros y el indice en tmp."""
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    return tmp_path


def _ruta_hist(base, marca, hid):
    """Ruta del .yaml de una entrada de historial (vive bajo historial/<YYYY>/<MM>/)."""
    hits = list((base / "datos" / marca / "historial").rglob(f"{hid}.yaml"))
    assert len(hits) == 1, hits
    return hits[0]


# --------------------------------------------------------------------------- #
# Layout: agente = marca = carpeta (+ marca.yaml / CLAUDE.md)                  #
# --------------------------------------------------------------------------- #


def test_carpeta_marca_siembra_meta_y_claude(base):
    hid = repos.registrar_historial_prompt("copy-desde-nota", "unotv", "Hola")
    carpeta = base / "datos" / "unotv"
    assert carpeta.is_dir()
    assert (carpeta / "marca.yaml").is_file()
    assert (carpeta / "CLAUDE.md").is_file()
    meta = yaml.safe_load((carpeta / "marca.yaml").read_text())
    assert meta["id"] == "unotv"
    assert meta["etiqueta"] == "UnoTV"
    assert meta["id_metricas"] == "unotv"
    # El YAML del historial existe y NO repite id ni marca dentro (id=nombre, marca=carpeta).
    cuerpo = yaml.safe_load(_ruta_hist(base, "unotv", hid).read_text())
    assert "id" not in cuerpo
    assert "marca" not in cuerpo
    assert cuerpo["prompt"] == "copy-desde-nota"


# --------------------------------------------------------------------------- #
# Round-trip: crear -> .yaml legible -> editar a mano -> repos lo lee          #
# --------------------------------------------------------------------------- #


def test_round_trip_historial(base):
    hid = repos.registrar_historial_prompt(
        "copy-desde-nota", "unotv", "Cuerpo largo\nmultilinea", titulo="T",
        piezas=[{"red": "x", "contenido": "c", "caracteres": 1}],
    )
    ruta = _ruta_hist(base, "unotv", hid)
    # Editamos el YAML A MANO (como haria una persona en su editor).
    datos = yaml.safe_load(ruta.read_text())
    datos["titulo"] = "Editado a mano"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False))
    # repos lo lee actualizado (re-indexa por mtime distinto).
    leido = repos.obtener_historial_prompt(hid)
    assert leido["titulo"] == "Editado a mano"
    assert leido["resultado"] == "Cuerpo largo\nmultilinea"
    assert leido["piezas"][0]["red"] == "x"


def test_contenido_largo_en_bloque_literal(base):
    largo = "linea1\nlinea2\nlinea3 con texto\n"
    hid = repos.registrar_historial_prompt("p", "unotv", largo)
    texto = _ruta_hist(base, "unotv", hid).read_text()
    # PyYAML usa bloque '|' para multilinea: el texto crudo aparece sin escapes \n.
    assert "linea1" in texto and "\\n" not in texto
    assert repos.obtener_historial_prompt(hid)["resultado"] == largo


def test_historial_round_trip_y_layout_por_fecha(base):
    hid = repos.registrar_historial_prompt(
        "copy-desde-nota", "unotv", "Resultado largo\ncon saltos", titulo="T",
        piezas=[{"red": "x", "contenido": "c", "caracteres": 1}],
    )
    leido = repos.obtener_historial_prompt(hid)
    assert leido["prompt"] == "copy-desde-nota"
    assert leido["piezas"][0]["red"] == "x"
    # Sin metricas => None.
    assert leido["metricas"] is None
    # Vive bajo historial/<YYYY>/<MM>/<id>.yaml
    encontrados = list((base / "datos" / "unotv" / "historial").rglob(f"{hid}.yaml"))
    assert len(encontrados) == 1


def test_historial_guarda_y_devuelve_metricas(base):
    metricas = {"tokens_in": 10, "tokens_out": 5, "num_turns": 1,
                "total_cost_usd": 0.02, "duration_ms": 99, "modelo": "m"}
    hid = repos.registrar_historial_prompt(
        "copy-desde-nota", "unotv", "RES", metricas=metricas
    )
    leido = repos.obtener_historial_prompt(hid)
    assert leido["metricas"] == metricas
    assert repos.listar_historial_prompts()[0]["metricas"] == metricas


# --------------------------------------------------------------------------- #
# Orden por fecha-hora (mas reciente primero, determinista)                    #
# --------------------------------------------------------------------------- #


def test_orden_historial_por_fecha_hora(base):
    a = repos.registrar_historial_prompt("p", "unotv", "A")
    time.sleep(1.05)  # fecha_creacion tiene resolucion de segundos
    b = repos.registrar_historial_prompt("p", "unotv", "B")
    ids = [h["id"] for h in repos.listar_historial_prompts()]
    # Mas reciente primero (B antes que A).
    assert ids.index(b) < ids.index(a)


# --------------------------------------------------------------------------- #
# Validacion: YAML corrupto se OMITE sin romper                                #
# --------------------------------------------------------------------------- #


def test_yaml_corrupto_se_omite(base):
    ok = repos.registrar_historial_prompt("p", "unotv", "Buena")
    mala = repos.registrar_historial_prompt("p", "unotv", "Mala")
    # Corrompemos el YAML de 'mala' a mano.
    _ruta_hist(base, "unotv", mala).write_text(":\n  - [esto no es yaml valido")
    ids = {h["id"] for h in repos.listar_historial_prompts()}
    assert ok in ids
    assert mala not in ids  # omitida, no rompe el listado
    assert repos.obtener_historial_prompt(mala) is None


# --------------------------------------------------------------------------- #
# Escritura atomica (no quedan .tmp)                                          #
# --------------------------------------------------------------------------- #


def test_escritura_no_deja_temporales(base):
    for i in range(5):
        repos.registrar_historial_prompt("p", "unotv", f"R{i}")
    tmp = list((base / "datos").rglob(".tmp-*"))
    assert tmp == []
    # Y los .yaml definitivos si estan.
    yamls = list((base / "datos" / "unotv" / "historial").rglob("*.yaml"))
    assert len(yamls) == 5


# --------------------------------------------------------------------------- #
# Regeneracion del indice si se borra                                         #
# --------------------------------------------------------------------------- #


def test_indice_se_regenera_si_se_borra(base):
    a = repos.registrar_historial_prompt("p", "unotv", "A")
    b = repos.registrar_historial_prompt("p", "claro-sports", "B")
    # Borra el indice (NO es la verdad): los YAML siguen en disco.
    indice.ruta_indice().unlink()
    # Listar lo reconstruye desde los ficheros.
    ids = {h["id"] for h in repos.listar_historial_prompts()}
    assert {a, b} <= ids
    # Y obtener por id tambien funciona tras el borrado.
    indice.ruta_indice().unlink()
    assert repos.obtener_historial_prompt(a)["resultado"] == "A"

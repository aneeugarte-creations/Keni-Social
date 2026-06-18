"""Fachada `servicio`: el contrato estable que consume la Consola (H1).

TODO OFFLINE: `KENI_METRICAS_CONFIG` apunta a un archivo inexistente => fuente de
muestra; nunca toca la red. Cubre lo que la Consola consume: rangos, fuente activa,
cuentas, reporte (con `fuente`), exports y la gestion de config (leer estado +
escribir fuente/alcance sin tocar credenciales).
"""

from __future__ import annotations

import json

import pytest

from keni_metricas import servicio
from keni_metricas.servicio import ConfigInvalida, CuentaNoEncontrada


@pytest.fixture
def muestra(monkeypatch, tmp_path):
    """Fuente de muestra aislada (sin config en disco, sin env vars de marcas).

    La fuente única por defecto ahora es `metricool`; para probar la demo offline
    fijamos `KENI_METRICAS_FUENTE=muestra` explícitamente.
    """
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    return tmp_path


# --- Constantes re-exportadas -------------------------------------------------


def test_rangos_validos_expone_los_del_schema(muestra):
    assert "semana" in servicio.RANGOS_VALIDOS
    assert "mes" in servicio.RANGOS_VALIDOS
    assert "anio" in servicio.RANGOS_VALIDOS  # "Último año" es un rango valido de entrada


def test_precalentar_es_subconjunto_estrecho_de_validos(muestra):
    # El daemon precalienta solo las ventanas rodantes baratas: ni los duplicados
    # "7d"/"30d" ni el costoso "anio" (se rellenan en caliente al primer uso).
    assert servicio.RANGOS_PRECALENTAR == ("semana", "mes")
    assert {"7d", "30d", "anio"}.isdisjoint(servicio.RANGOS_PRECALENTAR)
    assert set(servicio.RANGOS_PRECALENTAR) <= set(servicio.RANGOS_VALIDOS)


def test_fuentes_disponibles(muestra):
    # `metricool` (consumidor de la API REST de Metricool, ADR 0005 §B) se suma a
    # las fuentes válidas junto a `muestra` (demo) y `real` (adaptadores propios).
    assert set(servicio.FUENTES_DISPONIBLES) == {"muestra", "metricool", "real"}


# --- Lectura de metricas ------------------------------------------------------


def test_nombre_fuente_es_muestra(muestra):
    assert servicio.nombre_fuente() == "muestra"


def test_cuentas_disponibles_devuelve_pares(muestra):
    cuentas = servicio.cuentas_disponibles()
    assert cuentas, "la muestra debe traer cuentas"
    assert all(isinstance(par, tuple) and len(par) == 2 for par in cuentas)
    ids = {cid for cid, _ in cuentas}
    assert "claro_sports" in ids


def test_construir_reporte_incluye_fuente_y_total(muestra):
    rep = servicio.construir_reporte("mes")
    assert rep["fuente"] == "muestra"
    assert "total" in rep
    assert "cuentas" in rep


def test_construir_reporte_acotado_a_una_marca(muestra):
    rep = servicio.construir_reporte("mes", marca="claro_sports")
    ids = {f["resumen"]["cuenta"] for f in rep["cuentas"]}
    assert ids == {"claro_sports"}


def test_construir_reporte_rango_invalido_lanza_valueerror(muestra):
    with pytest.raises(ValueError):
        servicio.construir_reporte("trimestre")


def test_reporte_csv_y_markdown_son_texto(muestra):
    assert "claro_sports" in servicio.reporte_csv("mes") or servicio.reporte_csv("mes")
    md = servicio.reporte_markdown("mes")
    assert isinstance(md, str) and md.strip()


def test_reporte_json_es_json_valido_con_fuente(muestra):
    rep = json.loads(servicio.reporte_json("mes"))
    assert rep["fuente"] == "muestra"


# --- Gestion de configuracion -------------------------------------------------


def test_instantanea_config_sin_credenciales(muestra):
    estado = servicio.instantanea_config()
    assert estado["fuente"] == "muestra"
    assert estado["marcas"] == []
    assert isinstance(estado["marcas_disponibles"], list)
    # presencia de credenciales: ninguna en la muestra (solo presencia, nunca valor)
    assert estado["credenciales_presentes"] == {
        "meta": False,
        "youtube": False,
        "x": False,
        "tiktok": False,
    }


def test_guardar_fuente_y_alcance_escribe_y_preserva(muestra, monkeypatch):
    ruta = muestra / "config.toml"
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    servicio.guardar_fuente_y_alcance("muestra", ["claro_sports"])
    assert ruta.exists()
    texto = ruta.read_text(encoding="utf-8")
    assert "claro_sports" in texto
    # releer via la fachada refleja el alcance guardado
    estado = servicio.instantanea_config()
    assert estado["marcas"] == ["claro_sports"]


def test_guardar_fuente_invalida_lanza_valueerror(muestra, monkeypatch):
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(muestra / "config.toml"))
    with pytest.raises(ValueError):
        servicio.guardar_fuente_y_alcance("inexistente", [])


def test_alcance_vacio_borra_marcas(muestra, monkeypatch):
    ruta = muestra / "config.toml"
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    servicio.guardar_fuente_y_alcance("muestra", ["claro_sports"])
    servicio.guardar_fuente_y_alcance("muestra", [])
    assert servicio.instantanea_config()["marcas"] == []


def test_instantanea_config_propaga_config_invalida(muestra, monkeypatch):
    ruta = muestra / "config.toml"
    ruta.write_text('fuente = "muestra"\n[[cuenta]\n', encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    with pytest.raises(ConfigInvalida):
        servicio.instantanea_config()


def test_listado_piezas_expone_campo_texto(muestra):
    # El listado SIEMPRE expone la clave `texto` (caption completo) además del `titulo`
    # corto: es el insumo del detector de hashtags de campaña. Las fuentes reales lo
    # rellenan con el caption; la muestra no inventa hashtags (queda vacío).
    piezas = servicio.construir_listado_piezas("mes")
    assert piezas, "la muestra debe emitir piezas"
    assert all("texto" in p for p in piezas)


def test_listado_piezas_expone_alcance(muestra):
    # El listado SIEMPRE expone la clave `alcance` (usuarios únicos): un entero para las
    # piezas de Meta (FB/IG), None para el resto (degradación honesta, nunca un 0 falso).
    piezas = servicio.construir_listado_piezas("mes")
    assert all("alcance" in p for p in piezas)
    meta = [p for p in piezas if p["red"] in ("facebook", "instagram")]
    assert meta, "la muestra debe incluir piezas de Meta"
    assert all(isinstance(p["alcance"], int) for p in meta)
    no_meta = [p for p in piezas if p["red"] not in ("facebook", "instagram")]
    assert all(p["alcance"] is None for p in no_meta)


def test_excepciones_reexportadas_son_las_del_dominio():
    # La Consola captura estas desde la fachada; deben ser las clases reales.
    from keni_metricas.config import ConfigInvalida as RealConfigInvalida
    from keni_metricas.fuentes.base import CuentaNoEncontrada as RealCuentaNoEncontrada

    assert ConfigInvalida is RealConfigInvalida
    assert CuentaNoEncontrada is RealCuentaNoEncontrada

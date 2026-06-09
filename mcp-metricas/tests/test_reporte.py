from __future__ import annotations

import csv
import io

import pytest

from keni_metricas.formato import miles
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.reporte import (
    CSV_ENCABEZADOS,
    construir_reporte,
    render_csv,
    render_markdown,
)


def test_reporte_recorre_todas_las_cuentas():
    rep = construir_reporte(FuenteMuestra(), "mes", top=3)
    assert rep["total"]["cuentas"] == 7
    assert rep["total"]["visualizaciones"] > 0
    # engagement global = None: combina marcas y plataformas con bases de
    # visualizacion heterogeneas; no se divide sobre bases incomparables (#138).
    assert rep["total"]["engagement_pct"] is None
    # total = suma de las marcas
    suma = sum(f["resumen"]["visualizaciones"] for f in rep["cuentas"])
    assert rep["total"]["visualizaciones"] == suma
    # cada marca trae sus mejores piezas (solo el top, aunque se cuenten todas)
    assert all(len(f["mejores_piezas"]) == 3 for f in rep["cuentas"])
    # publicaciones = nº TOTAL de piezas del periodo (no solo el top); > nº de marcas.
    assert rep["total"]["publicaciones"] > rep["total"]["cuentas"]


def test_render_markdown():
    md = render_markdown(construir_reporte(FuenteMuestra(), "semana", top=2))
    assert md.startswith("# Reporte de redes — semana")
    assert "## Total" in md


def test_reporte_muestra_lleva_aviso_destacado():
    # #131: con fuente de muestra, el reporte debe AVISAR de forma destacada que
    # los datos son sinteticos, no solo en el campo `fuente`.
    rep = construir_reporte(FuenteMuestra(), "mes", top=1)
    assert "aviso" in rep and "MUESTRA" in rep["aviso"].upper()
    md = render_markdown(rep)
    # el banner va al inicio (antes de la linea de "Generado")
    assert "DATOS DE MUESTRA" in md
    assert md.index("DATOS DE MUESTRA") < md.index("Generado")


def test_reporte_fuente_real_sin_aviso_de_muestra():
    # #131: una fuente real (nombre != "muestra") NO debe llevar el aviso ni el
    # banner; el comportamiento de datos reales no cambia.
    rep = construir_reporte(FuenteMuestra(), "mes", top=1)
    rep["fuente"] = "real"
    rep.pop("aviso", None)
    md = render_markdown(rep)
    assert "DATOS DE MUESTRA" not in md


def test_reporte_expone_nombres_legibles():
    # el reporte debe traer el mapa id->nombre legible (mismo origen que el
    # dashboard) para que el render no imprima el id crudo.
    rep = construir_reporte(FuenteMuestra(), "mes", top=1)
    assert rep["nombres"]["claro_sports"] == "Claro Sports"


def test_render_markdown_cabecera_usa_nombre_legible_no_id():
    # la cabecera de marca debe ser el NOMBRE legible ("## Claro Sports"), no el
    # id crudo ("## claro_sports").
    md = render_markdown(construir_reporte(FuenteMuestra(), "mes", top=1))
    assert "## Claro Sports" in md
    # el id crudo no debe aparecer como cabecera de marca
    assert "## claro_sports" not in md


def test_render_markdown_usa_separador_es_mx_punto_no_coma():
    # D1: el texto debe usar el separador de miles es-MX (punto), MISMA fuente de
    # verdad (`formato.miles`) que el dashboard. No debe filtrarse la coma de
    # Python (`f"{n:,}"`) que se usaba antes.
    rep = construir_reporte(FuenteMuestra(), "mes", top=1)
    md = render_markdown(rep)
    total_vis = rep["total"]["visualizaciones"]
    assert total_vis >= 1000, "la muestra debe dar cifras con separador visible"
    assert miles(total_vis) in md  # formato unico es-MX (punto)
    assert f"{total_vis:,}" not in md  # la coma de Python no debe aparecer


def test_rango_invalido_propaga():
    with pytest.raises(ValueError):
        construir_reporte(FuenteMuestra(), "trimestre")


def test_render_csv_estructura_y_totales():
    # render_csv: encabezados en español + una fila por marca x plataforma + un
    # TOTAL por marca + un total global; y el TOTAL por marca cuadra con la suma
    # de sus plataformas.
    rep = construir_reporte(FuenteMuestra(), "mes", top=1)
    filas = list(csv.reader(io.StringIO(render_csv(rep))))

    assert filas[0] == CSV_ENCABEZADOS
    cuerpo = filas[1:]

    n_plataformas = sum(len(f["resumen"]["por_plataforma"]) for f in rep["cuentas"])
    n_marcas = len(rep["cuentas"])
    assert len(cuerpo) == n_plataformas + n_marcas + 1  # +TOTAL por marca +global

    # ultima fila = total global, debe coincidir con rep["total"]
    glob = cuerpo[-1]
    assert glob[0] == "TOTAL" and glob[1] == "TOTAL"
    assert int(glob[2]) == rep["total"]["visualizaciones"]
    assert int(glob[3]) == rep["total"]["alcance"]
    assert int(glob[4]) == rep["total"]["interacciones"]

    # el TOTAL de la primera marca = suma de sus filas de plataforma
    primera = rep["cuentas"][0]["resumen"]
    marca = rep["nombres"][primera["cuenta"]]
    plats = [f for f in cuerpo if f[0] == marca and f[1] != "TOTAL"]
    total_marca = next(f for f in cuerpo if f[0] == marca and f[1] == "TOTAL")
    assert sum(int(f[2]) for f in plats) == int(total_marca[2])
    assert int(total_marca[2]) == primera["visualizaciones"]


def test_render_csv_usa_nombre_legible_no_id():
    rep = construir_reporte(FuenteMuestra(), "mes", top=1)
    salida = render_csv(rep)
    assert "Claro Sports" in salida
    # el id crudo no debe aparecer en el CSV
    assert "claro_sports" not in salida

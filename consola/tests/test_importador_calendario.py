"""Tests del parser PURO del importador de calendario (sin tocar DB ni red).

Cubre: mapeo flexible de cabeceras (sinonimos es/en, acentos), fechas en varios formatos,
prioridad, deteccion de compromiso, normalizacion de redes y marcas, y errores honestos
(fila sin titulo, sin cabecera de titulo, archivo vacio).
"""

from __future__ import annotations

import io

import pytest

from keni_consola import importador_calendario as ic


def _csv(texto: str) -> bytes:
    return texto.encode("utf-8")


def test_csv_basico_mapea_columnas_y_normaliza():
    data = _csv(
        "Tema,Fecha,Marca,Redes,Prioridad,Compromiso,Notas\n"
        "Final de la Liga MX,2026-06-01,Claro Sports,\"Instagram, X\",alta,si,Cobertura en vivo\n"
    )
    filas, errores = ic.parsear(data, nombre="plan.csv")
    assert errores == []
    assert len(filas) == 1
    f = filas[0]
    assert f.titulo == "Final de la Liga MX"
    assert f.fecha == "2026-06-01"
    assert f.marca_id == "claro-sports"  # reconocida por etiqueta "Claro Sports"
    assert f.redes == ["instagram", "x"]
    assert f.prioridad == "alta"
    assert f.compromiso is True
    assert f.green is False
    assert f.notas == "Cobertura en vivo"


def test_green_se_detecta_por_sinonimos_es_en():
    for cabecera in ("Green", "Verde", "Green List", "Lista verde"):
        data = _csv(f"Tema,{cabecera}\nTema del equipo,si\n")
        filas, errores = ic.parsear(data, nombre="x.csv")
        assert errores == []
        assert filas[0].green is True, cabecera


def test_green_falso_por_defecto_y_con_valor_negativo():
    data = _csv("Tema,Green\nUno,\nDos,no\n")
    filas, _ = ic.parsear(data, nombre="x.csv")
    assert [f.green for f in filas] == [False, False]


def test_cabeceras_en_ingles_y_con_acentos():
    data = _csv("Título,Date,Account\nNota de prueba,01/06/2026,UnoTV\n")
    filas, errores = ic.parsear(data, nombre="x.csv")
    assert errores == []
    assert filas[0].titulo == "Nota de prueba"
    assert filas[0].fecha == "2026-06-01"  # dd/mm/yyyy mexicano
    assert filas[0].marca_id == "unotv"


def test_fecha_invalida_queda_vacia_sin_romper():
    data = _csv("Tema,Fecha\nAlgo,31/02/2026\nOtro,no-es-fecha\n")
    filas, _ = ic.parsear(data, nombre="x.csv")
    assert [f.fecha for f in filas] == ["", ""]
    assert [f.titulo for f in filas] == ["Algo", "Otro"]


def test_compromiso_sin_prioridad_sube_a_alta():
    data = _csv("Tema,Obligatorio\nGrito de Independencia,x\n")
    filas, _ = ic.parsear(data, nombre="x.csv")
    assert filas[0].compromiso is True
    assert filas[0].prioridad == "alta"


def test_prioridad_por_defecto_media_sin_compromiso():
    data = _csv("Tema\nRelleno evergreen\n")
    filas, _ = ic.parsear(data, nombre="x.csv")
    assert filas[0].prioridad == "media"
    assert filas[0].compromiso is False


def test_marca_desconocida_queda_vacia():
    data = _csv("Tema,Marca\nAlgo,MarcaInexistente\n")
    filas, _ = ic.parsear(data, nombre="x.csv")
    assert filas[0].marca_id == ""


def test_redes_desconocidas_se_descartan():
    data = _csv("Tema,Redes\nAlgo,\"Instagram, MySpace, web\"\n")
    filas, _ = ic.parsear(data, nombre="x.csv")
    assert filas[0].redes == ["instagram", "web"]


def test_fila_sin_titulo_es_error_y_no_rompe():
    data = _csv("Tema,Fecha\n,2026-06-01\nValida,2026-06-02\n")
    filas, errores = ic.parsear(data, nombre="x.csv")
    assert [f.titulo for f in filas] == ["Valida"]
    assert len(errores) == 1 and errores[0]["fila"] == 2


def test_sin_columna_de_titulo_devuelve_error():
    data = _csv("Fecha,Marca\n2026-06-01,UnoTV\n")
    filas, errores = ic.parsear(data, nombre="x.csv")
    assert filas == []
    assert errores and "titulo" in errores[0]["motivo"].lower()


def test_archivo_vacio_devuelve_error():
    filas, errores = ic.parsear(b"", nombre="x.csv")
    assert filas == []
    assert errores


def test_filas_en_blanco_se_ignoran():
    data = _csv("Tema\nUno\n\n\nDos\n")
    filas, errores = ic.parsear(data, nombre="x.csv")
    assert [f.titulo for f in filas] == ["Uno", "Dos"]
    assert errores == []


def test_separador_punto_y_coma():
    data = _csv("Tema;Fecha;Prioridad\nAlgo;2026-06-01;baja\n")
    filas, errores = ic.parsear(data, nombre="x.csv")
    assert errores == []
    assert filas[0].prioridad == "baja"


def test_xlsx_se_lee_igual_que_csv():
    openpyxl = pytest.importorskip("openpyxl")
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Tema", "Fecha", "Marca", "Compromiso"])
    hoja.append(["Partido estelar", "2026-07-04", "Claro Sports", "si"])
    buffer = io.BytesIO()
    libro.save(buffer)
    filas, errores = ic.parsear(buffer.getvalue(), nombre="plan.xlsx")
    assert errores == []
    assert filas[0].titulo == "Partido estelar"
    assert filas[0].fecha == "2026-07-04"
    assert filas[0].marca_id == "claro-sports"
    assert filas[0].compromiso is True


def test_xlsx_detectado_por_firma_pk_sin_extension():
    openpyxl = pytest.importorskip("openpyxl")
    libro = openpyxl.Workbook()
    libro.active.append(["Tema"])
    libro.active.append(["Sin extension"])
    buffer = io.BytesIO()
    libro.save(buffer)
    filas, _ = ic.parsear(buffer.getvalue(), nombre="archivo_sin_ext")
    assert filas[0].titulo == "Sin extension"


# --------------------------------------------------------------------------- #
# Extracción AGNÓSTICA de formato con Claude (parseo PURO de su respuesta +    #
# dispatch con ejecutor inyectado: no toca el binario `claude`).               #
# --------------------------------------------------------------------------- #


def test_parsear_respuesta_claude_objeto_filas():
    """Un objeto {"filas":[...]} de Claude se normaliza con las mismas reglas que un Excel."""
    texto = (
        '{"filas": [{"titulo": "Final de la Liga MX", "fecha": "2026-06-01", '
        '"marca": "Claro Sports", "redes": ["Instagram", "X"], "prioridad": "alta", '
        '"compromiso": true, "green": false, "notas": "Cobertura en vivo"}]}'
    )
    filas, errores = ic.parsear_respuesta_claude(texto)
    assert errores == []
    assert len(filas) == 1
    f = filas[0]
    assert f.titulo == "Final de la Liga MX"
    assert f.fecha == "2026-06-01"
    assert f.marca_id == "claro-sports"
    assert f.redes == ["instagram", "x"]
    assert f.prioridad == "alta"
    assert f.compromiso is True


def test_parsear_respuesta_claude_tolera_fences_y_array_desnudo():
    fenced = '```json\n[{"titulo": "Nota A"}, {"titulo": "Nota B"}]\n```'
    filas, errores = ic.parsear_respuesta_claude(fenced)
    assert [f.titulo for f in filas] == ["Nota A", "Nota B"]
    assert errores == []


def test_parsear_respuesta_claude_registro_sin_titulo_es_error_no_rompe():
    texto = '{"filas": [{"titulo": "Ok"}, {"fecha": "2026-01-01"}]}'
    filas, errores = ic.parsear_respuesta_claude(texto)
    assert [f.titulo for f in filas] == ["Ok"]
    assert len(errores) == 1


def test_parsear_respuesta_claude_basura_devuelve_error_honesto():
    filas, errores = ic.parsear_respuesta_claude("lo siento, no encontré un calendario")
    assert filas == []
    assert errores and "JSON" in errores[0]["motivo"]


def test_extraer_con_claude_usa_ejecutor_inyectado():
    """`extraer_con_claude` vuelca el archivo y normaliza lo que devuelva el ejecutor."""
    visto = {}

    def fake_ejecutor(prompt: str, carpeta: str) -> str:
        visto["prompt"] = prompt
        visto["carpeta"] = carpeta
        return '{"filas": [{"titulo": "Desde un PDF", "redes": ["TikTok"]}]}'

    filas, errores = ic.extraer_con_claude(
        b"%PDF-1.7 binario...", nombre="plan.pdf", ejecutor=fake_ejecutor
    )
    assert errores == []
    assert filas[0].titulo == "Desde un PDF"
    assert filas[0].redes == ["tiktok"]
    # El prompt apunta al archivo volcado en la carpeta temporal.
    assert "plan.pdf" in visto["prompt"]


def test_extraer_con_claude_ejecutor_que_falla_devuelve_error_legible():
    def ejecutor_roto(prompt: str, carpeta: str) -> str:
        raise RuntimeError("claude no disponible")

    filas, errores = ic.extraer_con_claude(b"x", nombre="x.bin", ejecutor=ejecutor_roto)
    assert filas == []
    assert errores and "IA" in errores[0]["motivo"]

"""Tests unitarios del parser de insumos del día. PURO (sin red, sin claude).

Cubre: _extraer_json_items, parsear_respuesta_haiku, extraer_insumos con ejecutor
inyectado, cajón desconocido, ejecutor que falla.
"""

from __future__ import annotations

import json

from keni_consola.dominio import ingesta as dom_ingesta
from keni_consola.dominio import recibir_parse as ip

# --------------------------------------------------------------------------- #
# Prompts por cajón (Biblioteca editable + fallback)                           #
# --------------------------------------------------------------------------- #


def test_prompt_archivo_inserta_ruta_y_contrato_json():
    # El prompt del cajón sale de la Biblioteca (semilla del paquete): inserta la RUTA donde
    # estaba el marcador (que NO debe quedar crudo) y conserva el contrato JSON {"items": [...]}.
    prompt = ip.construir_prompt_archivo("portal", "/tmp/insumo.txt")
    assert "/tmp/insumo.txt" in prompt
    assert ip._MARCA_RUTA not in prompt
    assert '{"items"' in prompt


def test_prompt_texto_incrusta_contenido():
    prompt = ip.construir_prompt_texto("corresponsales", "VOSOT CDMX (Ana) Marcha -Tengo material-")
    assert "VOSOT CDMX (Ana) Marcha" in prompt
    assert "INSUMO" in prompt  # delimitadores del bloque a procesar


def test_fallback_de_cajon_sale_de_la_semilla(monkeypatch):
    # Red de seguridad: si la lectura del store falla, el prompt sale de la SEMILLA del
    # paquete (sin strings duplicados en el código) y conserva el contrato JSON parseable.
    from keni_consola import libtexto

    def boom(_pid):
        raise RuntimeError("store roto")

    monkeypatch.setattr(libtexto, "cuerpo_efectivo", boom)
    fb = ip._prompt_de_cajon("eventos_claro", "/x")
    assert '{"items"' in fb and "/x" in fb


# --------------------------------------------------------------------------- #
# _extraer_json_items                                                          #
# --------------------------------------------------------------------------- #


def test_extrae_lista_items_directa():
    texto = json.dumps([{"titulo": "Nota A"}, {"titulo": "Nota B"}])
    resultado = ip._extraer_json_items(texto)
    assert resultado is not None
    assert len(resultado) == 2
    assert resultado[0]["titulo"] == "Nota A"


def test_extrae_items_dentro_de_wrapper():
    texto = json.dumps({"items": [{"titulo": "X"}, {"titulo": "Y"}]})
    resultado = ip._extraer_json_items(texto)
    assert resultado is not None
    assert len(resultado) == 2


def test_extrae_con_fence_json():
    texto = '```json\n{"items": [{"titulo": "Dentro fence"}]}\n```'
    resultado = ip._extraer_json_items(texto)
    assert resultado is not None
    assert resultado[0]["titulo"] == "Dentro fence"


def test_devuelve_none_cuando_basura():
    assert ip._extraer_json_items("lo siento, no encontré nada") is None
    assert ip._extraer_json_items("") is None


# --------------------------------------------------------------------------- #
# parsear_respuesta_haiku                                                      #
# --------------------------------------------------------------------------- #


def test_parsear_respuesta_haiku_normaliza_marca_valida():
    texto = json.dumps({"items": [
        {"titulo": "Nota deportes", "marca": "claro-sports", "tipo": "nota"},
    ]})
    items, errores = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001"
    )
    assert errores == []
    assert len(items) == 1
    assert items[0]["marca"] == "claro-sports"


def test_parsear_respuesta_haiku_normaliza_marca_por_etiqueta():
    """La IA puede devolver el nombre legible ("UnoTV") en vez del id."""
    texto = json.dumps({"items": [
        {"titulo": "Nota política", "marca": "UnoTV"},
    ]})
    items, errores = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001"
    )
    assert items[0]["marca"] == "unotv"


def test_parsear_respuesta_haiku_marca_defecto_rellena_sin_marca():
    """Ítem sin marca reconocida hereda la marca del lote (marca_defecto).

    Sin este fallback el ítem quedaba con marca "" y el filtro por marca del cajón
    (WHERE marca = ?) lo ocultaba: el síntoma de "los cajones no filtran por marca".
    """
    texto = json.dumps({"items": [
        {"titulo": "Nota sin marca clara"},
        {"titulo": "Marca no reconocida", "marca": "marca-inexistente"},
    ]})
    items, errores = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001",
        marca_defecto="claro-sports",
    )
    assert errores == []
    assert items[0]["marca"] == "claro-sports"
    assert items[1]["marca"] == "claro-sports"


def test_parsear_respuesta_haiku_marca_de_la_ia_prevalece_sobre_defecto():
    """Si la IA SÍ reconoce una marca, prevalece sobre marca_defecto."""
    texto = json.dumps({"items": [
        {"titulo": "Nota política", "marca": "unotv"},
    ]})
    items, _ = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001",
        marca_defecto="claro-sports",
    )
    assert items[0]["marca"] == "unotv"


def test_parsear_respuesta_haiku_sin_defecto_deja_marca_vacia():
    """Sin marca_defecto, un ítem sin marca reconocida queda con marca '' (comportamiento previo)."""
    texto = json.dumps({"items": [{"titulo": "Nota suelta"}]})
    items, _ = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001"
    )
    assert items[0]["marca"] == ""


def test_parsear_respuesta_haiku_omite_item_sin_titulo():
    texto = json.dumps({"items": [
        {"titulo": "", "resumen": "sin título"},
        {"titulo": "Con título"},
    ]})
    items, errores = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001"
    )
    assert len(items) == 1
    assert len(errores) == 1
    assert "título" in errores[0]["motivo"]


def test_parsear_respuesta_haiku_tipo_invalido_cae_a_nota():
    texto = json.dumps({"items": [
        {"titulo": "Item raro", "tipo": "DESCONOCIDO"},
    ]})
    items, _ = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001"
    )
    assert items[0]["tipo"] == "nota"


def test_cajon_notas_default_nota():
    """El cajón `notas` (Claro Sports) produce ítems tipo `nota` por defecto (van al pool)."""
    texto = json.dumps({"items": [{"titulo": "Gol de México en el último minuto"}]})
    items, _ = ip.parsear_respuesta_haiku(
        texto, cajon="notas", fecha="2026-06-05", lote_id="l001"
    )
    assert items[0]["tipo"] == "nota"


def test_cajon_contexto_default_contexto():
    """El cajón `contexto` produce ítems tipo `contexto` (guía editorial) por defecto."""
    texto = json.dumps({"items": [{"titulo": "Transmitimos la final a las 14:00"}]})
    items, _ = ip.parsear_respuesta_haiku(
        texto, cajon="contexto", fecha="2026-06-05", lote_id="l001"
    )
    assert items[0]["tipo"] == "contexto"


def test_contexto_es_tipo_valido_y_se_respeta():
    """`contexto` es un tipo válido: si la IA lo marca, NO se degrada al default del cajón."""
    texto = json.dumps({"items": [
        {"titulo": "No llamar 'Tri' a la selección", "tipo": "contexto"},
    ]})
    items, _ = ip.parsear_respuesta_haiku(
        texto, cajon="notas", fecha="2026-06-05", lote_id="l001"
    )
    assert items[0]["tipo"] == "contexto"


def test_noticia_item_de_insumo_excluye_eventos_y_contexto():
    """Eventos e indicaciones (contexto) NUNCA entran al pool de noticias; las notas sí."""
    base = {"titulo": "Resumen del partido", "marca": "claro-sports", "cajon": "notas"}
    assert dom_ingesta.noticia_item_de_insumo({**base, "tipo": "nota"}) is not None
    assert dom_ingesta.noticia_item_de_insumo({**base, "tipo": "evento"}) is None
    assert dom_ingesta.noticia_item_de_insumo({**base, "tipo": "contexto"}) is None


def test_parsear_respuesta_haiku_estado_material_normalizado():
    texto = json.dumps({"items": [
        {"titulo": "Corresponsal Oaxaca", "estado_material": "Tengo"},
        {"titulo": "Corresponsal CDMX", "estado_material": "ESPERO"},
        {"titulo": "Sin material", "estado_material": "???"},
    ]})
    items, _ = ip.parsear_respuesta_haiku(
        texto, cajon="corresponsales", fecha="2026-06-05", lote_id="l001"
    )
    assert items[0]["estado_material"] == "tengo"
    assert items[1]["estado_material"] == "espero"
    assert items[2]["estado_material"] == ""


def test_parsear_respuesta_haiku_json_invalido_devuelve_error():
    items, errores = ip.parsear_respuesta_haiku(
        "esto no es json", cajon="portal", fecha="2026-06-05", lote_id="l001"
    )
    assert items == []
    assert errores and "JSON" in errores[0]["motivo"]


def test_parsear_respuesta_haiku_truncado_avisa_y_no_silencia(caplog):
    """Un campo que supera su límite se recorta, con WARN y AVISO visible en `errores`."""
    import logging

    texto = json.dumps({"items": [
        {"titulo": "T" * 600, "resumen": "R" * 2500, "linea": "L" * 600},
    ]})
    with caplog.at_level(logging.WARNING, logger="keni_consola.dominio.recibir_parse"):
        items, errores = ip.parsear_respuesta_haiku(
            texto, cajon="portal", fecha="2026-06-05", lote_id="l001"
        )
    assert len(items) == 1
    assert len(items[0]["titulo"]) == 500
    assert len(items[0]["resumen"]) == 2000
    assert len(items[0]["linea"]) == 500
    # Los límites no se mueven; el recorte deja constancia (aviso por campo, fila 1).
    avisos = [e for e in errores if e.get("aviso")]
    assert {a["fila"] for a in avisos} == {1}
    motivos = " ".join(a["motivo"] for a in avisos)
    assert "titulo" in motivos and "resumen" in motivos and "linea" in motivos
    assert any("truncado" in r.message for r in caplog.records)


def test_parsear_respuesta_haiku_sin_truncado_no_deja_avisos():
    texto = json.dumps({"items": [{"titulo": "Corto", "resumen": "ok"}]})
    items, errores = ip.parsear_respuesta_haiku(
        texto, cajon="portal", fecha="2026-06-05", lote_id="l001"
    )
    assert len(items) == 1
    assert errores == []


def test_procesar_insumos_persiste_aviso_de_truncado_en_el_lote(monkeypatch):
    """El worker deja el lote `listo` y la constancia del recorte viaja en su campo `error`."""
    from keni_consola import repos

    lotes: list[tuple[str, dict]] = []
    monkeypatch.setattr(repos, "crear_insumo_items", lambda items: items)
    monkeypatch.setattr(repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(
        repos, "actualizar_insumo_lote", lambda lote_id, campos: lotes.append((lote_id, campos))
    )
    salida = json.dumps({"items": [{"titulo": "T" * 600}]})
    procesar = ip.construir_procesar_insumos(lote_id="l9", cajon="portal", fecha="2026-06-05")
    res = procesar(salida, None)
    assert res["estado"] == "listo"
    assert lotes and lotes[-1][0] == "l9"
    campos = lotes[-1][1]
    assert campos["estado"] == "listo"
    assert "titulo" in campos.get("error", "") and "Aviso" in campos.get("error", "")


# --------------------------------------------------------------------------- #
# extraer_insumos con ejecutor inyectado                                       #
# --------------------------------------------------------------------------- #


def _ejecutor_fake_portal(prompt: str, carpeta: str) -> str:
    return json.dumps({"items": [
        {"titulo": "Titular 1", "resumen": "Cuerpo de la nota", "marca": "unotv"},
        {"titulo": "Titular deportivo", "marca": "claro-sports"},
    ]})


def test_extraer_insumos_portal_ejecutor_inyectado():
    items, errores = ip.extraer_insumos(
        b"1.- Titular 1\nCuerpo de la nota\n2.- Titular deportivo",
        nombre="portal.txt",
        cajon="portal",
        fecha="2026-06-05",
        lote_id="lote_test",
        ejecutor=_ejecutor_fake_portal,
    )
    assert errores == []
    assert len(items) == 2
    assert items[0]["titulo"] == "Titular 1"
    assert items[0]["lote_id"] == "lote_test"
    assert items[0]["fecha"] == "2026-06-05"
    assert items[0]["cajon"] == "portal"
    assert items[1]["marca"] == "claro-sports"


def test_extraer_insumos_cajon_desconocido():
    items, errores = ip.extraer_insumos(
        b"texto",
        nombre="x.txt",
        cajon="inexistente",
        fecha="2026-06-05",
        lote_id="l001",
    )
    assert items == []
    assert errores and "Cajón desconocido" in errores[0]["motivo"]


def test_extraer_insumos_ejecutor_que_falla():
    def ejecutor_roto(prompt: str, carpeta: str) -> str:
        raise RuntimeError("claude no disponible")

    items, errores = ip.extraer_insumos(
        b"texto",
        nombre="agenda.pdf",
        cajon="reporteros",
        fecha="2026-06-05",
        lote_id="l001",
        ejecutor=ejecutor_roto,
    )
    assert items == []
    assert errores and "IA" in errores[0]["motivo"]


def test_extraer_insumos_eventos_claro_marca_siempre_claro():
    def ejecutor_eventos(prompt: str, carpeta: str) -> str:
        return json.dumps({"items": [
            {"titulo": "Chivas vs América", "hora": "20:00", "marca": "claro-sports"},
        ]})

    items, errores = ip.extraer_insumos(
        b"evento,hora\nChivas vs America,20:00",
        nombre="eventos.csv",
        cajon="eventos_claro",
        fecha="2026-06-05",
        lote_id="l002",
        ejecutor=ejecutor_eventos,
    )
    assert errores == []
    assert items[0]["tipo"] == "evento"
    assert items[0]["marca"] == "claro-sports"


def test_extraer_insumos_corresponsales_lugar_y_estado_material():
    def ejecutor_corr(prompt: str, carpeta: str) -> str:
        return json.dumps({"items": [
            {
                "titulo": "Disturbios en Oaxaca",
                "lugar": "Oaxaca",
                "estado_material": "tengo",
                "tipo": "cobertura",
            },
        ]})

    items, _ = ip.extraer_insumos(
        b"VOSOT OAXACA (J. CORTES) Disturbios - Tengo material y guion-",
        nombre="corresponsales.txt",
        cajon="corresponsales",
        fecha="2026-06-05",
        lote_id="l003",
        ejecutor=ejecutor_corr,
    )
    assert items[0]["lugar"] == "Oaxaca"
    assert items[0]["estado_material"] == "tengo"
    assert items[0]["tipo"] == "cobertura"

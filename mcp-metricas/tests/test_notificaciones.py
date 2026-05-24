from __future__ import annotations

import json

import httpx
import respx

from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.notificaciones import (
    construir_digest,
    enviar,
    formatear_payload,
    main,
)

WEBHOOK = "https://hooks.ejemplo.test/servicios/XYZ"


# --- funciones puras (sin red) ----------------------------------------------
def test_construir_digest_arma_picos():
    d = construir_digest(FuenteMuestra(), "semana", 50)
    assert d["fuente"] == FuenteMuestra().nombre
    assert d["rango"] == "semana"
    assert "alertas" in d["picos"]
    assert d["n_alertas"] == len(d["picos"]["alertas"])
    assert d["picos_markdown"].startswith("## Alertas")
    assert "resumen" not in d  # sin incluir_resumen


def test_construir_digest_con_resumen():
    d = construir_digest(FuenteMuestra(), "semana", 50, incluir_resumen=True)
    assert "resumen" in d
    t = d["resumen"]["total"]
    assert {"visualizaciones", "alcance", "interacciones", "engagement_pct", "cuentas"} <= t.keys()


def test_formatear_payload_slack_es_text():
    d = construir_digest(FuenteMuestra(), "semana", 50)
    p = formatear_payload(d, "slack")
    assert set(p.keys()) == {"text"}
    assert isinstance(p["text"], str)
    assert "alertas de redes" in p["text"]


def test_digest_texto_usa_nombre_legible_no_id():
    # el texto plano del digest (lo que ve un humano en Slack) debe mostrar el
    # NOMBRE legible de la marca, no el id crudo.
    d = construir_digest(FuenteMuestra(), "semana", 50)
    texto = formatear_payload(d, "slack")["text"]
    assert "Claro Sports" in texto
    assert "claro_sports" not in texto


def test_digest_texto_acota_picos_a_top_n():
    # el texto del digest no debe volcar las ~29 alertas planas: top-N + resumen.
    from keni_metricas.formato import PICOS_VISIBLES

    d = construir_digest(FuenteMuestra(), "semana", 50)
    assert d["n_alertas"] > PICOS_VISIBLES, "la muestra debe dar mas alertas que el top-N"
    texto = formatear_payload(d, "slack")["text"]
    lineas_alerta = [ln for ln in texto.splitlines() if ln.startswith(("- 🔼", "- 📈", "- 📉"))]
    assert len(lineas_alerta) <= PICOS_VISIBLES
    # y aparece la linea-resumen del resto colapsado
    n_resto = d["n_alertas"] - PICOS_VISIBLES
    assert any(str(n_resto) in ln and "mas" in ln for ln in texto.splitlines())


def test_digest_texto_usa_separador_es_mx_punto_no_coma():
    # D1: el resumen del digest usa el separador es-MX (punto), MISMA regla
    # (`formato.miles`) que el reporte/dashboard. La coma de Python no debe salir.
    from keni_metricas.formato import miles

    d = construir_digest(FuenteMuestra(), "mes", 50, incluir_resumen=True)
    texto = formatear_payload(d, "slack")["text"]
    total_vis = d["resumen"]["total"]["visualizaciones"]
    assert total_vis >= 1000
    assert miles(total_vis) in texto
    assert f"{total_vis:,}" not in texto


def test_formatear_payload_generico_es_rico():
    d = construir_digest(FuenteMuestra(), "semana", 50)
    p = formatear_payload(d, "generico")
    assert p["text"]
    assert p["fuente"] == d["fuente"]
    assert p["n_alertas"] == d["n_alertas"]
    assert "picos" in p


def test_formatear_payload_formato_invalido():
    d = construir_digest(FuenteMuestra(), "semana", 50)
    try:
        formatear_payload(d, "telegram")
    except ValueError as e:
        assert "telegram" in str(e)
    else:
        raise AssertionError("se esperaba ValueError por formato invalido")


# --- CLI: SAFE BY DEFAULT (cero red) ----------------------------------------
@respx.mock
def test_preview_sin_url_cero_red(monkeypatch, capsys):
    """Sin KENI_WEBHOOK_URL: solo preview, ninguna peticion de red."""
    monkeypatch.delenv("KENI_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")  # offline puro
    ruta = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))

    code = main(["--enviar"])  # pide enviar pero sin URL => no debe tocar la red
    assert code == 2  # --enviar sin URL aborta
    assert not ruta.called
    assert respx.calls.call_count == 0


@respx.mock
def test_preview_con_url_sin_flag_cero_red(monkeypatch, capsys):
    """Con URL pero sin --enviar: solo preview, ninguna peticion de red."""
    monkeypatch.setenv("KENI_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    ruta = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))

    code = main([])  # sin --enviar
    assert code == 0
    salida = capsys.readouterr().out
    assert "PREVIEW" in salida
    assert "NADA se ha enviado" in salida
    # el payload previsualizado es JSON valido
    cuerpo = salida[salida.index("{") :]
    json.loads(cuerpo)
    assert not ruta.called
    assert respx.calls.call_count == 0


@respx.mock
def test_formato_env_invalido_aborta_sin_red(monkeypatch, capsys):
    """KENI_WEBHOOK_FORMATO invalido (p.ej. 'telegram'): rc=2, stderr, cero red."""
    monkeypatch.setenv("KENI_WEBHOOK_FORMATO", "telegram")
    monkeypatch.setenv("KENI_WEBHOOK_URL", WEBHOOK)  # aun con URL, no debe tocar la red
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    ruta = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))

    code = main([])
    assert code == 2
    err = capsys.readouterr().err
    assert "telegram" in err
    assert "KENI_WEBHOOK_FORMATO" in err
    assert not ruta.called
    assert respx.calls.call_count == 0


@respx.mock
def test_no_url_ni_flag_cero_red(monkeypatch, capsys):
    """Caso por defecto absoluto: sin URL y sin flag => preview, code 0, cero red."""
    monkeypatch.delenv("KENI_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    ruta = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))

    code = main([])
    assert code == 0
    assert "PREVIEW" in capsys.readouterr().out
    assert not ruta.called
    assert respx.calls.call_count == 0


# --- CLI: camino REAL (URL + --enviar), mockeado ----------------------------
@respx.mock
def test_enviar_con_url_y_flag_postea_payload(monkeypatch, capsys):
    monkeypatch.setenv("KENI_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("KENI_WEBHOOK_FORMATO", "slack")
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    ruta = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={"ok": True}))

    code = main(["--enviar"])
    assert code == 0
    assert ruta.called
    assert respx.calls.call_count == 1
    # el body posteado es el payload Slack: {"text": ...}
    enviado = json.loads(ruta.calls.last.request.content)
    assert set(enviado.keys()) == {"text"}
    assert "alertas de redes" in enviado["text"]
    assert "enviada" in capsys.readouterr().out


@respx.mock
def test_enviar_generico_postea_payload_rico(monkeypatch, capsys):
    monkeypatch.setenv("KENI_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    ruta = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={"ok": True}))

    code = main(["--enviar", "--formato", "generico"])
    assert code == 0
    enviado = json.loads(ruta.calls.last.request.content)
    assert "picos" in enviado
    assert "n_alertas" in enviado
    assert enviado["fuente"] == FuenteMuestra().nombre


@respx.mock
def test_enviar_falla_de_red_devuelve_1_sin_romper(monkeypatch, capsys):
    monkeypatch.setenv("KENI_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    respx.post(WEBHOOK).mock(return_value=httpx.Response(500, json={"err": "x"}))

    code = main(["--enviar"])
    assert code == 1  # degrada limpio
    assert "Error al enviar" in capsys.readouterr().err


# --- helper enviar() directo ------------------------------------------------
@respx.mock
def test_enviar_usa_post_json():
    ruta = respx.post(WEBHOOK).mock(return_value=httpx.Response(200, json={"recibido": 1}))
    resp = enviar({"text": "hola", "n_alertas": 0}, WEBHOOK)
    assert ruta.called
    assert resp == {"recibido": 1}

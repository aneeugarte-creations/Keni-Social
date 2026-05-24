"""Tests de la cola/agendador y de la CLI de publicacion (todo DRY-RUN salvo mock)."""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import respx

from keni_metricas.publicacion import AdaptadorPublicacionMeta, Borrador, ColaPublicacion
from keni_metricas.publicacion.__main__ import main
from keni_metricas.publicacion.meta import BASE
from keni_metricas.schema import Plataforma

AHORA = datetime(2026, 5, 24, 12, 0, 0)


def _borrador_fb(texto: str = "hola") -> Borrador:
    return Borrador(plataforma=Plataforma.facebook, cuenta="PAGE", texto=texto)


# --- cola ------------------------------------------------------------------
@respx.mock
def test_cola_dry_run_dispara_vencidos_sin_red():
    ad = AdaptadorPublicacionMeta(creds={})
    cola = ColaPublicacion(adaptador=ad)
    cola.encolar(_borrador_fb("ya"))  # sin hora -> vencido siempre
    cola.encolar(_borrador_fb("futuro"), publicar_en=AHORA + timedelta(hours=1))

    res = cola.publicar_pendientes(AHORA)  # dry_run por defecto
    assert len(res) == 1  # solo el sin-hora vence
    assert res[0].dry_run is True
    assert respx.calls.call_count == 0
    # dry-run NO consume la cola: el item sigue no publicado
    assert cola.items[0].publicado is False


def test_cola_orden_por_hora():
    ad = AdaptadorPublicacionMeta(creds={})
    cola = ColaPublicacion(adaptador=ad)
    cola.encolar(_borrador_fb("B"), publicar_en=AHORA - timedelta(minutes=10))
    cola.encolar(_borrador_fb("A"), publicar_en=AHORA - timedelta(minutes=30))
    res = cola.publicar_pendientes(AHORA)
    textos = [r.peticiones[0].data["message"] for r in res]
    assert textos == ["A", "B"]  # mas antiguo primero


def test_cola_no_dispara_no_vencidos():
    ad = AdaptadorPublicacionMeta(creds={})
    cola = ColaPublicacion(adaptador=ad)
    cola.encolar(_borrador_fb(), publicar_en=AHORA + timedelta(days=1))
    assert cola.publicar_pendientes(AHORA) == []


@respx.mock
def test_cola_real_marca_publicado():
    ruta = respx.post(f"{BASE}/PAGE/feed").mock(
        return_value=httpx.Response(200, json={"id": "PAGE_1"})
    )
    ad = AdaptadorPublicacionMeta(creds={"access_token": "tok"})
    cola = ColaPublicacion(adaptador=ad)
    cola.encolar(_borrador_fb("real"))
    res = cola.publicar_pendientes(AHORA, dry_run=False)

    assert ruta.called
    assert res[0].dry_run is False
    assert cola.items[0].publicado is True
    # ya no vuelve a dispararse
    assert cola.publicar_pendientes(AHORA, dry_run=False) == []


# --- CLI -------------------------------------------------------------------
@respx.mock
def test_cli_dry_run_imprime_payload_sin_red(capsys):
    ruta = respx.post(f"{BASE}/PAGE/feed").mock(return_value=httpx.Response(200, json={"id": "x"}))
    code = main(["--plataforma", "facebook", "--cuenta", "PAGE", "--texto", "Hola", "--formato", "json"])
    assert code == 0
    salida = capsys.readouterr().out
    assert '"dry_run": true' in salida
    assert "PAGE/feed" in salida
    assert not ruta.called  # la CLI nunca toca la red


@respx.mock
def test_cli_instagram_dos_pasos(capsys):
    code = main(
        [
            "--plataforma",
            "instagram",
            "--cuenta",
            "IGID",
            "--texto",
            "foto",
            "--imagen",
            "https://e/x.jpg",
            "--hashtag",
            "deporte",
            "--formato",
            "texto",
        ]
    )
    assert code == 0
    salida = capsys.readouterr().out
    assert "ig_container" in salida and "ig_publish" in salida
    assert "NADA se ha publicado" in salida
    assert respx.calls.call_count == 0


def test_cli_plataforma_invalida_devuelve_error(capsys):
    # argparse rechaza un choice invalido con SystemExit(2)
    try:
        main(["--plataforma", "tiktok", "--cuenta", "X"])
    except SystemExit as e:
        assert e.code == 2
    else:  # pragma: no cover
        raise AssertionError("esperaba SystemExit")

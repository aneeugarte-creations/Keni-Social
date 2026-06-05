"""Tests del daemon de ingesta (`ingesta_daemon`): planificación PURA + barrido con fakes.

`planificar_proximo` es PURA (sin reloj ni BD): se verifica la cadencia en éxito y el backoff
exponencial acotado en error. `ejecutar_barrido` se prueba con `repos`/`db` parcheados (feeds
falsos, fetcher falso vía monkeypatch de la descarga) para que NUNCA se toque la red ni
Postgres: se comprueba que persiste items nuevos y que programa el próximo sondeo (intervalo en
éxito, pausa de backoff en error).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from keni_consola import config, ingesta_daemon
from keni_consola.dominio import ingesta

_AHORA = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)

_FEED_OK = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Nota uno</title><link>https://example.com/1</link><guid>1</guid></item>
  <item><title>Nota dos</title><link>https://example.com/2</link><guid>2</guid></item>
</channel></rss>"""


# --------------------------------------------------------------------------- #
# planificar_proximo (PURA)                                                    #
# --------------------------------------------------------------------------- #


def test_planificar_exito_programa_intervalo_y_resetea_errores():
    plan = ingesta_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=False, errores_previos=3
    )
    assert plan["errores_seguidos"] == 0
    assert plan["pausado_hasta"] == ""
    # proximo = ahora + 600s
    assert plan["proximo_sondeo"] == "2026-06-05T12:10:00+00:00"


def test_planificar_error_aplica_backoff_exponencial():
    # Primer error: espera = intervalo * 2^1 = 1200s.
    p1 = ingesta_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=0
    )
    assert p1["errores_seguidos"] == 1
    assert p1["proximo_sondeo"] == "2026-06-05T12:20:00+00:00"
    assert p1["pausado_hasta"] == p1["proximo_sondeo"]
    # Segundo error: espera = 600 * 2^2 = 2400s.
    p2 = ingesta_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=1
    )
    assert p2["errores_seguidos"] == 2
    assert p2["proximo_sondeo"] == "2026-06-05T12:40:00+00:00"


def test_planificar_backoff_no_supera_el_tope():
    # Muchos errores: la espera se acota al tope (1h por defecto), no crece sin límite.
    plan = ingesta_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=50,
        backoff_tope_seg=3600,
    )
    assert plan["proximo_sondeo"] == "2026-06-05T13:00:00+00:00"  # +3600s


# --------------------------------------------------------------------------- #
# _intervalo_feed                                                              #
# --------------------------------------------------------------------------- #


def test_intervalo_feed_usa_intervalo_propio_si_positivo():
    assert ingesta_daemon._intervalo_feed({"intervalo_min": 42, "categoria": "mx"}) == 42


def test_intervalo_feed_cae_a_default_por_categoria():
    assert ingesta_daemon._intervalo_feed({"intervalo_min": 0, "categoria": "deportes"}) == (
        config.INGESTA_INTERVALO_DEPORTES_DEF
    )
    assert ingesta_daemon._intervalo_feed({"categoria": "desconocida"}) == (
        config.INGESTA_INTERVALO_DEFECTO_DEF
    )


# --------------------------------------------------------------------------- #
# ejecutar_barrido (con fakes; sin red ni BD)                                  #
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _lock_concedido(_nombre):
    yield True


def _parchear_comun(monkeypatch, *, feeds, fetcher):
    """Parchea db.lock_barrido, repos.feeds_vencidos y la descarga de http_feed."""
    monkeypatch.setattr(ingesta_daemon.db, "lock_barrido", _lock_concedido)
    monkeypatch.setattr(ingesta_daemon.repos, "feeds_vencidos", lambda ahora, lim: list(feeds))
    # La descarga real de http_feed es el único punto de red: lo sustituimos por el fetcher.
    monkeypatch.setattr(ingesta.http_feed, "_DESCARGADOR", fetcher)


def test_barrido_persiste_items_y_programa_intervalo_en_exito(monkeypatch):
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    registrados = []
    persistidos = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))

    resumen = ingesta_daemon.ejecutar_barrido()
    assert resumen == {"feeds": 1, "items_nuevos": 2, "errores": 0}
    assert len(persistidos) == 2
    # Se programó el próximo sondeo SIN backoff (éxito) y con errores reseteados.
    fid, kw = registrados[0]
    assert fid == "f1"
    assert kw["errores_seguidos"] == 0
    assert kw["pausado_hasta"] == ""
    assert kw["proximo_sondeo"]  # ISO no vacío


def test_barrido_aplica_backoff_cuando_el_feed_falla(monkeypatch):
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    registrados = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: "esto no es xml")
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))

    resumen = ingesta_daemon.ejecutar_barrido()
    assert resumen["errores"] == 1
    assert resumen["items_nuevos"] == 0
    fid, kw = registrados[0]
    assert kw["errores_seguidos"] == 1
    assert kw["pausado_hasta"]  # pausado por backoff
    assert kw["error"]  # mensaje de error registrado


def test_barrido_sin_feeds_vencidos_no_hace_nada(monkeypatch):
    _parchear_comun(monkeypatch, feeds=[], fetcher=lambda _u: _FEED_OK)
    resumen = ingesta_daemon.ejecutar_barrido()
    assert resumen == {"feeds": 0, "items_nuevos": 0, "errores": 0}


def test_barrido_respeta_single_flight(monkeypatch):
    @contextlib.contextmanager
    def _ocupado(_n):
        yield False

    monkeypatch.setattr(ingesta_daemon.db, "lock_barrido", _ocupado)
    # No debería ni consultar feeds si el lock está tomado.
    def _no_llamar(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería consultar feeds con el lock tomado")

    monkeypatch.setattr(ingesta_daemon.repos, "feeds_vencidos", _no_llamar)
    resumen = ingesta_daemon.ejecutar_barrido()
    assert resumen == {"feeds": 0, "items_nuevos": 0, "errores": 0}

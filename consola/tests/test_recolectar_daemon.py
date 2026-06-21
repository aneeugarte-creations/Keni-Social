"""Tests del daemon de ingesta (`recolectar_daemon`): planificación PURA + barrido con fakes.

`planificar_proximo` es PURA (sin reloj ni BD): se verifica la cadencia en éxito y el backoff
exponencial acotado en error. `ejecutar_barrido` se prueba con `repos`/`db` parcheados (feeds
falsos, fetcher falso vía monkeypatch de la descarga) para que NUNCA se toque la red ni
Postgres: se comprueba que persiste items nuevos y que programa el próximo sondeo (intervalo en
éxito, pausa de backoff en error).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

import pytest

from keni_consola import config, recolectar_daemon
from keni_consola.dominio import ingesta
from keni_consola.recolectar_daemon import _comun

_AHORA = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_throttle_fusionar():
    """Resetea el throttle y la huella globales de `paso_fusionar_semantica` antes/después de cada
    test: así ni una pasada sellada por un test previo la hace salir por el throttle, ni una huella
    previa la hace saltar por skip-if-unchanged."""
    _comun._ultimo_fusionar = 0.0
    _comun._ultima_huella_fusionar = None
    yield
    _comun._ultimo_fusionar = 0.0
    _comun._ultima_huella_fusionar = None

_FEED_OK = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Nota uno</title><link>https://example.com/1</link><guid>1</guid></item>
  <item><title>Nota dos</title><link>https://example.com/2</link><guid>2</guid></item>
</channel></rss>"""


# --------------------------------------------------------------------------- #
# planificar_proximo (PURA)                                                    #
# --------------------------------------------------------------------------- #


def test_planificar_exito_programa_intervalo_y_resetea_errores():
    plan = recolectar_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=False, errores_previos=3
    )
    assert plan["errores_seguidos"] == 0
    assert plan["pausado_hasta"] == ""
    # proximo = ahora + 600s
    assert plan["proximo_sondeo"] == "2026-06-05T12:10:00"  # canon UTC sin offset (tiempo.iso_utc)


def test_planificar_error_aplica_backoff_exponencial():
    # Primer error: espera = intervalo * 2^1 = 1200s.
    p1 = recolectar_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=0
    )
    assert p1["errores_seguidos"] == 1
    assert p1["proximo_sondeo"] == "2026-06-05T12:20:00"
    assert p1["pausado_hasta"] == p1["proximo_sondeo"]
    # Segundo error: espera = 600 * 2^2 = 2400s.
    p2 = recolectar_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=1
    )
    assert p2["errores_seguidos"] == 2
    assert p2["proximo_sondeo"] == "2026-06-05T12:40:00"


def test_planificar_backoff_no_supera_el_tope():
    # Muchos errores: la espera se acota al tope (1h por defecto), no crece sin límite.
    plan = recolectar_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=50,
        backoff_tope_seg=3600,
    )
    assert plan["proximo_sondeo"] == "2026-06-05T13:00:00"  # +3600s


# --------------------------------------------------------------------------- #
# _intervalo_feed                                                              #
# --------------------------------------------------------------------------- #


def test_intervalo_feed_usa_intervalo_propio_si_positivo():
    assert recolectar_daemon._intervalo_feed({"intervalo_min": 42, "categoria": "mx"}) == 42


def test_intervalo_feed_cae_a_default_por_categoria():
    assert recolectar_daemon._intervalo_feed({"intervalo_min": 0, "categoria": "futbol"}) == (
        config.INGESTA_INTERVALO_DEPORTES_DEF
    )
    assert recolectar_daemon._intervalo_feed({"categoria": "desconocida"}) == (
        config.INGESTA_INTERVALO_DEFECTO_DEF
    )


def test_intervalo_feed_usa_cadencia_de_la_linea(monkeypatch):
    # Con línea asociada, el ritmo lo dicta la CADENCIA de la línea, no el slug `categoria`.
    from keni_consola.recolectar_daemon import _bucle

    monkeypatch.setattr(_bucle.db, "obtener_etiqueta", lambda _id: {"cadencia": "evergreen"})
    assert recolectar_daemon._intervalo_feed({"linea_id": "L1", "categoria": "futbol"}) == (
        config.INGESTA_INTERVALO_EVERGREEN_DEF
    )


# --------------------------------------------------------------------------- #
# ejecutar_barrido (con fakes; sin red ni BD)                                  #
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _lock_concedido(_nombre):
    yield True


def _parchear_comun(monkeypatch, *, feeds, fetcher):
    """Parchea db.lock_barrido, repos.feeds_vencidos y la descarga de http_feed.

    Apaga además el FILTRO DE ENTRADA por vocabulario (def ON): estos tests cubren la
    mecánica del barrido (persistencia, planificación, backoff) con titulares neutros
    («Nota uno») que no casan ninguna agenda; el filtro tiene sus propios tests abajo.
    """
    monkeypatch.setenv(config.ENV_INGESTA_FILTRO, "0")
    monkeypatch.setattr(recolectar_daemon.db, "lock_barrido", _lock_concedido)
    # Sin BD: el intervalo de un feed con LÍNEA consulta su etiqueta; lo dejamos sin resolver para
    # que caiga a la cadencia por categoría (legado), sin tocar Postgres.
    monkeypatch.setattr(recolectar_daemon.db, "obtener_etiqueta", lambda _id: None)
    monkeypatch.setattr(recolectar_daemon.repos, "feeds_vencidos", lambda ahora, lim: list(feeds))
    # La descarga real de http_feed es el único punto de red: lo sustituimos por el fetcher.
    monkeypatch.setattr(ingesta.http_feed, "_DESCARGADOR", fetcher)


def test_barrido_persiste_items_y_programa_intervalo_en_exito(monkeypatch):
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    registrados = []
    persistidos = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))

    resumen = recolectar_daemon.ejecutar_barrido()
    # Aditivo (Ola D): el resumen lleva más claves (agrupar/traducir/auto_desactivados);
    # verificamos las del barrido de ingesta por separado, no por igualdad exacta.
    assert resumen["feeds"] == 1
    assert resumen["items_nuevos"] == 2
    assert resumen["errores"] == 0
    assert resumen["auto_desactivados"] == 0
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
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))

    resumen = recolectar_daemon.ejecutar_barrido()
    assert resumen["errores"] == 1
    assert resumen["items_nuevos"] == 0
    fid, kw = registrados[0]
    assert kw["errores_seguidos"] == 1
    assert kw["pausado_hasta"]  # pausado por backoff
    assert kw["error"]  # mensaje de error registrado


def test_barrido_sin_feeds_vencidos_corre_los_pasos_post_rss(monkeypatch):
    """Sin feeds RSS vencidos, el barrido NO sondea nada pero los pasos post-RSS corren igual."""
    _parchear_comun(monkeypatch, feeds=[], fetcher=lambda _u: _FEED_OK)
    llamados: list[str] = []
    monkeypatch.setattr(recolectar_daemon, "paso_agencias",
                        lambda: llamados.append("agencias") or {"items": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar",
                        lambda: llamados.append("agrupar") or {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_rescore",
                        lambda *a, **k: llamados.append("rescore") or {"revisados": 0, "actualizados": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_fusionar_semantica",
                        lambda **k: llamados.append("fusion") or {"grupos": 0, "fusionadas": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir",
                        lambda: llamados.append("traducir") or {"traducidos": 0, "candidatos": 0})

    resumen = recolectar_daemon.ejecutar_barrido()
    assert resumen["feeds"] == 0
    assert resumen["items_nuevos"] == 0
    assert resumen["errores"] == 0
    # Los pasos post-RSS corrieron AUNQUE no hubiera feeds vencidos (sin merge léxico: la
    # agrupación del mismo evento la hace la fusión semántica).
    assert llamados == ["agencias", "agrupar", "rescore", "fusion", "traducir"]


def test_barrido_respeta_single_flight(monkeypatch):
    @contextlib.contextmanager
    def _ocupado(_n):
        yield False

    monkeypatch.setattr(recolectar_daemon.db, "lock_barrido", _ocupado)
    # No debería ni consultar feeds si el lock está tomado.
    def _no_llamar(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería consultar feeds con el lock tomado")

    monkeypatch.setattr(recolectar_daemon.repos, "feeds_vencidos", _no_llamar)
    resumen = recolectar_daemon.ejecutar_barrido()
    assert resumen == {"feeds": 0, "items_nuevos": 0, "errores": 0}


def test_barrido_salta_feeds_de_marca_apagada(monkeypatch):
    """Excepción por marca de KENI_PIPELINE_RECOLECTAR: el feed de una marca apagada se salta; el feed
    COMPARTIDO (marca vacía) y el de una marca permitida sí se sondean."""
    feed_apagado = {"id": "off", "nombre": "Off", "url": "https://93.184.216.34/a",
                    "categoria": "mx", "marca": "nacion-gamer", "errores_seguidos": 0}
    feed_permitido = {"id": "on", "nombre": "On", "url": "https://93.184.216.34/b",
                      "categoria": "mx", "marca": "claro-sports", "errores_seguidos": 0}
    feed_compartido = {"id": "shared", "nombre": "Shared", "url": "https://93.184.216.34/c",
                       "categoria": "mx", "marca": "", "errores_seguidos": 0}
    # Override falsy de KENI_PIPELINE_RECOLECTAR solo para nacion-gamer -> esa marca queda apagada.
    overrides = {config.clave_por_marca(config.ENV_PIPELINE_RECOLECTAR, "nacion-gamer"): "0"}
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: overrides.get(clave))

    registrados = []
    _parchear_comun(monkeypatch, feeds=[feed_apagado, feed_permitido, feed_compartido],
                    fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append(fid))
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})

    resumen = recolectar_daemon.ejecutar_barrido()
    # El feed apagado NO se sondea; el permitido y el compartido sí.
    assert resumen["feeds"] == 2
    assert set(registrados) == {"on", "shared"}
    assert "off" not in registrados


def test_barrido_aplaza_feeds_fuera_del_plan(monkeypatch):
    """PLAN EDITORIAL: una marca con plan solo digiere los feeds de las categorías del plan.

    El feed fuera de plan NO se sondea y se APLAZA (registrar_sondeo_feed con proximo_sondeo
    futuro). Fail-open: un feed sin LÍNEA se sondea aunque la marca tenga plan. El plan se
    clava por LÍNEA (id de etiqueta vertical), no por el slug de categoría."""
    en_plan = {"id": "mx1", "nombre": "MX", "url": "https://93.184.216.34/a",
               "linea_id": "lin-nacional", "marca": "unotv", "errores_seguidos": 0}
    fuera = {"id": "dep1", "nombre": "Dep", "url": "https://93.184.216.34/b",
             "linea_id": "lin-deportes", "marca": "unotv", "errores_seguidos": 0}
    sin_categoria = {"id": "sc1", "nombre": "SC", "url": "https://93.184.216.34/c",
                     "linea_id": "", "marca": "unotv", "errores_seguidos": 0}
    monkeypatch.setenv("KENI_PLAN_DIA::unotv", "lin-nacional:4,breaking:2")

    registrados = {}
    _parchear_comun(monkeypatch, feeds=[en_plan, fuera, sin_categoria], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.setdefault(fid, kw))
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})

    resumen = recolectar_daemon.ejecutar_barrido()

    assert resumen["feeds"] == 2  # mx1 + sin_categoria; dep1 fuera de plan
    # El fuera-de-plan quedó APLAZADO: solo se le registró el proximo_sondeo (sin conteo).
    assert "dep1" in registrados and registrados["dep1"].get("proximo_sondeo")
    assert "conteo" not in registrados["dep1"]


# --------------------------------------------------------------------------- #
# FILTRO DE ENTRADA por vocabulario de marca (la puerta del pool)               #
# --------------------------------------------------------------------------- #

_FEED_MIXTO = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Sismo sacude la CDMX esta mañana</title><link>https://example.com/sismo</link></item>
  <item><title>Celebrity gossip from Hollywood</title><link>https://example.com/gossip</link></item>
</channel></rss>"""


def _parchear_filtro(monkeypatch, *, feeds, fetcher):
    """Como `_parchear_comun` pero con el filtro de entrada ACTIVO (su comportamiento real)."""
    _parchear_comun(monkeypatch, feeds=feeds, fetcher=fetcher)
    monkeypatch.setenv(config.ENV_INGESTA_FILTRO, "1")
    # Sin estos pasos (sin BD aquí), el barrido se queda en la mecánica de ingesta.
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})


def test_filtro_entrada_descarta_lo_que_no_casa_la_agenda(monkeypatch):
    """Feed de marca: solo se archiva lo que casa el vocabulario; lo filtrado se cuenta."""
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    persistidos, registrados = [], []
    _parchear_filtro(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_MIXTO)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))

    resumen = recolectar_daemon.ejecutar_barrido()

    assert [it["titulo"] for it in persistidos] == ["Sismo sacude la CDMX esta mañana"]
    assert resumen["items_nuevos"] == 1
    assert resumen["items_filtrados"] == 1
    _fid, kw = registrados[0]
    assert kw["filtrados"] == 1  # observable por feed en /salud (`ultimo_filtrados`)


def test_filtro_entrada_exime_feeds_propios_y_sin_marca(monkeypatch):
    """Un feed PROPIO (su contenido ES la marca) y uno COMPARTIDO (sin marca) no se filtran."""
    propio = {"id": "p", "nombre": "Propio", "url": "https://93.184.216.34/p", "categoria": "mx",
              "marca": "unotv", "propia": True, "errores_seguidos": 0}
    compartido = {"id": "s", "nombre": "Shared", "url": "https://93.184.216.34/s",
                  "categoria": "mx", "marca": "", "errores_seguidos": 0}
    persistidos = []
    _parchear_filtro(monkeypatch, feeds=[propio, compartido], fetcher=lambda _u: _FEED_MIXTO)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)

    resumen = recolectar_daemon.ejecutar_barrido()

    assert resumen["items_nuevos"] == 4  # 2 del propio + 2 del compartido, sin filtrar
    assert resumen["items_filtrados"] == 0


def test_filtro_entrada_apagado_archiva_todo(monkeypatch):
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    persistidos = []
    _parchear_filtro(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_MIXTO)
    monkeypatch.setenv(config.ENV_INGESTA_FILTRO, "0")  # apagado: comportamiento anterior
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)

    resumen = recolectar_daemon.ejecutar_barrido()
    assert resumen["items_nuevos"] == 2
    assert resumen["items_filtrados"] == 0


def test_filtro_entrada_fail_open_si_el_filtro_revienta(monkeypatch):
    """Si el filtro falla, se archiva TODO (perder cobertura es peor que archivar ruido)."""
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    persistidos = []
    _parchear_filtro(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_MIXTO)
    def _revienta(items, palabras):  # noqa: ANN001
        raise RuntimeError("boom")
    monkeypatch.setattr(recolectar_daemon.ingesta, "filtrar_por_vocabulario", _revienta)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)

    resumen = recolectar_daemon.ejecutar_barrido()
    assert resumen["items_nuevos"] == 2  # fail-open: nada se perdió
    assert resumen["items_filtrados"] == 0


# --------------------------------------------------------------------------- #
# AUTO-DESACTIVADO de feeds muertos (Ola D)                                    #
# --------------------------------------------------------------------------- #


def test_barrido_auto_desactiva_feed_al_alcanzar_max_errores(monkeypatch):
    # Feed con errores_previos = max-1: este fallo lo lleva al umbral -> auto-desactivado.
    max_err = config.ingesta_max_errores()
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": max_err - 1, "desactivado_auto": False}
    registrados = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: "esto no es xml")
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))
    # Aislar agrupar/traducción (no relevantes aquí; sin BD).
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})

    resumen = recolectar_daemon.ejecutar_barrido()
    assert resumen["auto_desactivados"] == 1
    _fid, kw = registrados[0]
    assert kw["errores_seguidos"] == max_err
    assert kw["activo"] is False
    assert kw["desactivado_auto"] is True


def test_barrido_no_desactiva_antes_del_umbral(monkeypatch):
    max_err = config.ingesta_max_errores()
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0, "desactivado_auto": False}
    registrados = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: "esto no es xml")
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})

    resumen = recolectar_daemon.ejecutar_barrido()
    # Un solo error (< umbral): NO se desactiva; no se toca `activo`.
    assert resumen["auto_desactivados"] == 0
    assert max_err > 1  # el umbral por defecto deja margen
    _fid, kw = registrados[0]
    assert kw["activo"] is None
    assert kw["desactivado_auto"] is None


def test_barrido_reactiva_feed_auto_desactivado_al_recuperarse(monkeypatch):
    # Un feed que venía auto-desactivado vuelve a sondear OK -> se reactiva.
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 3, "desactivado_auto": True}
    registrados = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})

    recolectar_daemon.ejecutar_barrido()
    _fid, kw = registrados[0]
    assert kw["errores_seguidos"] == 0
    assert kw["activo"] is True
    assert kw["desactivado_auto"] is False


# --------------------------------------------------------------------------- #
# Paso de TRADUCCIÓN (Ola D) con ejecutor falso (sin red ni BD)                #
# --------------------------------------------------------------------------- #


def test_paso_traducir_marca_clusters_y_guarda_es(monkeypatch):
    candidatos = [
        {"id": "c1", "titulo": "Foreign one", "resumen": "Body one", "idioma": "en"},
        {"id": "c2", "titulo": "Foreign two", "resumen": "Body two", "idioma": "fr"},
    ]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_extranjeros_sin_traducir",
                        lambda ventana_h, **kw: list(candidatos))
    guardados = []
    monkeypatch.setattr(recolectar_daemon.repos, "marcar_cluster_traducido",
                        lambda cid, **kw: guardados.append((cid, kw)) or {"id": cid})

    # Ejecutor falso: devuelve traducciones ES deterministas para cada id (sin llamar a claude).
    def _ejecutor_ok(prompt, _dir):
        import json as _json
        import re
        cola = prompt.partition("## Lista de ítems")[2] or prompt
        m = re.search(r"\[.*?\]", cola, re.DOTALL)
        items = _json.loads(m.group(0)) if m else []
        return _json.dumps({"traducciones": [
            {"id": it["id"], "titulo_es": "ES " + it["titulo"], "resumen_es": "ES " + it["resumen"]}
            for it in items
        ]})

    resumen = recolectar_daemon.paso_traducir(ejecutor=_ejecutor_ok)
    assert resumen == {"traducidos": 2, "candidatos": 2}
    por_id = dict(guardados)
    assert por_id["c1"]["titulo_es"] == "ES Foreign one"
    assert por_id["c1"]["titulo_original"] == "Foreign one"
    assert por_id["c2"]["resumen_es"] == "ES Body two"


def test_paso_traducir_no_persiste_si_falla(monkeypatch):
    """Si Haiku falla, el cluster NO se marca `traducido` con el título extranjero: queda intacto
    para reintentarse en el próximo barrido (no se envenena con texto en idioma original)."""
    candidatos = [{"id": "c1", "titulo": "Foreign one", "resumen": "Body one", "idioma": "en"}]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_extranjeros_sin_traducir",
                        lambda ventana_h, **kw: list(candidatos))
    guardados = []
    monkeypatch.setattr(recolectar_daemon.repos, "marcar_cluster_traducido",
                        lambda cid, **kw: guardados.append(cid))

    def _ejecutor_falla(_prompt, _dir):
        raise RuntimeError("haiku caído")

    resumen = recolectar_daemon.paso_traducir(ejecutor=_ejecutor_falla)
    assert resumen == {"traducidos": 0, "candidatos": 1}
    assert guardados == []  # nada persistido -> sigue siendo candidato (reintento)


def test_paso_traducir_sin_candidatos_no_hace_nada(monkeypatch):
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_extranjeros_sin_traducir",
                        lambda ventana_h, **kw: [])
    def _no_guardar(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería guardar sin candidatos")
    monkeypatch.setattr(recolectar_daemon.repos, "marcar_cluster_traducido", _no_guardar)
    assert recolectar_daemon.paso_traducir() == {"traducidos": 0, "candidatos": 0}


# --------------------------------------------------------------------------- #
# Paso de AGENCIAS (Fase 2): vuelca Reuters/AFP al pool (con fakes, sin red)   #
# --------------------------------------------------------------------------- #


def test_paso_agencias_sin_credencial_es_noop(monkeypatch):
    # traer_items degrada honesto a [] sin credencial -> nada que persistir, sin red.
    monkeypatch.setattr(recolectar_daemon.agencias, "traer_items", lambda _ag: [])
    def _no_persistir(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería persistir sin items de agencia")
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", _no_persistir)
    assert recolectar_daemon.paso_agencias() == {"items": 0}


def test_paso_agencias_ingiere_items_al_pool(monkeypatch):
    crudos = {
        "reuters": [{"titulo": "Nota R", "resumen": "", "enlace": "https://r/1", "fecha": "", "fuente": "Reuters", "clave": "https://r/1"}],
        "afp": [{"titulo": "Nota A", "resumen": "", "enlace": "https://a/1", "fecha": "", "fuente": "AFP", "clave": "https://a/1"}],
    }
    monkeypatch.setattr(recolectar_daemon.agencias, "traer_items", lambda ag: crudos.get(ag, []))
    persistidos = []
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))

    resumen = recolectar_daemon.paso_agencias()
    assert resumen == {"items": 2}
    fuentes = {f["fuente_id"] for f in persistidos}
    assert fuentes == {"agencia-reuters", "agencia-afp"}
    assert all(f["categoria"] == "agencias" for f in persistidos)


def test_paso_agencias_best_effort_una_agencia_que_falla_no_aborta(monkeypatch):
    # Reuters revienta; AFP debe seguir ingiriendo (best-effort por agencia).
    def _traer(ag):
        if ag == "reuters":
            raise RuntimeError("boom de auth")
        return [{"titulo": "Nota A", "resumen": "", "enlace": "https://a/1", "fecha": "", "fuente": "AFP", "clave": "https://a/1"}]
    monkeypatch.setattr(recolectar_daemon.agencias, "traer_items", _traer)
    persistidos = []
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))

    resumen = recolectar_daemon.paso_agencias()
    assert resumen == {"items": 1}
    assert [f["fuente_id"] for f in persistidos] == ["agencia-afp"]


def test_barrido_ingiere_agencias_y_suma_a_items_nuevos(monkeypatch):
    # El barrido completo: RSS persiste 2 + agencias persisten 1 -> items_nuevos == 3.
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    persistidos = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})
    monkeypatch.setattr(recolectar_daemon.agencias, "traer_items",
                        lambda ag: [{"titulo": "Ag", "resumen": "", "enlace": f"https://{ag}/1", "fecha": "", "fuente": ag.upper(), "clave": f"https://{ag}/1"}] if ag == "reuters" else [])

    resumen = recolectar_daemon.ejecutar_barrido()
    assert resumen["items_nuevos"] == 3  # 2 RSS + 1 agencia
    assert resumen["agencias"] == {"items": 1}
    assert any(f.get("fuente_id") == "agencia-reuters" for f in persistidos)


def test_barrido_no_aborta_si_paso_agencias_revienta(monkeypatch):
    # Si paso_agencias lanzara, el barrido lo captura y sigue con RSS/agrupar.
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(recolectar_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(recolectar_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)
    monkeypatch.setattr(recolectar_daemon, "paso_agrupar", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(recolectar_daemon, "paso_traducir", lambda: {"traducidos": 0, "candidatos": 0})
    def _revienta():
        raise RuntimeError("boom")
    monkeypatch.setattr(recolectar_daemon, "paso_agencias", _revienta)

    resumen = recolectar_daemon.ejecutar_barrido()
    # RSS no se ve afectado; agencias cae a su default sin sumar.
    assert resumen["items_nuevos"] == 2
    assert resumen["agencias"] == {"items": 0}


# --------------------------------------------------------------------------- #
# Actividad IA del pool: fusión semántica deja constancia VISIBLE (noticias-ia) #
# --------------------------------------------------------------------------- #


def test_paso_fusionar_semantica_registra_actividad_ia(monkeypatch):
    """Al fundir, sella `noticias-ia` con el Haiku REAL (prompt + salida) + el resumen humano."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [
        {"id": "c1", "titulo": "Remontada épica", "estado": "nuevo", "marca": "unotv"},
        {"id": "c2", "titulo": "Remontada increíble", "estado": "nuevo", "marca": "unotv"},
    ]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: list(recientes))

    def _fake_proponer(lote, *, ejecutor=None, al_ejecutar=None):
        if al_ejecutar:  # el daemon captura el prompt+salida reales de Haiku
            al_ejecutar("PROMPT-HAIKU-FUSION", '{"grupos": [["c1","c2"]]}')
        return [["c1", "c2"]]
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_fusiones", _fake_proponer)
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_macro_eventos", lambda lote, **kw: [])
    monkeypatch.setattr(recolectar_daemon, "_fusionar_grupo", lambda *a, **k: True)
    registradas: list[tuple[str, str, str, str, str]] = []
    monkeypatch.setattr(
        recolectar_daemon, "_registrar_actividad_ia",
        lambda marca, etiqueta, salida, *, prompt="", etapa="":
            registradas.append((marca, etiqueta, salida, prompt, etapa)),
    )

    resumen = recolectar_daemon.paso_fusionar_semantica()
    assert resumen == {"grupos": 1, "fusionadas": 1}
    assert len(registradas) == 1
    marca, etiqueta, salida, prompt, etapa = registradas[0]
    assert marca == "unotv"
    assert "Fusionar historias" in etiqueta
    assert etapa == "Fusionar"  # ETAPA explícita para el desglose por etapa de la economía
    assert prompt == "PROMPT-HAIKU-FUSION"  # el prompt REAL de Haiku
    assert '{"grupos"' in salida  # la salida REAL de Haiku
    assert "Remontada épica" in salida  # + el resumen humano de qué se unió


def test_paso_fusionar_semantica_sin_fusiones_no_registra(monkeypatch):
    """Si Haiku no agrupa nada, no hay generación de actividad (sin ruido a 0)."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [
        {"id": "c1", "titulo": "A", "estado": "nuevo", "marca": "unotv"},
        {"id": "c2", "titulo": "B", "estado": "nuevo", "marca": "unotv"},
    ]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: list(recientes))
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_fusiones", lambda lote, **kw: [])
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_macro_eventos", lambda lote, **kw: [])
    registradas: list[object] = []
    monkeypatch.setattr(recolectar_daemon, "_registrar_actividad_ia",
                        lambda *a, **k: registradas.append(a))

    assert recolectar_daemon.paso_fusionar_semantica() == {"grupos": 0, "fusionadas": 0}
    assert registradas == []


def test_paso_fusionar_semantica_etiqueta_macro_evento(monkeypatch):
    """Tras la fusión dura, ETIQUETA familias de macro-evento (clusters DISTINTOS del mismo gran
    evento) SIN fundirlos: persiste `tema_macro` por familia y sella la actividad IA."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [
        {"id": "c1", "titulo": "Meloni deja de fumar en el G7", "estado": "nuevo", "marca": "unotv"},
        {"id": "c2", "titulo": "Trump habla de Irán en el G7", "estado": "nuevo", "marca": "unotv"},
        {"id": "c3", "titulo": "Acuerdo comercial en el G7", "estado": "nuevo", "marca": "unotv"},
    ]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: list(recientes))
    # Sin fusión dura: aislamos el etiquetado de macro-evento.
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_fusiones", lambda lote, **kw: [])

    def _fake_macro(lote, *, ejecutor=None, al_ejecutar=None):
        if al_ejecutar:
            al_ejecutar("PROMPT-MACRO", '{"familias": [{"tema": "Cumbre del G7", "ids": ["c1","c2","c3"]}]}')
        return [{"tema": "Cumbre del G7", "ids": ["c1", "c2", "c3"]}]
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_macro_eventos", _fake_macro)

    etiquetados: list[tuple[list[str], str]] = []
    monkeypatch.setattr(recolectar_daemon.repos, "marcar_clusters_tema_macro",
                        lambda ids, tema: etiquetados.append((list(ids), tema)) or len(ids))
    registradas: list[tuple[str, str, str, str, str]] = []
    monkeypatch.setattr(
        recolectar_daemon, "_registrar_actividad_ia",
        lambda marca, etiqueta, salida, *, prompt="", etapa="":
            registradas.append((marca, etiqueta, salida, prompt, etapa)),
    )

    recolectar_daemon.paso_fusionar_semantica()

    # La familia se persiste tal cual (no se funde ningún cluster).
    assert etiquetados == [(["c1", "c2", "c3"], "Cumbre del G7")]
    # Y se deja constancia IA del macro-evento (con el Haiku real + resumen humano).
    assert len(registradas) == 1
    marca, etiqueta, salida, prompt, etapa = registradas[0]
    assert marca == "unotv"
    assert "Macro-evento" in etiqueta
    assert etapa == "Macro-evento"  # ETAPA explícita para el desglose por etapa de la economía
    assert prompt == "PROMPT-MACRO"
    assert "Cumbre del G7" in salida


def test_paso_fusionar_semantica_macro_reusa_etiqueta_dominante(monkeypatch):
    """Backstop determinista: si la familia ya tiene una `tema_macro` persistida, se reusa la
    DOMINANTE (no el sinónimo propuesto), para que el evento no se parta en dos cajas."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    # c1/c2 ya etiquetados "Mundial 2026"; c3 con el sinónimo "Copa del Mundo 2026".
    recientes = [
        {"id": "c1", "titulo": "México vs Corea", "estado": "nuevo", "marca": "unotv",
         "tema_macro": "Mundial 2026"},
        {"id": "c2", "titulo": "Adopta un coreano", "estado": "nuevo", "marca": "unotv",
         "tema_macro": "Mundial 2026"},
        {"id": "c3", "titulo": "CDMX recibe la Copa", "estado": "nuevo", "marca": "unotv",
         "tema_macro": "Copa del Mundo 2026"},
    ]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: list(recientes))
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_fusiones", lambda lote, **kw: [])
    # Haiku agrupa las 3 pero propone el sinónimo "Copa del Mundo 2026".
    monkeypatch.setattr(
        recolectar_daemon.fusionar_semantica, "proponer_macro_eventos",
        lambda lote, **kw: [{"tema": "Copa del Mundo 2026", "ids": ["c1", "c2", "c3"]}],
    )
    etiquetados: list[tuple[list[str], str]] = []
    monkeypatch.setattr(recolectar_daemon.repos, "marcar_clusters_tema_macro",
                        lambda ids, tema: etiquetados.append((list(ids), tema)) or len(ids))
    monkeypatch.setattr(recolectar_daemon, "_registrar_actividad_ia", lambda *a, **k: None)

    recolectar_daemon.paso_fusionar_semantica()

    # Gana la etiqueta dominante ("Mundial 2026", 2 historias) sobre el sinónimo propuesto.
    assert etiquetados == [(["c1", "c2", "c3"], "Mundial 2026")]


# --------------------------------------------------------------------------- #
# paso_agrupar: marca por vocabulario + durabilidad + escritura en lote     #
# --------------------------------------------------------------------------- #


def test_paso_agrupar_asigna_marca_por_vocabulario_a_historia_solo_trends(monkeypatch):
    """Un cluster formado SOLO por items sin marca (Trends) acaba con marca asignada por
    vocabulario y, por tanto, SELECCIONABLE por la promoción por marca (no queda con marca=''
    e invisible para todas)."""
    item = {
        "id": "i1", "fuente_id": "google-trends", "fuente_nombre": "ESPN",
        "categoria": "mx", "marca": "",  # <- Trends llega SIN marca
        "titulo": "Futbol: gol agónico en la final de la liga mx",
        "resumen": "", "url": "https://e.com/n1", "url_canonica": "e.com/n1",
        "idioma": "es", "senal": 50_000, "geo": "MX", "estado": "nuevo",
        "publicado_en": datetime.now(UTC).isoformat(),
        "capturado_en": datetime.now(UTC).isoformat(),
    }
    eventos: list[tuple[str, object]] = []
    monkeypatch.setattr(recolectar_daemon.config, "priorizar_perfil_activo", lambda: False)
    monkeypatch.setattr(recolectar_daemon.config, "rendimiento_ranking_activo", lambda: False)
    monkeypatch.setattr(recolectar_daemon.repos, "limpiar_items_cluster_colgante", lambda: 0)
    monkeypatch.setattr(recolectar_daemon.repos, "items_sin_cluster", lambda desde, lim: [dict(item)])
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes", lambda ventana_h, *a, **k: [])
    monkeypatch.setattr(recolectar_daemon.repos, "obtener_noticia_cluster", lambda cid: None)
    monkeypatch.setattr(recolectar_daemon.repos, "items_de_cluster",
                        lambda cid, **kw: [dict(item, cluster_id=cid)])
    monkeypatch.setattr(recolectar_daemon.repos, "upsert_noticia_cluster",
                        lambda c: eventos.append(("upsert", dict(c))) or dict(c))
    monkeypatch.setattr(recolectar_daemon.repos, "asignar_cluster_items",
                        lambda asg: eventos.append(("asignar", dict(asg))))

    resumen = recolectar_daemon.paso_agrupar()

    assert resumen["items"] == 1
    assert resumen["clusters_nuevos"] == 1
    # DURABILIDAD: el stub del cluster nuevo se upserteó ANTES de asignarle items.
    tipos = [t for t, _ in eventos]
    assert tipos.index("upsert") < tipos.index("asignar")
    # La asignación fue en LOTE (cluster -> [item_ids]).
    asignaciones = next(d for t, d in eventos if t == "asignar")
    assert list(asignaciones.values()) == [["i1"]]
    # El recálculo final fijó la marca por VOCABULARIO (claro-sports: futbol/gol/liga mx).
    final = [d for t, d in eventos if t == "upsert"][-1]
    assert final["marca"] == "claro-sports"
    assert float(final.get("score") or 0.0) > 0.0


def test_paso_agrupar_clasifica_por_ia_una_corroborada_sin_marca(monkeypatch):
    """Una historia SIN marca que el vocabulario no casa (jerga/entidad nueva) pero CORROBORADA
    por 2+ fuentes se clasifica por IA (no solo el breaking), de modo que no queda sin clasificar
    e invisible en los paneles por marca. Misma historia (mismo título, sin url) vista por dos outlets."""
    base_item = {
        "marca": "", "categoria": "internacional",
        "titulo": "Quarterly briefing on a niche protocol upgrade",  # sin vocabulario de ninguna marca
        "resumen": "", "url": "", "url_canonica": "",
        "idioma": "en", "senal": 1_000, "geo": "", "estado": "nuevo",
        "publicado_en": datetime.now(UTC).isoformat(),
        "capturado_en": datetime.now(UTC).isoformat(),
    }
    it1 = dict(base_item, id="i1", fuente_id="agencia-a", fuente_nombre="Agencia A")
    it2 = dict(base_item, id="i2", fuente_id="agencia-b", fuente_nombre="Agencia B")
    eventos: list[tuple[str, object]] = []
    monkeypatch.setattr(recolectar_daemon.config, "priorizar_perfil_activo", lambda: False)
    monkeypatch.setattr(recolectar_daemon.config, "rendimiento_ranking_activo", lambda: False)
    monkeypatch.setattr(recolectar_daemon.config, "clasificar_marca_ia", lambda: True)
    monkeypatch.setattr(recolectar_daemon, "_clasificar_marca_ia", lambda recalc: "unotv")
    monkeypatch.setattr(recolectar_daemon.repos, "limpiar_items_cluster_colgante", lambda: 0)
    monkeypatch.setattr(recolectar_daemon.repos, "items_sin_cluster",
                        lambda desde, lim: [dict(it1), dict(it2)])
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes", lambda ventana_h, *a, **k: [])
    monkeypatch.setattr(recolectar_daemon.repos, "obtener_noticia_cluster", lambda cid: None)
    monkeypatch.setattr(recolectar_daemon.repos, "items_de_cluster",
                        lambda cid, **kw: [dict(it1, cluster_id=cid), dict(it2, cluster_id=cid)])
    monkeypatch.setattr(recolectar_daemon.repos, "upsert_noticia_cluster",
                        lambda c: eventos.append(("upsert", dict(c))) or dict(c))
    monkeypatch.setattr(recolectar_daemon.repos, "asignar_cluster_items",
                        lambda asg: eventos.append(("asignar", dict(asg))))
    monkeypatch.setattr(recolectar_daemon.repos, "marcar_cluster_marca_ia",
                        lambda cid: eventos.append(("sello_ia", cid)))

    resumen = recolectar_daemon.paso_agrupar()

    # Una sola historia (mismo título, sin url => misma clave), corroborada por 2 outlets.
    assert resumen["clusters_nuevos"] == 1
    final = [d for t, d in eventos if t == "upsert"][-1]
    assert int(final.get("n_fuentes") or 0) == 2
    assert int(final.get("breaking") or 0) == 0  # corroborada, NO breaking
    # La IA le asigna marca aunque el título no case el vocabulario (no queda con marca='').
    assert final["marca"] == "unotv"
    assert ("sello_ia", final["id"]) in eventos  # se sella el encaje por IA (no lo pisa un recalc)


# --------------------------------------------------------------------------- #
# paso_rescore: el score ENVEJECE (la frescura decae sin items nuevos)          #
# --------------------------------------------------------------------------- #


def test_paso_rescore_baja_el_score_de_una_historia_vieja(monkeypatch):
    vieja = {
        "id": "c-vieja", "titulo": "Historia de hace tres días", "resumen": "",
        "marca": "", "n_fuentes": 2, "senal": 0, "breaking": 0, "estado": "nuevo",
        "ultimo_visto": (datetime.now(UTC) - timedelta(hours=60)).isoformat(),
        "score": 0.9,  # score persistido cuando era FRESCA (congelado desde entonces)
    }
    monkeypatch.setattr(recolectar_daemon.config, "priorizar_perfil_activo", lambda: False)
    monkeypatch.setattr(recolectar_daemon.config, "rendimiento_ranking_activo", lambda: False)
    guardados: list[dict] = []
    monkeypatch.setattr(recolectar_daemon.repos, "actualizar_scores_clusters",
                        lambda scores: guardados.append(dict(scores)) or len(scores))

    resumen = recolectar_daemon.paso_rescore([vieja], forzar=True)

    assert resumen["revisados"] == 1
    assert resumen["actualizados"] == 1
    # El re-score guarda score + explicación REFRESCADA (la razón acompaña al score nuevo).
    assert guardados
    cambio = guardados[0]["c-vieja"]
    assert cambio["score"] < 0.9  # la frescura decayó con el reloj
    assert isinstance(cambio["score_razon"], str)
    assert isinstance(cambio["score_desglose"], dict)


def test_paso_rescore_ignora_historias_usadas(monkeypatch):
    usada = {"id": "c-usada", "estado": "usado", "score": 0.5, "ultimo_visto": "", "titulo": "x"}
    def _no_guardar(scores):  # noqa: ANN001
        raise AssertionError("no debería re-puntuar historias usadas")
    monkeypatch.setattr(recolectar_daemon.repos, "actualizar_scores_clusters", _no_guardar)
    resumen = recolectar_daemon.paso_rescore([usada], forzar=True)
    assert resumen == {"revisados": 0, "actualizados": 0}


# --------------------------------------------------------------------------- #
# _fusionar_grupo: anti-TOCTOU (no absorbe una historia ya promovida)           #
# --------------------------------------------------------------------------- #


def test_fusionar_grupo_no_absorbe_historia_promovida_entre_lectura_y_fusion(monkeypatch):
    c1 = {"id": "c1", "titulo": "A", "n_fuentes": 2, "score": 0.6, "estado": "nuevo"}
    c2 = {"id": "c2", "titulo": "B", "n_fuentes": 1, "score": 0.2, "estado": "nuevo"}
    # Entre la lectura del lote y la fusión, el pipeline PROMOVIÓ c2 (publicacion_id sellado).
    promovida = dict(c2, estado="usado", publicacion_id="tema-9")
    monkeypatch.setattr(recolectar_daemon.repos, "obtener_noticia_cluster",
                        lambda cid: {"c1": dict(c1), "c2": promovida}.get(cid))
    def _no_tocar(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería reasignar ni borrar una historia promovida")
    monkeypatch.setattr(recolectar_daemon.repos, "asignar_cluster_items", _no_tocar)
    monkeypatch.setattr(recolectar_daemon.repos, "borrar_noticia_cluster", _no_tocar)

    fusionado = recolectar_daemon._fusionar_grupo(
        ["c1", "c2"], {"c1": c1, "c2": c2},
        pesos=None, breaking_peso=3.0, breaking_ventana_h=6,
        fuentes_baja=frozenset(), perfil_activo=False, ahora=datetime.now(UTC),
    )
    assert fusionado is False  # nada que fundir: la única absorbible ya fue promovida


# --------------------------------------------------------------------------- #
# paso_fusionar_semantica: throttle ligero (no re-llamar a Haiku en cada tick)   #
# --------------------------------------------------------------------------- #


def test_paso_fusionar_semantica_va_throttled(monkeypatch):
    """Tras una pasada (que sella el throttle), la siguiente sin `forzar` sale temprano y NO
    re-lee la ventana ni llama a Haiku; `forzar=True` la salta."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    lecturas = []
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: lecturas.append(ventana_h) or [])
    recolectar_daemon.paso_fusionar_semantica(forzar=True)   # corre y sella el throttle
    assert recolectar_daemon.paso_fusionar_semantica() == {"grupos": 0, "fusionadas": 0}  # throttled
    assert len(lecturas) == 1  # la 2ª no llegó a leer la ventana


def test_paso_fusionar_semantica_salta_si_el_lote_no_cambio(monkeypatch):
    """Skip-if-unchanged: si el conjunto candidato no cambió desde la última pasada, NO se llama al
    LLM (no hay nada nuevo que fusionar). Un cluster nuevo/actualizado mueve la huella y re-evalúa."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [
        {"id": "c1", "titulo": "A", "estado": "nuevo", "marca": "unotv", "ultimo_visto": "t1"},
        {"id": "c2", "titulo": "B", "estado": "nuevo", "marca": "unotv", "ultimo_visto": "t1"},
    ]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    llamadas = {"fusiones": 0, "macro": 0}

    def _fusiones(lote, **kw):
        llamadas["fusiones"] += 1
        return []

    def _macro(lote, **kw):
        llamadas["macro"] += 1
        return []

    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_fusiones", _fusiones)
    monkeypatch.setattr(recolectar_daemon.fusionar_semantica, "proponer_macro_eventos", _macro)

    # 1ª pasada: lote nuevo -> evalúa (llama al LLM) y sella la huella.
    recolectar_daemon.paso_fusionar_semantica()
    assert (llamadas["fusiones"], llamadas["macro"]) == (1, 1)

    # 2ª pasada con el MISMO lote (throttle reseteado para que no gatee él): huella idéntica -> salta.
    _comun._ultimo_fusionar = 0.0
    assert recolectar_daemon.paso_fusionar_semantica() == {"grupos": 0, "fusionadas": 0}
    assert (llamadas["fusiones"], llamadas["macro"]) == (1, 1)  # no se volvió a llamar

    # Cambia el marcador de un cluster (entró un item nuevo) -> la huella cambia -> re-evalúa.
    recientes[0]["ultimo_visto"] = "t2"
    _comun._ultimo_fusionar = 0.0
    recolectar_daemon.paso_fusionar_semantica()
    assert (llamadas["fusiones"], llamadas["macro"]) == (2, 2)


def test_paso_fusionar_semantica_gateado_off_no_corre(monkeypatch):
    """Con `KENI_PIPELINE_FUSIONAR=0` (apagado explícito) el paso es no-op, antes del throttle."""
    monkeypatch.setenv(config.ENV_PIPELINE_FUSIONAR, "0")
    def _no_leer(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("apagado: no debe leer la ventana")
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes", _no_leer)
    assert recolectar_daemon.paso_fusionar_semantica(forzar=True) == {"grupos": 0, "fusionadas": 0}


# --------------------------------------------------------------------------- #
# paso_caducidad: el pool envejece SOLO (TTL) dentro del barrido de ingesta     #
# --------------------------------------------------------------------------- #


def test_paso_caducidad_llama_con_los_umbrales_vivos(monkeypatch):
    llamadas = []
    monkeypatch.setattr(recolectar_daemon.repos, "caducar_pool",
                        lambda **kw: llamadas.append(kw) or {"caducadas": 2, "purgadas": 1, "items_purgados": 3})
    monkeypatch.setattr(recolectar_daemon.config, "noticias_ttl_horas", lambda: 48)
    monkeypatch.setattr(recolectar_daemon.config, "noticias_retencion_horas", lambda: 240)

    resumen = recolectar_daemon.paso_caducidad(forzar=True)

    assert resumen == {"caducadas": 2, "purgadas": 1, "items_purgados": 3}
    assert llamadas == [{"ttl_horas": 48, "retencion_horas": 240}]


def test_paso_caducidad_va_throttled(monkeypatch):
    llamadas = []
    monkeypatch.setattr(recolectar_daemon.repos, "caducar_pool",
                        lambda **kw: llamadas.append(kw) or {"caducadas": 0, "purgadas": 0, "items_purgados": 0})
    recolectar_daemon.paso_caducidad(forzar=True)   # corre y sella el throttle
    recolectar_daemon.paso_caducidad()              # dentro del intervalo: no corre
    assert len(llamadas) == 1


def test_registrar_actividad_ia_sella_metricas_acumuladas(entorno):
    """El registro de actividad del pool sella las MÉTRICAS acumuladas por el ejecutor síncrono
    (tokens/coste/duración de las llamadas Haiku de ese paso) y la toma RESETEA: el siguiente
    registro sin llamadas sale sin métricas (no se duplica el coste). Antes estas generaciones
    salían sin coste y las etapas Fusionar/Priorizar aparecían a cero en Producción."""
    import pytest

    from keni_consola import generaciones
    from keni_consola.dominio import traducir

    traducir.tomar_metricas_acumuladas()  # limpia restos del hilo
    traducir._acumular_metricas(
        {"tokens_in": 100, "tokens_out": 40, "total_cost_usd": 0.0123, "duration_ms": 4200}
    )
    recolectar_daemon._registrar_actividad_ia(
        "unotv", "Fusionar historias — UnoTV: 1 absorbida(s)", "SALIDA", prompt="PROMPT",
    )
    gen = next(
        g for g in generaciones.listar(limite=None)
        if (g.get("etiqueta") or "").startswith("Fusionar")
    )
    m = gen.get("metricas") or {}
    assert m.get("tokens_in") == 100
    assert m.get("tokens_out") == 40
    assert m.get("total_cost_usd") == pytest.approx(0.0123)
    assert m.get("duration_ms") == 4200

    recolectar_daemon._registrar_actividad_ia("unotv", "Priorizar historias — UnoTV", "S2")
    gen2 = next(
        g for g in generaciones.listar(limite=None)
        if (g.get("etiqueta") or "").startswith("Priorizar")
    )
    assert not gen2.get("metricas")


def test_partir_en_subtemas_persiste_cada_faceta(monkeypatch):
    """`_partir_en_subtemas` parte la familia (Haiku) y persiste cada subtema por sus ids."""
    from keni_consola.recolectar_daemon.pasos import fusionar_semantica as paso

    por_id = {
        "p1": {"id": "p1", "titulo": "México vence a Sudáfrica"},
        "p2": {"id": "p2", "titulo": "Argentina golea a Argelia"},
        "show": {"id": "show", "titulo": "Concierto en la inauguración"},
    }
    monkeypatch.setattr(
        paso.fusionar_semantica, "proponer_subtemas",
        lambda familia, *, ejecutor=None: [
            {"subtema": "Partidos", "ids": ["p1", "p2"]},
            {"subtema": "Espectáculo", "ids": ["show"]},
        ],
    )
    persistidos: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        paso.repos, "marcar_clusters_subtema",
        lambda ids, subtema: (persistidos.append((list(ids), subtema)), len(ids))[1],
    )

    n = paso._partir_en_subtemas("Mundial 2026", ["p1", "p2", "show"], por_id, ejecutor=None)

    assert n == 3
    assert persistidos == [(["p1", "p2"], "Partidos"), (["show"], "Espectáculo")]


def test_partir_en_subtemas_familia_de_uno_no_llama_a_haiku(monkeypatch):
    """Con <2 historias no hay nada que partir: ni Haiku ni persistencia."""
    from keni_consola.recolectar_daemon.pasos import fusionar_semantica as paso

    def _no_llamar(*a, **k):
        raise AssertionError("no debería invocarse con familia de uno")

    monkeypatch.setattr(paso.fusionar_semantica, "proponer_subtemas", _no_llamar)
    n = paso._partir_en_subtemas("Mundial 2026", ["solo"], {"solo": {"id": "solo", "titulo": "X"}}, ejecutor=None)
    assert n == 0

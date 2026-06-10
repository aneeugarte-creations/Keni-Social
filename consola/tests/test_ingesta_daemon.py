"""Tests del daemon de ingesta (`ingesta_daemon`): planificación PURA + barrido con fakes.

`planificar_proximo` es PURA (sin reloj ni BD): se verifica la cadencia en éxito y el backoff
exponencial acotado en error. `ejecutar_barrido` se prueba con `repos`/`db` parcheados (feeds
falsos, fetcher falso vía monkeypatch de la descarga) para que NUNCA se toque la red ni
Postgres: se comprueba que persiste items nuevos y que programa el próximo sondeo (intervalo en
éxito, pausa de backoff en error).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

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
    assert plan["proximo_sondeo"] == "2026-06-05T12:10:00"  # canon UTC sin offset (tiempo.iso_utc)


def test_planificar_error_aplica_backoff_exponencial():
    # Primer error: espera = intervalo * 2^1 = 1200s.
    p1 = ingesta_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=0
    )
    assert p1["errores_seguidos"] == 1
    assert p1["proximo_sondeo"] == "2026-06-05T12:20:00"
    assert p1["pausado_hasta"] == p1["proximo_sondeo"]
    # Segundo error: espera = 600 * 2^2 = 2400s.
    p2 = ingesta_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=1
    )
    assert p2["errores_seguidos"] == 2
    assert p2["proximo_sondeo"] == "2026-06-05T12:40:00"


def test_planificar_backoff_no_supera_el_tope():
    # Muchos errores: la espera se acota al tope (1h por defecto), no crece sin límite.
    plan = ingesta_daemon.planificar_proximo(
        ahora=_AHORA, intervalo_seg=600, error=True, errores_previos=50,
        backoff_tope_seg=3600,
    )
    assert plan["proximo_sondeo"] == "2026-06-05T13:00:00"  # +3600s


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
    """Parchea db.lock_barrido, repos.feeds_vencidos y la descarga de http_feed.

    Apaga además el FILTRO DE ENTRADA por vocabulario (def ON): estos tests cubren la
    mecánica del barrido (persistencia, planificación, backoff) con titulares neutros
    («Nota uno») que no casan ninguna agenda; el filtro tiene sus propios tests abajo.
    """
    monkeypatch.setenv(config.ENV_INGESTA_FILTRO, "0")
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
    # Aditivo (Ola D): el resumen lleva más claves (clustering/traduccion/auto_desactivados);
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


def test_barrido_sin_feeds_vencidos_corre_los_pasos_post_rss(monkeypatch):
    """Sin feeds RSS vencidos, el barrido NO sondea nada pero los pasos post-RSS corren igual.

    Antes un `return` temprano dejaba los items de Trends/agencias SIN clusterizar
    indefinidamente si ningún RSS estaba vencido (Trends inserta por su propio daemon).
    """
    _parchear_comun(monkeypatch, feeds=[], fetcher=lambda _u: _FEED_OK)
    llamados: list[str] = []
    monkeypatch.setattr(ingesta_daemon, "paso_agencias",
                        lambda: llamados.append("agencias") or {"items": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_clustering",
                        lambda: llamados.append("clustering") or {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_rescore",
                        lambda *a, **k: llamados.append("rescore") or {"revisados": 0, "actualizados": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_fusion_semantica",
                        lambda **k: llamados.append("fusion") or {"grupos": 0, "fusionadas": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion",
                        lambda: llamados.append("traduccion") or {"traducidos": 0, "candidatos": 0})

    resumen = ingesta_daemon.ejecutar_barrido()
    assert resumen["feeds"] == 0
    assert resumen["items_nuevos"] == 0
    assert resumen["errores"] == 0
    # Los pasos post-RSS corrieron AUNQUE no hubiera feeds vencidos.
    assert llamados == ["agencias", "clustering", "rescore", "fusion", "traduccion"]


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


def test_barrido_salta_feeds_de_marca_apagada(monkeypatch):
    """Excepción por marca de KENI_PIPELINE_SELECCION: el feed de una marca apagada se salta; el feed
    COMPARTIDO (marca vacía) y el de una marca permitida sí se sondean."""
    feed_apagado = {"id": "off", "nombre": "Off", "url": "https://93.184.216.34/a",
                    "categoria": "mx", "marca": "nacion-gamer", "errores_seguidos": 0}
    feed_permitido = {"id": "on", "nombre": "On", "url": "https://93.184.216.34/b",
                      "categoria": "mx", "marca": "claro-sports", "errores_seguidos": 0}
    feed_compartido = {"id": "shared", "nombre": "Shared", "url": "https://93.184.216.34/c",
                       "categoria": "mx", "marca": "", "errores_seguidos": 0}
    # Override falsy de KENI_PIPELINE_SELECCION solo para nacion-gamer -> esa marca queda apagada.
    overrides = {config.clave_por_marca(config.ENV_PIPELINE_SELECCION, "nacion-gamer"): "0"}
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: overrides.get(clave))

    registrados = []
    _parchear_comun(monkeypatch, feeds=[feed_apagado, feed_permitido, feed_compartido],
                    fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append(fid))
    monkeypatch.setattr(ingesta_daemon, "paso_clustering", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion", lambda: {"traducidos": 0, "candidatos": 0})

    resumen = ingesta_daemon.ejecutar_barrido()
    # El feed apagado NO se sondea; el permitido y el compartido sí.
    assert resumen["feeds"] == 2
    assert set(registrados) == {"on", "shared"}
    assert "off" not in registrados


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
    monkeypatch.setattr(ingesta_daemon, "paso_clustering", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion", lambda: {"traducidos": 0, "candidatos": 0})


def test_filtro_entrada_descarta_lo_que_no_casa_la_agenda(monkeypatch):
    """Feed de marca: solo se archiva lo que casa el vocabulario; lo filtrado se cuenta."""
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    persistidos, registrados = [], []
    _parchear_filtro(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_MIXTO)
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))

    resumen = ingesta_daemon.ejecutar_barrido()

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
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)

    resumen = ingesta_daemon.ejecutar_barrido()

    assert resumen["items_nuevos"] == 4  # 2 del propio + 2 del compartido, sin filtrar
    assert resumen["items_filtrados"] == 0


def test_filtro_entrada_apagado_archiva_todo(monkeypatch):
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    persistidos = []
    _parchear_filtro(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_MIXTO)
    monkeypatch.setenv(config.ENV_INGESTA_FILTRO, "0")  # apagado: comportamiento anterior
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)

    resumen = ingesta_daemon.ejecutar_barrido()
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
    monkeypatch.setattr(ingesta_daemon.ingesta, "filtrar_por_vocabulario", _revienta)
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)

    resumen = ingesta_daemon.ejecutar_barrido()
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
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))
    # Aislar clustering/traducción (no relevantes aquí; sin BD).
    monkeypatch.setattr(ingesta_daemon, "paso_clustering", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion", lambda: {"traducidos": 0, "candidatos": 0})

    resumen = ingesta_daemon.ejecutar_barrido()
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
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))
    monkeypatch.setattr(ingesta_daemon, "paso_clustering", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion", lambda: {"traducidos": 0, "candidatos": 0})

    resumen = ingesta_daemon.ejecutar_barrido()
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
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed",
                        lambda fid, **kw: registrados.append((fid, kw)))
    monkeypatch.setattr(ingesta_daemon, "paso_clustering", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion", lambda: {"traducidos": 0, "candidatos": 0})

    ingesta_daemon.ejecutar_barrido()
    _fid, kw = registrados[0]
    assert kw["errores_seguidos"] == 0
    assert kw["activo"] is True
    assert kw["desactivado_auto"] is False


# --------------------------------------------------------------------------- #
# Paso de TRADUCCIÓN (Ola D) con ejecutor falso (sin red ni BD)                #
# --------------------------------------------------------------------------- #


def test_paso_traduccion_marca_clusters_y_guarda_es(monkeypatch):
    candidatos = [
        {"id": "c1", "titulo": "Foreign one", "resumen": "Body one", "idioma": "en"},
        {"id": "c2", "titulo": "Foreign two", "resumen": "Body two", "idioma": "fr"},
    ]
    monkeypatch.setattr(ingesta_daemon.repos, "clusters_extranjeros_sin_traducir",
                        lambda ventana_h, **kw: list(candidatos))
    guardados = []
    monkeypatch.setattr(ingesta_daemon.repos, "marcar_cluster_traducido",
                        lambda cid, **kw: guardados.append((cid, kw)) or {"id": cid})

    # Ejecutor falso: devuelve traducciones ES deterministas para cada id (sin llamar a claude).
    def _ejecutor_ok(prompt, _dir):
        import json as _json
        import re
        cola = prompt.partition("Lista de ítems:")[2] or prompt
        m = re.search(r"\[.*\]", cola, re.DOTALL)
        items = _json.loads(m.group(0)) if m else []
        return _json.dumps({"traducciones": [
            {"id": it["id"], "titulo_es": "ES " + it["titulo"], "resumen_es": "ES " + it["resumen"]}
            for it in items
        ]})

    resumen = ingesta_daemon.paso_traduccion(ejecutor=_ejecutor_ok)
    assert resumen == {"traducidos": 2, "candidatos": 2}
    por_id = dict(guardados)
    assert por_id["c1"]["titulo_es"] == "ES Foreign one"
    assert por_id["c1"]["titulo_original"] == "Foreign one"
    assert por_id["c2"]["resumen_es"] == "ES Body two"


def test_paso_traduccion_sin_candidatos_no_hace_nada(monkeypatch):
    monkeypatch.setattr(ingesta_daemon.repos, "clusters_extranjeros_sin_traducir",
                        lambda ventana_h, **kw: [])
    def _no_guardar(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería guardar sin candidatos")
    monkeypatch.setattr(ingesta_daemon.repos, "marcar_cluster_traducido", _no_guardar)
    assert ingesta_daemon.paso_traduccion() == {"traducidos": 0, "candidatos": 0}


# --------------------------------------------------------------------------- #
# Paso de AGENCIAS (Fase 2): vuelca Reuters/AFP al pool (con fakes, sin red)   #
# --------------------------------------------------------------------------- #


def test_paso_agencias_sin_credencial_es_noop(monkeypatch):
    # traer_items degrada honesto a [] sin credencial -> nada que persistir, sin red.
    monkeypatch.setattr(ingesta_daemon.agencias, "traer_items", lambda _ag: [])
    def _no_persistir(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería persistir sin items de agencia")
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items", _no_persistir)
    assert ingesta_daemon.paso_agencias() == {"items": 0}


def test_paso_agencias_ingiere_items_al_pool(monkeypatch):
    crudos = {
        "reuters": [{"titulo": "Nota R", "resumen": "", "enlace": "https://r/1", "fecha": "", "fuente": "Reuters", "clave": "https://r/1"}],
        "afp": [{"titulo": "Nota A", "resumen": "", "enlace": "https://a/1", "fecha": "", "fuente": "AFP", "clave": "https://a/1"}],
    }
    monkeypatch.setattr(ingesta_daemon.agencias, "traer_items", lambda ag: crudos.get(ag, []))
    persistidos = []
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))

    resumen = ingesta_daemon.paso_agencias()
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
    monkeypatch.setattr(ingesta_daemon.agencias, "traer_items", _traer)
    persistidos = []
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))

    resumen = ingesta_daemon.paso_agencias()
    assert resumen == {"items": 1}
    assert [f["fuente_id"] for f in persistidos] == ["agencia-afp"]


def test_barrido_ingiere_agencias_y_suma_a_items_nuevos(monkeypatch):
    # El barrido completo: RSS persiste 2 + agencias persisten 1 -> items_nuevos == 3.
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    persistidos = []
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items",
                        lambda items: persistidos.extend(items) or len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)
    monkeypatch.setattr(ingesta_daemon, "paso_clustering", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion", lambda: {"traducidos": 0, "candidatos": 0})
    monkeypatch.setattr(ingesta_daemon.agencias, "traer_items",
                        lambda ag: [{"titulo": "Ag", "resumen": "", "enlace": f"https://{ag}/1", "fecha": "", "fuente": ag.upper(), "clave": f"https://{ag}/1"}] if ag == "reuters" else [])

    resumen = ingesta_daemon.ejecutar_barrido()
    assert resumen["items_nuevos"] == 3  # 2 RSS + 1 agencia
    assert resumen["agencias"] == {"items": 1}
    assert any(f.get("fuente_id") == "agencia-reuters" for f in persistidos)


def test_barrido_no_aborta_si_paso_agencias_revienta(monkeypatch):
    # Si paso_agencias lanzara, el barrido lo captura y sigue con RSS/clustering.
    feed = {"id": "f1", "nombre": "F1", "url": "https://93.184.216.34/x", "categoria": "mx",
            "marca": "unotv", "errores_seguidos": 0}
    _parchear_comun(monkeypatch, feeds=[feed], fetcher=lambda _u: _FEED_OK)
    monkeypatch.setattr(ingesta_daemon.repos, "crear_noticias_items", lambda items: len(items))
    monkeypatch.setattr(ingesta_daemon.repos, "registrar_sondeo_feed", lambda fid, **kw: None)
    monkeypatch.setattr(ingesta_daemon, "paso_clustering", lambda: {"items": 0, "clusters_nuevos": 0})
    monkeypatch.setattr(ingesta_daemon, "paso_traduccion", lambda: {"traducidos": 0, "candidatos": 0})
    def _revienta():
        raise RuntimeError("boom")
    monkeypatch.setattr(ingesta_daemon, "paso_agencias", _revienta)

    resumen = ingesta_daemon.ejecutar_barrido()
    # RSS no se ve afectado; agencias cae a su default sin sumar.
    assert resumen["items_nuevos"] == 2
    assert resumen["agencias"] == {"items": 0}


# --------------------------------------------------------------------------- #
# Actividad IA del pool: fusión semántica deja constancia VISIBLE (noticias-ia) #
# --------------------------------------------------------------------------- #


def test_paso_fusion_semantica_registra_actividad_ia(monkeypatch):
    """Al fundir, sella `noticias-ia` con el Haiku REAL (prompt + salida) + el resumen humano."""
    monkeypatch.setattr(ingesta_daemon.config, "fusion_semantica_activa", lambda: True)
    recientes = [
        {"id": "c1", "titulo": "Remontada épica", "estado": "nuevo", "marca": "unotv"},
        {"id": "c2", "titulo": "Remontada increíble", "estado": "nuevo", "marca": "unotv"},
    ]
    monkeypatch.setattr(ingesta_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: list(recientes))

    def _fake_proponer(lote, *, ejecutor=None, al_ejecutar=None):
        if al_ejecutar:  # el daemon captura el prompt+salida reales de Haiku
            al_ejecutar("PROMPT-HAIKU-FUSION", '{"grupos": [["c1","c2"]]}')
        return [["c1", "c2"]]
    monkeypatch.setattr(ingesta_daemon.fusion_semantica, "proponer_fusiones", _fake_proponer)
    monkeypatch.setattr(ingesta_daemon, "_fusionar_grupo", lambda *a, **k: True)
    registradas: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        ingesta_daemon, "_registrar_actividad_ia",
        lambda marca, etiqueta, salida, *, prompt="":
            registradas.append((marca, etiqueta, salida, prompt)),
    )

    resumen = ingesta_daemon.paso_fusion_semantica()
    assert resumen == {"grupos": 1, "fusionadas": 1}
    assert len(registradas) == 1
    marca, etiqueta, salida, prompt = registradas[0]
    assert marca == "unotv"
    assert "Fusión de historias" in etiqueta
    assert prompt == "PROMPT-HAIKU-FUSION"  # el prompt REAL de Haiku
    assert '{"grupos"' in salida  # la salida REAL de Haiku
    assert "Remontada épica" in salida  # + el resumen humano de qué se unió


def test_paso_fusion_semantica_sin_fusiones_no_registra(monkeypatch):
    """Si Haiku no agrupa nada, no hay generación de actividad (sin ruido a 0)."""
    monkeypatch.setattr(ingesta_daemon.config, "fusion_semantica_activa", lambda: True)
    recientes = [
        {"id": "c1", "titulo": "A", "estado": "nuevo", "marca": "unotv"},
        {"id": "c2", "titulo": "B", "estado": "nuevo", "marca": "unotv"},
    ]
    monkeypatch.setattr(ingesta_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: list(recientes))
    monkeypatch.setattr(ingesta_daemon.fusion_semantica, "proponer_fusiones", lambda lote, **kw: [])
    registradas: list[object] = []
    monkeypatch.setattr(ingesta_daemon, "_registrar_actividad_ia",
                        lambda *a, **k: registradas.append(a))

    assert ingesta_daemon.paso_fusion_semantica() == {"grupos": 0, "fusionadas": 0}
    assert registradas == []


# --------------------------------------------------------------------------- #
# paso_clustering: marca por vocabulario + durabilidad + escritura en lote     #
# --------------------------------------------------------------------------- #


def test_paso_clustering_asigna_marca_por_vocabulario_a_historia_solo_trends(monkeypatch):
    """Un cluster formado SOLO por items sin marca (Trends) acaba con marca asignada por
    vocabulario y, por tanto, SELECCIONABLE por la promoción por marca (antes quedaba con
    marca='' e invisible para todas)."""
    item = {
        "id": "i1", "fuente_id": "google-trends", "fuente_nombre": "ESPN",
        "categoria": "tendencias", "marca": "",  # <- Trends llega SIN marca
        "titulo": "Futbol: gol agónico en la final de la liga mx",
        "resumen": "", "url": "https://e.com/n1", "url_canonica": "e.com/n1",
        "idioma": "es", "senal": 50_000, "geo": "MX", "estado": "nuevo",
        "publicado_en": datetime.now(UTC).isoformat(),
        "capturado_en": datetime.now(UTC).isoformat(),
    }
    eventos: list[tuple[str, object]] = []
    monkeypatch.setattr(ingesta_daemon.config, "perfil_editorial_activo", lambda: False)
    monkeypatch.setattr(ingesta_daemon.config, "rendimiento_ranking_activo", lambda: False)
    monkeypatch.setattr(ingesta_daemon.repos, "limpiar_items_cluster_colgante", lambda: 0)
    monkeypatch.setattr(ingesta_daemon.repos, "items_sin_cluster", lambda desde, lim: [dict(item)])
    monkeypatch.setattr(ingesta_daemon.repos, "clusters_recientes", lambda ventana_h, *a, **k: [])
    monkeypatch.setattr(ingesta_daemon.repos, "obtener_noticia_cluster", lambda cid: None)
    monkeypatch.setattr(ingesta_daemon.repos, "items_de_cluster",
                        lambda cid, **kw: [dict(item, cluster_id=cid)])
    monkeypatch.setattr(ingesta_daemon.repos, "upsert_noticia_cluster",
                        lambda c: eventos.append(("upsert", dict(c))) or dict(c))
    monkeypatch.setattr(ingesta_daemon.repos, "asignar_cluster_items",
                        lambda asg: eventos.append(("asignar", dict(asg))))

    resumen = ingesta_daemon.paso_clustering()

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
    monkeypatch.setattr(ingesta_daemon.config, "perfil_editorial_activo", lambda: False)
    monkeypatch.setattr(ingesta_daemon.config, "rendimiento_ranking_activo", lambda: False)
    guardados: list[dict] = []
    monkeypatch.setattr(ingesta_daemon.repos, "actualizar_scores_clusters",
                        lambda scores: guardados.append(dict(scores)) or len(scores))

    resumen = ingesta_daemon.paso_rescore([vieja], forzar=True)

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
    monkeypatch.setattr(ingesta_daemon.repos, "actualizar_scores_clusters", _no_guardar)
    resumen = ingesta_daemon.paso_rescore([usada], forzar=True)
    assert resumen == {"revisados": 0, "actualizados": 0}


# --------------------------------------------------------------------------- #
# _fusionar_grupo: anti-TOCTOU (no absorbe una historia ya promovida)           #
# --------------------------------------------------------------------------- #


def test_fusionar_grupo_no_absorbe_historia_promovida_entre_lectura_y_fusion(monkeypatch):
    c1 = {"id": "c1", "titulo": "A", "n_fuentes": 2, "score": 0.6, "estado": "nuevo"}
    c2 = {"id": "c2", "titulo": "B", "n_fuentes": 1, "score": 0.2, "estado": "nuevo"}
    # Entre la lectura del lote y la fusión, el pipeline PROMOVIÓ c2 (contenido_id sellado).
    promovida = dict(c2, estado="usado", contenido_id="tema-9")
    monkeypatch.setattr(ingesta_daemon.repos, "obtener_noticia_cluster",
                        lambda cid: {"c1": dict(c1), "c2": promovida}.get(cid))
    def _no_tocar(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("no debería reasignar ni borrar una historia promovida")
    monkeypatch.setattr(ingesta_daemon.repos, "asignar_cluster_items", _no_tocar)
    monkeypatch.setattr(ingesta_daemon.repos, "borrar_noticia_cluster", _no_tocar)

    fusionado = ingesta_daemon._fusionar_grupo(
        ["c1", "c2"], {"c1": c1, "c2": c2},
        pesos=None, breaking_fuentes=3, breaking_ventana_h=6,
        fuentes_baja=frozenset(), perfil_activo=False, ahora=datetime.now(UTC),
    )
    assert fusionado is False  # nada que fundir: la única absorbible ya fue promovida

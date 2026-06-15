"""Tests PUROS (sin DB ni red) del dominio de clustering de historias (`dominio.clustering`).

Cubre la identidad de cluster (`clave_cluster`: url canónica sin query vs hash de título), la
asignación incremental (`asignar`: cruce por misma url, fuzzy de título, ventana/umbral, item
nuevo), el recálculo de agregados (`recalcular`: n_items/n_fuentes/idiomas/señal/representativo/
breaking) y el scoring (`puntuar`: fórmula documentada + monotonía por señal). Todo determinista,
con `ahora` inyectado: nunca se toca el reloj real, la BD ni la red.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from keni_consola.dominio import clustering

_T0 = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)


def _item(**campos):
    base = {
        "fuente_id": "f1",
        "titulo": "Titulo de prueba sobre algo",
        "resumen": "Resumen",
        "idioma": "es",
        "senal": 0,
        "marca": "unotv",
        "categoria": "mx",
        "geo": "MX",
        "url": "https://example.com/n",
        "publicado_en": _T0.isoformat(),
    }
    base.update(campos)
    return base


# --------------------------------------------------------------------------- #
# clave_cluster / url_canonica_clustering                                       #
# --------------------------------------------------------------------------- #


def test_clave_por_url_ignora_query_y_tracking():
    a = clustering.clave_cluster(_item(url="https://www.example.com/nota-1?utm_source=x&ref=y"))
    b = clustering.clave_cluster(_item(url="https://example.com/nota-1?pagina=2"))
    assert a == "url:example.com/nota-1"
    assert a == b  # misma nota, distinta query → misma clave


def test_clave_por_titulo_si_no_hay_url():
    k = clustering.clave_cluster(_item(url="", titulo="¡Selección Mexicana golea!"))
    assert k.startswith("t:")
    # Título equivalente (sin signos) colisiona.
    assert k == clustering.clave_cluster(_item(url="", titulo="seleccion mexicana golea"))


def test_clave_vacia_sin_url_ni_titulo():
    assert clustering.clave_cluster({"url": "", "titulo": ""}) == ""


# --------------------------------------------------------------------------- #
# asignar                                                                       #
# --------------------------------------------------------------------------- #


def test_asignar_une_por_misma_url():
    item = _item(url="https://example.com/nota-1?utm_source=tw", titulo="Algo distinto")
    cluster = {"id": "c1", "clave": "url:example.com/nota-1", "titulo": "Titular original"}
    assert clustering.asignar(item, [cluster]) == "c1"


def test_asignar_une_por_titulo_fuzzy():
    cluster = {
        "id": "c2",
        "clave": "t:abc",
        "titulo": "El presidente anuncia una nueva reforma para los estados",
    }
    item = _item(url="", titulo="El presidente anuncia nueva reforma para los estados")
    assert clustering.asignar(item, [cluster], umbral=0.82) == "c2"


def test_asignar_cluster_nuevo_si_nada_casa():
    cluster = {"id": "c2", "clave": "t:abc", "titulo": "Reforma energética en el senado"}
    item = _item(url="", titulo="Resultados de la jornada de fútbol del domingo")
    assert clustering.asignar(item, [cluster], umbral=0.82) is None


def test_asignar_respeta_umbral():
    cluster = {"id": "c2", "clave": "t:abc", "titulo": "Gana el equipo local el partido de hoy"}
    item = _item(url="", titulo="Pierde el equipo local el partido de ayer")
    # Con umbral muy alto no une; con uno bajo sí.
    assert clustering.asignar(item, [cluster], umbral=0.99) is None
    assert clustering.asignar(item, [cluster], umbral=0.5) == "c2"


def test_asignar_titulos_muy_cortos_no_entran_fuzzy():
    cluster = {"id": "c2", "clave": "t:nfl", "titulo": "NFL"}
    item = _item(url="", titulo="F1")
    assert clustering.asignar(item, [cluster], umbral=0.3) is None


def test_asignar_gana_el_mas_parecido():
    c_lejos = {"id": "lejos", "clave": "t:1", "titulo": "Reforma fiscal en discusion general"}
    c_cerca = {"id": "cerca", "clave": "t:2", "titulo": "El presidente anuncia nueva reforma estados"}
    item = _item(url="", titulo="El presidente anuncia nueva reforma para los estados")
    assert clustering.asignar(item, [c_lejos, c_cerca], umbral=0.6) == "cerca"


def test_asignar_une_por_titulo_traducido():
    # La historia extranjera ya TRADUCIDA debe atrapar al titular en español que llega después.
    cluster = {
        "id": "c-ext",
        "clave": "t:abc",
        "titulo": "Earthquake of 6.2 shakes Guerrero this afternoon",
        "titulo_es": "Un sismo de 6.2 sacude Guerrero esta tarde",
    }
    item = _item(url="", titulo="Sismo de 6.2 sacude Guerrero esta tarde")
    assert clustering.asignar(item, [cluster], umbral=0.82) == "c-ext"
    # El Asignador (índice) toma la misma decisión.
    asignador = clustering.Asignador([cluster], umbral=0.82)
    assert asignador.asignar(item) == "c-ext"


def test_fuzzy_veta_numeros_incompatibles():
    # Mismo texto, cifras DISTINTAS = eventos distintos: el fuzzy no debe unirlos.
    cluster = {"id": "c1", "clave": "t:abc", "titulo": "Sismo de magnitud 5.8 sacude Guerrero hoy"}
    item = _item(url="", titulo="Sismo de magnitud 7.1 sacude Guerrero hoy")
    assert clustering.asignar(item, [cluster], umbral=0.7) is None
    # Con la MISMA cifra sí une (la compatibilidad de números no castiga el caso bueno).
    mismo = _item(url="", titulo="Sismo de magnitud 5.8 sacude Guerrero hoy")
    assert clustering.asignar(mismo, [cluster], umbral=0.7) == "c1"


def test_fuzzy_sin_numeros_no_se_penaliza():
    cluster = {"id": "c1", "clave": "t:abc", "titulo": "Sismo de magnitud 5.8 sacude Guerrero"}
    item = _item(url="", titulo="Sismo sacude Guerrero esta tarde")
    # Un lado sin números no dispara el veto (puede unir o no por ratio, pero no por veto).
    assert not clustering._numeros_incompatibles(
        clustering.similitud.clave_fuzzy(item["titulo"]),
        clustering.similitud.clave_fuzzy(cluster["titulo"]),
    )


# --------------------------------------------------------------------------- #
# grupos_lexicos: merge tardío de la ventana                                    #
# --------------------------------------------------------------------------- #


def test_grupos_lexicos_agrupa_duplicados_tardios():
    clusters = [
        {"id": "a", "titulo": "El presidente anuncia una nueva reforma para los estados", "categoria": "mx"},
        {"id": "b", "titulo": "El presidente anuncia nueva reforma para los estados", "categoria": "mx"},
        {"id": "c", "titulo": "Resultados de la jornada de futbol del domingo", "categoria": "deportes"},
    ]
    grupos = clustering.grupos_lexicos(clusters, umbral=0.86)
    assert grupos == [["a", "b"]]


def test_grupos_lexicos_no_cruza_categorias_distintas():
    clusters = [
        {"id": "a", "titulo": "El presidente anuncia una nueva reforma para los estados", "categoria": "mx"},
        {"id": "b", "titulo": "El presidente anuncia nueva reforma para los estados", "categoria": "deportes"},
    ]
    assert clustering.grupos_lexicos(clusters, umbral=0.86) == []
    # Una categoría VACÍA casa con cualquiera.
    clusters[1]["categoria"] = ""
    assert clustering.grupos_lexicos(clusters, umbral=0.86) == [["a", "b"]]


def test_grupos_lexicos_une_por_traduccion():
    clusters = [
        {"id": "ext", "titulo": "Earthquake shakes Mexico City",
         "titulo_es": "Un sismo sacude la Ciudad de Mexico esta manana", "categoria": "mx"},
        {"id": "mx", "titulo": "Un sismo sacude la Ciudad de Mexico esta manana", "categoria": "mx"},
    ]
    assert clustering.grupos_lexicos(clusters, umbral=0.86) == [["ext", "mx"]]


def test_grupos_lexicos_respeta_veto_de_numeros():
    clusters = [
        {"id": "a", "titulo": "Sismo de magnitud 5.8 sacude Guerrero hoy", "categoria": "mx"},
        {"id": "b", "titulo": "Sismo de magnitud 7.1 sacude Guerrero hoy", "categoria": "mx"},
    ]
    assert clustering.grupos_lexicos(clusters, umbral=0.5) == []


def test_grupos_lexicos_umbral_cero_apaga():
    clusters = [
        {"id": "a", "titulo": "El presidente anuncia una nueva reforma", "categoria": ""},
        {"id": "b", "titulo": "El presidente anuncia una nueva reforma", "categoria": ""},
    ]
    assert clustering.grupos_lexicos(clusters, umbral=0) == []


# --------------------------------------------------------------------------- #
# recalcular                                                                    #
# --------------------------------------------------------------------------- #


def _base_cluster():
    return {"id": "c1", "estado": "nuevo", "contenido_id": "", "creado": ""}


def test_recalcular_agrega_fuentes_idiomas_y_senal():
    items = [
        _item(fuente_id="a", idioma="es", senal=100, publicado_en=_T0.isoformat()),
        _item(fuente_id="b", idioma="en", senal=5000, publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
        _item(fuente_id="a", idioma="es", senal=10, publicado_en=(_T0 + timedelta(hours=2)).isoformat()),
    ]
    r = clustering.recalcular(_base_cluster(), items)
    assert r["n_items"] == 3
    assert r["n_fuentes"] == 2  # fuente_id distintos (a, b)
    assert r["idiomas"] == ["en", "es"]
    assert r["senal"] == 5000  # máximo
    assert r["primer_visto"] == _T0.isoformat()
    assert r["ultimo_visto"] == (_T0 + timedelta(hours=2)).isoformat()
    assert r["marca"] == "unotv"


def test_recalcular_titulo_representativo_prefiere_es():
    items = [
        _item(fuente_id="a", idioma="en", senal=9000, titulo="Big news in english today"),
        _item(fuente_id="b", idioma="es", senal=10, titulo="Gran noticia en español hoy"),
    ]
    r = clustering.recalcular(_base_cluster(), items)
    assert r["titulo"] == "Gran noticia en español hoy"


def test_recalcular_breaking_si_masa_de_fuentes_en_la_ventana_actual():
    # Tres outlets NORMALES (peso 1.0) sumados en la ventana actual: masa 3.0 >= 3.0.
    items = [
        _item(fuente_id="a", url="https://a.com/n", publicado_en=_T0.isoformat()),
        _item(fuente_id="b", url="https://b.com/n", publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
        _item(fuente_id="c", url="https://c.com/n", publicado_en=(_T0 + timedelta(hours=2)).isoformat()),
    ]
    r = clustering.recalcular(
        _base_cluster(), items, breaking_peso=3.0, breaking_ventana_h=6,
        ahora=_T0 + timedelta(hours=2),
    )
    assert r["breaking"] == 1
    assert r["velocidad"] == 0.75  # masa 3.0 / satura 4.0


def test_recalcular_dos_potentes_a_la_vez_son_breaking():
    # 2 fuentes POTENTES (peso 2.0) casi a la vez: masa 4.0 >= 3.0 → última hora.
    items = [
        _item(fuente_id="a", url="https://reuters.com/n", fuente_peso=2.0, publicado_en=_T0.isoformat()),
        _item(fuente_id="b", url="https://bbc.com/n", fuente_peso=2.0,
              publicado_en=(_T0 + timedelta(minutes=15)).isoformat()),
    ]
    r = clustering.recalcular(
        _base_cluster(), items, breaking_peso=3.0, breaking_ventana_h=6,
        ahora=_T0 + timedelta(minutes=20),
    )
    assert r["breaking"] == 1
    assert r["velocidad"] == 1.0  # masa 4.0 satura la señal


def test_recalcular_dos_normales_no_son_breaking():
    items = [
        _item(fuente_id="a", url="https://a.com/n", publicado_en=_T0.isoformat()),
        _item(fuente_id="b", url="https://b.com/n", publicado_en=(_T0 + timedelta(minutes=15)).isoformat()),
    ]
    r = clustering.recalcular(
        _base_cluster(), items, breaking_peso=3.0, breaking_ventana_h=6,
        ahora=_T0 + timedelta(minutes=20),
    )
    assert r["breaking"] == 0  # masa 2.0 < 3.0
    assert r["velocidad"] == 0.5


def test_recalcular_breaking_decae_al_envejecer():
    # La MISMA historia, evaluada 10 horas después: los outlets salen de la ventana actual
    # (anclada en ahora) y el flag decae — un breaking de ayer deja de serlo.
    items = [
        _item(fuente_id="a", url="https://a.com/n", publicado_en=_T0.isoformat()),
        _item(fuente_id="b", url="https://b.com/n", publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
        _item(fuente_id="c", url="https://c.com/n", publicado_en=(_T0 + timedelta(hours=2)).isoformat()),
    ]
    r = clustering.recalcular(
        _base_cluster(), items, breaking_peso=3.0, breaking_ventana_h=6,
        ahora=_T0 + timedelta(hours=12),
    )
    assert r["breaking"] == 0
    assert r["velocidad"] == 0.0


def test_recalcular_no_breaking_si_fuentes_dispersas_en_el_tiempo():
    items = [
        _item(fuente_id="a", url="https://a.com/n", publicado_en=_T0.isoformat()),
        _item(fuente_id="b", url="https://b.com/n", publicado_en=(_T0 + timedelta(hours=10)).isoformat()),
        _item(fuente_id="c", url="https://c.com/n", publicado_en=(_T0 + timedelta(hours=30)).isoformat()),
    ]
    r = clustering.recalcular(
        _base_cluster(), items, breaking_peso=3.0, breaking_ventana_h=6,
        ahora=_T0 + timedelta(hours=30),
    )
    assert r["breaking"] == 0  # solo 1 outlet en la ventana actual


def test_recalcular_conserva_identidad_del_cluster():
    base = {"id": "c9", "estado": "usado", "contenido_id": "x123", "creado": "2026-01-01"}
    r = clustering.recalcular(base, [_item(fuente_id="a")])
    assert r["id"] == "c9"
    assert r["estado"] == "usado"
    assert r["contenido_id"] == "x123"
    assert r["creado"] == "2026-01-01"


# --------------------------------------------------------------------------- #
# Tracking de fuentes: fuentes_detalle / peso_corroboracion                     #
# --------------------------------------------------------------------------- #


def test_fuentes_detalle_deduplica_por_outlet_y_ordena_cronologico():
    items = [
        _item(fuente_id="b", fuente_nombre="Medio B", url="https://b.com/n1", fuente_peso=1.0,
              publicado_en=(_T0 + timedelta(minutes=30)).isoformat()),
        _item(fuente_id="a", fuente_nombre="Reuters", url="https://reuters.com/n1", fuente_peso=2.0,
              publicado_en=_T0.isoformat()),
        # Segundo enlace del MISMO outlet (host reuters.com): no es una fuente nueva.
        _item(fuente_id="a", fuente_nombre="Reuters", url="https://reuters.com/n2", fuente_peso=2.0,
              publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
    ]
    detalle = clustering.fuentes_detalle(items)
    assert [d["fuente"] for d in detalle] == ["Reuters", "Medio B"]  # cronológico: quién abrió
    assert detalle[0]["primer_visto"] == _T0.isoformat()
    assert detalle[0]["n_items"] == 2  # dos artículos del mismo outlet
    assert detalle[0]["peso"] == 2.0
    assert clustering.peso_corroboracion(detalle) == 3.0  # 2.0 + 1.0


def test_fuentes_detalle_sin_url_cae_a_fuente_id():
    items = [
        _item(fuente_id="cajon-portal", fuente_nombre="portal", url="", fuente_peso=1.0),
        _item(fuente_id="cajon-portal", fuente_nombre="portal", url="", fuente_peso=1.0),
    ]
    detalle = clustering.fuentes_detalle(items)
    assert len(detalle) == 1
    assert detalle[0]["fuente_id"] == "cajon-portal"
    assert detalle[0]["n_items"] == 2


def test_recalcular_persiste_timeline_y_peso_de_fuentes():
    items = [
        _item(fuente_id="b", fuente_nombre="Medio B", url="https://b.com/n1", fuente_peso=1.0,
              publicado_en=(_T0 + timedelta(minutes=20)).isoformat()),
        _item(fuente_id="a", fuente_nombre="Reuters", url="https://reuters.com/n1", fuente_peso=2.0,
              publicado_en=_T0.isoformat()),
    ]
    r = clustering.recalcular(_base_cluster(), items)
    assert r["peso_fuentes"] == 3.0
    assert r["primera_fuente"] == "a"
    assert r["primera_fuente_nombre"] == "Reuters"
    assert [d["fuente"] for d in r["fuentes_detalle"]] == ["Reuters", "Medio B"]


def test_recalcular_sin_items_deja_tracking_vacio():
    r = clustering.recalcular(_base_cluster(), [])
    assert r["fuentes_detalle"] == []
    assert r["peso_fuentes"] == 0.0
    assert r["primera_fuente"] == ""
    assert r["primera_fuente_nombre"] == ""


# --------------------------------------------------------------------------- #
# Dedup por EVENTO: titulares reordenados (token-sort)                          #
# --------------------------------------------------------------------------- #


def test_asignar_une_titulares_reordenados_mismo_evento():
    """El mismo evento con la sintaxis cambiada (mismas palabras, otro orden) se une."""
    cluster = {"id": "c1", "clave": "url:medio-a.com/n1",
               "titulo": "América vence a Chivas en el clásico nacional"}
    item = _item(url="https://medio-b.com/otra-nota",
                 titulo="En el clásico nacional, América vence a Chivas")
    assert clustering.asignar(item, [cluster]) == "c1"


def test_asignador_une_titulares_reordenados_como_asignar():
    """El índice incremental (`Asignador`) toma la MISMA decisión que `asignar` (paridad)."""
    cluster = {"id": "c1", "clave": "url:medio-a.com/n1",
               "titulo": "América vence a Chivas en el clásico nacional"}
    item = _item(url="https://medio-b.com/otra-nota",
                 titulo="En el clásico nacional, América vence a Chivas")
    asignador = clustering.Asignador([cluster])
    assert asignador.asignar(item) == "c1"


def test_asignar_no_une_eventos_distintos_con_palabras_comunes():
    """Compartir un par de tokens NO basta: eventos distintos siguen separados."""
    cluster = {"id": "c1", "clave": "url:medio-a.com/n1",
               "titulo": "América vence a Chivas en el clásico nacional"}
    item = _item(url="https://medio-b.com/x",
                 titulo="Cruz Azul golea a Pumas en el estadio olímpico")
    assert clustering.asignar(item, [cluster]) is None


def test_seleccionar_diversos_salta_macro_tema_reordenado():
    """La diversidad de la promoción también detecta el macro-tema con el titular reordenado."""
    clusters = [
        {"id": "a", "titulo": "América vence a Chivas en el clásico nacional", "score": 0.9},
        {"id": "b", "titulo": "En el clásico nacional América vence a Chivas", "score": 0.8},
        {"id": "c", "titulo": "Sismo de magnitud sacude la capital del país", "score": 0.5},
    ]
    elegidos = clustering.seleccionar_diversos(clusters, maximo=2, umbral=0.80)
    assert [c["id"] for c in elegidos] == ["a", "c"]


# --------------------------------------------------------------------------- #
# puntuar (fórmula + monotonía)                                                 #
# --------------------------------------------------------------------------- #


def _cluster(**campos):
    base = {"n_fuentes": 1, "senal": 0, "ultimo_visto": _T0.isoformat(), "breaking": 0, "titulo": "x"}
    base.update(campos)
    return base


def test_puntuar_en_rango_0_1():
    s, razon = clustering.puntuar(_cluster(n_fuentes=6, senal=1_000_000, breaking=1), ahora=_T0)
    assert 0.0 <= s <= 1.0
    assert isinstance(razon, str) and razon


def test_puntuar_monotono_en_corroboracion():
    ahora = _T0 + timedelta(hours=1)
    lo = clustering.puntuar(_cluster(n_fuentes=1), ahora=ahora)[0]
    hi = clustering.puntuar(_cluster(n_fuentes=6), ahora=ahora)[0]
    assert hi > lo


def test_puntuar_monotono_en_frescura():
    ahora = _T0 + timedelta(hours=1)
    fresca = clustering.puntuar(_cluster(ultimo_visto=ahora.isoformat()), ahora=ahora)[0]
    vieja = clustering.puntuar(
        _cluster(ultimo_visto=(ahora - timedelta(hours=60)).isoformat()), ahora=ahora
    )[0]
    assert fresca > vieja


def test_puntuar_monotono_en_viralidad():
    s_baja = clustering.puntuar(_cluster(senal=10), ahora=_T0)[0]
    s_alta = clustering.puntuar(_cluster(senal=500_000), ahora=_T0)[0]
    assert s_alta > s_baja


def test_puntuar_breaking_sin_bonus_por_defecto():
    # Breaking ya NO es un empujón aditivo (emerge de corroboración ponderada × velocidad):
    # con los pesos por defecto el flag solo no cambia el score…
    sin = clustering.puntuar(_cluster(n_fuentes=3, breaking=0), ahora=_T0)[0]
    con = clustering.puntuar(_cluster(n_fuentes=3, breaking=1), ahora=_T0)[0]
    assert con == sin
    # …pero el knob de rollback sigue funcionando si config lo reactiva.
    pesos = clustering.PesosScore(breaking=0.10)
    con_bonus = clustering.puntuar(_cluster(n_fuentes=3, breaking=1), ahora=_T0, pesos=pesos)[0]
    assert con_bonus > sin


def _detalle(*entradas):
    """Atajo: timeline de outlets como lo persiste `recalcular` (peso + primer_visto)."""
    return [
        {"fuente_id": f"f{i}", "fuente": f"Fuente {i}", "host": f"f{i}.com",
         "peso": peso, "primer_visto": visto.isoformat(), "n_items": 1}
        for i, (peso, visto) in enumerate(entradas)
    ]


def test_puntuar_dos_potentes_simultaneas_rankean_top_y_breaking():
    # 2 fuentes potentes a la vez → corroboración 0.67 + velocidad 1.0 + frescura ≈ score 0.6+
    # y flag breaking EN VIVO: tiene que salir al top del pool y al feed (vía listón).
    cl = _cluster(
        n_fuentes=2, peso_fuentes=4.0, ultimo_visto=_T0.isoformat(),
        fuentes_detalle=_detalle((2.0, _T0 - timedelta(minutes=20)), (2.0, _T0 - timedelta(minutes=5))),
    )
    score, _razon, desglose = clustering.puntuar_detalle(cl, ahora=_T0)
    assert score >= 0.55
    assert desglose["breaking"] == 1
    assert desglose["velocidad"] == 1.0
    assert desglose["peso_fuentes"] == 4.0


def test_puntuar_velocidad_decae_al_envejecer():
    detalle = _detalle((2.0, _T0), (2.0, _T0 + timedelta(minutes=15)))
    cl = _cluster(n_fuentes=2, peso_fuentes=4.0, ultimo_visto=(_T0 + timedelta(minutes=15)).isoformat(),
                  fuentes_detalle=detalle)
    fresca = clustering.puntuar_detalle(cl, ahora=_T0 + timedelta(minutes=20))
    vieja = clustering.puntuar_detalle(cl, ahora=_T0 + timedelta(hours=12))
    assert fresca[2]["velocidad"] == 1.0
    assert vieja[2]["velocidad"] == 0.0
    assert fresca[2]["breaking"] == 1
    assert vieja[2]["breaking"] == 0  # el breaking decae con la ventana
    assert fresca[0] > vieja[0]


def test_puntuar_corroboracion_pondera_el_peso_no_solo_el_conteo():
    # 2 potentes (masa 4.0) corroboran MÁS que 3 normales (masa 3.0).
    dos_potentes = _cluster(n_fuentes=2, peso_fuentes=4.0)
    tres_normales = _cluster(n_fuentes=3, peso_fuentes=3.0)
    s2 = clustering.puntuar_detalle(dos_potentes, ahora=_T0)[2]["corroboracion"]
    s3 = clustering.puntuar_detalle(tres_normales, ahora=_T0)[2]["corroboracion"]
    assert s2 > s3


def test_puntuar_unica_fuente_fresca_queda_bajo_el_liston():
    # Una sola fuente recién llegada, sin encaje de marca, NO debe abrir el listón (0.35).
    sola = _cluster(n_fuentes=1, peso_fuentes=1.0, senal=0, ultimo_visto=_T0.isoformat())
    score = clustering.puntuar(sola, ahora=_T0)[0]
    assert score < clustering.LISTON_MIN_SCORE_DEF


def test_puntuar_fallback_a_n_fuentes_sin_peso_persistido():
    # Cluster pre-migración (peso_fuentes=0): la masa cae al conteo de fuentes — el pool
    # vivo no colapsa a 0 en el primer arranque.
    viejo = _cluster(n_fuentes=4, peso_fuentes=0.0)
    nuevo = _cluster(n_fuentes=4, peso_fuentes=4.0)
    assert (
        clustering.puntuar_detalle(viejo, ahora=_T0)[2]["corroboracion"]
        == clustering.puntuar_detalle(nuevo, ahora=_T0)[2]["corroboracion"]
    )


def test_puntuar_relevancia_de_marca_sube_el_score():
    pal = frozenset({"reforma"})
    sin = clustering.puntuar(_cluster(titulo="Noticia cualquiera"), ahora=_T0)[0]
    con = clustering.puntuar(_cluster(titulo="Aprueban la reforma hoy"), palabras_marca=pal, ahora=_T0)[0]
    assert con > sin


def test_puntuar_pesos_inyectados_cambian_el_score():
    """Pesos inyectados (PesosScore) reemplazan los defaults: el ranking es configurable."""
    cl = _cluster(n_fuentes=6, senal=0, breaking=0, ultimo_visto=_T0.isoformat())
    solo_corro = clustering.PesosScore(
        corroboracion=1.0, frescura=0.0, viralidad=0.0, marca=0.0, breaking=0.0
    )
    todo_cero = clustering.PesosScore(
        corroboracion=0.0, frescura=0.0, viralidad=0.0, marca=0.0, breaking=0.0
    )
    assert clustering.puntuar(cl, ahora=_T0, pesos=solo_corro)[0] > 0.0
    assert clustering.puntuar(cl, ahora=_T0, pesos=todo_cero)[0] == 0.0


def test_puntuar_senal_rendimiento_inerte_sin_peso():
    """La señal de rendimiento (Fase 2c) NO afecta con el peso por defecto (0): no rompe nada."""
    base = _cluster(n_fuentes=2, ultimo_visto=_T0.isoformat())
    con_bonus = {**base, "bonus_rendimiento": 1.0}
    assert clustering.puntuar(base, ahora=_T0)[0] == clustering.puntuar(con_bonus, ahora=_T0)[0]


def test_puntuar_senal_rendimiento_con_peso_sube_el_score():
    """Con peso > 0, una historia en una línea top (bonus 1.0) puntúa más que una sin bonus."""
    base = _cluster(n_fuentes=2, ultimo_visto=_T0.isoformat())
    pesos = clustering.PesosScore(rendimiento=0.2)
    sin = clustering.puntuar(base, ahora=_T0, pesos=pesos)[0]
    con = clustering.puntuar({**base, "bonus_rendimiento": 1.0}, ahora=_T0, pesos=pesos)[0]
    assert con > sin


# --------------------------------------------------------------------------- #
# puntuar_detalle: la explicación estructurada del score                        #
# --------------------------------------------------------------------------- #


def test_puntuar_detalle_desglosa_las_senales_y_las_palabras():
    pal = frozenset({"sismo", "cdmx"})
    cl = _cluster(
        n_fuentes=3, senal=1000, breaking=1,
        titulo="Sismo de 6.1 sacude la CDMX", ultimo_visto=_T0.isoformat(),
    )
    score, razon, desglose = clustering.puntuar_detalle(cl, palabras_marca=pal, ahora=_T0)
    assert clustering.puntuar(cl, palabras_marca=pal, ahora=_T0) == (score, razon)  # wrapper fiel
    assert set(desglose) == {
        "corroboracion", "velocidad", "frescura", "viralidad", "marca", "rendimiento",
        "peso_fuentes", "breaking", "palabras",
    }
    for senal in ("corroboracion", "velocidad", "frescura", "viralidad", "marca", "rendimiento"):
        assert 0.0 <= desglose[senal] <= 1.0
    assert desglose["breaking"] == 1  # sin timeline persistido se respeta el flag
    assert desglose["palabras"] == ["cdmx", "sismo"]  # qué del vocabulario casó (explicable)
    assert "cdmx" in razon  # la razón humana nombra las palabras que casaron


def test_relevancia_marca_casa_tambien_la_traduccion():
    """Una historia extranjera TRADUCIDA evalúa la relevancia también sobre titulo_es/resumen_es."""
    pal = frozenset({"sismo", "cdmx"})
    extranjera = {
        "titulo": "Earthquake shakes Mexico City this morning",
        "resumen": "",
        "titulo_es": "Un sismo sacude la CDMX esta mañana",
        "resumen_es": "",
    }
    s, casadas = clustering.relevancia_marca_detalle(extranjera, pal)
    assert s > 0.0
    assert casadas == ("cdmx", "sismo")
    # Sin traducción, el titular EN no casa el vocabulario ES (comportamiento previo).
    sin_trad = {"titulo": "Earthquake shakes Mexico City this morning", "resumen": ""}
    assert clustering.relevancia_marca_detalle(sin_trad, pal)[0] == 0.0


def test_puntuar_detalle_casa_vocabulario_pese_a_la_puntuacion():
    """La tokenización separa por no-alfanuméricos: 'México:' casa el término 'mexico'."""
    pal = frozenset({"mexico"})
    _s, _r, desglose = clustering.puntuar_detalle(
        _cluster(titulo="México: arranca la jornada", ultimo_visto=_T0.isoformat()),
        palabras_marca=pal, ahora=_T0,
    )
    assert desglose["palabras"] == ["mexico"]


# --------------------------------------------------------------------------- #
# evaluar_liston: el listón de producción automática                            #
# --------------------------------------------------------------------------- #


def _cluster_apto(**campos):
    """Cluster que SUPERA el listón por defecto: fresco, corroborado y con encaje de marca."""
    base = _cluster(
        n_fuentes=3, senal=100, ultimo_visto=_T0.isoformat(),
        titulo="Sismo sacude la CDMX esta mañana", verificacion="corroborada",
    )
    base.update(campos)
    return base


_PAL = frozenset({"sismo", "cdmx", "mexico"})


def test_liston_supera_con_motivo_explicable():
    ok, motivo = clustering.evaluar_liston(_cluster_apto(), palabras_marca=_PAL, ahora=_T0)
    assert ok
    assert "sismo" in motivo  # el motivo nombra las palabras que casaron


def test_liston_rechaza_verificacion_dudosa():
    ok, motivo = clustering.evaluar_liston(
        _cluster_apto(verificacion="dudosa"), palabras_marca=_PAL, ahora=_T0
    )
    assert not ok
    assert "dudosa" in motivo


def test_liston_rechaza_score_bajo():
    vieja_sin_senales = _cluster_apto(
        n_fuentes=1, senal=0, ultimo_visto=(_T0 - timedelta(hours=70)).isoformat()
    )
    ok, motivo = clustering.evaluar_liston(vieja_sin_senales, palabras_marca=_PAL, ahora=_T0)
    assert not ok
    assert "score" in motivo


def test_liston_recalcula_el_score_no_usa_el_persistido():
    """Un score persistido alto NO cuela: el listón evalúa las señales DE AHORA (envejece)."""
    vieja = _cluster_apto(
        score=0.95, n_fuentes=1, senal=0,
        ultimo_visto=(_T0 - timedelta(hours=70)).isoformat(),
    )
    ok, _motivo = clustering.evaluar_liston(vieja, palabras_marca=_PAL, ahora=_T0)
    assert not ok


def test_liston_rechaza_sin_encaje_de_marca():
    ok, motivo = clustering.evaluar_liston(
        _cluster_apto(titulo="Celebrity gossip news today"), palabras_marca=_PAL, ahora=_T0
    )
    assert not ok
    assert "marca" in motivo


def test_liston_madura_antes_de_promover():
    """Con maduración, una historia recién vista NO se promueve aún (motivo explicable)."""
    recien = _cluster_apto(primer_visto=(_T0 - timedelta(minutes=10)).isoformat())
    ok, motivo = clustering.evaluar_liston(
        recien, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert not ok
    assert "madurando" in motivo


def test_liston_madurada_se_promueve():
    madura = _cluster_apto(primer_visto=(_T0 - timedelta(minutes=50)).isoformat())
    ok, _motivo = clustering.evaluar_liston(
        madura, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok


def test_liston_maduracion_exime_breaking_corroborada_y_curadas():
    from keni_consola.dominio.ingesta import SENAL_CURADO

    breaking = _cluster_apto(breaking=1, primer_visto=(_T0 - timedelta(minutes=1)).isoformat())
    ok, _m = clustering.evaluar_liston(
        breaking, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok  # la urgencia real no espera
    curada = _cluster_apto(
        senal=SENAL_CURADO, primer_visto=(_T0 - timedelta(minutes=1)).isoformat()
    )
    ok, _m = clustering.evaluar_liston(
        curada, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok  # el humano ya decidió


def test_liston_maduracion_sin_primer_visto_no_retiene():
    """Un dato ausente no castiga: sin `primer_visto` parseable la regla no aplica."""
    ok, _m = clustering.evaluar_liston(
        _cluster_apto(), palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok


def test_liston_exime_de_marca_a_lo_curado_por_el_equipo():
    from keni_consola.dominio.ingesta import SENAL_CURADO

    curada = _cluster_apto(titulo="Apunte del equipo sin vocabulario", senal=SENAL_CURADO)
    ok, _motivo = clustering.evaluar_liston(curada, palabras_marca=_PAL, ahora=_T0)
    assert ok  # el humano ya decidió: no se le exige vocabulario


def test_liston_exime_de_marca_a_breaking_corroborada():
    breaking = _cluster_apto(titulo="Evento inesperado sin vocabulario aun", breaking=1)
    ok, _motivo = clustering.evaluar_liston(breaking, palabras_marca=_PAL, ahora=_T0)
    assert ok  # evento mayor confirmado por varias fuentes a la vez


def test_liston_dos_potentes_recien_nacida_sale_sin_madurar():
    # El caso de diseño: una nota en 2 fuentes potentes A LA VEZ sube al top y sale al feed
    # sin esperar maduración ni encaje de marca (breaking derivado EN VIVO del timeline).
    detalle = [
        {"fuente_id": "a", "fuente": "Reuters", "host": "reuters.com", "peso": 2.0,
         "primer_visto": (_T0 - timedelta(minutes=20)).isoformat(), "n_items": 1},
        {"fuente_id": "b", "fuente": "BBC", "host": "bbc.com", "peso": 2.0,
         "primer_visto": (_T0 - timedelta(minutes=5)).isoformat(), "n_items": 1},
    ]
    cl = _cluster(
        n_fuentes=2, peso_fuentes=4.0, fuentes_detalle=detalle, verificacion="corroborada",
        titulo="Evento inesperado sin vocabulario", ultimo_visto=_T0.isoformat(),
        primer_visto=(_T0 - timedelta(minutes=2)).isoformat(),
        breaking=0,  # flag persistido desfasado: el listón deriva el vivo del timeline
    )
    ok, motivo = clustering.evaluar_liston(
        cl, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok
    assert "score" in motivo


def test_liston_breaking_sin_corroborar_no_queda_exenta():
    breaking_unica = _cluster_apto(
        titulo="Evento inesperado sin vocabulario", breaking=1, verificacion="unica_fuente"
    )
    ok, _motivo = clustering.evaluar_liston(breaking_unica, palabras_marca=_PAL, ahora=_T0)
    assert not ok


def test_liston_umbral_cero_desactiva_cada_regla():
    sin_encaje = _cluster_apto(titulo="Celebrity gossip news today")
    ok, _ = clustering.evaluar_liston(
        sin_encaje, palabras_marca=_PAL, min_marca=0.0, ahora=_T0
    )
    assert ok  # min_marca=0 apaga el listón de marca (el de score se mantiene)


# --------------------------------------------------------------------------- #
# Auto-verificación por corroboración (Ola D)                                  #
# --------------------------------------------------------------------------- #


def test_verificacion_corroborada_con_dos_outlets_distintos():
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n"),
        _item(fuente_id="b", url="https://medio-b.com/n"),
    ]
    assert clustering.clasificar_verificacion(items) == "corroborada"


def test_verificacion_dos_enlaces_del_mismo_outlet_no_corrobora():
    # Dos urls del MISMO host = una sola fuente real (no corroboración).
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n1"),
        _item(fuente_id="a2", url="https://medio-a.com/n2"),
    ]
    assert clustering.clasificar_verificacion(items) == "unica_fuente"


def test_verificacion_unica_fuente_fiable():
    items = [_item(fuente_id="a", url="https://medio-serio.com/n")]
    assert clustering.clasificar_verificacion(items) == "unica_fuente"


def test_verificacion_dudosa_si_unica_fuente_es_de_baja_confianza():
    baja = frozenset({"reddit.com"})
    items = [_item(fuente_id="r", url="https://reddit.com/r/x/post", fuente_nombre="Reddit")]
    assert clustering.clasificar_verificacion(items, fuentes_baja=baja) == "dudosa"


def test_verificacion_dudosa_por_clickbait():
    items = [_item(fuente_id="a", url="https://medio.com/n", titulo="No vas a creer lo que pasó")]
    assert clustering.clasificar_verificacion(items) == "dudosa"


def test_verificacion_corroborada_gana_a_baja_confianza():
    # Aunque una sea de baja confianza, dos outlets distintos = corroborada.
    baja = frozenset({"reddit.com"})
    items = [
        _item(fuente_id="r", url="https://reddit.com/r/x/post"),
        _item(fuente_id="b", url="https://medio-serio.com/n"),
    ]
    assert clustering.clasificar_verificacion(items, fuentes_baja=baja) == "corroborada"


def test_recalcular_fija_verificacion_e_idioma_representativo():
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n", idioma="en", titulo="Foreign headline here"),
        _item(fuente_id="b", url="https://medio-b.com/n", idioma="en", titulo="Foreign headline here"),
    ]
    rec = clustering.recalcular({"id": "c1"}, items)
    assert rec["verificacion"] == "corroborada"
    # idioma del representativo (no hay 'es' -> el de mayor señal/título): inglés.
    assert rec["idioma"] == "en"
    assert "en" in rec["idiomas"]


# --------------------------------------------------------------------------- #
# Asignación determinista + Asignador (índice con blocking)                     #
# --------------------------------------------------------------------------- #


def test_asignar_empate_exacto_gana_el_primero():
    """A empate EXACTO de ratio gana el primer candidato (antes ganaba el último: no determinista)."""
    c_a = {"id": "primero", "clave": "t:1", "titulo": "El presidente anuncia nueva reforma"}
    c_b = {"id": "segundo", "clave": "t:2", "titulo": "El presidente anuncia nueva reforma"}
    item = _item(url="", titulo="El presidente anuncia nueva reforma")
    assert clustering.asignar(item, [c_a, c_b], umbral=0.8) == "primero"
    # Invertir el orden invierte el ganador (decide el orden de entrada, no el azar del dict).
    assert clustering.asignar(item, [c_b, c_a], umbral=0.8) == "segundo"


def test_asignador_replica_las_decisiones_de_asignar():
    clusters = [
        {"id": "u1", "clave": "url:example.com/nota-1", "titulo": "Titular original"},
        {"id": "f1", "clave": "t:abc", "titulo": "El presidente anuncia una nueva reforma para los estados"},
    ]
    asignador = clustering.Asignador(clusters, umbral=0.82)
    # (a) cruce exacto por url canónica.
    por_url = _item(url="https://example.com/nota-1?utm_source=tw", titulo="Algo distinto")
    assert asignador.asignar(por_url) == "u1" == clustering.asignar(por_url, clusters)
    # (b) fuzzy de título.
    por_titulo = _item(url="", titulo="El presidente anuncia nueva reforma para los estados")
    assert asignador.asignar(por_titulo) == "f1" == clustering.asignar(por_titulo, clusters, umbral=0.82)
    # (c) nada casa -> None (cluster nuevo).
    nuevo = _item(url="", titulo="Resultados de la jornada de fútbol del domingo")
    assert asignador.asignar(nuevo) is None
    assert clustering.asignar(nuevo, clusters, umbral=0.82) is None


def test_asignador_agregar_une_items_del_mismo_barrido():
    asignador = clustering.Asignador([], umbral=0.82)
    asignador.agregar({"id": "n1", "clave": "t:x", "titulo": "Gran final del torneo de verano"})
    assert asignador.asignar(_item(url="", titulo="Gran final del torneo de verano hoy")) == "n1"


def test_asignador_titulos_cortos_no_entran_fuzzy():
    asignador = clustering.Asignador([{"id": "c", "clave": "t:nfl", "titulo": "NFL"}], umbral=0.3)
    assert asignador.asignar(_item(url="", titulo="F1")) is None


# --------------------------------------------------------------------------- #
# Relevancia de marca GRADUADA (saturación suave + límite de palabra)           #
# --------------------------------------------------------------------------- #


def test_relevancia_marca_gradua_por_numero_de_coincidencias():
    pal = frozenset({"futbol", "gol", "liga mx"})
    una = clustering._relevancia_marca({"titulo": "El futbol de hoy", "resumen": ""}, pal)
    tres = clustering._relevancia_marca({"titulo": "Futbol: gol en la liga mx", "resumen": ""}, pal)
    assert 0.0 < una < tres <= 1.0  # 1 keyword ya NO puntúa igual que 3 (escalón eliminado)


def test_relevancia_marca_resumen_pesa_menos_que_titulo():
    pal = frozenset({"reforma"})
    en_titulo = clustering._relevancia_marca({"titulo": "Aprueban la reforma", "resumen": ""}, pal)
    en_resumen = clustering._relevancia_marca({"titulo": "Noticia del día", "resumen": "sobre la reforma"}, pal)
    assert en_titulo > en_resumen > 0.0


def test_relevancia_marca_frases_casan_por_limite_de_palabra():
    pal = frozenset({"box office"})
    assert clustering._relevancia_marca({"titulo": "box office records", "resumen": ""}, pal) > 0.0
    assert clustering._relevancia_marca({"titulo": "boxofficemania total", "resumen": ""}, pal) == 0.0


def test_puntuar_sigue_monotono_en_relevancia_graduada():
    pal = frozenset({"futbol", "gol"})
    poco = clustering.puntuar(_cluster(titulo="El futbol de hoy"), palabras_marca=pal, ahora=_T0)[0]
    mucho = clustering.puntuar(_cluster(titulo="Futbol con gol agónico"), palabras_marca=pal, ahora=_T0)[0]
    assert mucho > poco > clustering.puntuar(_cluster(titulo="Nada relacionado"), palabras_marca=pal, ahora=_T0)[0]


# --------------------------------------------------------------------------- #
# Marca por vocabulario (historias solo-Trends/agencias, sin marca dominante)   #
# --------------------------------------------------------------------------- #


def test_marca_por_vocabulario_elige_la_mejor_sobre_el_umbral():
    voc = {
        "claro-sports": frozenset({"futbol", "gol"}),
        "unotv": frozenset({"sismo", "cdmx"}),
    }
    cluster = {"titulo": "Futbol: gol de último minuto", "resumen": ""}
    assert clustering.marca_por_vocabulario(cluster, voc) == "claro-sports"


def test_marca_por_vocabulario_sin_encaje_queda_vacia():
    voc = {"claro-sports": frozenset({"futbol"}), "unotv": frozenset({"sismo"})}
    assert clustering.marca_por_vocabulario({"titulo": "Tema sin encaje alguno", "resumen": ""}, voc) == ""
    # Coincidencia SOLO de resumen (0.2) no alcanza el umbral por defecto (0.3).
    solo_resumen = {"titulo": "Tema neutro", "resumen": "se habló de futbol"}
    assert clustering.marca_por_vocabulario(solo_resumen, voc) == ""


def test_marca_por_vocabulario_empate_determinista():
    voc = {"b-marca": frozenset({"futbol"}), "a-marca": frozenset({"futbol"})}
    assert clustering.marca_por_vocabulario({"titulo": "El futbol manda", "resumen": ""}, voc) == "a-marca"


# --------------------------------------------------------------------------- #
# Insumos CURADOS: no secuestran el titular ni saturan la viralidad             #
# --------------------------------------------------------------------------- #


def test_representativo_prefiere_titular_periodistico_sobre_curado():
    items = [
        _item(fuente_id="cajon-ideas", titulo="nota curada del equipo", senal=1_000_000),
        _item(fuente_id="rss1", titulo="Titular periodístico real de la noticia", senal=500),
    ]
    r = clustering.recalcular(_base_cluster(), items)
    assert r["titulo"] == "Titular periodístico real de la noticia"
    # La señal artificial del curado NO satura la viralidad de la historia mixta.
    assert r["senal"] == 500


def test_cluster_solo_curado_conserva_su_senal_y_titulo():
    items = [_item(fuente_id="cajon-ideas", titulo="nota curada del equipo", senal=1_000_000)]
    r = clustering.recalcular(_base_cluster(), items)
    assert r["titulo"] == "nota curada del equipo"
    assert r["senal"] == 1_000_000  # el auto-feed de curados sigue funcionando


# --------------------------------------------------------------------------- #
# seleccionar_diversos (MMR suave para la promoción CI)                         #
# --------------------------------------------------------------------------- #


def _c_div(cid, titulo):
    return {"id": cid, "titulo": titulo}


def test_seleccionar_diversos_salta_titulos_casi_identicos():
    clusters = [
        _c_div("a", "Messi gana el premio en París"),
        _c_div("b", "Messi gana el premio en París hoy"),  # casi idéntico al primero
        _c_div("c", "Sismo de magnitud en la capital"),
    ]
    out = clustering.seleccionar_diversos(clusters, maximo=2, umbral=0.8)
    assert [c["id"] for c in out] == ["a", "c"]  # el macro-tema no se come las dos plazas


def test_seleccionar_diversos_es_suave_rellena_si_faltan():
    clusters = [
        _c_div("a", "Messi gana el premio en París"),
        _c_div("b", "Messi gana el premio en París hoy"),
    ]
    out = clustering.seleccionar_diversos(clusters, maximo=2, umbral=0.8)
    assert [c["id"] for c in out] == ["a", "b"]  # nunca devuelve menos por diversificar


def test_seleccionar_diversos_umbral_cero_es_top_n_puro():
    clusters = [_c_div("a", "Mismo título repetido"), _c_div("b", "Mismo título repetido")]
    assert [c["id"] for c in clustering.seleccionar_diversos(clusters, maximo=2, umbral=0.0)] == ["a", "b"]

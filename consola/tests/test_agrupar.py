"""Tests PUROS (sin DB ni red) del dominio de agrupar de historias (`dominio.agrupar`).

Cubre la identidad de cluster (`clave_cluster`: url canónica sin query vs hash de título), la
asignación incremental (`asignar`: DEDUP EXACTO — misma url canónica o título normalizado
idéntico; sin léxico fuzzy, que ahora resuelve la fusión semántica con Haiku), el recálculo de
agregados (`recalcular`: n_items/n_fuentes/idiomas/señal/representativo/
breaking) y el scoring (`puntuar`: fórmula documentada + monotonía por señal). Todo determinista,
con `ahora` inyectado: nunca se toca el reloj real, la BD ni la red.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from keni_consola.dominio import agrupar

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
    a = agrupar.clave_cluster(_item(url="https://www.example.com/nota-1?utm_source=x&ref=y"))
    b = agrupar.clave_cluster(_item(url="https://example.com/nota-1?pagina=2"))
    assert a == "url:example.com/nota-1"
    assert a == b  # misma nota, distinta query → misma clave


def test_clave_por_titulo_si_no_hay_url():
    k = agrupar.clave_cluster(_item(url="", titulo="¡Selección Mexicana golea!"))
    assert k.startswith("t:")
    # Título equivalente (sin signos) colisiona.
    assert k == agrupar.clave_cluster(_item(url="", titulo="seleccion mexicana golea"))


def test_clave_vacia_sin_url_ni_titulo():
    assert agrupar.clave_cluster({"url": "", "titulo": ""}) == ""


# --------------------------------------------------------------------------- #
# asignar — DEDUP EXACTO (sin léxico): solo url canónica o título idéntico       #
# --------------------------------------------------------------------------- #


def test_asignar_une_por_misma_url():
    # (a) Misma url canónica (host+path), distinta query/título → mismo cluster.
    item = _item(url="https://example.com/nota-1?utm_source=tw", titulo="Algo distinto")
    cluster = {"id": "c1", "clave": "url:example.com/nota-1", "titulo": "Titular original"}
    assert agrupar.asignar(item, [cluster]) == "c1"
    # El Asignador (índice) toma la misma decisión.
    assert agrupar.Asignador([cluster]).asignar(item) == "c1"


def test_asignar_une_por_titulo_identico_sin_url():
    # (b) Sin url, título normalizado IDÉNTICO (mismo `t:<hash>`) → mismo cluster.
    titulo = "¡Selección Mexicana golea!"
    clave = agrupar.clave_cluster(_item(url="", titulo=titulo))
    assert clave.startswith("t:")
    cluster = {"id": "c2", "clave": clave, "titulo": titulo}
    # Variante equivalente (sin signos / mayúsculas) colisiona por su hash.
    item = _item(url="", titulo="seleccion mexicana golea")
    assert agrupar.asignar(item, [cluster]) == "c2"
    assert agrupar.Asignador([cluster]).asignar(item) == "c2"


def test_asignar_cluster_nuevo_si_nada_casa():
    cluster = {"id": "c2", "clave": "t:abc", "titulo": "Reforma energética en el senado"}
    item = _item(url="", titulo="Resultados de la jornada de fútbol del domingo")
    assert agrupar.asignar(item, [cluster]) is None


def test_asignar_titulo_no_identico_no_une():
    # El léxico (fuzzy) ya NO une: dos titulares parecidos pero NO idénticos forman clusters
    # distintos; la fusión semántica (Haiku) los agrupará después.
    cluster = {
        "id": "c2",
        "clave": agrupar.clave_cluster(_item(url="", titulo="El presidente anuncia una nueva reforma para los estados")),
        "titulo": "El presidente anuncia una nueva reforma para los estados",
    }
    item = _item(url="", titulo="El presidente anuncia nueva reforma para los estados")
    assert agrupar.asignar(item, [cluster]) is None


def test_asignar_sin_clave_estable_devuelve_none():
    cluster = {"id": "c1", "clave": "t:abc", "titulo": "Algo"}
    assert agrupar.asignar({"url": "", "titulo": ""}, [cluster]) is None


def test_asignar_shrek_titulares_distintos_forman_singletons():
    """Tres titulares REALES del mismo evento (trailer de Shrek 5), sin url compartida y con
    títulos NO idénticos: el dedup exacto NO los une (cada uno es un singleton). Documenta que la
    agrupación del mismo evento recae ahora en la fusión semántica (Haiku), no en el léxico."""
    titulares = [
        "SHREK 5 Trailer Features Gingerbread Twerking and a Back Alley Snowman",
        "Shrek And Donkey Look Too Lifelike In New Shrek 5 Trailer",
        "DreamWorks Drops First Trailer For 'Shrek 5,' Coming Next Summer",
    ]
    clusters = [
        {"id": f"c{i}", "clave": agrupar.clave_cluster(_item(url="", titulo=t)), "titulo": t}
        for i, t in enumerate(titulares)
    ]
    # Cada item, contra el índice de los OTROS dos, no casa con ninguno (3 singletons).
    for i, t in enumerate(titulares):
        item = _item(url="", titulo=t, marca="unotv")
        otros = [c for j, c in enumerate(clusters) if j != i]
        assert agrupar.asignar(item, otros) is None
        assert agrupar.Asignador(otros).asignar(item) is None


def test_numeros_incompatibles_helper_sigue_disponible():
    # `_numeros_incompatibles` sobrevive como helper del scoring (selección diversa); un lado sin
    # números NO dispara el veto.
    assert not agrupar._numeros_incompatibles(
        agrupar.similitud.clave_fuzzy("Sismo sacude Guerrero esta tarde"),
        agrupar.similitud.clave_fuzzy("Sismo de magnitud 5.8 sacude Guerrero"),
    )
    # Mismas claves con cifras DISJUNTAS sí vetan.
    assert agrupar._numeros_incompatibles(
        agrupar.similitud.clave_fuzzy("Sismo de magnitud 5.8 sacude Guerrero hoy"),
        agrupar.similitud.clave_fuzzy("Sismo de magnitud 7.1 sacude Guerrero hoy"),
    )


# --------------------------------------------------------------------------- #
# recalcular                                                                    #
# --------------------------------------------------------------------------- #


def _base_cluster():
    return {"id": "c1", "estado": "nuevo", "publicacion_id": "", "creado": ""}


def test_recalcular_agrega_fuentes_idiomas_y_senal():
    items = [
        _item(fuente_id="a", idioma="es", senal=100, publicado_en=_T0.isoformat()),
        _item(fuente_id="b", idioma="en", senal=5000, publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
        _item(fuente_id="a", idioma="es", senal=10, publicado_en=(_T0 + timedelta(hours=2)).isoformat()),
    ]
    r = agrupar.recalcular(_base_cluster(), items)
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
    r = agrupar.recalcular(_base_cluster(), items)
    assert r["titulo"] == "Gran noticia en español hoy"


def test_recalcular_breaking_si_masa_de_fuentes_en_la_ventana_actual():
    # Tres outlets NORMALES (peso 1.0) sumados en la ventana actual: masa 3.0 >= 3.0.
    items = [
        _item(fuente_id="a", url="https://a.com/n", publicado_en=_T0.isoformat()),
        _item(fuente_id="b", url="https://b.com/n", publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
        _item(fuente_id="c", url="https://c.com/n", publicado_en=(_T0 + timedelta(hours=2)).isoformat()),
    ]
    r = agrupar.recalcular(
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
    r = agrupar.recalcular(
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
    r = agrupar.recalcular(
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
    r = agrupar.recalcular(
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
    r = agrupar.recalcular(
        _base_cluster(), items, breaking_peso=3.0, breaking_ventana_h=6,
        ahora=_T0 + timedelta(hours=30),
    )
    assert r["breaking"] == 0  # solo 1 outlet en la ventana actual


def test_recalcular_conserva_identidad_del_cluster():
    base = {"id": "c9", "estado": "usado", "publicacion_id": "x123", "creado": "2026-01-01"}
    r = agrupar.recalcular(base, [_item(fuente_id="a")])
    assert r["id"] == "c9"
    assert r["estado"] == "usado"
    assert r["publicacion_id"] == "x123"
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
    detalle = agrupar.fuentes_detalle(items)
    assert [d["fuente"] for d in detalle] == ["Reuters", "Medio B"]  # cronológico: quién abrió
    assert detalle[0]["primer_visto"] == _T0.isoformat()
    assert detalle[0]["n_items"] == 2  # dos artículos del mismo outlet
    assert detalle[0]["peso"] == 2.0
    assert agrupar.peso_corroboracion(detalle) == 3.0  # 2.0 + 1.0


def test_fuentes_detalle_sin_url_cae_a_fuente_id():
    items = [
        _item(fuente_id="cajon-portal", fuente_nombre="portal", url="", fuente_peso=1.0),
        _item(fuente_id="cajon-portal", fuente_nombre="portal", url="", fuente_peso=1.0),
    ]
    detalle = agrupar.fuentes_detalle(items)
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
    r = agrupar.recalcular(_base_cluster(), items)
    assert r["peso_fuentes"] == 3.0
    assert r["primera_fuente"] == "a"
    assert r["primera_fuente_nombre"] == "Reuters"
    assert [d["fuente"] for d in r["fuentes_detalle"]] == ["Reuters", "Medio B"]


def test_recalcular_sin_items_deja_tracking_vacio():
    r = agrupar.recalcular(_base_cluster(), [])
    assert r["fuentes_detalle"] == []
    assert r["peso_fuentes"] == 0.0
    assert r["primera_fuente"] == ""
    assert r["primera_fuente_nombre"] == ""


# --------------------------------------------------------------------------- #
# Titulares reordenados del MISMO evento: ya NO los une `asignar` (dedup exacto, #
# sin léxico). Los agrupa después la fusión semántica con Haiku.                 #
# --------------------------------------------------------------------------- #


def test_asignar_no_une_titulares_reordenados_distinta_url():
    """Mismo evento con la sintaxis cambiada (mismas palabras, otro orden) y URLs distintas:
    `asignar` (dedup exacto) NO los une —los fusiona Haiku—, ya no hay léxico fuzzy."""
    cluster = {"id": "c1", "clave": "url:medio-a.com/n1",
               "titulo": "América vence a Chivas en el clásico nacional"}
    item = _item(url="https://medio-b.com/otra-nota",
                 titulo="En el clásico nacional, América vence a Chivas")
    assert agrupar.asignar(item, [cluster]) is None


def test_asignador_paridad_titulares_reordenados():
    """El índice incremental (`Asignador`) toma la MISMA decisión que `asignar`: tampoco los une."""
    cluster = {"id": "c1", "clave": "url:medio-a.com/n1",
               "titulo": "América vence a Chivas en el clásico nacional"}
    item = _item(url="https://medio-b.com/otra-nota",
                 titulo="En el clásico nacional, América vence a Chivas")
    asignador = agrupar.Asignador([cluster])
    assert asignador.asignar(item) is None


def test_asignar_no_une_eventos_distintos_con_palabras_comunes():
    """Compartir un par de tokens NO basta: eventos distintos siguen separados."""
    cluster = {"id": "c1", "clave": "url:medio-a.com/n1",
               "titulo": "América vence a Chivas en el clásico nacional"}
    item = _item(url="https://medio-b.com/x",
                 titulo="Cruz Azul golea a Pumas en el estadio olímpico")
    assert agrupar.asignar(item, [cluster]) is None


def test_seleccionar_diversos_salta_macro_tema_reordenado():
    """La diversidad de la promoción también detecta el macro-tema con el titular reordenado."""
    clusters = [
        {"id": "a", "titulo": "América vence a Chivas en el clásico nacional", "score": 0.9},
        {"id": "b", "titulo": "En el clásico nacional América vence a Chivas", "score": 0.8},
        {"id": "c", "titulo": "Sismo de magnitud sacude la capital del país", "score": 0.5},
    ]
    elegidos = agrupar.seleccionar_diversos(clusters, maximo=2, umbral=0.80)
    assert [c["id"] for c in elegidos] == ["a", "c"]


# --------------------------------------------------------------------------- #
# puntuar (fórmula + monotonía)                                                 #
# --------------------------------------------------------------------------- #


def _cluster(**campos):
    base = {"n_fuentes": 1, "senal": 0, "ultimo_visto": _T0.isoformat(), "breaking": 0, "titulo": "x"}
    base.update(campos)
    return base


def test_puntuar_en_rango_0_1():
    s, razon = agrupar.puntuar(_cluster(n_fuentes=6, senal=1_000_000, breaking=1), ahora=_T0)
    assert 0.0 <= s <= 1.0
    assert isinstance(razon, str) and razon


def test_puntuar_monotono_en_corroboracion():
    ahora = _T0 + timedelta(hours=1)
    lo = agrupar.puntuar(_cluster(n_fuentes=1), ahora=ahora)[0]
    hi = agrupar.puntuar(_cluster(n_fuentes=6), ahora=ahora)[0]
    assert hi > lo


def test_puntuar_monotono_en_frescura():
    ahora = _T0 + timedelta(hours=1)
    fresca = agrupar.puntuar(_cluster(ultimo_visto=ahora.isoformat()), ahora=ahora)[0]
    vieja = agrupar.puntuar(
        _cluster(ultimo_visto=(ahora - timedelta(hours=60)).isoformat()), ahora=ahora
    )[0]
    assert fresca > vieja


def test_puntuar_monotono_en_viralidad():
    s_baja = agrupar.puntuar(_cluster(senal=10), ahora=_T0)[0]
    s_alta = agrupar.puntuar(_cluster(senal=500_000), ahora=_T0)[0]
    assert s_alta > s_baja


def test_puntuar_breaking_sin_bonus_por_defecto():
    # Breaking ya NO es un empujón aditivo (emerge de corroboración ponderada × velocidad):
    # con los pesos por defecto el flag solo no cambia el score…
    sin = agrupar.puntuar(_cluster(n_fuentes=3, breaking=0), ahora=_T0)[0]
    con = agrupar.puntuar(_cluster(n_fuentes=3, breaking=1), ahora=_T0)[0]
    assert con == sin
    # …pero el knob de rollback sigue funcionando si config lo reactiva.
    pesos = agrupar.PesosScore(breaking=0.10)
    con_bonus = agrupar.puntuar(_cluster(n_fuentes=3, breaking=1), ahora=_T0, pesos=pesos)[0]
    assert con_bonus > sin


def _detalle(*entradas):
    """Atajo: timeline de outlets como lo persiste `recalcular` (peso + primer_visto)."""
    return [
        {"fuente_id": f"f{i}", "fuente": f"Fuente {i}", "host": f"f{i}.com",
         "peso": peso, "primer_visto": visto.isoformat(), "n_items": 1}
        for i, (peso, visto) in enumerate(entradas)
    ]


def test_puntuar_dos_potentes_simultaneas_rankean_top_y_breaking():
    # 2 fuentes potentes a la vez y on-brand → confianza 1.0 (la masa satura la corroboración)
    # × mérito alto (frescura + velocidad + marca) ⇒ top del pool, con flag breaking EN VIVO.
    pal = frozenset({"sismo", "cdmx", "magnitud"})
    cl = _cluster(
        n_fuentes=2, peso_fuentes=4.0, ultimo_visto=_T0.isoformat(),
        titulo="Sismo de magnitud 6.1 en CDMX",
        fuentes_detalle=_detalle((2.0, _T0 - timedelta(minutes=20)), (2.0, _T0 - timedelta(minutes=5))),
    )
    score, _razon, desglose = agrupar.puntuar_detalle(cl, palabras_marca=pal, ahora=_T0)
    assert score >= 0.55
    assert desglose["confianza"] == 1.0  # 2 potentes saturan la corroboración → confianza plena
    assert desglose["breaking"] == 1
    assert desglose["velocidad"] == 1.0
    assert desglose["peso_fuentes"] == 4.0


def test_puntuar_velocidad_decae_al_envejecer():
    detalle = _detalle((2.0, _T0), (2.0, _T0 + timedelta(minutes=15)))
    cl = _cluster(n_fuentes=2, peso_fuentes=4.0, ultimo_visto=(_T0 + timedelta(minutes=15)).isoformat(),
                  fuentes_detalle=detalle)
    fresca = agrupar.puntuar_detalle(cl, ahora=_T0 + timedelta(minutes=20))
    vieja = agrupar.puntuar_detalle(cl, ahora=_T0 + timedelta(hours=12))
    assert fresca[2]["velocidad"] == 1.0
    assert vieja[2]["velocidad"] == 0.0
    assert fresca[2]["breaking"] == 1
    assert vieja[2]["breaking"] == 0  # el breaking decae con la ventana
    assert fresca[0] > vieja[0]


def test_puntuar_corroboracion_pondera_el_peso_no_solo_el_conteo():
    # 2 potentes (masa 4.0) corroboran MÁS que 3 normales (masa 3.0).
    dos_potentes = _cluster(n_fuentes=2, peso_fuentes=4.0)
    tres_normales = _cluster(n_fuentes=3, peso_fuentes=3.0)
    s2 = agrupar.puntuar_detalle(dos_potentes, ahora=_T0)[2]["corroboracion"]
    s3 = agrupar.puntuar_detalle(tres_normales, ahora=_T0)[2]["corroboracion"]
    assert s2 > s3


def test_puntuar_unica_fuente_fresca_queda_bajo_el_umbral():
    # Una sola fuente recién llegada, sin encaje de marca, NO debe abrir el umbral (0.35).
    sola = _cluster(n_fuentes=1, peso_fuentes=1.0, senal=0, ultimo_visto=_T0.isoformat())
    score = agrupar.puntuar(sola, ahora=_T0)[0]
    assert score < agrupar.UMBRAL_MIN_SCORE_DEF


def test_puntuar_fallback_a_n_fuentes_sin_peso_persistido():
    # Cluster pre-migración (peso_fuentes=0): la masa cae al conteo de fuentes — el pool
    # vivo no colapsa a 0 en el primer arranque.
    viejo = _cluster(n_fuentes=4, peso_fuentes=0.0)
    nuevo = _cluster(n_fuentes=4, peso_fuentes=4.0)
    assert (
        agrupar.puntuar_detalle(viejo, ahora=_T0)[2]["corroboracion"]
        == agrupar.puntuar_detalle(nuevo, ahora=_T0)[2]["corroboracion"]
    )


def test_puntuar_relevancia_de_marca_sube_el_score():
    pal = frozenset({"reforma"})
    sin = agrupar.puntuar(_cluster(titulo="Noticia cualquiera"), ahora=_T0)[0]
    con = agrupar.puntuar(_cluster(titulo="Aprueban la reforma hoy"), palabras_marca=pal, ahora=_T0)[0]
    assert con > sin


def test_puntuar_pesos_inyectados_cambian_el_score():
    """Pesos de mérito inyectados (PesosScore) reemplazan los defaults: el ranking es configurable.

    Con mérito 0 (todos los pesos a 0) el score es 0 por mucha confianza/corroboración que haya:
    la corroboración MULTIPLICA el mérito, no lo crea (modelo v2).
    """
    pal = frozenset({"reforma"})
    cl = _cluster(n_fuentes=6, senal=0, breaking=0, ultimo_visto=_T0.isoformat(),
                  titulo="Aprueban la reforma")
    solo_marca = agrupar.PesosScore(
        frescura=0.0, marca=1.0, evento=0.0, viralidad=0.0, velocidad=0.0, rendimiento=0.0
    )
    todo_cero = agrupar.PesosScore(
        frescura=0.0, marca=0.0, evento=0.0, viralidad=0.0, velocidad=0.0, rendimiento=0.0
    )
    assert agrupar.puntuar(cl, palabras_marca=pal, ahora=_T0, pesos=solo_marca)[0] > 0.0
    assert agrupar.puntuar(cl, palabras_marca=pal, ahora=_T0, pesos=todo_cero)[0] == 0.0


def test_puntuar_senal_rendimiento_inerte_sin_peso():
    """La señal de rendimiento (Fase 2c) NO afecta con el peso por defecto (0): no rompe nada."""
    base = _cluster(n_fuentes=2, ultimo_visto=_T0.isoformat())
    con_bonus = {**base, "bonus_rendimiento": 1.0}
    assert agrupar.puntuar(base, ahora=_T0)[0] == agrupar.puntuar(con_bonus, ahora=_T0)[0]


def test_puntuar_senal_rendimiento_con_peso_sube_el_score():
    """Con peso > 0, una historia en una línea top (bonus 1.0) puntúa más que una sin bonus."""
    base = _cluster(n_fuentes=2, ultimo_visto=_T0.isoformat())
    pesos = agrupar.PesosScore(rendimiento=0.2)
    sin = agrupar.puntuar(base, ahora=_T0, pesos=pesos)[0]
    con = agrupar.puntuar({**base, "bonus_rendimiento": 1.0}, ahora=_T0, pesos=pesos)[0]
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
    score, razon, desglose = agrupar.puntuar_detalle(cl, palabras_marca=pal, ahora=_T0)
    assert agrupar.puntuar(cl, palabras_marca=pal, ahora=_T0) == (score, razon)  # wrapper fiel
    assert set(desglose) == {
        "corroboracion", "confianza", "velocidad", "frescura", "viralidad", "marca", "evento",
        "rendimiento", "peso_fuentes", "breaking", "palabras", "evento_titulo",
    }
    for senal in (
        "corroboracion", "confianza", "velocidad", "frescura", "viralidad", "marca", "evento",
        "rendimiento",
    ):
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
    s, casadas = agrupar.relevancia_marca_detalle(extranjera, pal)
    assert s > 0.0
    assert casadas == ("cdmx", "sismo")
    # Sin traducción, el titular EN no casa el vocabulario ES (comportamiento previo).
    sin_trad = {"titulo": "Earthquake shakes Mexico City this morning", "resumen": ""}
    assert agrupar.relevancia_marca_detalle(sin_trad, pal)[0] == 0.0


def test_puntuar_detalle_casa_vocabulario_pese_a_la_puntuacion():
    """La tokenización separa por no-alfanuméricos: 'México:' casa el término 'mexico'."""
    pal = frozenset({"mexico"})
    _s, _r, desglose = agrupar.puntuar_detalle(
        _cluster(titulo="México: arranca la jornada", ultimo_visto=_T0.isoformat()),
        palabras_marca=pal, ahora=_T0,
    )
    assert desglose["palabras"] == ["mexico"]


# --------------------------------------------------------------------------- #
# Modelo v2: confianza-multiplicador y encaje de evento                         #
# --------------------------------------------------------------------------- #


def test_puntuar_confianza_topa_la_fuente_unica():
    """Un rumor de fuente única, por fresco y on-brand que sea, queda TOPADO por la confianza.

    Misma historia, mismo mérito; la única diferencia es la corroboración. La corroborada
    (confianza plena) puntúa estrictamente más que la de fuente única (confianza = piso).
    """
    pal = frozenset({"reforma"})
    base = dict(titulo="Aprueban la reforma", ultimo_visto=_T0.isoformat())
    sola = _cluster(n_fuentes=1, peso_fuentes=1.0, **base)
    corroborada = _cluster(n_fuentes=4, peso_fuentes=4.0, **base)
    s_sola, _r, d_sola = agrupar.puntuar_detalle(sola, palabras_marca=pal, ahora=_T0)
    s_corr, _r2, d_corr = agrupar.puntuar_detalle(corroborada, palabras_marca=pal, ahora=_T0)
    assert d_sola["confianza"] == 0.5  # piso por defecto: no se mata, pero queda topada
    assert d_corr["confianza"] == 1.0  # masa 4 satura la corroboración
    assert s_corr > s_sola


def test_encaje_evento_casa_partido_proximo():
    """Una noticia que nombra los equipos de un evento PRÓXIMO de la agenda casa el encaje."""
    eventos = [{"titulo": "Portugal vs Uzbekistán", "fecha": _T0.date().isoformat()}]
    cl = _cluster(titulo="¿Dónde ver Portugal vs Uzbekistán hoy?", ultimo_visto=_T0.isoformat())
    s, titulo = agrupar.encaje_evento_detalle(cl, eventos, ahora=_T0)
    assert s == 1.0  # ambos equipos en el título + evento hoy (proximidad plena)
    assert titulo == "Portugal vs Uzbekistán"


def test_encaje_evento_fuera_de_ventana_no_casa():
    """Un evento lejano (más allá de la ventana) o ya pasado no aporta encaje."""
    lejano = [{"titulo": "Final", "fecha": (_T0 + timedelta(days=30)).date().isoformat()}]
    cl = _cluster(titulo="La gran final del torneo", ultimo_visto=_T0.isoformat())
    assert agrupar.encaje_evento_detalle(cl, lejano, ahora=_T0)[0] == 0.0
    # Sin agenda tampoco hay señal.
    assert agrupar.encaje_evento_detalle(cl, [], ahora=_T0)[0] == 0.0


def test_puntuar_evento_sube_el_score():
    """Con un evento próximo que casa, el score sube respecto a la misma historia sin agenda."""
    eventos = [{"titulo": "Portugal vs Uzbekistán", "fecha": _T0.date().isoformat()}]
    cl = _cluster(
        n_fuentes=2, peso_fuentes=2.0,
        titulo="Previa: Portugal vs Uzbekistán", ultimo_visto=_T0.isoformat(),
    )
    sin = agrupar.puntuar(cl, ahora=_T0)[0]
    con = agrupar.puntuar(cl, eventos=eventos, ahora=_T0)[0]
    assert con > sin


# --------------------------------------------------------------------------- #
# evaluar_umbral: el umbral de producción automática                            #
# --------------------------------------------------------------------------- #


def _cluster_apto(**campos):
    """Cluster que SUPERA el umbral por defecto: fresco, corroborado y con encaje de marca."""
    base = _cluster(
        n_fuentes=3, senal=100, ultimo_visto=_T0.isoformat(),
        titulo="Sismo sacude la CDMX esta mañana", verificacion="corroborada",
    )
    base.update(campos)
    return base


_PAL = frozenset({"sismo", "cdmx", "mexico"})


def test_umbral_supera_con_motivo_explicable():
    ok, motivo = agrupar.evaluar_umbral(_cluster_apto(), palabras_marca=_PAL, ahora=_T0)
    assert ok
    assert "sismo" in motivo  # el motivo nombra las palabras que casaron


def test_umbral_rechaza_verificacion_dudosa():
    ok, motivo = agrupar.evaluar_umbral(
        _cluster_apto(verificacion="dudosa"), palabras_marca=_PAL, ahora=_T0
    )
    assert not ok
    assert "dudosa" in motivo


def test_umbral_rechaza_score_bajo():
    vieja_sin_senales = _cluster_apto(
        n_fuentes=1, senal=0, ultimo_visto=(_T0 - timedelta(hours=70)).isoformat()
    )
    ok, motivo = agrupar.evaluar_umbral(vieja_sin_senales, palabras_marca=_PAL, ahora=_T0)
    assert not ok
    assert "score" in motivo


def test_umbral_recalcula_el_score_no_usa_el_persistido():
    """Un score persistido alto NO cuela: el umbral evalúa las señales DE AHORA (envejece)."""
    vieja = _cluster_apto(
        score=0.95, n_fuentes=1, senal=0,
        ultimo_visto=(_T0 - timedelta(hours=70)).isoformat(),
    )
    ok, _motivo = agrupar.evaluar_umbral(vieja, palabras_marca=_PAL, ahora=_T0)
    assert not ok


def test_umbral_rechaza_sin_encaje_de_marca():
    ok, motivo = agrupar.evaluar_umbral(
        _cluster_apto(titulo="Celebrity gossip news today"), palabras_marca=_PAL, ahora=_T0
    )
    assert not ok
    assert "marca" in motivo


def test_umbral_madura_antes_de_promover():
    """Con maduración, una historia recién vista NO se promueve aún (motivo explicable)."""
    recien = _cluster_apto(primer_visto=(_T0 - timedelta(minutes=10)).isoformat())
    ok, motivo = agrupar.evaluar_umbral(
        recien, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert not ok
    assert "madurando" in motivo


def test_umbral_madurada_se_promueve():
    madura = _cluster_apto(primer_visto=(_T0 - timedelta(minutes=50)).isoformat())
    ok, _motivo = agrupar.evaluar_umbral(
        madura, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok


def test_umbral_maduracion_exime_breaking_corroborada_y_curadas():
    from keni_consola.dominio.ingesta import SENAL_CURADO

    breaking = _cluster_apto(breaking=1, primer_visto=(_T0 - timedelta(minutes=1)).isoformat())
    ok, _m = agrupar.evaluar_umbral(
        breaking, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok  # la urgencia real no espera
    curada = _cluster_apto(
        senal=SENAL_CURADO, primer_visto=(_T0 - timedelta(minutes=1)).isoformat()
    )
    ok, _m = agrupar.evaluar_umbral(
        curada, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok  # el humano ya decidió


def test_umbral_maduracion_sin_primer_visto_no_retiene():
    """Un dato ausente no castiga: sin `primer_visto` parseable la regla no aplica."""
    ok, _m = agrupar.evaluar_umbral(
        _cluster_apto(), palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok


def test_umbral_exime_de_marca_a_lo_curado_por_el_equipo():
    from keni_consola.dominio.ingesta import SENAL_CURADO

    curada = _cluster_apto(titulo="Apunte del equipo sin vocabulario", senal=SENAL_CURADO)
    ok, _motivo = agrupar.evaluar_umbral(curada, palabras_marca=_PAL, ahora=_T0)
    assert ok  # el humano ya decidió: no se le exige vocabulario


def test_umbral_exime_de_marca_a_breaking_corroborada():
    breaking = _cluster_apto(titulo="Evento inesperado sin vocabulario aun", breaking=1)
    ok, _motivo = agrupar.evaluar_umbral(breaking, palabras_marca=_PAL, ahora=_T0)
    assert ok  # evento mayor confirmado por varias fuentes a la vez


def test_umbral_dos_potentes_recien_nacida_sale_sin_madurar():
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
        breaking=0,  # flag persistido desfasado: el umbral deriva el vivo del timeline
    )
    ok, motivo = agrupar.evaluar_umbral(
        cl, palabras_marca=_PAL, min_maduracion_min=45, ahora=_T0
    )
    assert ok
    assert "score" in motivo


def test_umbral_breaking_sin_corroborar_no_queda_exenta():
    breaking_unica = _cluster_apto(
        titulo="Evento inesperado sin vocabulario", breaking=1, verificacion="unica_fuente"
    )
    ok, _motivo = agrupar.evaluar_umbral(breaking_unica, palabras_marca=_PAL, ahora=_T0)
    assert not ok


def test_umbral_umbral_cero_desactiva_cada_regla():
    sin_encaje = _cluster_apto(titulo="Celebrity gossip news today")
    ok, _ = agrupar.evaluar_umbral(
        sin_encaje, palabras_marca=_PAL, min_marca=0.0, ahora=_T0
    )
    assert ok  # min_marca=0 apaga el umbral de marca (el de score se mantiene)


# --------------------------------------------------------------------------- #
# Auto-verificación por corroboración (Ola D)                                  #
# --------------------------------------------------------------------------- #


def test_verificacion_corroborada_con_dos_outlets_distintos():
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n"),
        _item(fuente_id="b", url="https://medio-b.com/n"),
    ]
    assert agrupar.clasificar_verificacion(items) == "corroborada"


def test_verificacion_dos_enlaces_del_mismo_outlet_no_corrobora():
    # Dos urls del MISMO host = una sola fuente real (no corroboración).
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n1"),
        _item(fuente_id="a2", url="https://medio-a.com/n2"),
    ]
    assert agrupar.clasificar_verificacion(items) == "unica_fuente"


def test_verificacion_unica_fuente_fiable():
    items = [_item(fuente_id="a", url="https://medio-serio.com/n")]
    assert agrupar.clasificar_verificacion(items) == "unica_fuente"


def test_verificacion_dudosa_si_unica_fuente_es_de_baja_confianza():
    baja = frozenset({"reddit.com"})
    items = [_item(fuente_id="r", url="https://reddit.com/r/x/post", fuente_nombre="Reddit")]
    assert agrupar.clasificar_verificacion(items, fuentes_baja=baja) == "dudosa"


def test_verificacion_dudosa_por_clickbait():
    items = [_item(fuente_id="a", url="https://medio.com/n", titulo="No vas a creer lo que pasó")]
    assert agrupar.clasificar_verificacion(items) == "dudosa"


def test_verificacion_corroborada_gana_a_baja_confianza():
    # Aunque una sea de baja confianza, dos outlets distintos = corroborada.
    baja = frozenset({"reddit.com"})
    items = [
        _item(fuente_id="r", url="https://reddit.com/r/x/post"),
        _item(fuente_id="b", url="https://medio-serio.com/n"),
    ]
    assert agrupar.clasificar_verificacion(items, fuentes_baja=baja) == "corroborada"


def test_recalcular_fija_verificacion_e_idioma_representativo():
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n", idioma="en", titulo="Foreign headline here"),
        _item(fuente_id="b", url="https://medio-b.com/n", idioma="en", titulo="Foreign headline here"),
    ]
    rec = agrupar.recalcular({"id": "c1"}, items)
    assert rec["verificacion"] == "corroborada"
    # idioma del representativo (no hay 'es' -> el de mayor señal/título): inglés.
    assert rec["idioma"] == "en"
    assert "en" in rec["idiomas"]


# --------------------------------------------------------------------------- #
# Asignación determinista + Asignador (índice con blocking)                     #
# --------------------------------------------------------------------------- #


def test_asignar_empate_exacto_gana_el_primero():
    """A clave IDÉNTICA entre varios clusters gana el primer candidato (determinista: decide el
    orden de entrada, no el azar del dict)."""
    clave = agrupar.clave_cluster({"url": "", "titulo": "El presidente anuncia nueva reforma"})
    c_a = {"id": "primero", "clave": clave, "titulo": "El presidente anuncia nueva reforma"}
    c_b = {"id": "segundo", "clave": clave, "titulo": "El presidente anuncia nueva reforma"}
    item = _item(url="", titulo="El presidente anuncia nueva reforma")
    assert agrupar.asignar(item, [c_a, c_b]) == "primero"
    # Invertir el orden invierte el ganador.
    assert agrupar.asignar(item, [c_b, c_a]) == "segundo"


def test_asignador_replica_las_decisiones_de_asignar():
    titulo_largo = "El presidente anuncia una nueva reforma para los estados"
    clusters = [
        {"id": "u1", "clave": "url:example.com/nota-1", "titulo": "Titular original"},
        {"id": "f1", "clave": agrupar.clave_cluster({"url": "", "titulo": titulo_largo}),
         "titulo": titulo_largo},
    ]
    asignador = agrupar.Asignador(clusters)
    # (a) cruce exacto por url canónica (la query se ignora).
    por_url = _item(url="https://example.com/nota-1?utm_source=tw", titulo="Algo distinto")
    assert asignador.asignar(por_url) == "u1" == agrupar.asignar(por_url, clusters)
    # (b) título normalizado IDÉNTICO.
    por_titulo = _item(url="", titulo=titulo_largo)
    assert asignador.asignar(por_titulo) == "f1" == agrupar.asignar(por_titulo, clusters)
    # (c) nada casa -> None (cluster nuevo).
    nuevo = _item(url="", titulo="Resultados de la jornada de fútbol del domingo")
    assert asignador.asignar(nuevo) is None
    assert agrupar.asignar(nuevo, clusters) is None


def test_asignador_agregar_une_items_del_mismo_barrido():
    asignador = agrupar.Asignador([])
    titulo = "Gran final del torneo de verano"
    asignador.agregar(
        {"id": "n1", "clave": agrupar.clave_cluster({"url": "", "titulo": titulo}), "titulo": titulo}
    )
    assert asignador.asignar(_item(url="", titulo=titulo)) == "n1"


def test_asignador_titulos_distintos_no_se_unen():
    """Sin léxico fuzzy: dos titulares distintos (aunque cortos) nunca colisionan en `asignar`."""
    asignador = agrupar.Asignador([{"id": "c", "clave": "t:nfl", "titulo": "NFL"}])
    assert asignador.asignar(_item(url="", titulo="F1")) is None


# --------------------------------------------------------------------------- #
# Relevancia de marca GRADUADA (saturación suave + límite de palabra)           #
# --------------------------------------------------------------------------- #


def test_relevancia_marca_gradua_por_numero_de_coincidencias():
    pal = frozenset({"futbol", "gol", "liga mx"})
    una = agrupar._relevancia_marca({"titulo": "El futbol de hoy", "resumen": ""}, pal)
    tres = agrupar._relevancia_marca({"titulo": "Futbol: gol en la liga mx", "resumen": ""}, pal)
    assert 0.0 < una < tres <= 1.0  # 1 keyword ya NO puntúa igual que 3 (escalón eliminado)


def test_relevancia_marca_resumen_pesa_menos_que_titulo():
    pal = frozenset({"reforma"})
    en_titulo = agrupar._relevancia_marca({"titulo": "Aprueban la reforma", "resumen": ""}, pal)
    en_resumen = agrupar._relevancia_marca({"titulo": "Noticia del día", "resumen": "sobre la reforma"}, pal)
    assert en_titulo > en_resumen > 0.0


def test_relevancia_marca_frases_casan_por_limite_de_palabra():
    pal = frozenset({"box office"})
    assert agrupar._relevancia_marca({"titulo": "box office records", "resumen": ""}, pal) > 0.0
    assert agrupar._relevancia_marca({"titulo": "boxofficemania total", "resumen": ""}, pal) == 0.0


def test_puntuar_sigue_monotono_en_relevancia_graduada():
    pal = frozenset({"futbol", "gol"})
    poco = agrupar.puntuar(_cluster(titulo="El futbol de hoy"), palabras_marca=pal, ahora=_T0)[0]
    mucho = agrupar.puntuar(_cluster(titulo="Futbol con gol agónico"), palabras_marca=pal, ahora=_T0)[0]
    assert mucho > poco > agrupar.puntuar(_cluster(titulo="Nada relacionado"), palabras_marca=pal, ahora=_T0)[0]


# --------------------------------------------------------------------------- #
# Marca por vocabulario (historias solo-Trends/agencias, sin marca dominante)   #
# --------------------------------------------------------------------------- #


def test_marca_por_vocabulario_elige_la_mejor_sobre_el_umbral():
    voc = {
        "claro-sports": frozenset({"futbol", "gol"}),
        "unotv": frozenset({"sismo", "cdmx"}),
    }
    cluster = {"titulo": "Futbol: gol de último minuto", "resumen": ""}
    assert agrupar.marca_por_vocabulario(cluster, voc) == "claro-sports"


def test_marca_por_vocabulario_sin_encaje_queda_vacia():
    voc = {"claro-sports": frozenset({"futbol"}), "unotv": frozenset({"sismo"})}
    assert agrupar.marca_por_vocabulario({"titulo": "Tema sin encaje alguno", "resumen": ""}, voc) == ""
    # Coincidencia SOLO de resumen (0.2) no alcanza el umbral por defecto (0.3).
    solo_resumen = {"titulo": "Tema neutro", "resumen": "se habló de futbol"}
    assert agrupar.marca_por_vocabulario(solo_resumen, voc) == ""


def test_marca_por_vocabulario_empate_determinista():
    voc = {"b-marca": frozenset({"futbol"}), "a-marca": frozenset({"futbol"})}
    assert agrupar.marca_por_vocabulario({"titulo": "El futbol manda", "resumen": ""}, voc) == "a-marca"


# --------------------------------------------------------------------------- #
# Insumos CURADOS: no secuestran el titular ni saturan la viralidad             #
# --------------------------------------------------------------------------- #


def test_representativo_prefiere_titular_periodistico_sobre_curado():
    items = [
        _item(fuente_id="cajon-ideas", titulo="nota curada del equipo", senal=1_000_000),
        _item(fuente_id="rss1", titulo="Titular periodístico real de la noticia", senal=500),
    ]
    r = agrupar.recalcular(_base_cluster(), items)
    assert r["titulo"] == "Titular periodístico real de la noticia"
    # La señal artificial del curado NO satura la viralidad de la historia mixta.
    assert r["senal"] == 500


def test_cluster_solo_curado_conserva_su_senal_y_titulo():
    items = [_item(fuente_id="cajon-ideas", titulo="nota curada del equipo", senal=1_000_000)]
    r = agrupar.recalcular(_base_cluster(), items)
    assert r["titulo"] == "nota curada del equipo"
    assert r["senal"] == 1_000_000  # el auto-feed de curados sigue funcionando


# --------------------------------------------------------------------------- #
# seleccionar_diversos (MMR suave para la promoción ADMITIR)                    #
# --------------------------------------------------------------------------- #


def _c_div(cid, titulo):
    return {"id": cid, "titulo": titulo}


def test_seleccionar_diversos_salta_titulos_casi_identicos():
    clusters = [
        _c_div("a", "Messi gana el premio en París"),
        _c_div("b", "Messi gana el premio en París hoy"),  # casi idéntico al primero
        _c_div("c", "Sismo de magnitud en la capital"),
    ]
    out = agrupar.seleccionar_diversos(clusters, maximo=2, umbral=0.8)
    assert [c["id"] for c in out] == ["a", "c"]  # el macro-tema no se come las dos plazas


def test_seleccionar_diversos_es_suave_rellena_si_faltan():
    clusters = [
        _c_div("a", "Messi gana el premio en París"),
        _c_div("b", "Messi gana el premio en París hoy"),
    ]
    out = agrupar.seleccionar_diversos(clusters, maximo=2, umbral=0.8)
    assert [c["id"] for c in out] == ["a", "b"]  # nunca devuelve menos por diversificar


def test_seleccionar_diversos_umbral_cero_es_top_n_puro():
    clusters = [_c_div("a", "Mismo título repetido"), _c_div("b", "Mismo título repetido")]
    assert [c["id"] for c in agrupar.seleccionar_diversos(clusters, maximo=2, umbral=0.0)] == ["a", "b"]

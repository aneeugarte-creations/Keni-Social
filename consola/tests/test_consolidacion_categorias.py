"""Consolidación de LÍNEAS (un solo eje por marca): `grupo`/`cadencia` en `etiquetas`,
`linea_id` en `fuentes_rss`, y el backfill `categoria`->`linea_id` del bootstrap.

Slice 1 del rediseño: las líneas editoriales (clase `categoria`) pasan a llevar su agrupación
(`grupo`) y su ritmo de sondeo (`cadencia`); cada feed cuelga de una línea (`linea_id`) en vez
del slug libre `categoria`. Aquí se cubre el round-trip de persistencia y la siembra por marca.
"""

from __future__ import annotations

from keni_consola import bootstrap_categorias, db, repos


def test_etiqueta_roundtrip_grupo_cadencia(entorno):
    # Explícitos: grupo + cadencia viajan a la BD y vuelven.
    et = repos.crear_etiqueta(
        nombre="Liga MX", clase="categoria", marca="claro-sports",
        grupo="Fútbol", cadencia="rapida",
    )
    leida = repos.obtener_etiqueta_por_nombre("Liga MX", "categoria", "claro-sports")
    assert leida is not None
    assert leida["grupo"] == "Fútbol"
    assert leida["cadencia"] == "rapida"
    assert et["grupo"] == "Fútbol" and et["cadencia"] == "rapida"


def test_etiqueta_defaults_grupo_cadencia(entorno):
    # Omitidos: grupo '' (línea plana) y cadencia 'normal' (ritmo por defecto).
    repos.crear_etiqueta(nombre="Nacional", clase="categoria", marca="unotv")
    leida = repos.obtener_etiqueta_por_nombre("Nacional", "categoria", "unotv")
    assert leida is not None
    assert leida["grupo"] == ""
    assert leida["cadencia"] == "normal"


def test_crear_etiqueta_devuelve_flags_como_bool(entorno):
    # `crear_etiqueta` homogeneiza con `obtener`/`listar`: `activo`/`es_evergreen` son bool.
    et = repos.crear_etiqueta(
        nombre="Evergreen", clase="campania", marca="unotv", es_evergreen=True,
    )
    assert et["activo"] is True
    assert et["es_evergreen"] is True
    leida = repos.obtener_etiqueta(et["id"])
    assert leida is not None
    assert et["activo"] == leida["activo"] and et["es_evergreen"] == leida["es_evergreen"]


def test_fuente_roundtrip_linea_id(entorno):
    fr = repos.crear_fuente_rss(
        "Diario", "https://example.com/feed.xml", marca="unotv", linea_id="abc123",
    )
    assert db.obtener_fuente_rss(fr["id"])["linea_id"] == "abc123"


def test_bootstrap_siembra_grupos_cadencia_y_pilares(entorno):
    bootstrap_categorias.inicializar_categorias()
    # Claro: la competición cuelga del grupo "Fútbol" y sondea rápido.
    liga = repos.obtener_etiqueta_por_nombre("Liga MX", "categoria", "claro-sports")
    assert liga is not None and liga["grupo"] == "Fútbol" and liga["cadencia"] == "rapida"
    # UnoTV: solo sus líneas reales (Nacional/Internacional/Entretenimiento), planas y normales.
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "categoria", "unotv")
    assert nacional is not None and nacional["grupo"] == "" and nacional["cadencia"] == "normal"
    # Fundación: sus pilares de misión quedan sembrados (no nace sin líneas).
    salud = repos.obtener_etiqueta_por_nombre("Salud", "categoria", "fundacion")
    assert salud is not None and salud["cadencia"] == "evergreen"
    # Nación Gamer: al menos su línea base.
    gaming = repos.obtener_etiqueta_por_nombre("Gaming", "categoria", "nacion-gamer")
    assert gaming is not None


def test_bootstrap_siembra_keywords_de_fundacion(entorno):
    # Las líneas de Fundación reciben su catálogo de keywords: sus feeds traen slugs gruesos que
    # no mapean a sus líneas, así que la Mesa y la admisión las clasifican por CONTENIDO.
    bootstrap_categorias.inicializar_categorias()
    ciencia = repos.obtener_etiqueta_por_nombre("Ciencia/Tech", "categoria", "fundacion")
    salud = repos.obtener_etiqueta_por_nombre("Salud", "categoria", "fundacion")
    assert "cientifico" in (ciencia["keywords"] or "")
    assert "vacuna" in (salud["keywords"] or "")


def test_slug_hashtag_normaliza_nombre_de_linea():
    # El hashtag de una línea es el slug de su nombre: sin acentos, minúscula, solo alfanumérico.
    assert bootstrap_categorias.slug_hashtag("Ciencia/Tech") == "cienciatech"
    assert bootstrap_categorias.slug_hashtag("Medio ambiente") == "medioambiente"
    assert bootstrap_categorias.slug_hashtag("LaLiga (España)") == "laligaespana"
    assert bootstrap_categorias.slug_hashtag("Educación") == "educacion"
    assert bootstrap_categorias.slug_hashtag("  ") == ""


def test_bootstrap_siembra_hashtag_de_linea(entorno):
    # Cada línea recibe su hashtag (slug del nombre): la firma de la sección que la etapa Keywords
    # inyecta siempre, para que el desglose de métricas por línea exista también en el caption.
    bootstrap_categorias.inicializar_categorias()
    ciencia = repos.obtener_etiqueta_por_nombre("Ciencia/Tech", "categoria", "fundacion")
    assert ciencia is not None and ciencia["hashtags"] == "cienciatech"
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "categoria", "unotv")
    assert nacional is not None and nacional["hashtags"] == "nacional"


def test_bootstrap_fuerza_el_hashtag_de_linea_aunque_difiera(entorno):
    # Línea = hashtag (1:1, derivado del nombre): NO es un campo libre. El bootstrap reconcilia
    # forzando el slug aunque una línea existente tuviera otro valor (lo mantiene en sincronía).
    repos.crear_etiqueta(
        nombre="Salud", clase="categoria", marca="fundacion", hashtags="otracosa",
    )
    bootstrap_categorias.inicializar_categorias()
    salud = repos.obtener_etiqueta_por_nombre("Salud", "categoria", "fundacion")
    assert salud is not None and salud["hashtags"] == "salud"


def test_crear_linea_deriva_el_hashtag_del_nombre_e_ignora_lo_enviado(entorno):
    # Una línea nueva (clase categoria) deriva su hashtag del nombre, pase lo que pase en `hashtags`.
    from keni_consola.api.etiquetas import _crear

    status, cuerpo = _crear(
        nombre="Ciencia/Tech", clase="categoria", marca="fundacion", color="",
        keywords="", hashtags="loquesea", ttl_dias=0, es_evergreen=True, grupo="", cadencia="evergreen",
    )
    assert status == 200 and cuerpo["etiqueta"]["hashtags"] == "cienciatech"


def test_crear_campania_respeta_el_hashtag_del_equipo(entorno):
    # Las campañas NO derivan: el equipo fija sus hashtags (puede llevar varios, su casing).
    from keni_consola.api.etiquetas import _crear

    _status, cuerpo = _crear(
        nombre="Mundial", clase="campania", marca="unotv", color="",
        keywords="", hashtags="Mundial2026", ttl_dias=0, es_evergreen=False, grupo="", cadencia="normal",
    )
    assert cuerpo["etiqueta"]["hashtags"] == "Mundial2026"


def test_renombrar_linea_resincroniza_su_hashtag(entorno):
    # Renombrar una línea re-sincroniza su hashtag (línea = hashtag, 1:1).
    from keni_consola.api.etiquetas import _actualizar, _crear

    _status, c = _crear(
        nombre="Salud", clase="categoria", marca="fundacion", color="",
        keywords="", hashtags="", ttl_dias=0, es_evergreen=True, grupo="", cadencia="evergreen",
    )
    status, cuerpo = _actualizar(c["etiqueta"]["id"], {"nombre": "Medio ambiente"})
    assert status == 200 and cuerpo["etiqueta"]["hashtags"] == "medioambiente"


def test_bootstrap_claro_grupos_de_navegacion_y_lineas_nuevas(entorno):
    bootstrap_categorias.inicializar_categorias()

    def g(nombre: str) -> dict:
        et = repos.obtener_etiqueta_por_nombre(nombre, "categoria", "claro-sports")
        assert et is not None, nombre
        return et

    # Cada disciplina cae en su CHIP de la barra de navegación, no en un cajón "Otros deportes".
    assert g("F1 Checo")["grupo"] == "Motor"
    assert g("F1 (no Checo)")["grupo"] == "Motor"
    assert g("NFL")["grupo"] == "NFL"
    assert g("NBA")["grupo"] == "NBA"
    assert g("MLB")["grupo"] == "Béisbol"
    assert g("LMB")["grupo"] == "Béisbol"
    # Transversal pasó a llamarse Actualidad.
    assert g("Televisión")["grupo"] == "Actualidad"
    # Líneas NUEVAS sembradas con su grupo y sus keywords.
    boxeo = g("Boxeo")
    assert boxeo["grupo"] == "Boxeo" and "canelo" in boxeo["keywords"]
    assert g("Tenis")["grupo"] == "Otros deportes" and "tenis" in g("Tenis")["keywords"]
    assert g("UFC")["grupo"] == "Otros deportes"


def test_reconcilia_regrupa_y_siembra_keywords_guarded(entorno):
    # Línea con la taxonomía VIEJA (NFL bajo "Otros deportes", sin keywords) y otra con grupo +
    # keywords puestos a mano (el equipo): la reconciliación debe re-grupar la primera y sembrar
    # sus keywords, pero NUNCA pisar las ediciones a mano de la segunda.
    repos.crear_etiqueta(
        nombre="NFL", clase="categoria", marca="claro-sports",
        grupo="Otros deportes", cadencia="rapida",
    )
    repos.crear_etiqueta(
        nombre="Boxeo", clase="categoria", marca="claro-sports",
        grupo="Mi grupo a mano", keywords="mis, keywords", cadencia="rapida",
    )
    bootstrap_categorias.inicializar_categorias()
    nfl = repos.obtener_etiqueta_por_nombre("NFL", "categoria", "claro-sports")
    assert nfl["grupo"] == "NFL"  # re-grupado (grupo gestionado por el bootstrap)
    assert "nfl" in nfl["keywords"]  # keywords sembradas (estaban vacías)
    boxeo = repos.obtener_etiqueta_por_nombre("Boxeo", "categoria", "claro-sports")
    assert boxeo["grupo"] == "Mi grupo a mano"  # grupo a mano: intacto
    assert boxeo["keywords"] == "mis, keywords"  # keywords a mano: intactas


def test_clasificador_asigna_linea_claro_por_keywords_sembradas(entorno):
    from keni_consola.dominio import clasificador_categorias

    bootstrap_categorias.inicializar_categorias()
    res = clasificador_categorias.clasificar_pieza(
        "Canelo Álvarez ya tendría pactada su próxima pelea de box", "", "claro-sports",
    )
    boxeo = repos.obtener_etiqueta_por_nombre("Boxeo", "categoria", "claro-sports")
    assert res["categoria"] == boxeo["id"]


def test_vincular_fuentes_a_lineas_mapea_por_marca(entorno):
    bootstrap_categorias.inicializar_categorias()
    # Feed de UnoTV con slug 'mx' -> debe quedar enganchado a la línea "Nacional".
    mapeada = repos.crear_fuente_rss("UnoTV MX", "https://u.example/mx.xml", marca="unotv", categoria="mx")
    # Feed con slug sin equivalencia 1:1 -> se queda en catch-all (linea_id '').
    suelta = repos.crear_fuente_rss("UnoTV otra", "https://u.example/x.xml", marca="unotv", categoria="negocios")
    bootstrap_categorias.vincular_fuentes_a_lineas()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "categoria", "unotv")
    assert db.obtener_fuente_rss(mapeada["id"])["linea_id"] == nacional["id"]
    assert db.obtener_fuente_rss(suelta["id"])["linea_id"] == ""


def test_vincular_fuentes_es_idempotente_y_no_pisa(entorno):
    bootstrap_categorias.inicializar_categorias()
    # Una asociación ya puesta a mano no se sobreescribe aunque la categoría mapearía a otra línea.
    fija = repos.crear_fuente_rss(
        "Fija", "https://u.example/f.xml", marca="unotv", categoria="mx", linea_id="manual-x",
    )
    bootstrap_categorias.vincular_fuentes_a_lineas()
    assert db.obtener_fuente_rss(fija["id"])["linea_id"] == "manual-x"


# --------------------------------------------------------------------------- #
# API: etiquetas (grupo/cadencia) y fuentes (linea_id)                         #
# --------------------------------------------------------------------------- #
_URL_OK = "https://93.184.216.34/feed.xml"  # IP pública literal: pasa el guard SSRF sin DNS.


def test_api_etiqueta_acepta_grupo_y_cadencia(cliente):
    r = cliente.post(
        "/api/etiquetas",
        json={"nombre": "Liga MX", "clase": "categoria", "marca": "claro-sports",
              "grupo": "Fútbol", "cadencia": "rapida"},
    )
    assert r.status_code == 200, r.text
    et = r.json()["etiqueta"]
    assert et["grupo"] == "Fútbol" and et["cadencia"] == "rapida"


def test_api_etiqueta_cadencia_invalida_cae_a_normal(cliente):
    r = cliente.post(
        "/api/etiquetas",
        json={"nombre": "X", "clase": "categoria", "marca": "unotv", "cadencia": "turbo"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["etiqueta"]["cadencia"] == "normal"


def test_api_fuente_acepta_linea_id_valida(cliente):
    et = cliente.post(
        "/api/etiquetas",
        json={"nombre": "Nacional", "clase": "categoria", "marca": "unotv"},
    ).json()["etiqueta"]
    r = cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "Diario", "url": _URL_OK, "marca": "unotv", "linea_id": et["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["fuente"]["linea_id"] == et["id"]


def test_api_fuente_rechaza_linea_inexistente(cliente):
    r = cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "Diario", "url": _URL_OK, "marca": "unotv", "linea_id": "nope"},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Re-clavado del scheduler: slug -> línea (resolver + migración plan/franjas)  #
# --------------------------------------------------------------------------- #


def test_linea_id_de_slug_resuelve_y_es_idempotente(entorno):
    bootstrap_categorias.inicializar_categorias()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "categoria", "unotv")
    # Señales del motor: pasan tal cual.
    assert bootstrap_categorias.linea_id_de_slug("unotv", "breaking") == "breaking"
    assert bootstrap_categorias.linea_id_de_slug("unotv", "evergreen") == "evergreen"
    assert bootstrap_categorias.linea_id_de_slug("unotv", "") == ""
    # Slug temático -> id de su línea.
    assert bootstrap_categorias.linea_id_de_slug("unotv", "mx") == nacional["id"]
    # Idempotente: un id de línea ya migrado se devuelve igual.
    assert bootstrap_categorias.linea_id_de_slug("unotv", nacional["id"]) == nacional["id"]
    # No mapeable (cajón 'mx' de Claro, sin línea fina) -> genérico ''.
    assert bootstrap_categorias.linea_id_de_slug("claro-sports", "mx") == ""


def test_migrar_plan_y_franjas_a_lineas(entorno):
    from keni_consola import ajustes

    bootstrap_categorias.inicializar_categorias()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "categoria", "unotv")
    # Plan y franja en forma SLUG (la forma de entrada, anterior al re-clavado a líneas).
    ajustes.guardar("KENI_PLAN_DIA::unotv", "mx:4,breaking:2")
    franja = repos.crear_franja(1, "09:00", marca="unotv", red="x", categoria="mx")
    bootstrap_categorias.migrar_plan_y_franjas_a_lineas()
    # Plan re-clavado: 'mx' -> id de Nacional; 'breaking' conservado.
    assert ajustes.obtener("KENI_PLAN_DIA::unotv") == f"{nacional['id']}:4,breaking:2"
    # Franja re-clavada a la línea (borrada+recreada con la nueva categoría).
    franjas_unotv = [f for f in repos.listar_franjas() if f["marca"] == "unotv"]
    assert any(f["categoria"] == nacional["id"] for f in franjas_unotv)
    assert not any(f["categoria"] == "mx" for f in franjas_unotv)
    # Idempotente: una segunda pasada no cambia nada.
    antes = ajustes.obtener("KENI_PLAN_DIA::unotv")
    assert bootstrap_categorias.migrar_plan_y_franjas_a_lineas() == 0
    assert ajustes.obtener("KENI_PLAN_DIA::unotv") == antes


def test_retirar_categorias_obsoletas_desactiva_pero_conserva(entorno):
    bootstrap_categorias.inicializar_categorias()
    # Una etiqueta vieja que ya no es línea del plan (creada como activa).
    com = repos.crear_etiqueta(nombre="Comercial", clase="categoria", marca="unotv")
    assert com["activo"] is True
    n = bootstrap_categorias.retirar_categorias_obsoletas()
    assert n >= 1
    # Desactivada (no borrada): sigue existiendo pero activo=False.
    leida = repos.obtener_etiqueta_por_nombre("Comercial", "categoria", "unotv")
    assert leida is not None and leida["activo"] is False
    # Una línea real de UnoTV sigue activa.
    nac = repos.obtener_etiqueta_por_nombre("Nacional", "categoria", "unotv")
    assert nac is not None and nac["activo"] is True
    # Idempotente: una segunda pasada no toca nada (ya inactiva).
    assert bootstrap_categorias.retirar_categorias_obsoletas() == 0

"""Consolidación de LÍNEAS (un solo eje por marca): `grupo`/`cadencia` en `etiquetas`,
`linea_id` en `fuentes_rss`, y el backfill `categoria`->`linea_id` del bootstrap.

Slice 1 del rediseño: las líneas editoriales (clase `vertical`) pasan a llevar su agrupación
(`grupo`) y su ritmo de sondeo (`cadencia`); cada feed cuelga de una línea (`linea_id`) en vez
del slug libre `categoria`. Aquí se cubre el round-trip de persistencia y la siembra por marca.
"""

from __future__ import annotations

from keni_consola import bootstrap_lineas, db, repos


def test_etiqueta_roundtrip_grupo_cadencia(entorno):
    # Explícitos: grupo + cadencia viajan a la BD y vuelven.
    et = repos.crear_etiqueta(
        nombre="Liga MX", clase="vertical", marca="claro-sports",
        grupo="Fútbol", cadencia="rapida",
    )
    leida = repos.obtener_etiqueta_por_nombre("Liga MX", "vertical", "claro-sports")
    assert leida is not None
    assert leida["grupo"] == "Fútbol"
    assert leida["cadencia"] == "rapida"
    assert et["grupo"] == "Fútbol" and et["cadencia"] == "rapida"


def test_etiqueta_defaults_grupo_cadencia(entorno):
    # Omitidos: grupo '' (línea plana) y cadencia 'normal' (ritmo por defecto).
    repos.crear_etiqueta(nombre="Nacional", clase="vertical", marca="unotv")
    leida = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")
    assert leida is not None
    assert leida["grupo"] == ""
    assert leida["cadencia"] == "normal"


def test_fuente_roundtrip_linea_id(entorno):
    fr = repos.crear_fuente_rss(
        "Diario", "https://example.com/feed.xml", marca="unotv", linea_id="abc123",
    )
    assert db.obtener_fuente_rss(fr["id"])["linea_id"] == "abc123"


def test_bootstrap_siembra_grupos_cadencia_y_pilares(entorno):
    bootstrap_lineas.inicializar_lineas()
    # Claro: la competición cuelga del grupo "Fútbol" y sondea rápido.
    liga = repos.obtener_etiqueta_por_nombre("Liga MX", "vertical", "claro-sports")
    assert liga is not None and liga["grupo"] == "Fútbol" and liga["cadencia"] == "rapida"
    # UnoTV: Ciencia/Tech es de cambio lento (evergreen), sin grupo.
    ciencia = repos.obtener_etiqueta_por_nombre("Ciencia/Tech", "vertical", "unotv")
    assert ciencia is not None and ciencia["grupo"] == "" and ciencia["cadencia"] == "evergreen"
    # Fundación: sus pilares de misión quedan sembrados (antes vacía).
    salud = repos.obtener_etiqueta_por_nombre("Salud", "vertical", "fundacion")
    assert salud is not None and salud["cadencia"] == "evergreen"
    # Nación Gamer: al menos su línea base.
    gaming = repos.obtener_etiqueta_por_nombre("Gaming", "vertical", "nacion-gamer")
    assert gaming is not None


def test_vincular_fuentes_a_lineas_mapea_por_marca(entorno):
    bootstrap_lineas.inicializar_lineas()
    # Feed de UnoTV con slug 'mx' -> debe quedar enganchado a la línea "Nacional".
    mapeada = repos.crear_fuente_rss("UnoTV MX", "https://u.example/mx.xml", marca="unotv", categoria="mx")
    # Feed con slug sin equivalencia 1:1 -> se queda en catch-all (linea_id '').
    suelta = repos.crear_fuente_rss("UnoTV otra", "https://u.example/x.xml", marca="unotv", categoria="negocios")
    bootstrap_lineas.vincular_fuentes_a_lineas()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")
    assert db.obtener_fuente_rss(mapeada["id"])["linea_id"] == nacional["id"]
    assert db.obtener_fuente_rss(suelta["id"])["linea_id"] == ""


def test_vincular_fuentes_es_idempotente_y_no_pisa(entorno):
    bootstrap_lineas.inicializar_lineas()
    # Una asociación ya puesta a mano no se sobreescribe aunque la categoría mapearía a otra línea.
    fija = repos.crear_fuente_rss(
        "Fija", "https://u.example/f.xml", marca="unotv", categoria="mx", linea_id="manual-x",
    )
    bootstrap_lineas.vincular_fuentes_a_lineas()
    assert db.obtener_fuente_rss(fija["id"])["linea_id"] == "manual-x"


# --------------------------------------------------------------------------- #
# API: etiquetas (grupo/cadencia) y fuentes (linea_id)                         #
# --------------------------------------------------------------------------- #
_URL_OK = "https://93.184.216.34/feed.xml"  # IP pública literal: pasa el guard SSRF sin DNS.


def test_api_etiqueta_acepta_grupo_y_cadencia(cliente):
    r = cliente.post(
        "/api/etiquetas",
        json={"nombre": "Liga MX", "clase": "vertical", "marca": "claro-sports",
              "grupo": "Fútbol", "cadencia": "rapida"},
    )
    assert r.status_code == 200, r.text
    et = r.json()["etiqueta"]
    assert et["grupo"] == "Fútbol" and et["cadencia"] == "rapida"


def test_api_etiqueta_cadencia_invalida_cae_a_normal(cliente):
    r = cliente.post(
        "/api/etiquetas",
        json={"nombre": "X", "clase": "vertical", "marca": "unotv", "cadencia": "turbo"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["etiqueta"]["cadencia"] == "normal"


def test_api_fuente_acepta_linea_id_valida(cliente):
    et = cliente.post(
        "/api/etiquetas",
        json={"nombre": "Nacional", "clase": "vertical", "marca": "unotv"},
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
    bootstrap_lineas.inicializar_lineas()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")
    # Señales del motor: pasan tal cual.
    assert bootstrap_lineas.linea_id_de_slug("unotv", "breaking") == "breaking"
    assert bootstrap_lineas.linea_id_de_slug("unotv", "evergreen") == "evergreen"
    assert bootstrap_lineas.linea_id_de_slug("unotv", "") == ""
    # Slug temático -> id de su línea.
    assert bootstrap_lineas.linea_id_de_slug("unotv", "mx") == nacional["id"]
    # Idempotente: un id de línea ya migrado se devuelve igual.
    assert bootstrap_lineas.linea_id_de_slug("unotv", nacional["id"]) == nacional["id"]
    # No mapeable (cajón 'mx' de Claro, sin línea fina) -> genérico ''.
    assert bootstrap_lineas.linea_id_de_slug("claro-sports", "mx") == ""


def test_migrar_plan_y_franjas_a_lineas(entorno):
    from keni_consola import ajustes

    bootstrap_lineas.inicializar_lineas()
    nacional = repos.obtener_etiqueta_por_nombre("Nacional", "vertical", "unotv")
    # Plan y franja en forma SLUG (lo de antes del re-clavado).
    ajustes.guardar("KENI_PLAN_DIA::unotv", "mx:4,breaking:2")
    franja = repos.crear_franja(1, "09:00", marca="unotv", red="x", categoria="mx")
    bootstrap_lineas.migrar_plan_y_franjas_a_lineas()
    # Plan re-clavado: 'mx' -> id de Nacional; 'breaking' conservado.
    assert ajustes.obtener("KENI_PLAN_DIA::unotv") == f"{nacional['id']}:4,breaking:2"
    # Franja re-clavada a la línea (borrada+recreada con la nueva categoría).
    franjas_unotv = [f for f in repos.listar_franjas() if f["marca"] == "unotv"]
    assert any(f["categoria"] == nacional["id"] for f in franjas_unotv)
    assert not any(f["categoria"] == "mx" for f in franjas_unotv)
    # Idempotente: una segunda pasada no cambia nada.
    antes = ajustes.obtener("KENI_PLAN_DIA::unotv")
    assert bootstrap_lineas.migrar_plan_y_franjas_a_lineas() == 0
    assert ajustes.obtener("KENI_PLAN_DIA::unotv") == antes

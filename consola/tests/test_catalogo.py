"""Tests del catálogo de apps (manifests + registro data-driven).

Verifican el contrato de `apps/registro.py` (ADR 0005 / plan §1) SIN red ni BD:
  - las 3 apps de producto + el shell se cargan de sus manifests TOML,
  - el catálogo reproduce EXACTAMENTE el sidebar hardcodeado de hoy (grupos/orden),
  - desactivar el flag de una app la OCULTA del catálogo sin romper nada,
  - el shell NO figura como app de catálogo (pero sí aporta su nav: Panel).

El endpoint `GET /api/catalogo` se prueba en su forma de payload aquí (la app
completa necesita Postgres y se cubre vía el cliente en los tests de API que skipean
sin PG); este test ataca el registro directamente, así corre siempre.
"""

from __future__ import annotations

from keni_consola.apps import registro

# Estructura ESPERADA del sidebar (espejo del `navegacion.ts` hardcodeado de hoy):
# 3 bloques sin encabezado, en este orden y con estas etiquetas.
_SIDEBAR_HOY = [
    ["Panel"],
    ["Generación", "Investigación", "Revisión", "Analíticas"],
    ["Publicaciones", "Parrilla", "Skills", "Agentes"],
]


def _entorno(**flags: str) -> dict[str, str]:
    """Entorno controlado: solo las env vars que pasamos (sin heredar el shell)."""
    return dict(flags)


def test_se_cargan_las_cuatro_unidades():
    ids = sorted(a.id for a in registro.cargar_apps())
    assert ids == ["metricas", "operacion", "produccion", "shell"]


def test_apps_de_catalogo_excluyen_el_shell():
    # Por defecto (sin flags) las 3 apps de producto están activas; el shell no es app.
    ids = sorted(a.id for a in registro.apps_activas(_entorno()))
    assert ids == ["metricas", "operacion", "produccion"]


def test_cada_app_lleva_descripcion_y_nav_para_la_tarjeta():
    # El launcher (cajón de apps) pinta una tarjeta por app con su `descripcion`
    # top-level y deriva la ruta primaria del PRIMER item de `nav`.
    cat = registro.catalogo(_entorno())
    porid = {a["id"]: a for a in cat["apps"]}

    # Descripción top-level (frase de la tarjeta) en cada app de catálogo.
    assert porid["produccion"]["descripcion"] == "Copy, clips, skills y verificación"
    assert porid["metricas"]["descripcion"] == "Métricas, comercial y reportes"
    assert porid["operacion"]["descripcion"] == "Rota, parrilla y publicación"

    # Cada app trae su nav (items con ruta/etiqueta/icono), ordenada.
    for app in cat["apps"]:
        assert app["nav"], f"{app['id']} sin nav"
        for item in app["nav"]:
            assert {"ruta", "etiqueta", "icono", "descripcion"} <= set(item)

    # La ruta primaria (primer item) de cada app es la esperada.
    assert porid["produccion"]["nav"][0]["ruta"] == "/generacion"
    assert porid["metricas"]["nav"][0]["ruta"] == "/analiticas"
    assert porid["operacion"]["nav"][0]["ruta"] == "/publicaciones"


def test_catalogo_reproduce_el_sidebar_de_hoy():
    cat = registro.catalogo(_entorno())
    grupos = [[i["etiqueta"] for i in g["items"]] for g in cat["navegacion"]]
    assert grupos == _SIDEBAR_HOY
    # Todos los bloques van sin encabezado (separador discreto), como hoy.
    assert all(g["etiqueta"] == "" for g in cat["navegacion"])


def test_iconos_de_nav_son_strings_lucide():
    cat = registro.catalogo(_entorno())
    iconos = {i["ruta"]: i["icono"] for g in cat["navegacion"] for i in g["items"]}
    assert iconos["/panel"] == "LayoutDashboard"
    assert iconos["/generacion"] == "Sparkles"
    assert iconos["/investigacion"] == "Search"
    assert iconos["/revision"] == "ShieldCheck"
    assert iconos["/analiticas"] == "BarChart3"
    assert iconos["/publicaciones"] == "Send"
    assert iconos["/parrilla"] == "CalendarClock"
    assert iconos["/skills"] == "Wand2"
    assert iconos["/agentes"] == "Bot"


def test_desactivar_flag_oculta_la_app_del_catalogo():
    cat = registro.catalogo(_entorno(KENI_APP_METRICAS="0"))
    ids = [a["id"] for a in cat["apps"]]
    assert "metricas" not in ids
    assert ids == ["operacion", "produccion"]
    # Y su entrada de nav (Analíticas) desaparece del sidebar.
    rutas = [i["ruta"] for g in cat["navegacion"] for i in g["items"]]
    assert "/analiticas" not in rutas
    # Las demás siguen.
    assert "/generacion" in rutas and "/publicaciones" in rutas and "/panel" in rutas


def test_flag_acepta_varias_formas_de_off():
    for off in ("0", "false", "FALSE", "no", "off"):
        cat = registro.catalogo(_entorno(KENI_APP_OPERACION=off))
        assert "operacion" not in [a["id"] for a in cat["apps"]], off
    # Cualquier otro valor (o vacío/ausente) la deja activa.
    for on in ("1", "true", "sí", ""):
        cat = registro.catalogo(_entorno(KENI_APP_OPERACION=on))
        assert "operacion" in [a["id"] for a in cat["apps"]], on


def test_panel_es_del_shell_pero_aparece_en_nav():
    # El shell no es app de catálogo, pero su entrada Panel encabeza el sidebar.
    cat = registro.catalogo(_entorno())
    assert "shell" not in [a["id"] for a in cat["apps"]]
    primer_bloque = cat["navegacion"][0]["items"]
    assert primer_bloque[0]["ruta"] == "/panel"


def test_modulo_a_app_cubre_todos_los_routers_sin_solapes():
    mapa = registro.modulo_a_app()
    # Reparto canónico de ADR 0005 (muestra representativa por unidad).
    assert mapa["generaciones"] == "produccion"
    assert mapa["metricas"] == "metricas"
    assert mapa["publicaciones"] == "operacion"
    assert mapa["auth"] == "shell"
    # Sin solapes: tantas claves como módulos sumados de los manifests.
    total = sum(len(a.modulos_backend) for a in registro.cargar_apps())
    assert len(mapa) == total


# --------------------------------------------------------------------------- #
# Endpoint vivo: GET /api/catalogo (usa el cliente; SKIPea sin Postgres).       #
# --------------------------------------------------------------------------- #
def test_endpoint_catalogo_sirve_apps_y_navegacion(cliente):
    datos = cliente.get("/api/catalogo").json()
    assert sorted(a["id"] for a in datos["apps"]) == ["metricas", "operacion", "produccion"]
    grupos = [[i["etiqueta"] for i in g["items"]] for g in datos["navegacion"]]
    assert grupos == _SIDEBAR_HOY


def test_endpoint_catalogo_respeta_el_flag(cliente, monkeypatch):
    # Desactivar el flag de Métricas la oculta del catálogo SIN romper el arranque.
    monkeypatch.setenv("KENI_APP_METRICAS", "0")
    datos = cliente.get("/api/catalogo").json()
    assert "metricas" not in [a["id"] for a in datos["apps"]]
    rutas = [i["ruta"] for g in datos["navegacion"] for i in g["items"]]
    assert "/analiticas" not in rutas

"""Tests del catálogo de apps (manifests + registro data-driven).

Verifican el contrato de `apps/registro.py` (ADR 0005 / plan §1) SIN red ni BD:
  - las 3 apps de producto + el shell se cargan de sus manifests TOML,
  - el catálogo agrupa la nav por MOMENTO DEL FLUJO (Operación / Contenido / Datos),
    con encabezado de bloque visible, en el orden y con las etiquetas esperadas,
  - desactivar el flag de una app la OCULTA del catálogo sin romper nada,
  - el shell NO figura como app de catálogo ni aporta entradas de nav.

El endpoint `GET /api/catalogo` se prueba en su forma de payload aquí (la app
completa necesita Postgres y se cubre vía el cliente en los tests de API que skipean
sin PG); este test ataca el registro directamente, así corre siempre.
"""

from __future__ import annotations

from keni_consola.apps import registro

# Estructura ESPERADA del sidebar: 3 bloques agrupados por MOMENTO DEL FLUJO, en este
# orden, con encabezado visible. El bloque es VISUAL y se desacopla del dueño de la app.
_SIDEBAR_BLOQUES = [
    # "Operación": los checkpoints que el equipo toca cada día — el Feed (red social interna +
    # lista de contenido), la Programación (calendario de publicaciones, por marca) y los Turnos
    # (rota de cobertura del equipo, por marca; el tablero de Tareas vive integrado como pestaña
    # «Cobertura» dentro de Turnos, sin entrada propia de nav). La página "Revisión" se retiró
    # por obsoleta (la aprobación vive en línea en el Feed).
    ["Feed", "Programación", "Turnos"],
    # "Contenido": TRES páginas planas por tipo de contenido (sin hub con pestañas) —
    # Imagen (editor de imagen por capas + IA), Video (estudio de video) y Texto (la
    # Texto: prompts + línea editorial + plantillas).
    ["Imagen", "Video", "Texto"],
    # "Máquina": la máquina de generación — dos cockpits de igual peso (Investigación:
    # descubre/verifica; Producción: genera copy/arte) + la página Agentes (los dos agentes de
    # ejecución: Workers —pool reactivo— y Daemons —proactivos— + economía de tokens + el FEED de
    # actividad, TODO JUNTO). Tras la consolidación de navegación, cada motor sale UNA sola vez y
    # vive aquí: las viejas entradas «datos» de Investigación y Producción (esta última, el feed)
    # se retiraron del menú (Investigación → cockpit; el feed → sección «Actividad» de Agentes).
    ["Investigación", "Producción", "Agentes"],
    # "Datos": lo que alimenta o refleja la automatización. Solo queda Analíticas (la medición
    # que cierra el loop); la aporta `metricas.toml`.
    ["Analíticas"],
]

# Encabezados humanos de cada bloque, en el mismo orden.
_ETIQUETAS_BLOQUES = ["Operación", "Contenido", "Máquina", "Datos"]


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
    assert porid["produccion"]["descripcion"] == "Copy, clips, imágenes y verificación"
    assert porid["metricas"]["descripcion"] == "Métricas, comercial y reportes"
    assert porid["operacion"]["descripcion"] == "Rota, parrilla y publicación"

    # Cada app trae su nav (items con ruta/etiqueta/icono), ordenada.
    for app in cat["apps"]:
        assert app["nav"], f"{app['id']} sin nav"
        for item in app["nav"]:
            assert {"ruta", "etiqueta", "icono", "descripcion"} <= set(item)

    # La ruta primaria (primer item) de cada app: `nav` viene ordenada por bloque de
    # flujo (grupo_orden, orden). Tras retirar Revisión, la 1ª entrada de Producción cae en
    # el bloque "contenido" (Imagen), ya que la app dejó de aportar entradas al bloque "operacion".
    assert porid["produccion"]["nav"][0]["ruta"] == "/contenido/imagen"
    assert porid["metricas"]["nav"][0]["ruta"] == "/datos/analiticas"
    # La app "operacion" aporta TRES entradas (Feed, Programación, Turnos); la 1ª por orden es
    # Feed (el tablero de Tareas ya no tiene entrada: vive dentro de Turnos como «Cobertura»).
    assert porid["operacion"]["nav"][0]["ruta"] == "/operacion/feed"


def test_catalogo_agrupa_la_nav_por_flujo():
    cat = registro.catalogo(_entorno())
    grupos = [[i["etiqueta"] for i in g["items"]] for g in cat["navegacion"]]
    assert grupos == _SIDEBAR_BLOQUES
    # Cada bloque lleva su encabezado humano (no "") en el orden esperado.
    assert [g["etiqueta"] for g in cat["navegacion"]] == _ETIQUETAS_BLOQUES


def test_iconos_de_nav_son_strings_lucide():
    cat = registro.catalogo(_entorno())
    iconos = {i["ruta"]: i["icono"] for g in cat["navegacion"] for i in g["items"]}
    assert iconos["/contenido/imagen"] == "Image"
    assert iconos["/contenido/video"] == "Clapperboard"
    assert iconos["/datos/analiticas"] == "BarChart3"
    assert iconos["/operacion/feed"] == "LayoutGrid"
    assert iconos["/operacion/programacion"] == "CalendarDays"
    assert iconos["/operacion/turnos"] == "CalendarClock"
    # Los motores de la máquina viven en el bloque «Máquina» (una sola entrada cada uno);
    # las viejas entradas «datos» (/datos/investigacion, /datos/produccion) se retiraron del menú.
    assert iconos["/maquina/investigacion"] == "Search"
    assert iconos["/maquina/produccion"] == "Sparkles"
    assert iconos["/maquina/agentes"] == "Bot"
    assert "/datos/investigacion" not in iconos
    assert "/datos/produccion" not in iconos


def test_desactivar_flag_oculta_la_app_del_catalogo():
    cat = registro.catalogo(_entorno(KENI_APP_METRICAS="0"))
    ids = [a["id"] for a in cat["apps"]]
    assert "metricas" not in ids
    assert ids == ["operacion", "produccion"]
    # Y su entrada de nav (Analíticas) desaparece del sidebar.
    rutas = [i["ruta"] for g in cat["navegacion"] for i in g["items"]]
    assert "/datos/analiticas" not in rutas
    # Las demás siguen.
    assert "/contenido/imagen" in rutas and "/operacion/feed" in rutas


def test_flag_acepta_varias_formas_de_off():
    for off in ("0", "false", "FALSE", "no", "off"):
        cat = registro.catalogo(_entorno(KENI_APP_OPERACION=off))
        assert "operacion" not in [a["id"] for a in cat["apps"]], off
    # Cualquier otro valor (o vacío/ausente) la deja activa.
    for on in ("1", "true", "sí", ""):
        cat = registro.catalogo(_entorno(KENI_APP_OPERACION=on))
        assert "operacion" in [a["id"] for a in cat["apps"]], on


def test_shell_no_es_app_ni_aporta_nav():
    # El shell no es app de catálogo y (tras retirar el Panel) ya no aporta nav: el
    # sidebar lo encabeza el Feed del equipo, no una entrada del shell.
    cat = registro.catalogo(_entorno())
    assert "shell" not in [a["id"] for a in cat["apps"]]
    primer_bloque = cat["navegacion"][0]["items"]
    assert primer_bloque[0]["ruta"] == "/operacion/feed"
    rutas = [i["ruta"] for g in cat["navegacion"] for i in g["items"]]
    assert "/panel" not in rutas


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
    assert grupos == _SIDEBAR_BLOQUES


def test_endpoint_catalogo_respeta_el_flag(cliente, monkeypatch):
    # Desactivar el flag de Métricas la oculta del catálogo SIN romper el arranque.
    monkeypatch.setenv("KENI_APP_METRICAS", "0")
    datos = cliente.get("/api/catalogo").json()
    assert "metricas" not in [a["id"] for a in datos["apps"]]
    rutas = [i["ruta"] for g in datos["navegacion"] for i in g["items"]]
    assert "/datos/analiticas" not in rutas

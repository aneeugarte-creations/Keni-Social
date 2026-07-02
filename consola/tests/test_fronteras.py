"""Lint de FRONTERAS entre apps (ADR 0002 · ADR 0005).

Regla de oro (ADR 0002): un módulo de una app NUNCA importa los internals de otra
app. Las apps de producto (Producción, Métricas, Operación) se comunican por contratos
del gateway / `keni-shared`, no importando las tripas unas de otras.

Tras la reorg por paquetes (ADR 0005), la UNIDAD de un fichero se deriva de su RUTA:

  - `keni_consola/produccion/**` → unidad `produccion`
  - `keni_consola/operacion/**`  → unidad `operacion`
  - `keni_consola/metricas/**`   → unidad `metricas`
  - `keni_consola/api/<m>(.py|/…)` → la app que declara `<m>` en su `apps/<app>.toml`
    (`registro.modulo_a_app()`); sin declaración cae a `nucleo` (lo caza aparte
    `test_cada_router_mapea_a_una_unica_app`).
  - TODO lo demás (raíz, `dominio/`, `db/`, `repos/`, `config/`, `_db_core/`,
    `libprompts/`, `pipeline_contenido/`, `generaciones/`, `auth/`, `apps/`,
    `motores/`, `esquema_api/`, `evals/`…) → `nucleo`: la base transversal (antes
    "shell"), análoga a `keni-shared`, que ofrece servicios a las apps.

Cómo lo verifica, SIN red ni BD (AST puro): escanea TODO el árbol `keni_consola/`
(salvo `webapp/` y `__pycache__`), resuelve cada import (relativo y absoluto, más
`importlib.import_module("keni_consola…")` literal) al MÓDULO destino, deriva su
unidad por la MISMA regla de ruta, y clasifica el cruce:

  - dst == src            : OK (mismo dueño).
  - dst == nucleo         : OK (app→nucleo / nucleo→nucleo: base transversal).
  - app → OTRA app        : PROHIBIDO salvo seam de la ALLOWLIST.
  - nucleo → app          : PROHIBIDO salvo RAÍZ DE COMPOSICIÓN (`daemons.py`,
                            `__main__.py`: cablean los daemons de cada app) o seam.

La ALLOWLIST codifica los seams de ADR 0005 (cruces legítimos de HOY); cada entrada
lleva su justificación. Clave: `(ruta_fichero_origen, fqn_modulo_destino)` relativos a
`keni_consola` (p.ej. `("api/produccion.py", "api.piezas")`).
"""

from __future__ import annotations

import ast
from pathlib import Path

from keni_consola import api
from keni_consola.apps import registro

_RAIZ_PKG = Path(api.__file__).parent.parent  # …/keni_consola
_PAQUETE_RAIZ = "keni_consola"

APPS_PRODUCTO = frozenset({"produccion", "operacion", "metricas"})

# Ficheros del núcleo que SÍ pueden importar módulos de una app: cablean los daemons de
# fondo de cada app (composición de arranque), no consumen sus internals de producto.
RAICES_COMPOSICION = frozenset({"daemons.py", "__main__.py"})

# --------------------------------------------------------------------------- #
# ALLOWLIST de seams (ADR 0005): (ruta_origen, fqn_destino) EXPLÍCITAMENTE      #
# permitidos. Mantener mínima y comentada.                                      #
# --------------------------------------------------------------------------- #
SEAMS_PERMITIDOS: frozenset[tuple[str, str]] = frozenset(
    {
        # Seam (producción lee la agenda de operación): el panel "Producción del día"
        # (`api/produccion.py`, app produccion) muestra la cola de programación con el
        # PRÓXIMO HUECO por red, y ese cálculo (franjas + ocupados) vive en
        # `api.piezas.calcular_hueco_para` (operacion) — la MISMA función del encolado
        # manual y de la auto-programación, a propósito: si el panel calculara sus huecos
        # aparte, mentiría en cuanto divergieran. SOLO LECTURA (no muta nada de operación).
        ("api/produccion.py", "api.piezas"),
        # Seam (el núcleo lee señales de producción para el DOCTOR de salud):
        # `api/estado.py` (núcleo) absorbió los chequeos del banner (cola, presupuesto,
        # daemons, disco…) y para el de la COLA lee el snapshot del router `api.actividad`
        # (producción) — SOLO LECTURA. El health-check es transversal: le importa a todo el
        # equipo, no a una app. (ADR 0005.)
        ("api/estado.py", "api.actividad"),
        # Seam (inyección del descargador de feeds): `agencias`, `agencias_fotos` y
        # `stock_fotos` (núcleo) reutilizan el descargador HTTP inyectable del router de RSS
        # (`api.rss._DESCARGADOR`) para no duplicar la lógica de descarga/reintentos. Es un
        # punto de inyección compartido, de solo lectura sobre el seam, no consumo de las
        # tripas del router. (ADR 0005.)
        ("agencias.py", "api.rss"),
        ("agencias_fotos.py", "api.rss"),
        ("stock_fotos.py", "api.rss"),
        # Seam (el auto-programador encola en el próximo hueco): `auto_programar` (núcleo)
        # deposita en el hueco libre por la función-CONTRATO de operación
        # `api.piezas._encolar_en_hueco_libre` (import TARDÍO para no enredar el grafo), la
        # MISMA ruta que el encolado manual. Es el handoff hacia la agenda de operación, no
        # acceso a su almacén. (ADR 0005.)
        ("auto_programar.py", "api.piezas"),
        # Seam (montaje único de la cadena de aprobación): el avance del pipeline
        # (`pipeline_contenido/_avance.py`, núcleo) monta la cadena por el punto ÚNICO de
        # operación `api.colaboracion.montar_cadena_aprobacion` (import TARDÍO), para que
        # exista una sola definición de la cadena. (ADR 0005.)
        ("pipeline_contenido/_avance.py", "api.colaboracion"),
        # NOTA — seams RETIRADOS al mover el contrato A→C al núcleo:
        #   ("historial","piezas") y ("marcas","colaboracion"): sus destinos
        #   (`dominio.piezas`, `dominio.colaboracion`) son ahora NÚCLEO por definición de
        #   ruta (viven en `dominio/`, no en una app). El contrato A→C (crear_borrador,
        #   primitivas de aprobación) vive donde ambos lados pueden llamarlo: el núcleo.
        #   Importarlo es app→núcleo (siempre permitido), ya no un cruce app↔app.
    }
)


def _seam_permitido(rel: str, fqn: str) -> bool:
    """La allowlist se declara a nivel de MÓDULO destino (`api.piezas`); un import de un
    SÍMBOLO de ese módulo (`api.piezas.calcular_hueco_para`) queda cubierto por el mismo
    seam. Casa por igualdad o por prefijo de módulo."""
    for origen, destino in SEAMS_PERMITIDOS:
        if origen == rel and (fqn == destino or fqn.startswith(destino + ".")):
            return True
    return False


def _unidad_de_partes(partes: list[str]) -> str:
    """Unidad de un módulo dadas sus partes RELATIVAS a `keni_consola` (sin el prefijo)."""
    if not partes or not partes[0]:
        return "nucleo"
    s0 = partes[0]
    if s0 in APPS_PRODUCTO:
        return s0
    if s0 == "api":
        if len(partes) >= 2:
            return registro.modulo_a_app().get(partes[1], "nucleo")
        return "nucleo"
    return "nucleo"


def unidad_de_ruta(relpath: str) -> str:
    """Unidad de un fichero fuente dado su path relativo a `keni_consola` (posix)."""
    partes = relpath.split("/")
    # api/<m>.py -> el <m> es partes[1] sin extensión; api/<m>/… -> partes[1]
    if partes[0] == "api" and len(partes) >= 2 and partes[1].endswith(".py"):
        partes = ["api", partes[1][:-3]]
    return _unidad_de_partes(partes)


def _pkg_partes(relpath: str) -> list[str]:
    """Partes del PAQUETE de un fichero (relativas a keni_consola), sin el nombre de fichero."""
    return relpath.split("/")[:-1]


def _abs_desde_relativo(pkg: list[str], level: int, modpath: str) -> list[str]:
    anchor = pkg if level == 1 else pkg[: len(pkg) - (level - 1)]
    return anchor + (modpath.split(".") if modpath else [])


def _fqns_import_from(node: ast.ImportFrom, pkg: list[str]) -> set[str]:
    """fqns (relativas a keni_consola) candidatas de un `from … import …`."""
    if node.level >= 1:
        container = _abs_desde_relativo(pkg, node.level, node.module or "")
    else:
        mod = node.module or ""
        partes = mod.split(".") if mod else []
        if not partes or partes[0] != _PAQUETE_RAIZ:
            return set()  # absoluto de otro paquete: nunca es de una app
        container = partes[1:]
    base = ".".join(container)
    fqns: set[str] = set()
    if base:
        fqns.add(base)
    for alias in node.names:
        fqns.add(f"{base}.{alias.name}" if base else alias.name)
    return fqns


def _fqns_import(node: ast.Import) -> set[str]:
    fqns: set[str] = set()
    for alias in node.names:
        partes = alias.name.split(".")
        if partes[0] == _PAQUETE_RAIZ and len(partes) >= 2:
            fqns.add(".".join(partes[1:]))
    return fqns


def _fqns_importlib(node: ast.Call) -> set[str]:
    func = node.func
    es = (isinstance(func, ast.Attribute) and func.attr == "import_module") or (
        isinstance(func, ast.Name) and func.id == "import_module"
    )
    if not es or not node.args:
        return set()
    arg = node.args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        return set()
    partes = arg.value.split(".")
    if partes[0] != _PAQUETE_RAIZ or len(partes) < 2:
        return set()
    return {".".join(partes[1:])}


def _fqns_de_nodo(node: ast.AST, pkg: list[str]) -> set[str]:
    if isinstance(node, ast.ImportFrom):
        return _fqns_import_from(node, pkg)
    if isinstance(node, ast.Import):
        return _fqns_import(node)
    if isinstance(node, ast.Call):
        return _fqns_importlib(node)
    return set()


def _ficheros() -> list[Path]:
    return [
        p
        for p in _RAIZ_PKG.rglob("*.py")
        if "__pycache__" not in p.parts and "webapp" not in p.parts
    ]


def _cruces() -> list[tuple[str, str, str, str]]:
    """(ruta_origen, unidad_origen, fqn_destino, unidad_destino) para cada cruce hacia una app
    que NO sea núcleo ni el mismo dueño. Excluye lo permitido por regla (app→núcleo)."""
    cruces: list[tuple[str, str, str, str]] = []
    for ruta in _ficheros():
        rel = ruta.relative_to(_RAIZ_PKG).as_posix()
        src_unit = unidad_de_ruta(rel)
        pkg = _pkg_partes(rel)
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        vistos: set[str] = set()
        for node in ast.walk(arbol):
            for fqn in _fqns_de_nodo(node, pkg):
                if fqn in vistos:
                    continue
                vistos.add(fqn)
                dst_unit = _unidad_de_partes(fqn.split("."))
                if dst_unit == src_unit or dst_unit == "nucleo":
                    continue
                cruces.append((rel, src_unit, fqn, dst_unit))
    return cruces


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #


def test_cada_router_mapea_a_una_unica_app():
    """Todo router (`api/<X>.py` con RUTAS) pertenece a EXACTAMENTE una unidad."""
    import importlib
    import pkgutil

    mapa = registro.modulo_a_app()
    sin_unidad: list[str] = []
    for info in pkgutil.iter_modules(api.__path__):
        if info.name.startswith("_"):
            continue
        try:
            modulo = importlib.import_module(f"{api.__name__}.{info.name}")
        except ImportError:
            continue
        if getattr(modulo, "RUTAS", None) is None:
            continue
        if info.name not in mapa:
            sin_unidad.append(info.name)
    assert not sin_unidad, (
        f"Routers sin app declarada en ningún manifest: {sin_unidad}. "
        "Añádelos a su `apps/<app>.toml` (modulos_backend)."
    )


def test_fronteras_apps_sin_cruces_fuera_de_allowlist():
    """NINGÚN fichero cruza a otra app salvo por un seam de la allowlist o una raíz de
    composición (ADR 0005). Verde con el repo de HOY."""
    violaciones = []
    for rel, src_unit, fqn, dst_unit in _cruces():
        if _seam_permitido(rel, fqn):
            continue
        # nucleo -> app permitido para las raíces de composición (cableado de daemons).
        nombre_fichero = rel.split("/")[-1]
        if src_unit == "nucleo" and nombre_fichero in RAICES_COMPOSICION:
            continue
        violaciones.append((rel, src_unit, fqn, dst_unit))
    assert not violaciones, (
        "Cruces de frontera entre apps FUERA de la allowlist (ADR 0005):\n"
        + "\n".join(
            f"  - {rel} ({src}) importa '{fqn}' ({dst})"
            for (rel, src, fqn, dst) in violaciones
        )
        + "\nResuélvelo por contrato del gateway / keni-shared, o (si es un seam "
        "legítimo) añádelo a SEAMS_PERMITIDOS con su justificación."
    )


def test_allowlist_no_tiene_seams_muertos():
    """Higiene: cada entrada de la allowlist apunta a un par existente (origen real en el
    árbol y destino que resuelve a una app), para que no acumule basura."""
    mapa = registro.modulo_a_app()
    for origen, destino in SEAMS_PERMITIDOS:
        assert (_RAIZ_PKG / origen).is_file(), f"Seam con origen inexistente: {origen}"
        partes = destino.split(".")
        unidad = _unidad_de_partes(partes)
        assert unidad in APPS_PRODUCTO, (
            f"Seam con destino que no es de ninguna app de producto: {destino} ({unidad})"
        )
        if partes[0] == "api":
            assert partes[1] in mapa, f"Seam a router api desconocido: {destino}"


def test_el_lint_detecta_una_violacion_sintetica():
    """PRUEBA de que el lint MUERDE: un fichero de `metricas/` que importa
    `keni_consola.produccion.trends` (internals de producción) DEBE dispararse."""
    mapa = registro.modulo_a_app()
    assert unidad_de_ruta("metricas/refresco_piezas.py") == "metricas"
    assert unidad_de_ruta("produccion/trends.py") == "produccion"

    pkg = _pkg_partes("metricas/algo.py")  # ["metricas"]
    for fragmento in (
        "from ..produccion import trends\n",
        "from ..produccion.trends import algo\n",
        "from keni_consola.produccion import trends\n",
        "from keni_consola.produccion.trends import algo\n",
        "import keni_consola.produccion.trends\n",
        "import importlib\nimportlib.import_module('keni_consola.produccion.trends')\n",
        "from importlib import import_module\nimport_module('keni_consola.produccion.trends')\n",
    ):
        arbol = ast.parse(fragmento)
        unidades = set()
        for node in ast.walk(arbol):
            for fqn in _fqns_de_nodo(node, pkg):
                unidades.add(_unidad_de_partes(fqn.split(".")))
        assert "produccion" in unidades, f"el resolver no detectó el cruce en: {fragmento!r}"

    # Absolutos de OTROS paquetes nunca cuentan.
    for fragmento in (
        "from keni_shared.marcas import opciones\n",
        "import starlette.routing\n",
        "importlib.import_module('keni_shared.marcas')\n",
    ):
        arbol = ast.parse(fragmento)
        for node in ast.walk(arbol):
            assert not _fqns_de_nodo(node, pkg), f"falso positivo en: {fragmento!r}"

    # Y (metricas -> produccion.trends) NO está en la allowlist: sería una violación.
    assert ("metricas/algo.py", "produccion.trends") not in SEAMS_PERMITIDOS

"""Lint de FRONTERAS entre apps (ADR 0002 · ADR 0005).

Regla de oro (ADR 0002): un módulo de una app NUNCA importa los internals de otra
app. Las apps de producto (A·Producción, B·Métricas, C·Operación) se comunican por
contratos del gateway / `keni-shared`, no importando las tripas unas de otras.

Cómo lo verifica este test, SIN red ni BD (AST puro):
  1. Mapea cada ROUTER (`api/<X>.py` que exporta `RUTAS`) a su app/unidad vía los
     manifests (`apps/<app>.toml`), usando `registro.modulo_a_app()`.
  2. Parsea los imports de cada router y los resuelve al módulo "dueño":
       - relativos: `from ..dominio.<Y>`, `from ..api.<Y>`, `from .. import <Y>`,
         `from ..<Y>`;
       - absolutos dentro del paquete: `from keni_consola.dominio.<Y> import ...`,
         `import keni_consola.api.<Y>` y `importlib.import_module("keni_consola...")`
         con string literal (las tres formas evadirían el lint si solo mirara los
         relativos).
     Todos apuntan al módulo base `<Y>`; si `<Y>` es un módulo declarado por OTRA
     unidad, es un cruce de frontera.
  3. CLASIFICA el cruce:
       - app → SHELL  : SIEMPRE permitido. El shell es la capa transversal/base que
                        ofrece servicios a A/B/C (auth, config, media, secretos…),
                        análoga a `keni-shared`. (ADR 0005.)
       - app ↔ app    : PROHIBIDO salvo seam explícito (A↔B↔C).
       - shell → app  : PROHIBIDO salvo seam explícito (el shell no debe acoplarse a
                        las tripas de una app salvo los cruces documentados).
  4. FALLA si hay un cruce prohibido fuera de la ALLOWLIST.

La ALLOWLIST codifica los seams de ADR 0005 (cruces legítimos de HOY) para
que el lint quede VERDE con el repo actual; cada entrada lleva su justificación.

Infra compartida (capa de datos del gateway + `keni-shared` + fachada de métricas)
NO es de ninguna app: `repos`, `marcas`, `redes`, `estados`, `seguridad`,
`observabilidad`, `lanzador`, `_http_json`, `db`, etc. no están en ningún manifest,
así que importarlas nunca cuenta como cruce (siempre permitido, seam #6).

La COLA DE JOBS `generaciones` (encolar `claude -p` en segundo plano + leer estado) es
esa misma categoría de infra transversal, pero como SÍ es un router (`api/generaciones.py`
con RUTAS) debe pertenecer a una unidad: vive en el SHELL (`shell.toml`). Importarla es
app→shell (siempre permitido), no un cruce — por eso sus consumidores (media,
parrilla_import, publicaciones, sugerencias) ya no necesitan entrada en la allowlist.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

from keni_consola import api
from keni_consola.apps import registro

# --------------------------------------------------------------------------- #
# ALLOWLIST de seams (ADR 0005). Cada par (router_origen, modulo_destino)         #
# es un cruce de frontera EXPLÍCITAMENTE permitido. Mantener mínima y comentada.  #
# --------------------------------------------------------------------------- #
SEAMS_PERMITIDOS: frozenset[tuple[str, str]] = frozenset(
    {
        # Seam #1 (A→C handoff de borrador): una generación de copy deposita un
        # *borrador* en `piezas` (C) por la función-CONTRATO
        # `dominio.piezas.crear_borrador` (C garantiza el estado inicial `borrador`),
        # no por `repos.crear_pieza` ni por tablas internas de C. Tras retirar el
        # sistema de skills, el handoff lo realizan `dominio.copy` (post-procesado de copy) e
        # `api/historial.py` (guardar como publicación). El cruce vive en el dominio, no en
        # los routers, así que el lint no lo dispara; el seam de `historial` SÍ se ve abajo.
        # `api/historial.py` (A, NEUTRO) hereda ese mismo seam: "guardar como publicación"
        # deposita borradores por el contrato `dominio.piezas.crear_borrador` (vía
        # `dominio.copy.crear_publicaciones_desde_piezas` o directo). Es el handoff A→C de
        # siempre, ahora desde el módulo de historial (al retirar el sistema de skills).
        ("historial", "piezas"),
        # Seam (produccion lee la agenda de C): el panel "Producción del día"
        # (`api/produccion.py`) muestra la cola de programación con el PRÓXIMO HUECO por
        # red, y ese cálculo (franjas + ocupados) vive en
        # `api.piezas.calcular_hueco_para` — la MISMA función del encolado manual y
        # de la auto-programación, a propósito: si el panel calculara sus huecos aparte,
        # mentiría en cuanto divergieran. SOLO LECTURA (no muta nada de C).
        ("produccion", "piezas"),
        # Seam (shell lee señales de operación para el DOCTOR de salud): `api/estado.py`
        # (shell) absorbió los chequeos del banner (cola, presupuesto, daemons, disco…) y
        # para el de la COLA lee el snapshot de `api.actividad` (produccion) — SOLO LECTURA,
        # mismo patrón que "produccion lee la agenda de C". El health-check es transversal:
        # le importa a todo el equipo, no a una app. (ADR 0005.)
        ("estado", "actividad"),
        # Seam (config de marca dispara un efecto en la cadena de aprobación): BAJAR el umbral
        # de likes de una marca en `api/marcas.py` (shell) resetea los OK humanos de sus piezas
        # EN REVISIÓN para que no se auto-programen bajo el nuevo umbral. Ese reseteo lee y
        # vuelve a `pendiente` los niveles de la cadena, primitivas de `dominio.colaboracion`
        # (operación: `contar_aprobaciones_humanas`, `es_nivel_critica_ia`, `DECISOR_AUTO_ID`,
        # `CAMPOS_NIVEL_PENDIENTE`). Es el efecto INTRÍNSECO de cambiar el umbral, no acoplamiento
        # arbitrario; acotado a ese único disparo. (ADR 0005.)
        ("marcas", "colaboracion"),
        # NOTA — seams RETIRADOS de la allowlist (cola-jobs-infra / T1.1 / T1.2 / borra-panel):
        #   ("media"|"parrilla_import"|"publicaciones"|"sugerencias", "generaciones")
        #       [cola-jobs-infra]: `generaciones` (la cola de jobs) se reclasificó de módulo
        #       de A a INFRA TRANSVERSAL del shell (shell.toml). Importarla pasó a ser
        #       app→shell (siempre permitido), así que estos 4 cruces dejaron de existir y
        #       sus entradas salieron de la allowlist. Era el síntoma clásico de frontera mal
        #       cortada: 4 seams al MISMO destino. (ADR 0005.)
        #   ("reciclaje", "piezas")  [T1.1]: `reciclaje` (A) ya NO lee el almacén
        #       de C en su router; pide el universo a la función-contrato de lectura de C
        #       `dominio.piezas.listar_para_reciclaje` a través de su propio
        #       `dominio.reciclaje`. El router quedó limpio: no hay cruce de frontera que
        #       permitir. (Era una entrada documental/precautoria; el seam sigue siendo
        #       legítimo pero ya no necesita allowlist porque no toca el router.)
        #   ("panel", "metricas")  [T1.2]: el panel leía B por la FACHADA
        #       `keni_metricas.servicio` (infra de solo lectura, ADR 0005), no
        #       por el router/internals de `metricas`. Nunca fue un cruce app↔app real;
        #       era una entrada documental.
        #   ("panel", "piezas") [borra-panel]: se retiró el dashboard `/api/panel`
        #       y su router `api/panel.py`; ya no existe el cruce shell→C.
    }
)

# Las tres apps de PRODUCTO (frente al shell, que es base transversal).
APPS_PRODUCTO = frozenset({"produccion", "metricas", "operacion"})

_RAIZ_API = Path(api.__file__).parent


def _routers() -> dict[str, str]:
    """Routers (módulos `api/<X>.py` con `RUTAS`) -> id de su unidad (app o shell).

    Solo los módulos que exportan `RUTAS` son routers; los helpers de `api/` (sin
    `RUTAS`) se ignoran (no se les asigna app). Un router fuera de todo manifest cae
    a "shell" SOLO para clasificar sus cruces; que exista es un fallo aparte
    (`test_cada_router_mapea_a_una_unica_app` + el invariante de `api.descubrir`).
    """
    mapa_modulos = registro.modulo_a_app()
    routers: dict[str, str] = {}
    for info in pkgutil.iter_modules(api.__path__):
        if info.name.startswith("_"):
            continue
        try:
            modulo = importlib.import_module(f"{api.__name__}.{info.name}")
        except ImportError:
            # Carrera xdist: otro worker pudo crear/borrar un módulo temporal en `api/`
            # (ver test_app) entre el listado y el import. Lo saltamos en vez de petar.
            continue
        if getattr(modulo, "RUTAS", None) is None:
            continue  # helper, no es router
        routers[info.name] = mapa_modulos.get(info.name, "shell")
    return routers


def _fuentes_router(nombre: str) -> list[Path]:
    """Ficheros fuente de un router (módulo de un fichero o PAQUETE).

    Un router es `api/<X>.py` o, tras partir un router grande en submódulos, un
    PAQUETE `api/<X>/` con `RUTAS` en su `__init__`. En el caso paquete escaneamos
    TODOS sus `.py` (p.ej. `_comun.py`) para no perder los cruces de frontera que
    se mudaron a submódulos: si solo miráramos `<X>.py`, el cruce dejaría de
    vigilarse al refactorizar el router a paquete.
    """
    fichero = _RAIZ_API / f"{nombre}.py"
    if fichero.is_file():
        return [fichero]
    paquete = _RAIZ_API / nombre
    if paquete.is_dir():
        return sorted(paquete.rglob("*.py"))
    return []


# Paquete raíz de la consola: los imports ABSOLUTOS que empiezan por él también son
# imports del propio paquete y cuentan para el lint (los de keni_shared, keni_metricas,
# starlette… nunca son módulos de una app).
_PAQUETE_RAIZ = "keni_consola"


def _resolver_partes(partes: list[str], nombres: list[str]) -> set[str]:
    """Resuelve un camino de módulo (ya RELATIVO a `keni_consola`) al módulo base `<Y>`.

    `partes` son los segmentos del módulo tras quitar el prefijo (`..` o `keni_consola.`);
    `nombres` son los símbolos importados (`import <Y>, <Z>`), que en las formas
    "paquete import submódulo" SON los módulos:
      - ["dominio", <Y>, ...] / ["api", <Y>, ...] -> {<Y>}
      - ["dominio"] / ["api"] + nombres           -> set(nombres)   (submódulos importados)
      - [<Y>, ...]                                -> {<Y>}
      - [] + nombres                              -> set(nombres)

    OJO con `from ..dominio import <Y>` (forma "paquete import submódulo"): el módulo
    cruzado es `<Y>` (un submódulo de `dominio/`), NO el paquete `dominio`. Resolverlo
    a `dominio` dejaba escapar cruces reales (p.ej. `from ..dominio import piezas`
    desde un router de otra app); por eso aquí los NOMBRES importados son los módulos.
    """
    if partes and partes[0] in ("dominio", "api"):
        if len(partes) >= 2:
            return {partes[1]}  # ..dominio.<Y> / keni_consola.api.<Y>
        return set(nombres)  # from ..dominio import <Y>, <Z>
    if partes:
        return {partes[0]}
    return set(nombres)  # `from .. import a, b` / `from keni_consola import a, b`


def _modulos_destino(node: ast.ImportFrom) -> set[str]:
    """Nombres de módulo base referenciados por un `from ... import ...`.

    Cubre los imports RELATIVOS (`from ..dominio.<Y>`, `from ..api import <Y>`, …) y los
    ABSOLUTOS dentro del paquete (`from keni_consola.dominio.<Y> import ...`), que
    resuelven a lo mismo. Los absolutos de OTROS paquetes (keni_shared, starlette…) se
    ignoran: nunca son módulos de una app.
    """
    mod = node.module or ""
    partes = mod.split(".") if mod else []
    nombres = [n.name for n in node.names]
    if node.level < 1:
        if not partes or partes[0] != _PAQUETE_RAIZ:
            return set()  # absoluto de otro paquete: nunca es de una app
        return _resolver_partes(partes[1:], nombres)
    return _resolver_partes(partes, nombres)


def _modulos_destino_import(node: ast.Import) -> set[str]:
    """Módulos base referenciados por un `import keni_consola.api.<Y>` (forma absoluta)."""
    destinos: set[str] = set()
    for alias in node.names:
        partes = alias.name.split(".")
        if partes[0] != _PAQUETE_RAIZ or len(partes) < 2:
            continue
        destinos |= _resolver_partes(partes[1:], [])
    return destinos


def _modulos_destino_importlib(node: ast.Call) -> set[str]:
    """Módulos base de un `importlib.import_module("keni_consola...")` con string LITERAL.

    Solo el primer argumento literal: un nombre construido dinámicamente no es resoluble
    por AST (y no es un patrón del repo). Acepta tanto `importlib.import_module(...)`
    como `import_module(...)` importado suelto.
    """
    func = node.func
    es_import_module = (
        isinstance(func, ast.Attribute) and func.attr == "import_module"
    ) or (isinstance(func, ast.Name) and func.id == "import_module")
    if not es_import_module or not node.args:
        return set()
    arg = node.args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        return set()
    partes = arg.value.split(".")
    if partes[0] != _PAQUETE_RAIZ or len(partes) < 2:
        return set()
    return _resolver_partes(partes[1:], [])


def _destinos_de_nodo(node: ast.AST, *, es_subpaquete: bool = False) -> set[str]:
    """Módulos base referenciados por un nodo AST cualquiera (o set() si no importa nada).

    Unifica las tres formas que vigila el lint: `from ... import` (relativo y absoluto),
    `import keni_consola...` y `importlib.import_module("keni_consola...")` literal. En un
    router-PAQUETE (`es_subpaquete`), los `from . import`/`from .sub import` de nivel 1 son
    hermanos del propio paquete (misma app) y no cuentan.
    """
    if isinstance(node, ast.ImportFrom):
        if es_subpaquete and node.level == 1:
            return set()
        return _modulos_destino(node)
    if isinstance(node, ast.Import):
        return _modulos_destino_import(node)
    if isinstance(node, ast.Call):
        return _modulos_destino_importlib(node)
    return set()


def _cruces() -> list[tuple[str, str, str, str]]:
    """Lista de cruces de frontera detectados: (router, app_origen, modulo, app_destino).

    Excluye:
      - imports de infra compartida (módulos que no pertenecen a ninguna unidad),
      - app → shell (siempre permitido: el shell es la base transversal).
    """
    mapa_modulos = registro.modulo_a_app()
    routers = _routers()
    cruces: list[tuple[str, str, str, str]] = []
    for nombre, app_origen in routers.items():
        for ruta in _fuentes_router(nombre):
            try:
                fuente = ruta.read_text(encoding="utf-8")
            except OSError:
                continue  # el fichero pudo desaparecer (carrera xdist con test_app)
            # Un router-PAQUETE (`api/<X>/...`) importa sus propios submódulos con
            # nivel 1 (`from .sub import` / `from . import sub`). Eso es intra-paquete
            # (misma app) y NO un cruce, aunque un submódulo se llame igual que un
            # módulo de otra app (p.ej. `contenido/metricas.py` ≠ la app `metricas`).
            # Los cruces reales escapan el paquete con nivel ≥ 2 (`from ..`, `from ...`).
            es_subpaquete = ruta.parent != _RAIZ_API
            arbol = ast.parse(fuente)
            for node in ast.walk(arbol):
                for destino in _destinos_de_nodo(node, es_subpaquete=es_subpaquete):
                    app_destino = mapa_modulos.get(destino)
                    if app_destino is None or app_destino == app_origen:
                        continue  # infra compartida o mismo dueño: permitido
                    # app -> shell: la base transversal, siempre permitido.
                    if app_destino == "shell":
                        continue
                    cruces.append((nombre, app_origen, destino, app_destino))
    return cruces


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #


def test_cada_router_mapea_a_una_unica_app():
    """Todo router (`api/<X>.py` con RUTAS) pertenece a EXACTAMENTE una unidad."""
    mapa = registro.modulo_a_app()
    routers = _routers()
    sin_unidad = [n for n in routers if n not in mapa]
    assert not sin_unidad, (
        f"Routers sin app declarada en ningún manifest: {sin_unidad}. "
        "Añádelos a su `apps/<app>.toml` (modulos_backend)."
    )


def test_fronteras_apps_sin_cruces_fuera_de_allowlist():
    """NINGÚN router cruza a otra app salvo por un seam de la allowlist (ADR 0005).

    Verde con el repo de HOY: los cruces reales están en `SEAMS_PERMITIDOS`.
    """
    cruces = _cruces()
    violaciones = [
        (origen, app_o, dest, app_d)
        for (origen, app_o, dest, app_d) in cruces
        if (origen, dest) not in SEAMS_PERMITIDOS
    ]
    assert not violaciones, (
        "Cruces de frontera entre apps FUERA de la allowlist (ADR 0005):\n"
        + "\n".join(
            f"  - api/{o}.py ({ao}) importa internals de '{d}' ({ad})"
            for (o, ao, d, ad) in violaciones
        )
        + "\nResuélvelo por contrato del gateway / keni-shared, o (si es un seam "
        "legítimo) añádelo a SEAMS_PERMITIDOS con su justificación."
    )


def test_allowlist_no_tiene_seams_muertos():
    """Higiene: cada entrada de la allowlist o dispara HOY o es un seam declarado.

    Distinguimos dos clases de entradas:
      - las que el lint detecta como cruce real HOY (import directo),
      - las DOCUMENTALES (el cruce va por la capa compartida y no dispara el lint).
    Aquí solo comprobamos que ninguna entrada apunta a un par imposible (módulos que
    no existen), para que la allowlist no acumule basura.
    """
    mapa = registro.modulo_a_app()
    routers = _routers()
    for origen, destino in SEAMS_PERMITIDOS:
        # El origen debe ser un módulo de api/ conocido: un fichero (`api/<X>.py`,
        # router o helper como historial) o un PAQUETE (`api/<X>/`, router partido
        # en submódulos).
        existe_origen = (_RAIZ_API / f"{origen}.py").is_file() or (
            _RAIZ_API / origen
        ).is_dir()
        assert existe_origen, f"Seam con origen inexistente en api/: {origen}"
        assert destino in mapa, f"Seam con destino que no es de ninguna app: {destino}"


def test_el_lint_detecta_una_violacion_sintetica():
    """PRUEBA de que el lint MUERDE: una violación inventada DEBE ser detectada.

    Simulamos que `api/metricas.py` (B) importa `from ..dominio.piezas import x`
    (internals de C) y comprobamos que el clasificador lo marca como cruce prohibido
    fuera de la allowlist. No tocamos ningún fichero del repo: parseamos un fragmento.
    """
    mapa = registro.modulo_a_app()
    assert mapa.get("metricas") == "metricas"
    assert mapa.get("piezas") == "operacion"

    # TODAS las formas de import deben resolverse a `piezas`: las relativas (dotada y
    # "paquete import submódulo") Y las absolutas (`from keni_consola...`, `import
    # keni_consola...`, `importlib.import_module("keni_consola...")` literal).
    for fragmento in (
        "from ..dominio.piezas import pieza_a_dict\n",
        "from ..dominio import piezas\n",
        "from keni_consola.dominio.piezas import pieza_a_dict\n",
        "from keni_consola.dominio import piezas\n",
        "import keni_consola.dominio.piezas\n",
        "import importlib\nimportlib.import_module('keni_consola.dominio.piezas')\n",
        "from importlib import import_module\nimport_module('keni_consola.dominio.piezas')\n",
    ):
        arbol = ast.parse(fragmento)
        destinos: set[str] = set()
        for node in ast.walk(arbol):
            destinos |= _destinos_de_nodo(node)
        assert "piezas" in destinos, (
            f"el resolver no detectó el módulo importado en: {fragmento!r}"
        )
    # Y los absolutos de OTROS paquetes siguen sin contar (nunca son de una app).
    for fragmento in (
        "from keni_shared.marcas import opciones\n",
        "import starlette.routing\n",
        "importlib.import_module('keni_shared.marcas')\n",
    ):
        arbol = ast.parse(fragmento)
        for node in ast.walk(arbol):
            assert not _destinos_de_nodo(node), f"falso positivo en: {fragmento!r}"

    app_origen = "metricas"
    cruce_prohibido = any(
        mapa.get(d) not in (None, app_origen, "shell") for d in destinos
    )
    assert cruce_prohibido, "el lint NO detectó el cruce B->C (debería)"
    # Y, como (metricas, piezas) NO está en la allowlist, sería una violación.
    assert ("metricas", "piezas") not in SEAMS_PERMITIDOS

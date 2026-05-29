"""Lint de FRONTERAS entre apps (ADR 0002 Fase A · ADR 0005 §Seams · plan §1.4).

Regla de oro (ADR 0002): un módulo de una app NUNCA importa los internals de otra
app. Las apps de producto (A·Producción, B·Métricas, C·Operación) se comunican por
contratos del gateway / `keni-shared`, no importando las tripas unas de otras.

Cómo lo verifica este test, SIN red ni BD (AST puro):
  1. Mapea cada ROUTER (`api/<X>.py` que exporta `RUTAS`) a su app/unidad vía los
     manifests (`apps/<app>.toml`), usando `registro.modulo_a_app()`.
  2. Parsea los imports relativos de cada router y los resuelve al módulo "dueño":
     `from ..dominio.<Y>`, `from ..api.<Y>`, `from .. import <Y>` y `from ..<Y>`
     apuntan al módulo base `<Y>`; si `<Y>` es un módulo declarado por OTRA unidad,
     es un cruce de frontera.
  3. CLASIFICA el cruce:
       - app → SHELL  : SIEMPRE permitido. El shell es la capa transversal/base que
                        ofrece servicios a A/B/C (auth, config, media, secretos…),
                        análoga a `keni-shared`. (ADR 0005 §Shell / seams #4,#5,#6.)
       - app ↔ app    : PROHIBIDO salvo seam explícito (A↔B↔C).
       - shell → app  : PROHIBIDO salvo seam explícito (el shell no debe acoplarse a
                        las tripas de una app salvo los cruces documentados).
  4. FALLA si hay un cruce prohibido fuera de la ALLOWLIST.

La ALLOWLIST codifica los seams de ADR 0005 §Seams (cruces legítimos de HOY) para
que el lint quede VERDE con el repo actual; cada entrada lleva su justificación.

Infra compartida (capa de datos del gateway + `keni-shared` + fachada de métricas)
NO es de ninguna app: `repos`, `marcas`, `redes`, `estados`, `seguridad`,
`observabilidad`, `lanzador`, `_http_json`, `db`, etc. no están en ningún manifest,
así que importarlas nunca cuenta como cruce (siempre permitido, seam #6).
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

from keni_consola import api
from keni_consola.apps import registro

# --------------------------------------------------------------------------- #
# ALLOWLIST de seams (ADR 0005 §Seams). Cada par (router_origen, modulo_destino)  #
# es un cruce de frontera EXPLÍCITAMENTE permitido. Mantener mínima y comentada.  #
# --------------------------------------------------------------------------- #
SEAMS_PERMITIDOS: frozenset[tuple[str, str]] = frozenset(
    {
        # Seam #4 (media shell consumida por A/C): `api/media.py` expone la
        # generación de imagen como TRABAJO en segundo plano y para ello usa la
        # infraestructura de jobs `generaciones` (de A). Es el único acoplamiento
        # shell→app de hoy; queda explícito aquí. T-futura puede moverlo tras la
        # fachada de jobs del gateway. (ADR 0005 §Seams #4.)
        ("media", "generaciones"),
        # Seam #1 (A→C handoff de borrador): una generación de copy puede crear un
        # *borrador* en `publicaciones` (C). HOY el helper `api/skills.py` (sin
        # RUTAS, no es router) usa `dominio.publicaciones`; lo dejamos declarado por
        # si un router de A lo tocara. (ADR 0005 §Seams #1; lo formaliza T1.3.)
        ("skills", "publicaciones"),
        ("skills_generacion_api", "publicaciones"),
        # Seam #2 (`reciclaje` A lee `publicaciones` C): hoy reciclaje lee las
        # publicaciones vía la capa compartida `repos` (no import directo de C), así
        # que no dispara el lint; se declara igualmente para dejar el seam visible.
        # T1.1 lo saneará a un contrato de lectura explícito. (ADR 0005 §Seams #2.)
        ("reciclaje", "publicaciones"),
        # Seam #3 (`panel` shell lee métricas B + cola C): panel agrega por las
        # fachadas de solo-lectura, no por internals; hoy no dispara el lint (usa
        # `repos`/`keni_metricas.servicio`). Declarado para dejarlo visible.
        # (ADR 0005 §Seams #3; lo formaliza T1.2.)
        ("panel", "metricas"),
        ("panel", "publicaciones"),
    }
)

# Las tres apps de PRODUCTO (frente al shell, que es base transversal).
APPS_PRODUCTO = frozenset({"produccion", "metricas", "operacion"})

_RAIZ_API = Path(api.__file__).parent


def _routers() -> dict[str, str]:
    """Routers (módulos `api/<X>.py` con `RUTAS`) -> id de su unidad (app o shell).

    Solo los módulos que exportan `RUTAS` son routers; los helpers de `api/` (sin
    `RUTAS`) se ignoran (no se les asigna app). `api/catalogo.py` es del shell pero
    no figura en un manifest: se trata como shell para no marcarlo huérfano.
    """
    mapa_modulos = registro.modulo_a_app()
    routers: dict[str, str] = {}
    for info in pkgutil.iter_modules(api.__path__):
        if info.name.startswith("_"):
            continue
        modulo = importlib.import_module(f"{api.__name__}.{info.name}")
        if getattr(modulo, "RUTAS", None) is None:
            continue  # helper, no es router
        # `catalogo` es del shell (lo sirve el shell) aunque no esté en un manifest.
        routers[info.name] = mapa_modulos.get(info.name, "shell")
    return routers


def _modulos_destino(node: ast.ImportFrom) -> set[str]:
    """Devuelve los nombres de módulo base referenciados por un import relativo.

    Resuelve los patrones de import del repo a un nombre de módulo base `<Y>`:
      - `from ..dominio.<Y> import ...`  -> {<Y>}
      - `from ..api.<Y> import ...`      -> {<Y>}
      - `from ..<Y> import ...`          -> {<Y>}
      - `from .. import <Y>, <Z>`        -> {<Y>, <Z>}
    Los imports absolutos (keni_shared, keni_metricas, starlette…) se ignoran: no son
    relativos a `keni_consola`, por tanto nunca son módulos de una app.
    """
    if node.level < 1:
        return set()  # import absoluto: fuera del paquete, nunca es de una app
    mod = node.module or ""
    partes = mod.split(".") if mod else []
    if partes and partes[0] in ("dominio", "api") and len(partes) >= 2:
        return {partes[1]}
    if partes:
        return {partes[0]}
    # `from .. import a, b` (sin módulo): los nombres SON los módulos.
    return {n.name for n in node.names}


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
        ruta = _RAIZ_API / f"{nombre}.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for node in ast.walk(arbol):
            if not isinstance(node, ast.ImportFrom):
                continue
            for destino in _modulos_destino(node):
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
    sin_unidad = [
        n for n, u in routers.items() if n != "catalogo" and n not in mapa
    ]
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
        "Cruces de frontera entre apps FUERA de la allowlist (ADR 0005 §Seams):\n"
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
        # El origen debe ser un módulo de api/ conocido (router o helper como skills).
        existe_origen = (_RAIZ_API / f"{origen}.py").is_file()
        assert existe_origen, f"Seam con origen inexistente en api/: {origen}"
        assert destino in mapa, f"Seam con destino que no es de ninguna app: {destino}"


def test_el_lint_detecta_una_violacion_sintetica():
    """PRUEBA de que el lint MUERDE: una violación inventada DEBE ser detectada.

    Simulamos que `api/metricas.py` (B) importa `from ..dominio.publicaciones import x`
    (internals de C) y comprobamos que el clasificador lo marca como cruce prohibido
    fuera de la allowlist. No tocamos ningún fichero del repo: parseamos un fragmento.
    """
    mapa = registro.modulo_a_app()
    assert mapa.get("metricas") == "metricas"
    assert mapa.get("publicaciones") == "operacion"

    fragmento = "from ..dominio.publicaciones import publicacion_a_dict\n"
    arbol = ast.parse(fragmento)
    node = next(n for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom))
    destinos = _modulos_destino(node)
    assert "publicaciones" in destinos, "el resolver no detectó el módulo importado"

    app_origen = "metricas"
    cruce_prohibido = any(
        mapa.get(d) not in (None, app_origen, "shell") for d in destinos
    )
    assert cruce_prohibido, "el lint NO detectó el cruce B->C (debería)"
    # Y, como (metricas, publicaciones) NO está en la allowlist, sería una violación.
    assert ("metricas", "publicaciones") not in SEAMS_PERMITIDOS

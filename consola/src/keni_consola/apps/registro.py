"""Cargador del catálogo de apps (ADR 0005 + ADR 0002).

Parsea los manifests TOML (`apps/<app>.toml`) y expone:
  - `cargar_apps()`        -> lista de `App` (todas las declaradas, ordenadas).
  - `apps_activas()`       -> solo las apps de catálogo (`es_app=True`) cuyo flag
                              de activación está ON (defaults: todas activas).
  - `entradas_nav_activas()` -> entradas de navegación del sidebar, agrupadas por
                              bloque visual, SOLO de las unidades activas.
  - `modulo_a_app`         -> mapa `api/<modulo>` -> id de app (lo usa el lint).

CONTRATO de los manifests (un fichero por app, sin colisión entre tareas):
  id, etiqueta, icono (nombre de icono lucide como string), flag_activacion (env),
  permisos, modulos_backend (lista de `api/*`), rutas_frontend, y entradas `[[nav]]`
  con {ruta, etiqueta, icono, descripcion, grupo, grupo_orden, orden}. El Shell lleva
  `es_app=false`: NO figura como app de catálogo ni aporta entradas de nav (sus
  servicios cuelgan del dropdown del avatar); solo mapea sus módulos a la unidad
  "shell" para el lint.

ACTIVACIÓN por flag (env var nombrada en `flag_activacion`):
  - ausente o vacía  -> ACTIVA (todo activo por defecto).
  - "0"/"false"/"no"/"off" (case-insensitive) -> DESACTIVADA (se oculta del catálogo).
  - cualquier otro valor -> ACTIVA.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_DIR_MANIFESTS = Path(__file__).parent

# Valores (lower) que apagan una app. Cualquier otra cosa (incl. ausente/vacía) la deja ON.
_VALORES_OFF = frozenset({"0", "false", "no", "off"})

# Etiqueta humana de cada bloque del sidebar (encabezado visible). El sidebar agrupa por
# MOMENTO DEL FLUJO, no por dueño de app: `operacion` = checkpoints diarios (tablero,
# revisión); `contenido` = herramientas para crear/editar a mano (estudio,
# texto, plantillas); `datos` = entradas que alimentan o reflejan la automatización
# (investigación, analíticas, actividad). Un `grupo` sin etiqueta aquí cae a "" (bloque
# sin encabezado), así un manifest nuevo no rompe aunque estrene un bloque.
ETIQUETAS_BLOQUE: dict[str, str] = {
    "operacion": "Operación",
    # `equipo` = quién trabaja y cuándo: «Trabajo» (eventos/tareas y su cobertura, la demanda) +
    # «Calendario» (el horario de turnos, la capacidad). Va entre Operación y Contenido: es otra
    # clase de cosa que el flujo de contenido, así que se separa de él en su propio bloque.
    "equipo": "Equipo",
    "contenido": "Contenido",
    # `maquina` = la máquina de generación (dos cockpits + la Cola compartida): el motor
    # automático que convierte señales en contenido; se sitúa entre Contenido y Datos.
    "maquina": "Máquina",
    "datos": "Datos",
}


@dataclass(frozen=True)
class EntradaNav:
    """Una entrada del sidebar (un enlace). El bloque visual lo dan `grupo`/`grupo_orden`."""

    ruta: str
    etiqueta: str
    icono: str
    descripcion: str
    grupo: str
    grupo_orden: int
    orden: int


@dataclass(frozen=True)
class App:
    """Una unidad declarada por su manifest TOML.

    `es_app=False` (Shell) => no es una app de catálogo (no se activa/oculta como tal,
    no figura en la lista de apps), pero sus módulos y nav siguen contando.
    """

    id: str
    etiqueta: str
    icono: str
    descripcion: str
    flag_activacion: str
    permisos: tuple[str, ...]
    modulos_backend: tuple[str, ...]
    rutas_frontend: tuple[str, ...]
    nav: tuple[EntradaNav, ...]
    es_app: bool = True

    def activa(self, entorno: dict[str, str] | None = None) -> bool:
        """True si la app está activada según su flag de env (default ON)."""
        env = entorno if entorno is not None else os.environ
        valor = (env.get(self.flag_activacion) or "").strip().lower()
        return valor not in _VALORES_OFF


def _entrada_nav(d: dict) -> EntradaNav:
    return EntradaNav(
        ruta=str(d["ruta"]),
        etiqueta=str(d["etiqueta"]),
        icono=str(d["icono"]),
        descripcion=str(d.get("descripcion", "")),
        grupo=str(d.get("grupo", "")),
        grupo_orden=int(d.get("grupo_orden", 0)),
        orden=int(d.get("orden", 0)),
    )


def _parsear_manifest(ruta: Path) -> App:
    with ruta.open("rb") as fh:
        datos = tomllib.load(fh)
    nav = tuple(_entrada_nav(n) for n in datos.get("nav", []))
    return App(
        id=str(datos["id"]),
        etiqueta=str(datos["etiqueta"]),
        icono=str(datos["icono"]),
        descripcion=str(datos.get("descripcion", "")),
        flag_activacion=str(datos["flag_activacion"]),
        permisos=tuple(str(p) for p in datos.get("permisos", [])),
        modulos_backend=tuple(str(m) for m in datos.get("modulos_backend", [])),
        rutas_frontend=tuple(str(r) for r in datos.get("rutas_frontend", [])),
        nav=nav,
        es_app=bool(datos.get("es_app", True)),
    )


@lru_cache(maxsize=1)
def cargar_apps() -> tuple[App, ...]:
    """Carga y cachea TODOS los manifests (`apps/*.toml`), orden estable por id."""
    rutas = sorted(_DIR_MANIFESTS.glob("*.toml"), key=lambda p: p.name)
    return tuple(_parsear_manifest(r) for r in rutas)


def apps_activas(entorno: dict[str, str] | None = None) -> list[App]:
    """Apps de CATÁLOGO (es_app=True) activadas por su flag. Excluye el Shell."""
    return [a for a in cargar_apps() if a.es_app and a.activa(entorno)]


def unidades_activas(entorno: dict[str, str] | None = None) -> list[App]:
    """TODAS las unidades activas, incluido el Shell (para nav y test scoping)."""
    return [a for a in cargar_apps() if a.activa(entorno)]


def entradas_nav_activas(entorno: dict[str, str] | None = None) -> list[dict]:
    """Entradas de nav del sidebar, agrupadas por bloque visual, solo de unidades activas.

    Devuelve `[{etiqueta, items: [{ruta, etiqueta, icono, descripcion}, ...]}, ...]`,
    ordenado por bloque de flujo (`grupo_orden`) y, dentro de cada bloque, por `orden`.
    La `etiqueta` del bloque es su encabezado humano (`ETIQUETAS_BLOQUE`); un bloque sin
    etiqueta declarada va sin encabezado (""). El Shell no aporta entradas de nav.
    """
    # Recolecta todas las entradas de nav de las unidades activas.
    todas: list[EntradaNav] = []
    for unidad in unidades_activas(entorno):
        todas.extend(unidad.nav)

    # Agrupa por bloque visual (grupo, grupo_orden) y ordena dentro de cada bloque.
    bloques: dict[str, list[EntradaNav]] = {}
    orden_bloque: dict[str, int] = {}
    for e in todas:
        bloques.setdefault(e.grupo, []).append(e)
        orden_bloque[e.grupo] = e.grupo_orden

    salida: list[dict] = []
    for grupo in sorted(bloques, key=lambda g: (orden_bloque[g], g)):
        items = sorted(bloques[grupo], key=lambda e: (e.orden, e.ruta))
        salida.append(
            {
                # Encabezado humano del bloque de flujo (o "" si el grupo no lo declara).
                "etiqueta": ETIQUETAS_BLOQUE.get(grupo, ""),
                "items": [
                    {
                        "ruta": i.ruta,
                        "etiqueta": i.etiqueta,
                        "icono": i.icono,
                        "descripcion": i.descripcion,
                    }
                    for i in items
                ],
            }
        )
    return salida


@lru_cache(maxsize=1)
def modulo_a_app() -> dict[str, str]:
    """Mapa `api/<modulo>` -> id de unidad (app o "shell"). Lo usa el lint de fronteras.

    Falla de forma visible si un módulo aparece en dos manifests (un router pertenece a
    UNA sola unidad).
    """
    mapa: dict[str, str] = {}
    for app in cargar_apps():
        for modulo in app.modulos_backend:
            if modulo in mapa:
                raise ValueError(
                    f"El módulo de API '{modulo}' está declarado en dos apps "
                    f"('{mapa[modulo]}' y '{app.id}'); cada router pertenece a una sola."
                )
            mapa[modulo] = app.id
    return mapa


def catalogo(entorno: dict[str, str] | None = None) -> dict:
    """Payload del catálogo para `GET /api/catalogo`: apps activas + nav agrupada.

    JSON serializable. `apps` son SOLO las apps de catálogo activas (sin el Shell);
    `navegacion` agrupa la nav de esas apps por bloque de flujo (el Shell no aporta nav).
    """
    apps = [
        {
            "id": a.id,
            "etiqueta": a.etiqueta,
            "icono": a.icono,
            "descripcion": a.descripcion,
            "permisos": list(a.permisos),
            "rutas_frontend": list(a.rutas_frontend),
            # Nav de ESTA app (ordenada por grupo/orden, como el sidebar). El
            # launcher la usa para: (a) la ruta primaria de la tarjeta (primer
            # item) y (b) el sidebar con scope (solo los items de la app actual).
            "nav": [
                {
                    "ruta": i.ruta,
                    "etiqueta": i.etiqueta,
                    "icono": i.icono,
                    "descripcion": i.descripcion,
                    "grupo": i.grupo,
                    "grupo_orden": i.grupo_orden,
                    "orden": i.orden,
                }
                for i in sorted(
                    a.nav, key=lambda e: (e.grupo_orden, e.grupo, e.orden, e.ruta)
                )
            ],
        }
        for a in apps_activas(entorno)
    ]
    return {"apps": apps, "navegacion": entradas_nav_activas(entorno)}

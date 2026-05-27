"""Config local de "carpetas de proyecto" para la pestana Proyectos.

El archivo vive en `~/.config/keni-social/consola.toml` (o la ruta de la env var
`KENI_CONSOLA_CONFIG`, util para tests). Formato simple, una tabla `[[proyecto]]`
por carpeta:

    [[proyecto]]
    nombre = "AMX Contenido"
    ruta = "/Users/cm/proyectos/amx"

    [[proyecto]]
    nombre = "Keni Social"
    ruta = "~/proyectos/keni-social"

Cada `ruta` apunta a una carpeta del disco donde (idealmente) vive un `CLAUDE.md`
que la persona quiere ver/editar y desde la que quiere lanzar Claude Code.

SEGURIDAD: este archivo es la **allowlist**. La consola SOLO escribe `CLAUDE.md`
o lanza Claude Code en carpetas que esten declaradas aqui (comparando rutas ya
resueltas). Nunca se opera sobre una ruta arbitraria venida del navegador.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import rutas


class ConsolaConfigInvalida(ValueError):
    """El consola.toml existe pero no se puede leer/parsear (mensaje en espanol)."""


def ruta_config_consola() -> Path:
    """Ruta del consola.toml.

    `KENI_CONSOLA_CONFIG` la sobreescribe (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.dir_config()`): local
    `${XDG_CONFIG_HOME:-~/.config}/keni-social/consola.toml`, o bajo `KENI_DATA_DIR`.
    """
    if (p := os.environ.get("KENI_CONSOLA_CONFIG")):
        return Path(p).expanduser()
    return rutas.dir_config() / "consola.toml"


@dataclass(frozen=True)
class Proyecto:
    """Una carpeta de proyecto declarada en consola.toml.

    `id` es un identificador estable derivado de la ruta resuelta; el navegador
    lo usa para referirse al proyecto sin mandar rutas crudas de vuelta.
    """

    id: str
    nombre: str
    ruta: Path  # ruta resuelta (absoluta)

    @property
    def tiene_claude_md(self) -> bool:
        archivo = self.ruta / "CLAUDE.md"
        return archivo.is_file()

    @property
    def existe(self) -> bool:
        return self.ruta.is_dir()


def _id_de_ruta(ruta: Path) -> str:
    """Identificador estable y opaco para una ruta (no expone el path al cliente)."""
    import hashlib

    return hashlib.sha256(str(ruta).encode("utf-8")).hexdigest()[:12]


def crear_config_si_falta() -> Path:
    """Crea un consola.toml vacio (con comentario-guia) si aun no existe."""
    ruta = ruta_config_consola()
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        plantilla = (
            "# Carpetas de proyecto de la Consola Keni.\n"
            "# Una tabla [[proyecto]] por carpeta. Ejemplo:\n"
            "#\n"
            '# [[proyecto]]\n'
            '# nombre = "AMX Contenido"\n'
            '# ruta = "~/proyectos/amx"\n'
        )
        ruta.write_text(plantilla, encoding="utf-8")
    return ruta


def cargar_proyectos() -> list[Proyecto]:
    """Lee consola.toml y devuelve los proyectos (rutas ya resueltas).

    Crea el archivo si no existe (devuelve lista vacia). Lanza
    `ConsolaConfigInvalida` (en espanol) si el TOML esta mal formado o una entrada
    `[[proyecto]]` no es valida.
    """
    ruta = crear_config_si_falta()
    try:
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConsolaConfigInvalida(
            f"El consola.toml en {ruta} tiene un error de sintaxis TOML: {e}"
        ) from e
    except OSError as e:
        raise ConsolaConfigInvalida(f"No se pudo leer el consola.toml en {ruta}: {e}") from e

    crudos = datos.get("proyecto", [])
    if not isinstance(crudos, list):
        raise ConsolaConfigInvalida(
            "El campo 'proyecto' del consola.toml debe ser una lista de tablas [[proyecto]]."
        )

    proyectos: list[Proyecto] = []
    vistos: set[Path] = set()
    for i, c in enumerate(crudos):
        n = f"#{i + 1}"
        if not isinstance(c, dict):
            raise ConsolaConfigInvalida(f"El proyecto {n} no es una tabla [[proyecto]] valida.")
        nombre = c.get("nombre")
        ruta_cruda = c.get("ruta")
        if not (isinstance(nombre, str) and nombre.strip()):
            raise ConsolaConfigInvalida(f"El proyecto {n} no tiene un 'nombre' valido.")
        if not (isinstance(ruta_cruda, str) and ruta_cruda.strip()):
            raise ConsolaConfigInvalida(f"El proyecto {n} (nombre={nombre!r}) no tiene una 'ruta' valida.")
        ruta_res = Path(ruta_cruda).expanduser().resolve()
        if ruta_res in vistos:
            continue  # ruta duplicada: nos quedamos con la primera declaracion
        vistos.add(ruta_res)
        proyectos.append(Proyecto(id=_id_de_ruta(ruta_res), nombre=nombre.strip(), ruta=ruta_res))
    return proyectos


def proyecto_por_id(proyecto_id: str) -> Proyecto | None:
    """Busca un proyecto por su id estable (None si no esta en la allowlist)."""
    for p in cargar_proyectos():
        if p.id == proyecto_id:
            return p
    return None


def anadir_proyecto(nombre: str, ruta_cruda: str) -> Proyecto:
    """Anade una carpeta al consola.toml tras validarla.

    Valida que `nombre` no este vacio y que la ruta exista y sea un directorio.
    Lanza `ValueError` (en espanol) ante cualquier fallo. Si la carpeta ya estaba
    declarada, lo indica con un `ValueError` claro (no duplica).
    """
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del proyecto no puede estar vacio.")
    if not (ruta_cruda or "").strip():
        raise ValueError("La ruta del proyecto no puede estar vacia.")

    ruta = Path(ruta_cruda).expanduser().resolve()
    if not ruta.exists():
        raise ValueError(f"La ruta {ruta} no existe.")
    if not ruta.is_dir():
        raise ValueError(f"La ruta {ruta} no es una carpeta.")

    existentes = cargar_proyectos()
    if any(p.ruta == ruta for p in existentes):
        raise ValueError(f"La carpeta {ruta} ya esta anadida.")

    archivo = crear_config_si_falta()
    # Anadimos una nueva tabla [[proyecto]] al final del archivo. Escapamos las
    # comillas dobles del contenido para no romper el TOML (rutas/nombres con ").
    nombre_esc = nombre.replace("\\", "\\\\").replace('"', '\\"')
    ruta_esc = str(ruta).replace("\\", "\\\\").replace('"', '\\"')
    bloque = f'\n[[proyecto]]\nnombre = "{nombre_esc}"\nruta = "{ruta_esc}"\n'
    texto_actual = archivo.read_text(encoding="utf-8")
    if texto_actual and not texto_actual.endswith("\n"):
        texto_actual += "\n"
    archivo.write_text(texto_actual + bloque, encoding="utf-8")

    return Proyecto(id=_id_de_ruta(ruta), nombre=nombre, ruta=ruta)


def claude_md_de(proyecto: Proyecto) -> str:
    """Contenido del CLAUDE.md del proyecto, o cadena vacia si no existe."""
    archivo = proyecto.ruta / "CLAUDE.md"
    if archivo.is_file():
        return archivo.read_text(encoding="utf-8")
    return ""


def guardar_claude_md(proyecto: Proyecto, contenido: str) -> Path:
    """Escribe el CLAUDE.md DENTRO de la carpeta del proyecto (allowlist).

    El llamante DEBE haber resuelto `proyecto` desde la allowlist (consola.toml).
    Por defensa en profundidad volvemos a verificar que el destino cae dentro de
    la carpeta declarada antes de escribir.
    """
    destino = (proyecto.ruta / "CLAUDE.md").resolve()
    base = proyecto.ruta.resolve()
    if destino.parent != base:
        raise ValueError("Ruta de destino fuera de la carpeta del proyecto.")
    if not base.is_dir():
        raise ValueError(f"La carpeta del proyecto {base} ya no existe.")
    destino.write_text(contenido, encoding="utf-8")
    return destino

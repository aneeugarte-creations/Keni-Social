"""Dominio AGENTES de la Consola Keni: un agente = una marca = su carpeta.

La Ola 2a unifico el contenido por MARCA en `<KENI_CONSOLA_RAIZ>/<marca>/`
(publicaciones, plantillas, RSS, hashtags, franjas, historial). Este modulo da el
salto conceptual: cada MARCA del catalogo unico (`marcas.opciones()`) ES un agente,
y su carpeta es su espacio de trabajo. Un agente tiene:

  - `CLAUDE.md`              contexto principal del agente (su "memoria").
  - `contexto/<nombre>.md`   sub-contextos opcionales (apuntes adicionales).
  - `runs/<id>.yaml`         ejecuciones de un prompt en esa carpeta.

NO existe "crear agente" arbitrario: los agentes SON las marcas. Por eso toda
operacion parte de un `marca_id` que se valida contra el catalogo (`marcas.es_marca`);
nunca se aceptan rutas crudas del navegador. La carpeta (y un `CLAUDE.md` desde
plantilla por tipo, reutilizando `api.carpetas`) se crean ON-DEMAND si faltan.

LAYOUT (raiz = `KENI_CONSOLA_RAIZ`, def `~/keni-proyectos`; misma que `ficheros.py`):

    <raiz>/<marca>/
        CLAUDE.md
        contexto/<nombre>.md
        runs/<id>.yaml

SEGURIDAD: el `marca_id` se valida contra el catalogo; la carpeta del agente es
`<raiz>/<marca>` con la marca como UNICO componente (un id de catalogo, slug-guion,
sin separadores). La escritura de CLAUDE.md, sub-contextos y runs es DEFENSIVA: la
ruta resuelta debe caer DENTRO de la carpeta del agente (anti-traversal por
`is_relative_to`), los sub-contextos son SOLO `*.md` con el nombre saneado, y la
escritura es ATOMICA (tmp + os.replace) como en `ficheros.py`/`secretos.py`.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from . import ficheros, marcas

# --------------------------------------------------------------------------- #
# Plantilla de CLAUDE.md por marca (reutiliza las plantillas de api.carpetas)  #
# --------------------------------------------------------------------------- #

# Mapa marca_id -> id de plantilla de `api.carpetas`. Una marca sin entrada cae a
# la plantilla "general". Asi el CLAUDE.md inicial encaja con el tipo de la marca.
_PLANTILLA_POR_MARCA: dict[str, str] = {
    "unotv": "noticias",
    "claro-sports": "deportes",
    "claro-sports-golf": "deportes",
    "piso-15": "podcast",
    "fundacion": "social",
}
_PLANTILLA_DEF = "general"

# Sub-carpetas dentro de la carpeta del agente.
_DIR_CONTEXTO = "contexto"
_DIR_RUNS = "runs"

# Nombre de sub-contexto: base sin separadores/control, terminada en `.md`.
_RE_NOMBRE_CONTEXTO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 ._-]*[A-Za-z0-9])?$")

# Modos validos de un run.
MODOS_RUN: tuple[str, ...] = ("headless", "interactivo")


class AgenteInvalido(ValueError):
    """El `marca_id` no es una marca del catalogo (mensaje en espanol)."""


class NombreContextoInvalido(ValueError):
    """El nombre de sub-contexto no es valido o escaparia de `contexto/`."""


# --------------------------------------------------------------------------- #
# Localizacion de la carpeta del agente (on-demand, validada contra el catalogo)#
# --------------------------------------------------------------------------- #


def _render_claude_md(marca_id: str) -> str:
    """Renderiza el CLAUDE.md inicial del agente desde su plantilla por tipo.

    Import LOCAL de `api.carpetas` para no crear un ciclo (carpetas no importa este
    modulo, pero el dominio no debe depender del paquete `api` a nivel de modulo).
    """
    from .api import carpetas

    plantilla_id = _PLANTILLA_POR_MARCA.get(marca_id, _PLANTILLA_DEF)
    return carpetas.render_claude_md(plantilla_id, marcas.etiqueta_de(marca_id))


def carpeta_agente(marca_id: str, *, crear: bool = True) -> Path:
    """Carpeta `<raiz>/<marca>/` de un agente, validando la marca contra el catalogo.

    Si `crear` (defecto), crea la carpeta y un `CLAUDE.md` (desde la plantilla por
    tipo de la marca) ON-DEMAND si no existen. Lanza `AgenteInvalido` si `marca_id`
    no es una marca del catalogo. La carpeta es siempre `raiz/<marca_id>` con la
    marca como UNICO componente (id de catalogo, sin separadores): no hay traversal
    posible, pero verificamos por defensa en profundidad que cae dentro de la raiz.
    """
    if not isinstance(marca_id, str) or not marcas.es_marca(marca_id):
        raise AgenteInvalido("Agente (marca) no permitido o inexistente.")

    raiz = ficheros.raiz_datos().resolve()
    carpeta = (raiz / marca_id).resolve()
    # Defensa en profundidad: la marca es un id de catalogo (sin `/`, `..`), pero
    # comprobamos igualmente que la carpeta queda DENTRO de la raiz.
    if carpeta == raiz or not carpeta.is_relative_to(raiz):
        raise AgenteInvalido("Agente (marca) no permitido o inexistente.")

    if crear:
        carpeta.mkdir(parents=True, exist_ok=True)
        claude = carpeta / "CLAUDE.md"
        if not claude.exists():
            claude.write_text(_render_claude_md(marca_id), encoding="utf-8")
    return carpeta


# --------------------------------------------------------------------------- #
# CLAUDE.md (contexto principal): lectura / escritura defensiva                #
# --------------------------------------------------------------------------- #


def leer_claude_md(marca_id: str) -> str:
    """Contenido del `CLAUDE.md` del agente (creandolo on-demand si falta)."""
    archivo = carpeta_agente(marca_id) / "CLAUDE.md"
    if archivo.is_file():
        return archivo.read_text(encoding="utf-8")
    return ""


def guardar_claude_md(marca_id: str, contenido: str) -> Path:
    """Escribe `<marca>/CLAUDE.md` de forma DEFENSIVA (dentro de la carpeta del agente)."""
    carpeta = carpeta_agente(marca_id)
    destino = (carpeta / "CLAUDE.md").resolve()
    if destino.parent != carpeta:
        raise ValueError("Ruta de destino fuera de la carpeta del agente.")
    _escribir_texto_atomico(destino, contenido)
    return destino


# --------------------------------------------------------------------------- #
# Sub-contextos: `*.md` dentro de `contexto/` (defensivo, anti-traversal)      #
# --------------------------------------------------------------------------- #


def _dir_contexto(marca_id: str) -> Path:
    """Sub-carpeta `contexto/` del agente (creada si falta)."""
    carpeta = carpeta_agente(marca_id) / _DIR_CONTEXTO
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _sanear_nombre_contexto(nombre: str) -> str:
    """Valida/normaliza el nombre de un sub-contexto y devuelve su nombre de fichero.

    Solo `*.md`: si no trae extension se le anade `.md`; si trae `.md` se respeta.
    El nombre BASE (sin extension) se valida contra `_RE_NOMBRE_CONTEXTO` (letras,
    digitos, espacio, `.`, `_`, `-`, sin empezar/acabar en separador) para impedir
    traversal (`/`, `\\`, `..`), rutas absolutas y caracteres de control. Lanza
    `NombreContextoInvalido` (en espanol) ante cualquier nombre no permitido.
    """
    crudo = (nombre or "").strip()
    if not crudo:
        raise NombreContextoInvalido("El nombre del contexto no puede estar vacío.")
    if crudo.lower().endswith(".md"):
        base = crudo[:-3]
    else:
        base = crudo
    base = base.strip()
    # Rechaza separadores de ruta, `..`, control y nombres que escaparian.
    if not base or base in (".", "..") or not _RE_NOMBRE_CONTEXTO.match(base):
        raise NombreContextoInvalido(
            "El nombre del contexto solo puede tener letras, dígitos, espacios, '.', '_' o '-'."
        )
    return f"{base}.md"


def _resolver_contexto(marca_id: str, nombre: str) -> Path:
    """Ruta de un sub-contexto DENTRO de `contexto/` (defensa anti-traversal)."""
    carpeta = _dir_contexto(marca_id)
    destino = (carpeta / _sanear_nombre_contexto(nombre)).resolve()
    base = carpeta.resolve()
    if destino.parent != base or not destino.is_relative_to(base):
        raise NombreContextoInvalido("El nombre del contexto saldría de la carpeta de contexto.")
    return destino


def listar_contextos(marca_id: str) -> list[dict[str, str]]:
    """Sub-contextos del agente: `[{nombre, contenido}]`, ordenados por nombre."""
    carpeta = carpeta_agente(marca_id) / _DIR_CONTEXTO
    if not carpeta.is_dir():
        return []
    salida: list[dict[str, str]] = []
    for ruta in sorted(carpeta.glob("*.md")):
        if not ruta.is_file():
            continue
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        salida.append({"nombre": ruta.name, "contenido": contenido})
    return salida


def guardar_contexto(marca_id: str, nombre: str, contenido: str) -> Path:
    """Escribe un sub-contexto `*.md` (saneado) DENTRO de `contexto/` (atomico)."""
    destino = _resolver_contexto(marca_id, nombre)
    _escribir_texto_atomico(destino, contenido)
    return destino


def borrar_contexto(marca_id: str, nombre: str) -> bool:
    """Borra un sub-contexto; True si existia, False si no. Saneado y defensivo."""
    destino = _resolver_contexto(marca_id, nombre)
    if not destino.is_file():
        return False
    destino.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------------- #
# Runs (ejecuciones de un prompt): `runs/<id>.yaml`                            #
# --------------------------------------------------------------------------- #


def _dir_runs(marca_id: str) -> Path:
    """Sub-carpeta `runs/` del agente (creada si falta)."""
    carpeta = carpeta_agente(marca_id) / _DIR_RUNS
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def nuevo_run_id() -> str:
    """Nuevo id de run (12 hex, mismo formato que `ficheros._nuevo_id`)."""
    return uuid.uuid4().hex[:12]


def ahora_iso() -> str:
    """Fecha-hora ISO a segundos (orden determinista de los runs)."""
    return datetime.now().isoformat(timespec="seconds")


def _parsear_run(datos: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Reconstruye el dict publico de un run (id implicito = nombre de fichero)."""
    return {
        "id": run_id,
        "prompt": datos.get("prompt", "") or "",
        "modo": datos.get("modo", "") or "",
        "estado": datos.get("estado", "") or "",
        "salida": datos.get("salida", "") or "",
        "fecha_inicio": datos.get("fecha_inicio", "") or "",
        "fecha_fin": datos.get("fecha_fin", "") or "",
    }


def guardar_run(marca_id: str, run: dict[str, Any]) -> dict[str, Any]:
    """Escribe `runs/<id>.yaml` (atomico) y devuelve el run con su `id`.

    Si el run no trae `id`, se genera uno. El cuerpo YAML no repite el `id` (es
    implicito por el nombre de fichero).
    """
    run_id = run.get("id") or nuevo_run_id()
    cuerpo = {
        "prompt": run.get("prompt", "") or "",
        "modo": run.get("modo", "") or "",
        "estado": run.get("estado", "") or "",
        "salida": run.get("salida", "") or "",
        "fecha_inicio": run.get("fecha_inicio", "") or "",
        "fecha_fin": run.get("fecha_fin", "") or "",
    }
    ruta = _dir_runs(marca_id) / f"{run_id}.yaml"
    _escribir_yaml_atomico(ruta, cuerpo)
    return {"id": run_id, **cuerpo}


def listar_runs(marca_id: str) -> list[dict[str, Any]]:
    """Runs del agente, recientes primero (por `fecha_inicio` desc, luego id)."""
    carpeta = carpeta_agente(marca_id) / _DIR_RUNS
    if not carpeta.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for ruta in carpeta.glob("*.yaml"):
        if ruta.name.startswith(".tmp-"):
            continue
        datos = _leer_yaml(ruta)
        if datos is None:
            continue
        runs.append(_parsear_run(datos, ruta.stem))
    runs.sort(key=lambda r: (r["fecha_inicio"], r["id"]), reverse=True)
    return runs


def obtener_run(marca_id: str, run_id: str) -> dict[str, Any] | None:
    """Un run del agente por id (None si no existe o su YAML no valida).

    El `run_id` se sanea (solo el `stem`) para impedir traversal por la ruta.
    """
    if not isinstance(run_id, str) or not run_id:
        return None
    # Solo el nombre base: descarta cualquier separador/`..` del id.
    seguro = Path(run_id).name
    if seguro != run_id or seguro in (".", ".."):
        return None
    ruta = (carpeta_agente(marca_id) / _DIR_RUNS / f"{seguro}.yaml").resolve()
    base = (carpeta_agente(marca_id) / _DIR_RUNS).resolve()
    if ruta.parent != base or not ruta.is_file():
        return None
    datos = _leer_yaml(ruta)
    if datos is None:
        return None
    return _parsear_run(datos, seguro)


# --------------------------------------------------------------------------- #
# Resumen de un agente (para el listado / detalle)                            #
# --------------------------------------------------------------------------- #


def _contar(carpeta: Path, patron: str) -> int:
    """Cuenta ficheros que casan un glob dentro de `carpeta` (0 si no existe)."""
    if not carpeta.is_dir():
        return 0
    return sum(1 for _ in carpeta.glob(patron))


def resumen_agente(marca_id: str) -> dict[str, Any]:
    """Resumen ligero de un agente (NO crea la carpeta si aun no existe).

    Cuenta publicaciones y runs leyendo el disco; reporta si el `CLAUDE.md` existe.
    No siembra nada (`crear=False`) para que el LISTADO no materialice carpetas.
    """
    carpeta = carpeta_agente(marca_id, crear=False)
    n_pub = _contar(carpeta / "publicaciones", "*.yaml")
    n_runs = _contar(carpeta / _DIR_RUNS, "*.yaml")
    return {
        "id": marca_id,
        "nombre": marcas.etiqueta_de(marca_id),
        "ruta": str(carpeta),
        "tiene_claude_md": (carpeta / "CLAUDE.md").is_file(),
        "n_publicaciones": n_pub,
        "n_runs": n_runs,
    }


def listar_agentes() -> list[dict[str, Any]]:
    """Todos los agentes = todas las marcas del catalogo (orden de presentacion)."""
    return [resumen_agente(mid) for mid, _etiqueta in marcas.opciones()]


# --------------------------------------------------------------------------- #
# Escritura atomica (mismo patron que ficheros.py / secretos.py)              #
# --------------------------------------------------------------------------- #


def _escribir_texto_atomico(ruta: Path, contenido: str) -> None:
    """Escribe texto en `ruta` de forma ATOMICA (tmp en el mismo dir + os.replace)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_nombre = tempfile.mkstemp(dir=str(ruta.parent), prefix=".tmp-", suffix=ruta.suffix)
    tmp = Path(tmp_nombre)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(contenido)
        os.replace(tmp, ruta)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _escribir_yaml_atomico(ruta: Path, datos: dict[str, Any]) -> None:
    """Escribe un dict como YAML legible de forma ATOMICA (tmp + os.replace)."""
    texto = yaml.safe_dump(
        datos, default_flow_style=False, allow_unicode=True, sort_keys=False, width=4096
    )
    _escribir_texto_atomico(ruta, texto)


def _leer_yaml(ruta: Path) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return datos

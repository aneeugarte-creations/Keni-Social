"""Preferencias LOCALES de la Consola Keni (ajustes no secretos del equipo).

Hoy guarda una sola cosa: el NIVEL DE ESFUERZO de razonamiento que se pasa a
`claude` (`--effort`) al GENERAR con IA (copy, RSS, hashtags y agentes). Un
esfuerzo mas alto «piensa» mas (mejor calidad, mas lento/caro); uno mas bajo
responde antes. El valor vacio ("") significa «usa el predeterminado del modelo»
y NO se pasa `--effort` (no cambia el comportamiento actual).

El archivo vive en `~/.config/keni-social/preferencias.toml` (o la ruta de
`KENI_CONSOLA_PREFERENCIAS`, util en tests). Escritura ATOMICA (temp + os.replace),
mismo patron defensivo que `secretos.py`. NO contiene secretos.
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path

# Niveles validos de `claude --effort` (ver `claude --help`), de menor a mayor
# esfuerzo. La UI respeta este orden al pintar el selector.
ESFUERZOS_VALIDOS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

# Valor por defecto: vacio = «predeterminado del modelo» (no se pasa `--effort`).
ESFUERZO_DEFECTO = ""

# Sinonimos que tambien borran el ajuste (vuelven al predeterminado del modelo).
_ALIAS_DEFECTO = frozenset({"", "predeterminado", "default", "auto"})

_CABECERA = (
    "# Preferencias LOCALES de la Consola Keni. Las gestiona keni_consola.preferencias\n"
    "# (no editar a mano).\n"
)


def ruta_preferencias() -> Path:
    """Ruta del archivo de preferencias. `KENI_CONSOLA_PREFERENCIAS` la sobreescribe (tests)."""
    if (p := os.environ.get("KENI_CONSOLA_PREFERENCIAS")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "preferencias.toml"


# --------------------------------------------------------------------------- #
# Lectura / escritura del almacen                                             #
# --------------------------------------------------------------------------- #


def _leer() -> dict:
    """Lee el TOML de preferencias (o {} si no existe / esta corrupto). Solo lectura."""
    ruta = ruta_preferencias()
    if not ruta.exists():
        return {}
    try:
        return tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _serializar(datos: dict) -> str:
    """Serializa las preferencias a TOML (hoy solo la clave `esfuerzo`)."""
    esfuerzo = datos.get("esfuerzo")
    if isinstance(esfuerzo, str) and esfuerzo in ESFUERZOS_VALIDOS:
        return f'esfuerzo = "{esfuerzo}"\n'
    return ""


def _escribir(datos: dict) -> None:
    """Escribe las preferencias como TOML de forma atomica (temp + os.replace)."""
    ruta = ruta_preferencias()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = _CABECERA + _serializar(datos)

    fd, tmp_nombre = tempfile.mkstemp(
        dir=str(ruta.parent), prefix=".preferencias-", suffix=".toml.tmp"
    )
    tmp = Path(tmp_nombre)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(contenido)
        os.replace(tmp, ruta)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# API publica: nivel de esfuerzo                                              #
# --------------------------------------------------------------------------- #


def obtener_esfuerzo() -> str:
    """Nivel de esfuerzo guardado, o "" (predeterminado del modelo) si no hay/invalido."""
    valor = _leer().get("esfuerzo")
    if isinstance(valor, str) and valor in ESFUERZOS_VALIDOS:
        return valor
    return ESFUERZO_DEFECTO


def guardar_esfuerzo(nivel: str) -> str:
    """Guarda el nivel de esfuerzo (escritura atomica). Devuelve el nivel normalizado.

    `""` (o `predeterminado`/`default`/`auto`) BORRA el ajuste y vuelve al
    predeterminado del modelo. Lanza `ValueError` si el nivel no es valido.
    """
    nivel = (nivel or "").strip().lower()
    if nivel in _ALIAS_DEFECTO:
        datos = _leer()
        if "esfuerzo" in datos:
            datos.pop("esfuerzo", None)
            _escribir(datos)
        return ESFUERZO_DEFECTO
    if nivel not in ESFUERZOS_VALIDOS:
        raise ValueError(nivel)
    datos = _leer()
    datos["esfuerzo"] = nivel
    _escribir(datos)
    return nivel


def arg_esfuerzo() -> list[str]:
    """`['--effort', <nivel>]` si hay un nivel valido guardado; si no, `[]`.

    La consumen los constructores de argv de `claude` (generaciones y agentes).
    """
    nivel = obtener_esfuerzo()
    if nivel in ESFUERZOS_VALIDOS:
        return ["--effort", nivel]
    return []

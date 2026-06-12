"""Preferencias de la Consola Keni: el NIVEL DE ESFUERZO de la generacion.

Es el `--effort` que se pasa a `claude` al GENERAR con IA (copy, RSS, hashtags y
agentes). Un esfuerzo mas alto «piensa» mas (mejor calidad, mas lento/caro); uno
mas bajo responde antes. El valor vacio ("") significa «usa el predeterminado del
modelo» y NO se pasa `--effort`.

FUENTE DE VERDAD (consolidación): el ajuste `KENI_ESFUERZO` del catalogo de ajustes
(`ajustes_catalogo.py`, tipo select), con la precedencia habitual STORE > ENV. El
TOML local (`~/.config/keni-social/preferencias.toml` o `KENI_CONSOLA_PREFERENCIAS`)
queda SOLO como FALLBACK LEGADO de lectura: si nadie escribio aun el ajuste nuevo
(ni store ni env), se respeta lo que el equipo guardo antes aqui. `guardar_esfuerzo`
escribe ya en el store de ajustes (y retira la clave legada del TOML: migracion
definitiva al primer guardado). Escritura ATOMICA; NO contiene secretos.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from . import config, rutas
from .io_atomico import escribir_atomico

# Niveles validos de `claude --effort` (ver `claude --help`), de menor a mayor
# esfuerzo. La UI respeta este orden al pintar el selector.
ESFUERZOS_VALIDOS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

# Etiquetas humanas de cada nivel (incluido "" = predeterminado del modelo). Fuente
# UNICA para el catalogo de ajustes (select `KENI_ESFUERZO`) y el shim deprecado de
# `/api/config/esfuerzo`; el orden de pintado es ("", *ESFUERZOS_VALIDOS).
ESFUERZO_ETIQUETAS: dict[str, str] = {
    "": "Predeterminado",
    "low": "Bajo",
    "medium": "Medio",
    "high": "Alto",
    "xhigh": "Muy alto",
    "max": "Máximo",
}

# Valor por defecto: vacio = «predeterminado del modelo» (no se pasa `--effort`).
ESFUERZO_DEFECTO = ""

# Sinonimos que tambien borran el ajuste (vuelven al predeterminado del modelo).
_ALIAS_DEFECTO = frozenset({"", "predeterminado", "default", "auto"})

_CABECERA = (
    "# Preferencias LOCALES de la Consola Keni. Las gestiona keni_consola.preferencias\n"
    "# (no editar a mano).\n"
)


def ruta_preferencias() -> Path:
    """Ruta del archivo de preferencias.

    `KENI_CONSOLA_PREFERENCIAS` la sobreescribe (override de maxima prioridad; tests). Si
    no, cuelga de la raiz de estado unica (`rutas.dir_config()`): local
    `${XDG_CONFIG_HOME:-~/.config}/keni-social/preferencias.toml`, o bajo `KENI_DATA_DIR`.
    """
    if (p := config.override_ruta(config.ENV_PREFERENCIAS)) is not None:
        return p
    return rutas.dir_config() / "preferencias.toml"


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
    contenido = _CABECERA + _serializar(datos)
    escribir_atomico(
        ruta_preferencias(), contenido, prefijo=".preferencias-", sufijo=".toml.tmp"
    )


# --------------------------------------------------------------------------- #
# API publica: nivel de esfuerzo                                              #
# --------------------------------------------------------------------------- #


def obtener_esfuerzo() -> str:
    """Nivel de esfuerzo EFECTIVO, o "" (predeterminado del modelo) si no hay/invalido.

    Lee el ajuste `KENI_ESFUERZO` con la precedencia del catalogo (STORE > ENV) y cae al
    TOML LEGADO de preferencias solo si el ajuste nuevo no existe en ninguna de las dos
    (migracion suave: lo guardado con la UI vieja sigue valiendo hasta el primer guardado
    nuevo). OJO: un "" EXPLICITO en el store (el equipo eligio «Predeterminado» en la UI
    nueva) GANA al valor legado; por eso se distingue None (ausente) de "" (elegido).
    """
    from . import ajustes  # perezoso: mismo idiom que `config._crudo` (evita ciclos)

    desde_store = ajustes.obtener(config.ENV_ESFUERZO)
    if desde_store is not None:
        valor = desde_store.strip().lower()
        return valor if valor in ESFUERZOS_VALIDOS else ESFUERZO_DEFECTO
    desde_env = (os.environ.get(config.ENV_ESFUERZO) or "").strip().lower()
    if desde_env:
        return desde_env if desde_env in ESFUERZOS_VALIDOS else ESFUERZO_DEFECTO
    # FALLBACK LEGADO: el TOML local de preferencias (la UI vieja escribia aqui).
    valor = _leer().get("esfuerzo")
    if isinstance(valor, str) and valor in ESFUERZOS_VALIDOS:
        return valor
    return ESFUERZO_DEFECTO


def guardar_esfuerzo(nivel: str) -> str:
    """Guarda el nivel en el AJUSTE `KENI_ESFUERZO` (store editable). Devuelve el normalizado.

    `""` (o `predeterminado`/`default`/`auto`) guarda "" = predeterminado del modelo. Se
    PERSISTE el "" (no se borra la clave): un «Predeterminado» explicito debe ganar al
    valor legado del TOML y a una env var. Ademas RETIRA la clave legada del TOML local
    (migracion definitiva: el fallback deja de tener voz tras el primer guardado). Lanza
    `ValueError` si el nivel no es valido.
    """
    from . import ajustes  # perezoso: mismo idiom que `config._crudo` (evita ciclos)

    nivel = (nivel or "").strip().lower()
    if nivel in _ALIAS_DEFECTO:
        nivel = ESFUERZO_DEFECTO
    elif nivel not in ESFUERZOS_VALIDOS:
        raise ValueError(nivel)
    ajustes.guardar(config.ENV_ESFUERZO, nivel)
    datos = _leer()
    if "esfuerzo" in datos:
        datos.pop("esfuerzo", None)
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

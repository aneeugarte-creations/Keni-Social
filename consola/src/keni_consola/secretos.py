"""Almacen LOCAL de secretos de la Consola Keni (clave del proveedor de imagen IA).

El archivo vive en `~/.config/keni-social/secretos.toml` (o la ruta de
`KENI_CONSOLA_SECRETOS`, util en tests). Solo contiene la clave del proveedor de
imagen y el nombre del proveedor. Escritura ATOMICA con permisos `0600`
(temp + os.replace + os.chmod), mismo patron defensivo que el config de metricas.

SEGURIDAD MAXIMA:
  - El archivo se escribe siempre con permisos `0600` (solo el dueno lo lee).
  - La clave NUNCA se loguea ni se devuelve entera por la API. `estado_imagen()`
    solo reporta presencia y, como mucho, una PISTA con los ultimos 4 caracteres.
  - Los tokens de redes sociales NO viven aqui: esos los gestiona el config de
    metricas (`keni_metricas.asistente`), no este modulo.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .io_atomico import escribir_atomico

# Proveedor de imagen por defecto (no se cambia el motor: OpenAI gpt-image-1).
PROVEEDOR_DEFECTO = "openai"

# Cabecera del archivo de secretos (recordatorio de que NO se debe compartir).
_CABECERA = (
    "# Secretos LOCALES de la Consola Keni. NO compartas ni subas este archivo.\n"
    "# Permisos 0600; lo gestiona keni_consola.secretos (no editar a mano).\n"
)


def ruta_secretos() -> Path:
    """Ruta del archivo de secretos. `KENI_CONSOLA_SECRETOS` la sobreescribe (tests)."""
    if (p := os.environ.get("KENI_CONSOLA_SECRETOS")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "secretos.toml"


# --------------------------------------------------------------------------- #
# Lectura / escritura del almacen                                             #
# --------------------------------------------------------------------------- #


def _leer() -> dict:
    """Lee el TOML de secretos (o {} si no existe / esta corrupto). Solo lectura."""
    ruta = ruta_secretos()
    if not ruta.exists():
        return {}
    try:
        return tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _bloque_imagen(datos: dict) -> dict:
    """Devuelve el sub-dict `[imagen]` del config de secretos ({} si falta)."""
    bloque = datos.get("imagen")
    return bloque if isinstance(bloque, dict) else {}


def _escribir(datos: dict) -> None:
    """Escribe el dict de secretos como TOML de forma atomica con permisos `0600`.

    Mismo patron que `keni_metricas.asistente.escribir_config_atomico`: temporal en
    el mismo directorio + `os.chmod(0600)` + `os.replace` (sin archivo a medias).
    """
    contenido = _CABECERA + _serializar(datos)
    # modo=0o600: el fichero final nace con permisos de solo-dueno (contiene claves).
    escribir_atomico(
        ruta_secretos(), contenido, modo=0o600, prefijo=".secretos-", sufijo=".toml.tmp"
    )


def _toml_str(valor: str) -> str:
    """Escapa una cadena para un TOML basic string (comillas dobles)."""
    escapado = (
        valor.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escapado}"'


def _serializar(datos: dict) -> str:
    """Serializa el bloque `[imagen]` a TOML (estructura fija: proveedor + api_key)."""
    bloque = _bloque_imagen(datos)
    if not bloque:
        return ""
    lineas = ["[imagen]"]
    for clave in ("proveedor", "api_key"):
        valor = bloque.get(clave)
        if isinstance(valor, str) and valor:
            lineas.append(f"{clave} = {_toml_str(valor)}")
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------- #
# API publica: clave del proveedor de imagen                                  #
# --------------------------------------------------------------------------- #


def guardar_clave_imagen(proveedor: str, api_key: str) -> None:
    """Guarda la clave del proveedor de imagen (escritura atomica, permisos `0600`).

    `proveedor` se normaliza (minusculas, sin espacios); si viene vacio se usa el
    proveedor por defecto. `api_key` se guarda tal cual (sin loguearla nunca).
    """
    proveedor = (proveedor or "").strip().lower() or PROVEEDOR_DEFECTO
    api_key = (api_key or "").strip()
    datos = _leer()
    datos["imagen"] = {"proveedor": proveedor, "api_key": api_key}
    _escribir(datos)


def borrar_clave_imagen() -> None:
    """Borra la clave del proveedor de imagen (deja el almacen sin bloque `[imagen]`)."""
    datos = _leer()
    if "imagen" in datos:
        datos.pop("imagen", None)
        _escribir(datos)


def obtener_clave_imagen() -> str | None:
    """Devuelve la clave guardada del proveedor de imagen, o None si no hay.

    Uso INTERNO (la consume `media.py`). NUNCA se expone por la API ni se loguea.
    """
    clave = _bloque_imagen(_leer()).get("api_key")
    if isinstance(clave, str) and clave.strip():
        return clave
    return None


def obtener_proveedor_imagen() -> str:
    """Devuelve el proveedor de imagen configurado (def. `openai`)."""
    proveedor = _bloque_imagen(_leer()).get("proveedor")
    if isinstance(proveedor, str) and proveedor.strip():
        return proveedor.strip().lower()
    return PROVEEDOR_DEFECTO


def _pista(clave: str | None) -> str:
    """Pista NO sensible de la clave: `····` + ultimos 4 chars (o "" si no hay)."""
    if not clave:
        return ""
    return "····" + clave[-4:]


def estado_imagen() -> dict:
    """Estado del proveedor de imagen, SIN exponer la clave.

    Devuelve `{proveedor, configurado, pista}` donde `pista` son `····` + los
    ultimos 4 caracteres de la clave (o "" si no hay clave configurada).
    """
    clave = obtener_clave_imagen()
    return {
        "proveedor": obtener_proveedor_imagen(),
        "configurado": clave is not None,
        "pista": _pista(clave),
    }

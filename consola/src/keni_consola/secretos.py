"""Almacen LOCAL de secretos de la Consola Keni (clave del proveedor de imagen IA).

El archivo cuelga de la raiz de estado unica (`rutas.dir_config()`): local
`${XDG_CONFIG_HOME:-~/.config}/keni-social/secretos.toml`, o `<KENI_DATA_DIR>/
keni-social/secretos.toml` en contenedor. `KENI_CONSOLA_SECRETOS` lo sobreescribe
(override de maxima prioridad; util en tests). Contiene la clave del proveedor de
imagen, el nombre del proveedor y, opcionalmente, el modelo de imagen elegido por la
UI. Escritura ATOMICA con permisos `0600`
(temp + os.replace + os.chmod), mismo patron defensivo que el config de metricas.

SECRETOS POR ENTORNO (servicio en contenedor): ademas del fichero, la clave del
proveedor de imagen se puede INYECTAR por variable de entorno, util cuando el secreto lo
gestiona el orquestador (Compose/CI) y no hay un fichero `0600` persistente. Variables
leidas (en este orden de precedencia para la clave):
  - `KENI_IMAGEN_API_KEY`  clave del proveedor de imagen (cualquier proveedor).
  - `OPENROUTER_API_KEY`   clave de OpenRouter (gateway de IA por defecto).
  - `OPENAI_API_KEY`       fallback historico.
  - el fichero `secretos.toml` (almacen local persistente).
  - `KENI_IMAGEN_PROVEEDOR` nombre del proveedor de imagen por entorno (def. el del
                            fichero o `openrouter`).
El fichero gana al entorno SOLO si el fichero tiene clave; en contenedor sin fichero, el
entorno es la fuente. NO se degrada la seguridad del fichero (sigue naciendo `0600`).

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

from . import config, rutas
from .io_atomico import escribir_atomico

# Variables de entorno que pueden INYECTAR el secreto de imagen (ver docstring).
# Nombres canonicos en `config` (fuente unica); re-exportados aqui (tests los referencian).
ENV_IMAGEN_API_KEY = config.ENV_IMAGEN_API_KEY
ENV_IMAGEN_PROVEEDOR = config.ENV_IMAGEN_PROVEEDOR
# Clave de OpenRouter por entorno: gateway de IA por defecto.
ENV_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
# Fallback historico: clave de OpenAI por entorno.
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"

# Proveedor de imagen por defecto: OpenRouter (gateway unico compatible con OpenAI; el
# modelo concreto se elige por id, ver `media.py` / skill `estudio-imagen`).
PROVEEDOR_DEFECTO = "openrouter"

# Cabecera del archivo de secretos (recordatorio de que NO se debe compartir).
_CABECERA = (
    "# Secretos LOCALES de la Consola Keni. NO compartas ni subas este archivo.\n"
    "# Permisos 0600; lo gestiona keni_consola.secretos (no editar a mano).\n"
)


def ruta_secretos() -> Path:
    """Ruta del archivo de secretos.

    `KENI_CONSOLA_SECRETOS` la sobreescribe (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.dir_config()`): local
    `${XDG_CONFIG_HOME:-~/.config}/keni-social/secretos.toml`, o bajo `KENI_DATA_DIR`.
    """
    if (p := config.override_ruta(config.ENV_SECRETOS)) is not None:
        return p
    return rutas.dir_config() / "secretos.toml"


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
    """Serializa el bloque `[imagen]` a TOML (campos fijos: proveedor + api_key + modelo)."""
    bloque = _bloque_imagen(datos)
    if not bloque:
        return ""
    lineas = ["[imagen]"]
    for clave in ("proveedor", "api_key", "modelo"):
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
    bloque = dict(_bloque_imagen(datos))  # preserva otros campos (p.ej. `modelo`)
    bloque["proveedor"] = proveedor
    bloque["api_key"] = api_key
    datos["imagen"] = bloque
    _escribir(datos)


def borrar_clave_imagen() -> None:
    """Borra la clave del proveedor de imagen (deja el almacen sin bloque `[imagen]`)."""
    datos = _leer()
    if "imagen" in datos:
        datos.pop("imagen", None)
        _escribir(datos)


def _clave_por_entorno() -> str | None:
    """Clave del proveedor de imagen inyectada por entorno, o None si no hay.

    Precedencia: `KENI_IMAGEN_API_KEY` (generica), `OPENROUTER_API_KEY` (gateway por
    defecto) y, como fallback historico, `OPENAI_API_KEY`. Util en contenedor cuando el
    secreto lo gestiona el orquestador y no hay fichero `0600` persistente.
    """
    for var in (ENV_IMAGEN_API_KEY, ENV_OPENROUTER_API_KEY, ENV_OPENAI_API_KEY):
        valor = os.environ.get(var)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


def obtener_clave_imagen() -> str | None:
    """Devuelve la clave del proveedor de imagen, o None si no hay.

    Precedencia: el FICHERO de secretos (almacen local, configurado por la UI) gana si
    tiene clave; si no, se INYECTA por entorno (`KENI_IMAGEN_API_KEY`/`OPENAI_API_KEY`).
    Uso INTERNO (la consume `media.py`). NUNCA se expone por la API ni se loguea.
    """
    clave = _bloque_imagen(_leer()).get("api_key")
    if isinstance(clave, str) and clave.strip():
        return clave
    return _clave_por_entorno()


def obtener_proveedor_imagen() -> str:
    """Devuelve el proveedor de imagen configurado (def. `openrouter`).

    Precedencia: el FICHERO de secretos gana; si no, `KENI_IMAGEN_PROVEEDOR` por entorno;
    si tampoco, el proveedor por defecto.
    """
    proveedor = _bloque_imagen(_leer()).get("proveedor")
    if isinstance(proveedor, str) and proveedor.strip():
        return proveedor.strip().lower()
    env = os.environ.get(ENV_IMAGEN_PROVEEDOR)
    if isinstance(env, str) and env.strip():
        return env.strip().lower()
    return PROVEEDOR_DEFECTO


def obtener_modelo_imagen() -> str | None:
    """Devuelve el modelo de imagen GUARDADO por la UI, o None si no hay.

    Solo lee el FICHERO de secretos (campo `[imagen].modelo`). La precedencia frente al
    env y al por defecto la resuelve `media._modelo()`; aqui no hay fallback. Una cadena
    vacia se trata como ausente (None).
    """
    modelo = _bloque_imagen(_leer()).get("modelo")
    if isinstance(modelo, str) and modelo.strip():
        return modelo.strip()
    return None


def guardar_modelo_imagen(modelo: str) -> None:
    """Guarda SOLO el campo `modelo` del bloque `[imagen]` (preserva clave y proveedor).

    Escritura ATOMICA con permisos `0600`, igual que el resto del almacen. NO toca
    `api_key` ni `proveedor`. La VALIDACION del id (que sea uno de la lista curada) la
    hace el endpoint; aqui se persiste tal cual (normalizando espacios).
    """
    modelo = (modelo or "").strip()
    datos = _leer()
    bloque = dict(_bloque_imagen(datos))
    bloque["modelo"] = modelo
    datos["imagen"] = bloque
    _escribir(datos)


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

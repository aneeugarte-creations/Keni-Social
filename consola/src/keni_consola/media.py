"""Almacenamiento de media (imagenes) de la Consola Keni + generacion por IA.

Las imagenes adjuntas a las publicaciones viven en el ALMACEN DE OBJETOS (`almacen_media`),
que elige backend segun la config S3:
  - SIN S3 cableado  -> disco local (`KENI_CONSOLA_MEDIA`; por defecto bajo la raiz de
    estado unica). Perfil privado/local: nada sale de la maquina.
  - CON S3 cableado  -> bucket S3/Garage (perfil hosted; el stack `deploy/` lo cablea).
Nada de eso cambia el flujo de IA: el prompt de generacion solo sale hacia el proveedor de
imagen configurado (OpenRouter por defecto), y SOLO si hay clave.

SEGURIDAD:
  - El NOMBRE del objeto SIEMPRE lo generamos nosotros (uuid + extension saneada); NUNCA el
    del cliente. Asi un nombre malicioso (`../../etc/passwd`) jamas se usa.
  - En disco, `resolver_media` valida ANTI-TRAVERSAL que el archivo caiga DENTRO del dir; en
    S3 el almacen rechaza cualquier nombre con separadores (defensa en profundidad).
  - Limite de tamano para subidas de imagen (15 MB) y solo mimes de imagen.

GENERACION POR IA (inyectable / mockeable):
  - `proveedor_configurado()` decide si HAY proveedor (clave presente). Si no, el
    endpoint responde 400 con un mensaje claro en espanol.
  - `generar_imagen(prompt)` delega en `_PROVEEDOR` (modulo-nivel). Los tests lo
    parchean para NUNCA tocar la red: ni se llama a OpenAI ni se necesita httpx real.
  - Proveedor por defecto: OpenRouter (gateway compatible con OpenAI; el modelo de
    imagen se elige por id de una lista curada `MODELOS_IMAGEN`, def.
    `openai/gpt-5-image-mini`). El modelo se resuelve por precedencia en `_modelo()`:
    almacen de secretos (UI) > env `OPENROUTER_IMAGE_MODEL` > por defecto. La clave se
    toma del almacen de secretos (`keni_consola.secretos`) y, si no, del env
    `OPENROUTER_API_KEY`.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import uuid
from pathlib import Path

from . import almacen_media

# Logger del módulo (#123): los fallos del proveedor de imagen se LOGUEAN con el motivo
# real (status + cuerpo recortado) en vez de tragarlo, y el motivo viaja al mensaje de
# error (toast) para que el usuario sepa POR QUÉ (p.ej. el modelo respondió texto/rechazo).
_log = logging.getLogger("keni_consola.media")

# Extensiones de imagen permitidas (sin punto) -> mime de salida al servir/guardar.
_EXT_A_MIME: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
# Mimes de imagen aceptados en la subida -> extension canonica del archivo en disco.
_MIME_A_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}

# Limite de tamano de una imagen subida o generada (bytes).
LIMITE_IMAGEN = 15 * 1024 * 1024  # 15 MB

# Trozo de lectura al volcar a disco (medir tamano sin cargar todo en memoria).
_TROZO = 1024 * 1024  # 1 MB

# Solo letras minusculas y digitos en la extension (1..8 chars), sin punto.
_RE_EXT = re.compile(r"^[a-z0-9]{1,8}$")

# Timeout (segundos) de la llamada al proveedor de imagen.
_TIMEOUT_GEN = 120

# Endpoint y modelo por defecto en OpenRouter (gateway compatible con OpenAI; el modelo
# de imagen se elige por id y se puede cambiar con OPENROUTER_IMAGE_MODEL).
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Por defecto el modelo ECONOMICO que SI genera personas reales (GPT-5 Image Mini). Las
# alternativas tipo Nano Banana (Gemini) son aun mas baratas pero BLOQUEAN personas.
_MODELO_DEFECTO = "openai/gpt-5-image-mini"

# Lista curada de modelos de imagen ofrecidos en la UI (FUENTE UNICA de verdad: alimenta
# tanto el dropdown de Ajustes como la validacion del PUT en `api/conexiones.py`). El
# orden es el orden de presentacion; el primero es el por defecto.
MODELOS_IMAGEN: list[dict[str, str]] = [
    {
        "id": "openai/gpt-5-image-mini",
        "etiqueta": "GPT-5 Image Mini — económico · personas ✓",
    },
    {
        "id": "openai/gpt-5-image",
        "etiqueta": "GPT-5 Image — equilibrado · personas ✓",
    },
    {
        "id": "openai/gpt-5.4-image-2",
        "etiqueta": "GPT-5.4 Image 2 — máxima calidad, caro · personas ✓",
    },
    {
        "id": "google/gemini-2.5-flash-image",
        "etiqueta": "Nano Banana — el más barato · SIN personas",
    },
]

# Conjunto de ids validos (derivado de MODELOS_IMAGEN; no se duplica la lista).
_IDS_MODELO: frozenset[str] = frozenset(m["id"] for m in MODELOS_IMAGEN)


def modelos_disponibles() -> list[dict[str, str]]:
    """Lista curada de modelos de imagen `[{id, etiqueta}, ...]` para poblar el dropdown.

    Devuelve una COPIA para que nadie mute la fuente unica `MODELOS_IMAGEN`.
    """
    return [dict(m) for m in MODELOS_IMAGEN]


def modelo_valido(modelo: str) -> bool:
    """True si `modelo` es uno de los ids de la lista curada (`MODELOS_IMAGEN`)."""
    return modelo in _IDS_MODELO


class MediaError(RuntimeError):
    """Error de media con mensaje ya en espanol, apto para mostrar al usuario."""


# --------------------------------------------------------------------------- #
# Directorio de media                                                          #
# --------------------------------------------------------------------------- #


def dir_media() -> Path:
    """Directorio de media en disco (delega en `almacen_media.dir_media`; perfil local).

    Solo aplica al backend de DISCO. En S3 no se usa (los objetos viven en el bucket).
    """
    return almacen_media.dir_media()


def resolver_media(nombre: str) -> Path | None:
    """Resuelve `nombre` DENTRO del dir de media (disco); None si escaparia (anti-traversal).

    Delega en `almacen_media.resolver_media`. Solo aplica al backend de DISCO; el serving
    backend-neutral pasa por `leer_media` (que en S3 lee del bucket).
    """
    return almacen_media.resolver_media(nombre)


def leer_media(nombre: str) -> bytes | None:
    """Bytes de una imagen por nombre, sea cual sea el backend; None si no existe.

    Es el camino backend-NEUTRAL de servir (lo usa `api/media.py:servir`): en disco aplica
    el anti-traversal de `resolver_media`; en S3 lee la key del bucket.
    """
    return almacen_media.leer_objeto(nombre)


def mime_de(nombre: str) -> str:
    """Mime a partir de la extension del nombre de archivo (octet-stream si no se conoce)."""
    ext = Path(nombre).suffix.lower().lstrip(".")
    return _EXT_A_MIME.get(ext, "application/octet-stream")


def _ext_desde_content_type(content_type: str | None) -> str | None:
    """Extension canonica a partir del content-type de imagen; None si no es imagen."""
    if not content_type:
        return None
    base = content_type.split(";", 1)[0].strip().lower()
    return _MIME_A_EXT.get(base)


def _ext_desde_nombre(nombre_cliente: str | None) -> str | None:
    """Extension de imagen a partir del nombre del cliente; None si no es imagen valida."""
    if not nombre_cliente:
        return None
    sufijo = Path(nombre_cliente).suffix.lower().lstrip(".")
    if _RE_EXT.match(sufijo) and sufijo in _EXT_A_MIME:
        # Normaliza jpeg -> jpg para un solo nombre de extension en disco.
        return "jpg" if sufijo == "jpeg" else sufijo
    return None


# --------------------------------------------------------------------------- #
# Guardado seguro de una imagen subida                                         #
# --------------------------------------------------------------------------- #


async def guardar_subida(archivo, *, content_type: str | None = None) -> str:  # noqa: ANN001
    """Vuelca un `UploadFile` de imagen al almacen de media (disco o S3) de forma segura.

    - Acepta SOLO mimes de imagen (por content-type o, en su defecto, por la
      extension del nombre del cliente). El NOMBRE del objeto lo generamos (uuid +
      extension canonica); NUNCA el del cliente.
    - Lee en trozos MIDIENDO el tamano; si supera `LIMITE_IMAGEN`, aborta antes de
      escribir nada. Se bufferea en memoria (acotado por el limite de 15 MB) para tener
      UN solo camino de guardado valido en disco y en S3 (S3 no escribe en streaming).

    Devuelve el NOMBRE del objeto (no la ruta). Lanza `MediaError` (en espanol) ante
    mime no permitido, archivo vacio o demasiado grande.
    """
    ct = content_type if content_type is not None else getattr(archivo, "content_type", None)
    ext = _ext_desde_content_type(ct) or _ext_desde_nombre(getattr(archivo, "filename", None))
    if ext is None:
        raise MediaError("Solo se aceptan imágenes (PNG, JPG, GIF o WEBP).")

    trozos: list[bytes] = []
    total = 0
    try:
        while True:
            trozo = await archivo.read(_TROZO)
            if not trozo:
                break
            total += len(trozo)
            if total > LIMITE_IMAGEN:
                raise MediaError(
                    "La imagen es demasiado grande (máximo 15 MB); sube una más pequeña."
                )
            trozos.append(trozo)
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- cualquier fallo de E/S: reporta en espanol
        raise MediaError("No se pudo guardar la imagen subida.") from e
    if total == 0:
        raise MediaError("La imagen está vacía.")
    datos = b"".join(trozos)
    nombre = f"{uuid.uuid4().hex}.{ext}"
    try:
        almacen_media.guardar_objeto(nombre, datos, content_type=_EXT_A_MIME[ext])
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- fallo del backend (disco/S3): reporta en espanol
        raise MediaError("No se pudo guardar la imagen subida.") from e
    return nombre


def guardar_bytes(datos: bytes, *, ext: str = "png") -> str:
    """Guarda `datos` (una imagen ya generada) en el almacen de media y devuelve su nombre."""
    ext = ext.lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    if not (_RE_EXT.match(ext) and ext in _EXT_A_MIME):
        ext = "png"
    if len(datos) > LIMITE_IMAGEN:
        raise MediaError("La imagen generada es demasiado grande.")
    nombre = f"{uuid.uuid4().hex}.{ext}"
    almacen_media.guardar_objeto(nombre, datos, content_type=_EXT_A_MIME[ext])
    return nombre


def importar_imagen(ruta) -> str:  # noqa: ANN001 -- acepta str | Path
    """COPIA una imagen que ya está en disco (ruta absoluta) al almacén de media.

    Pensado para la salida de las skills de imagen (estudio-imagen): las
    herramientas deterministas/generativas escriben los .png en disco y aquí los
    importamos al almacén de media para poder PREVISUALIZARLOS por `/api/media/...`.
    El NOMBRE en disco lo generamos (uuid), nunca el de origen. Valida que sea un
    archivo de imagen real (extensión conocida) y respeta el límite de tamaño.

    Devuelve el NOMBRE de archivo del media importado. Lanza `MediaError` (en
    español) si la ruta no existe, no es imagen o es demasiado grande.
    """
    origen = Path(ruta)
    ext = _ext_desde_nombre(origen.name)
    if ext is None:
        raise MediaError("El archivo no es una imagen reconocible (PNG, JPG, GIF o WEBP).")
    try:
        if not origen.is_file():
            raise MediaError("No se encontró la imagen generada para previsualizarla.")
        datos = origen.read_bytes()
    except MediaError:
        raise
    except OSError as e:
        raise MediaError("No se pudo leer la imagen generada.") from e
    if not datos:
        raise MediaError("La imagen generada está vacía.")
    return guardar_bytes(datos, ext=ext)


# --------------------------------------------------------------------------- #
# Generacion por IA — abstraccion de proveedor (inyectable / mockeable)        #
# --------------------------------------------------------------------------- #


def _clave_imagen() -> str | None:
    """Clave del proveedor de imagen (almacen de secretos o entorno). NUNCA se loguea.

    La resuelve `secretos.obtener_clave_imagen()`: gana el fichero `0600` (configurado por
    la UI); si no, el entorno (`OPENROUTER_API_KEY`/`KENI_IMAGEN_API_KEY`, fallback OpenAI).
    """
    from . import secretos

    return secretos.obtener_clave_imagen()


def proveedor_configurado() -> bool:
    """True si HAY un proveedor de imagen configurado (clave presente)."""
    return _clave_imagen() is not None


def _modelo() -> str:
    """Modelo de imagen en OpenRouter, con esta PRECEDENCIA (cadena vacia = ausente):

    1. el modelo GUARDADO en el almacen de secretos (elegido por la UI),
    2. la env `OPENROUTER_IMAGE_MODEL`,
    3. el por defecto `_MODELO_DEFECTO` (GPT-5 Image Mini: barato y con personas).
    """
    from . import secretos

    guardado = secretos.obtener_modelo_imagen()
    if guardado:
        return guardado
    return os.environ.get("OPENROUTER_IMAGE_MODEL") or _MODELO_DEFECTO


def _json_seguro(respuesta) -> dict:  # noqa: ANN001
    """`respuesta.json()` tolerante: {} si el cuerpo no es JSON (no rompe el manejo de error)."""
    try:
        data = respuesta.json()
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _recortar(texto: str, n: int = 300) -> str:
    """Normaliza espacios y recorta a `n` caracteres (para mensajes/toasts)."""
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def _texto_respuesta(data: dict) -> str:
    """Motivo legible de una respuesta de OpenRouter, SIN exponer la clave.

    Prioriza: error explícito (`error.message`) > el TEXTO que devolvió el modelo
    (`choices[0].message.content`, p.ej. un rechazo/aclaración) > `finish_reason`.
    Devuelve "" si no hay nada útil que mostrar.
    """
    err = data.get("error")
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])
    if isinstance(err, str) and err.strip():
        return err
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        msg = choices[0].get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str) and msg["content"].strip():
            return msg["content"]
        fr = choices[0].get("finish_reason")
        if fr:
            return f"finish_reason={fr}"
    return ""


def _proveedor_openrouter(prompt: str) -> bytes:
    """Genera una imagen vía OpenRouter (gateway compatible con OpenAI) y devuelve bytes.

    Mismo camino que la skill `estudio-imagen`: endpoint chat/completions con
    `modalities:["image","text"]`; el modelo se elige por id (`OPENROUTER_IMAGE_MODEL`).
    `follow_redirects=False`: un 3xx a otro host no debe reenviar el Bearer (anti-SSRF).
    Importacion diferida de httpx; los tests NUNCA llegan aqui (parchean `_PROVEEDOR`).
    """
    clave = _clave_imagen()
    if clave is None:
        raise MediaError(
            "La generación de imagen no está configurada. Añade una clave de "
            "proveedor de imagen para activarla."
        )
    try:
        import httpx
    except ImportError as e:  # pragma: no cover -- httpx es dependencia transitiva
        raise MediaError("Falta la librería para generar imágenes en este equipo.") from e

    modelo = _modelo()
    try:
        respuesta = httpx.post(
            _OPENROUTER_URL,
            headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
            json={
                "model": modelo,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
            },
            timeout=_TIMEOUT_GEN,
            follow_redirects=False,
        )
    except httpx.TimeoutException as e:
        raise MediaError("El proveedor de imagen tardó demasiado y se canceló.") from e
    except httpx.HTTPError as e:
        raise MediaError("No se pudo contactar al proveedor de imagen.") from e

    if respuesta.status_code != 200:
        motivo = _recortar(_texto_respuesta(_json_seguro(respuesta)))
        _log.warning(
            "generar_imagen: OpenRouter %s [%s] -> %s",
            respuesta.status_code, modelo, motivo or "(sin cuerpo)",
        )
        sufijo = f": {motivo}" if motivo else ""
        raise MediaError(
            f"El proveedor de imagen devolvió un error ({respuesta.status_code}){sufijo}"
        )

    data = _json_seguro(respuesta)
    try:
        url = data["choices"][0]["message"]["images"][0]["image_url"]["url"]
        b64 = url.split(",", 1)[1] if "," in url else url
        return base64.b64decode(b64)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        # 200 sin imagen: casi siempre el modelo respondió TEXTO (rechazo/aclaración) en
        # vez de imagen. Mostramos ese texto (recortado) para que se vea el PORQUÉ.
        motivo = _recortar(_texto_respuesta(data))
        _log.warning("generar_imagen: 200 sin imagen [%s] -> %s", modelo, motivo or "(sin texto)")
        if motivo:
            raise MediaError(f"El modelo no devolvió una imagen. Respondió: {motivo}") from e
        raise MediaError(
            "El proveedor de imagen devolvió una respuesta inesperada (sin imagen)."
        ) from e


# Punto INYECTABLE: lo unico que toca el proveedor real. Los tests lo parchean.
_PROVEEDOR = _proveedor_openrouter


def generar_imagen(prompt: str) -> bytes:
    """Genera una imagen a partir de `prompt` con el proveedor configurado.

    Lanza `MediaError` (en espanol) si no hay proveedor o si el prompt esta vacio.
    NUNCA toca la red en tests: `_PROVEEDOR` se parchea.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise MediaError("Falta el texto (prompt) para generar la imagen.")
    if not proveedor_configurado():
        raise MediaError(
            "La generación de imagen no está configurada. Añade una clave de "
            "proveedor de imagen para activarla."
        )
    datos = _PROVEEDOR(prompt)
    if not datos:
        raise MediaError("El proveedor de imagen no devolvió ninguna imagen.")
    return datos

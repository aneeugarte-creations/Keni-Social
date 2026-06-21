"""Almacenamiento de media (imagenes) de la Consola Keni + generacion por IA.

Las imagenes adjuntas a las piezas viven en el ALMACEN DE OBJETOS (`almacen_media`),
que elige backend segun la config S3:
  - SIN S3 cableado  -> disco local (`KENI_CONSOLA_MEDIA`; por defecto bajo la raiz de
    estado unica). Perfil privado/local: nada sale de la maquina.
  - CON S3 cableado  -> bucket S3/Garage (perfil hosted; el stack `deploy/` lo cablea).
Nada de eso cambia el flujo de IA: el prompt de generacion solo sale hacia el proveedor de
imagen configurado (OpenRouter por defecto), y SOLO si hay clave.

SEGURIDAD:
  - El NOMBRE del objeto SIEMPRE lo generamos nosotros (uuid + extension reparada); NUNCA el
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
import hashlib
import io
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import almacen_media


@dataclass(frozen=True)
class SalidaImagen:
    """Resultado de generar UNA imagen: los bytes + su coste real y el modelo usado.

    `coste_usd` es el coste que reporta el proveedor (OpenRouter `usage.cost`, en USD);
    0.0 si el proveedor no lo devuelve. `modelo` es el id concreto que se usó (resuelta ya
    la precedencia). Lo consume el lanzador de imagen para dejar el gasto en el ledger
    `gasto_ia` (tipo `imagen`) y poder estimar el coste medio por imagen y por modelo.
    """

    datos: bytes
    coste_usd: float
    modelo: str

# Logger del módulo: los fallos del proveedor de imagen se LOGUEAN con el motivo
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

# VIDEO (piezas de formato video): mimes aceptados -> extension canonica del archivo en el
# almacen. Misma lista que `transcripcion._MIME_A_EXT` (la parte de video; reusamos el contrato
# de formatos del equipo). El limite de tamano es alto (un clip de redes pesa decenas/cientos de
# MB) y configurable por `KENI_VIDEO_MAX_MB` (def 300; ver `config.video_max_mb`).
_MIME_A_EXT_VIDEO: dict[str, str] = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/mpeg": "mpeg",
    "video/3gpp": "3gp",
}
# Extensiones de video aceptadas (subida por nombre cuando no llega content-type fiable).
_EXT_VIDEO: frozenset[str] = frozenset({*_MIME_A_EXT_VIDEO.values(), "m4v", "mpg"})

# DOCUMENTOS (importacion de parrilla): tipos que un `claude -p` READ-ONLY puede leer del
# documento subido (PDF, captura, Word, Excel, texto). NO afectan al camino de imagen (mimes
# de imagen siguen yendo por `_MIME_A_EXT`). El limite es mayor (un PDF/escaneo pesa mas que
# una imagen suelta) pero acotado para no permitir subidas enormes.
LIMITE_DOCUMENTO = 25 * 1024 * 1024  # 25 MB

# Mimes de documento aceptados -> extension canonica del archivo en el almacen.
_MIME_A_EXT_DOC: dict[str, str] = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "text/csv": "csv",
}
# Extensiones de documento aceptadas (subida por nombre cuando no hay content-type fiable).
_EXT_DOC: frozenset[str] = frozenset(
    {"pdf", "doc", "docx", "xls", "xlsx", "txt", "csv", *_MIME_A_EXT_DOC.values()}
)
# Mimes que se sirven con un content-type util (el resto, octet-stream).
_EXT_A_MIME_DOC: dict[str, str] = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "txt": "text/plain; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}

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

# Mensaje de SISTEMA con DOS encargos. (1) Forzar salida de imagen: los modelos de imagen de
# OpenAI (GPT-5 Image / Mini) son chat-based y, si el prompt "suena" a noticia/articulo,
# RESPONDEN TEXTO ("¿Quieres que redacte un titular?") en vez de generar la imagen. (2) Forzar
# que sea UNA FOTO realista y NO una infografia: ante una noticia de TV tienden a producir el
# tipico grafico de canal (mapa con etiquetas, titular, cintillo "UnoTV", marco), justo lo que
# NO queremos: en la consola el titular y la marca se componen DESPUES, de forma determinista,
# encima de una foto limpia. Los generadores puros (Nano Banana/Gemini) lo respetan sin dano.
#
# El TEXTO de esta directiva vive en la Prompts de Texto como prompt EDITABLE
# (`_SISTEMA_IMAGEN_ID`): el equipo lo ajusta desde el estudio sin tocar codigo. El paquete trae la version base; `_FALLBACK` abajo es una red defensiva por si la lectura fallara.
_SISTEMA_IMAGEN_ID = "prompt/ilustrar"
_SISTEMA_IMAGEN_FALLBACK = (
    "Eres un generador de fotografias. Tu UNICA salida es UNA sola fotografia realista que "
    "represente la peticion; NUNCA respondas con texto. PROHIBIDO dentro de la imagen: texto, "
    "letras, titulares, cintillos, logos, marcas de agua, infografias, mapas con etiquetas, "
    "plantillas, marcos o bordes. Devuelve una unica imagen fotografica limpia."
)


def _sistema_imagen() -> str:
    """Directiva de SISTEMA del generador de imagen, leida de la Prompts (editable).

    Resuelve el cuerpo EFECTIVO del prompt `_SISTEMA_IMAGEN_ID` (store del equipo > base del
    paquete). Import diferido de `libprompts` (evita ciclos; igual que `config`/`secretos`). Si la
    lectura fallara o viniera vacia, cae al `_SISTEMA_IMAGEN_FALLBACK` para no quedarnos sin la
    directiva (sin ella los modelos GPT devuelven texto/infografia).
    """
    try:
        from . import libprompts

        cuerpo = (libprompts.cuerpo_efectivo(_SISTEMA_IMAGEN_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar la generacion sin directiva por un fallo de lectura
        cuerpo = ""
    return cuerpo or _SISTEMA_IMAGEN_FALLBACK

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


def leer_objeto(nombre: str) -> bytes | None:
    """Bytes de un objeto cualquiera del almacen por su key; None si no existe.

    Alias backend-NEUTRAL de `leer_media` con nombre genérico (no solo imágenes): lo usa el
    PREFETCH del worker para bajar un documento subido (la importación de parrilla) desde S3.
    """
    return almacen_media.leer_objeto(nombre)


# --------------------------------------------------------------------------- #
# Derivadas redimensionadas (resize on-the-fly + cache en el almacen)          #
# --------------------------------------------------------------------------- #

# Allowlist ESTRICTA de anchos de derivada (px). Un ancho pedido fuera de la lista se CLAMPa
# al permitido mas cercano (nunca se redimensiona a un ancho arbitrario): asi un cliente no
# puede forzar millones de variantes distintas, solo este conjunto acotado. El orden no importa.
ANCHOS_DERIVADOS: tuple[int, ...] = (64, 160, 320, 640, 960, 1280)

# Calidad WebP de las derivadas (0..100). 80 = buen equilibrio peso/calidad para feed/listas.
_CALIDAD_WEBP = 80

# Extensiones cuyas derivadas redimensionamos. Lo demas (video, etc.) se sirve TAL CUAL.
_EXT_DERIVABLE: frozenset[str] = frozenset({"png", "jpg", "jpeg", "webp", "gif"})


def _ancho_objetivo(valor: str | int) -> int:
    """Ancho de la allowlist mas cercano a `valor`. Lanza ValueError si no es un entero positivo.

    El llamante (`api/media.py:servir`) traduce el ValueError a un 400; un entero positivo
    fuera de la lista se CLAMPa al permitido mas cercano (defensa anti-abuso: solo anchos de
    `ANCHOS_DERIVADOS` llegan a Pillow).
    """
    try:
        ancho = int(valor)
    except (TypeError, ValueError) as e:
        raise ValueError("ancho de imagen invalido") from e
    if ancho <= 0:
        raise ValueError("ancho de imagen invalido")
    return min(ANCHOS_DERIVADOS, key=lambda a: abs(a - ancho))


def _derivar_webp(datos: bytes, ancho: int) -> bytes | None:
    """Redimensiona `datos` a lo ancho `ancho` (sin upscale) y devuelve WebP; None si no aplica.

    Mantiene el aspecto y NUNCA agranda: si el original es mas estrecho que `ancho`, codifica a su
    ancho real. Devuelve None ante un GIF ANIMADO o cualquier imagen que Pillow no pueda abrir
    (el llamante sirve entonces el original intacto). Aplica la orientacion EXIF (fotos de movil).
    """
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(datos)) as img:
            if getattr(img, "is_animated", False):
                return None
            img = ImageOps.exif_transpose(img)
            objetivo = min(ancho, img.width)
            if objetivo <= 0:
                return None
            if objetivo < img.width:
                alto = max(1, round(img.height * objetivo / img.width))
                img = img.resize((objetivo, alto), Image.LANCZOS)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=_CALIDAD_WEBP, method=6)
            return buf.getvalue()
    except Exception:  # noqa: BLE001 -- imagen corrupta/formato raro: servir el original, sin traza
        return None


def derivada(nombre: str, ancho: str | int) -> tuple[bytes, str] | None:
    """Derivada WebP de `nombre` al ancho de la allowlist mas cercano a `ancho` -> `(bytes, mime)`.

    Camino del resize ON-THE-FLY con cache en el almacen (`deriv/<ancho>-<raiz>.webp`): mira
    primero la cache; si esta, la sirve; si no, lee el original, lo redimensiona (Pillow,
    manteniendo aspecto, sin upscale), lo codifica WebP, lo guarda en la cache y lo sirve. La key
    es DETERMINISTA y content-addressed (la raiz del original ya es uuid/sha256), asi dos
    peticiones simultaneas del mismo derivado convergen a la misma key (idempotente).

    Devuelve None si el original NO existe o NO es una imagen redimensionable (video, GIF animado,
    formato no soportado): el llamante sirve entonces el original intacto. Lanza ValueError si
    `ancho` no es un entero positivo (el llamante responde 400).
    """
    objetivo = _ancho_objetivo(ancho)
    ext = Path(nombre).suffix.lower().lstrip(".")
    if ext not in _EXT_DERIVABLE:
        return None
    raiz = nombre.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    try:
        clave = almacen_media.componer_clave("deriv", f"{objetivo}-{raiz}.webp")
    except ValueError:
        return None
    cacheada = almacen_media.leer_objeto(clave)
    if cacheada is not None:
        return cacheada, "image/webp"
    original = leer_media(nombre)
    if original is None:
        return None
    webp = _derivar_webp(original, objetivo)
    if webp is None:
        return None
    try:
        almacen_media.guardar_objeto(clave, webp, content_type="image/webp")
    except Exception:  # noqa: BLE001 -- la cache es best-effort: si el guardado falla, servimos igual
        pass
    return webp, "image/webp"


# Extension de VIDEO (sin punto) -> mime al servir (`/api/media/{n}` sirve tambien videos).
_EXT_A_MIME_VIDEO_SERVIR: dict[str, str] = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
    "mpeg": "video/mpeg",
    "3gp": "video/3gpp",
}


def mime_de(nombre: str) -> str:
    """Mime a partir de la extension del nombre de archivo (octet-stream si no se conoce).

    Cubre imagenes (`_EXT_A_MIME`) y videos (`_EXT_A_MIME_VIDEO_SERVIR`): el mismo endpoint
    `/api/media/{n}` sirve ambos, asi que el video se devuelve con su content-type correcto.
    """
    ext = Path(nombre).suffix.lower().lstrip(".")
    return _EXT_A_MIME.get(ext) or _EXT_A_MIME_VIDEO_SERVIR.get(ext, "application/octet-stream")


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


def _guardar_contenido(datos: bytes, *, ext: str, categoria: str, mime: str) -> str:
    """Guarda `datos` bajo una key CONTENT-ADDRESSED `<categoria>/<sha256>.<ext>`; devuelve la key.

    Misma categoria + mismo contenido -> misma key -> UN solo objeto (dedup). Idempotente: si la
    key ya existe NO re-sube bytes identicos. Es el camino comun de subidas y composiciones: por
    eso subir la misma foto 4 veces guarda 1 objeto, no 4.
    """
    digest = hashlib.sha256(datos).hexdigest()
    clave = almacen_media.componer_clave(categoria, f"{digest}.{ext}")
    if not almacen_media.objeto_existe(clave):
        almacen_media.guardar_objeto(clave, datos, content_type=mime)
    return clave


async def guardar_subida(
    archivo, *, content_type: str | None = None, categoria: str = "fotos"
) -> str:  # noqa: ANN001
    """Vuelca un `UploadFile` de imagen al almacen de media (disco o S3) de forma segura.

    - Acepta SOLO mimes de imagen (por content-type o, en su defecto, por la
      extension del nombre del cliente). El NOMBRE del objeto lo generamos; NUNCA el del cliente.
    - DEDUP: la key es CONTENT-ADDRESSED (`<categoria>/<sha256>.<ext>`), asi subir la misma foto
      varias veces guarda UN solo objeto. La `categoria` (carpeta) la fija el llamante segun el
      contexto de subida (def `fotos`; el editor de plantillas sube como `plantillas`).
    - Lee en trozos MIDIENDO el tamano; si supera `LIMITE_IMAGEN`, aborta antes de
      escribir nada. Se bufferea en memoria (acotado por el limite de 15 MB) para tener
      UN solo camino de guardado valido en disco y en S3 (S3 no escribe en streaming).

    Devuelve la KEY del objeto (con su carpeta). Lanza `MediaError` (en espanol) ante
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
    try:
        return _guardar_contenido(datos, ext=ext, categoria=categoria, mime=_EXT_A_MIME[ext])
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- fallo del backend (disco/S3): reporta en espanol
        raise MediaError("No se pudo guardar la imagen subida.") from e


def _ext_doc_desde_content_type(content_type: str | None) -> str | None:
    """Extension canonica de DOCUMENTO a partir del content-type; None si no es documento."""
    if not content_type:
        return None
    base = content_type.split(";", 1)[0].strip().lower()
    return _MIME_A_EXT_DOC.get(base)


def _ext_doc_desde_nombre(nombre_cliente: str | None) -> str | None:
    """Extension de DOCUMENTO a partir del nombre del cliente; None si no es aceptada."""
    if not nombre_cliente:
        return None
    sufijo = Path(nombre_cliente).suffix.lower().lstrip(".")
    if _RE_EXT.match(sufijo) and sufijo in _EXT_DOC:
        return sufijo
    return None


async def guardar_documento_subido(
    archivo, *, content_type: str | None = None
) -> tuple[str, str]:  # noqa: ANN001
    """Vuelca un `UploadFile` de DOCUMENTO (PDF/imagen/docx/xlsx/txt/csv) al almacen de media.

    Camino PARALELO a `guardar_subida`: la importacion de parrilla acepta MAS tipos (documentos y
    tambien imagenes/capturas) y un limite mayor (`LIMITE_DOCUMENTO`). El NOMBRE del objeto lo
    generamos; NUNCA el del cliente, y va a la carpeta `documentos/` con key CONTENT-ADDRESSED
    (dedup: el mismo PDF subido dos veces guarda un objeto). Lee en trozos midiendo el tamano y
    aborta si supera el limite. Devuelve `(key_objeto, ext)`. Lanza `MediaError` (en espanol) ante
    tipo no permitido, archivo vacio o demasiado grande.
    """
    ct = content_type if content_type is not None else getattr(archivo, "content_type", None)
    nombre_cli = getattr(archivo, "filename", None)
    # Acepta imagen (mismo mapa que las fotos) O documento. Imagen primero por compatibilidad.
    ext = (
        _ext_desde_content_type(ct)
        or _ext_doc_desde_content_type(ct)
        or _ext_desde_nombre(nombre_cli)
        or _ext_doc_desde_nombre(nombre_cli)
    )
    if ext is None:
        raise MediaError(
            "Tipo de archivo no admitido. Sube un PDF, imagen, Word, Excel o texto."
        )

    trozos: list[bytes] = []
    total = 0
    try:
        while True:
            trozo = await archivo.read(_TROZO)
            if not trozo:
                break
            total += len(trozo)
            if total > LIMITE_DOCUMENTO:
                raise MediaError(
                    "El archivo es demasiado grande (máximo 25 MB); sube uno más pequeño."
                )
            trozos.append(trozo)
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- cualquier fallo de E/S: reporta en espanol
        raise MediaError("No se pudo guardar el documento subido.") from e
    if total == 0:
        raise MediaError("El documento está vacío.")
    datos = b"".join(trozos)
    mime = _EXT_A_MIME.get(ext) or _EXT_A_MIME_DOC.get(ext) or "application/octet-stream"
    try:
        clave = _guardar_contenido(datos, ext=ext, categoria="documentos", mime=mime)
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- fallo del backend (disco/S3): reporta en espanol
        raise MediaError("No se pudo guardar el documento subido.") from e
    return clave, ext


def _ext_video_desde_content_type(content_type: str | None) -> str | None:
    """Extension canonica de VIDEO a partir del content-type; None si no es video aceptado."""
    if not content_type:
        return None
    base = content_type.split(";", 1)[0].strip().lower()
    return _MIME_A_EXT_VIDEO.get(base)


def _ext_video_desde_nombre(nombre_cliente: str | None) -> str | None:
    """Extension de VIDEO a partir del nombre del cliente; None si no es aceptada."""
    if not nombre_cliente:
        return None
    sufijo = Path(nombre_cliente).suffix.lower().lstrip(".")
    if _RE_EXT.match(sufijo) and sufijo in _EXT_VIDEO:
        return sufijo
    return None


async def guardar_video_subida(
    archivo, *, content_type: str | None = None
) -> str:  # noqa: ANN001
    """Vuelca un `UploadFile` de VIDEO al almacen de media (disco o S3) de forma segura.

    Camino PARALELO a `guardar_subida` (imagen) para las piezas de formato video:
    - Acepta SOLO mimes de video (`video/mp4`, `video/quicktime`, `video/webm`,
      `video/x-matroska`, `video/mpeg`, `video/3gpp`) por content-type o, en su defecto, por la
      extension del nombre del cliente. El NOMBRE del objeto lo generamos; NUNCA el del cliente.
    - DEDUP: la key es CONTENT-ADDRESSED (`videos/<sha256>.<ext>`), asi subir el mismo clip dos
      veces guarda UN solo objeto.
    - Lee en trozos MIDIENDO el tamano; si supera `config.video_max_mb()` MB (def 300), aborta
      antes de escribir nada.

    Devuelve la KEY del objeto. Lanza `MediaError` (en espanol) ante mime no permitido, archivo
    vacio o demasiado grande.
    """
    from . import config

    ct = content_type if content_type is not None else getattr(archivo, "content_type", None)
    ext = _ext_video_desde_content_type(ct) or _ext_video_desde_nombre(
        getattr(archivo, "filename", None)
    )
    if ext is None:
        raise MediaError("Solo se aceptan videos (MP4, MOV, WEBM, MKV, MPEG o 3GP).")

    limite = config.video_max_mb() * 1024 * 1024
    limite_mb = config.video_max_mb()
    trozos: list[bytes] = []
    total = 0
    try:
        while True:
            trozo = await archivo.read(_TROZO)
            if not trozo:
                break
            total += len(trozo)
            if total > limite:
                raise MediaError(
                    f"El video es demasiado grande (máximo {limite_mb} MB); sube uno más pequeño."
                )
            trozos.append(trozo)
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- cualquier fallo de E/S: reporta en espanol
        raise MediaError("No se pudo guardar el video subido.") from e
    if total == 0:
        raise MediaError("El video está vacío.")
    datos = b"".join(trozos)
    # Normaliza mpg->mpeg para una sola extension canonica en el almacen (mismo mime).
    if ext in ("mpg",):
        ext = "mpeg"
    mime = next((m for m, e in _MIME_A_EXT_VIDEO.items() if e == ext), "video/mp4")
    try:
        return _guardar_contenido(datos, ext=ext, categoria="videos", mime=mime)
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- fallo del backend (disco/S3): reporta en espanol
        raise MediaError("No se pudo guardar el video subido.") from e


async def guardar_audio_subida(
    archivo, *, content_type: str | None = None
) -> str:  # noqa: ANN001
    """Vuelca un `UploadFile` de AUDIO o VIDEO al almacen para el gestor de transcripciones.

    A diferencia de `guardar_video_subida` (solo video, para piezas), aqui aceptamos AUDIO y VIDEO:
    el gestor audio→texto extrae la pista de voz de cualquier contenedor. El NOMBRE del objeto lo
    generamos (sha256); NUNCA el del cliente. Reutiliza el mapeo mime/extension de
    `keni_consola.transcripcion` (la fuente del flujo whisper.cpp). DEDUP content-addressed bajo
    `audios/<sha256>.<ext>`; limite de tamano `config.video_max_mb()` MB (def 300).

    Devuelve la KEY del objeto. Lanza `MediaError` (en espanol) ante formato no soportado, archivo
    vacio o demasiado grande.
    """
    from . import config, transcripcion

    ct = content_type if content_type is not None else getattr(archivo, "content_type", None)
    ext = transcripcion.ext_de_subida(ct, getattr(archivo, "filename", None))
    if ext is None:
        raise MediaError("Solo se aceptan audios o videos (MP4, MOV, MP3, M4A, WAV, OGG…).")

    limite_mb = config.video_max_mb()
    limite = limite_mb * 1024 * 1024
    trozos: list[bytes] = []
    total = 0
    try:
        while True:
            trozo = await archivo.read(_TROZO)
            if not trozo:
                break
            total += len(trozo)
            if total > limite:
                raise MediaError(
                    f"El archivo es demasiado grande (máximo {limite_mb} MB); sube uno más corto."
                )
            trozos.append(trozo)
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- cualquier fallo de E/S: reporta en espanol
        raise MediaError("No se pudo guardar el archivo subido.") from e
    if total == 0:
        raise MediaError("El archivo está vacío.")
    datos = b"".join(trozos)
    mime = next(
        (m for m, e in transcripcion._MIME_A_EXT.items() if e == ext), "application/octet-stream"
    )
    try:
        return _guardar_contenido(datos, ext=ext, categoria="audios", mime=mime)
    except MediaError:
        raise
    except Exception as e:  # noqa: BLE001 -- fallo del backend (disco/S3): reporta en espanol
        raise MediaError("No se pudo guardar el archivo subido.") from e


def guardar_bytes(datos: bytes, *, ext: str = "png", categoria: str = "generadas") -> str:
    """Guarda `datos` (una imagen ya generada) en el almacen de media y devuelve su KEY.

    NOMBRE por UUID (objeto ÚNICO por llamada): para la generación por IA (`generar_variante`),
    donde cada variante debe ser un objeto distinto aunque el contenido coincida. Va a la carpeta
    `categoria` (def `generadas`). Las composiciones de plantilla NO pasan por aquí: usan
    `importar_imagen`/`guardar_bytes_contenido` (content-addressed, carpeta `render`).
    """
    ext = ext.lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    if not (_RE_EXT.match(ext) and ext in _EXT_A_MIME):
        ext = "png"
    if len(datos) > LIMITE_IMAGEN:
        raise MediaError("La imagen generada es demasiado grande.")
    clave = almacen_media.componer_clave(categoria, f"{uuid.uuid4().hex}.{ext}")
    almacen_media.guardar_objeto(clave, datos, content_type=_EXT_A_MIME[ext])
    return clave


def guardar_bytes_contenido(datos: bytes, *, ext: str = "png", categoria: str = "render") -> str:
    """Guarda `datos` bajo una key CONTENT-ADDRESSED (`<categoria>/<sha256>.<ext>`); devuelve la key.

    Mismo contenido -> misma key -> UN solo objeto en el almacén. Es la pieza que evita los
    duplicados de plantilla: dos piezas con el mismo logo+pleca+titular(+foto) comparten la
    imagen compuesta en vez de hornear un PNG idéntico por cada una. Si la key ya existe, NO
    re-sube los bytes (el contenido es, por definición, idéntico). Va a la carpeta `categoria`
    (def `render`: composites/cache regenerable).
    """
    ext = ext.lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    if not (_RE_EXT.match(ext) and ext in _EXT_A_MIME):
        ext = "png"
    if len(datos) > LIMITE_IMAGEN:
        raise MediaError("La imagen generada es demasiado grande.")
    return _guardar_contenido(datos, ext=ext, categoria=categoria, mime=_EXT_A_MIME[ext])


def importar_imagen(ruta, *, categoria: str = "render") -> str:  # noqa: ANN001 -- acepta str | Path
    """COPIA una imagen que ya está en disco (ruta absoluta) al almacén de media.

    Pensado para la salida de los motores de imagen (estudio-imagen): las herramientas
    deterministas/generativas escriben los .png en disco y aquí los importamos al almacén para
    poder servirlos por `/api/media/...`. El NOMBRE lo generamos nosotros (NUNCA el de origen):
    es CONTENT-ADDRESSED (`<categoria>/<sha256>.<ext>`), de modo que dos salidas idénticas (la
    misma placa de marca, la misma composición de plantilla) comparten UN solo objeto y no se
    duplican. Va a la carpeta `categoria` (def `render`). Valida que sea un archivo de imagen
    real (extensión conocida) y respeta el límite de tamaño.

    Devuelve la KEY del media importado. Lanza `MediaError` (en español) si la ruta no existe,
    no es imagen o es demasiado grande.
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
    return guardar_bytes_contenido(datos, ext=ext, categoria=categoria)


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


def _coste_de(data: dict) -> float:
    """Coste en USD de una respuesta de OpenRouter (`usage.cost`); 0.0 si no viene/inválido."""
    try:
        usage = data.get("usage")
        if isinstance(usage, dict):
            return max(0.0, float(usage.get("cost") or 0.0))
    except (TypeError, ValueError):
        pass
    return 0.0


def _proveedor_openrouter(prompt: str, modelo: str = "") -> SalidaImagen:
    """Genera una imagen vía OpenRouter (gateway compatible con OpenAI) -> `SalidaImagen`.

    Mismo camino que el estudio de imagen: endpoint chat/completions con
    `modalities:["image","text"]`; el modelo se elige por id (`modelo`, o la precedencia
    de `_modelo()` si viene vacío). Pide `usage.include` para que el gateway devuelva el
    COSTE real de la llamada (`usage.cost`, USD): así el lanzador puede dejarlo en el
    ledger y estimar el coste por imagen (0.0 si el proveedor no lo reporta).
    Antepone un mensaje de SISTEMA (`_sistema_imagen()`, editable en la Prompts) que fuerza
    salida de imagen y prohibe infografia/texto incrustado: sin el,
    los modelos GPT-5 Image responden TEXTO ante prompts noticiosos en vez de la imagen.
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

    modelo = modelo or _modelo()
    try:
        respuesta = httpx.post(
            _OPENROUTER_URL,
            headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
            json={
                "model": modelo,
                "messages": [
                    {"role": "system", "content": _sistema_imagen()},
                    {"role": "user", "content": prompt},
                ],
                "modalities": ["image", "text"],
                # Pide el COSTE real de la llamada (OpenRouter lo añade en `usage.cost`, USD).
                "usage": {"include": True},
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
        return SalidaImagen(base64.b64decode(b64), _coste_de(data), modelo)
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


def generar_imagen_detallado(prompt: str, *, modelo: str = "") -> SalidaImagen:
    """Genera una imagen y devuelve `SalidaImagen` (bytes + coste + modelo usado).

    `modelo` opcional: un id de la lista curada (`modelos_disponibles`); vacío => el modelo
    configurado por defecto (`_modelo()`, con su precedencia). Lanza `MediaError` (en
    español) si no hay proveedor, si el prompt está vacío o si el modelo no es válido.
    NUNCA toca la red en tests: `_PROVEEDOR` se parchea.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise MediaError("Falta el texto (prompt) para generar la imagen.")
    modelo = (modelo or "").strip()
    if modelo and not modelo_valido(modelo):
        raise MediaError("Modelo de imagen no reconocido.")
    if not proveedor_configurado():
        raise MediaError(
            "La generación de imagen no está configurada. Añade una clave de "
            "proveedor de imagen para activarla."
        )
    salida = _PROVEEDOR(prompt, modelo or _modelo())
    if not salida.datos:
        raise MediaError("El proveedor de imagen no devolvió ninguna imagen.")
    return salida


def generar_imagen(prompt: str) -> bytes:
    """Genera una imagen a partir de `prompt` (bytes) con el modelo por defecto.

    Atajo de `generar_imagen_detallado` para los llamadores que solo quieren los bytes
    (estudio, auto-arte, pipeline). Lanza `MediaError` igual que aquel.
    """
    return generar_imagen_detallado(prompt).datos

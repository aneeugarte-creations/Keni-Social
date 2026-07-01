"""Quitar fondo (recorte del sujeto) de una imagen — rembg server-side.

Toma los bytes de una imagen y devuelve un PNG con alpha (fondo transparente). Es OPCIONAL: si
`rembg` no está instalado en el servidor, `disponible()` es False y el endpoint responde 503 (la UI
degrada, no revienta). El modelo se carga una sola vez por proceso: la sesión de rembg se cachea.
"""

from __future__ import annotations

import io
import threading

_MODELO = "u2net"

_sesion = None
_lock = threading.Lock()


class FondoError(Exception):
    """Error de dominio al quitar el fondo (mensaje en español, sin traceback al cliente)."""


def disponible() -> bool:
    """¿Está `rembg` instalado en este servidor?"""
    try:
        import rembg  # noqa: F401
    except Exception:
        return False
    return True


def _obtener_sesion():  # noqa: ANN202 -- tipo de rembg, opcional
    """Sesión rembg cacheada por proceso: carga el modelo una sola vez (thread-safe)."""
    global _sesion
    if _sesion is None:
        with _lock:
            if _sesion is None:
                from rembg import new_session

                _sesion = new_session(_MODELO)
    return _sesion


def quitar_fondo(datos: bytes) -> bytes:
    """Recorta el sujeto de `datos` (una imagen) -> PNG con el fondo transparente.

    Lanza `FondoError` (en español) si rembg no está disponible o la imagen no se puede procesar.
    """
    if not datos:
        raise FondoError("La imagen está vacía.")
    try:
        from PIL import Image
        from rembg import remove
    except Exception as e:  # rembg/Pillow no instalados
        raise FondoError(
            "La herramienta de quitar fondo no está disponible en este servidor."
        ) from e
    try:
        origen = Image.open(io.BytesIO(datos)).convert("RGBA")
        salida = remove(origen, session=_obtener_sesion())  # PIL Image RGBA con alpha
        buf = io.BytesIO()
        salida.save(buf, format="PNG")
        return buf.getvalue()
    except FondoError:
        raise
    except Exception as e:
        raise FondoError("No se pudo quitar el fondo de la imagen.") from e

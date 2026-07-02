"""Assets de marca (logo / marca de agua / pleca) por marca — MOCKS sustituibles.

DECISION DE DIRECCION (plan §5): los assets de marca YA existen (no criticos); se
arranca con MOCKS ahora y se sustituyen por los oficiales SIN tocar codigo. Este
modulo es la fuente unica de "donde esta el asset de una marca" para el flujo de
arte multi-formato, con esta cascada de resolucion (la primera que exista gana):

  1. OFICIAL en disco: `<dir-assets>/<marca>/<tipo>.png` — el equipo deja aqui el PNG
     oficial (logo transparente, marca de agua, pleca) y el flujo lo usa tal cual.
  2. MOCK generado: si no hay oficial, se genera un PNG mock determinista (wordmark de
     la marca en su rojo) y se cachea en disco. Es un placeholder util, no "cara de IA".

El DIRECTORIO es configurable por entorno (`KENI_MARCA_ASSETS_DIR`); por defecto cuelga
de la config de la consola (`rutas.dir_config()/marca_assets`, junto a las plantillas de
marca). Asi el path/archivo de cada marca es configurable y los oficiales entran dejando
el PNG en su carpeta, sin desplegar codigo nuevo.

Devuelve SIEMPRE una RUTA de disco (lo que esperan los motores `componer`/render Node),
nunca un id de media: el asset de marca es un activo de la CASA (versionable como fichero),
no un objeto subido por pieza. Sin red. Pillow solo se usa para fabricar el mock.
"""

from __future__ import annotations

import os
from pathlib import Path

from keni_shared import marcas

from . import rutas

# Tipos de asset de marca soportados (un PNG por tipo y marca).
TIPO_LOGO = "logo"
TIPO_MARCA_AGUA = "marca-agua"
TIPO_PLECA = "pleca"
TIPOS = (TIPO_LOGO, TIPO_MARCA_AGUA, TIPO_PLECA)

# Override de la raiz del store de assets (maxima prioridad; util en tests).
ENV_ASSETS_DIR = "KENI_MARCA_ASSETS_DIR"
_SUBDIR = "marca_assets"

# Color de marca por defecto para el mock (cae a un rojo generico si la marca no es visual).
_ROJO_POR_MARCA = {
    "unotv": (227, 6, 19),        # #E30613
    "claro-sports": (207, 46, 46),  # #CF2E2E
    "fundacion": (217, 119, 6),   # #D97706 (ambar; color de zona de la marca en la consola)
}
_ROJO_GENERICO = (227, 6, 19)
_BLANCO = (255, 255, 255)

# Tamano nominal del mock por tipo (transparente, para superponer).
_TAMANO_MOCK = {
    TIPO_LOGO: (480, 160),
    TIPO_MARCA_AGUA: (360, 120),
    TIPO_PLECA: (1080, 120),
}


class MarcaAssetError(RuntimeError):
    """Error al resolver/fabricar un asset de marca, con mensaje en espanol."""


def _raiz() -> Path:
    """Raiz del store de assets: `KENI_MARCA_ASSETS_DIR` o `dir_config()/marca_assets`."""
    if env := os.environ.get(ENV_ASSETS_DIR):
        return Path(env).expanduser()
    return rutas.dir_config() / _SUBDIR


def _dir_marca(marca: str) -> Path:
    return _raiz() / marca


def ruta_oficial(marca: str, tipo: str) -> Path:
    """Ruta del PNG OFICIAL esperado (exista o no): `<raiz>/<marca>/<tipo>.png`."""
    return _dir_marca(marca) / f"{tipo}.png"


def _ruta_mock(marca: str, tipo: str) -> Path:
    """Ruta del PNG MOCK cacheado: `<raiz>/<marca>/<tipo>.mock.png`."""
    return _dir_marca(marca) / f"{tipo}.mock.png"


def _rojo(marca: str) -> tuple[int, int, int]:
    return _ROJO_POR_MARCA.get(marca, _ROJO_GENERICO)


def _fabricar_mock(marca: str, tipo: str, destino: Path) -> None:
    """Genera un PNG mock determinista (wordmark/banda en el rojo de la marca) en `destino`.

    Pillow se importa AQUI (no a nivel de modulo) para que importar este modulo no exija
    Pillow salvo cuando hay que fabricar un mock. El mock es un placeholder honesto: el
    nombre de la marca sobre su color, sin pretension de ser el arte oficial.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:  # pragma: no cover - entorno sin Pillow
        raise MarcaAssetError(
            "Falta Pillow para generar el mock del asset de marca."
        ) from e

    w, h = _TAMANO_MOCK.get(tipo, _TAMANO_MOCK[TIPO_LOGO])
    rojo = _rojo(marca)
    texto = marcas.etiqueta_de(marca) if marcas.es_marca(marca) else marca

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if tipo == TIPO_PLECA:
        # Pleca: banda solida de marca, texto blanco (ej. "ULTIMA HORA" sustituible).
        draw.rectangle([0, 0, w, h], fill=rojo + (235,))
        relleno = _BLANCO
        margen = 28
    else:
        # Logo / marca de agua: chip redondeado con el wordmark de la marca.
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=18, fill=rojo + (235,))
        relleno = _BLANCO
        margen = 24

    fuente = _cargar_fuente(int(h * 0.42))
    # Centrado vertical aproximado; alineado a la izquierda con margen.
    try:
        bbox = draw.textbbox((0, 0), texto, font=fuente)
        th = bbox[3] - bbox[1]
        ty = max(0, (h - th) // 2 - bbox[1])
    except Exception:  # noqa: BLE001 -- bbox puede fallar con fuente default antigua
        ty = h // 3
    draw.text((margen, ty), texto, font=fuente, fill=relleno)

    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "PNG")


def _cargar_fuente(tam: int):
    """Primera fuente bold disponible al tamano pedido; default escalable si no hay."""
    from PIL import ImageFont

    candidatas = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    )
    for ruta in candidatas:
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow < 10
        return ImageFont.load_default()


def ruta_asset(marca: str, tipo: str = TIPO_LOGO, *, fabricar_mock: bool = True) -> str:
    """Ruta de disco al asset de una marca (oficial si existe; si no, mock).

    Cascada: PNG oficial (`<marca>/<tipo>.png`) -> mock cacheado (`<tipo>.mock.png`).
    Si no hay mock y `fabricar_mock`, lo genera y cachea. Devuelve "" solo si no se puede
    fabricar el mock (sin Pillow) y no hay oficial, para que el flujo degrade al wordmark
    de texto del motor (nunca rompe).
    """
    if tipo not in TIPOS:
        raise MarcaAssetError(f"Tipo de asset desconocido: {tipo}. Usa: {', '.join(TIPOS)}.")
    oficial = ruta_oficial(marca, tipo)
    if oficial.is_file():
        return str(oficial)
    mock = _ruta_mock(marca, tipo)
    if mock.is_file():
        return str(mock)
    if not fabricar_mock:
        return ""
    try:
        _fabricar_mock(marca, tipo, mock)
    except MarcaAssetError:
        return ""
    return str(mock)


def tiene_oficial(marca: str, tipo: str = TIPO_LOGO) -> bool:
    """True si la marca tiene el asset OFICIAL en disco (no el mock)."""
    return ruta_oficial(marca, tipo).is_file()

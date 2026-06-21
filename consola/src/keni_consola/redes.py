"""Fuente UNICA de verdad de las REDES sociales destino de copy en la Consola.

Cada red tiene:
  - `id`      identificador estable en minusculas que usan API y persistencia
              (p.ej. `x`, `instagram`). Es lo que viaja en JSON y en la columna
              `red` de `piezas`.
  - `nombre`  nombre HUMANO legible (p.ej. "X", "Instagram"). Lo unico que ve la
              persona en la UI.
  - `limite`  limite DURO de caracteres de la red, o `None` cuando no hay un tope
              tecnico practico (Facebook/YouTube). NO se redefine aqui: viene de
              la fuente unica `limites_plataforma.LIMITES`, de donde tambien
              la lee el frontend (`GET /api/limites`).

Sin estado ni I/O: solo datos y funciones puras. El orden de `REDES` es FIJO y se
respeta en toda la consola (UI, opciones, generacion por red).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import limites_plataforma


@dataclass(frozen=True)
class Red:
    """Una red social destino de copy. Ver el docstring del modulo."""

    id: str
    nombre: str
    limite: int | None


# Orden de presentacion estable (X, Instagram, Facebook, TikTok, YouTube). Los
# nombres viven aqui; el `limite` se toma de la fuente unica `limites_plataforma`.
REDES: tuple[Red, ...] = (
    Red(id="x", nombre="X", limite=limites_plataforma.limite_de("x")),
    Red(id="instagram", nombre="Instagram", limite=limites_plataforma.limite_de("instagram")),
    Red(id="facebook", nombre="Facebook", limite=limites_plataforma.limite_de("facebook")),
    Red(id="tiktok", nombre="TikTok", limite=limites_plataforma.limite_de("tiktok")),
    Red(id="youtube", nombre="YouTube", limite=limites_plataforma.limite_de("youtube")),
)

# Indice id->Red para acceso O(1). Construido una sola vez al importar.
_POR_ID: dict[str, Red] = {r.id: r for r in REDES}


def es_red(red_id: str) -> bool:
    """True si `red_id` es una red canonica conocida."""
    return red_id in _POR_ID


def nombre_por_id(red_id: str) -> str:
    """Nombre humano desde el `id`; cae al propio id si no se conoce."""
    red = _POR_ID.get(red_id)
    return red.nombre if red is not None else red_id


def ids() -> list[str]:
    """Lista de `id` de todas las redes, en orden de presentacion."""
    return [r.id for r in REDES]


def opciones() -> list[dict[str, object]]:
    """Lista `[{id, nombre, limite}]` para poblar la UI, en orden fijo."""
    return [{"id": r.id, "nombre": r.nombre, "limite": r.limite} for r in REDES]


# --------------------------------------------------------------------------- #
# FORMATO de pieza -> REDES destino (fuente UNICA del mapeo)                   #
# --------------------------------------------------------------------------- #
#
# Regla del dueño: el FORMATO de la pieza decide a qué redes va.
#   - FOTO     -> 3 redes (instagram, x, facebook).
#   - VIDEO    -> las 5 (instagram, x, facebook, tiktok, youtube).
#   - CARRUSEL -> 2 redes (instagram, facebook): las que publican carruseles
#     nativos vía el scheduler de Metricool (varias media en un solo post). La
#     pieza lleva PORTADA compuesta (placa) como primer slide y el resto del
#     media va EN CRUDO (campo `carrusel` de la fila por plataforma).
#
# El flujo automático (auto-feed + pipeline) no sabe de antemano si un ítem será
# foto o video, así que crea piezas de FOTO (3 redes) explícitamente. El mapeo de
# VIDEO queda definido aquí para que cualquier flujo futuro lo use sin redefinirlo.
# Las redes se FILTRAN contra `es_red` y se devuelven en el orden de `REDES`.

FORMATO_FOTO = "foto"
FORMATO_VIDEO = "video"
FORMATO_CARRUSEL = "carrusel"

# Formatos cuyo asset principal es una IMAGEN (portada/placa): comparten checklist
# (`falta_imagen`) y parte visual (foto cruda + plantilla); el video es N/A en ellos.
FORMATOS_IMAGEN: tuple[str, ...] = (FORMATO_FOTO, FORMATO_CARRUSEL)

# Subconjunto de redes por formato (ids canónicos; el orden lo fija `REDES`).
# FOTO y CARRUSEL (asset = imagen) van SOLO a Instagram/X/Facebook; YouTube y TikTok son redes
# de VÍDEO y NUNCA reciben piezas de imagen. El vídeo va a las cinco.
_REDES_POR_FORMATO: dict[str, tuple[str, ...]] = {
    FORMATO_FOTO: ("instagram", "x", "facebook"),
    FORMATO_VIDEO: ("instagram", "x", "facebook", "tiktok", "youtube"),
    FORMATO_CARRUSEL: ("instagram", "x", "facebook"),
}

# Etiquetas humanas del formato para la UI.
_ETIQUETA_FORMATO: dict[str, str] = {
    FORMATO_FOTO: "Foto",
    FORMATO_VIDEO: "Video",
    FORMATO_CARRUSEL: "Carrusel",
}


def normalizar_formato(formato: str | None) -> str:
    """Formato canónico (`foto`|`video`|`carrusel`); cae a `foto` ante vacío/desconocido (PURO)."""
    f = (formato or "").strip().lower()
    return f if f in _REDES_POR_FORMATO else FORMATO_FOTO


def redes_de_formato(formato: str | None) -> tuple[str, ...]:
    """Redes destino de un FORMATO de pieza, en el orden de `REDES` (PURO, testeable).

    `foto` y `carrusel` -> (instagram, x, facebook); `video` -> las 5. Vacío/desconocido ->
    `foto`. YouTube/TikTok NUNCA reciben imagen (solo vídeo).
    Filtra por `es_red` (si el catálogo cambiara, las redes inexistentes se omiten).
    """
    pedidas = set(_REDES_POR_FORMATO[normalizar_formato(formato)])
    return tuple(r for r in ids() if r in pedidas and es_red(r))


def etiqueta_formato(formato: str | None) -> str:
    """Etiqueta humana del formato para la UI ("Foto"/"Video"/"Carrusel"). Desconocido -> "Foto"."""
    return _ETIQUETA_FORMATO[normalizar_formato(formato)]

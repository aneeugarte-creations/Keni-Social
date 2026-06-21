"""Fuente UNICA de verdad de los LIMITES DE CARACTERES por plataforma.

`limite` es el TOPE TECNICO DURO de caracteres de la red, o `None` cuando no hay
un tope practico (Facebook / YouTube descripcion). No es la recomendacion
editorial (esa vive en `plataformas.md`).

TikTok: el caption admite hasta 4.000 caracteres (lo editorial sigue siendo corto;
eso lo dice la skill, no este tope). Ver el porque en el docstring de `LIMITES`
y en `plataformas.md`.

X: 25.000 es el limite del post con X Premium. Lo editorial (concision) lo dice
`plataformas.md`, no este tope.

Sin estado ni I/O: solo datos y funciones puras. El orden es FIJO (igual que en
`redes.REDES`): X, Instagram, Facebook, TikTok, YouTube.
"""

from __future__ import annotations

# Limites tecnicos duros por id de red (None = sin tope practico).
#
# Justificacion de cada valor:
#   - x          25000 : limite del post con X Premium.
#   - instagram  2200  : limite del caption.
#   - facebook   None  : el tope es enorme (~63k); a efectos editoriales, sin tope.
#   - tiktok     4000  : maximo tecnico del caption.
#   - youtube    None  : la DESCRIPCION no tiene tope practico (5000). El TITULO si
#                        tiene tope (100) pero ese es un campo distinto del cuerpo de
#                        copy; no se modela aqui como "limite de la red".
LIMITES: dict[str, int | None] = {
    "x": 25000,
    "instagram": 2200,
    "facebook": None,
    "tiktok": 4000,
    "youtube": None,
}


def limite_de(red_id: str) -> int | None:
    """Limite de caracteres de una red por su `id`; `None` si no tiene tope o si
    la red no se conoce (defensivo: ante un id desconocido no inventamos un tope).
    """
    return LIMITES.get(red_id)


def como_lista() -> list[dict[str, object]]:
    """Lista `[{id, limite}]` en el orden fijo de las redes, para poblar la UI."""
    return [{"id": rid, "limite": lim} for rid, lim in LIMITES.items()]


# Especificaciones BASICAS de VIDEO por red (Ola VIDEO). INFORMATIVAS, no son topes
# duros: la UI las usa para AVISAR (best-effort), no para bloquear la subida. El backend
# solo aplica el limite de tamano global de subida (`config.video_max_mb`, def 300 MB); estos
# valores orientan al equipo sobre qué dura/pesa/encuadre van bien en cada red. Valores
# conservadores y redondos (no exhaustivos; las plataformas cambian sus topes a menudo):
#   - duracion_s : duracion MAXIMA practica recomendada (s).
#   - max_mb     : peso MAXIMO practico recomendado (MB).
#   - aspecto    : relacion de aspecto sugerida ("9:16" vertical, "16:9" horizontal, "1:1").
# Mismo orden fijo que `LIMITES` (X, Instagram, Facebook, TikTok, YouTube).
VIDEO_SPECS: dict[str, dict[str, object]] = {
    "x": {"duracion_s": 140, "max_mb": 512, "aspecto": "16:9"},
    "instagram": {"duracion_s": 90, "max_mb": 250, "aspecto": "9:16"},
    "facebook": {"duracion_s": 240, "max_mb": 1024, "aspecto": "9:16"},
    "tiktok": {"duracion_s": 600, "max_mb": 500, "aspecto": "9:16"},
    "youtube": {"duracion_s": 60, "max_mb": 1024, "aspecto": "9:16"},
}


def video_specs_de(red_id: str) -> dict[str, object] | None:
    """Specs de VIDEO sugeridas de una red por su `id`; `None` si la red no se conoce.

    INFORMATIVO (avisos en la UI), no es un tope duro. Ver `VIDEO_SPECS`.
    """
    return VIDEO_SPECS.get(red_id)


def video_specs_como_lista() -> list[dict[str, object]]:
    """Lista `[{id, duracion_s, max_mb, aspecto}]` en el orden fijo de las redes, para la UI."""
    return [{"id": rid, **specs} for rid, specs in VIDEO_SPECS.items()]

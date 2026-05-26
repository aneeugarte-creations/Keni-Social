"""Fuente UNICA de verdad de los LIMITES DE CARACTERES por plataforma.

Antes los limites estaban duplicados en tres sitios sin enlace (#112 / H7):
  - `redes.py` (backend, dataclass `Red.limite`),
  - `consola/frontend/src/pages/publicaciones/meta.ts` (dict `META_REDES`),
  - `skills-copy/contexto-editorial/plataformas.md` (prosa de la skill).

Esto los centraliza en el backend. `redes.py` consume estos valores (no los
redefine), el frontend los lee por `GET /api/limites` y el guard estatico de
skills (`skills-copy/evals/test_limites.py`) verifica que `plataformas.md`
coincide con esta tabla.

`limite` es el TOPE TECNICO DURO de caracteres de la red, o `None` cuando no hay
un tope practico (Facebook / YouTube descripcion). No es la recomendacion
editorial (esa vive en `plataformas.md`).

TikTok: el caption admite hasta 4.000 caracteres desde la ampliacion de 2023-24
(antes eran 2.200). Tomamos 4.000 como el limite tecnico ACTUAL real (lo editorial
sigue siendo corto; eso lo dice la skill, no este tope). Ver el porque en el
docstring de `LIMITES` y en `plataformas.md`.

Sin estado ni I/O: solo datos y funciones puras. El orden es FIJO (igual que en
`redes.REDES`): X, Instagram, Facebook, TikTok, YouTube.
"""

from __future__ import annotations

# Limites tecnicos duros por id de red (None = sin tope practico).
#
# Justificacion de cada valor:
#   - x          280   : limite duro del tuit (cuerpo del post).
#   - instagram  2200  : limite del caption.
#   - facebook   None  : el tope es enorme (~63k); a efectos editoriales, sin tope.
#   - tiktok     4000  : caption ampliado (2023-24). Antes 2200; ahora 4000 es el
#                        maximo tecnico actual. Reconcilia la divergencia de #112
#                        (meta.ts decia 2200; plataformas.md decia "2200/4000").
#   - youtube    None  : la DESCRIPCION no tiene tope practico (5000). El TITULO si
#                        tiene tope (100) pero ese es un campo distinto del cuerpo de
#                        copy; no se modela aqui como "limite de la red".
LIMITES: dict[str, int | None] = {
    "x": 280,
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

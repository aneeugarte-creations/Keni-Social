"""Fuente UNICA de verdad de las REDES sociales destino de copy en la Consola.

Cada red tiene:
  - `id`      identificador estable en minusculas que usan API y persistencia
              (p.ej. `x`, `instagram`). Es lo que viaja en JSON y en la columna
              `red` de `publicaciones`.
  - `nombre`  nombre HUMANO legible (p.ej. "X", "Instagram"). Lo unico que ve la
              persona en la UI.
  - `limite`  limite DURO de caracteres de la red, o `None` cuando no hay un tope
              tecnico practico (Facebook/YouTube). Coincide con
              `skills-copy/contexto-editorial/plataformas.md`.

Sin estado ni I/O: solo datos y funciones puras. El orden de `REDES` es FIJO y se
respeta en toda la consola (UI, opciones, generacion por red).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Red:
    """Una red social destino de copy. Ver el docstring del modulo."""

    id: str
    nombre: str
    limite: int | None


# Orden de presentacion estable (X, Instagram, Facebook, TikTok, YouTube).
REDES: tuple[Red, ...] = (
    Red(id="x", nombre="X", limite=280),
    Red(id="instagram", nombre="Instagram", limite=2200),
    Red(id="facebook", nombre="Facebook", limite=None),
    Red(id="tiktok", nombre="TikTok", limite=2200),
    Red(id="youtube", nombre="YouTube", limite=None),
)

# Indice id->Red para acceso O(1). Construido una sola vez al importar.
_POR_ID: dict[str, Red] = {r.id: r for r in REDES}


def red_por_id(red_id: str) -> Red | None:
    """Devuelve la `Red` con ese `id`, o `None` si no existe."""
    return _POR_ID.get(red_id)


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

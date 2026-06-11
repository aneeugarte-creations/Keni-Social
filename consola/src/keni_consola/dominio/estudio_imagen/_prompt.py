"""Estudio de imagen — composición del PROMPT generativo y generación de UNA variante (IA).

Submódulo de área del paquete `dominio.estudio_imagen`. La red la toca SOLO `media.generar_imagen`
(mockeable): los tests nunca salen a internet.
"""

from __future__ import annotations

from typing import Any

from ... import libtexto, media
from ._comun import _ESTILO_MARCA, ASPECTOS, FORMATOS, PROMPT_IMAGEN_DEFECTO

__all__ = ["componer_prompt", "generar_variante"]


def componer_prompt(
    prompt: str, marca: str = "", formato: str = "feed", prompt_id: str = PROMPT_IMAGEN_DEFECTO
) -> str:
    """Arma el prompt de imagen: base de la Texto + lo pedido + estilo de marca + aspecto.

    El estilo de marca (hoy una constante) pasa a ser editable: si la Texto tiene el
    prompt base (`prompt/arte*`) gana esa version; la nota de marca es un complemento
    corto. NO volcamos la linea editorial de copy (voz) en un prompt de imagen: seria ruido.
    """
    formato = formato if formato in FORMATOS else "feed"
    base = libtexto.cuerpo_efectivo(prompt_id) or ""
    estilo = _ESTILO_MARCA.get(marca, "")
    aspecto = ASPECTOS[formato]
    partes = [
        base.strip(),
        (prompt or "").strip(),
        estilo,
        f"Formato {formato}, relacion de aspecto {aspecto}.",
    ]
    return "\n\n".join(p for p in partes if p)


def generar_variante(prompt_final: str) -> dict[str, Any]:
    """Genera UNA imagen con el proveedor y la guarda en el almacen -> `{id, url}`.

    Es el callable que corre `lanzar_job_imagen`. La red la toca SOLO `media.generar_imagen`
    (`_PROVEEDOR`, mockeable): los tests nunca salen a internet.
    """
    crudos = media.generar_imagen(prompt_final)
    nombre = media.guardar_bytes(crudos, ext="png")
    return {"id": nombre, "url": f"/api/media/{nombre}"}

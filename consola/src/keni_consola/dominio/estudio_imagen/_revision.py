"""Estudio de imagen — revisión legal/editorial (job `claude` que VE la imagen).

Submódulo de área del paquete `dominio.estudio_imagen`. Pasa un objeto de media por una revisión
con `claude -p` (gate humano, NO bloquea publicar) y devuelve el registro del job.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ... import libtexto, media
from .. import generar, jobspec
from ._comun import REGLAS_IMAGEN, EstudioError

__all__ = ["_instruccion_revision", "revisar"]


def _instruccion_revision(archivo: str) -> str:
    """Instruccion al revisor: mira la imagen adjunta y devuelve un checklist; NO aprueba."""
    return (
        f"Revisa la imagen adjunta `{archivo}` contra estas reglas de imagen y devuelve un "
        "checklist con un emoji por cada punto (✅ cumple · ⚠️ revisar · ❌ incumple), citando "
        "concretamente lo que VES en la imagen que justifica cada marca. No apruebes tu: tu "
        "salida es un INFORME para que un humano decida si publica. Si algo no se puede "
        "comprobar con la imagen, marcalo como ⚠️ y dilo, no lo inventes."
    )


def revisar(imagen: str, *, marca: str = "", autor: dict[str, str] | None = None) -> dict[str, Any]:
    """Pasa un objeto de media por una revision legal/editorial con `claude -p` -> registro.

    Es el gate humano (opcion §3.5.a del diseno): NO bloquea publicar. `claude` VE la imagen
    via `--add-dir` (materializada en un temporal) y aplica las reglas de imagen de la
    Texto (`editorial/reglas/imagen`); devuelve un checklist ✅/⚠️/❌. El texto en vivo
    queda en `salida` del registro (el frontend lo sondea). El post-procesado es IDENTIDAD
    (`PROC_PROMPT`): no crea piezas ni artefactos.

    El temporal NO lo borramos aqui: `generar.lanzar` lo pasa como `--add-dir` y lo limpia al
    terminar el job (igual que las subidas de copy/clip).
    """
    datos = media.leer_media(imagen)
    if datos is None:
        raise EstudioError("Esa imagen no existe en el almacen.")

    # Materializa la imagen en un temporal PERSISTENTE (sin context manager): `generar.lanzar`
    # lo borra al terminar el job. Conserva la extension para que `claude` la abra bien.
    carpeta = Path(tempfile.mkdtemp(prefix="keni-revision-"))
    ext = Path(imagen).suffix.lower() or ".png"
    archivo = f"imagen{ext}"
    (carpeta / archivo).write_bytes(datos)

    reglas = libtexto.cuerpo_efectivo(REGLAS_IMAGEN) or ""
    prompt = generar.componer(
        _instruccion_revision(archivo),
        [],
        ("REGLAS DE IMAGEN:\n\n" + reglas) if reglas else "",
    )

    return generar.lanzar(
        tipo="qa-editorial",
        titulo="Revisión de imagen",
        marca=marca,
        prompt=prompt,
        procesar=jobspec.reconstruir_procesar({"procesar": jobspec.construir_prompt_lib()}),
        procesar_spec=jobspec.construir_prompt_lib(),
        dir_temporal=carpeta,
        autor=autor,
    )

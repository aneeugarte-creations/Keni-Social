"""Migración one-shot: piezas derivables de receta -> `imagen` vacío (render ON-DEMAND).

Antes cada pieza horneaba y PERSISTÍA un PNG con el logo + pleca + titular (+ foto). Ahora la
imagen publicable se DERIVA de la receta (marca + foto + copy_in + foto_encuadre + plantilla) y
se renderiza on-demand (`/api/publicaciones/{id}/compuesta`, content-addressed). Esta migración
vacía `imagen` en las piezas cuya composición es RECONSTRUIBLE desde su receta, para que dejen de
apuntar a un PNG horneado. Esos PNG quedan huérfanos y los recicla el GC de media.

CONSERVADORA — solo vacía `imagen` cuando es SEGURO:
  - la pieza tiene RECETA (`render_pieza.tiene_receta`: placa de marca o plantilla del estudio,
    no placa oculta), Y
  - NO es una composición BESPOKE del editor pro (sin versiones de documento por pieza:
    `repos.listar_documento_versiones`), cuya imagen NO se reconstruye desde la receta simple.
Las piezas sin receta (imagen subida/generada, fuente, solo-foto) y las bespoke CONSERVAN su
`imagen`. Idempotente: una pieza ya vaciada se salta (no tiene `imagen`).

    docker compose exec -T back python -m keni_consola.migrar_render_ondemand
    # simulación (no escribe): añade --dry-run
"""

from __future__ import annotations

import sys
from typing import Any

from . import repos
from .dominio import render_pieza


def _es_bespoke(pub: dict[str, Any]) -> bool:
    """True si la pieza tiene una composición bespoke del editor pro (versiones de documento)."""
    contenido_id = pub.get("contenido_id") or ""
    plataforma_id = pub.get("id") or ""
    if not plataforma_id:
        return False
    try:
        versiones = repos.listar_documento_versiones(contenido_id, plataforma_id)
    except Exception:  # noqa: BLE001 -- ante la duda, NO migrar (se trata como bespoke)
        return True
    return bool(versiones)


def migrar_una(pub: dict[str, Any], *, dry_run: bool) -> str:
    """Decide y aplica la migración de UNA pieza. Devuelve el estado para el log."""
    if not (pub.get("imagen") or "").strip():
        return "sin-imagen"  # ya está en render on-demand (o nunca tuvo placa)
    if not render_pieza.tiene_receta(pub):
        return "conserva-sin-receta"  # imagen subida/generada/fuente: es un asset real
    if _es_bespoke(pub):
        return "conserva-bespoke"  # composición del editor pro: no reconstruible desde receta
    if dry_run:
        return "vaciaria"
    actualizada = repos.actualizar_publicacion(pub["id"], {"imagen": ""})
    return "vaciada" if actualizada is not None else "carrera"


def main(argv: list[str] | None = None) -> None:
    dry_run = "--dry-run" in (argv if argv is not None else sys.argv[1:])
    conteo: dict[str, int] = {}
    for pub in repos.listar_publicaciones():
        try:
            estado = migrar_una(pub, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 -- no abortar el resto por una pieza
            estado = f"error: {exc}"
        conteo[estado] = conteo.get(estado, 0) + 1
    etiqueta = "DRY-RUN" if dry_run else "APLICADO"
    print(f"[migrar_render_ondemand · {etiqueta}]")
    for estado, n in sorted(conteo.items()):
        print(f"  {estado}: {n}")


if __name__ == "__main__":
    main()

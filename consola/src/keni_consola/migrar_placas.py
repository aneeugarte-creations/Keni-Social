"""Migración one-shot: la PLACA DE MARCA (spec) -> una plantilla del estudio por marca.

Unifica los dos sistemas de plantilla. Hasta ahora la "placa de marca" (chip + degradado +
titular) vivía en `spec_plantilla`/`plantillas_marca` (un motor aparte) y las plantillas del
estudio en `PlantillaDiseno` (otro). Esta migración convierte la placa de cada marca en una
`PlantillaDiseno` editable —con su HUECO DE FOTO a sangre (`es_foto`)— para que viva en la misma
galería por marca que el resto. Así el editor puede unificarse en un solo sistema.

Idempotente: si la marca ya tiene una plantilla llamada "Placa de marca", no la duplica. Se
ejecuta a mano en el servidor (el back tiene Node para renderizar la miniatura):

    docker compose exec -T back python -m keni_consola.migrar_placas
"""

from __future__ import annotations

import json

from . import marcas, plantillas_marca, repos
from .dominio import estudio_imagen
from .motores.estudio_imagen import documento as doc_capas

NOMBRE_PLACA = "Placa de marca"
# Formato 4:5 (regla de producto: todo post de foto es 4:5). Migramos solo ese lienzo.
FORMATO_FEED = "feed"


def _ya_migrada(marca_id: str) -> bool:
    """¿La marca ya tiene su plantilla 'Placa de marca' en el estudio?"""
    existentes = repos.listar_plantillas_diseno(marca=marca_id)
    return any((p.get("nombre") or "").strip() == NOMBRE_PLACA for p in existentes)


def migrar_una(marca_id: str) -> str:
    """Crea la plantilla del estudio para la placa de UNA marca. Devuelve el estado para el log."""
    if _ya_migrada(marca_id):
        return "ya-existe"
    spec = plantillas_marca.obtener_spec(marca_id)
    documento = doc_capas.desde_spec(spec, FORMATO_FEED)  # incluye el hueco de foto (es_foto)
    # Miniatura best-effort: render del documento con un titular de muestra (el hueco va vacío =>
    # placeholder). Si Node no está disponible, se crea sin miniatura (la galería usa respaldo).
    miniatura = ""
    try:
        resultado = estudio_imagen.renderizar_documento(
            documento, bindings={"copy_in": "Titular de ejemplo"}
        )
        miniatura = resultado.get("id", "")
    except Exception:  # noqa: BLE001 — best-effort; la plantilla se crea igual sin miniatura
        miniatura = ""
    repos.crear_plantilla_diseno(
        marca=marca_id,
        nombre=NOMBRE_PLACA,
        categoria="post",
        documento=json.dumps(documento, ensure_ascii=False),
        miniatura=miniatura,
    )
    return "creada" if miniatura else "creada-sin-miniatura"


def main() -> None:
    for marca_id in marcas.ids():
        try:
            estado = migrar_una(marca_id)
        except Exception as exc:  # noqa: BLE001 — no abortar el resto de marcas por una
            estado = f"error: {exc}"
        print(f"{marca_id}: {estado}")


if __name__ == "__main__":
    main()

"""Guardas previas al encolado, compartidas por los botones manuales de generación de copy.

Los caminos manuales (usar historia/ítem, empujar insumo, preparar breaking, aportar) encolan
copy con `autogen_redactar.lanzar_para_topic(..., manual=True)`. Si la etapa «Redactar» está
apagada para la marca, encolar dejaría un tema sin copy y un toast «Copy en marcha» mentiroso:
estas guardas cortan ANTES de crear nada y devuelven un 409 que dice cómo encenderla. El maestro
auto (`KENI_MAQUINA`) NO se mira aquí: el botón es acción humana, solo respeta el toggle de etapa.
"""

from __future__ import annotations

from .. import config, marcas


def redactar_apagado(marca: str) -> dict | None:
    """Cuerpo de error 409 si «Redactar» está apagada para `marca` (global o `::marca`); None si no.

    Misma fuente de verdad que el daemon y la vista Pipelines (`config.etapa_activa`).
    """
    if not config.etapa_activa(config.ENV_PIPELINE_REDACTAR, marca):
        nombre = marcas.etiqueta_de(marca)
        return {
            "error": (
                f"La etapa «Redactar» está apagada para «{nombre}». "
                "Enciéndela en Máquina → Contexto → Producción para generar copy."
            ),
            "etapa_apagada": "redactar",
            "marca": marca,
        }
    return None

"""Repositorio — dominio historial. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
    ficheros,
)

# --------------------------------------------------------------------------- #
# Historial de prompts (CONTENIDO: ficheros YAML via ficheros.py)              #
# --------------------------------------------------------------------------- #


def registrar_historial_prompt(
    prompt_id: str,
    marca: str,
    resultado: str,
    *,
    piezas: list[dict[str, Any]] | None = None,
    titulo: str = "",
    metricas: dict[str, Any] | None = None,
    autor: dict[str, str] | None = None,
) -> str:
    return ficheros.registrar_historial_prompt(
        prompt_id, marca, resultado, piezas=piezas, titulo=titulo, metricas=metricas, autor=autor
    )


def listar_historial_prompts(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return ficheros.listar_historial_prompts(limite=limite, desplazamiento=desplazamiento)


def contar_historial_prompts() -> int:
    return ficheros.contar_historial_prompts()


def obtener_historial_prompt(historial_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_historial_prompt(historial_id)


def registrar_veredicto_qa(
    *,
    plataforma_id: str,
    contenido_id: str,
    verdicto: str,
    resumen: str = "",
    copy_hash: str = "",
    historial_id: str = "",
) -> str:
    """Persiste un veredicto del QA editorial ATADO a una pieza (item A). Devuelve su id."""
    return db.registrar_veredicto_qa(
        plataforma_id=plataforma_id,
        contenido_id=contenido_id,
        verdicto=verdicto,
        resumen=resumen,
        copy_hash=copy_hash,
        historial_id=historial_id,
    )


def ultimo_veredicto_qa(
    plataforma_id: str, contenido_id: str = ""
) -> dict[str, Any] | None:
    """Ultimo veredicto del QA editorial VIGENTE de una pieza, o None si no hay/expiro (item B/D).

    Lee el ultimo veredicto persistido para `plataforma_id` (`db.ultimo_veredicto_qa`) y lo
    INVALIDA si el copy de la pieza cambio despues del QA: compara el `copy_hash` del veredicto
    con el hash del copy ACTUAL de la fila. Si no coinciden (el copy se reescribio tras la
    revision), devuelve None -> el nivel automatico de QA queda `pendiente` (lo decide un humano),
    que es el comportamiento CONSERVADOR y seguro. Si coinciden (o el veredicto no guardo hash,
    p. ej. registros viejos), devuelve `{"verdicto", "resumen"}` para resolver el nivel.
    """
    if not plataforma_id:
        return None
    registro = db.ultimo_veredicto_qa(plataforma_id)
    if not registro:
        return None
    copy_hash_qa = (registro.get("copy_hash") or "").strip()
    if copy_hash_qa:
        # Import local: `dominio.qa_editorial` importa `repos` (evita ciclo en carga).
        from .dominio import qa_editorial as dom_qa

        plat = db.obtener_contenido_plataforma(plataforma_id)
        copy_actual = (plat or {}).get("copy", "") or ""
        if dom_qa.hash_copy(copy_actual) != copy_hash_qa:
            return None  # el copy cambio tras el QA: veredicto invalido, lo decide un humano.
    return {
        "verdicto": registro.get("verdicto", "") or "",
        "resumen": registro.get("resumen", "") or "",
    }

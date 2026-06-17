"""Imports y helpers COMPARTIDOS por los submódulos de `api/noticias/`.

Este módulo NO exporta `RUTAS` (su nombre va con `_`, así que el descubridor de
`api/__init__.py` ni lo escanea —vive dentro del subpaquete—). Reúne lo que más de un
handler del archivo de noticias necesita: validación de marca, filtrado de redes
iniciales, la serialización de un item del archivo y las constantes de paginación /
límites de texto. Los submódulos (`items.py`, `historias.py`) importan de aquí
EXPLÍCITAMENTE.
"""

from __future__ import annotations

from typing import Any

from ... import marcas, redes

# Paginación: defecto holgado (el archivo es un flujo continuo) y tope duro defensivo.
_LIMITE_DEFECTO = 50
_LIMITE_MAX = 200
_MAX_TITULO = 300
_MAX_TEXTO = 8000

def _validar_marca(valor: Any) -> tuple[str | None, str | None]:
    """`(marca, None)` o `(None, error)`. '' / None = todas (no filtra).

    Solo admite marcas de NOTICIAS (`marcas.es_noticias`): las de contenido propio
    (p. ej. piso-15/fundación) se saltan la investigación y no tienen panel de Noticias.
    """
    if valor is None:
        return "", None
    if not isinstance(valor, str):
        return None, "La marca debe ser texto."
    valor = valor.strip()
    if valor and not marcas.es_noticias(valor):
        return None, "Marca no permitida."
    return valor, None


def _redes_iniciales(crudo: Any) -> list[str]:
    """Filtra una lista de ids de red contra las canónicas (sin duplicar, en orden)."""
    if not isinstance(crudo, list):
        return []
    vistas: list[str] = []
    for r in crudo:
        if isinstance(r, str) and redes.es_red(r) and r not in vistas:
            vistas.append(r)
    return vistas


def _item_a_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Serializa un item del archivo resolviendo el nombre humano de la marca y su tier."""
    from ...dominio import fuentes_pesos

    return {
        **item,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        # Tier legible del peso de la fuente (potente/normal/baja): para el timeline del detalle.
        "tier": fuentes_pesos.tier_de_peso(float(item.get("fuente_peso") or 1.0)),
    }

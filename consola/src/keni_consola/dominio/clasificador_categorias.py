"""Clasifica una pieza en su CATEGORÍA (etiqueta clase 'categoria') y su ORIGEN (clase 'origen').

Determinístico y sin IA: casa las palabras clave (`keywords`, CSV de cada etiqueta) contra el
título + resumen de la nota, normalizando acentos y mayúsculas. Gana la categoría con más keywords
casados (empate → la primera, orden estable de entrada).

Diseño:
  - `clasificar(texto, etiquetas)` es PURO (sin BD): recibe las etiquetas candidatas y
    devuelve el id de la mejor o None. Fácil de testear.
  - `clasificar_pieza(titulo, resumen, marca)` es el envoltorio con BD: trae las etiquetas
    de la marca (categoria y origen) vía `repos` y devuelve `{categoria, origen}`.

Política de "sin categoría": si NINGUNA categoría casa, `categoria` queda None — la pieza NO se
descarta; quien llama la marca con un aviso. El ORIGEN nunca queda vacío: si ninguna etiqueta
de origen con keywords casa, se usa el ORIGEN POR DEFECTO (la etiqueta de origen sin keywords,
convención = 'interno').

La capa de IA de respaldo (clasificar lo ambiguo con `claude -p`) se enchufará después; este
módulo cubre el camino barato (0 tokens) que resuelve la mayoría.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalizar(texto: str) -> str:
    """Minúsculas sin acentos ni signos diacríticos (NFKD → ascii)."""
    base = unicodedata.normalize("NFKD", texto or "")
    base = base.encode("ascii", "ignore").decode("ascii")
    return base.lower()


def _keywords(etiqueta: dict[str, Any]) -> list[str]:
    """Lista normalizada de keywords de una etiqueta (CSV en `keywords`)."""
    crudo = etiqueta.get("keywords") or ""
    return [k for k in (_normalizar(p).strip() for p in crudo.split(",")) if k]


def _coincide(base: str, keyword: str) -> bool:
    """True si `keyword` aparece como palabra (límites de palabra) en `base` ya normalizado."""
    if not keyword:
        return False
    return re.search(rf"\b{re.escape(keyword)}\b", base) is not None


def contar_coincidencias(texto: str, etiqueta: dict[str, Any]) -> int:
    """Cuántos keywords de `etiqueta` casan en `texto` (para depurar/ordenar)."""
    base = _normalizar(texto)
    return sum(1 for kw in _keywords(etiqueta) if _coincide(base, kw))


def clasificar(texto: str, etiquetas: list[dict[str, Any]]) -> str | None:
    """Id de la etiqueta cuyos keywords mejor casan en `texto`, o None si ninguna casa.

    PURO: no toca la BD. Empate de coincidencias → la primera en el orden de `etiquetas`.
    """
    base = _normalizar(texto)
    mejor_id: str | None = None
    mejor_n = 0
    for et in etiquetas:
        n = sum(1 for kw in _keywords(et) if _coincide(base, kw))
        if n > mejor_n:
            mejor_n = n
            mejor_id = et.get("id")
    return mejor_id


def origen_por_defecto(origenes: list[dict[str, Any]]) -> str | None:
    """Id del origen FALLBACK = la etiqueta de origen SIN keywords (convención 'interno').

    Si ninguna está sin keywords, devuelve la primera (o None si la lista está vacía).
    """
    for et in origenes:
        if not _keywords(et):
            return et.get("id")
    return origenes[0].get("id") if origenes else None


def clasificar_pieza(titulo: str, resumen: str, marca: str) -> dict[str, str | None]:
    """Clasifica una pieza de `marca`: devuelve `{"categoria": id|None, "origen": id|None}`.

    `categoria` None = sin categoría (la pieza se marca con aviso, no se descarta). `origen` solo
    es None si la marca no tiene ninguna etiqueta de origen inicializada.
    """
    from .. import repos  # import perezoso: mantiene `clasificar` puro/testeable

    texto = f"{titulo or ''}\n{resumen or ''}"
    categorias = repos.listar_etiquetas(marca=marca, clase="categoria", solo_activas=True)
    origenes = repos.listar_etiquetas(marca=marca, clase="origen", solo_activas=True)

    categoria_id = clasificar(texto, categorias)
    # Origen: solo las que tienen keywords compiten; lo que no casa cae al fallback (interno).
    origenes_con_kw = [o for o in origenes if _keywords(o)]
    origen_id = clasificar(texto, origenes_con_kw) or origen_por_defecto(origenes)

    return {"categoria": categoria_id, "origen": origen_id}

"""Observabilidad de la TUBERIA automatica: en que ETAPA esta cada tema (Fase 2 / Flujo C).

PROBLEMA QUE RESUELVE
=====================
Los daemons (`radar_auto` -> `autogen_copy` -> `autogen_arte` -> revision) llevan cada tema
de "entrada" a "borrador completo en cola de revision", pero hoy NO hay forma de ver EN QUE
PUNTO esta cada pieza a lo largo de la cadena. Este modulo deriva, de las senales que YA
existen (estado de `contenido_plataforma`, presencia de copy/imagen, etiquetas de dedup
`autogen`/`autogen-arte`, origen auto-generable), la ETAPA de cada tema y CUENTA piezas por
etapa para un panel de un vistazo.

DISENO
======
PURO y testeable: `etapa_de_tema` y `contar_por_etapa` reciben dicts ya leidos (items del
tablero + sus filas por plataforma + sus etiquetas resueltas a NOMBRES); no tocan la BD ni
el disco. La capa `api/panel.py` lee `repos.*` y se las pasa. Determinista.

NO reescribe estados ni inventa un enum nuevo en `estados.py` (frontera con la coordinacion):
las etapas son una LECTURA derivada, no un campo persistido. El ciclo de vida real de una
fila sigue siendo `estados.ESTADOS_CONTENIDO_PLATAFORMA`.
"""

from __future__ import annotations

from typing import Any

from .estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN

# Etiquetas de dedup que ponen los daemons al ENCOLAR copy / arte (fuente unica: el valor
# que usan `autogen_copy.ETIQUETA_AUTOGEN` y `autogen_arte.ETIQUETA_AUTOGEN_ARTE`). Se
# replican aqui como literales para no acoplar este modulo neutro a los daemons (que
# importan config/media/etc.); si cambian alla, este modulo no compila menos, solo deja de
# distinguir "en cola" de "generando" (degrada con elegancia, no rompe).
ETIQUETA_AUTOGEN = "autogen"
ETIQUETA_AUTOGEN_ARTE = "autogen-arte"

# Estado terminal del contenido padre: ya no esta "en la tuberia".
_ESTADO_CERRADO = "hecha"

# --------------------------------------------------------------------------- #
# Etapas de la tuberia (orden = avance). Son una LECTURA derivada, no un enum   #
# persistido: NO viven en `estados.py` (no son estados del dominio).            #
# --------------------------------------------------------------------------- #
ETAPA_PRIORIZADA = "priorizada"          # tema auto-generable en cola, sin copy aun
ETAPA_GENERANDO_COPY = "generando_copy"  # copy ya encolado (etiqueta autogen), sin copy listo
ETAPA_GENERANDO_ARTE = "generando_arte"  # tiene copy pero le falta imagen (arte en curso/pendiente)
ETAPA_LISTA_REVISAR = "lista_para_revisar"  # copy + imagen listos / ya en revision o mas alla
ETAPA_FUERA = "fuera_de_tuberia"         # no entra a la auto-generacion (manual tecleado, tarea)

# Orden canonico para presentar los contadores (entrada -> salida -> fuera).
ETAPAS: tuple[str, ...] = (
    ETAPA_PRIORIZADA,
    ETAPA_GENERANDO_COPY,
    ETAPA_GENERANDO_ARTE,
    ETAPA_LISTA_REVISAR,
    ETAPA_FUERA,
)

# Estados de fila por plataforma que YA estan en revision o mas alla: la pieza salio de la
# fase de produccion automatica y vive en el gate humano (cola de revision/aprobacion).
_ESTADOS_EN_REVISION_O_MAS = frozenset(
    {"en_revision", "aprobado", "programado", "publicado"}
)

_ORIGENES_AUTOGEN = frozenset(ORIGENES_AUTOGEN)


def _norm(texto: object) -> str:
    return " ".join(("" if texto is None else str(texto)).strip().lower().split())


def _tiene_copy(plataforma: dict[str, Any]) -> bool:
    """True si la fila por plataforma tiene copy redactado (mismo criterio que autogen_arte)."""
    return bool((plataforma.get("copy") or "").strip())


def _tiene_imagen(plataforma: dict[str, Any]) -> bool:
    """True si la fila por plataforma tiene imagen adjunta (media compuesto)."""
    return bool((plataforma.get("imagen") or "").strip())


def _en_revision_o_mas(plataforma: dict[str, Any]) -> bool:
    """True si la fila por plataforma ya esta en revision/aprobado/programado/publicado."""
    return _norm(plataforma.get("estado")) in _ESTADOS_EN_REVISION_O_MAS


def etapa_de_tema(
    item: dict[str, Any],
    plataformas: list[dict[str, Any]],
    *,
    etiquetas: list[str] | None = None,
) -> str:
    """Etapa de la tuberia de UN tema (PURA). `etiquetas` = NOMBRES ya resueltos.

    Reglas, de la SALIDA hacia la ENTRADA (gana la mas avanzada que aplique):
      - clase != 'contenido' (una tarea) o estado padre 'hecha' (cerrado) -> FUERA.
      - origen NO auto-generable (alta tecleada legada `origen=""`, etc.) -> FUERA: la
        auto-generacion no lo toca (lo lleva el equipo a mano).
      - alguna plataforma en revision/aprobado/... O (con copy Y con imagen) -> LISTA_PARA_REVISAR.
      - alguna plataforma con copy pero SIN imagen -> GENERANDO_ARTE.
      - sin copy aun, pero ya etiquetado `autogen` (copy encolado) -> GENERANDO_COPY.
      - sin copy y sin encolar todavia -> PRIORIZADA (en cola de trabajo de la IA).

    Determinista; depende solo de sus argumentos.
    """
    etiquetas = etiquetas or []
    if (item.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
        return ETAPA_FUERA
    if _norm(item.get("estado")) == _ESTADO_CERRADO:
        return ETAPA_FUERA
    if (item.get("origen") or "") not in _ORIGENES_AUTOGEN:
        return ETAPA_FUERA

    # Salida: alguna pieza ya esta en revision o ya tiene copy + imagen (lista para aprobar).
    if any(_en_revision_o_mas(p) for p in plataformas):
        return ETAPA_LISTA_REVISAR
    if any(_tiene_copy(p) and _tiene_imagen(p) for p in plataformas):
        return ETAPA_LISTA_REVISAR

    # Tiene copy en alguna red pero le falta imagen: el arte esta en curso/pendiente.
    if any(_tiene_copy(p) for p in plataformas):
        return ETAPA_GENERANDO_ARTE

    # Sin copy todavia: distinguimos "ya encolado" (etiqueta autogen) de "en cola".
    nombres = {_norm(e) for e in etiquetas}
    if ETIQUETA_AUTOGEN in nombres:
        return ETAPA_GENERANDO_COPY
    return ETAPA_PRIORIZADA


def contar_por_etapa(
    items: list[dict[str, Any]],
    *,
    plataformas_por_item: dict[str, list[dict[str, Any]]] | None = None,
    etiquetas_por_item: dict[str, list[str]] | None = None,
    incluir_fuera: bool = False,
) -> dict[str, int]:
    """Cuenta temas por ETAPA de la tuberia (PURA). Devuelve un dict etapa -> n.

    `plataformas_por_item`: id de contenido -> sus filas `contenido_plataforma`.
    `etiquetas_por_item`:    id de contenido -> NOMBRES de etiqueta resueltos.
    Ambos se inyectan (los lee la capa API), de modo que esta funcion no toca la BD.

    Por defecto NO cuenta los temas FUERA de la tuberia (manual/tarea/cerrado): el panel
    quiere ver el flujo automatico. `incluir_fuera=True` los suma (etapa `fuera_de_tuberia`).
    El dict de salida SIEMPRE trae las etapas relevantes en 0 (forma estable para la UI).
    """
    plataformas_por_item = plataformas_por_item or {}
    etiquetas_por_item = etiquetas_por_item or {}

    etapas_salida = ETAPAS if incluir_fuera else ETAPAS[:-1]
    conteo: dict[str, int] = {e: 0 for e in etapas_salida}
    for item in items:
        cid = item.get("id") or ""
        etapa = etapa_de_tema(
            item,
            plataformas_por_item.get(cid, []),
            etiquetas=etiquetas_por_item.get(cid, []),
        )
        if etapa == ETAPA_FUERA and not incluir_fuera:
            continue
        conteo[etapa] = conteo.get(etapa, 0) + 1
    return conteo

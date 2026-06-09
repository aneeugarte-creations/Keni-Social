"""Generacion de COPY para un tema del tablero (lanzador reutilizable).

PROBLEMA QUE RESUELVE
Varios caminos del producto necesitan ENCOLAR la generacion de copy de un tema del tablero
por el MISMO camino que el boton manual del asistente (el lanzador NEUTRO
`dominio.generar.lanzar_copy`): los endpoints manuales (api/fuentes, api/noticias,
api/contenido, api/breaking, api/insumos) y la ETAPA DE COPY del pipeline, que es el ÚNICO
motor de copy automático (ver `pipeline_contenido.ejecutar_cd`). Este módulo expone esa
función única (`lanzar_para_topic`) + su dedup por etiqueta (`autogen`).

Antes existía además un DAEMON suelto (`KENI_AUTOGEN`) que barría el tablero y auto-generaba
copy; se RETIRÓ: la selección de temas del news-pool sin copy vive ahora dentro de la etapa de
copy del pipeline (`pipeline_contenido.temas_autogen_sin_copy`), gateada por `KENI_PIPELINE_COPY`.

  - SOLO FUENTES: la etapa de copy solo procesa temas cuyo `origen` es de una FUENTE
    (`estados.ORIGENES_AUTOGEN`); el contenido manual del equipo NO se toca.
  - REQUIERE MARCA: sin marca no hay voz/tropicalizacion; esos temas se omiten.
  - DEDUP: tras encolar, el tema se ETIQUETA `autogen` para no re-generarlo. La selección lee
    esa etiqueta para saltarse lo ya hecho.
  - NO PUBLICA: el borrador nace `borrador` y pasa por la MISMA revision/aprobacion humana;
    la publicacion real (vía Metricool) sigue gated por `KENI_PUBLICAR_REAL`.
"""

from __future__ import annotations

import logging
from typing import Any

from . import marcas, redes, repos
from .dominio import generar as dom_generar
from .estados import ORIGENES_AUTOGEN

_log = logging.getLogger("keni_consola.autogen_copy")

# Origenes de contenido que cuentan como "tema redactable" (un borrador se encola solo).
# Fuente UNICA del vocabulario: `estados.ORIGENES_AUTOGEN` (modulo neutro), para que los
# flujos transversales no compitan por este literal. Incluye las fuentes externas historicas
# (import-calendario, radar-auto, radar, rss) Y el alta creativa del equipo (`equipo`), que
# la direccion decidio auto-generar SIEMPRE (2026-06-01). El alta TECLEADA legada (origen "")
# sigue EXCLUIDA a proposito: no auto-generamos lo que el equipo teclea sin marcar como alta.
ORIGENES_TOPIC: frozenset[str] = frozenset(ORIGENES_AUTOGEN)

# Etiqueta de origen del historial para el copy auto-generado (nota -> piezas por red, con
# auto-verificacion). Tras retirar el sistema de skills, el copy va por el lanzador NEUTRO
# (`dominio.generar.lanzar_copy`), que compone el prompt copy-desde-nota autocontenido; este
# valor es solo la etiqueta de procedencia en el historial.
ORIGEN_HISTORIAL = "copy-desde-nota"

# Etiqueta-marca de dedup: un tema ya encolado para auto-generacion la lleva.
ETIQUETA_AUTOGEN = "autogen"


def _normaliza(texto: object) -> str:
    return " ".join(("" if texto is None else str(texto)).strip().lower().split())


def _id_etiqueta_autogen(*, crear: bool = True) -> str:
    """Id de la etiqueta `autogen` (la crea si no existe y `crear`). "" si no se puede."""
    for et in repos.listar_etiquetas():
        if _normaliza(et.get("nombre", "")) == ETIQUETA_AUTOGEN:
            return et.get("id", "")
    if not crear:
        return ""
    return repos.crear_etiqueta(nombre=ETIQUETA_AUTOGEN).get("id", "")


def ids_ya_generados() -> set[str]:
    """Ids de contenido ya encolados para auto-generacion (etiqueta `autogen`).

    Best-effort: si la lectura falla, devuelve set vacio (peor caso: un re-encolado, que el
    propio worker/historial acotan, nunca una excepcion que rompa el barrido).
    """
    try:
        et_id = _id_etiqueta_autogen(crear=False)
        if not et_id:
            return set()
        return repos.ids_contenido_con_etiqueta(et_id)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar el barrido
        return set()


def _nota_de(item: dict[str, Any]) -> str:
    """Nota de partida del copy: titulo + descripcion del tema (sin inventar)."""
    titulo = (item.get("titulo") or "").strip()
    descripcion = (item.get("descripcion") or "").strip()
    return f"{titulo}\n\n{descripcion}".strip() if descripcion else titulo


def _redes_de(item: dict[str, Any]) -> list[str]:
    """Redes objetivo: las del propio tema si las tiene; si no, las redes por defecto."""
    try:
        plataformas = repos.listar_contenido_plataforma(item["id"])
    except Exception:  # noqa: BLE001 -- sin plataformas legibles, caemos al defecto
        plataformas = []
    reds = [p.get("red") for p in plataformas if redes.es_red(p.get("red") or "")]
    if reds:
        return list(dict.fromkeys(reds))
    # Defecto: la lista canonica de redes (la misma que usa el asistente/copy del tablero).
    return redes.ids()


def lanzar_para_topic(item: dict[str, Any]) -> dict[str, Any] | None:
    """Encola una generacion de copy para un tema y lo marca como generado. None si se omite.

    Reutiliza el lanzador NEUTRO `dominio.generar.lanzar_copy` (mismo camino que el boton
    manual del asistente y que `api/rss.generar`): compone el prompt copy-desde-nota
    autocontenido (semilla + editorial de la marca + la nota del tema), encola en background
    y el borrador entra a la cola de revision. `contenido_id` NIDA el borrador bajo el tema.
    """
    marca = item.get("marca") or ""
    if not marca or not marcas.es_marca(marca):
        return None
    nota = _nota_de(item)
    if not nota:
        return None
    redes_ids = _redes_de(item)
    gen = dom_generar.lanzar_copy(
        tipo="autogen",
        marca=marca,
        contexto=nota,
        redes_ids=redes_ids,
        titulo="Auto-copy",
        titulo_dado=(item.get("titulo") or "").strip()[:300],
        texto_base=nota,
        origen_historial=ORIGEN_HISTORIAL,
        autor=None,
        # Lista viva: el borrador auto-generado cuelga del tema origen (su tarjeta lo
        # muestra y sigue fluyendo por aprobacion/programador), no como contenido suelto.
        contenido_id=item.get("id") or "",
    )
    # Dedup: marca el tema como ya encolado (solo si el encolado no lanzo). Best-effort.
    et_id = _id_etiqueta_autogen()
    if et_id:
        repos.asignar_etiqueta(item["id"], et_id)
    return gen


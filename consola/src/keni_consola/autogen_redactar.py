"""Generacion de COPY para un tema del tablero (lanzador reutilizable).

PROBLEMA QUE RESUELVE
Varios caminos del producto necesitan ENCOLAR la generacion de copy de un tema del tablero
por el MISMO camino que el boton manual del asistente (el lanzador NEUTRO
`dominio.generar.lanzar_copy`): los endpoints manuales (api/fuentes, api/noticias,
api/publicaciones, api/breaking, api/insumos) y la ETAPA de Redactar del pipeline, que es el ÚNICO
motor de copy automático (ver `pipeline_contenido.ejecutar_redactar`). Este módulo expone esa
función única (`lanzar_para_topic`) + su dedup por etiqueta (`autogen`).

La selección de temas del news-pool sin copy vive dentro de la etapa de
Redactar del pipeline (`pipeline_contenido.temas_autogen_sin_copy`), gateada por `KENI_PIPELINE_REDACTAR`.

  - SOLO FUENTES: la etapa de Redactar solo procesa temas cuyo `origen` es de una FUENTE
    (`estados.ORIGENES_AUTOGEN`); el contenido manual del equipo NO se toca.
  - REQUIERE MARCA: sin marca no hay voz/tropicalizacion; esos temas se omiten.
  - DEDUP: al COMPLETAR CON EXITO el copy, el post-procesado ETIQUETA el tema `autogen` para
    no re-generarlo (la selección lee esa etiqueta para saltarse lo ya hecho). Se etiqueta al
    éxito —no al encolar— para que un copy fallido se REINTENTE en el siguiente barrido; el
    doble lanzamiento en curso lo evita la clave de idempotencia de `dominio.generar.lanzar`.
  - NO PUBLICA: el borrador nace `borrador` y pasa por la MISMA revision/aprobacion humana;
    la pieza real (vía Metricool) sigue gated por `KENI_PUBLICAR_REAL`.
"""

from __future__ import annotations

import logging
from typing import Any

from keni_shared import marcas

from . import redes, repos
from .dominio import generar as dom_generar
from .estados import ORIGENES_AUTOGEN

_log = logging.getLogger("keni_consola.autogen_redactar")

# Origenes de contenido que cuentan como "tema redactable" (un borrador se encola solo).
# Fuente UNICA del vocabulario: `estados.ORIGENES_AUTOGEN` (modulo neutro), para que los
# flujos transversales no compitan por este literal. Incluye las fuentes externas historicas
# (import-calendario, radar-auto, radar, rss) Y el alta creativa del equipo (`equipo`), que
# se auto-genera SIEMPRE. El alta TECLEADA legada (origen "") sigue EXCLUIDA a proposito:
# no auto-generamos lo que el equipo teclea sin marcar como alta.
ORIGENES_TOPIC: frozenset[str] = frozenset(ORIGENES_AUTOGEN)

# Etiqueta de origen del historial para el copy auto-generado (nota -> piezas por red).
# El copy va por el lanzador NEUTRO (`dominio.generar.lanzar_copy`), que
# compone el prompt copy-desde-nota autocontenido; este valor es solo la etiqueta de procedencia.
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
        plataformas = repos.listar_piezas_fila(item["id"])
    except Exception:  # noqa: BLE001 -- sin plataformas legibles, caemos al defecto
        plataformas = []
    reds = [p.get("red") for p in plataformas if redes.es_red(p.get("red") or "")]
    if reds:
        return list(dict.fromkeys(reds))
    # Defecto: las redes del FORMATO de la pieza (foto -> Instagram/X/Facebook), NO todas: una
    # pieza de imagen nunca debe ir a YouTube/TikTok (redes de vídeo).
    return list(redes.redes_de_formato(item.get("formato")))


def lanzar_para_topic(item: dict[str, Any], *, manual: bool = False) -> dict[str, Any] | None:
    """Encola una generacion de copy para un tema y lo marca como generado. None si se omite.

    `manual` (def False): el lanzamiento lo dispara una PERSONA (p. ej. "Empujar al feed"), no el
    barrido del pipeline. Entonces el copy va con prioridad MANUAL —no lo corta el nivel
    SOLO_MANUAL del presupuesto ni cede el paso en la cola—. Por defecto es trabajo de fondo.

    Reutiliza el lanzador NEUTRO `dominio.generar.lanzar_copy` (mismo camino que el boton
    manual del asistente y que `api/rss.generar`): compone el prompt copy-desde-nota
    autocontenido (prompt base + editorial de la marca + la nota del tema), encola en background
    y el borrador entra a la cola de revision. `publicacion_id` NIDA el borrador bajo el tema.

    Es trabajo del PIPELINE (su etapa de Redactar redactando un tema del tablero), asi que se
    sella IGUAL que el copy de un tema ingerido: `tipo="pipeline"` + marcador de etapa CD
    correlacionado al tema. Antes salia como `tipo="autogen"` / "Auto-copy" (un nombre
    legado, suelto en Produccion, fuera de su run): el feed unificado lo muestra ahora como
    la run del tema con su etapa Redactar.
    """
    marca = item.get("marca") or ""
    if not marca or not marcas.es_marca(marca):
        return None
    nota = _nota_de(item)
    if not nota:
        return None
    redes_ids = _redes_de(item)
    titulo = (item.get("titulo") or "").strip()
    gen = dom_generar.lanzar_copy(
        # `pipeline`: misma marca de trabajo que el copy de los temas ingeridos (la etapa CD
        # del pipeline es el UNICO motor de copy; "autogen" era el nombre del daemon legado).
        tipo="pipeline",
        # Empuje a mano (endpoint del asistente): MANUAL real, intocable por el presupuesto de fondo.
        # Sin él, el copy del pipeline es AUTOMATICO y cede el paso a lo manual (gestor `prioridad`).
        manual=manual,
        marca=marca,
        contexto=nota,
        redes_ids=redes_ids,
        titulo=titulo or "Copy",
        titulo_dado=titulo[:300],
        texto_base=nota,
        origen_historial=ORIGEN_HISTORIAL,
        autor=None,
        # Lista viva: el borrador auto-generado cuelga del tema origen (su tarjeta lo
        # muestra y sigue fluyendo por aprobacion/programador), no como contenido suelto.
        publicacion_id=item.get("id") or "",
        # DEDUP AL EXITO (no al encolar): la etiqueta `autogen` la asigna el POST-PROCESADO
        # del copy al completar con exito, NO al encolar, para que un copy FALLIDO no excluya
        # el tema para siempre de la seleccion y pueda reintentarse.
        # Mientras el job esta EN CURSO no hay doble lanzamiento: la clave de idempotencia
        # de `dominio.generar.lanzar` devuelve el run en curso.
        etiqueta_exito=ETIQUETA_AUTOGEN,
    )
    _registrar_etapa_redactar(item, gen)
    return gen


def _registrar_etapa_redactar(item: dict[str, Any], gen: dict[str, Any] | None) -> None:
    """Marcador de etapa CD correlacionado al tema (espejo de `_copy.lanzar_copy_tema`).

    Ata la generacion REAL al tema para que el detalle del pipeline muestre su stream y la
    run sume sus metricas. Best-effort: un fallo de traza no rompe el lanzamiento. Import
    diferido de `pipeline_contenido` (mismo patron que `autogen_ilustrar`) para no acoplar la
    carga del modulo (evita ciclo con `_barrido`).
    """
    try:
        from .pipeline_contenido import ETAPA_REDACTAR, registrar_etapa

        registrar_etapa(
            ETAPA_REDACTAR,
            item.get("marca") or "",
            f"Generación de copy (tablero) — '{(item.get('titulo') or '')[:120]}'",
            publicacion_id=item.get("id") or "",
            gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
        )
    except Exception:  # noqa: BLE001 -- la traza es observabilidad; nunca rompe el copy
        _log.warning("Auto-copy: no se pudo registrar el marcador de etapa CD.", exc_info=True)


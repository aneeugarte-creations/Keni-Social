"""Persistencia — purga de borradores MUERTOS del tablero (retencion a N dias).

POLITICA (aprobada por el dueño): un tema AUTO-GENERADO que NINGUN humano toco jamas se borra
pasados N dias (def 90, `config.piezas_purga_dias`). Todo lo publicado o con cualquier huella
humana se conserva PARA SIEMPRE. Es una politica de retencion deliberada, no un GC tecnico.

QUE ES "MUERTO" (todas las condiciones a la vez; ante la duda, se conserva):
  - `origen` de MAQUINA en allowlist estricta: `pipeline`, `portal`, `historia`. Cualquier otro
    origen (`equipo`, `''` alta tecleada, `post-directo`, `presidencia`, `clips`, `evergreen`,
    importadores…) NUNCA se purga, aunque algunos sean tambien automaticos: solo se purga lo
    que la politica enumero explicitamente.
  - clase 'contenido' (una tarea libre es trabajo del equipo, no un borrador de maquina).
  - mas viejo que el corte (sobre `creado`; sin fecha no hay evidencia de edad: se conserva).
  - SIN huella humana en el padre: sin responsable (nadie lo cogio jamas: la maquina nunca
    asigna responsable — ver `auto_responsable`, reparto PULL), `estado` aun 'pendiente' y sin
    `id_post_metricool`.
  - TODAS sus piezas en `borrador` y sin trazas de haber avanzado: sin enviar a revision, sin
    revisor, sin fecha programada, sin id/enlace de post publicado y sin imagen autorizada por
    un humano (`imagen_autorizada`). Un tema SIN piezas cuenta como muerto (cascara vacia).
  - SIN comentarios, SIN historial de copy (`pieza_copy_versiones`: solo lo escribe la edicion
    de copy via API), SIN cadena de aprobacion (`pieza_aprobaciones`: nace al enviar a revision
    o al decidir; incluye likes/dislikes) y SIN versiones de documento del editor
    (`documento_versiones`: solo las escribe el Estudio de imagen a peticion de una persona).
  - SIN etiquetas atribuibles a un humano. La maquina etiqueta TODOS sus temas (clasificador de
    categoria/linea en la admision + marcadores de dedup de los daemons autogen), asi que "tiene
    etiquetas" no es señal: solo cuenta como huella humana una etiqueta que NO es de las clases
    taxonomicas que estampa la maquina ('categoria'/'origen') NI un marcador autogen reservado.

BORRADO: se REUTILIZA la cascada canonica `db_publicacion.borrar_publicacion` (suelta el
sentinel de noticias promovidas + borra piezas/etiquetas/tema); las FKs reales ON DELETE CASCADE
(`migraciones_integridad._FKS`) arrastran comentarios/versiones/aprobaciones/doc-versiones, que
por definicion de "muerto" estan vacias. Cada candidato se RE-VERIFICA contra el criterio
completo justo antes de borrarlo (una huella aparecida entre el listado y el borrado lo salva).

MEDIA: aqui NO se toca el almacen. Los objetos que referenciaban las piezas borradas (foto del
portal, arte IA, stock) quedan sin dueño y los recoge el GC de media (`dominio.media_gc`
calcula referencias vivas sobre las filas `pieza`/catalogos; gateado por `KENI_MEDIA_GC`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ._comun import Any, _conectar
from .publicacion import borrar_publicacion
from ..tiempo import iso_utc

# Origenes purgables (allowlist ESTRICTA de la politica). Literales a proposito: los simbolos
# canonicos viven en `pipeline_contenido._comun` (ORIGEN_PIPELINE/ORIGEN_PORTAL) y `estados`
# (ORIGEN_HISTORIA), pero un modulo de persistencia no importa el pipeline (mismo criterio que
# `pipeline_estado` con las etiquetas autogen: replicar el literal antes que acoplar capas).
ORIGENES_PURGABLES: tuple[str, ...] = ("pipeline", "portal", "historia")

# Clases de etiqueta que estampa la MAQUINA como taxonomia (clasificador de la admision):
# su presencia NO es huella humana. Cualquier otra clase ('campania', 'tipo') si lo es.
_CLASES_ETIQUETA_MAQUINA: tuple[str, ...] = ("categoria", "origen")

# Marcadores de dedup de los daemons de auto-produccion (nacen con la clase por defecto
# 'campania', asi que se excluyen POR NOMBRE). Fuente: `autogen_redactar.ETIQUETA_AUTOGEN`,
# `autogen_ilustrar.ETIQUETA_AUTOGEN_ARTE`, `autogen_stock.ETIQUETA_AUTOGEN_STOCK`.
_ETIQUETAS_MARCADOR_MAQUINA: tuple[str, ...] = ("autogen", "autogen-arte", "autogen-stock")

# Criterio SQL completo de "borrador muerto" sobre el alias `p` (publicacion). Placeholders en
# orden: 3 origenes + corte + 2 clases de etiqueta + 3 marcadores (ver `_params_muerto`).
_WHERE_MUERTO = (
    "p.clase = 'contenido' "
    "AND p.origen IN (?, ?, ?) "
    "AND p.responsable_id = '' AND p.responsable_nombre = '' "
    "AND p.estado = 'pendiente' "
    "AND p.id_post_metricool = '' "
    "AND p.creado IS NOT NULL AND p.creado < ? "
    "AND NOT EXISTS (SELECT 1 FROM pieza cp WHERE cp.publicacion_id = p.id AND ("
    "cp.estado <> 'borrador' OR cp.id_post_metricool <> '' OR cp.enlace <> '' "
    "OR cp.fecha_programada <> '' OR cp.enviado_a_revision_en <> '' "
    "OR cp.revisado_en <> '' OR cp.revisor_id <> '' OR cp.imagen_autorizada <> 0)) "
    "AND NOT EXISTS (SELECT 1 FROM publicacion_comentarios c WHERE c.publicacion_id = p.id) "
    "AND NOT EXISTS (SELECT 1 FROM pieza_copy_versiones v "
    "LEFT JOIN pieza cpv ON cpv.id = v.pieza_id "
    "WHERE v.publicacion_id = p.id OR cpv.publicacion_id = p.id) "
    "AND NOT EXISTS (SELECT 1 FROM pieza_aprobaciones a "
    "LEFT JOIN pieza cpa ON cpa.id = a.pieza_id "
    "WHERE a.publicacion_id = p.id OR cpa.publicacion_id = p.id) "
    "AND NOT EXISTS (SELECT 1 FROM documento_versiones d WHERE d.publicacion_id = p.id) "
    "AND NOT EXISTS (SELECT 1 FROM publicacion_etiquetas pe "
    "JOIN etiquetas e ON e.id = pe.etiqueta_id "
    "WHERE pe.publicacion_id = p.id "
    "AND e.clase NOT IN (?, ?) AND lower(e.nombre) NOT IN (?, ?, ?))"
)


def _params_muerto(corte_iso: str) -> tuple[str, ...]:
    """Parametros de `_WHERE_MUERTO`, en el orden de sus placeholders."""
    return (
        *ORIGENES_PURGABLES,
        corte_iso,
        *_CLASES_ETIQUETA_MAQUINA,
        *_ETIQUETAS_MARCADOR_MAQUINA,
    )


def corte_purga(dias: int) -> str:
    """Corte ISO UTC de la retencion: ahora - `dias` (comparable con `publicacion.creado`)."""
    return iso_utc(datetime.now(UTC) - timedelta(days=max(0, int(dias))))


def candidatos_purga(corte_iso: str, *, limite: int = 200) -> list[dict[str, str]]:
    """Borradores MUERTOS mas viejos que `corte_iso` (los mas antiguos primero), acotados.

    Solo lectura. Devuelve `[{id, marca}, ...]`; `limite` acota el lote por barrido para que
    el primer drenaje de un backlog grande no sea una rafaga (el resto cae en barridos
    siguientes: la cadencia del limpiador drena en horas sin bloquear la BD).
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"SELECT p.id, p.marca FROM publicacion p WHERE {_WHERE_MUERTO} "
            "ORDER BY p.creado ASC, p.id ASC LIMIT ?",
            (*_params_muerto(corte_iso), max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [{"id": f["id"], "marca": f["marca"] or ""} for f in filas]


def es_borrador_muerto(publicacion_id: str, corte_iso: str) -> bool:
    """True si `publicacion_id` cumple AHORA el criterio completo de borrador muerto."""
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT 1 AS ok FROM publicacion p WHERE p.id = ? AND {_WHERE_MUERTO}",
            (publicacion_id, *_params_muerto(corte_iso)),
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def purgar_borradores_muertos(dias: int, *, limite: int = 200) -> dict[str, Any]:
    """Borra hasta `limite` borradores muertos mas viejos que `dias`. Conteos por marca.

    `dias <= 0` = purga APAGADA (no toca nada). Cada candidato se re-verifica contra el
    criterio completo justo antes de borrar (una huella humana aparecida entre el listado y el
    borrado lo salva) y cae con la cascada canonica de `borrar_publicacion` (+ FKs CASCADE).
    Devuelve `{"purgadas": int, "por_marca": {marca: n}, "corte": iso}`.
    """
    if int(dias) <= 0:
        return {"purgadas": 0, "por_marca": {}, "corte": ""}
    corte = corte_purga(dias)
    por_marca: dict[str, int] = {}
    purgadas = 0
    for cand in candidatos_purga(corte, limite=limite):
        pub_id = cand["id"]
        if not es_borrador_muerto(pub_id, corte):
            continue  # alguien lo toco entre el listado y el borrado: se conserva
        if borrar_publicacion(pub_id):
            purgadas += 1
            marca = cand["marca"] or "(sin marca)"
            por_marca[marca] = por_marca.get(marca, 0) + 1
    return {"purgadas": purgadas, "por_marca": por_marca, "corte": corte}

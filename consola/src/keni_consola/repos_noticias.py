"""Repositorio — dominio noticias. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Fuentes RSS + items vistos + salud (OPERACIONAL: Postgres via db.py; ADR 0006) #
# --------------------------------------------------------------------------- #


def listar_fuentes_rss(
    *,
    marca: str | None = None,
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    return db.listar_fuentes_rss(
        marca=marca, limite=limite, desplazamiento=desplazamiento
    )


def contar_fuentes_rss() -> int:
    return db.contar_fuentes_rss()


def obtener_fuente_rss(fuente_id: str) -> dict[str, Any] | None:
    return db.obtener_fuente_rss(fuente_id)


def crear_fuente_rss(
    nombre: str,
    url: str,
    marca: str = "",
    *,
    marcas: list[str] | None = None,
    incluir: str = "",
    excluir: str = "",
    redes_def: str = "",
    propia: bool = False,
    categoria: str = "",
    linea_id: str = "",
    prioridad: int = 0,
    intervalo_min: int = 0,
    peso: float = 1.0,
    idioma: str = "",
) -> dict[str, Any]:
    return db.crear_fuente_rss(
        nombre,
        url,
        marca=marca,
        marcas=marcas,
        incluir=incluir,
        excluir=excluir,
        redes_def=redes_def,
        propia=propia,
        categoria=categoria,
        linea_id=linea_id,
        prioridad=prioridad,
        intervalo_min=intervalo_min,
        peso=peso,
        idioma=idioma,
    )


def actualizar_fuente_rss(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_fuente_rss(fuente_id, campos)


def registrar_salud_fuente_rss(fuente_id: str, *, conteo: int, error: str = "") -> None:
    return db.registrar_salud_fuente_rss(fuente_id, conteo=conteo, error=error)


def borrar_fuente_rss(fuente_id: str) -> bool:
    return db.borrar_fuente_rss(fuente_id)


def borrar_noticia_cluster(cluster_id: str) -> bool:
    return db.borrar_noticia_cluster(cluster_id)


def borrar_clusters_con_items(cluster_ids: list[str]) -> int:
    return db.borrar_clusters_con_items(cluster_ids)


def vaciar_clusters(marca: str | None = None, estado: str | None = None) -> int:
    return db.vaciar_clusters(marca, estado)


def purgar_pool_irrelevante(
    *, score_umbral: float, inactividad_horas: int, dry_run: bool = False
) -> dict[str, int]:
    return db.purgar_pool_irrelevante(
        score_umbral=score_umbral, inactividad_horas=inactividad_horas, dry_run=dry_run
    )


def caducar_pool(*, ttl_horas: int, retencion_horas: int = 0) -> dict[str, int]:
    return db.caducar_pool(ttl_horas=ttl_horas, retencion_horas=retencion_horas)


def marcar_item(fuente_id: str, clave: str, usado: bool) -> None:
    return db.marcar_item(fuente_id, clave, usado)



# --- Motor de ingesta persistente (Ola A): delega 1:1 en db.py ------------- #

ESTADOS_NOTICIA_ITEM = db.ESTADOS_NOTICIA_ITEM


def crear_noticias_items(items: list[dict[str, Any]]) -> int:
    return db.crear_noticias_items(items)


def claves_existentes_directas(
    claves: list[str], *, desde: str = "", excluir_fuente: str = ""
) -> set[str]:
    return db.claves_existentes_directas(claves, desde=desde, excluir_fuente=excluir_fuente)


def listar_noticias_items(
    *,
    marca: str | None = None,
    desde: str | None = None,
    q: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    return db.listar_noticias_items(
        marca=marca,
        desde=desde,
        q=q,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def obtener_noticia_item(item_id: str) -> dict[str, Any] | None:
    return db.obtener_noticia_item(item_id)


def noticia_item_por_clave(fuente_id: str, clave: str) -> dict[str, Any] | None:
    return db.noticia_item_por_clave(fuente_id, clave)


def actualizar_noticia_item(
    item_id: str,
    *,
    estado: str | None = None,
    publicacion_id: str | None = None,
    cluster_id: str | None = None,
) -> dict[str, Any] | None:
    return db.actualizar_noticia_item(
        item_id, estado=estado, publicacion_id=publicacion_id, cluster_id=cluster_id
    )


def feeds_vencidos(ahora: str, limite: int) -> list[dict[str, Any]]:
    return db.feeds_vencidos(ahora, limite)


def items_sin_tags(dominios: list[str], limite: int) -> list[dict[str, Any]]:
    return db.items_sin_tags(dominios, limite)


def actualizar_tags_item(item_id: str, tags: list[str]) -> None:
    return db.actualizar_tags_item(item_id, tags)


def marcar_etiquetas_revisadas(item_id: str) -> None:
    return db.marcar_etiquetas_revisadas(item_id)


def notas_por_etiqueta(
    slug: str, *, desde: str, dominios: list[str]
) -> list[dict[str, Any]]:
    return db.notas_por_etiqueta(slug, desde=desde, dominios=dominios)


def categoria_promovida_de_contenido(publicacion_id: str) -> str:
    """Categoría del plan de un contenido promovido ('' si no aplica). Delegado en `db.py`."""
    return db.categoria_promovida_de_contenido(publicacion_id)


def registrar_sondeo_feed(
    feed_id: str,
    *,
    conteo: int = 0,
    error: str = "",
    proximo_sondeo: str = "",
    errores_seguidos: int = 0,
    pausado_hasta: str = "",
    activo: bool | None = None,
    desactivado_auto: bool | None = None,
    filtrados: int = 0,
) -> None:
    return db.registrar_sondeo_feed(
        feed_id,
        conteo=conteo,
        error=error,
        proximo_sondeo=proximo_sondeo,
        errores_seguidos=errores_seguidos,
        pausado_hasta=pausado_hasta,
        activo=activo,
        desactivado_auto=desactivado_auto,
        filtrados=filtrados,
    )


def resumen_cobertura() -> dict[str, Any]:
    return db.resumen_cobertura()



# --- Monitor de cobertura / salud (Ola D): delega 1:1 en db.py ------------- #


def salud_feeds(marca: str | None = None) -> list[dict[str, Any]]:
    return db.salud_feeds(marca)


def conteos_items_recientes(
    marca: str | None = None, *, horas: int = 24
) -> dict[str, dict[str, int]]:
    return db.conteos_items_recientes(marca, horas=horas)


def stats_fuentes(marca: str | None = None, *, dias: int = 7) -> list[dict[str, Any]]:
    return db.stats_fuentes(marca, dias=dias)



# --- Clustering de historias (Ola B): delega 1:1 en db.py ------------------ #

ESTADOS_NOTICIA_CLUSTER = db.ESTADOS_NOTICIA_CLUSTER
VERIFICACIONES_CLUSTER = db.VERIFICACIONES_CLUSTER


def upsert_noticia_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    return db.upsert_noticia_cluster(cluster)


def listar_noticia_clusters(
    *,
    marca: str | None = None,
    desde: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    return db.listar_noticia_clusters(
        marca=marca,
        desde=desde,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def obtener_noticia_cluster(cluster_id: str) -> dict[str, Any] | None:
    return db.obtener_noticia_cluster(cluster_id)


def cluster_por_contenido(publicacion_id: str) -> dict[str, Any] | None:
    return db.cluster_por_contenido(publicacion_id)


def clusters_por_contenidos(publicacion_ids: list[str]) -> dict[str, dict[str, Any]]:
    return db.clusters_por_contenidos(publicacion_ids)


def actualizar_noticia_cluster(
    cluster_id: str,
    *,
    estado: str | None = None,
    publicacion_id: str | None = None,
) -> dict[str, Any] | None:
    return db.actualizar_noticia_cluster(
        cluster_id, estado=estado, publicacion_id=publicacion_id
    )


def clusters_recientes(ventana_h: int, marca: str | None = None) -> list[dict[str, Any]]:
    return db.clusters_recientes(ventana_h, marca)


def clusters_por_tema_macro(
    tema_macro: str, marca: str, *, solo_nuevos: bool = True
) -> list[dict[str, Any]]:
    return db.clusters_por_tema_macro(tema_macro, marca, solo_nuevos=solo_nuevos)


def clusters_por_subtema(
    tema_macro: str, subtema: str, marca: str, *, solo_nuevos: bool = True
) -> list[dict[str, Any]]:
    return db.clusters_por_subtema(tema_macro, subtema, marca, solo_nuevos=solo_nuevos)


def clusters_con_fuente_propia(
    marca: str, *, estado: str = "nuevo", limite: int = 200
) -> list[dict[str, Any]]:
    return db.clusters_con_fuente_propia(marca, estado=estado, limite=limite)


def ids_clusters_con_fuente_propia(marca: str, *, estado: str = "nuevo") -> set[str]:
    return db.ids_clusters_con_fuente_propia(marca, estado=estado)


def items_de_cluster(cluster_id: str, *, limite: int = 200) -> list[dict[str, Any]]:
    return db.items_de_cluster(cluster_id, limite=limite)


def cuerpos_de_cluster(cluster_id: str, *, limite: int = 200) -> dict[str, str]:
    return db.cuerpos_de_cluster(cluster_id, limite=limite)


def items_sin_cluster(desde: str, limite: int) -> list[dict[str, Any]]:
    return db.items_sin_cluster(desde, limite)


def cluster_por_url_canonica(url_recortada: str, desde: str, marca: str | None = None) -> str:
    return db.cluster_por_url_canonica(url_recortada, desde, marca=marca)


def clusters_extranjeros_sin_traducir(
    ventana_h: int, *, min_score: float = 0.0, limite: int = 40
) -> list[dict[str, Any]]:
    return db.clusters_extranjeros_sin_traducir(
        ventana_h, min_score=min_score, limite=limite
    )


def marcar_clusters_traduccion_encolada(ids: list[str]) -> int:
    return db.marcar_clusters_traduccion_encolada(ids)


def limpiar_traduccion_encolada(ids: list[str]) -> int:
    return db.limpiar_traduccion_encolada(ids)


def reparar_traduccion_encolada_atascada(umbral_iso: str) -> int:
    return db.reparar_traduccion_encolada_atascada(umbral_iso)


def marcar_cluster_verificacion(cluster_id: str, verificacion: str, hallazgos: str = "") -> None:
    return db.marcar_cluster_verificacion(cluster_id, verificacion, hallazgos)


def marcar_clusters_tema_macro(ids: list[str], tema: str) -> int:
    return db.marcar_clusters_tema_macro(ids, tema)


def marcar_clusters_subtema(ids: list[str], subtema: str) -> int:
    return db.marcar_clusters_subtema(ids, subtema)


def marcar_clusters_fusion_vista(ids: list[str]) -> int:
    return db.marcar_clusters_fusion_vista(ids)


def contar_clusters_admision_verificacion(marca: str, estados: tuple[str, ...]) -> int:
    return db.contar_clusters_admision_verificacion(marca, estados)


def reparar_verificacion_clusters_en_curso(umbral_iso: str) -> int:
    return db.reparar_verificacion_clusters_en_curso(umbral_iso)


def marcar_cluster_traducido(
    cluster_id: str,
    *,
    titulo_es: str,
    resumen_es: str,
    titulo_original: str = "",
) -> dict[str, Any] | None:
    return db.marcar_cluster_traducido(
        cluster_id,
        titulo_es=titulo_es,
        resumen_es=resumen_es,
        titulo_original=titulo_original,
    )


def traduccion_por_clave(clave: str) -> dict[str, Any] | None:
    return db.traduccion_por_clave(clave)


def asignar_cluster_item(item_id: str, cluster_id: str) -> None:
    return db.asignar_cluster_item(item_id, cluster_id)


def asignar_cluster_items(asignaciones: dict[str, list[str]]) -> None:
    return db.asignar_cluster_items(asignaciones)


def limpiar_items_cluster_colgante() -> int:
    return db.limpiar_items_cluster_colgante()


def actualizar_scores_clusters(scores: dict[str, float]) -> int:
    return db.actualizar_scores_clusters(scores)


def marcar_items_cluster_usados(cluster_id: str, publicacion_id: str) -> None:
    return db.marcar_items_cluster_usados(cluster_id, publicacion_id)


def desmarcar_items_cluster_usados(cluster_id: str) -> None:
    return db.desmarcar_items_cluster_usados(cluster_id)


def descartar_cluster(cluster_id: str) -> bool:
    return db.descartar_cluster(cluster_id)


def claves_vistas(fuente_id: str) -> set[str]:
    return db.claves_vistas(fuente_id)



# --------------------------------------------------------------------------- #
# Algoritmo: fuentes de industria + noticias clasificadas (OPERACIONAL: Postgres) #
# --------------------------------------------------------------------------- #
#
# Inteligencia de plataforma (cambios de algoritmo + tendencias), distinta del RSS de
# marca: alimenta la pagina Algoritmos y el panel. La clasificacion vive en `algoritmos.py`;
# la fachada solo delega la persistencia 1:1 en db.py.


def listar_fuentes_algoritmo() -> list[dict[str, Any]]:
    return db.listar_fuentes_algoritmo()


def contar_fuentes_algoritmo() -> int:
    return db.contar_fuentes_algoritmo()


def obtener_fuente_algoritmo(fuente_id: str) -> dict[str, Any] | None:
    return db.obtener_fuente_algoritmo(fuente_id)


def crear_fuente_algoritmo(
    nombre: str, url: str, *, plataforma: str = "general", tipo: str = "agregador"
) -> dict[str, Any]:
    return db.crear_fuente_algoritmo(nombre, url, plataforma=plataforma, tipo=tipo)


def actualizar_fuente_algoritmo(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_fuente_algoritmo(fuente_id, campos)


def registrar_salud_fuente_algoritmo(fuente_id: str, *, conteo: int, error: str = "") -> None:
    return db.registrar_salud_fuente_algoritmo(fuente_id, conteo=conteo, error=error)


def borrar_fuente_algoritmo(fuente_id: str) -> bool:
    return db.borrar_fuente_algoritmo(fuente_id)


def guardar_noticia_algoritmo(noticia: dict[str, Any]) -> str:
    return db.guardar_noticia_algoritmo(noticia)


def listar_noticias_algoritmo(
    *,
    plataforma: str | None = None,
    nivel: str | None = None,
    solo_cambios: bool = False,
    solo_no_sugeridas: bool = False,
    incluir_archivadas: bool = False,
    limite: int | None = None,
) -> list[dict[str, Any]]:
    return db.listar_noticias_algoritmo(
        plataforma=plataforma,
        nivel=nivel,
        solo_cambios=solo_cambios,
        solo_no_sugeridas=solo_no_sugeridas,
        incluir_archivadas=incluir_archivadas,
        limite=limite,
    )


def obtener_noticia_algoritmo(noticia_id: str) -> dict[str, Any] | None:
    return db.obtener_noticia_algoritmo(noticia_id)


def marcar_noticia_algoritmo(
    noticia_id: str,
    *,
    aplicada: bool | None = None,
    archivada: bool | None = None,
    sugerida: bool | None = None,
) -> dict[str, Any] | None:
    return db.marcar_noticia_algoritmo(
        noticia_id, aplicada=aplicada, archivada=archivada, sugerida=sugerida
    )

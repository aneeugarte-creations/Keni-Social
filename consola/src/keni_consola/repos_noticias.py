"""Repositorio — dominio noticias. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Fuentes RSS + items vistos + salud (OPERACIONAL: Postgres via db.py; ADR 0006) #
# --------------------------------------------------------------------------- #
# Ultimo rezago file-backed cerrado: el indice SQLite de rutas absolutas dejaba la pagina de
# Fuentes RSS vacia tras recrear contenedores. Ahora vive en Postgres (ADR 0006). El dict
# devuelto conserva las mismas claves; la fachada delega 1:1 en db.py.


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
    incluir: str = "",
    excluir: str = "",
    redes_def: str = "",
    propia: bool = False,
    categoria: str = "",
    prioridad: int = 0,
    intervalo_min: int = 0,
) -> dict[str, Any]:
    return db.crear_fuente_rss(
        nombre,
        url,
        marca=marca,
        incluir=incluir,
        excluir=excluir,
        redes_def=redes_def,
        propia=propia,
        categoria=categoria,
        prioridad=prioridad,
        intervalo_min=intervalo_min,
    )


def actualizar_fuente_rss(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_fuente_rss(fuente_id, campos)


def registrar_salud_fuente_rss(fuente_id: str, *, conteo: int, error: str = "") -> None:
    return db.registrar_salud_fuente_rss(fuente_id, conteo=conteo, error=error)


def borrar_fuente_rss(fuente_id: str) -> bool:
    return db.borrar_fuente_rss(fuente_id)


def marcar_item(fuente_id: str, clave: str, usado: bool) -> None:
    return db.marcar_item(fuente_id, clave, usado)



# --- Motor de ingesta persistente (Ola A): delega 1:1 en db.py ------------- #

ESTADOS_NOTICIA_ITEM = db.ESTADOS_NOTICIA_ITEM


def crear_noticias_items(items: list[dict[str, Any]]) -> int:
    return db.crear_noticias_items(items)


def listar_noticias_items(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    desde: str | None = None,
    q: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    return db.listar_noticias_items(
        marca=marca,
        categoria=categoria,
        desde=desde,
        q=q,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def obtener_noticia_item(item_id: str) -> dict[str, Any] | None:
    return db.obtener_noticia_item(item_id)


def actualizar_noticia_item(
    item_id: str,
    *,
    estado: str | None = None,
    contenido_id: str | None = None,
    cluster_id: str | None = None,
) -> dict[str, Any] | None:
    return db.actualizar_noticia_item(
        item_id, estado=estado, contenido_id=contenido_id, cluster_id=cluster_id
    )


def feeds_vencidos(ahora: str, limite: int) -> list[dict[str, Any]]:
    return db.feeds_vencidos(ahora, limite)


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



# --- Clustering de historias (Ola B): delega 1:1 en db.py ------------------ #

ESTADOS_NOTICIA_CLUSTER = db.ESTADOS_NOTICIA_CLUSTER
VERIFICACIONES_CLUSTER = db.VERIFICACIONES_CLUSTER


def upsert_noticia_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    return db.upsert_noticia_cluster(cluster)


def listar_noticia_clusters(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    desde: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    return db.listar_noticia_clusters(
        marca=marca,
        categoria=categoria,
        desde=desde,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def obtener_noticia_cluster(cluster_id: str) -> dict[str, Any] | None:
    return db.obtener_noticia_cluster(cluster_id)


def actualizar_noticia_cluster(
    cluster_id: str,
    *,
    estado: str | None = None,
    contenido_id: str | None = None,
) -> dict[str, Any] | None:
    return db.actualizar_noticia_cluster(
        cluster_id, estado=estado, contenido_id=contenido_id
    )


def clusters_recientes(ventana_h: int, marca: str | None = None) -> list[dict[str, Any]]:
    return db.clusters_recientes(ventana_h, marca)


def items_de_cluster(cluster_id: str, *, limite: int = 200) -> list[dict[str, Any]]:
    return db.items_de_cluster(cluster_id, limite=limite)


def items_sin_cluster(desde: str, limite: int) -> list[dict[str, Any]]:
    return db.items_sin_cluster(desde, limite)


def clusters_extranjeros_sin_traducir(
    ventana_h: int, *, min_score: float = 0.0, limite: int = 40
) -> list[dict[str, Any]]:
    return db.clusters_extranjeros_sin_traducir(
        ventana_h, min_score=min_score, limite=limite
    )


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


def asignar_cluster_item(item_id: str, cluster_id: str) -> None:
    return db.asignar_cluster_item(item_id, cluster_id)


def marcar_items_cluster_usados(cluster_id: str, contenido_id: str) -> None:
    return db.marcar_items_cluster_usados(cluster_id, contenido_id)


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


# Estados validos de una sugerencia editorial (re-export para los `api/*.py`).
ESTADOS_SUGERENCIA_EDITORIAL = db.ESTADOS_SUGERENCIA_EDITORIAL


def crear_sugerencia_editorial(
    *,
    plataforma: str,
    tipo: str,
    titulo: str,
    detalle: str,
    ficha_id: str = "",
    noticia_ids: list[str] | None = None,
) -> dict[str, Any]:
    return db.crear_sugerencia_editorial(
        plataforma=plataforma, tipo=tipo, titulo=titulo, detalle=detalle,
        ficha_id=ficha_id, noticia_ids=noticia_ids,
    )


def listar_sugerencias_editoriales(
    *, estado: str | None = None, limite: int | None = None
) -> list[dict[str, Any]]:
    return db.listar_sugerencias_editoriales(estado=estado, limite=limite)


def contar_sugerencias_editoriales(*, estado: str | None = None) -> int:
    return db.contar_sugerencias_editoriales(estado=estado)


def obtener_sugerencia_editorial(sugerencia_id: str) -> dict[str, Any] | None:
    return db.obtener_sugerencia_editorial(sugerencia_id)


def actualizar_estado_sugerencia_editorial(
    sugerencia_id: str, estado: str
) -> dict[str, Any] | None:
    return db.actualizar_estado_sugerencia_editorial(sugerencia_id, estado)

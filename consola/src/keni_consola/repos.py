"""Capa REPOSITORIO de la Consola Keni: fachada UNICA de persistencia.

Esta capa existe para DESACOPLAR los `api/*.py` del almacen concreto. Cada
`api/*.py` consume SIEMPRE a traves de `repos`, sin saber que hay debajo. La fachada
enruta cada entidad a su almacen de forma FIJA (no hay conmutador ni env var):

  - CONTENIDO editorial (editable a mano, fuente de verdad) -> ficheros YAML por
    marca (`ficheros.py`), con un indice SQLite regenerable (`indice.py`):
    publicaciones, plantillas e historial de skills.
  - OPERACIONAL + editorial reutilizable -> Postgres (`db.py`, via `motor_db`; ADR
    0004/0006): `comercial` (piezas + serie temporal de snapshots), `rota`,
    `usuarios`/`sesiones` (via `auth/`), la cola de `jobs`, y las 3 entidades editoriales
    que cerraron su rezago file->pg (ADR 0006): `fuentes_rss` + items vistos + salud,
    `grupos_hashtags` y `franjas` editoriales.

Las firmas publicas son ESTABLES: ningun `api/*.py` cambia aunque cambie el almacen.

Uso en las features:

    from .. import repos

    repos.crear_publicacion(marca="unotv", red="x", titulo="Hola")  # -> YAML
    repos.crear_publicacion_comercial(url="https://…", titulo="Promo")  # -> Postgres
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import db, ficheros

# Re-export de las constantes neutras de dominio (los `api/*.py` las leen via `repos`,
# p. ej. `repos.ESTADOS_PUBLICACION`). Viven en `estados.py`, fuera de los almacenes.
from .estados import (  # noqa: F401 -- re-exportadas como parte de la API publica
    ESTADO_COMERCIAL_ACTIVA,
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_PROPUESTO,
    ESTADOS_COMERCIAL,
    ESTADOS_PIEZA,
    ESTADOS_PUBLICACION,
    ESTADOS_ROTA,
    ESTADOS_SWAP,
    ESTADOS_TAREA,
    METRICAS_COMERCIAL,
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
    TIPOS_AUSENCIA,
)


def conectar() -> Any:
    """Conexion al backend operacional (delega en `db.conectar`; Postgres).

    La usa la capa de auth (`auth/`) para operar sobre `usuarios`/`sesiones`, igual que el
    resto de funciones de `db` se consumen via esta fachada. `motor_db` abre Postgres con
    `DATABASE_URL` (obligatoria, ADR 0004).
    """
    return db.conectar()


def arrancar_persistencia() -> None:
    """Arranque de la persistencia operacional (delega en `db.arrancar_persistencia`).

    Crea/migra el esquema Postgres on-demand (ADR 0004). Lo llama `crear_app`. Ver `db.py`.
    """
    return db.arrancar_persistencia()


def raiz_datos() -> Path:
    """Raiz de datos de ficheros (delega en `ficheros.raiz_datos`; CONTENIDO editorial vive ahi)."""
    return ficheros.raiz_datos()


# --------------------------------------------------------------------------- #
# Historial de skills (CONTENIDO: ficheros YAML via ficheros.py)               #
# --------------------------------------------------------------------------- #


def registrar_historial_skill(
    skill: str,
    marca: str,
    resultado: str,
    *,
    piezas: list[dict[str, Any]] | None = None,
    titulo: str = "",
    metricas: dict[str, Any] | None = None,
    autor: dict[str, str] | None = None,
) -> str:
    return ficheros.registrar_historial_skill(
        skill, marca, resultado, piezas=piezas, titulo=titulo, metricas=metricas, autor=autor
    )


def listar_historial_skills(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return ficheros.listar_historial_skills(limite=limite, desplazamiento=desplazamiento)


def contar_historial_skills() -> int:
    return ficheros.contar_historial_skills()


def obtener_historial_skill(historial_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_historial_skill(historial_id)


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


# --------------------------------------------------------------------------- #
# Publicaciones (OPERACIONAL: Postgres via db.py; fusión sobre `contenido`, paso 3)    #
# --------------------------------------------------------------------------- #
# Una publicacion = una fila `contenido_plataforma` (es_publicacion=1) + su padre. Misma
# forma de dict que antes (YAML); el resto del sistema (API/aprobación/Metricool/skills)
# no cambia. `id`/`fecha_creacion` permiten preservar identidad al migrar desde YAML.


def crear_publicacion(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    copy_in: str = "",
    estado: str = "borrador",
    veredicto: str = "",
    fecha_programada: str = "",
    origen: str = "",
    imagen: str = "",
    imagen_fuente: str = "",
    tipo_contenido: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
    id: str = "",
    fecha_creacion: str = "",
) -> dict[str, Any]:
    return db.crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=contenido,
        copy_in=copy_in,
        estado=estado,
        veredicto=veredicto,
        fecha_programada=fecha_programada,
        origen=origen,
        imagen=imagen,
        imagen_fuente=imagen_fuente,
        tipo_contenido=tipo_contenido,
        evergreen=evergreen,
        autor=autor,
        id=id,
        fecha_creacion=fecha_creacion,
    )


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return db.crear_publicaciones(lista)


def listar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    *,
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    return db.listar_publicaciones(
        marca=marca,
        red=red,
        estado=estado,
        evergreen=evergreen,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
) -> int:
    return db.contar_publicaciones(marca=marca, red=red, estado=estado, evergreen=evergreen)


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    return db.obtener_publicacion(publicacion_id)


def actualizar_publicacion(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_publicacion(publicacion_id, campos)


def borrar_publicacion(publicacion_id: str) -> bool:
    return db.borrar_publicacion(publicacion_id)


def reclamar_preparacion(publicacion_id: str, ts: str) -> bool:
    return db.reclamar_preparacion(publicacion_id, ts)


# --------------------------------------------------------------------------- #
# Grupos de hashtags (OPERACIONAL: Postgres via db.py; rezago cerrado, ADR 0006) #
# --------------------------------------------------------------------------- #
# CONTENIDO editorial reutilizable que vivia file-backed (YAML + indice SQLite de rutas
# absolutas). El indice se desincronizaba al recrear contenedores; ahora vive en Postgres
# (ADR 0006). El dict devuelto conserva las mismas claves; la fachada delega 1:1 en db.py.


def listar_grupos_hashtags(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return db.listar_grupos_hashtags(limite=limite, desplazamiento=desplazamiento)


def contar_grupos_hashtags() -> int:
    return db.contar_grupos_hashtags()


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    return db.obtener_grupo_hashtags(grupo_id)


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    return db.crear_grupo_hashtags(nombre, marca=marca, hashtags=hashtags)


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_grupo_hashtags(grupo_id, campos)


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    return db.borrar_grupo_hashtags(grupo_id)


# --------------------------------------------------------------------------- #
# Franjas editoriales (OPERACIONAL: Postgres via db.py; rezago cerrado, ADR 0006) #
# --------------------------------------------------------------------------- #


def listar_franjas() -> list[dict[str, Any]]:
    return db.listar_franjas()


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    return db.crear_franja(dia_semana, hora, marca=marca, red=red)


def borrar_franja(franja_id: str) -> bool:
    return db.borrar_franja(franja_id)


# --------------------------------------------------------------------------- #
# Plantillas de copy PLANO: el concepto se FUSIONÓ en el catálogo unificado          #
# `plantilla_contenido` (modo 'plano'). Las funciones planas YAML (`ficheros.*`) ya     #
# no tienen fachada aquí; solo las usa `migrar_contenido.migrar_plantillas_plano` para  #
# la migración one-shot. Ver `crear_plantilla_contenido` (modo) más abajo.              #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Fuentes RSS + items vistos + salud (OPERACIONAL: Postgres via db.py; ADR 0006) #
# --------------------------------------------------------------------------- #
# Ultimo rezago file-backed cerrado: el indice SQLite de rutas absolutas dejaba la pagina de
# Fuentes RSS vacia tras recrear contenedores. Ahora vive en Postgres (ADR 0006). El dict
# devuelto conserva las mismas claves; la fachada delega 1:1 en db.py.


def listar_fuentes_rss(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return db.listar_fuentes_rss(limite=limite, desplazamiento=desplazamiento)


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
) -> dict[str, Any]:
    return db.crear_fuente_rss(
        nombre,
        url,
        marca=marca,
        incluir=incluir,
        excluir=excluir,
        redes_def=redes_def,
        propia=propia,
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


# --- Hub generico de fuentes (item G): delega 1:1 en db.py ----------------- #


def listar_fuentes(*, tipo: str | None = None) -> list[dict[str, Any]]:
    return db.listar_fuentes(tipo=tipo)


def obtener_fuente(fuente_id: str) -> dict[str, Any] | None:
    return db.obtener_fuente(fuente_id)


def crear_fuente(
    *,
    tipo: str,
    nombre: str,
    config: dict[str, Any] | None = None,
    marca: str = "",
    prioridad: int = 0,
    etiquetas: list[str] | None = None,
) -> dict[str, Any]:
    return db.crear_fuente(
        tipo=tipo, nombre=nombre, config=config, marca=marca, prioridad=prioridad, etiquetas=etiquetas
    )


def actualizar_fuente(fuente_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_fuente(fuente_id, campos)


def borrar_fuente(fuente_id: str) -> bool:
    return db.borrar_fuente(fuente_id)


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


# --------------------------------------------------------------------------- #
# Publicaciones comerciales (OPERACIONAL: Postgres via db.py; serie temporal)    #
# --------------------------------------------------------------------------- #
#
# El apartado comercial es una serie temporal append-only (snapshots de
# interacciones/alcance); no encaja en un fichero por entidad. La fachada delega 1:1
# en db.py.


def crear_publicacion_comercial(
    url: str = "",
    *,
    id_post_metricool: str = "",
    titulo: str = "",
    marca: str = "",
    cliente: str = "",
    campania: str = "",
    red: str = "",
    formato: str = "",
    metrica_objetivo: str = "interacciones",
    objetivo: int = 0,
    estado: str = "activa",
    publicado: str = "",
    notas: str = "",
) -> dict[str, Any]:
    return db.crear_publicacion_comercial(
        url,
        id_post_metricool=id_post_metricool,
        titulo=titulo,
        marca=marca,
        cliente=cliente,
        campania=campania,
        red=red,
        formato=formato,
        metrica_objetivo=metrica_objetivo,
        objetivo=objetivo,
        estado=estado,
        publicado=publicado,
        notas=notas,
    )


def listar_publicaciones_comerciales(
    estado: str | None = None,
    cliente: str | None = None,
    campania: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_publicaciones_comerciales(estado=estado, cliente=cliente, campania=campania)


def obtener_publicacion_comercial(publicacion_id: str) -> dict[str, Any] | None:
    return db.obtener_publicacion_comercial(publicacion_id)


def actualizar_publicacion_comercial(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_publicacion_comercial(publicacion_id, campos)


def marcar_aviso_comercial(publicacion_id: str, ts: str) -> None:
    return db.marcar_aviso_comercial(publicacion_id, ts)


def borrar_publicacion_comercial(publicacion_id: str) -> bool:
    return db.borrar_publicacion_comercial(publicacion_id)


def registrar_snapshot_comercial(
    publicacion_id: str,
    ts: str,
    interacciones: int,
    alcance: int,
    visualizaciones: int = 0,
    *,
    granulares: dict[str, Any] | None = None,
) -> bool:
    return db.registrar_snapshot_comercial(
        publicacion_id, ts, interacciones, alcance, visualizaciones, granulares=granulares
    )


def listar_snapshots_comerciales(publicacion_id: str) -> list[dict[str, Any]]:
    return db.listar_snapshots_comerciales(publicacion_id)


def ultimo_snapshot_comercial(publicacion_id: str) -> dict[str, Any] | None:
    return db.ultimo_snapshot_comercial(publicacion_id)


# --------------------------------------------------------------------------- #
# Cache de metricas (OPERACIONAL: Postgres via db.py; lo orquesta metricas_cache.py) #
# --------------------------------------------------------------------------- #


def leer_metricas_cache(clave: str) -> dict[str, Any] | None:
    return db.leer_metricas_cache(clave)


def guardar_metricas_cache(
    clave: str,
    tipo: str,
    rango: str,
    marca: str,
    payload: dict[str, Any],
    fuente: str,
    generado_en: str,
) -> None:
    return db.guardar_metricas_cache(
        clave, tipo, rango, marca, payload, fuente, generado_en
    )


# --------------------------------------------------------------------------- #
# Rota de horarios del equipo (OPERACIONAL: Postgres via db.py)                  #
# --------------------------------------------------------------------------- #
#
# Eventos/transmisiones + turnos (asignaciones) de la parrilla del equipo (F4 · #144).
# No es contenido editorial por marca: es dato operacional de coordinacion interna,
# por eso vive en Postgres. La fachada delega 1:1 en db.py.


def crear_evento_rota(
    titulo: str,
    *,
    fecha: str = "",
    hora: str = "",
    contenido: str = "",
    nota: str = "",
    tipo_cobertura: str = "transmision",
    prioridad: str = "media",
) -> dict[str, Any]:
    return db.crear_evento_rota(
        titulo,
        fecha=fecha,
        hora=hora,
        contenido=contenido,
        nota=nota,
        tipo_cobertura=tipo_cobertura,
        prioridad=prioridad,
    )


def listar_eventos_rota(
    desde: str | None = None,
    hasta: str | None = None,
    *,
    solo_cambiados: bool = False,
    tipo_cobertura: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_eventos_rota(
        desde=desde, hasta=hasta, solo_cambiados=solo_cambiados, tipo_cobertura=tipo_cobertura
    )


def obtener_evento_rota(evento_id: str) -> dict[str, Any] | None:
    return db.obtener_evento_rota(evento_id)


def actualizar_evento_rota(evento_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_evento_rota(evento_id, campos)


def borrar_evento_rota(evento_id: str) -> bool:
    return db.borrar_evento_rota(evento_id)


def crear_turno_rota(
    semana: str,
    fecha: str,
    *,
    miembro_id: str = "",
    miembro_nombre: str = "",
    franja_id: str = "",
    estado: str = ESTADO_ROTA_PROPUESTO,
    override: bool = False,
    motivo: str = "",
    nota_relevo: str = "",
    franja: str | None = None,
) -> dict[str, Any]:
    """Crea un turno (horario `(fecha, franja_id)` para un miembro). Delegado en `db.py`.

    Retrocompat para tests legados: acepta `franja` (literal 'matutino'/'vespertino'/
    'descanso'). El shim vive en `db.crear_turno_rota` (la traduccion necesita conexion BD
    para sembrar franjas por defecto). Codigo NUEVO debe pasar `franja_id` directamente.
    """
    return db.crear_turno_rota(
        semana,
        fecha,
        miembro_id=miembro_id,
        miembro_nombre=miembro_nombre,
        franja_id=franja_id,
        estado=estado,
        override=override,
        motivo=motivo,
        nota_relevo=nota_relevo,
        franja=franja,
    )


def crear_turnos_rota_lote(turnos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Crea varios turnos en lote (delegado en `db.py`)."""
    return db.crear_turnos_rota_lote(turnos)


def listar_turnos_rota(semana: str | None = None) -> list[dict[str, Any]]:
    return db.listar_turnos_rota(semana=semana)


def obtener_turno_rota(turno_id: str) -> dict[str, Any] | None:
    return db.obtener_turno_rota(turno_id)


def existe_turno_para(
    miembro_id: str, fecha: str, franja_id: str
) -> dict[str, Any] | None:
    """True si existe un turno para `(miembro_id, fecha, franja_id)` (delegado en `db.py`)."""
    return db.existe_turno_para(miembro_id, fecha, franja_id)


def actualizar_turno_rota(turno_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_turno_rota(turno_id, campos)


def actualizar_turnos_rota_lote(
    ids: list[str], campos: dict[str, Any]
) -> tuple[int, list[dict[str, Any]]]:
    """UPDATE masivo sobre `rota_turnos` por lista de ids (delega en `db.py`)."""
    return db.actualizar_turnos_rota_lote(ids, campos)


def copiar_turnos_rota(
    de_lunes: str, a_lunes: str, *, reemplazar: bool = False
) -> int:
    """Copia los turnos de una semana a otra (offset +N dias por fila)."""
    return db.copiar_turnos_rota(de_lunes, a_lunes, reemplazar=reemplazar)


def borrar_turnos_semana_rota(semana: str) -> int:
    return db.borrar_turnos_semana_rota(semana)


def borrar_turno_rota(turno_id: str) -> bool:
    return db.borrar_turno_rota(turno_id)


def borrar_turnos_rota_lote(ids: list[str]) -> int:
    return db.borrar_turnos_rota_lote(ids)


def aprobar_semana_rota(semana: str) -> int:
    return db.aprobar_semana_rota(semana)


def desaprobar_semana_rota(semana: str) -> int:
    return db.desaprobar_semana_rota(semana)


def duplicar_turno_rota(
    turno_id: str,
    *,
    fecha: str | None = None,
    miembro_id: str | None = None,
    miembro_nombre: str | None = None,
    franja_id: str | None = None,
    semana: str | None = None,
) -> dict[str, Any] | None:
    """Clona un turno con overrides (delegado en `db.py`)."""
    return db.duplicar_turno_rota(
        turno_id,
        fecha=fecha,
        miembro_id=miembro_id,
        miembro_nombre=miembro_nombre,
        franja_id=franja_id,
        semana=semana,
    )


def crear_ausencia_rota(
    miembro_id: str,
    desde: str,
    hasta: str,
    *,
    miembro_nombre: str = "",
    tipo: str = "otro",
    motivo: str = "",
) -> dict[str, Any]:
    return db.crear_ausencia_rota(
        miembro_id, desde, hasta, miembro_nombre=miembro_nombre, tipo=tipo, motivo=motivo
    )


def listar_ausencias_rota(
    miembro_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_ausencias_rota(miembro_id=miembro_id, desde=desde, hasta=hasta)


def obtener_ausencia_rota(ausencia_id: str) -> dict[str, Any] | None:
    return db.obtener_ausencia_rota(ausencia_id)


def actualizar_ausencia_rota(
    ausencia_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_ausencia_rota(ausencia_id, campos)


def borrar_ausencia_rota(ausencia_id: str) -> bool:
    return db.borrar_ausencia_rota(ausencia_id)


# --------------------------------------------------------------------------- #
# Piezas de la parrilla (OPERACIONAL: Postgres via db.py; #150 PARRILLA 2026)   #
# --------------------------------------------------------------------------- #
#
# Una pieza = un POST individual (no un evento). Un evento puede generar varias piezas;
# tambien hay piezas SUELTAS (campanas evergreen sin evento). La fachada delega 1:1 en
# db.py.


def crear_pieza_rota(
    *,
    evento_id: str = "",
    programa: str = "",
    red_social: str = "",
    tipo_pieza: str = "",
    contenido_sugerido: str = "",
    dia: str = "",
    hora_post: str = "",
    estado: str = "pendiente",
    material_entregado: bool = False,
    contenido_entregado: bool = False,
    publicado: bool = False,
    enlace: str = "",
    responsable_id: str = "",
    responsable_nombre: str = "",
    notas: str = "",
    salida: str = "",
    comentarios: str = "",
    fecha_entrega_material: str = "",
    always_on: bool = False,
) -> dict[str, Any]:
    return db.crear_pieza_rota(
        evento_id=evento_id,
        programa=programa,
        red_social=red_social,
        tipo_pieza=tipo_pieza,
        contenido_sugerido=contenido_sugerido,
        dia=dia,
        hora_post=hora_post,
        estado=estado,
        material_entregado=material_entregado,
        contenido_entregado=contenido_entregado,
        publicado=publicado,
        enlace=enlace,
        responsable_id=responsable_id,
        responsable_nombre=responsable_nombre,
        notas=notas,
        salida=salida,
        comentarios=comentarios,
        fecha_entrega_material=fecha_entrega_material,
        always_on=always_on,
    )


def listar_piezas_rota(
    *,
    evento_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    red: str | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    responsable_id: str | None = None,
    programa: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_piezas_rota(
        evento_id=evento_id,
        desde=desde,
        hasta=hasta,
        red=red,
        tipo=tipo,
        estado=estado,
        responsable_id=responsable_id,
        programa=programa,
    )


def obtener_pieza_rota(pieza_id: str) -> dict[str, Any] | None:
    return db.obtener_pieza_rota(pieza_id)


def actualizar_pieza_rota(
    pieza_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_pieza_rota(pieza_id, campos)


def borrar_pieza_rota(pieza_id: str) -> bool:
    return db.borrar_pieza_rota(pieza_id)


def borrar_piezas_rota_lote(ids: list[str]) -> int:
    """Borra varias piezas a la vez (delegado en `db.py`)."""
    return db.borrar_piezas_rota_lote(ids)


def duplicar_pieza_rota(
    pieza_id: str, *, dia: str | None = None, evento_id: str | None = None
) -> dict[str, Any] | None:
    """Clona una pieza (workflow reset; delegado en `db.py`)."""
    return db.duplicar_pieza_rota(pieza_id, dia=dia, evento_id=evento_id)


# --------------------------------------------------------------------------- #
# Tablero de CONTENIDO unificado (OPERACIONAL: Postgres via db.py)              #
# --------------------------------------------------------------------------- #
# Padre `contenido` (item del tablero: importante/evergreen/evento, o tarea libre) +
# hijos `contenido_plataforma` (una fila por red con estado y checklist). La fachada
# delega 1:1 en `db.py`.


def crear_contenido(
    *,
    clase: str = "contenido",
    flujo: str = "",
    titulo: str = "",
    descripcion: str = "",
    marca: str = "",
    evento_id: str = "",
    programa: str = "",
    prioridad: str = "media",
    estado: str = "pendiente",
    fecha_objetivo: str = "",
    hora_objetivo: str = "",
    fecha_entrega: str = "",
    autor: dict[str, str] | None = None,
    responsable: dict[str, str] | None = None,
    origen: str = "",
    notas: str = "",
    tipo_contenido: str = "ia",
    id_post_metricool: str = "",
    senal_viralidad: int = 0,
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea un item del tablero (padre). Delegado en `db.py`."""
    return db.crear_contenido(
        clase=clase,
        flujo=flujo,
        titulo=titulo,
        descripcion=descripcion,
        marca=marca,
        evento_id=evento_id,
        programa=programa,
        prioridad=prioridad,
        estado=estado,
        fecha_objetivo=fecha_objetivo,
        hora_objetivo=hora_objetivo,
        fecha_entrega=fecha_entrega,
        autor=autor,
        responsable=responsable,
        origen=origen,
        notas=notas,
        tipo_contenido=tipo_contenido,
        id_post_metricool=id_post_metricool,
        senal_viralidad=senal_viralidad,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_contenido(
    *,
    clase: str | None = None,
    flujo: str | None = None,
    marca: str | None = None,
    evento_id: str | None = None,
    responsable_id: str | None = None,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Lista items del tablero (padres), filtros combinables. Delegado en `db.py`."""
    return db.listar_contenido(
        clase=clase,
        flujo=flujo,
        marca=marca,
        evento_id=evento_id,
        responsable_id=responsable_id,
        estado=estado,
        desde=desde,
        hasta=hasta,
    )


def obtener_contenido(contenido_id: str) -> dict[str, Any] | None:
    return db.obtener_contenido(contenido_id)


def actualizar_contenido(
    contenido_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_contenido(contenido_id, campos)


def borrar_contenido(contenido_id: str) -> bool:
    return db.borrar_contenido(contenido_id)


def crear_contenido_plataforma(
    *,
    contenido_id: str,
    red: str,
    estado: str = "pendiente",
    falta_copy: bool | None = None,
    falta_imagen: bool | None = None,
    falta_revision: bool = True,
    falta_publicar: bool = True,
    copy: str = "",
    copy_in: str = "",
    imagen: str = "",
    imagen_fuente: str = "",
    foto: str = "",
    veredicto: str = "",
    revisor_id: str = "",
    revisor_nombre: str = "",
    revisado_en: str = "",
    enviado_a_revision_en: str = "",
    fecha_programada: str = "",
    preparado_en: str = "",
    id_post_metricool: str = "",
    enlace: str = "",
    evergreen: bool = False,
    es_publicacion: bool = False,
    hora_post: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea una fila por plataforma de un contenido. Delegado en `db.py`."""
    return db.crear_contenido_plataforma(
        contenido_id=contenido_id,
        red=red,
        estado=estado,
        falta_copy=falta_copy,
        falta_imagen=falta_imagen,
        falta_revision=falta_revision,
        falta_publicar=falta_publicar,
        copy=copy,
        copy_in=copy_in,
        imagen=imagen,
        imagen_fuente=imagen_fuente,
        foto=foto,
        veredicto=veredicto,
        revisor_id=revisor_id,
        revisor_nombre=revisor_nombre,
        revisado_en=revisado_en,
        enviado_a_revision_en=enviado_a_revision_en,
        fecha_programada=fecha_programada,
        preparado_en=preparado_en,
        id_post_metricool=id_post_metricool,
        enlace=enlace,
        evergreen=evergreen,
        es_publicacion=es_publicacion,
        hora_post=hora_post,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_contenido_plataforma(
    contenido_id: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_contenido_plataforma(contenido_id)


def obtener_contenido_plataforma(plataforma_id: str) -> dict[str, Any] | None:
    return db.obtener_contenido_plataforma(plataforma_id)


def actualizar_contenido_plataforma(
    plataforma_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_contenido_plataforma(plataforma_id, campos)


def borrar_contenido_plataforma(plataforma_id: str) -> bool:
    return db.borrar_contenido_plataforma(plataforma_id)


# --------------------------------------------------------------------------- #
# Plantillas de CONTENIDO por tipo de nota (OPERACIONAL: Postgres via db.py)    #
# --------------------------------------------------------------------------- #
# Distintas de `plantillas` (copy plano en YAML): modelan un TIPO de nota recurrente con
# ESTRUCTURA `{{variables}}` + lista declarada de variables. Activos reutilizables (no
# editorial por marca en fichero): viven en Postgres. La fachada delega 1:1 en `db.py`.


def crear_plantilla_contenido(
    *,
    nombre: str,
    modo: str = "estructura",
    tipo_nota: str = "",
    descripcion: str = "",
    marca: str = "",
    red: str = "",
    contenido: str = "",
    estructura: str = "",
    variables: str = "[]",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_plantilla_contenido(
        nombre=nombre,
        modo=modo,
        tipo_nota=tipo_nota,
        descripcion=descripcion,
        marca=marca,
        red=red,
        contenido=contenido,
        estructura=estructura,
        variables=variables,
        activo=activo,
        autor=autor,
        id=id,
        creado=creado,
        actualizado=actualizado,
    )


def listar_plantillas_contenido(
    *, marca: str | None = None, tipo_nota: str | None = None, solo_activas: bool = False
) -> list[dict[str, Any]]:
    return db.listar_plantillas_contenido(
        marca=marca, tipo_nota=tipo_nota, solo_activas=solo_activas
    )


def obtener_plantilla_contenido(plantilla_id: str) -> dict[str, Any] | None:
    return db.obtener_plantilla_contenido(plantilla_id)


def actualizar_plantilla_contenido(
    plantilla_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_plantilla_contenido(plantilla_id, campos)


def borrar_plantilla_contenido(plantilla_id: str) -> bool:
    return db.borrar_plantilla_contenido(plantilla_id)


# --------------------------------------------------------------------------- #
# Biblioteca de MEDIOS interna (OPERACIONAL: Postgres via db.py)                #
# --------------------------------------------------------------------------- #
# Catalogo editorial de medios APROBADOS y etiquetables. El binario lo guarda/sirve
# `media.py`; aqui solo el catalogo reutilizable. La fachada delega 1:1 en `db.py`.


def crear_media_biblioteca(
    *,
    objeto: str,
    tipo: str = "imagen",
    titulo: str = "",
    descripcion: str = "",
    marca: str = "",
    etiquetas: str = "[]",
    credito: str = "",
    aprobado: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_media_biblioteca(
        objeto=objeto,
        tipo=tipo,
        titulo=titulo,
        descripcion=descripcion,
        marca=marca,
        etiquetas=etiquetas,
        credito=credito,
        aprobado=aprobado,
        autor=autor,
        id=id,
        creado=creado,
        actualizado=actualizado,
    )


def listar_media_biblioteca(
    *, marca: str | None = None, tipo: str | None = None, solo_aprobados: bool = False
) -> list[dict[str, Any]]:
    return db.listar_media_biblioteca(
        marca=marca, tipo=tipo, solo_aprobados=solo_aprobados
    )


def obtener_media_biblioteca(media_id: str) -> dict[str, Any] | None:
    return db.obtener_media_biblioteca(media_id)


def existe_media_objeto(objeto: str) -> bool:
    return db.existe_media_objeto(objeto)


def actualizar_media_biblioteca(
    media_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_media_biblioteca(media_id, campos)


def borrar_media_biblioteca(media_id: str) -> dict[str, Any] | None:
    return db.borrar_media_biblioteca(media_id)


# --------------------------------------------------------------------------- #
# Webhooks salientes + bitacora de eventos internos (OPERACIONAL: Postgres)      #
# --------------------------------------------------------------------------- #


def crear_webhook(
    *,
    nombre: str = "",
    url: str = "",
    eventos: list[str] | None = None,
    formato: str = "generico",
    secreto: str = "",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
) -> dict[str, Any]:
    return db.crear_webhook(
        nombre=nombre,
        url=url,
        eventos=eventos,
        formato=formato,
        secreto=secreto,
        activo=activo,
        autor=autor,
        id=id,
    )


def listar_webhooks(*, solo_activos: bool = False) -> list[dict[str, Any]]:
    return db.listar_webhooks(solo_activos=solo_activos)


def listar_webhooks_para(evento: str) -> list[dict[str, Any]]:
    """Webhooks activos suscritos a `evento` (CON secreto; uso interno del repartidor)."""
    return db.listar_webhooks_para(evento)


def obtener_webhook(webhook_id: str) -> dict[str, Any] | None:
    return db.obtener_webhook(webhook_id)


def obtener_webhook_con_secreto(webhook_id: str) -> dict[str, Any] | None:
    """Suscripcion por id CON el secreto crudo (uso interno: probar/repartir)."""
    return db.obtener_webhook_con_secreto(webhook_id)


def actualizar_webhook(
    webhook_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_webhook(webhook_id, campos)


def borrar_webhook(webhook_id: str) -> bool:
    return db.borrar_webhook(webhook_id)


def registrar_evento_interno(
    *,
    tipo: str,
    contenido_id: str = "",
    plataforma_id: str = "",
    clave_idempotencia: str = "",
    payload: dict[str, Any] | None = None,
) -> bool:
    """Registra un evento interno (False si su clave de idempotencia ya existia)."""
    return db.registrar_evento_interno(
        tipo=tipo,
        contenido_id=contenido_id,
        plataforma_id=plataforma_id,
        clave_idempotencia=clave_idempotencia,
        payload=payload,
    )


def listar_eventos_internos(*, limite: int = 50) -> list[dict[str, Any]]:
    return db.listar_eventos_internos(limite=limite)


# --------------------------------------------------------------------------- #
# Etiquetas editoriales (campaña / vertical / tipo) y su N:M con `contenido`     #
# --------------------------------------------------------------------------- #
# Clasifican transversalmente las piezas del tablero. `marca=''` = etiqueta global.
# La fachada delega 1:1 en `db.py`; la validacion vive en `api/etiquetas`.


def crear_etiqueta(
    *,
    nombre: str,
    clase: str = "campania",
    marca: str = "",
    color: str = "",
    activo: bool = True,
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea una etiqueta editorial. Delegado en `db.py`."""
    return db.crear_etiqueta(
        nombre=nombre,
        clase=clase,
        marca=marca,
        color=color,
        activo=activo,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_etiquetas(
    *, marca: str | None = None, clase: str | None = None, solo_activas: bool = False
) -> list[dict[str, Any]]:
    """Lista etiquetas (`marca` incluye las globales). Delegado en `db.py`."""
    return db.listar_etiquetas(marca=marca, clase=clase, solo_activas=solo_activas)


def obtener_etiqueta(etiqueta_id: str) -> dict[str, Any] | None:
    return db.obtener_etiqueta(etiqueta_id)


def existe_etiqueta_nombre(
    nombre: str, clase: str, marca: str, *, excluir_id: str = ""
) -> bool:
    return db.existe_etiqueta_nombre(nombre, clase, marca, excluir_id=excluir_id)


def actualizar_etiqueta(
    etiqueta_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_etiqueta(etiqueta_id, campos)


def borrar_etiqueta(etiqueta_id: str) -> bool:
    return db.borrar_etiqueta(etiqueta_id)


def asignar_etiqueta(contenido_id: str, etiqueta_id: str) -> None:
    db.asignar_etiqueta(contenido_id, etiqueta_id)


def quitar_etiqueta(contenido_id: str, etiqueta_id: str) -> bool:
    return db.quitar_etiqueta(contenido_id, etiqueta_id)


def etiquetas_por_contenido() -> dict[str, list[str]]:
    return db.etiquetas_por_contenido()


def ids_contenido_con_etiqueta(etiqueta_id: str) -> set[str]:
    return db.ids_contenido_con_etiqueta(etiqueta_id)


# --------------------------------------------------------------------------- #
# Ola COLABORACION: comentarios + versiones de copy + aprobacion multinivel    #
# --------------------------------------------------------------------------- #
# Tres familias APENDIDAS al tablero de contenido (Planable-style). La fachada solo
# delega en `db.py`; la validacion y la logica de cadena viven en la API/dominio.


def crear_comentario(
    *,
    contenido_id: str,
    plataforma_id: str = "",
    texto: str,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    return db.crear_comentario(
        contenido_id=contenido_id,
        plataforma_id=plataforma_id,
        texto=texto,
        autor=autor,
    )


def listar_comentarios(
    contenido_id: str, plataforma_id: str | None = None
) -> list[dict[str, Any]]:
    return db.listar_comentarios(contenido_id, plataforma_id)


def obtener_comentario(comentario_id: str) -> dict[str, Any] | None:
    return db.obtener_comentario(comentario_id)


def comentarios_sin_resolver(contenido_id: str, plataforma_id: str = "") -> int:
    """Cuenta los comentarios SIN resolver que afectan a una pieza (item B).

    Un comentario afecta a la pieza si es del item entero (`plataforma_id`="") o de ESTA
    plataforma concreta. Un hilo sin resolver es una objecion editorial pendiente: bloquea
    publicar (gate en `api/aprobacion.programar`) y la UI lo muestra como contador. Lectura
    sobre `contenido_comentarios` (sin esquema nuevo).
    """
    if not contenido_id:
        return 0
    sin_resolver = 0
    for c in db.listar_comentarios(contenido_id):
        if c.get("resuelto"):
            continue
        pid = (c.get("plataforma_id") or "").strip()
        if not pid or (plataforma_id and pid == plataforma_id):
            sin_resolver += 1
    return sin_resolver


def actualizar_comentario(
    comentario_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_comentario(comentario_id, campos)


def borrar_comentario(comentario_id: str) -> bool:
    return db.borrar_comentario(comentario_id)


def registrar_copy_version(
    *,
    plataforma_id: str,
    contenido_id: str,
    copy: str,
    autor: dict[str, str] | None = None,
    nota: str = "",
) -> dict[str, Any]:
    return db.registrar_copy_version(
        plataforma_id=plataforma_id,
        contenido_id=contenido_id,
        copy=copy,
        autor=autor,
        nota=nota,
    )


def listar_copy_versiones(plataforma_id: str) -> list[dict[str, Any]]:
    return db.listar_copy_versiones(plataforma_id)


def obtener_copy_version(version_id: str) -> dict[str, Any] | None:
    return db.obtener_copy_version(version_id)


def crear_cadena_aprobacion(
    *,
    plataforma_id: str,
    contenido_id: str,
    etiquetas: list[str],
    cargos: list[str] | None = None,
) -> list[dict[str, Any]]:
    return db.crear_cadena_aprobacion(
        plataforma_id=plataforma_id,
        contenido_id=contenido_id,
        etiquetas=etiquetas,
        cargos=cargos,
    )


def listar_aprobaciones(plataforma_id: str) -> list[dict[str, Any]]:
    return db.listar_aprobaciones(plataforma_id)


def obtener_aprobacion(aprobacion_id: str) -> dict[str, Any] | None:
    return db.obtener_aprobacion(aprobacion_id)


def actualizar_aprobacion(
    aprobacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_aprobacion(aprobacion_id, campos)


def duplicar_evento_rota(
    evento_id: str,
    *,
    fecha: str | None = None,
    hora: str | None = None,
    titulo: str | None = None,
) -> dict[str, Any] | None:
    """Clona un evento (sin turnos, `cambiado` reset; delegado en `db.py`)."""
    return db.duplicar_evento_rota(evento_id, fecha=fecha, hora=hora, titulo=titulo)


# --------------------------------------------------------------------------- #
# Catalogo de programas (OPERACIONAL: Postgres via db.py; #150)                #
# --------------------------------------------------------------------------- #


def crear_programa_rota(
    nombre: str,
    *,
    descripcion: str = "",
    color: str = "",
    inicio: str = "",
    fin: str = "",
    activo: bool = True,
) -> dict[str, Any]:
    return db.crear_programa_rota(
        nombre,
        descripcion=descripcion,
        color=color,
        inicio=inicio,
        fin=fin,
        activo=activo,
    )


def listar_programas_rota(*, activo: bool | None = None) -> list[dict[str, Any]]:
    return db.listar_programas_rota(activo=activo)


def obtener_programa_rota(programa_id: str) -> dict[str, Any] | None:
    return db.obtener_programa_rota(programa_id)


def actualizar_programa_rota(
    programa_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_programa_rota(programa_id, campos)


def borrar_programa_rota(programa_id: str) -> bool:
    return db.borrar_programa_rota(programa_id)


def existe_programa_por_nombre(nombre: str) -> bool:
    return db.existe_programa_por_nombre(nombre)


def contar_piezas_por_programa(nombre: str) -> int:
    return db.contar_piezas_por_programa(nombre)


# --------------------------------------------------------------------------- #
# Solicitudes de cambio de turno entre companeros (OPERACIONAL; #175)          #
# --------------------------------------------------------------------------- #
#
# Cuando un CM (A) le pide a otro (B) intercambiar turnos por un asunto personal y
# Elias (admin) lo aprueba, se aplica el swap sobre `rota_turnos_trabajo`. Las ausencias
# REALES (vacaciones/baja) viven en SAP, no aqui. La fachada delega 1:1 en db.py.


def crear_swap_turno(
    solicitante_id: str,
    destinatario_id: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    *,
    solicitante_nombre: str = "",
    destinatario_nombre: str = "",
    motivo: str = "",
) -> dict[str, Any]:
    return db.crear_swap_turno(
        solicitante_id,
        destinatario_id,
        fecha_a,
        franja_a,
        fecha_b,
        franja_b,
        solicitante_nombre=solicitante_nombre,
        destinatario_nombre=destinatario_nombre,
        motivo=motivo,
    )


def listar_swaps_turno(
    estado: str | None = None,
    solicitante_id: str | None = None,
    destinatario_id: str | None = None,
    *,
    mio_id: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_swaps_turno(
        estado=estado,
        solicitante_id=solicitante_id,
        destinatario_id=destinatario_id,
        mio_id=mio_id,
    )


def obtener_swap_turno(swap_id: str) -> dict[str, Any] | None:
    return db.obtener_swap_turno(swap_id)


def actualizar_swap_turno(
    swap_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_swap_turno(swap_id, campos)


def borrar_swap_turno(swap_id: str) -> bool:
    return db.borrar_swap_turno(swap_id)


def aplicar_swap_turno(
    swap_id: str,
    *,
    solicitante_id: str,
    solicitante_nombre: str,
    destinatario_id: str,
    destinatario_nombre: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    respuesta_admin: str = "",
) -> dict[str, Any] | None:
    return db.aplicar_swap_turno(
        swap_id,
        solicitante_id=solicitante_id,
        solicitante_nombre=solicitante_nombre,
        destinatario_id=destinatario_id,
        destinatario_nombre=destinatario_nombre,
        fecha_a=fecha_a,
        franja_a=franja_a,
        fecha_b=fecha_b,
        franja_b=franja_b,
        respuesta_admin=respuesta_admin,
    )


# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (OPERACIONAL: persistencia via db.py; #130 Fase 2) #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA y un WORKER (in-proceso en local, servicio aparte en hosted) clava y
# ejecuta `claude -p`. La fachada delega 1:1 en db.py (Postgres).


def encolar_job(gen_id: str, spec: str) -> str:
    return db.encolar_job(gen_id, spec)


def reclamar_job(worker: str = "") -> dict[str, Any] | None:
    return db.reclamar_job(worker)


def terminar_job(job_id: str) -> None:
    return db.terminar_job(job_id)


def cancelar_job(gen_id: str) -> bool:
    return db.cancelar_job(gen_id)


def job_cancelado(job_id: str) -> bool:
    return db.job_cancelado(job_id)


# --------------------------------------------------------------------------- #
# Config de franjas (#185)                                                     #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Franjas POR SEMANA (modelo "Mundial": N franjas/semana, solapes permitidos)   #
# --------------------------------------------------------------------------- #


def listar_franjas_semana(lunes: str) -> list[dict[str, Any]]:
    """Franjas vivas de la semana cuyo lunes es `lunes` (delegado en `db.py`)."""
    return db.listar_franjas_semana(lunes)


def obtener_franja_semana(franja_id: str) -> dict[str, Any] | None:
    return db.obtener_franja_semana(franja_id)


def crear_franja_semana(
    lunes: str,
    nombre: str,
    inicio: str,
    fin: str,
    *,
    orden: int = 0,
    es_descanso: bool = False,
) -> dict[str, Any] | None:
    return db.crear_franja_semana(
        lunes, nombre, inicio, fin, orden=orden, es_descanso=es_descanso
    )


def actualizar_franja_semana(
    franja_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_franja_semana(franja_id, campos)


def borrar_franja_semana(franja_id: str, *, forzar: bool = False) -> dict[str, Any]:
    return db.borrar_franja_semana(franja_id, forzar=forzar)


def contar_turnos_de_franja(franja_id: str) -> int:
    return db.contar_turnos_de_franja(franja_id)


def sembrar_franjas_por_defecto(lunes: str) -> list[dict[str, Any]]:
    return db.sembrar_franjas_por_defecto(lunes)


# --------------------------------------------------------------------------- #
# Coordinador por turno (ola "coord")                                          #
# --------------------------------------------------------------------------- #


def listar_coordinacion_semana(lunes: str) -> list[dict[str, Any]]:
    """Coordinaciones de la semana (delegado en `db.py`)."""
    return db.listar_coordinacion_semana(lunes)


def set_coordinador_rota(
    lunes: str, fecha: str, franja_id: str, coordinador_id: str
) -> dict[str, Any]:
    """UPSERT por (fecha, franja_id) del coordinador asignado a la celda."""
    return db.set_coordinador_rota(lunes, fecha, franja_id, coordinador_id)


def quitar_coordinador_rota(fecha: str, franja_id: str) -> bool:
    """Borra la coordinacion de la celda (fecha, franja_id)."""
    return db.quitar_coordinador_rota(fecha, franja_id)


def obtener_franjas_config() -> dict[str, str]:
    return db.obtener_franjas_config()


def guardar_franjas_config(
    matutino_inicio: str,
    matutino_fin: str,
    vespertino_inicio: str,
    vespertino_fin: str,
) -> dict[str, str]:
    return db.guardar_franjas_config(
        matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin
    )


# --------------------------------------------------------------------------- #
# PARRILLA: propuestas de importacion desde documento                          #
# --------------------------------------------------------------------------- #


def crear_propuesta_parrilla(
    *,
    semana: str,
    doc_nombre: str,
    doc_tipo: str = "",
    gen_id: str = "",
    autor_id: str = "",
    autor_nombre: str = "",
    estado: str = "generando",
) -> dict[str, Any]:
    return db.crear_propuesta_parrilla(
        semana=semana,
        doc_nombre=doc_nombre,
        doc_tipo=doc_tipo,
        gen_id=gen_id,
        autor_id=autor_id,
        autor_nombre=autor_nombre,
        estado=estado,
    )


def obtener_propuesta_parrilla(propuesta_id: str) -> dict[str, Any] | None:
    return db.obtener_propuesta_parrilla(propuesta_id)


def listar_propuestas_parrilla(
    *, estado: str | None = None, limite: int = 100
) -> list[dict[str, Any]]:
    return db.listar_propuestas_parrilla(estado=estado, limite=limite)


def actualizar_propuesta_parrilla(
    propuesta_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_propuesta_parrilla(propuesta_id, campos)


def aplicar_propuesta_parrilla(
    propuesta_id: str,
    operaciones: list[dict[str, Any]],
    *,
    nombres_miembros: dict[str, str],
    origen: str = "import-doc",
) -> dict[str, Any]:
    return db.aplicar_propuesta_parrilla(
        propuesta_id, operaciones, nombres_miembros=nombres_miembros, origen=origen
    )

"""Repositorio — dominio contenido. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

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
    formato: str = "foto",
    id_post_metricool: str = "",
    senal_viralidad: int = 0,
    qa_veredicto: str = "",
    qa_hallazgos: str = "",
    copy_pendiente: str = "",
    fecha_fuente: str = "",
    url_fuente: str = "",
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
        formato=formato,
        id_post_metricool=id_post_metricool,
        senal_viralidad=senal_viralidad,
        qa_veredicto=qa_veredicto,
        qa_hallazgos=qa_hallazgos,
        copy_pendiente=copy_pendiente,
        fecha_fuente=fecha_fuente,
        url_fuente=url_fuente,
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


def titulos_recientes_marca(marca: str, desde_iso: str) -> list[str]:
    """Títulos del contenido reciente de una marca (dedup del pipeline). Delegado en `db.py`."""
    return db.titulos_recientes_marca(marca, desde_iso)


def contar_contenido_origen_desde(marca: str, origen: str, desde_iso: str) -> int:
    """Nº de items del tablero de `marca` con `origen` creados desde `desde_iso`. Delegado en `db.py`."""
    return db.contar_contenido_origen_desde(marca, origen, desde_iso)


def existe_publicado_similar(
    marca: str, titulo: str, url: str = "", *, umbral: float = 0.85
) -> bool:
    """True si la marca ya publicó algo equivalente (título/URL). Delegado en `db.py`."""
    return db.existe_publicado_similar(marca, titulo, url, umbral=umbral)


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
    marca: str | None = None,
    estado: str = "pendiente",
    falta_copy: bool | None = None,
    falta_imagen: bool | None = None,
    falta_revision: bool = True,
    falta_publicar: bool = True,
    falta_video: bool | None = None,
    copy: str = "",
    copy_in: str = "",
    imagen: str = "",
    imagen_fuente: str = "",
    foto: str = "",
    video: str = "",
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
    copy_in_exento: bool = False,
    placa_oculta: bool = False,
    plantilla_diseno_id: str = "",
    foto_encuadre: str = "",
    fotos: str = "",
    qa_auto_hash: str = "",
    hora_post: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea una fila por plataforma de un contenido. Delegado en `db.py`."""
    return db.crear_contenido_plataforma(
        contenido_id=contenido_id,
        red=red,
        marca=marca,
        estado=estado,
        falta_copy=falta_copy,
        falta_imagen=falta_imagen,
        falta_revision=falta_revision,
        falta_publicar=falta_publicar,
        falta_video=falta_video,
        copy=copy,
        copy_in=copy_in,
        imagen=imagen,
        imagen_fuente=imagen_fuente,
        foto=foto,
        video=video,
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
        copy_in_exento=copy_in_exento,
        placa_oculta=placa_oculta,
        plantilla_diseno_id=plantilla_diseno_id,
        foto_encuadre=foto_encuadre,
        fotos=fotos,
        qa_auto_hash=qa_auto_hash,
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


def ajustar_plataformas_por_formato(
    contenido_id: str, formato: str
) -> dict[str, list[str]]:
    """Reconcilia las filas por plataforma de una pieza con su `formato` (FLIP foto<->video).

    El FORMATO de una pieza decide a qué redes va (`redes.redes_de_formato`: foto=3, video=5).
    Cuando el formato cambia hay que AÑADIR las filas que falten y, en `video->foto`, RETIRAR las
    redes extra (youtube/tiktok) SIN PERDER trabajo. Reglas (contrato F-video):

      - `foto->video`: crea las filas que falten de las 5 redes (youtube/tiktok) con
        `falta_copy=1`. En TODAS las filas, si no hay `video`, marca `falta_video=1` (el asset es
        obligatorio); `falta_imagen=0` (la imagen pasa a opcional: portada/thumbnail).
      - `video->foto`: deja las 3 redes de foto. Las extra (youtube/tiktok) se ELIMINAN solo si
        están VACÍAS (sin copy ni video); si tienen contenido, se CONSERVAN (no perder trabajo) y
        se reportan en `conservadas`. En las filas que quedan, `falta_video=0` (N/A) y, si no hay
        imagen real, `falta_imagen=1`.

    Idempotente y PURO de side-effects salvo las escrituras descritas. Devuelve un resumen
    `{creadas, eliminadas, conservadas}` (listas de ids de red) para que la API avise al usuario.
    """
    from . import redes

    formato = redes.normalizar_formato(formato)
    es_video = formato == redes.FORMATO_VIDEO
    objetivo = set(redes.redes_de_formato(formato))
    existentes = {
        p.get("red", ""): p for p in db.listar_contenido_plataforma(contenido_id)
    }

    creadas: list[str] = []
    eliminadas: list[str] = []
    conservadas: list[str] = []

    # 1) AÑADIR las redes del objetivo que aún no existan (orden de `redes.ids`).
    for red in redes.ids():
        if red not in objetivo or red in existentes:
            continue
        db.crear_contenido_plataforma(
            contenido_id=contenido_id,
            red=red,
            falta_copy=True,
            falta_video=es_video,
        )
        creadas.append(red)

    # 2) En `video->foto`, RETIRAR las redes que sobran (no están en el objetivo) solo si están
    #    vacías; si tienen copy o video, conservarlas y reportarlas (no perder trabajo).
    for red, plat in existentes.items():
        if red in objetivo or not red:
            continue
        tiene_trabajo = bool(
            str(plat.get("copy") or "").strip()
            or str(plat.get("video") or "").strip()
        )
        if tiene_trabajo:
            conservadas.append(red)
        else:
            db.borrar_contenido_plataforma(plat["id"])
            eliminadas.append(red)

    # 3) Reaplicar el checklist por formato a TODAS las filas que QUEDAN (objetivo + conservadas).
    #    foto: falta_video=0 (N/A); video: falta_video=1 si no hay asset de video. La imagen es
    #    obligatoria en foto (falta_imagen=1 si no hay imagen real) y opcional en video (0).
    for plat in db.listar_contenido_plataforma(contenido_id):
        tiene_video = bool(str(plat.get("video") or "").strip())
        tiene_imagen = bool(
            str(plat.get("imagen") or "").strip()
            or str(plat.get("foto") or "").strip()
            or str(plat.get("imagen_fuente") or "").strip()
        )
        if es_video:
            campos = {"falta_video": not tiene_video, "falta_imagen": False}
        else:
            campos = {"falta_video": False, "falta_imagen": not tiene_imagen}
        db.actualizar_contenido_plataforma(plat["id"], campos)

    return {"creadas": creadas, "eliminadas": eliminadas, "conservadas": conservadas}


def adjuntar_video_a_pieza(contenido_id: str, clave_media: str) -> list[str]:
    """Adjunta un mp4 renderizado a las plataformas de VIDEO de una pieza (cableado VIDEO).

    El asset de video vive POR PLATAFORMA (`contenido_plataforma.video` + flag `falta_video`).
    Una pieza de video arranca con `falta_video=1` hasta que se adjunta el asset; aquí cerramos
    ese hueco: para cada fila de la pieza cuya red sea de FORMATO VIDEO (`redes.redes_de_formato`
    -> instagram/x/facebook/tiktok/youtube) que EXISTA en la pieza, fija `video=clave_media` y
    `falta_video=0`. No crea filas (eso lo decide el formato vía `ajustar_plataformas_por_formato`)
    ni fuerza un flip de formato: solo cablea el asset a las redes de video ya presentes.

    Idempotente: re-adjuntar la misma clave deja el mismo estado. Devuelve la lista de ids de red
    tocadas (vacía si la pieza no tiene plataformas de video).
    """
    from . import redes

    redes_video = set(redes.redes_de_formato(redes.FORMATO_VIDEO))
    tocadas: list[str] = []
    for plat in db.listar_contenido_plataforma(contenido_id):
        if plat.get("red", "") not in redes_video:
            continue
        db.actualizar_contenido_plataforma(
            plat["id"], {"video": clave_media, "falta_video": False}
        )
        tocadas.append(plat["red"])
    return tocadas



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
    keywords: str = "",
    activo: bool = True,
    ttl_dias: int = 0,
    es_green: bool = False,
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
        keywords=keywords,
        activo=activo,
        ttl_dias=ttl_dias,
        es_green=es_green,
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


def obtener_etiqueta_por_nombre(nombre: str, clase: str, marca: str) -> dict[str, Any] | None:
    """Devuelve la etiqueta por (nombre, clase, marca). None si no existe."""
    return db.obtener_etiqueta_por_nombre(nombre, clase, marca)


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
# Taller GREEN / brainstorming: ideas evergreen. La fachada delega 1:1 en db; #
# la validacion vive en `api/green`.                                          #
# --------------------------------------------------------------------------- #


def crear_green_idea(
    *,
    marca: str = "",
    titulo: str = "",
    descripcion: str = "",
    estado: str = "propuesta",
    origen: str = "ia",
    generacion_id: str = "",
    contenido_id: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea una idea de contenido evergreen. Delegado en `db.py`."""
    return db.crear_green_idea(
        marca=marca,
        titulo=titulo,
        descripcion=descripcion,
        estado=estado,
        origen=origen,
        generacion_id=generacion_id,
        contenido_id=contenido_id,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_green_ideas(
    *, marca: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    """Lista ideas evergreen (recientes primero). Delegado en `db.py`."""
    return db.listar_green_ideas(marca=marca, estado=estado)


def obtener_green_idea(idea_id: str) -> dict[str, Any] | None:
    return db.obtener_green_idea(idea_id)


def actualizar_green_idea(
    idea_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_green_idea(idea_id, campos)


def borrar_green_idea(idea_id: str) -> bool:
    return db.borrar_green_idea(idea_id)



# --------------------------------------------------------------------------- #
# Insumos del día (cajones): delega 1:1 en db.py                               #
# --------------------------------------------------------------------------- #


def crear_insumo_lote(
    *,
    fecha: str,
    cajon: str,
    marca: str = "",
    origen_texto: str = "",
    origen_archivo: str = "",
    estado: str = "listo",
    error: str = "",
    total_items: int = 0,
    creado_por: str = "",
) -> dict[str, Any]:
    return db.crear_insumo_lote(
        fecha=fecha,
        cajon=cajon,
        marca=marca,
        origen_texto=origen_texto,
        origen_archivo=origen_archivo,
        estado=estado,
        error=error,
        total_items=total_items,
        creado_por=creado_por,
    )


def actualizar_insumo_lote(lote_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_insumo_lote(lote_id, campos)


def obtener_insumo_lote(lote_id: str) -> dict[str, Any] | None:
    return db.obtener_insumo_lote(lote_id)


def borrar_insumo_lote(lote_id: str) -> bool:
    return db.borrar_insumo_lote(lote_id)


def crear_insumo_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return db.crear_insumo_items(items)


def listar_insumo_items(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
    marca: str | None = None,
    lote_id: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_insumo_items(fecha=fecha, cajon=cajon, marca=marca, lote_id=lote_id)


def obtener_insumo_item(item_id: str) -> dict[str, Any] | None:
    return db.obtener_insumo_item(item_id)


def actualizar_insumo_item(item_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_insumo_item(item_id, campos)


def marcar_insumo_item_usado(item_id: str, *, contenido_id: str) -> dict[str, Any] | None:
    return db.marcar_insumo_item_usado(item_id, contenido_id=contenido_id)


def listar_lotes(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_lotes(fecha=fecha, cajon=cajon)


def dias_con_insumos() -> list[dict[str, Any]]:
    return db.dias_con_insumos()

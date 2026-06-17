"""Repositorio — dominio contenido. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
    verificar_publicacion_inmutable,
)

# --------------------------------------------------------------------------- #
# Tablero de CONTENIDO unificado (OPERACIONAL: Postgres via db.py)              #
# --------------------------------------------------------------------------- #
# Padre `contenido` (item del tablero: importante/evergreen/evento, o tarea libre) +
# hijos `pieza` (una fila por red con estado y checklist). La fachada
# delega 1:1 en `db.py`.


def crear_publicacion(
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
    categoria: str = "",
    tipo_contenido: str = "ia",
    formato: str = "foto",
    id_post_metricool: str = "",
    senal_viralidad: int = 0,
    verificacion_fuente: str = "",
    verificar_hallazgos: str = "",
    copy_pendiente: str = "",
    fecha_fuente: str = "",
    url_fuente: str = "",
    fuente_nombre: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea un item del tablero (padre). Delegado en `db.py`."""
    return db.crear_publicacion(
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
        categoria=categoria,
        tipo_contenido=tipo_contenido,
        formato=formato,
        id_post_metricool=id_post_metricool,
        senal_viralidad=senal_viralidad,
        verificacion_fuente=verificacion_fuente,
        verificar_hallazgos=verificar_hallazgos,
        copy_pendiente=copy_pendiente,
        fecha_fuente=fecha_fuente,
        url_fuente=url_fuente,
        fuente_nombre=fuente_nombre,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_publicacion(
    *,
    clase: str | None = None,
    flujo: str | None = None,
    marca: str | None = None,
    evento_id: str | None = None,
    responsable_id: str | None = None,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    creado_desde: str | None = None,
) -> list[dict[str, Any]]:
    """Lista items del tablero (padres), filtros combinables. Delegado en `db.py`."""
    return db.listar_publicacion(
        clase=clase,
        flujo=flujo,
        marca=marca,
        evento_id=evento_id,
        responsable_id=responsable_id,
        estado=estado,
        desde=desde,
        hasta=hasta,
        creado_desde=creado_desde,
    )


def titulos_recientes_marca(marca: str, desde_iso: str) -> list[str]:
    """Títulos del contenido reciente de una marca (dedup del pipeline). Delegado en `db.py`."""
    return db.titulos_recientes_marca(marca, desde_iso)


def listar_publicaciones_origenes(
    origenes: list[str], *, excluir_estado: str | None = None
) -> list[dict[str, Any]]:
    """Items del tablero con `origen` en la lista (WHERE en SQL). Delegado en `db.py`."""
    return db.listar_publicaciones_origenes(origenes, excluir_estado=excluir_estado)


def ids_publicacion_con_copy(marca: str | None = None) -> set[str]:
    """Ids de contenido con alguna pieza con copy (gate serial del pipeline). Delegado en `db.py`."""
    return db.ids_publicacion_con_copy(marca)


def verificacion_fuente_por_publicacion(publicacion_ids: list[str]) -> dict[str, str]:
    """Revision verificación (Verificar la fuente) por publicacion_id, en lote. Delegado en `db.py`."""
    return db.verificacion_fuente_por_publicacion(publicacion_ids)


def reparar_verificacion_en_curso_sueltos(umbral_iso: str) -> int:
    """Resetea a "" los `verificacion_fuente='en_curso'` atascados (limpiador). Delegado en `db.py`."""
    return db.reparar_verificacion_en_curso_sueltos(umbral_iso)


def resumen_plan_por_categoria(marca: str, desde_iso: str) -> dict[str, dict[str, int]]:
    """Generados/publicados por línea del plan (ventana). Delegado en `db.py`."""
    return db.resumen_plan_por_categoria(marca, desde_iso)


def contar_publicacion_origen_desde(marca: str, origen: str, desde_iso: str) -> int:
    """Nº de items del tablero de `marca` con `origen` creados desde `desde_iso`. Delegado en `db.py`."""
    return db.contar_publicacion_origen_desde(marca, origen, desde_iso)


def existe_publicado_similar(
    marca: str, titulo: str, url: str = "", *, umbral: float = 0.85
) -> bool:
    """True si la marca ya publicó algo equivalente (título/URL). Delegado en `db.py`."""
    return db.existe_publicado_similar(marca, titulo, url, umbral=umbral)


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    return db.obtener_publicacion(publicacion_id)


def actualizar_publicacion(
    publicacion_id: str, campos: dict[str, Any], *, version_esperada: int | None = None
) -> dict[str, Any] | None:
    return db.actualizar_publicacion(publicacion_id, campos, version_esperada=version_esperada)


def reclamar_publicacion(
    publicacion_id: str, *, responsable_id: str, responsable_nombre: str
) -> dict[str, Any] | None:
    return db.reclamar_publicacion(
        publicacion_id, responsable_id=responsable_id, responsable_nombre=responsable_nombre
    )


def borrar_publicacion(publicacion_id: str) -> bool:
    return db.borrar_publicacion(publicacion_id)


def crear_pieza_fila(
    *,
    publicacion_id: str,
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
    revision: str = "",
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
    carrusel: str = "",
    verificar_auto_hash: str = "",
    hora_post: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea una fila por plataforma de un contenido. Delegado en `db.py`."""
    return db.crear_pieza_fila(
        publicacion_id=publicacion_id,
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
        revision=revision,
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
        carrusel=carrusel,
        verificar_auto_hash=verificar_auto_hash,
        hora_post=hora_post,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_piezas_fila(
    publicacion_id: str | None = None,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_piezas_fila(publicacion_id, marca=marca)


def obtener_pieza_fila(pieza_id: str) -> dict[str, Any] | None:
    return db.obtener_pieza_fila(pieza_id)


def estado_pieza_por_publicacion(publicacion_ids: list[str]) -> dict[str, str]:
    return db.estado_pieza_por_publicacion(publicacion_ids)


def actualizar_pieza_fila(
    pieza_id: str, campos: dict[str, Any], *, version_esperada: int | None = None
) -> dict[str, Any] | None:
    # INMUTABILIDAD: una pieza ya `publicado` no se edita (copy/imagen/foto/plantilla…); lo
    # que salió a redes no puede diferir de lo mostrado. Escrituras operativas siguen pasando.
    verificar_publicacion_inmutable(db.obtener_pieza_fila(pieza_id), campos)
    return db.actualizar_pieza_fila(
        pieza_id, campos, version_esperada=version_esperada
    )


def borrar_pieza_fila(pieza_id: str) -> bool:
    return db.borrar_pieza_fila(pieza_id)


def ajustar_plataformas_por_formato(
    publicacion_id: str, formato: str
) -> dict[str, list[str]]:
    """Reconcilia las filas por plataforma de una pieza con su `formato` (FLIP foto/video/carrusel).

    El FORMATO de una pieza decide a qué redes va (`redes.redes_de_formato`: foto=3, video=5,
    carrusel=2). Cuando el formato cambia hay que AÑADIR las filas que falten y RETIRAR las
    redes extra SIN PERDER trabajo. Reglas (contrato F-video, extendido a carrusel):

      - hacia `video`: crea las filas que falten de las 5 redes (youtube/tiktok) con
        `falta_copy=1`. En TODAS las filas, si no hay `video`, marca `falta_video=1` (el asset es
        obligatorio); `falta_imagen=0` (la imagen pasa a opcional: portada/thumbnail).
      - hacia un formato de IMAGEN (`foto`/`carrusel`): deja las redes de ese formato. Las extra
        se ELIMINAN solo si están VACÍAS (sin copy ni video); si tienen contenido, se CONSERVAN
        (no perder trabajo) y se reportan en `conservadas`. En las filas que quedan,
        `falta_video=0` (N/A) y, si no hay imagen real, `falta_imagen=1`.

    Además, cambiar de formato cambia la PARTE VISUAL de la pieza, así que en CADA fila restante:
      - se BORRA el asset del formato anterior (hacia `video` borra foto/collage/encuadre/placa;
        hacia imagen borra el vídeo). Los formatos de IMAGEN comparten la portada (foto+placa):
        el flip `foto<->carrusel` la CONSERVA; al salir de `carrusel` se limpian sus slides
        extra (`carrusel`). El COPY no se toca (es independiente del formato).
      - se LIMPIA la `plantilla_diseno_id` (la plantilla foto no aplica a vídeo —que va con
        miniatura— ni al revés); el render la re-deriva por marca/tipo.
      - la pieza vuelve a BORRADOR (`estado=pendiente`, `falta_revision/publicar=1`), salvo lo ya
        `publicado`: pierde el "listo para revisar"/aprobación para que se revise de nuevo.

    Idempotente y PURO de side-effects salvo las escrituras descritas. Devuelve un resumen
    `{creadas, eliminadas, conservadas}` (listas de ids de red) para que la API avise al usuario.
    """
    from . import redes

    formato = redes.normalizar_formato(formato)
    es_video = formato == redes.FORMATO_VIDEO
    es_carrusel = formato == redes.FORMATO_CARRUSEL
    objetivo = set(redes.redes_de_formato(formato))
    existentes = {
        p.get("red", ""): p for p in db.listar_piezas_fila(publicacion_id)
    }

    creadas: list[str] = []
    eliminadas: list[str] = []
    conservadas: list[str] = []

    # 1) AÑADIR las redes del objetivo que aún no existan (orden de `redes.ids`).
    for red in redes.ids():
        if red not in objetivo or red in existentes:
            continue
        db.crear_pieza_fila(
            publicacion_id=publicacion_id,
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
            db.borrar_pieza_fila(plat["id"])
            eliminadas.append(red)

    # 3) Reaplicar el checklist por formato a TODAS las filas que QUEDAN + LIMPIAR lo que el cambio
    #    de formato invalida. Cambiar de formato cambia la PARTE VISUAL de la pieza, así que:
    #      - El ASSET del formato anterior deja de servir: `foto->video` borra la foto y su placa
    #        (el vídeo trae su propio asset + miniatura); `video->foto` borra el vídeo (la foto, si
    #        la hay, se conserva). El COPY (texto) NO se toca: es independiente del formato.
    #      - La PLANTILLA del formato anterior ya no aplica (foto usa plantilla tipo "foto"; el
    #        vídeo va con "miniatura"): se limpia y el render la re-deriva por marca/tipo.
    #      - La pieza vuelve a BORRADOR: pierde "listo para revisar"/aprobación/programación, para
    #        que un humano la revise de nuevo con su nueva parte visual.
    #    Checklist: foto -> falta_video=0 (N/A), falta_imagen=1 si no hay imagen real; video ->
    #    falta_video=1 si no hay asset de vídeo, falta_imagen=0 (opcional: portada/thumbnail).
    for plat in db.listar_piezas_fila(publicacion_id):
        # Lo ya PUBLICADO no se toca (no se le borra el asset ni se le revierte el estado): solo
        # se le reaplica el checklist del formato, como siempre.
        publicada = (plat.get("estado") or "") == "publicado"
        tiene_imagen = bool(
            str(plat.get("imagen") or "").strip()
            or str(plat.get("foto") or "").strip()
            or str(plat.get("imagen_fuente") or "").strip()
        )
        if es_video:
            campos: dict[str, Any] = {
                "falta_video": not bool(str(plat.get("video") or "").strip()),
                "falta_imagen": False,
            }
            if not publicada:
                # imagen -> video: borra la foto (cruda, collage, encuadre), la placa horneada
                # y los slides extra de carrusel (parte visual del formato anterior).
                campos.update(
                    {"foto": "", "fotos": "", "foto_encuadre": "", "imagen": "", "carrusel": ""}
                )
        else:
            campos = {"falta_video": False, "falta_imagen": not tiene_imagen}
            if not publicada:
                # video -> imagen: borra el vídeo; la foto (si la hay) se conserva.
                campos["video"] = ""
                # Los slides extra son EXCLUSIVOS del formato carrusel: al salir de él se
                # limpian; el flip foto<->carrusel conserva la portada (foto+placa).
                if not es_carrusel:
                    campos["carrusel"] = ""
        if not publicada:
            # La plantilla del formato anterior ya no aplica: se limpia (el render la re-deriva).
            campos["plantilla_diseno_id"] = ""
            # Volver a BORRADOR: el cambio de formato invalida la revisión/aprobación/programación.
            campos["estado"] = "borrador"
            campos["falta_revision"] = True
            campos["falta_publicar"] = True
        db.actualizar_pieza_fila(plat["id"], campos)

    return {"creadas": creadas, "eliminadas": eliminadas, "conservadas": conservadas}


def adjuntar_video_a_pieza(publicacion_id: str, clave_media: str) -> list[str]:
    """Adjunta un mp4 renderizado a las plataformas de VIDEO de una pieza (cableado VIDEO).

    El asset de video vive POR PLATAFORMA (`pieza.video` + flag `falta_video`).
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
    for plat in db.listar_piezas_fila(publicacion_id):
        if plat.get("red", "") not in redes_video:
            continue
        db.actualizar_pieza_fila(
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
    hashtags: str = "",
    activo: bool = True,
    ttl_dias: int = 0,
    es_evergreen: bool = False,
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
        hashtags=hashtags,
        activo=activo,
        ttl_dias=ttl_dias,
        es_evergreen=es_evergreen,
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


def asignar_etiqueta(publicacion_id: str, etiqueta_id: str) -> None:
    db.asignar_etiqueta(publicacion_id, etiqueta_id)


def quitar_etiqueta(publicacion_id: str, etiqueta_id: str) -> bool:
    return db.quitar_etiqueta(publicacion_id, etiqueta_id)


def etiquetas_por_contenido() -> dict[str, list[str]]:
    return db.etiquetas_por_contenido()


def ids_contenido_con_etiqueta(etiqueta_id: str) -> set[str]:
    return db.ids_contenido_con_etiqueta(etiqueta_id)


# --------------------------------------------------------------------------- #
# Taller EVERGREEN / brainstorming: ideas evergreen. La fachada delega 1:1 en db; #
# la validacion vive en `api/evergreen`.                                          #
# --------------------------------------------------------------------------- #


def crear_evergreen_idea(
    *,
    marca: str = "",
    titulo: str = "",
    descripcion: str = "",
    estado: str = "propuesta",
    origen: str = "ia",
    generacion_id: str = "",
    publicacion_id: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea una idea de contenido evergreen. Delegado en `db.py`."""
    return db.crear_evergreen_idea(
        marca=marca,
        titulo=titulo,
        descripcion=descripcion,
        estado=estado,
        origen=origen,
        generacion_id=generacion_id,
        publicacion_id=publicacion_id,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_evergreen_ideas(
    *, marca: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    """Lista ideas evergreen (recientes primero). Delegado en `db.py`."""
    return db.listar_evergreen_ideas(marca=marca, estado=estado)


def obtener_evergreen_idea(idea_id: str) -> dict[str, Any] | None:
    return db.obtener_evergreen_idea(idea_id)


def actualizar_evergreen_idea(
    idea_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_evergreen_idea(idea_id, campos)


def borrar_evergreen_idea(idea_id: str) -> bool:
    return db.borrar_evergreen_idea(idea_id)



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


def reparar_lotes_parseando_sueltos(antes_de: str) -> int:
    return db.reparar_lotes_parseando_sueltos(antes_de)


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


def marcar_insumo_item_usado(item_id: str, *, publicacion_id: str) -> dict[str, Any] | None:
    return db.marcar_insumo_item_usado(item_id, publicacion_id=publicacion_id)


def borrar_insumo_item(item_id: str) -> bool:
    return db.borrar_insumo_item(item_id)


def listar_lotes(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_lotes(fecha=fecha, cajon=cajon)


def dias_con_insumos() -> list[dict[str, Any]]:
    return db.dias_con_insumos()

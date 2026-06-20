"""Repositorio — dominio editor. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Texto de MEDIOS interna (OPERACIONAL: Postgres via db.py)                #
# --------------------------------------------------------------------------- #
# Catalogo editorial de medios APROBADOS y etiquetables. El binario lo guarda/sirve
# `media.py`; aqui solo el catalogo reutilizable. La fachada delega 1:1 en `db.py`.


def crear_media_catalogo(
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
    return db.crear_media_catalogo(
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


def listar_media_catalogo(
    *,
    marca: str | None = None,
    tipo: str | None = None,
    solo_aprobados: bool = False,
    incluir_globales: bool = False,
) -> list[dict[str, Any]]:
    return db.listar_media_catalogo(
        marca=marca, tipo=tipo, solo_aprobados=solo_aprobados,
        incluir_globales=incluir_globales,
    )


def obtener_media_catalogo(media_id: str) -> dict[str, Any] | None:
    return db.obtener_media_catalogo(media_id)


def existe_media_objeto(objeto: str) -> bool:
    return db.existe_media_objeto(objeto)


def actualizar_media_catalogo(
    media_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_media_catalogo(media_id, campos)


def borrar_media_catalogo(media_id: str) -> dict[str, Any] | None:
    return db.borrar_media_catalogo(media_id)



# --------------------------------------------------------------------------- #
# Activos de marca (editor profesional)                                          #
# --------------------------------------------------------------------------- #


def crear_marca_activo(
    *,
    marca: str,
    tipo: str = "arte",
    nombre: str = "",
    objeto: str = "",
    metadatos: str = "{}",
    lineas: str = "[]",
    aprobado: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_marca_activo(
        marca=marca,
        tipo=tipo,
        nombre=nombre,
        objeto=objeto,
        metadatos=metadatos,
        lineas=lineas,
        aprobado=aprobado,
        autor=autor,
        id=id,
        creado=creado,
        actualizado=actualizado,
    )


def listar_marca_activos(
    *, marca: str | None = None, tipo: str | None = None, solo_aprobados: bool = False
) -> list[dict[str, Any]]:
    return db.listar_marca_activos(marca=marca, tipo=tipo, solo_aprobados=solo_aprobados)


def obtener_marca_activo(activo_id: str) -> dict[str, Any] | None:
    return db.obtener_marca_activo(activo_id)


def actualizar_marca_activo(activo_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_marca_activo(activo_id, campos)


def borrar_marca_activo(activo_id: str) -> dict[str, Any] | None:
    return db.borrar_marca_activo(activo_id)



# --------------------------------------------------------------------------- #
# Plantillas de diseño (editor profesional)                                      #
# --------------------------------------------------------------------------- #


def crear_plantilla_diseno(
    *,
    marca: str,
    nombre: str = "",
    categoria: str = "general",
    tipo: str = "foto",
    documento: str = "{}",
    miniatura: str = "",
    foto_muestra: str = "",
    titular_muestra: str = "",
    etiqueta_muestra: str = "",
    lineas: str = "[]",
    activo: bool = True,
    rotar: bool = False,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_plantilla_diseno(
        marca=marca,
        nombre=nombre,
        categoria=categoria,
        tipo=tipo,
        documento=documento,
        miniatura=miniatura,
        foto_muestra=foto_muestra,
        titular_muestra=titular_muestra,
        etiqueta_muestra=etiqueta_muestra,
        lineas=lineas,
        activo=activo,
        rotar=rotar,
        autor=autor,
        id=id,
        creado=creado,
        actualizado=actualizado,
    )


def listar_plantillas_diseno(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    tipo: str | None = None,
    solo_activas: bool = False,
) -> list[dict[str, Any]]:
    return db.listar_plantillas_diseno(
        marca=marca, categoria=categoria, tipo=tipo, solo_activas=solo_activas
    )


def obtener_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    return db.obtener_plantilla_diseno(plantilla_id)


def actualizar_plantilla_diseno(plantilla_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_plantilla_diseno(plantilla_id, campos)


def borrar_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    return db.borrar_plantilla_diseno(plantilla_id)


def reordenar_plantillas_diseno(ids: list[str]) -> int:
    return db.reordenar_plantillas_diseno(ids)


# --------------------------------------------------------------------------- #
# Etiquetas de plantilla (catálogo de categorías editable, por marca)         #
# --------------------------------------------------------------------------- #


def listar_etiquetas_plantilla(*, marca: str | None = None) -> list[dict[str, Any]]:
    return db.listar_etiquetas_plantilla(marca=marca)


def upsert_etiqueta_plantilla(*, marca: str, slug: str, etiqueta: str) -> dict[str, Any]:
    return db.upsert_etiqueta_plantilla(marca=marca, slug=slug, etiqueta=etiqueta)


def borrar_etiqueta_plantilla(*, marca: str, slug: str) -> bool:
    return db.borrar_etiqueta_plantilla(marca=marca, slug=slug)



# --------------------------------------------------------------------------- #
# Motor de video: composiciones + subtitulos (Ola VIDEO)                        #
# --------------------------------------------------------------------------- #


def crear_video_composicion(
    *,
    marca: str,
    documento: str = "{}",
    publicacion_id: str = "",
    titulo: str = "",
    estado: str = "borrador",
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_video_composicion(
        marca=marca,
        documento=documento,
        publicacion_id=publicacion_id,
        titulo=titulo,
        estado=estado,
        id=id,
        creado=creado,
        actualizado=actualizado,
    )


def listar_video_composiciones(
    *, marca: str | None = None, publicacion_id: str | None = None
) -> list[dict[str, Any]]:
    return db.listar_video_composiciones(marca=marca, publicacion_id=publicacion_id)


def obtener_video_composicion(composicion_id: str) -> dict[str, Any] | None:
    return db.obtener_video_composicion(composicion_id)


def actualizar_video_composicion(
    composicion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_video_composicion(composicion_id, campos)


def borrar_video_composicion(composicion_id: str) -> bool:
    return db.borrar_video_composicion(composicion_id)


def crear_video_subtitulo(
    *, composicion_id: str, idioma: str = "es-MX", estado: str = "pendiente",
    segmentos: str = "", ass: str = "", transcrito_en: str = "", id: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_video_subtitulo(
        composicion_id=composicion_id, idioma=idioma, estado=estado,
        segmentos=segmentos, ass=ass, transcrito_en=transcrito_en, id=id,
        actualizado=actualizado,
    )


def listar_video_subtitulos(
    *, composicion_id: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    return db.listar_video_subtitulos(composicion_id=composicion_id, estado=estado)


def obtener_video_subtitulo(subtitulo_id: str) -> dict[str, Any] | None:
    return db.obtener_video_subtitulo(subtitulo_id)


def actualizar_video_subtitulo(
    subtitulo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_video_subtitulo(subtitulo_id, campos)


# --------------------------------------------------------------------------- #
# Gestor de audio: transcripciones (audio→texto)                                #
# --------------------------------------------------------------------------- #


def crear_audio_transcripcion(
    *,
    marca: str,
    nombre: str = "",
    media_id: str = "",
    idioma: str = "es-MX",
    estado: str = "pendiente",
    duracion_ms: int = 0,
    segmentos: str = "",
    texto: str = "",
    resumen: str = "",
    error: str = "",
    tratamientos: str = "",
    autor_id: str = "",
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_audio_transcripcion(
        marca=marca, nombre=nombre, media_id=media_id, idioma=idioma, estado=estado,
        duracion_ms=duracion_ms, segmentos=segmentos, texto=texto, resumen=resumen,
        error=error, tratamientos=tratamientos, autor_id=autor_id,
        id=id, creado=creado, actualizado=actualizado,
    )


def listar_audio_transcripciones(
    *, marca: str | None = None, estado: str | None = None, visible_para: str | None = None
) -> list[dict[str, Any]]:
    return db.listar_audio_transcripciones(marca=marca, estado=estado, visible_para=visible_para)


def media_ids_audio_transcripciones() -> list[str]:
    return db.media_ids_audio_transcripciones()


def obtener_audio_transcripcion(transcripcion_id: str) -> dict[str, Any] | None:
    return db.obtener_audio_transcripcion(transcripcion_id)


def actualizar_audio_transcripcion(
    transcripcion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_audio_transcripcion(transcripcion_id, campos)


def borrar_audio_transcripcion(transcripcion_id: str) -> bool:
    return db.borrar_audio_transcripcion(transcripcion_id)


def crear_audio_artefacto(
    *, transcripcion_id: str, tipo: str, titulo: str = "", contenido: str = "",
    formato: str = "txt", estado: str = "listo", gen_id: str = "", error: str = "",
    origen_id: str = "", origen_version: str = "",
    id: str = "", creado: str = "", actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_audio_artefacto(
        transcripcion_id=transcripcion_id, tipo=tipo, titulo=titulo, contenido=contenido,
        formato=formato, estado=estado, gen_id=gen_id, error=error,
        origen_id=origen_id, origen_version=origen_version,
        id=id, creado=creado, actualizado=actualizado,
    )


def listar_audio_artefactos(transcripcion_id: str) -> list[dict[str, Any]]:
    return db.listar_audio_artefactos(transcripcion_id)


def obtener_audio_artefacto(artefacto_id: str) -> dict[str, Any] | None:
    return db.obtener_audio_artefacto(artefacto_id)


def actualizar_audio_artefacto(artefacto_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_audio_artefacto(artefacto_id, campos)


def borrar_audio_artefacto(artefacto_id: str) -> bool:
    return db.borrar_audio_artefacto(artefacto_id)


# --------------------------------------------------------------------------- #
# Bloques (almacén de capas reutilizables)                                       #
# --------------------------------------------------------------------------- #


def crear_bloque(
    *,
    marca: str = "",
    nombre: str = "",
    capas: str = "[]",
    lineas: str = "[]",
    miniatura: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    return db.crear_bloque(
        marca=marca,
        nombre=nombre,
        capas=capas,
        lineas=lineas,
        miniatura=miniatura,
        autor=autor,
        id=id,
        creado=creado,
        actualizado=actualizado,
    )


def listar_bloques(*, marca: str | None = None) -> list[dict[str, Any]]:
    return db.listar_bloques(marca=marca)


def obtener_bloque(bloque_id: str) -> dict[str, Any] | None:
    return db.obtener_bloque(bloque_id)


def actualizar_bloque(bloque_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_bloque(bloque_id, campos)


def borrar_bloque(bloque_id: str) -> dict[str, Any] | None:
    return db.borrar_bloque(bloque_id)



# --------------------------------------------------------------------------- #
# Versiones de documento (historial del editor por pieza)                        #
# --------------------------------------------------------------------------- #


def crear_documento_version(
    *,
    publicacion_id: str,
    pieza_id: str,
    documento: str,
    render_objeto: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
) -> dict[str, Any]:
    return db.crear_documento_version(
        publicacion_id=publicacion_id,
        pieza_id=pieza_id,
        documento=documento,
        render_objeto=render_objeto,
        autor=autor,
        id=id,
        creado=creado,
    )


def listar_documento_versiones(publicacion_id: str, pieza_id: str) -> list[dict[str, Any]]:
    return db.listar_documento_versiones(publicacion_id, pieza_id)


def ultima_documento_version(publicacion_id: str, pieza_id: str) -> dict[str, Any] | None:
    return db.ultima_documento_version(publicacion_id, pieza_id)

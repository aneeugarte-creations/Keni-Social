"""Persistencia — dominio piezas. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from collections.abc import Sequence

from ._db_comun import (
    PRIORIDAD_EVENTO_DEFECTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPO_CONTENIDO_DEFECTO,
    Any,
    _conectar,
    ahora_iso,
    iso_o_vacio,
)
from .db_publicacion import (
    _fila_publicacion_nueva,
    _insertar_publicacion,
    _insertar_pieza,
    obtener_pieza_fila,
)
from .db_rota import (
    crear_evento_rota,
    obtener_evento_rota,
)

# --------------------------------------------------------------------------- #
# Piezas sobre el modelo unificado (FUSIÓN, paso 3)                       #
# --------------------------------------------------------------------------- #
# Una PIEZA = una fila `pieza` con `es_publicacion=1` unida a su
# `contenido` padre (1:1). Estas funciones conservan EXACTAMENTE la firma y la forma del
# dict que consumen `api/piezas`, `api/aprobacion`, `programador` (Metricool),
# `dominio/piezas` y el frontend de Piezas, de modo que todos van por la fachada `repos`
# sin cambios. El estado de la pieza usa el vocabulario único canónico
# (borrador→en_revision→programado→publicado).

# El estado de PIEZA y el de la fila por plataforma usan el MISMO vocabulario canónico
# (borrador/en_revision/programado/publicado), sin traducción entre ellos: la fila guarda
# el estado tal cual.

# Columnas de la fila por plataforma que mapean campos editables de una pieza.
# (El `contenido` de la pieza es el `copy` de la plataforma; ver `_campos_pub_a_plat`.)
_SELECT_PUBLICACION = (
    "SELECT cp.id AS pid, cp.red AS red, cp.estado AS pestado, cp.copy AS copy, "
    "cp.copy_in AS copy_in, "
    "cp.imagen AS imagen, cp.imagen_fuente AS imagen_fuente, cp.foto AS foto, "
    "cp.imagen_origen AS imagen_origen, cp.imagen_proveedor AS imagen_proveedor, "
    "cp.imagen_autor AS imagen_autor, cp.imagen_licencia AS imagen_licencia, "
    "cp.imagen_credito_url AS imagen_credito_url, cp.imagen_autorizada AS imagen_autorizada, "
    "cp.imagen_clave AS imagen_clave, "
    "cp.video AS video, cp.falta_video AS falta_video, "
    "cp.revision AS revision, cp.revisor_id AS revisor_id, "
    "cp.revisor_nombre AS revisor_nombre, cp.revisado_en AS revisado_en, "
    "cp.enviado_a_revision_en AS enviado_a_revision_en, cp.fecha_programada AS fecha_programada, "
    "cp.preparado_en AS preparado_en, cp.id_post_metricool AS id_post_metricool, "
    "cp.falta_copy AS falta_copy, cp.falta_imagen AS falta_imagen, "
    "cp.falta_revision AS falta_revision, cp.falta_publicar AS falta_publicar, "
    "cp.evergreen AS evergreen, cp.copy_in_exento AS copy_in_exento, "
    "cp.placa_oculta AS placa_oculta, cp.plantilla_diseno_id AS plantilla_diseno_id, "
    "cp.foto_encuadre AS foto_encuadre, cp.fotos AS fotos, cp.carrusel AS carrusel, "
    "cp.hashtags_sugeridos AS hashtags_sugeridos, "
    "cp.verificar_auto_hash AS verificar_auto_hash, cp.actualizado AS pactualizado, "
    "c.id AS cid, c.titulo AS titulo, c.marca AS marca, c.autor_id AS autor_id, "
    "c.autor_nombre AS autor_nombre, "
    "c.responsable_id AS responsable_id, c.responsable_nombre AS responsable_nombre, "
    "c.origen AS origen, c.creado AS ccreado, "
    "c.fecha_fuente AS fecha_fuente, "
    "c.url_fuente AS url_fuente, c.fuente_nombre AS fuente_nombre, "
    "c.tipo_contenido AS tipo_contenido, c.categoria AS categoria, "
    "c.formato AS formato, c.espejo AS espejo, "
    # Hashtags de la LÍNEA editorial del contenido (etiqueta activa clase 'vertical'): columna
    # calculada en el mismo SELECT (no un query por pieza) para que el gate `falta_hashtags` exija
    # también el hashtag de la sección sin N+1. "" si el contenido no tiene línea o esta no lo fija.
    "(SELECT e.hashtags FROM publicacion_etiquetas pe "
    "JOIN etiquetas e ON pe.etiqueta_id = e.id "
    "WHERE pe.publicacion_id = c.id AND e.clase = 'vertical' AND e.activo = 1 "
    "ORDER BY e.id LIMIT 1) AS linea_hashtags "
    "FROM pieza cp JOIN publicacion c ON cp.publicacion_id = c.id "
    # Toda fila por plataforma de un `contenido` (no de una `tarea`) ES una pieza:
    # el muro `es_publicacion` no se usa. La columna persiste por compatibilidad pero
    # no filtra; `clase` excluye las tareas.
    "WHERE c.clase = 'contenido'"
)


def _fila_a_publicacion(f: Any) -> dict[str, Any]:
    """Reconstruye el dict público de una pieza desde la fila unida (plat + padre)."""
    return {
        "id": f["pid"],
        "publicacion_id": f["cid"] or "",
        "titulo": f["titulo"] or "",
        "marca": f["marca"] or "",
        "red": f["red"] or "",
        "contenido": f["copy"] or "",
        "copy_in": f["copy_in"] or "",
        "estado": f["pestado"] or "borrador",
        "revision": f["revision"] or "",
        "autor_id": f["autor_id"] or "",
        "autor_nombre": f["autor_nombre"] or "",
        # REPARTO ("la lista"): quién tiene COGIDA la pieza. Vive en el `contenido` padre
        # (el reparto es del tema completo, no de cada red); "" = libre, nadie la cogió.
        "responsable_id": f["responsable_id"] or "",
        "responsable_nombre": f["responsable_nombre"] or "",
        "enviado_a_revision_en": f["enviado_a_revision_en"] or "",
        "revisor_id": f["revisor_id"] or "",
        "revisor_nombre": f["revisor_nombre"] or "",
        "revisado_en": f["revisado_en"] or "",
        "preparado_en": f["preparado_en"] or "",
        "id_post_metricool": f["id_post_metricool"] or "",
        # Origen de la imagen: `tipo_contenido` ('ia'|'galeria'|'fuente') y, si es 'fuente',
        # la URL original del artículo en `imagen_fuente` (el editor ofrece "usar original").
        "tipo_contenido": f["tipo_contenido"] or "ia",
        # FORMATO de la pieza (foto|video): heredado del `contenido` padre. Decide a qué redes
        # va (`redes.redes_de_formato`). BD vieja / sin valor -> 'foto' (el flujo automático).
        "formato": f["formato"] or "foto",
        # ESPEJO entre redes (propiedad del padre, default ON): editar el contenido de esta
        # pieza propaga los mismos campos a sus redes hermanas (api/piezas lo aplica).
        "espejo": bool(f["espejo"]) if f["espejo"] is not None else True,
        "imagen_fuente": f["imagen_fuente"] or "",
        # Media id de la FOTO CRUDA de fondo (separada de `imagen`, la placa ya compuesta);
        # permite al editor inline recomponer la placa en vivo al reabrir la pieza.
        "foto": f["foto"] or "",
        # PROCEDENCIA + AUTORIZACIÓN de la imagen adjunta (fotos de stock como ayuda visual).
        # `imagen_origen='stock'` => foto externa con watermark "SIN LICENCIA" que NO se publica
        # hasta `imagen_autorizada=True`; el resto es crédito/licencia/atribución para el badge.
        "imagen_origen": f["imagen_origen"] or "",
        "imagen_proveedor": f["imagen_proveedor"] or "",
        "imagen_autor": f["imagen_autor"] or "",
        "imagen_licencia": f["imagen_licencia"] or "",
        "imagen_credito_url": f["imagen_credito_url"] or "",
        "imagen_autorizada": bool(f["imagen_autorizada"]),
        # Keyword de búsqueda de foto (sujeto visual) que propone la etapa Sugerir hashtags.
        "imagen_clave": f["imagen_clave"] or "",
        # Checklist de producción por red (el editor lo expone como checks marcables).
        "falta_copy": bool(f["falta_copy"]),
        "falta_imagen": bool(f["falta_imagen"]),
        "falta_revision": bool(f["falta_revision"]),
        "falta_publicar": bool(f["falta_publicar"]),
        # `ccreado` = `contenido.creado`, ahora timestamptz (migracion 0033): se re-emite al
        # canon ISO. `pactualizado` = `pieza.actualizado`, SIGUE siendo TEXT.
        "fecha_creacion": iso_o_vacio(f["ccreado"]),
        "fecha_actualizacion": f["pactualizado"] or "",
        "fecha_programada": f["fecha_programada"] or "",
        # Fecha de la FUENTE de origen (pipeline): pubDate normalizado a ISO UTC; "" si la
        # pieza no nació de una fuente con fecha. La UI muestra "Fuente del …".
        "fecha_fuente": f["fecha_fuente"] or "",
        # PROCEDENCIA de la nota original: URL canónica + nombre legible del medio (copiado
        # en la promoción CI). La serialización pública deriva de aquí `fuente_original`.
        "url_fuente": f["url_fuente"] or "",
        "fuente_nombre": f["fuente_nombre"] or "",
        "origen": f["origen"] or "",
        # Categoría del PLAN (p.ej. 'breaking'): la usa el feed para avisar de "última hora"
        # (rayo rojo) — esa pieza, al aprobarla, se programa de inmediato sin esperar franja.
        "categoria": f["categoria"] or "",
        "imagen": f["imagen"] or "",
        # Asset de VIDEO (Ola VIDEO): clave del media (`videos/<sha256>.<ext>`) y su checklist,
        # espejo de `imagen`/`falta_imagen`. Lo usa el programador para publicar `TipoMedia.video`.
        "video": f["video"] or "",
        "falta_video": bool(f["falta_video"]),
        "evergreen": bool(f["evergreen"]),
        # Auto-avance: exencion de copy-in + hash del copy con verificación auto lanzada.
        "copy_in_exento": bool(f["copy_in_exento"]),
        # "Quitar plantilla": publicar solo la foto, sin la placa de marca encima.
        "placa_oculta": bool(f["placa_oculta"]),
        # Plantilla del estudio (PlantillaDiseno) que la pieza usa para componer. "" = ninguna.
        "plantilla_diseno_id": f["plantilla_diseno_id"] or "",
        # Reencuadre manual de la foto (JSON `{"foco":[x,y],"zoom":z}`; "" = sin reencuadre).
        "foto_encuadre": f["foto_encuadre"] or "",
        # COLLAGE: JSON array `[{objeto,foco,zoom}, …]`, una por hueco. "" = sin collage (hueco
        # único derivado de `foto`/`foto_encuadre`).
        "fotos": f["fotos"] or "",
        # CARRUSEL: slides EXTRA en crudo (JSON `[{tipo,objeto}, …]`, orden de publicación).
        # La portada del carrusel es la imagen compuesta de siempre (foto + placa).
        "carrusel": f["carrusel"] or "",
        # Sugerencia de hashtags (etapa `sugerir_hashtags`): JSON array de strings CON '#'.
        # '[]' por defecto; la etapa la rellena tras Redactar y `pieza_a_dict` la parsea a lista.
        "hashtags_sugeridos": f["hashtags_sugeridos"] or "[]",
        "verificar_auto_hash": f["verificar_auto_hash"] or "",
        # Hashtags (CSV, sin '#') de la LÍNEA editorial del contenido: el gate `falta_hashtags`
        # los exige en el caption (no basta con tener hashtags cualesquiera). "" si no hay línea.
        "linea_hashtags": f["linea_hashtags"] or "",
    }


def crear_pieza(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    copy_in: str = "",
    estado: str = "borrador",
    revision: str = "",
    fecha_programada: str = "",
    origen: str = "",
    imagen: str = "",
    imagen_fuente: str = "",
    foto: str = "",
    # Default "" (no TIPO_CONTENIDO_DEFECTO) para que la firma sea IDÉNTICA a la de
    # `repos.crear_pieza` (test de paridad); el valor real se coalesce abajo.
    tipo_contenido: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
    id: str = "",
    fecha_creacion: str = "",
) -> dict[str, Any]:
    """Crea una pieza (padre `contenido` + fila `pieza` es_publicacion=1).

    ATOMICA: padre y fila por plataforma se insertan en UNA transaccion (antes eran dos:
    un fallo entre ambas dejaba un `contenido` suelto sin fila por plataforma).

    Acepta `id`/`fecha_creacion` opcionales (preservaban identidad al migrar desde el YAML
    legado, hoy retirado). El `estado` editorial se traduce al de
    plataforma. `imagen_fuente` (URL original, p.ej. de un RSS de marca propia) +
    `tipo_contenido='fuente'` nacen juntos: hay imagen (la del artículo), así que la pieza
    no queda con `falta_imagen`. `foto` (foto cruda ya descargada, p.ej. la og:image original):
    foto real → cuenta como imagen y la placa se compone sobre ella; la pieza nace lista.
    """
    con = _conectar()
    try:
        padre, plat = _insertar_publicacion_con_pieza(
            con,
            marca=marca,
            red=red,
            titulo=titulo,
            contenido=contenido,
            copy_in=copy_in,
            estado=estado,
            revision=revision,
            fecha_programada=fecha_programada,
            origen=origen,
            imagen=imagen,
            imagen_fuente=imagen_fuente,
            foto=foto,
            tipo_contenido=tipo_contenido,
            evergreen=evergreen,
            autor=autor,
            id=id,
            fecha_creacion=fecha_creacion,
        )
        con.commit()
    finally:
        con.close()
    return obtener_pieza(plat["id"]) or _publicacion_de_filas(padre, plat)


def _insertar_publicacion_con_pieza(
    con: Any, *, marca: str, red: str, **campos: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Inserta padre + fila por plataforma sobre `con` (SIN commit). Devuelve `(padre, plat)`.

    Nucleo compartido por `crear_pieza` (transaccion propia) y `crear_publicaciones`
    (lote todo-o-nada: N piezas en UNA transaccion del llamante). Mismos kwargs que
    `crear_pieza` (menos los posicionales `marca`/`red`).
    """
    evergreen = bool(campos.get("evergreen"))
    fecha_creacion = campos.get("fecha_creacion") or ""
    imagen_fuente = campos.get("imagen_fuente") or ""
    foto = campos.get("foto") or ""
    padre = _fila_publicacion_nueva(
        clase="contenido",
        flujo="evergreen" if evergreen else "",
        # Reciclaje = línea 'evergreen' del plan (cuenta como generado de esa línea y usa
        # sus horarios). Una publicación normal no trae línea ('' = genéricas).
        categoria="evergreen" if evergreen else "",
        titulo=campos.get("titulo") or "",
        marca=marca,
        tipo_contenido=campos.get("tipo_contenido") or TIPO_CONTENIDO_DEFECTO,
        autor=campos.get("autor"),
        origen=campos.get("origen") or "",
        creado=fecha_creacion,
        actualizado=fecha_creacion,
    )
    _insertar_publicacion(con, padre)
    plat = _insertar_pieza(
        con,
        id=campos.get("id") or "",
        publicacion_id=padre["id"],
        red=red,
        # Marca denormalizada explicita: la del padre recien insertado (evita un lookup extra).
        marca=padre["marca"],
        estado=campos.get("estado") or "borrador",
        copy=campos.get("contenido") or "",
        copy_in=campos.get("copy_in") or "",
        imagen=campos.get("imagen") or "",
        imagen_fuente=imagen_fuente,
        foto=foto,
        # Solo la foto real (og:image descargada a media) cuenta como imagen y limpia el flag;
        # un `imagen_fuente` a secas es la URL del artículo (referencia), no la foto de la pieza
        # —y si la descarga la rechazó por basura/diminuta, `foto` queda "" y la pieza SÍ falta imagen.
        falta_imagen=False if foto else None,
        revision=campos.get("revision") or "",
        fecha_programada=campos.get("fecha_programada") or "",
        evergreen=evergreen,
        es_publicacion=True,
        creado=fecha_creacion,
        actualizado=fecha_creacion,
    )
    return padre, plat


def _publicacion_de_filas(
    padre: dict[str, Any], plat: dict[str, Any]
) -> dict[str, Any]:
    """Construye el dict publico de una pieza desde las filas padre+plataforma en mano.

    Equivale a `_fila_a_publicacion` sobre la fila unida, sin re-leer la base: lo usan los
    caminos que acaban de INSERTAR ambas filas (creacion y lote) y ya tienen los datos.
    """
    return _fila_a_publicacion(
        {
            "pid": plat["id"], "red": plat["red"], "pestado": plat["estado"],
            "copy": plat["copy"], "copy_in": plat["copy_in"], "imagen": plat["imagen"],
            "imagen_fuente": plat["imagen_fuente"], "foto": plat["foto"],
            # PROCEDENCIA/AUTORIZACIÓN de imagen (fotos de stock): la fila de lote no las trae
            # (pieza recién creada sin foto de stock) -> `.get` => None, que `_fila_a_publicacion`
            # resuelve a "" / False. Sin estas claves el camino del LOTE caía con KeyError.
            "imagen_origen": plat.get("imagen_origen"),
            "imagen_proveedor": plat.get("imagen_proveedor"),
            "imagen_autor": plat.get("imagen_autor"),
            "imagen_licencia": plat.get("imagen_licencia"),
            "imagen_credito_url": plat.get("imagen_credito_url"),
            "imagen_autorizada": plat.get("imagen_autorizada"),
            # Keyword de búsqueda de foto (sujeto visual) que propone la etapa Sugerir hashtags;
            # nace "" en la fila de lote. Sin esta clave el camino del LOTE caía con KeyError.
            "imagen_clave": plat.get("imagen_clave"),
            "video": plat["video"], "falta_video": plat["falta_video"],
            "revision": plat["revision"], "revisor_id": plat["revisor_id"],
            "revisor_nombre": plat["revisor_nombre"], "revisado_en": plat["revisado_en"],
            "enviado_a_revision_en": plat["enviado_a_revision_en"],
            "fecha_programada": plat["fecha_programada"],
            "preparado_en": plat["preparado_en"],
            "id_post_metricool": plat["id_post_metricool"],
            "falta_copy": plat["falta_copy"], "falta_imagen": plat["falta_imagen"],
            "falta_revision": plat["falta_revision"],
            "falta_publicar": plat["falta_publicar"], "evergreen": plat["evergreen"],
            "copy_in_exento": plat["copy_in_exento"],
            "placa_oculta": plat["placa_oculta"],
            "plantilla_diseno_id": plat["plantilla_diseno_id"],
            "foto_encuadre": plat["foto_encuadre"], "fotos": plat["fotos"],
            "carrusel": plat["carrusel"],
            "hashtags_sugeridos": plat.get("hashtags_sugeridos", "[]"),
            "verificar_auto_hash": plat["verificar_auto_hash"], "pactualizado": plat["actualizado"],
            # `linea_hashtags` es una COLUMNA CALCULADA del SELECT (subconsulta a la etiqueta de
            # línea del contenido), no una columna real: una pieza recién creada por lote aún no
            # tiene línea editorial -> "". Sin esta clave el camino del LOTE caía con KeyError.
            "linea_hashtags": "",
            "cid": padre["id"], "titulo": padre["titulo"], "marca": padre["marca"],
            "autor_id": padre["autor_id"], "autor_nombre": padre["autor_nombre"],
            "responsable_id": padre.get("responsable_id"),
            "responsable_nombre": padre.get("responsable_nombre"),
            "origen": padre["origen"], "categoria": padre.get("categoria"),
            "ccreado": padre["creado"],
            "fecha_fuente": padre["fecha_fuente"],
            "url_fuente": padre["url_fuente"], "fuente_nombre": padre["fuente_nombre"],
            "tipo_contenido": padre["tipo_contenido"], "formato": padre["formato"],
            # `espejo` vive en el padre con DEFAULT 1 en BD; la fila recién construida en
            # memoria no lo trae -> None, que `_fila_a_publicacion` resuelve a True (el
            # mismo default). Sin esta clave, el camino del LOTE caía con KeyError.
            "espejo": padre.get("espejo"),
        }
    )


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Crea varias piezas (una por dict de entrada) y las devuelve. TODO-O-NADA.

    Antes iteraba `crear_pieza` (una transaccion POR pieza): un fallo a mitad dejaba
    el lote a medias pese a que el endpoint promete "si una falla, no inserta". Ahora las N
    piezas se insertan en UNA SOLA transaccion: si cualquier insert falla, ninguna
    queda (el `close()` sin commit hace rollback) y la excepcion se propaga al caller.
    """
    con = _conectar()
    creadas: list[dict[str, Any]] = []
    try:
        for d in lista:
            padre, plat = _insertar_publicacion_con_pieza(
                con,
                marca=d.get("marca", "") or "",
                red=d.get("red", "") or "",
                titulo=d.get("titulo", "") or "",
                contenido=d.get("contenido", "") or "",
                copy_in=d.get("copy_in", "") or "",
                estado=d.get("estado", "borrador") or "borrador",
                revision=d.get("revision", "") or "",
                fecha_programada=d.get("fecha_programada", "") or "",
                origen=d.get("origen", "") or "",
                imagen=d.get("imagen", "") or "",
                evergreen=bool(d.get("evergreen")),
                autor=(
                    {"id": d.get("autor_id", ""), "usuario": d.get("autor_nombre", "")}
                    if d.get("autor_id")
                    else None
                ),
            )
            creadas.append(_publicacion_de_filas(padre, plat))
        con.commit()
    finally:
        con.close()
    return creadas


def _filtros_publicacion(
    marca: str | Sequence[str] | None,
    red: str | None,
    estado: str | None,
    evergreen: bool | None,
    linea: str | None = None,
    responsable: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    origen: str | None = None,
    categoria: str | None = None,
    tipo_contenido: str | None = None,
    fuente: str | None = None,
    fase: str | None = None,
    creado_antes: str | None = None,
    excluir_origen: str | None = None,
) -> tuple[str, list[Any]]:
    """Construye la cláusula WHERE adicional (tras `es_publicacion=1`) y sus parámetros.

    `marca` admite UNA marca (str) o VARIAS (secuencia -> `c.marca IN (...)`). El caso
    multi-marca empuja al SQL el foco por marcas preferentes del feed, que antes se
    post-filtraba en memoria y ROMPIA el keyset (página corta + cursor que salta filas).

    `desde`/`hasta` (ISO `YYYY-MM-DD`, ambos opcionales) acotan por `fecha_programada`: el
    CALENDARIO pide solo la ventana visible en vez del conjunto completo (que el cap de 1000
    truncaba en silencio). Una pieza SIN fecha (`''`/NULL) NUNCA cae dentro de un rango: se
    excluye con `fecha_programada != ''` (y los `>=`/`<=` tampoco casan NULL).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        if isinstance(marca, str):
            clausulas.append("c.marca = ?")
            params.append(marca)
        else:
            marcas_lista = sorted({m for m in marca if m})
            if marcas_lista:
                marcadores = ", ".join("?" for _ in marcas_lista)
                clausulas.append(f"c.marca IN ({marcadores})")
                params.extend(marcas_lista)
    if red:
        clausulas.append("cp.red = ?")
        params.append(red)
    # ORIGEN del contenido padre (el clon «Portal» del feed pide `origen='portal'`): el
    # contenido `c` ya está en el JOIN del SELECT, así que se filtra directo (sin denormalizar).
    if origen:
        clausulas.append("c.origen = ?")
        params.append(origen)
    # EXCLUSIÓN por origen: el FEED normal pide `excluir_origen='portal'` para mantenerse
    # independiente del canal Portal (que tiene su propia superficie). Las piezas SIN origen
    # (NULL) NO son del canal, así que se conservan (`c.origen IS NULL OR c.origen != ?`).
    if excluir_origen:
        clausulas.append("(c.origen IS NULL OR c.origen != ?)")
        params.append(excluir_origen)
    # Línea editorial = etiqueta de clase `vertical` asignada al `contenido` padre. Se filtra
    # con un EXISTS sobre la tabla puente (no JOIN, para no duplicar filas si hubiera varias).
    if linea:
        clausulas.append(
            "EXISTS (SELECT 1 FROM publicacion_etiquetas ce "
            "WHERE ce.publicacion_id = c.id AND ce.etiqueta_id = ?)"
        )
        params.append(linea)
    if estado:
        # PSEUDO-ESTADO `pendiente` (NO es un estado real: el vocabulario es borrador/
        # en_revision/programado/publicado): la partición "Pendientes" del feed = TODO lo que aún
        # no salió, esto es, cualquier estado que no sea `publicado` (incluido un estado nulo).
        # Su complementario exacto es `estado=publicado`, así "Pendientes + Publicadas = Todas".
        if estado == "pendiente":
            clausulas.append("(cp.estado IS NULL OR cp.estado != 'publicado')")
        else:
            clausulas.append("cp.estado = ?")
            params.append(estado)
    if evergreen is not None:
        clausulas.append("cp.evergreen = ?")
        params.append(1 if evergreen else 0)
    # REPARTO ("la lista"): el responsable vive en el `contenido` PADRE (el reparto es del
    # tema, no de cada red). `""` = piezas LIBRES (por coger); otro valor = cogidas por ese
    # usuario. El IS NULL cubre filas anteriores a la columna (el claim escribe siempre "").
    if responsable is not None:
        if responsable == "":
            clausulas.append("(c.responsable_id = '' OR c.responsable_id IS NULL)")
        else:
            clausulas.append("c.responsable_id = ?")
            params.append(responsable)
    # RANGO de fecha_programada (calendario): las piezas SIN fecha quedan FUERA del rango.
    if desde or hasta:
        clausulas.append("cp.fecha_programada != ''")
        if desde:
            clausulas.append("cp.fecha_programada >= ?")
            params.append(desde)
        if hasta:
            clausulas.append("cp.fecha_programada <= ?")
            params.append(hasta)
    # FILTROS de limpieza del feed (todos sobre el `contenido` PADRE `c`, ya en el JOIN):
    # categoría del plan, tipo de contenido, medio de origen.
    if categoria:
        clausulas.append("c.categoria = ?")
        params.append(categoria)
    if tipo_contenido:
        clausulas.append("c.tipo_contenido = ?")
        params.append(tipo_contenido)
    if fuente:
        clausulas.append("c.fuente_nombre = ?")
        params.append(fuente)
    # ANTIGÜEDAD: solo lo creado ANTES del corte (ISO UTC que calcula el handler desde el
    # preset >24h/>48h/…). Sobre `c.creado` (creación del tema), mismo eje que el keyset.
    if creado_antes:
        clausulas.append("c.creado <= ?")
        params.append(creado_antes)
    # FASE de producción (limpieza): 'incompleto' = aún en producción (le falta copy/arte/
    # revisión y sigue en borrador) — los candidatos a barrer; 'producido' = listo, sin
    # aprobar (no le falta nada y no salió); 'programado'/'publicado' = ya completados. Se
    # deriva de los flags `falta_*` + `estado` (SQL puro, sin recomputar la etapa del cliente).
    if fase == "incompleto":
        clausulas.append(
            "((cp.estado IS NULL OR cp.estado = 'borrador') "
            "AND (cp.falta_copy = 1 OR cp.falta_imagen = 1 OR cp.falta_revision = 1))"
        )
    elif fase == "producido":
        clausulas.append(
            "(cp.falta_copy = 0 AND cp.falta_imagen = 0 AND cp.falta_revision = 0 "
            "AND (cp.estado IS NULL OR cp.estado IN ('borrador', 'en_revision')))"
        )
    elif fase == "programado":
        clausulas.append("cp.estado = 'programado'")
    elif fase == "publicado":
        clausulas.append("cp.estado = 'publicado'")
    return (" AND " + " AND ".join(clausulas) if clausulas else ""), params


def listar_piezas(
    marca: str | Sequence[str] | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    linea: str | None = None,
    responsable: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    origen: str | None = None,
    categoria: str | None = None,
    tipo_contenido: str | None = None,
    fuente: str | None = None,
    fase: str | None = None,
    creado_antes: str | None = None,
    excluir_origen: str | None = None,
    *,
    limite: int | None = None,
    desplazamiento: int | None = None,
    cursor: tuple[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Piezas (más recientes primero) con filtros y paginación opcionales.

    Orden estable `(c.creado DESC, cp.id DESC)` apto para scroll infinito. Dos modos
    de paginar, mutuamente excluyentes (KEYSET tiene prioridad si se pasan ambos):
      - OFFSET (`limite`/`desplazamiento`): ventana clásica; sirve al calendario/lista que
        ya lo usaban. Sin `limite` se devuelve el conjunto COMPLETO (comportamiento previo).
      - KEYSET (`cursor`): `cursor=(creado, id)` = última clave vista; devuelve solo las
        filas ESTRICTAMENTE posteriores en el orden (más antiguas). Inmune a inserciones
        nuevas al principio (no desplaza páginas), ideal para el feed social.
    """
    extra, params = _filtros_publicacion(
        marca, red, estado, evergreen, linea, responsable, desde, hasta, origen,
        categoria, tipo_contenido, fuente, fase, creado_antes,
        excluir_origen=excluir_origen,
    )
    if cursor is not None:
        # Keyset sobre la tupla (creado, id) en orden DESC: la página siguiente son las filas
        # con (creado, id) ESTRICTAMENTE menor que la última vista. Forma expandida (no
        # row-value) para máxima portabilidad del motor.
        cur_creado, cur_id = cursor
        extra += " AND (c.creado < ? OR (c.creado = ? AND cp.id < ?))"
        params = [*params, cur_creado, cur_creado, cur_id]
    sql = f"{_SELECT_PUBLICACION}{extra} ORDER BY c.creado DESC, cp.id DESC"
    if limite is not None:
        if cursor is not None:
            # Con keyset el offset no aplica (la posición la fija el cursor); solo acotamos el
            # tamaño de página.
            sql += " LIMIT ?"
            params = [*params, limite]
        else:
            sql += " LIMIT ? OFFSET ?"
            params = [*params, limite, desplazamiento or 0]
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_publicacion(f) for f in filas]


def contar_piezas(
    marca: str | Sequence[str] | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    linea: str | None = None,
    responsable: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    origen: str | None = None,
    categoria: str | None = None,
    tipo_contenido: str | None = None,
    fuente: str | None = None,
    fase: str | None = None,
    creado_antes: str | None = None,
    excluir_origen: str | None = None,
) -> int:
    """Total de piezas que casan los filtros (para el `total` de paginación)."""
    extra, params = _filtros_publicacion(
        marca, red, estado, evergreen, linea, responsable, desde, hasta, origen,
        categoria, tipo_contenido, fuente, fase, creado_antes,
        excluir_origen=excluir_origen,
    )
    sql = (
        "SELECT COUNT(*) AS n FROM pieza cp "
        "JOIN publicacion c ON cp.publicacion_id = c.id WHERE c.clase = 'contenido'" + extra
    )
    con = _conectar()
    try:
        fila = con.execute(sql, tuple(params)).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_pieza(pieza_id: str) -> dict[str, Any] | None:
    """Una pieza por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PUBLICACION} AND cp.id = ?", (pieza_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_publicacion(fila) if fila is not None else None


# Campo de pieza -> columna de la fila por plataforma (edición parcial).
_CAMPOS_PUB_A_PLAT: dict[str, str] = {
    "contenido": "copy",
    "copy_in": "copy_in",
    "revision": "revision",
    # Flags de readiness DERIVADAS del contenido (copy/foto): el editor/espejo las recalcula y
    # persiste al editar para que la LISTA del feed (que las lee) no quede stale. Bool->int abajo.
    "falta_copy": "falta_copy",
    "falta_imagen": "falta_imagen",
    "falta_video": "falta_video",
    "fecha_programada": "fecha_programada",
    "imagen": "imagen",
    "foto": "foto",
    "evergreen": "evergreen",
    "placa_oculta": "placa_oculta",
    "plantilla_diseno_id": "plantilla_diseno_id",
    "foto_encuadre": "foto_encuadre",
    "fotos": "fotos",
    "carrusel": "carrusel",
    "hashtags_sugeridos": "hashtags_sugeridos",
    # Keyword de búsqueda de foto: la etapa Sugerir hashtags la escribe gemela en todas las redes.
    "imagen_clave": "imagen_clave",
    "enviado_a_revision_en": "enviado_a_revision_en",
    "revisor_id": "revisor_id",
    "revisor_nombre": "revisor_nombre",
    "revisado_en": "revisado_en",
    "preparado_en": "preparado_en",
    "id_post_metricool": "id_post_metricool",
}


def actualizar_pieza(
    pieza_id: str,
    campos: dict[str, Any],
    *,
    estado_esperado: str | None = None,
) -> dict[str, Any] | None:
    """Edita parcialmente una pieza; None si no existe. Mapea a padre/plataforma.

    ATOMICA: la fila por plataforma y el padre se actualizan en UNA SOLA transaccion
    (antes eran dos: un fallo entre ambas dejaba media edicion aplicada, p. ej. el estado
    movido pero el titulo sin tocar).

    `estado_esperado` (opcional) añade un CAS al UPDATE de la fila por plataforma: solo
    aplica si el `estado` ACTUAL (de pieza) sigue siendo ese; si otro flujo lo movio
    entre el snapshot del caller y esta escritura, NO se toca nada y se devuelve None (el
    caller lo distingue de "no existe" re-leyendo). Cierra el TOCTOU del PUT generico.
    """
    plat = obtener_pieza_fila(pieza_id)
    if plat is None:
        return None

    cambios_plat: dict[str, Any] = {}
    for clave, columna in _CAMPOS_PUB_A_PLAT.items():
        if clave in campos:
            valor = campos[clave]
            if clave in ("evergreen", "placa_oculta", "falta_copy", "falta_imagen", "falta_video"):
                valor = 1 if valor else 0
            cambios_plat[columna] = valor
    if "estado" in campos:
        cambios_plat["estado"] = campos["estado"]

    cambios_padre: dict[str, Any] = {}
    if "titulo" in campos:
        cambios_padre["titulo"] = campos["titulo"]
    if "evergreen" in campos:
        cambios_padre["flujo"] = "evergreen" if campos["evergreen"] else ""
    # ESPEJO entre redes: vive en el padre (es de la idea, no de una red). Se acepta desde
    # cualquier pieza hermana (el editor lo togglea desde la red que tenga abierta).
    if "espejo" in campos:
        cambios_padre["espejo"] = 1 if campos["espejo"] else 0

    ahora = ahora_iso()
    con = _conectar()
    try:
        if cambios_plat:
            asignaciones = [f"{col} = ?" for col in cambios_plat]
            asignaciones.append("actualizado = ?")
            params: list[Any] = [*cambios_plat.values(), ahora, pieza_id]
            sql = (
                f"UPDATE pieza SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
                "WHERE id = ?"
            )
            if estado_esperado is not None:
                # Vocabulario único: el estado de la fila ES el estado de publicación, así
                # que el CAS compara contra el esperado tal cual (1:1).
                sql += " AND estado = ?"
                params.append(estado_esperado)
            cur = con.execute(sql, tuple(params))
            if cur.rowcount == 0:
                # No existe o el CAS no aplico (estado movido): nada que commitear.
                return None
        if cambios_padre:
            asignaciones_p = [f"{col} = ?" for col in cambios_padre]
            asignaciones_p.append("actualizado = ?")
            con.execute(
                f"UPDATE publicacion SET {', '.join(asignaciones_p)} WHERE id = ?",  # noqa: S608 -- allowlist
                (*cambios_padre.values(), ahora, plat["publicacion_id"]),
            )
        con.commit()
    finally:
        con.close()
    return obtener_pieza(pieza_id)


def reclamar_preparacion(pieza_id: str, ts: str) -> bool:
    """Claim ATOMICO de la preparacion de una pieza. True si ESTE llamante la reclamo.

    Estampa `preparado_en = ts` SOLO si aun estaba sin preparar (`'' / NULL`), en un unico
    UPDATE condicional. Devuelve `rowcount > 0`: True si la fila pasó de "sin preparar" a
    "preparada" en esta llamada; False si ya estaba preparada (otro barrido/replica gano la
    carrera) o si la pieza no existe. Evita la doble preparacion/pieza del
    patron leer-`preparado_en`-y-luego-UPDATE cuando hay >1 barrido en paralelo (varias
    replicas). La pieza es la fila `pieza` (su id ES `pieza_id`).
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE pieza SET preparado_en = ? "
            "WHERE id = ? AND (preparado_en = '' OR preparado_en IS NULL)",
            (ts, pieza_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def transicionar_estado_pieza(
    pieza_id: str,
    estado_origen: str,
    estado_destino: str,
    campos_extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Transicion de estado GUARDADA (CAS) de una pieza. None si el origen ya cambió.

    Cierra el TOCTOU de "leer estado en Python -> escribir en una transaccion posterior" del
    flujo de aprobacion (`enviar_a_revision`, `programar`): en lugar de confiar en un snapshot,
    mueve el `estado` en un UNICO UPDATE condicional
        `UPDATE pieza SET estado=? [, extras...] WHERE id=? AND estado=?`
    sobre la fila por plataforma (la pieza ES esa fila; su id ES `pieza_id`). Asi
    dos peticiones simultaneas (doble-click, dos revisores) NO pasan ambas: la primera gana y la
    segunda ve `rowcount == 0` y recibe `None` (el caller lo traduce a 409 "el estado cambió").

    `estado_origen`/`estado_destino` son estados canónicos (`borrador`/`en_revision`/
    `programado`/`publicado`); con el vocabulario único (colapso 2026-06) la fila los guarda
    tal cual (sin traducción). `campos_extra` son campos de PIEZA adicionales a sellar EN
    EL MISMO UPDATE (p.ej. `enviado_a_revision_en`, `fecha_programada`, `revisor_*`,
    `preparado_en`); solo se aceptan los que mapean a columnas de la fila por plataforma via
    `_CAMPOS_PUB_A_PLAT` (el resto se ignora). Igual que `reclamar_preparacion`, una
    `IntegrityError` (p.ej. el indice de slot de parrilla) se PROPAGA al caller para que la
    traduzca (no la traga). Devuelve la pieza actualizada o None (no existe / CAS no aplicó).
    """
    plat_origen = estado_origen
    plat_destino = estado_destino
    asignaciones = ["estado = ?", "actualizado = ?"]
    params: list[Any] = [plat_destino, ahora_iso()]
    for clave, valor in (campos_extra or {}).items():
        columna = _CAMPOS_PUB_A_PLAT.get(clave)
        if columna is None or columna == "estado":
            continue  # solo columnas de la fila por plataforma; el estado va por el CAS
        asignaciones.append(f"{columna} = ?")
        params.append(valor)
    # Concurrencia optimista (ADR 0012): el AVANCE de estado tambien sube `version`, de modo que
    # un editor humano que tenia una `version` previa detecte que el pipeline movio la pieza.
    asignaciones.append("version = version + 1")
    params.extend([pieza_id, plat_origen])
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE pieza SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
            "WHERE id = ? AND estado = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_pieza(pieza_id)


def existe_cadena_aprobacion(pieza_id: str) -> bool:
    """True si la pieza YA tiene cadena de aprobacion (>=1 nivel). Para montarla idempotente."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM pieza_aprobaciones WHERE pieza_id = ? LIMIT 1",
            (pieza_id,),
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def borrar_pieza(pieza_id: str) -> bool:
    """Borra una pieza. True si existía.

    Dos casos (modelo consolidado: pieza = fila `pieza` con
    `es_publicacion=1` colgada de un `contenido`):
      - Pieza SUELTA (su padre 1:1 solo contiene esta fila): se borra el padre, que
        arrastra la fila (no deja un `contenido` suelto y vacio). Es el caso de la
        generacion manual de copy de siempre.
      - Borrador ANIDADO bajo un tema (el padre tiene MAS filas por plataforma, p.ej. un tema
        importado/Radar con su copy auto-generado): se borra SOLO esta fila, conservando el
        tema y sus demas piezas. Evita que borrar un borrador se lleve el tema entero (#nido).

    UNA SOLA transaccion con `SELECT ... FOR UPDATE` del padre: el patron previo
    (listar hermanas -> decidir -> borrar, cada paso en su transaccion) tenia una carrera:
    dos borrados simultaneos de las DOS ultimas hermanas podian decidir ambos "quedan mas"
    y dejar el padre vivo y vacio (o al reves, llevarse el tema con piezas vivas). El lock
    de fila del padre serializa la decision contra otros borrados del mismo tema.
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT publicacion_id FROM pieza WHERE id = ?",
            (pieza_id,),
        ).fetchone()
        if fila is None:
            return False
        publicacion_id = fila["publicacion_id"]
        # Serializa contra otros borrados/ediciones del MISMO tema (lock de fila del padre).
        con.execute("SELECT id FROM publicacion WHERE id = ? FOR UPDATE", (publicacion_id,))
        cuenta = con.execute(
            "SELECT COUNT(*) AS n FROM pieza WHERE publicacion_id = ?",
            (publicacion_id,),
        ).fetchone()
        if cuenta is not None and int(cuenta["n"]) <= 1:
            # Padre 1:1 con la pieza: borrarlo arrastra fila y etiquetas (cascada manual,
            # mismas sentencias que `borrar_publicacion` pero dentro de ESTA transaccion).
            con.execute(
                "DELETE FROM pieza WHERE publicacion_id = ?", (publicacion_id,)
            )
            con.execute(
                "DELETE FROM publicacion_etiquetas WHERE publicacion_id = ?", (publicacion_id,)
            )
            cur = con.execute("DELETE FROM publicacion WHERE id = ?", (publicacion_id,))
            con.commit()
            return cur.rowcount > 0
        # Anidada bajo un tema con mas piezas: borrar SOLO esta fila, conservar el tema.
        cur = con.execute(
            "DELETE FROM pieza WHERE id = ?", (pieza_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def duplicar_evento_rota(
    evento_id: str,
    *,
    fecha: str | None = None,
    hora: str | None = None,
    titulo: str | None = None,
) -> dict[str, Any] | None:
    """Crea un evento nuevo clonando los campos editoriales de `evento_id`.

    DECISION DE NEGOCIO: el clon RESETEA el flag `cambiado` (un evento clonado NO ha sido
    reprogramado: es un evento RECIEN creado, aunque su `fecha` se ajuste al duplicarlo).
    `fecha`/`hora`/`titulo` se pueden sobrescribir (caso comun: "Pumas vs América Jornada
    17 -> Jornada 18"). No clona los turnos asociados: la cobertura es de la SEMANA, no
    del partido. Devuelve el evento nuevo o None si el `evento_id` no existe.
    """
    original = obtener_evento_rota(evento_id)
    if original is None:
        return None
    return crear_evento_rota(
        titulo if titulo is not None else original.get("titulo", ""),
        fecha=fecha if fecha is not None else original.get("fecha", ""),
        hora=hora if hora is not None else original.get("hora", ""),
        contenido=original.get("contenido", ""),
        nota=original.get("nota", ""),
        tipo_cobertura=original.get("tipo_cobertura", TIPO_COBERTURA_TRANSMISION),
        prioridad=original.get("prioridad", PRIORIDAD_EVENTO_DEFECTO),
        marca=original.get("marca", ""),
    )

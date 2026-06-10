"""Persistencia — dominio publicaciones. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from collections.abc import Sequence

from ._db_comun import (
    PRIORIDAD_EVENTO_DEFECTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPO_CONTENIDO_DEFECTO,
    Any,
    _conectar,
    ahora_iso,
)
from .db_contenido import (
    _fila_contenido_nueva,
    _insertar_contenido,
    _insertar_contenido_plataforma,
    obtener_contenido_plataforma,
)
from .db_rota import (
    crear_evento_rota,
    obtener_evento_rota,
)

# --------------------------------------------------------------------------- #
# Publicaciones sobre el modelo unificado (FUSIÓN, paso 3)                       #
# --------------------------------------------------------------------------- #
# Una PUBLICACION = una fila `contenido_plataforma` con `es_publicacion=1` unida a su
# `contenido` padre (1:1). Estas funciones conservan EXACTAMENTE la firma y la forma del
# dict que antes producía `ficheros.py` (YAML), de modo que `api/publicaciones`,
# `api/aprobacion`, `programador` (Metricool), `dominio/publicaciones` y el frontend de
# Publicaciones siguen funcionando sin cambios (van por la fachada `repos`). El ciclo
# editorial (borrador→en_revision→aprobado→programado→publicado) se traduce al ciclo
# unificado de plataforma: `borrador` ⇆ `pendiente`/`en_curso`.

# pub -> plataforma: el `borrador` editorial es el `pendiente` del tablero; el resto 1:1.
_ESTADO_PUB_A_PLAT: dict[str, str] = {
    "borrador": "pendiente",
    "en_revision": "en_revision",
    "aprobado": "aprobado",
    "programado": "programado",
    "publicado": "publicado",
}
# plataforma -> pub: el vocabulario editorial solo conoce `borrador` para "en progreso".
_ESTADO_PLAT_A_PUB: dict[str, str] = {
    "pendiente": "borrador",
    "en_curso": "borrador",
    "en_revision": "en_revision",
    "aprobado": "aprobado",
    "programado": "programado",
    "publicado": "publicado",
}

# Columnas de la fila por plataforma que mapean campos editables de una publicacion.
# (El `contenido` de la publicacion es el `copy` de la plataforma; ver `_campos_pub_a_plat`.)
_SELECT_PUBLICACION = (
    "SELECT cp.id AS pid, cp.red AS red, cp.estado AS pestado, cp.copy AS copy, "
    "cp.copy_in AS copy_in, "
    "cp.imagen AS imagen, cp.imagen_fuente AS imagen_fuente, cp.foto AS foto, "
    "cp.video AS video, cp.falta_video AS falta_video, "
    "cp.veredicto AS veredicto, cp.revisor_id AS revisor_id, "
    "cp.revisor_nombre AS revisor_nombre, cp.revisado_en AS revisado_en, "
    "cp.enviado_a_revision_en AS enviado_a_revision_en, cp.fecha_programada AS fecha_programada, "
    "cp.preparado_en AS preparado_en, cp.id_post_metricool AS id_post_metricool, "
    "cp.falta_copy AS falta_copy, cp.falta_imagen AS falta_imagen, "
    "cp.falta_revision AS falta_revision, cp.falta_publicar AS falta_publicar, "
    "cp.evergreen AS evergreen, cp.copy_in_exento AS copy_in_exento, "
    "cp.placa_oculta AS placa_oculta, cp.plantilla_diseno_id AS plantilla_diseno_id, "
    "cp.foto_encuadre AS foto_encuadre, cp.fotos AS fotos, "
    "cp.qa_auto_hash AS qa_auto_hash, cp.actualizado AS pactualizado, "
    "c.id AS cid, c.titulo AS titulo, c.marca AS marca, c.autor_id AS autor_id, "
    "c.autor_nombre AS autor_nombre, c.origen AS origen, c.creado AS ccreado, "
    "c.fecha_fuente AS fecha_fuente, "
    "c.url_fuente AS url_fuente, c.fuente_nombre AS fuente_nombre, "
    "c.tipo_contenido AS tipo_contenido, "
    "c.formato AS formato, c.espejo AS espejo "
    "FROM contenido_plataforma cp JOIN contenido c ON cp.contenido_id = c.id "
    # Toda fila por plataforma de un `contenido` (no de una `tarea`) ES una publicacion:
    # el muro `es_publicacion` se retiro al fusionar Tablero y Publicaciones (#fusion). La
    # columna persiste por compatibilidad pero ya no filtra; `clase` excluye las tareas.
    "WHERE c.clase = 'contenido'"
)


def _fila_a_publicacion(f: Any) -> dict[str, Any]:
    """Reconstruye el dict público de una publicacion desde la fila unida (plat + padre)."""
    return {
        "id": f["pid"],
        "contenido_id": f["cid"] or "",
        "titulo": f["titulo"] or "",
        "marca": f["marca"] or "",
        "red": f["red"] or "",
        "contenido": f["copy"] or "",
        "copy_in": f["copy_in"] or "",
        "estado": _ESTADO_PLAT_A_PUB.get(f["pestado"] or "pendiente", "borrador"),
        "veredicto": f["veredicto"] or "",
        "autor_id": f["autor_id"] or "",
        "autor_nombre": f["autor_nombre"] or "",
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
        # pieza propaga los mismos campos a sus redes hermanas (api/publicaciones lo aplica).
        "espejo": bool(f["espejo"]) if f["espejo"] is not None else True,
        "imagen_fuente": f["imagen_fuente"] or "",
        # Media id de la FOTO CRUDA de fondo (separada de `imagen`, la placa ya compuesta);
        # permite al editor inline recomponer la placa en vivo al reabrir la pieza.
        "foto": f["foto"] or "",
        # Checklist de producción por red (el editor lo expone como checks marcables).
        "falta_copy": bool(f["falta_copy"]),
        "falta_imagen": bool(f["falta_imagen"]),
        "falta_revision": bool(f["falta_revision"]),
        "falta_publicar": bool(f["falta_publicar"]),
        "fecha_creacion": f["ccreado"] or "",
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
        "imagen": f["imagen"] or "",
        # Asset de VIDEO (Ola VIDEO): clave del media (`videos/<sha256>.<ext>`) y su checklist,
        # espejo de `imagen`/`falta_imagen`. Lo usa el programador para publicar `TipoMedia.video`.
        "video": f["video"] or "",
        "falta_video": bool(f["falta_video"]),
        "evergreen": bool(f["evergreen"]),
        # Auto-avance: exencion de copy-in + hash del copy con QA auto lanzada.
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
        "qa_auto_hash": f["qa_auto_hash"] or "",
    }


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
    # Default "" (no TIPO_CONTENIDO_DEFECTO) para que la firma sea IDÉNTICA a la de
    # `repos.crear_publicacion` (test de paridad); el valor real se coalesce abajo.
    tipo_contenido: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
    id: str = "",
    fecha_creacion: str = "",
) -> dict[str, Any]:
    """Crea una publicacion (padre `contenido` + fila `contenido_plataforma` es_publicacion=1).

    ATOMICA: padre y fila por plataforma se insertan en UNA transaccion (antes eran dos:
    un fallo entre ambas dejaba un `contenido` huerfano sin fila por plataforma).

    Acepta `id`/`fecha_creacion` opcionales (preservaban identidad al migrar desde el YAML
    legado, hoy retirado). El `estado` editorial se traduce al de
    plataforma. `imagen_fuente` (URL original, p.ej. de un RSS de marca propia) +
    `tipo_contenido='fuente'` nacen juntos: hay imagen (la del artículo), así que la pieza
    no queda con `falta_imagen`.
    """
    con = _conectar()
    try:
        padre, plat = _insertar_publicacion(
            con,
            marca=marca,
            red=red,
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
        con.commit()
    finally:
        con.close()
    return obtener_publicacion(plat["id"]) or _publicacion_de_filas(padre, plat)


def _insertar_publicacion(
    con: Any, *, marca: str, red: str, **campos: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Inserta padre + fila por plataforma sobre `con` (SIN commit). Devuelve `(padre, plat)`.

    Nucleo compartido por `crear_publicacion` (transaccion propia) y `crear_publicaciones`
    (lote todo-o-nada: N publicaciones en UNA transaccion del llamante). Mismos kwargs que
    `crear_publicacion` (menos los posicionales `marca`/`red`).
    """
    evergreen = bool(campos.get("evergreen"))
    fecha_creacion = campos.get("fecha_creacion") or ""
    imagen_fuente = campos.get("imagen_fuente") or ""
    padre = _fila_contenido_nueva(
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
    _insertar_contenido(con, padre)
    plat = _insertar_contenido_plataforma(
        con,
        id=campos.get("id") or "",
        contenido_id=padre["id"],
        red=red,
        # Marca denormalizada explicita: la del padre recien insertado (evita un lookup extra).
        marca=padre["marca"],
        estado=_ESTADO_PUB_A_PLAT.get(campos.get("estado") or "borrador", "pendiente"),
        copy=campos.get("contenido") or "",
        copy_in=campos.get("copy_in") or "",
        imagen=campos.get("imagen") or "",
        imagen_fuente=imagen_fuente,
        # Si hay imagen de fuente (URL del artículo), la pieza YA tiene imagen.
        falta_imagen=False if imagen_fuente else None,
        veredicto=campos.get("veredicto") or "",
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
    """Construye el dict publico de una publicacion desde las filas padre+plataforma en mano.

    Equivale a `_fila_a_publicacion` sobre la fila unida, sin re-leer la base: lo usan los
    caminos que acaban de INSERTAR ambas filas (creacion y lote) y ya tienen los datos.
    """
    return _fila_a_publicacion(
        {
            "pid": plat["id"], "red": plat["red"], "pestado": plat["estado"],
            "copy": plat["copy"], "copy_in": plat["copy_in"], "imagen": plat["imagen"],
            "imagen_fuente": plat["imagen_fuente"], "foto": plat["foto"],
            "video": plat["video"], "falta_video": plat["falta_video"],
            "veredicto": plat["veredicto"], "revisor_id": plat["revisor_id"],
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
            "qa_auto_hash": plat["qa_auto_hash"], "pactualizado": plat["actualizado"],
            "cid": padre["id"], "titulo": padre["titulo"], "marca": padre["marca"],
            "autor_id": padre["autor_id"], "autor_nombre": padre["autor_nombre"],
            "origen": padre["origen"], "ccreado": padre["creado"],
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
    """Crea varias publicaciones (una por dict de entrada) y las devuelve. TODO-O-NADA.

    Antes iteraba `crear_publicacion` (una transaccion POR pieza): un fallo a mitad dejaba
    el lote a medias pese a que el endpoint promete "si una falla, no inserta". Ahora las N
    publicaciones se insertan en UNA SOLA transaccion: si cualquier insert falla, ninguna
    queda (el `close()` sin commit hace rollback) y la excepcion se propaga al caller.
    """
    con = _conectar()
    creadas: list[dict[str, Any]] = []
    try:
        for d in lista:
            padre, plat = _insertar_publicacion(
                con,
                marca=d.get("marca", "") or "",
                red=d.get("red", "") or "",
                titulo=d.get("titulo", "") or "",
                contenido=d.get("contenido", "") or "",
                copy_in=d.get("copy_in", "") or "",
                estado=d.get("estado", "borrador") or "borrador",
                veredicto=d.get("veredicto", "") or "",
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
) -> tuple[str, list[Any]]:
    """Construye la cláusula WHERE adicional (tras `es_publicacion=1`) y sus parámetros.

    `marca` admite UNA marca (str) o VARIAS (secuencia -> `c.marca IN (...)`). El caso
    multi-marca empuja al SQL el foco por marcas preferentes del feed, que antes se
    post-filtraba en memoria y ROMPIA el keyset (página corta + cursor que salta filas).
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
    # Línea editorial = etiqueta de clase `vertical` asignada al `contenido` padre. Se filtra
    # con un EXISTS sobre la tabla puente (no JOIN, para no duplicar filas si hubiera varias).
    if linea:
        clausulas.append(
            "EXISTS (SELECT 1 FROM contenido_etiquetas ce "
            "WHERE ce.contenido_id = c.id AND ce.etiqueta_id = ?)"
        )
        params.append(linea)
    if estado:
        # `borrador` casa los estados "en progreso" del tablero (pendiente/en_curso).
        if estado == "borrador":
            clausulas.append("cp.estado IN ('pendiente', 'en_curso')")
        else:
            clausulas.append("cp.estado = ?")
            params.append(_ESTADO_PUB_A_PLAT.get(estado, estado))
    if evergreen is not None:
        clausulas.append("cp.evergreen = ?")
        params.append(1 if evergreen else 0)
    return (" AND " + " AND ".join(clausulas) if clausulas else ""), params


def listar_publicaciones(
    marca: str | Sequence[str] | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    linea: str | None = None,
    *,
    limite: int | None = None,
    desplazamiento: int | None = None,
    cursor: tuple[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Publicaciones (más recientes primero) con filtros y paginación opcionales.

    Orden estable `(c.creado DESC, cp.id DESC)` apto para scroll infinito. Dos modos
    de paginar, mutuamente excluyentes (KEYSET tiene prioridad si se pasan ambos):
      - OFFSET (`limite`/`desplazamiento`): ventana clásica; sirve al calendario/lista que
        ya lo usaban. Sin `limite` se devuelve el conjunto COMPLETO (comportamiento previo).
      - KEYSET (`cursor`): `cursor=(creado, id)` = última clave vista; devuelve solo las
        filas ESTRICTAMENTE posteriores en el orden (más antiguas). Inmune a inserciones
        nuevas al principio (no desplaza páginas), ideal para el feed social.
    """
    extra, params = _filtros_publicacion(marca, red, estado, evergreen, linea)
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


def contar_publicaciones(
    marca: str | Sequence[str] | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    linea: str | None = None,
) -> int:
    """Total de publicaciones que casan los filtros (para el `total` de paginación)."""
    extra, params = _filtros_publicacion(marca, red, estado, evergreen, linea)
    sql = (
        "SELECT COUNT(*) AS n FROM contenido_plataforma cp "
        "JOIN contenido c ON cp.contenido_id = c.id WHERE c.clase = 'contenido'" + extra
    )
    con = _conectar()
    try:
        fila = con.execute(sql, tuple(params)).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    """Una publicacion por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PUBLICACION} AND cp.id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_publicacion(fila) if fila is not None else None


# Campo de publicacion -> columna de la fila por plataforma (edición parcial).
_CAMPOS_PUB_A_PLAT: dict[str, str] = {
    "contenido": "copy",
    "copy_in": "copy_in",
    "veredicto": "veredicto",
    "fecha_programada": "fecha_programada",
    "imagen": "imagen",
    "foto": "foto",
    "evergreen": "evergreen",
    "placa_oculta": "placa_oculta",
    "plantilla_diseno_id": "plantilla_diseno_id",
    "foto_encuadre": "foto_encuadre",
    "fotos": "fotos",
    "enviado_a_revision_en": "enviado_a_revision_en",
    "revisor_id": "revisor_id",
    "revisor_nombre": "revisor_nombre",
    "revisado_en": "revisado_en",
    "preparado_en": "preparado_en",
    "id_post_metricool": "id_post_metricool",
}


def actualizar_publicacion(
    publicacion_id: str,
    campos: dict[str, Any],
    *,
    estado_esperado: str | None = None,
) -> dict[str, Any] | None:
    """Edita parcialmente una publicacion; None si no existe. Mapea a padre/plataforma.

    ATOMICA: la fila por plataforma y el padre se actualizan en UNA SOLA transaccion
    (antes eran dos: un fallo entre ambas dejaba media edicion aplicada, p. ej. el estado
    movido pero el titulo sin tocar).

    `estado_esperado` (opcional) añade un CAS al UPDATE de la fila por plataforma: solo
    aplica si el `estado` ACTUAL (de publicacion) sigue siendo ese; si otro flujo lo movio
    entre el snapshot del caller y esta escritura, NO se toca nada y se devuelve None (el
    caller lo distingue de "no existe" re-leyendo). Cierra el TOCTOU del PUT generico.
    """
    plat = obtener_contenido_plataforma(publicacion_id)
    if plat is None:
        return None

    cambios_plat: dict[str, Any] = {}
    for clave, columna in _CAMPOS_PUB_A_PLAT.items():
        if clave in campos:
            valor = campos[clave]
            if clave in ("evergreen", "placa_oculta"):
                valor = 1 if valor else 0
            cambios_plat[columna] = valor
    if "estado" in campos:
        cambios_plat["estado"] = _ESTADO_PUB_A_PLAT.get(campos["estado"], "pendiente")

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
            params: list[Any] = [*cambios_plat.values(), ahora, publicacion_id]
            sql = (
                f"UPDATE contenido_plataforma SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
                "WHERE id = ?"
            )
            if estado_esperado is not None:
                # El estado de PUBLICACION es una proyeccion del de plataforma y NO es 1:1
                # (tanto `pendiente` como `en_curso` proyectan a `borrador`): el CAS acepta
                # CUALQUIER estado de plataforma que proyecte al esperado, o un en_curso
                # quedaria bloqueado para siempre por un falso "estado movido".
                plat_esperados = [
                    p for p, e in _ESTADO_PLAT_A_PUB.items() if e == estado_esperado
                ] or [estado_esperado]
                marcadores_cas = ", ".join("?" for _ in plat_esperados)
                sql += f" AND estado IN ({marcadores_cas})"
                params.extend(plat_esperados)
            cur = con.execute(sql, tuple(params))
            if cur.rowcount == 0:
                # No existe o el CAS no aplico (estado movido): nada que commitear.
                return None
        if cambios_padre:
            asignaciones_p = [f"{col} = ?" for col in cambios_padre]
            asignaciones_p.append("actualizado = ?")
            con.execute(
                f"UPDATE contenido SET {', '.join(asignaciones_p)} WHERE id = ?",  # noqa: S608 -- allowlist
                (*cambios_padre.values(), ahora, plat["contenido_id"]),
            )
        con.commit()
    finally:
        con.close()
    return obtener_publicacion(publicacion_id)


def reclamar_preparacion(publicacion_id: str, ts: str) -> bool:
    """Claim ATOMICO de la preparacion de una publicacion. True si ESTE llamante la reclamo.

    Estampa `preparado_en = ts` SOLO si aun estaba sin preparar (`'' / NULL`), en un unico
    UPDATE condicional. Devuelve `rowcount > 0`: True si la fila pasó de "sin preparar" a
    "preparada" en esta llamada; False si ya estaba preparada (otro barrido/replica gano la
    carrera) o si la publicacion no existe. Evita la doble preparacion/publicacion del
    patron leer-`preparado_en`-y-luego-UPDATE cuando hay >1 barrido en paralelo (varias
    replicas). La publicacion es la fila `contenido_plataforma` (su id ES `publicacion_id`).
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE contenido_plataforma SET preparado_en = ? "
            "WHERE id = ? AND (preparado_en = '' OR preparado_en IS NULL)",
            (ts, publicacion_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def transicionar_estado_publicacion(
    publicacion_id: str,
    estado_origen: str,
    estado_destino: str,
    campos_extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Transicion de estado GUARDADA (CAS) de una publicacion. None si el origen ya cambió.

    Cierra el TOCTOU de "leer estado en Python -> escribir en una transaccion posterior" del
    flujo de aprobacion (`enviar_a_revision`, `programar`): en lugar de confiar en un snapshot,
    mueve el `estado` en un UNICO UPDATE condicional
        `UPDATE contenido_plataforma SET estado=? [, extras...] WHERE id=? AND estado=?`
    sobre la fila por plataforma (la publicacion ES esa fila; su id ES `publicacion_id`). Asi
    dos peticiones simultaneas (doble-click, dos revisores) NO pasan ambas: la primera gana y la
    segunda ve `rowcount == 0` y recibe `None` (el caller lo traduce a 409 "el estado cambió").

    `estado_origen`/`estado_destino` son estados de PUBLICACION (`borrador`/`en_revision`/
    `aprobado`/`programado`/...); se mapean a los de la fila por plataforma con `_ESTADO_PUB_A_PLAT`
    (espejo del CAS de `actualizar_publicacion`). `campos_extra` son campos de PUBLICACION
    adicionales a sellar EN EL MISMO UPDATE (p.ej. `enviado_a_revision_en`, `fecha_programada`,
    `revisor_*`, `preparado_en`); solo se aceptan los que mapean a columnas de la fila por
    plataforma via `_CAMPOS_PUB_A_PLAT` (el resto se ignora). Igual que `reclamar_preparacion`,
    una `IntegrityError` (p.ej. el indice de slot de parrilla) se PROPAGA al caller para que la
    traduzca (no la traga). Devuelve la publicacion actualizada o None (no existe / CAS no aplicó).
    """
    plat_origen = _ESTADO_PUB_A_PLAT.get(estado_origen, estado_origen)
    plat_destino = _ESTADO_PUB_A_PLAT.get(estado_destino, estado_destino)
    asignaciones = ["estado = ?", "actualizado = ?"]
    params: list[Any] = [plat_destino, ahora_iso()]
    for clave, valor in (campos_extra or {}).items():
        columna = _CAMPOS_PUB_A_PLAT.get(clave)
        if columna is None or columna == "estado":
            continue  # solo columnas de la fila por plataforma; el estado va por el CAS
        asignaciones.append(f"{columna} = ?")
        params.append(valor)
    params.extend([publicacion_id, plat_origen])
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE contenido_plataforma SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
            "WHERE id = ? AND estado = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_publicacion(publicacion_id)


def existe_cadena_aprobacion(plataforma_id: str) -> bool:
    """True si la pieza YA tiene cadena de aprobacion (>=1 nivel). Para montarla idempotente."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM contenido_aprobaciones WHERE plataforma_id = ? LIMIT 1",
            (plataforma_id,),
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def borrar_publicacion(publicacion_id: str) -> bool:
    """Borra una publicacion. True si existía.

    Dos casos (modelo consolidado: publicacion = fila `contenido_plataforma` con
    `es_publicacion=1` colgada de un `contenido`):
      - Publicacion SUELTA (su padre 1:1 solo contiene esta fila): se borra el padre, que
        arrastra la fila (no deja un `contenido` huerfano y vacio). Es el caso de la
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
            "SELECT contenido_id FROM contenido_plataforma WHERE id = ?",
            (publicacion_id,),
        ).fetchone()
        if fila is None:
            return False
        contenido_id = fila["contenido_id"]
        # Serializa contra otros borrados/ediciones del MISMO tema (lock de fila del padre).
        con.execute("SELECT id FROM contenido WHERE id = ? FOR UPDATE", (contenido_id,))
        cuenta = con.execute(
            "SELECT COUNT(*) AS n FROM contenido_plataforma WHERE contenido_id = ?",
            (contenido_id,),
        ).fetchone()
        if cuenta is not None and int(cuenta["n"]) <= 1:
            # Padre 1:1 con la publicacion: borrarlo arrastra fila y etiquetas (cascada manual,
            # mismas sentencias que `borrar_contenido` pero dentro de ESTA transaccion).
            con.execute(
                "DELETE FROM contenido_plataforma WHERE contenido_id = ?", (contenido_id,)
            )
            con.execute(
                "DELETE FROM contenido_etiquetas WHERE contenido_id = ?", (contenido_id,)
            )
            cur = con.execute("DELETE FROM contenido WHERE id = ?", (contenido_id,))
            con.commit()
            return cur.rowcount > 0
        # Anidada bajo un tema con mas piezas: borrar SOLO esta fila, conservar el tema.
        cur = con.execute(
            "DELETE FROM contenido_plataforma WHERE id = ?", (publicacion_id,)
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
    )

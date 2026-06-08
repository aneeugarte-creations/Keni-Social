"""Persistencia — dominio publicaciones. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    PRIORIDAD_EVENTO_DEFECTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPO_CONTENIDO_DEFECTO,
    Any,
    _conectar,
    datetime,
)
from .db_contenido import (
    actualizar_contenido,
    actualizar_contenido_plataforma,
    borrar_contenido,
    borrar_contenido_plataforma,
    crear_contenido,
    crear_contenido_plataforma,
    listar_contenido_plataforma,
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
    "c.tipo_contenido AS tipo_contenido, "
    "c.formato AS formato "
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

    Acepta `id`/`fecha_creacion` opcionales (preservaban identidad al migrar desde el YAML
    legado, hoy retirado). El `estado` editorial se traduce al de
    plataforma. `imagen_fuente` (URL original, p.ej. de un RSS de marca propia) +
    `tipo_contenido='fuente'` nacen juntos: hay imagen (la del artículo), así que la pieza
    no queda con `falta_imagen`.
    """
    padre = crear_contenido(
        clase="contenido",
        flujo="evergreen" if evergreen else "",
        titulo=titulo,
        marca=marca,
        tipo_contenido=tipo_contenido or TIPO_CONTENIDO_DEFECTO,
        autor=autor,
        origen=origen,
        creado=fecha_creacion,
        actualizado=fecha_creacion,
    )
    plat = crear_contenido_plataforma(
        id=id,
        contenido_id=padre["id"],
        red=red,
        # Marca denormalizada explicita: la del padre recien creado (evita un lookup extra).
        marca=padre["marca"],
        estado=_ESTADO_PUB_A_PLAT.get(estado, "pendiente"),
        copy=contenido,
        copy_in=copy_in,
        imagen=imagen,
        imagen_fuente=imagen_fuente,
        # Si hay imagen de fuente (URL del artículo), la pieza YA tiene imagen.
        falta_imagen=False if imagen_fuente else None,
        veredicto=veredicto,
        fecha_programada=fecha_programada,
        evergreen=evergreen,
        es_publicacion=True,
        creado=fecha_creacion,
        actualizado=fecha_creacion,
    )
    return obtener_publicacion(plat["id"]) or _fila_a_publicacion(
        {
            "pid": plat["id"], "red": red, "pestado": plat["estado"], "copy": contenido,
            "copy_in": copy_in,
            "imagen": imagen, "veredicto": veredicto, "revisor_id": "", "revisor_nombre": "",
            "revisado_en": "", "enviado_a_revision_en": "", "fecha_programada": fecha_programada,
            "preparado_en": "", "id_post_metricool": "", "evergreen": plat["evergreen"],
            "pactualizado": plat["actualizado"], "cid": padre["id"], "titulo": titulo,
            "marca": marca, "autor_id": padre["autor_id"], "autor_nombre": padre["autor_nombre"],
            "origen": origen, "ccreado": padre["creado"],
        }
    )


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Crea varias publicaciones (una por dict de entrada) y las devuelve."""
    creadas: list[dict[str, Any]] = []
    for d in lista:
        creadas.append(
            crear_publicacion(
                d.get("marca", "") or "",
                d.get("red", "") or "",
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
        )
    return creadas


def _filtros_publicacion(
    marca: str | None,
    red: str | None,
    estado: str | None,
    evergreen: bool | None,
    linea: str | None = None,
) -> tuple[str, list[Any]]:
    """Construye la cláusula WHERE adicional (tras `es_publicacion=1`) y sus parámetros."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("c.marca = ?")
        params.append(marca)
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
    marca: str | None = None,
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
    marca: str | None = None,
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
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una publicacion; None si no existe. Mapea a padre/plataforma."""
    actual = obtener_publicacion(publicacion_id)
    if actual is None:
        return None
    plat = obtener_contenido_plataforma(publicacion_id)
    if plat is None:
        return None

    cambios_plat: dict[str, Any] = {}
    for clave, columna in _CAMPOS_PUB_A_PLAT.items():
        if clave in campos:
            cambios_plat[columna] = (
                bool(campos[clave]) if clave in ("evergreen", "placa_oculta") else campos[clave]
            )
    if "estado" in campos:
        cambios_plat["estado"] = _ESTADO_PUB_A_PLAT.get(campos["estado"], "pendiente")
    if cambios_plat:
        actualizar_contenido_plataforma(publicacion_id, cambios_plat)

    cambios_padre: dict[str, Any] = {}
    if "titulo" in campos:
        cambios_padre["titulo"] = campos["titulo"]
    if "evergreen" in campos:
        cambios_padre["flujo"] = "evergreen" if campos["evergreen"] else ""
    if cambios_padre:
        actualizar_contenido(plat["contenido_id"], cambios_padre)

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
    params: list[Any] = [plat_destino, datetime.now().isoformat(timespec="seconds")]
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
    """
    plat = obtener_contenido_plataforma(publicacion_id)
    if plat is None:
        return False
    hermanas = listar_contenido_plataforma(plat["contenido_id"])
    if len(hermanas) <= 1:
        # Padre 1:1 con la publicacion: borrarlo arrastra la fila por plataforma.
        return borrar_contenido(plat["contenido_id"])
    # Anidada bajo un tema con mas piezas: borrar SOLO esta fila, conservar el tema.
    return borrar_contenido_plataforma(publicacion_id)


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

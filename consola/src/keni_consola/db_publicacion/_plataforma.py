"""Persistencia — contenido por plataforma (`pieza`). Impl. de db.py (barrel)."""
from __future__ import annotations

from .._db_comun import (
    ESTADOS_PIEZA,
    Any,
    _conectar,
    ahora_iso,
    uuid,
)
from ._contenido import ConflictoVersion

__all__ = [
    "_COLS_PIEZA",
    "_SELECT_PIEZA",
    "_BOOLS_PIEZA",
    "_CAMPOS_EDITABLES_PIEZA",
    "_fila_a_pieza",
    "crear_pieza_fila",
    "listar_piezas_fila",
    "obtener_pieza_fila",
    "actualizar_pieza_fila",
    "borrar_pieza_fila",
]

_COLS_PIEZA = (
    "id",
    "publicacion_id",
    "red",
    # `marca` DENORMALIZADA (sync del padre). No es editable directamente (ver lista blanca).
    "marca",
    "estado",
    "falta_copy",
    "falta_imagen",
    "falta_revision",
    "falta_publicar",
    "falta_video",
    "copy",
    "copy_in",
    "imagen",
    "imagen_fuente",
    "foto",
    "video",
    "revision",
    "revisor_id",
    "revisor_nombre",
    "revisado_en",
    "enviado_a_revision_en",
    "fecha_programada",
    "preparado_en",
    "id_post_metricool",
    "enlace",
    "evergreen",
    "es_publicacion",
    "copy_in_exento",
    "placa_oculta",
    "plantilla_diseno_id",
    "foto_encuadre",
    "fotos",
    "carrusel",
    "verificar_auto_hash",
    "hora_post",
    "creado",
    "actualizado",
    # CONCURRENCIA OPTIMISTA (ADR 0012): sube en cada `actualizar_pieza_fila`/transicion.
    "version",
)
_SELECT_PIEZA = (
    f"SELECT {', '.join(_COLS_PIEZA)} FROM pieza"
)
_BOOLS_PIEZA = (
    "falta_copy",
    "falta_imagen",
    "falta_revision",
    "falta_publicar",
    "falta_video",
    "evergreen",
    "es_publicacion",
    "copy_in_exento",
    "placa_oculta",
)
# Campos editables de una fila por plataforma (lista blanca). `id`, `publicacion_id`,
# `red`, `marca`, `es_publicacion`, `creado` y `actualizado` no se editan (los dos ultimos los
# gestiona el sistema; `es_publicacion` se fija al crear; `marca` es DENORMALIZADA del padre y
# solo la sincroniza el sistema —insert + reasignacion de marca del padre—, nunca el cliente).
_CAMPOS_EDITABLES_PIEZA: tuple[str, ...] = tuple(
    c
    for c in _COLS_PIEZA
    if c
    not in (
        "id", "publicacion_id", "red", "marca", "es_publicacion", "creado", "actualizado",
        # `version` la gestiona el sistema (concurrencia optimista, ADR 0012): nunca editable.
        "version",
    )
)


def _fila_a_pieza(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `pieza` en dict (booleanos como bool)."""
    plat: dict[str, Any] = {col: fila[col] for col in _COLS_PIEZA}
    for col in _BOOLS_PIEZA:
        plat[col] = bool(fila[col])
    plat["estado"] = fila["estado"] or "borrador"
    # `imagen` es el NOMBRE de archivo en el dir de media; `imagen_url` es su ruta
    # servible. La UI debe usar SIEMPRE `imagen_url` en un <img>; `imagen` a secas no es
    # navegable. Si no hay media adjunta pero la pieza es de tipo "fuente" (trae la URL de
    # la imagen original en `imagen_fuente`), se sirve ESA tal cual (es ya navegable).
    imagen = plat.get("imagen") or ""
    fuente = plat.get("imagen_fuente") or ""
    plat["imagen"] = imagen
    plat["imagen_fuente"] = fuente
    # `imagen_url`: si hay `imagen` horneada, esa. Si NO, pero la pieza se DERIVA de una receta
    # (plantilla del estudio, o placa de marca: copy_in con la placa visible), apunta al render
    # on-demand `/compuesta` (el endpoint re-obtiene la pieza con su marca y compone). Si solo
    # hay foto/fuente, esas. La señal aquí es local (esta tabla no guarda `marca`): si la marca
    # no tuviera plantilla, `/compuesta` resuelve a la foto igualmente, sin romper.
    derivable = bool((plat.get("plantilla_diseno_id") or "").strip()) or (
        not plat.get("placa_oculta") and bool((plat.get("copy_in") or "").strip())
    )
    if imagen:
        plat["imagen_url"] = f"/api/media/{imagen}"
    elif derivable:
        plat["imagen_url"] = f"/api/piezas/{plat['id']}/compuesta"
    elif plat.get("foto"):
        plat["imagen_url"] = f"/api/media/{plat['foto']}"
    else:
        plat["imagen_url"] = fuente
    # `video` es el NOMBRE/clave del asset de video en el almacen; `video_url` su ruta servible
    # (`/api/media/{video}`, mismo endpoint que las imagenes). "" si no hay video adjunto. Espejo
    # del par `imagen`/`imagen_url`: la UI usa SIEMPRE `video_url` en un <video>.
    video = plat.get("video") or ""
    plat["video"] = video
    plat["video_url"] = f"/api/media/{video}" if video else ""
    return plat


def _plantilla_rotacion(con: Any, marca: str, publicacion_id: str) -> str:
    """Plantilla EN ROTACIÓN de la marca para esta pieza, o "" si no aplica.

    Las plantillas que el equipo marca «en rotación» (`rotar=1`) son las que MANDAN: una pieza nueva
    SIEMPRE se lleva una de ellas, nunca una de fuera de la rotación. Con UNA sola en rotación, esa se
    fija en todas las piezas; con VARIAS, se alternan (round-robin) y todas las redes de la MISMA
    pieza comparten color. Dormido SOLO si la marca no tiene NINGUNA plantilla con `rotar=1` (del
    `tipo` que toca según el formato): ahí devuelve "" y el render cae a la por defecto de la marca.
    Reglas:

      - El POOL son las plantillas activas de la marca con `rotar=1` y `tipo` acorde al formato de la
        pieza (foto -> "foto"; video -> "miniatura"), en orden estable (`creado ASC`).
      - MISMO color en todas las redes: si una red hermana de la pieza ya tiene una plantilla del
        pool, se reutiliza.
      - PRIMERA red de la pieza: round-robin por nº de PIEZAS de la marca ya rotadas
        (`pool[n % len(pool)]`), no por marca de tiempo —`creado` se guarda al segundo y empata
        entre piezas creadas a la vez, lo que hacía un "última usada" poco fiable—. Con un pool de
        UNA sola plantilla, `n % 1 == 0` siempre: esa misma plantilla en cada pieza.

    Stateless (sin contador propio): se deriva del recuento real de piezas ya rotadas, así funciona
    entre contenedores (back/worker/daemons) sin estado compartido y es estable.
    """
    # Atajo barato (la rotación está DORMIDA para casi todas las marcas): si la marca no tiene
    # NINGUNA plantilla en rotación, no toques nada más (evita el lookup de formato + pool).
    if con.execute(
        "SELECT 1 FROM plantillas_diseno WHERE marca = ? AND activo = 1 AND rotar = 1 LIMIT 1",
        (marca,),
    ).fetchone() is None:
        return ""
    padre = con.execute("SELECT formato FROM publicacion WHERE id = ?", (publicacion_id,)).fetchone()
    formato = (padre["formato"] if padre is not None else "") or "foto"
    tipo = "miniatura" if formato == "video" else "foto"
    pool = con.execute(
        "SELECT id FROM plantillas_diseno "
        "WHERE marca = ? AND activo = 1 AND rotar = 1 AND tipo = ? "
        "ORDER BY creado ASC, id ASC",
        (marca, tipo),
    ).fetchall()
    ids = [r["id"] for r in pool]
    # Sin NINGUNA plantilla en rotación del tipo acorde (p. ej. la rotación es de fotos y la pieza es
    # vídeo): no se fuerza un tipo que no toca; el render cae a la por defecto de la marca.
    if not ids:
        return ""
    # Mismo color en todas las redes: reutiliza el de una red hermana si ya tiene uno del pool.
    hermanas = con.execute(
        "SELECT plantilla_diseno_id FROM pieza "
        "WHERE publicacion_id = ? AND plantilla_diseno_id <> ''",
        (publicacion_id,),
    ).fetchall()
    for h in hermanas:
        if h["plantilla_diseno_id"] in ids:
            return str(h["plantilla_diseno_id"])
    # Primera red: round-robin por nº de PIEZAS de la marca ya rotadas (`pool[n % len(pool)]`). La
    # pieza actual aún no tiene ninguna red del pool (las hermanas se comprobaron arriba), así que
    # NO se cuenta a sí misma. Estable y sin depender de timestamps que empatan al segundo.
    marcadores = ", ".join("?" for _ in ids)
    fila = con.execute(
        f"SELECT COUNT(DISTINCT publicacion_id) AS n FROM pieza "  # noqa: S608 -- '?'
        f"WHERE marca = ? AND plantilla_diseno_id IN ({marcadores})",
        (marca, *ids),
    ).fetchone()
    n = int(fila["n"]) if fila is not None and fila["n"] is not None else 0
    return ids[n % len(ids)]


def _insertar_pieza(
    con: Any,
    *,
    publicacion_id: str,
    red: str,
    marca: str | None = None,
    estado: str = "borrador",
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
    """INSERT de una fila por plataforma sobre la conexion `con` del llamante (SIN commit).

    Nucleo de `crear_pieza_fila`, extraido para que un lote (p. ej.
    `db_piezas.crear_publicaciones`, todo-o-nada) inserte varias filas EN UNA SOLA
    transaccion: el llamante decide cuando commitear/cerrar. Devuelve la fila ya formateada.
    """
    ahora = ahora_iso()
    falta_copy = (not bool(copy)) if falta_copy is None else falta_copy
    falta_imagen = (not bool(imagen)) if falta_imagen is None else falta_imagen
    # `falta_video` (espejo de `falta_imagen`, pero con default INVERSO): cuando se pasa explicito
    # se respeta; cuando es None se asume 0 (N/A). El video solo es obligatorio en piezas
    # `formato='video'`; la creacion por defecto es `foto`, asi que `falta_video` nace en 0 y lo
    # activa quien sabe el formato (crear con `formato=video` o el flip `ajustar_plataformas_por_formato`).
    falta_video = False if falta_video is None else bool(falta_video)
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "publicacion_id": publicacion_id,
        "red": red,
        # Marca denormalizada: la del padre salvo override explicito. La derivacion real (lookup)
        # se hace abajo dentro de la conexion para que vea el padre ya commiteado.
        "marca": marca or "",
        "estado": estado if estado in ESTADOS_PIEZA else "borrador",
        "falta_copy": 1 if falta_copy else 0,
        "falta_imagen": 1 if falta_imagen else 0,
        "falta_revision": 1 if falta_revision else 0,
        "falta_publicar": 1 if falta_publicar else 0,
        "falta_video": 1 if falta_video else 0,
        "copy": copy or "",
        "copy_in": copy_in or "",
        "imagen": imagen or "",
        "imagen_fuente": imagen_fuente or "",
        "foto": foto or "",
        "video": video or "",
        "revision": revision or "",
        "revisor_id": revisor_id or "",
        "revisor_nombre": revisor_nombre or "",
        "revisado_en": revisado_en or "",
        "enviado_a_revision_en": enviado_a_revision_en or "",
        "fecha_programada": fecha_programada or "",
        "preparado_en": preparado_en or "",
        "id_post_metricool": id_post_metricool or "",
        "enlace": enlace or "",
        "evergreen": 1 if evergreen else 0,
        "es_publicacion": 1 if es_publicacion else 0,
        "copy_in_exento": 1 if copy_in_exento else 0,
        "placa_oculta": 1 if placa_oculta else 0,
        "plantilla_diseno_id": plantilla_diseno_id or "",
        "foto_encuadre": foto_encuadre or "",
        "fotos": fotos or "",
        "carrusel": carrusel or "",
        "verificar_auto_hash": verificar_auto_hash or "",
        "hora_post": hora_post or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
        # Concurrencia optimista (ADR 0012): nace en 0; lo sube cada update/transicion.
        "version": 0,
    }
    # Deriva la marca denormalizada del padre cuando el llamante no la pasa (el caso normal):
    # asi ningun call-site tiene que conocerla y la denormalizacion nace siempre alineada.
    if marca is None:
        padre = con.execute(
            "SELECT marca FROM publicacion WHERE id = ?", (publicacion_id,)
        ).fetchone()
        if padre is not None:
            fila["marca"] = padre["marca"] or ""
    # ROTACIÓN de plantillas: si el llamante NO fijó plantilla y la marca tiene plantillas EN
    # ROTACIÓN, asigna una de ellas (con varias, round-robin y mismo color en todas las redes; con
    # una sola, esa fija). Dormido solo si la marca no tiene NINGUNA plantilla con `rotar=1`.
    if not fila["plantilla_diseno_id"] and fila["marca"]:
        fila["plantilla_diseno_id"] = _plantilla_rotacion(con, fila["marca"], publicacion_id)
    marcadores = ", ".join("?" for _ in _COLS_PIEZA)
    con.execute(
        f"INSERT INTO pieza ({', '.join(_COLS_PIEZA)}) "
        f"VALUES ({marcadores})",
        tuple(fila[col] for col in _COLS_PIEZA),
    )
    return _fila_a_pieza(fila)


def crear_pieza_fila(
    *,
    publicacion_id: str,
    red: str,
    marca: str | None = None,
    estado: str = "borrador",
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
    """Inserta una fila por plataforma de un `contenido` y la devuelve. NO valida.

    El checklist `falta_copy`/`falta_imagen` se autodeduce de `copy`/`imagen` si no se pasa
    explicito (copy no vacio => no falta copy). `id`/`creado`/`actualizado` se pueden pasar
    para PRESERVAR identidad al migrar (p. ej. el id de una pieza legada).

    `marca` (DENORMALIZADA del padre) se DERIVA del `contenido` padre cuando no se pasa (`None`):
    asi la mayoria de los ~12 call-sites no tiene que enredarse con ella y la denormalizacion
    sigue siempre correcta. Pasar `marca` explicito solo lo necesita la migracion (preservar la
    marca de datos legados) o un padre aun no commiteado en otra transaccion. Mantenerla en sync
    es lo que da sentido al indice unico de parrilla POR MARCA (`idx_parrilla_slot_uniq`).
    El nucleo (INSERT sin commit) vive en `_insertar_pieza`, reutilizable por
    los lotes transaccionales; esta envoltura aporta la transaccion propia commit-y-cierra.
    """
    con = _conectar()
    try:
        fila = _insertar_pieza(
            con,
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
        con.commit()
    finally:
        con.close()
    return fila


def listar_piezas_fila(
    publicacion_id: str | None = None,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    """Filas por plataforma; filtros opcionales por `publicacion_id` y/o `marca` (denormalizada).

    `marca` empuja al SQL el filtro que el tablero aplicaba en memoria tras traer TODAS las
    filas (full scan por GET): con el workspace acotado a una marca, solo viajan sus filas.
    """
    sql = _SELECT_PIEZA
    clausulas: list[str] = []
    params: list[Any] = []
    if publicacion_id is not None:
        clausulas.append("publicacion_id = ?")
        params.append(publicacion_id)
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY publicacion_id ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_pieza(f) for f in filas]


def estado_pieza_por_publicacion(publicacion_ids: list[str]) -> dict[str, str]:
    """Estado de la PIEZA de feed por contenido: 'generando' | 'lista' (los ausentes = 'sin_pieza').

    Una pieza de feed es una fila `pieza` (el feed = esas filas unidas a su
    `contenido`). Por cada `publicacion_id` con AL MENOS una fila devuelve:
      - 'lista'      -> tiene >=1 fila con copy (`falta_copy=0`): sale REAL en el feed,
      - 'generando'  -> tiene fila(s) pero TODAS sin copy aún (`falta_copy=1`).
    Los ids SIN ninguna fila NO aparecen en el dict: el caller los trata como 'sin_pieza'
    (el tema se promovió pero no produjo pieza: dedup, sin redes, o copy aún por encolar).
    Batch (una sola query) para evitar N+1 al listar historias. PURA salvo I/O.
    """
    ids = [i for i in dict.fromkeys(publicacion_ids) if i]
    if not ids:
        return {}
    marcadores = ",".join("?" for _ in ids)
    sql = (
        "SELECT publicacion_id, MAX(CASE WHEN falta_copy = 0 THEN 1 ELSE 0 END) AS tiene_copy "
        f"FROM pieza WHERE publicacion_id IN ({marcadores}) GROUP BY publicacion_id"
    )
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(ids)).fetchall()
    finally:
        con.close()
    return {f["publicacion_id"]: ("lista" if f["tiene_copy"] else "generando") for f in filas}


def obtener_pieza_fila(pieza_id: str) -> dict[str, Any] | None:
    """Una fila por plataforma por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PIEZA} WHERE id = ?", (pieza_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_pieza(fila) if fila is not None else None


def actualizar_pieza_fila(
    pieza_id: str,
    campos: dict[str, Any],
    *,
    version_esperada: int | None = None,
) -> dict[str, Any] | None:
    """Edita parcialmente una fila por plataforma (estado/checklist/copy/...); None si no existe.

    CONCURRENCIA OPTIMISTA (ADR 0012): sube `version` en cada actualizacion y, si el llamante
    pasa `version_esperada` y otra escritura ya la adelanto, levanta `ConflictoVersion` (carrera
    pipeline↔humano) en vez de pisar. Sin `version_esperada` se conserva el last-write-wins.
    """
    cambios = {
        k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PIEZA
    }
    if not cambios:
        return obtener_pieza_fila(pieza_id)
    for col in _BOOLS_PIEZA:
        if col in cambios:
            cambios[col] = 1 if cambios[col] else 0
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    asignaciones.append("version = version + 1")
    params: list[Any] = [*cambios.values(), ahora, pieza_id]
    where = "WHERE id = ?"
    if version_esperada is not None:
        where += " AND version = ?"
        params.append(int(version_esperada))
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE pieza SET {', '.join(asignaciones)} {where}",  # noqa: S608 -- allowlist
            tuple(params),
        )
        if cur.rowcount == 0:
            con.rollback()
            if version_esperada is not None and obtener_pieza_fila(pieza_id) is not None:
                raise ConflictoVersion(
                    f"pieza {pieza_id}: version {version_esperada} obsoleta."
                )
            return None
        con.commit()
        fila = con.execute(
            f"{_SELECT_PIEZA} WHERE id = ?", (pieza_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_pieza(fila) if fila is not None else None


def borrar_pieza_fila(pieza_id: str) -> bool:
    """Borra una fila por plataforma; True si existia."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM pieza WHERE id = ?", (pieza_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()

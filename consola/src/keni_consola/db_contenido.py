"""Persistencia — dominio contenido. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    CLASE_CONTENIDO,
    ESTADOS_CONTENIDO,
    ESTADOS_CONTENIDO_PLATAFORMA,
    PRIORIDAD_CONTENIDO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_CONTENIDO_DEFECTO,
    TIPOS_CONTENIDO,
    Any,
    _conectar,
    datetime,
    redes,
    timedelta,
    uuid,
)

# --------------------------------------------------------------------------- #
# Tablero de CONTENIDO unificado (padre `contenido` + hijos `contenido_plataforma`)  #
# --------------------------------------------------------------------------- #

_COLS_CONTENIDO = (
    "id",
    "clase",
    "flujo",
    "titulo",
    "descripcion",
    "marca",
    "evento_id",
    "programa",
    "prioridad",
    "estado",
    "fecha_objetivo",
    "hora_objetivo",
    "fecha_entrega",
    "responsable_id",
    "responsable_nombre",
    "autor_id",
    "autor_nombre",
    "origen",
    "notas",
    "tipo_contenido",
    # FORMATO de la pieza (foto|video): decide a qué redes va (`redes.redes_de_formato`).
    "formato",
    "id_post_metricool",
    "senal_viralidad",
    # QA DE LA FUENTE (pre-copy): veredicto del cribado de la nota de origen antes de generar
    # copy. "no_verificado" (⚠️, OK para seguir, no verificado a fondo) o "problema" (❗, algo de
    # peso en contra: NO se generó copy). `qa_hallazgos` es el JSON estructurado de hallazgos.
    "qa_veredicto",
    "qa_hallazgos",
    # Parámetros de lanzamiento de copy PENDIENTE (JSON): el sweep guarda aquí, al crear el tema
    # en CI, lo que la fase CD necesitará para lanzar el copy (redes, imagen ya resuelta, fuente,
    # clave) SOLO si la QA de la fuente sale `no_verificado`. "" tras lanzar (o si no aplica).
    "copy_pendiente",
    # FECHA DE LA FUENTE (pipeline automático): pubDate/updated del item de origen (RSS/
    # noticia), normalizada a ISO UTC. La pieza la conserva para mostrar en la Consola
    # "Fuente del …" junto a "Generado el …" (`creado`). "" si la fuente no traía fecha o
    # si la pieza no nació del pipeline (alta manual).
    "fecha_fuente",
    # URL de la NOTA DE ORIGEN (Investigador F3): la URL de la fuente con que nació la pieza.
    # Permite el dedup por URL en `existe_publicado_similar` (cruza la url canónica contra lo
    # publicado) antes de caer al fuzzy de título. "" en alta manual o BD vieja.
    "url_fuente",
    "creado",
    "actualizado",
)
_SELECT_CONTENIDO = f"SELECT {', '.join(_COLS_CONTENIDO)} FROM contenido"

# Campos del padre editables via `actualizar_contenido` (lista blanca). `id`, `clase`,
# `autor_*`, `creado` y `actualizado` no son editables (el ultimo lo gestiona el sistema).
_CAMPOS_EDITABLES_CONTENIDO: tuple[str, ...] = (
    "flujo",
    "titulo",
    "descripcion",
    "marca",
    "evento_id",
    "programa",
    "prioridad",
    "estado",
    "fecha_objetivo",
    "hora_objetivo",
    "fecha_entrega",
    "responsable_id",
    "responsable_nombre",
    "origen",
    "notas",
    "tipo_contenido",
    # FORMATO de la pieza (foto|video): editable para poder pasar de foto a video más adelante.
    "formato",
    # Editable para que el flujo de publicación pueda fijar el id de Metricool a nivel
    # pieza cuando esté disponible (Item C); hoy se rellena solo si el publicador lo pasa.
    "id_post_metricool",
    # QA de la FUENTE: el sweep del pipeline persiste aquí el veredicto del cribado pre-copy
    # (`no_verificado`/`problema`) y sus hallazgos estructurados (JSON) sobre la nota de origen.
    "qa_veredicto",
    "qa_hallazgos",
    # Parámetros de lanzamiento de copy pendiente (JSON): editable para que el sweep lo fije al
    # crear el tema y lo limpie ("") tras lanzar el copy en la fase CD.
    "copy_pendiente",
    # URL de la nota de origen (Investigador F3): editable para poder rellenarla post-creación
    # cuando el pipeline resuelve la fuente de la pieza.
    "url_fuente",
)


def _fila_a_contenido(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `contenido` en un dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_CONTENIDO}
    item["estado"] = fila["estado"] or "pendiente"
    item["prioridad"] = fila["prioridad"] or PRIORIDAD_CONTENIDO_DEFECTO
    item["clase"] = fila["clase"] or CLASE_CONTENIDO
    # Señal de viralidad como int (Fase 5): defensivo ante NULL/no-numerico de bases viejas.
    try:
        item["senal_viralidad"] = int(fila["senal_viralidad"] or 0)
    except (TypeError, ValueError):
        item["senal_viralidad"] = 0
    return item


def _entero_no_negativo(valor: Any) -> int:
    """Entero >=0 desde un valor del llamante; 0 si no parsea o es negativo (defensivo)."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def crear_contenido(
    *,
    clase: str = CLASE_CONTENIDO,
    flujo: str = "",
    titulo: str = "",
    descripcion: str = "",
    marca: str = "",
    evento_id: str = "",
    programa: str = "",
    prioridad: str = PRIORIDAD_CONTENIDO_DEFECTO,
    estado: str = "pendiente",
    fecha_objetivo: str = "",
    hora_objetivo: str = "",
    fecha_entrega: str = "",
    autor: dict[str, str] | None = None,
    responsable: dict[str, str] | None = None,
    origen: str = "",
    notas: str = "",
    tipo_contenido: str = TIPO_CONTENIDO_DEFECTO,
    formato: str = redes.FORMATO_FOTO,
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
    """Inserta un item del tablero (padre) y lo devuelve. NO valida (lo hace la API).

    `clase` distingue un contenido publicable (con filas por plataforma) de una tarea libre
    del equipo (`tarea`, sin plataformas). `id`/`creado`/`actualizado` se pueden pasar para
    PRESERVAR identidad al migrar datos legados; si van vacios se generan.
    """
    autor = autor or {}
    responsable = responsable or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "clase": clase if clase in ("contenido", "tarea") else CLASE_CONTENIDO,
        "flujo": flujo or "",
        "titulo": titulo or "",
        "descripcion": descripcion or "",
        "marca": marca or "",
        "evento_id": evento_id or "",
        "programa": programa or "",
        "prioridad": prioridad if prioridad in PRIORIDADES_EVENTO else PRIORIDAD_CONTENIDO_DEFECTO,
        "estado": estado if estado in ESTADOS_CONTENIDO else "pendiente",
        "fecha_objetivo": fecha_objetivo or "",
        "hora_objetivo": hora_objetivo or "",
        "fecha_entrega": fecha_entrega or "",
        "responsable_id": responsable.get("id", "") or "",
        "responsable_nombre": responsable.get("usuario", "") or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "origen": origen or "",
        "notas": notas or "",
        "tipo_contenido": tipo_contenido if tipo_contenido in TIPOS_CONTENIDO else TIPO_CONTENIDO_DEFECTO,
        # FORMATO de la pieza (foto|video): decide las redes destino (`redes.redes_de_formato`).
        # Se normaliza (vacío/desconocido -> 'foto') para no persistir valores fuera de catálogo.
        "formato": redes.normalizar_formato(formato),
        # id de Metricool a nivel pieza (Item C): acceso directo opcional para el cruce
        # métricas↔contenido; el id real por red sigue en `contenido_plataforma`. Legado -> "".
        "id_post_metricool": id_post_metricool or "",
        # Señal de viralidad del Radar (Fase 5): >=0; defensivo ante valores no enteros.
        "senal_viralidad": _entero_no_negativo(senal_viralidad),
        # QA de la fuente (pre-copy): suele nacer "" (lo fija el sweep tras cribar la nota).
        "qa_veredicto": qa_veredicto or "",
        "qa_hallazgos": qa_hallazgos or "",
        "copy_pendiente": copy_pendiente or "",
        "fecha_fuente": fecha_fuente or "",
        # URL de la nota de origen (Investigador F3): la conserva la pieza para el dedup por URL.
        "url_fuente": url_fuente or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_CONTENIDO)
        con.execute(
            f"INSERT INTO contenido ({', '.join(_COLS_CONTENIDO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_CONTENIDO),
        )
        con.commit()
    finally:
        con.close()
    return fila


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
    """Items del tablero (padres), filtros combinables (AND). Orden estable.

    `desde`/`hasta` acotan por `fecha_objetivo` (ISO inclusivo). El resto filtran texto
    EXACTO. Sin filtros, devuelve el tablero completo del equipo.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    for col, val in (
        ("clase", clase),
        ("flujo", flujo),
        ("marca", marca),
        ("estado", estado),
    ):
        if val:
            clausulas.append(f"{col} = ?")
            params.append(val)
    if evento_id is not None:
        clausulas.append("evento_id = ?")
        params.append(evento_id)
    if responsable_id is not None:
        clausulas.append("responsable_id = ?")
        params.append(responsable_id)
    if desde:
        clausulas.append("fecha_objetivo >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("fecha_objetivo <= ?")
        params.append(hasta)
    sql = _SELECT_CONTENIDO
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    # Prioridad primero (alta antes que media/baja), luego por fecha objetivo y creacion.
    sql += (
        " ORDER BY CASE prioridad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,"
        " fecha_objetivo ASC, creado ASC, id ASC"
    )
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_contenido(f) for f in filas]


def titulos_recientes_marca(marca: str, desde_iso: str) -> list[str]:
    """Títulos del contenido (temas) de `marca` creados desde `desde_iso` (ISO inclusivo).

    Consulta ligera (solo `titulo`) para el dedup del pipeline: detectar que una noticia ya
    está en la cola o se creó/publicó hace poco. `clase='contenido'` excluye tareas. Acotada
    por `creado` (no `fecha_objetivo`): es "creado recientemente". Lista vacía si no hay.
    """
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT titulo FROM contenido "
            "WHERE marca = ? AND clase = 'contenido' AND creado >= ?",
            (marca, desde_iso),
        ).fetchall()
    finally:
        con.close()
    return [(f["titulo"] or "") for f in filas]


def contar_contenido_origen_desde(marca: str, origen: str, desde_iso: str) -> int:
    """Nº de items del tablero de `marca` con `origen` creados desde `desde_iso` (ISO inclusivo).

    Consulta de COUNT ligera para el tope diario del auto-feed: cuántas piezas `origen='autofeed'`
    se han creado hoy para una marca, para restarlo del cap. `clase='contenido'` excluye tareas.
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM contenido "
            "WHERE marca = ? AND origen = ? AND clase = 'contenido' AND creado >= ?",
            (marca, origen, desde_iso),
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def existe_publicado_similar(
    marca: str, titulo: str, url: str = "", *, umbral: float = 0.85
) -> bool:
    """True si `marca` ya PUBLICO algo equivalente al `titulo` (o `url`) dado.

    Best-effort (nunca rompe el flujo: ante cualquier error -> False):
      (a) por URL: si `url` no es vacia, cruza `dedup.url_canonica(url)` contra la `url_fuente`
          (canonizada) del contenido PUBLICADO de la marca (JOIN `contenido` x
          `contenido_plataforma`, ventana de 90 dias). Match exacto de URL canonica -> True
          (señal mas fuerte que el titulo: la MISMA fuente ya salio). Si no hay URL o no casa,
          cae a la rama (b).
      (b) por TITULO: trae los titulos del contenido de la marca con alguna plataforma en
          estado 'publicado' (JOIN `contenido` x `contenido_plataforma`), ventana de 90 dias,
          y aplica `dedup.es_similar` (exacto o fuzzy >= `umbral`).
    """
    from .dominio import dedup

    try:
        desde = (datetime.now() - timedelta(days=90)).isoformat(timespec="seconds")
        con = _conectar()
        try:
            # Rama (a) por URL: solo si traemos una url candidata. La url_fuente publicada se
            # canoniza en Python (mismo `dedup.url_canonica` que se usa al guardar la pieza),
            # para que el cruce sea robusto a variantes (querystring de tracking, etc.).
            url_canon = dedup.url_canonica(url) if url else ""
            if url_canon:
                filas_url = con.execute(
                    "SELECT DISTINCT c.url_fuente FROM contenido c "
                    "JOIN contenido_plataforma cp ON cp.contenido_id = c.id "
                    "WHERE c.marca = ? AND c.clase = 'contenido' "
                    "AND cp.estado = 'publicado' AND c.url_fuente <> '' AND c.creado >= ?",
                    (marca, desde),
                ).fetchall()
                publicadas = {
                    dedup.url_canonica(f["url_fuente"] or "") for f in filas_url
                }
                publicadas.discard("")
                if url_canon in publicadas:
                    return True
            # Rama (b): titulos del contenido de la marca con alguna plataforma 'publicado'.
            filas = con.execute(
                "SELECT DISTINCT c.titulo FROM contenido c "
                "JOIN contenido_plataforma cp ON cp.contenido_id = c.id "
                "WHERE c.marca = ? AND c.clase = 'contenido' "
                "AND cp.estado = 'publicado' AND c.creado >= ?",
                (marca, desde),
            ).fetchall()
        finally:
            con.close()
        titulos_norm = {dedup.clave(f["titulo"] or "") for f in filas}
        titulos_norm.discard("")
        return dedup.es_similar(titulo, titulos_norm, umbral=umbral)
    except Exception:  # noqa: BLE001 -- best-effort: el dedup nunca debe tumbar el pipeline
        return False


def obtener_contenido(contenido_id: str) -> dict[str, Any] | None:
    """Un item del tablero por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_CONTENIDO} WHERE id = ?", (contenido_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_contenido(fila) if fila is not None else None


def actualizar_contenido(
    contenido_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente un item; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_CONTENIDO}
    if not cambios:
        return obtener_contenido(contenido_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, contenido_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE contenido SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        # REASIGNACION DE MARCA: si cambia la marca del padre, hay que PROPAGARLA a la marca
        # denormalizada de sus filas por plataforma; si no, el indice unico de parrilla quedaria
        # mal-scope-ado (una pieza reasignada seguiria contando contra la marca vieja). Mismo
        # connection/commit que el UPDATE del padre -> atomico.
        if "marca" in cambios and cur.rowcount:
            con.execute(
                "UPDATE contenido_plataforma SET marca = ? WHERE contenido_id = ?",
                (cambios["marca"], contenido_id),
            )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_CONTENIDO} WHERE id = ?", (contenido_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_contenido(fila) if fila is not None else None


def borrar_contenido(contenido_id: str) -> bool:
    """Borra un item del tablero, SUS filas por plataforma y etiquetas (cascada). True si existia."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM contenido_plataforma WHERE contenido_id = ?", (contenido_id,)
        )
        con.execute(
            "DELETE FROM contenido_etiquetas WHERE contenido_id = ?", (contenido_id,)
        )
        cur = con.execute("DELETE FROM contenido WHERE id = ?", (contenido_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


_COLS_CONTENIDO_PLATAFORMA = (
    "id",
    "contenido_id",
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
    "veredicto",
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
    "qa_auto_hash",
    "hora_post",
    "creado",
    "actualizado",
)
_SELECT_CONTENIDO_PLATAFORMA = (
    f"SELECT {', '.join(_COLS_CONTENIDO_PLATAFORMA)} FROM contenido_plataforma"
)
_BOOLS_CONTENIDO_PLATAFORMA = (
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
# Campos editables de una fila por plataforma (lista blanca). `id`, `contenido_id`,
# `red`, `marca`, `es_publicacion`, `creado` y `actualizado` no se editan (los dos ultimos los
# gestiona el sistema; `es_publicacion` se fija al crear; `marca` es DENORMALIZADA del padre y
# solo la sincroniza el sistema —insert + reasignacion de marca del padre—, nunca el cliente).
_CAMPOS_EDITABLES_CONTENIDO_PLATAFORMA: tuple[str, ...] = tuple(
    c
    for c in _COLS_CONTENIDO_PLATAFORMA
    if c
    not in ("id", "contenido_id", "red", "marca", "es_publicacion", "creado", "actualizado")
)


def _fila_a_contenido_plataforma(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `contenido_plataforma` en dict (booleanos como bool)."""
    plat: dict[str, Any] = {col: fila[col] for col in _COLS_CONTENIDO_PLATAFORMA}
    for col in _BOOLS_CONTENIDO_PLATAFORMA:
        plat[col] = bool(fila[col])
    plat["estado"] = fila["estado"] or "pendiente"
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
        plat["imagen_url"] = f"/api/publicaciones/{plat['id']}/compuesta"
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
    """Inserta una fila por plataforma de un `contenido` y la devuelve. NO valida.

    El checklist `falta_copy`/`falta_imagen` se autodeduce de `copy`/`imagen` si no se pasa
    explicito (copy no vacio => no falta copy). `id`/`creado`/`actualizado` se pueden pasar
    para PRESERVAR identidad al migrar (p. ej. el id de una publicacion legada).

    `marca` (DENORMALIZADA del padre) se DERIVA del `contenido` padre cuando no se pasa (`None`):
    asi la mayoria de los ~12 call-sites no tiene que enredarse con ella y la denormalizacion
    sigue siempre correcta. Pasar `marca` explicito solo lo necesita la migracion (preservar la
    marca de datos legados) o un padre aun no commiteado en otra transaccion. Mantenerla en sync
    es lo que da sentido al indice unico de parrilla POR MARCA (`idx_parrilla_slot_uniq`).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    falta_copy = (not bool(copy)) if falta_copy is None else falta_copy
    falta_imagen = (not bool(imagen)) if falta_imagen is None else falta_imagen
    # `falta_video` (espejo de `falta_imagen`, pero con default INVERSO): cuando se pasa explicito
    # se respeta; cuando es None se asume 0 (N/A). El video solo es obligatorio en piezas
    # `formato='video'`; la creacion por defecto es `foto`, asi que `falta_video` nace en 0 y lo
    # activa quien sabe el formato (crear con `formato=video` o el flip `ajustar_plataformas_por_formato`).
    falta_video = False if falta_video is None else bool(falta_video)
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "contenido_id": contenido_id,
        "red": red,
        # Marca denormalizada: la del padre salvo override explicito. La derivacion real (lookup)
        # se hace abajo dentro de la conexion para que vea el padre ya commiteado.
        "marca": marca or "",
        "estado": estado if estado in ESTADOS_CONTENIDO_PLATAFORMA else "pendiente",
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
        "veredicto": veredicto or "",
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
        "qa_auto_hash": qa_auto_hash or "",
        "hora_post": hora_post or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        # Deriva la marca denormalizada del padre cuando el llamante no la pasa (el caso normal):
        # asi ningun call-site tiene que conocerla y la denormalizacion nace siempre alineada.
        if marca is None:
            padre = con.execute(
                "SELECT marca FROM contenido WHERE id = ?", (contenido_id,)
            ).fetchone()
            if padre is not None:
                fila["marca"] = padre["marca"] or ""
        marcadores = ", ".join("?" for _ in _COLS_CONTENIDO_PLATAFORMA)
        con.execute(
            f"INSERT INTO contenido_plataforma ({', '.join(_COLS_CONTENIDO_PLATAFORMA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_CONTENIDO_PLATAFORMA),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_contenido_plataforma(fila)


def listar_contenido_plataforma(
    contenido_id: str | None = None,
) -> list[dict[str, Any]]:
    """Filas por plataforma de un contenido (o de todos si `contenido_id` es None)."""
    sql = _SELECT_CONTENIDO_PLATAFORMA
    params: tuple[Any, ...] = ()
    if contenido_id is not None:
        sql += " WHERE contenido_id = ?"
        params = (contenido_id,)
    sql += " ORDER BY contenido_id ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_fila_a_contenido_plataforma(f) for f in filas]


def obtener_contenido_plataforma(plataforma_id: str) -> dict[str, Any] | None:
    """Una fila por plataforma por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_CONTENIDO_PLATAFORMA} WHERE id = ?", (plataforma_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_contenido_plataforma(fila) if fila is not None else None


def actualizar_contenido_plataforma(
    plataforma_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una fila por plataforma (estado/checklist/copy/...); None si no existe."""
    cambios = {
        k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_CONTENIDO_PLATAFORMA
    }
    if not cambios:
        return obtener_contenido_plataforma(plataforma_id)
    for col in _BOOLS_CONTENIDO_PLATAFORMA:
        if col in cambios:
            cambios[col] = 1 if cambios[col] else 0
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, plataforma_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE contenido_plataforma SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_CONTENIDO_PLATAFORMA} WHERE id = ?", (plataforma_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_contenido_plataforma(fila) if fila is not None else None


def borrar_contenido_plataforma(plataforma_id: str) -> bool:
    """Borra una fila por plataforma; True si existia."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM contenido_plataforma WHERE id = ?", (plataforma_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()



# --------------------------------------------------------------------------- #
# CONTENIDO editorial reutilizable migrado de FICHEROS a Postgres (ADR 0006)    #
# --------------------------------------------------------------------------- #
# Fuentes RSS (+ items vistos + salud), grupos de hashtags y franjas editoriales eran los
# ULTIMOS rezagados file-backed (YAML + indice SQLite de rutas absolutas). Su indice de
# rutas se desincronizaba al recrear contenedores (Fuentes RSS aparecia vacia). Aqui viven
# en Postgres (ADR 0004/0006). Los dicts devueltos CONSERVAN las mismas claves que la capa
# de ficheros para no romper `api/rss.py`/`hashtags.py`/`franjas.py` ni el frontend. db.py
# NO valida (lo hace la API); `?` lo traduce `motor_db` a `%s`.
















# --------------------------------------------------------------------------- #
# Etiquetas editoriales (campaña / vertical / tipo) y su N:M con `contenido`     #
# --------------------------------------------------------------------------- #
# Una etiqueta clasifica transversalmente las piezas del tablero. `marca = ''` =
# etiqueta GLOBAL. La capa API valida `clase`/`marca`/unicidad; db.py NO valida.

_COLS_ETIQUETA = (
    "id",
    "nombre",
    "clase",
    "marca",
    "color",
    "keywords",
    "activo",
    "ttl_dias",
    "es_evergreen",
    "creado",
    "actualizado",
)
_SELECT_ETIQUETA = f"SELECT {', '.join(_COLS_ETIQUETA)} FROM etiquetas"
_CAMPOS_EDITABLES_ETIQUETA: tuple[str, ...] = (
    "nombre",
    "clase",
    "marca",
    "color",
    "keywords",
    "activo",
    "ttl_dias",
    "es_evergreen",
)


def _fila_a_etiqueta(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `etiquetas` en dict (con `activo`/`es_evergreen` como bool)."""
    et: dict[str, Any] = {col: fila[col] for col in _COLS_ETIQUETA}
    et["activo"] = bool(fila["activo"])
    et["ttl_dias"] = int(fila["ttl_dias"] or 0)
    et["es_evergreen"] = bool(fila["es_evergreen"])
    return et


def crear_etiqueta(
    *,
    nombre: str,
    clase: str = "campania",
    marca: str = "",
    color: str = "",
    keywords: str = "",
    activo: bool = True,
    ttl_dias: int = 0,
    es_evergreen: bool = False,
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Inserta una etiqueta editorial y la devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "clase": clase or "campania",
        "marca": marca or "",
        "color": color or "",
        "keywords": keywords or "",
        "activo": 1 if activo else 0,
        "ttl_dias": max(0, int(ttl_dias or 0)),
        "es_evergreen": 1 if es_evergreen else 0,
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_ETIQUETA)
        con.execute(
            f"INSERT INTO etiquetas ({', '.join(_COLS_ETIQUETA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_ETIQUETA),
        )
        con.commit()
    finally:
        con.close()
    fila["activo"] = bool(fila["activo"])
    return fila


def listar_etiquetas(
    *, marca: str | None = None, clase: str | None = None, solo_activas: bool = False
) -> list[dict[str, Any]]:
    """Lista etiquetas. `marca`: incluye las de esa marca Y las globales (marca='').

    Sin `marca` devuelve TODAS (de cualquier marca). `solo_activas` excluye las ocultas.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if marca is not None:
        clausulas.append("(marca = ? OR marca = '')")
        params.append(marca)
    if clase:
        clausulas.append("clase = ?")
        params.append(clase)
    if solo_activas:
        clausulas.append("activo = 1")
    sql = _SELECT_ETIQUETA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY clase ASC, nombre ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_etiqueta(f) for f in filas]


def obtener_etiqueta(etiqueta_id: str) -> dict[str, Any] | None:
    """Una etiqueta por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_ETIQUETA} WHERE id = ?", (etiqueta_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_etiqueta(fila) if fila is not None else None


def existe_etiqueta_nombre(
    nombre: str, clase: str, marca: str, *, excluir_id: str = ""
) -> bool:
    """True si ya hay una etiqueta con ese (nombre, clase, marca) — unicidad case-insensitive."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_ETIQUETA} WHERE LOWER(nombre) = LOWER(?) AND clase = ? "
            "AND marca = ? AND id != ?",
            (nombre, clase, marca, excluir_id),
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def obtener_etiqueta_por_nombre(nombre: str, clase: str, marca: str) -> dict[str, Any] | None:
    """Devuelve la etiqueta por (nombre, clase, marca) — case-insensitive. None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_ETIQUETA} WHERE LOWER(nombre) = LOWER(?) AND clase = ? AND marca = ?",
            (nombre, clase, marca),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_etiqueta(fila) if fila is not None else None


def actualizar_etiqueta(
    etiqueta_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una etiqueta; None si no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_ETIQUETA}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if "es_evergreen" in cambios:
        cambios["es_evergreen"] = 1 if cambios["es_evergreen"] else 0
    if "ttl_dias" in cambios:
        cambios["ttl_dias"] = max(0, int(cambios["ttl_dias"] or 0))
    if not cambios:
        return obtener_etiqueta(etiqueta_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, etiqueta_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE etiquetas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_ETIQUETA} WHERE id = ?", (etiqueta_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_etiqueta(fila) if fila is not None else None


def borrar_etiqueta(etiqueta_id: str) -> bool:
    """Borra una etiqueta y todas SUS asignaciones (cascada). True si existia."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM contenido_etiquetas WHERE etiqueta_id = ?", (etiqueta_id,)
        )
        cur = con.execute("DELETE FROM etiquetas WHERE id = ?", (etiqueta_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()

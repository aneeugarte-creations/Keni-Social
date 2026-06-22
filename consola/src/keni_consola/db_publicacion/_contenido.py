"""Persistencia — contenido (padre `contenido`). Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

import logging

from .._db_comun import (
    CLASE_CONTENIDO,
    ESTADOS_PUBLICACION,
    PRIORIDAD_CONTENIDO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_CONTENIDO_DEFECTO,
    TIPOS_CONTENIDO,
    UTC,
    Any,
    _conectar,
    ahora_iso,
    datetime,
    redes,
    timedelta,
    uuid,
)
from ..tiempo import iso_o_vacio, iso_utc

__all__ = [
    "ConflictoVersion",
    "_COLS_PUBLICACION",
    "_SELECT_PUBLICACION",
    "_CAMPOS_EDITABLES_CONTENIDO",
    "_fila_a_publicacion",
    "_entero_no_negativo",
    "crear_publicacion",
    "listar_publicacion",
    "titulos_recientes_marca",
    "contar_publicacion_origen_desde",
    "resumen_plan_por_categoria",
    "existe_publicado_similar",
    "publicados_marca_cache",
    "existe_publicado_similar_en_cache",
    "obtener_publicacion",
    "actualizar_publicacion",
    "borrar_publicacion",
]

_log = logging.getLogger("keni_consola.db_publicacion.contenido")

# --------------------------------------------------------------------------- #
# Tablero de CONTENIDO unificado (padre `contenido` + hijos `pieza`)  #
# --------------------------------------------------------------------------- #


class ConflictoVersion(Exception):
    """Una actualizacion optimista llego con una `version` OBSOLETA (carrera detectada).

    La levanta `actualizar_publicacion`/`actualizar_pieza_fila` cuando el llamante pasa
    `version_esperada` y otra escritura ya adelanto el contador `version` de la fila: en vez de
    PISAR ese cambio (last-write-wins), se aborta de forma controlada para que la capa API lo
    traduzca a un 409 ("el contenido cambio mientras lo editabas; recarga"). Asi el AVANCE del
    pipeline no sobrescribe una decision humana (ni viceversa). Ver ADR 0012.
    """


_COLS_PUBLICACION = (
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
    # CATEGORÍA del plan editorial con la que nació ('' = sin línea / alta manual). Copiada
    # de la historia al promover ('breaking' si lo era) o 'evergreen' al reciclar; estable
    # frente al GC del pool. La consumen el conteo del plan y los horarios por categoría.
    "categoria",
    # MACRO-EVENTO de la pieza (copiado del cluster al promover). `tema_macro` = gran
    # acontecimiento ("Mundial 2026"); `subtema` = faceta coherente dentro de él ("partidos").
    # Gobiernan la cadencia por evento; "" = la pieza no pertenece a ningún macro-evento.
    "tema_macro",
    "subtema",
    "tipo_contenido",
    # FORMATO de la pieza (foto|video): decide a qué redes va (`redes.redes_de_formato`).
    "formato",
    "id_post_metricool",
    "senal_viralidad",
    # verificación DE LA FUENTE (pre-copy): veredicto de la nota de origen antes de generar copy.
    # "verificado" (✅), "requiere_humano" (⚠️, a la mesa) o "rechazado" (❗, NO se generó copy).
    # `verificar_hallazgos` es el JSON estructurado de hallazgos.
    "verificacion_fuente",
    "verificar_hallazgos",
    # Parámetros de lanzamiento de copy PENDIENTE (JSON): el sweep guarda aquí, al crear el tema
    # en CI, lo que la fase CD necesitará para lanzar el copy (redes, imagen ya resuelta, fuente,
    # clave) SOLO si la verificación de la fuente sale `no_verificado`. "" tras lanzar (o si no aplica).
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
    # NOMBRE legible del MEDIO de origen ("Récord"…): copiado en la promoción CI (el cluster
    # puede borrarlo el GC). "" en alta manual o BD vieja (la UI deriva el dominio de
    # `url_fuente` como fallback).
    "fuente_nombre",
    "creado",
    "actualizado",
    # CONCURRENCIA OPTIMISTA (ADR 0012): contador que sube en cada `actualizar_publicacion`.
    "version",
)
_SELECT_PUBLICACION = f"SELECT {', '.join(_COLS_PUBLICACION)} FROM publicacion"

# Campos del padre editables via `actualizar_publicacion` (lista blanca). `id`, `clase`,
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
    # CATEGORÍA del plan editorial con la que nació ('' = sin línea / alta manual). Copiada
    # de la historia al promover ('breaking' si lo era) o 'evergreen' al reciclar; estable
    # frente al GC del pool. La consumen el conteo del plan y los horarios por categoría.
    "categoria",
    "tipo_contenido",
    # FORMATO de la pieza (foto|video): editable para poder pasar de foto a video más adelante.
    "formato",
    # Editable para que el flujo de publicación pueda fijar el id de Metricool a nivel
    # pieza cuando esté disponible (Item C); hoy se rellena solo si el publicador lo pasa.
    "id_post_metricool",
    # verificación de la FUENTE: el sweep del pipeline persiste aquí el verificacion del verificado pre-copy
    # (`no_verificado`/`problema`) y sus hallazgos estructurados (JSON) sobre la nota de origen.
    "verificacion_fuente",
    "verificar_hallazgos",
    # Parámetros de lanzamiento de copy pendiente (JSON): editable para que el sweep lo fije al
    # crear el tema y lo limpie ("") tras lanzar el copy en la fase CD.
    "copy_pendiente",
    # URL de la nota de origen (Investigador F3): editable para poder rellenarla post-creación
    # cuando el pipeline resuelve la fuente de la pieza. `fuente_nombre` es su par legible (el
    # medio): se rellena en el mismo momento y alimenta el filtro de limpieza `?fuente=`.
    "url_fuente",
    "fuente_nombre",
)


def _fila_a_publicacion(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `contenido` en un dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_PUBLICACION}
    # `creado`/`actualizado` son timestamptz (migracion 0033): se re-emiten al canon ISO
    # (string), que es lo que consumen Pieza/API y el cursor del keyset del feed.
    item["creado"] = iso_o_vacio(fila["creado"])
    item["actualizado"] = iso_o_vacio(fila["actualizado"])
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


def crear_publicacion(
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
    categoria: str = "",
    tema_macro: str = "",
    subtema: str = "",
    tipo_contenido: str = TIPO_CONTENIDO_DEFECTO,
    formato: str = redes.FORMATO_FOTO,
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
    """Inserta un item del tablero (padre) y lo devuelve. NO valida (lo hace la API).

    `clase` distingue un contenido publicable (con filas por plataforma) de una tarea libre
    del equipo (`tarea`, sin plataformas). `id`/`creado`/`actualizado` se pueden pasar para
    PRESERVAR identidad al migrar datos legados; si van vacios se generan.

    El nucleo (construir fila + INSERT sin commit) vive en `_fila_publicacion_nueva` /
    `_insertar_publicacion`, reutilizables por los lotes transaccionales (todo-o-nada).
    """
    fila = _fila_publicacion_nueva(
        clase=clase, flujo=flujo, titulo=titulo, descripcion=descripcion, marca=marca,
        evento_id=evento_id, programa=programa, prioridad=prioridad, estado=estado,
        fecha_objetivo=fecha_objetivo, hora_objetivo=hora_objetivo,
        fecha_entrega=fecha_entrega, autor=autor, responsable=responsable, origen=origen,
        notas=notas, categoria=categoria, tema_macro=tema_macro, subtema=subtema,
        tipo_contenido=tipo_contenido, formato=formato,
        id_post_metricool=id_post_metricool, senal_viralidad=senal_viralidad,
        verificacion_fuente=verificacion_fuente, verificar_hallazgos=verificar_hallazgos,
        copy_pendiente=copy_pendiente, fecha_fuente=fecha_fuente, url_fuente=url_fuente,
        fuente_nombre=fuente_nombre, creado=creado, actualizado=actualizado, id=id,
    )
    con = _conectar()
    try:
        _insertar_publicacion(con, fila)
        con.commit()
    finally:
        con.close()
    return fila


def _fila_publicacion_nueva(**campos: Any) -> dict[str, Any]:
    """Construye la fila NORMALIZADA de un `contenido` nuevo (defaults + allowlists).

    Nucleo puro de `crear_publicacion` (mismos kwargs y misma normalizacion), separado para
    que los lotes transaccionales construyan filas sin insertar. No toca la BD.
    """
    autor = campos.get("autor") or {}
    responsable = campos.get("responsable") or {}
    ahora = ahora_iso()
    clase = campos.get("clase") or CLASE_CONTENIDO
    prioridad = campos.get("prioridad") or PRIORIDAD_CONTENIDO_DEFECTO
    estado = campos.get("estado") or "pendiente"
    tipo_contenido = campos.get("tipo_contenido") or TIPO_CONTENIDO_DEFECTO
    return {
        "id": campos.get("id") or uuid.uuid4().hex[:12],
        "clase": clase if clase in ("contenido", "tarea") else CLASE_CONTENIDO,
        "flujo": campos.get("flujo") or "",
        "titulo": campos.get("titulo") or "",
        "descripcion": campos.get("descripcion") or "",
        "marca": campos.get("marca") or "",
        "evento_id": campos.get("evento_id") or "",
        "programa": campos.get("programa") or "",
        "prioridad": prioridad if prioridad in PRIORIDADES_EVENTO else PRIORIDAD_CONTENIDO_DEFECTO,
        "estado": estado if estado in ESTADOS_PUBLICACION else "pendiente",
        "fecha_objetivo": campos.get("fecha_objetivo") or "",
        "hora_objetivo": campos.get("hora_objetivo") or "",
        "fecha_entrega": campos.get("fecha_entrega") or "",
        "responsable_id": responsable.get("id", "") or "",
        "responsable_nombre": responsable.get("usuario", "") or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "origen": campos.get("origen") or "",
        "notas": campos.get("notas") or "",
        # LÍNEA del plan: la explícita o, si nace EVERGREEN (banco/taller/alta manual con ese
        # flujo), su propia línea 'evergreen' — cualquier camino de creación cuenta en el plan.
        "categoria": (campos.get("categoria") or "").strip().lower()
        or ("evergreen" if (campos.get("flujo") or "") == "evergreen" else ""),
        # MACRO-EVENTO copiado del cluster al promover ('' = ninguno). Gobierna la cadencia/día.
        "tema_macro": (campos.get("tema_macro") or "").strip(),
        "subtema": (campos.get("subtema") or "").strip(),
        "tipo_contenido": tipo_contenido if tipo_contenido in TIPOS_CONTENIDO else TIPO_CONTENIDO_DEFECTO,
        # FORMATO de la pieza (foto|video): decide las redes destino (`redes.redes_de_formato`).
        # Se normaliza (vacío/desconocido -> 'foto') para no persistir valores fuera de catálogo.
        "formato": redes.normalizar_formato(campos.get("formato") or redes.FORMATO_FOTO),
        # id de Metricool a nivel pieza (Item C): acceso directo opcional para el cruce
        # métricas↔contenido; el id real por red sigue en `pieza`. Legado -> "".
        "id_post_metricool": campos.get("id_post_metricool") or "",
        # Señal de viralidad del Radar (Fase 5): >=0; defensivo ante valores no enteros.
        "senal_viralidad": _entero_no_negativo(campos.get("senal_viralidad") or 0),
        # verificación de la fuente (pre-copy): suele nacer "" (lo fija el sweep tras verificar la nota).
        "verificacion_fuente": campos.get("verificacion_fuente") or "",
        "verificar_hallazgos": campos.get("verificar_hallazgos") or "",
        "copy_pendiente": campos.get("copy_pendiente") or "",
        "fecha_fuente": campos.get("fecha_fuente") or "",
        # URL de la nota de origen (Investigador F3): la conserva la pieza para el dedup por URL.
        "url_fuente": campos.get("url_fuente") or "",
        # Nombre legible del medio de origen (copiado en la promoción CI; "" en alta manual).
        "fuente_nombre": campos.get("fuente_nombre") or "",
        "creado": campos.get("creado") or ahora,
        "actualizado": campos.get("actualizado") or ahora,
        # Concurrencia optimista (ADR 0012): nace en 0 y lo sube cada `actualizar_publicacion`.
        "version": 0,
    }


def _insertar_publicacion(con: Any, fila: dict[str, Any]) -> None:
    """INSERT de una fila YA construida de `contenido` sobre `con` (SIN commit).

    Extraido de `crear_publicacion` para que un lote (p. ej. `crear_publicaciones`,
    todo-o-nada) inserte varios padres EN UNA SOLA transaccion del llamante.
    """
    marcadores = ", ".join("?" for _ in _COLS_PUBLICACION)
    con.execute(
        f"INSERT INTO publicacion ({', '.join(_COLS_PUBLICACION)}) VALUES ({marcadores})",
        tuple(fila[col] for col in _COLS_PUBLICACION),
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
    """Items del tablero (padres), filtros combinables (AND). Orden estable.

    `desde`/`hasta` acotan por `fecha_objetivo` (ISO inclusivo). `creado_desde` acota por
    `creado` (ISO inclusivo): la JORNADA del día pide solo lo creado desde su inicio en vez de
    traer el histórico y filtrarlo en memoria. El resto filtran texto EXACTO. Sin filtros,
    devuelve el tablero completo del equipo.
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
    if creado_desde:
        clausulas.append("creado >= ?")
        params.append(creado_desde)
    sql = _SELECT_PUBLICACION
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
    return [_fila_a_publicacion(f) for f in filas]


def listar_publicaciones_origenes(
    origenes: list[str], *, excluir_estado: str | None = None
) -> list[dict[str, Any]]:
    """Items del tablero (clase 'contenido') cuyo `origen` esta en `origenes`. Orden estable.

    Variante con el WHERE empujado a SQL para los barridos del pipeline (antes recorrian
    `listar_publicacion()` COMPLETO y filtraban en Python en cada barrido). `excluir_estado`
    (p. ej. 'hecha') descarta los cerrados ya en la query. Mismo orden que `listar_publicacion`.
    """
    origenes = [o for o in origenes if o]
    if not origenes:
        return []
    marcadores = ",".join("?" for _ in origenes)
    sql = (
        f"{_SELECT_PUBLICACION} WHERE clase = 'contenido' AND origen IN ({marcadores})"
    )
    params: list[Any] = list(origenes)
    if excluir_estado:
        sql += " AND estado <> ?"
        params.append(excluir_estado)
    sql += (
        " ORDER BY CASE prioridad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,"
        " fecha_objetivo ASC, creado ASC, id ASC"
    )
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_publicacion(f) for f in filas]


def ids_publicacion_con_copy(marca: str | None = None) -> set[str]:
    """Ids de `contenido` con AL MENOS una pieza por plataforma con copy redactado.

    Variante agregada para el gate serial del pipeline (`temas_en_proceso`): antes se traia la
    tabla `pieza` ENTERA por cada marca y barrido y se filtraba en Python.
    Con `marca`, el JOIN acota a los temas de esa marca. Mismo criterio que el filtro previo
    en Python: `copy` no vacio (texto redactado, no solo la fila placeholder).
    """
    if marca:
        sql = (
            "SELECT DISTINCT cp.publicacion_id AS cid FROM pieza cp "
            "JOIN publicacion c ON c.id = cp.publicacion_id "
            "WHERE c.marca = ? AND cp.copy <> ''"
        )
        params: tuple[Any, ...] = (marca,)
    else:
        sql = (
            "SELECT DISTINCT publicacion_id AS cid FROM pieza WHERE copy <> ''"
        )
        params = ()
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return {f["cid"] for f in filas if f["cid"]}


def verificacion_fuente_por_publicacion(publicacion_ids: list[str]) -> dict[str, str]:
    """Verificacion de la fuente (verificación de fuente) por `publicacion_id`, en LOTE (sin N+1).

    El verificación corre sobre `contenido` (no sobre el cluster), así que la Mesa de Investigación lo
    trae por el `publicacion_id` de cada historia para mostrar «verificada / problema». `{}` si
    no hay ids; cada id sin fila o con verificacion vacío no aparece (el llamante cae a '').
    """
    ids = [i for i in dict.fromkeys(publicacion_ids) if i]
    if not ids:
        return {}
    marcadores = ",".join("?" for _ in ids)
    con = _conectar()
    try:
        filas = con.execute(
            f"SELECT id, verificacion_fuente FROM publicacion WHERE id IN ({marcadores})",  # noqa: S608 -- marcadores
            tuple(ids),
        ).fetchall()
    finally:
        con.close()
    return {f["id"]: (f["verificacion_fuente"] or "") for f in filas if (f["verificacion_fuente"] or "")}


def reparar_verificacion_en_curso_sueltos(umbral_iso: str) -> int:
    """Devuelve a re-verificación (verificacion_fuente='') los temas COLGADOS en 'en_curso' mas viejos que `umbral_iso`.

    Limpieza del recolector: la fase verificación marca el tema `en_curso` antes de lanzar la verificación; si
    la generacion muere sin finalizador, el sentinel quedaba para siempre (tema excluido de
    sin re-verificar y contando en `temas_en_proceso`). Compara contra `actualizado` (lo refresca
    cada escritura, incluida la que puso `en_curso`): un `en_curso` legitimo y reciente NUNCA
    se toca (el umbral es muy superior al timeout de la verificación). Devuelve cuantos reseteo.
    """
    con = _conectar()
    try:
        cur = con.execute(
            # `actualizado` es timestamptz (migracion 0033): `IS NOT NULL` sustituye al viejo
            # `<> ''` (el repo siempre lo escribe, asi que en la practica nunca es NULL); el
            # `< ?` compara nativo contra el umbral ISO (casteado a timestamptz).
            "UPDATE publicacion SET verificacion_fuente = '' "
            "WHERE verificacion_fuente = 'en_curso' AND actualizado IS NOT NULL AND actualizado < ?",
            (umbral_iso,),
        )
        con.commit()
        return int(cur.rowcount or 0)
    finally:
        con.close()


def titulos_recientes_marca(marca: str, desde_iso: str) -> list[str]:
    """Títulos del contenido (temas) de `marca` creados desde `desde_iso` (ISO inclusivo).

    Consulta ligera (solo `titulo`) para el dedup del pipeline: detectar que una noticia ya
    está en la cola o se creó/publicó hace poco. `clase='contenido'` excluye tareas. Acotada
    por `creado` (no `fecha_objetivo`): es "creado recientemente". Lista vacía si no hay.
    """
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT titulo FROM publicacion "
            "WHERE marca = ? AND clase = 'contenido' AND creado >= ?",
            (marca, desde_iso),
        ).fetchall()
    finally:
        con.close()
    return [(f["titulo"] or "") for f in filas]


def resumen_plan_por_categoria(marca: str, desde_iso: str) -> dict[str, dict[str, int]]:
    """GENERADOS y PUBLICADOS por LÍNEA del plan desde `desde_iso`: {cat: {generados, publicados}}.

    Cuenta el `contenido` de la marca con `categoria` propia (nacido de una historia del plan
    o del reciclaje evergreen; '' = alta manual, fuera del plan) creado en la ventana Y que
    tenga AL MENOS UNA pieza por red (`pieza`): un tema SIN ninguna pieza
    —promovido pero con el copy aún sin generar, o ya fallido/borrado— NO infla el plan (de
    ahí que borrar el último post baje el contador y que un tema colgado sin piezas no cuente).
    Se exige «≥1 pieza», NO «es_publicacion=1», a propósito: las reemisiones evergreen del
    banco nacen con piezas `es_publicacion=0` y deben seguir contando (si no, el barrido
    evergreen reemitiría sin fin al ver el cupo vacío).
    PUBLICADOS = de esos, cuántos tienen ya alguna pieza por red en estado 'publicado'.
    Es el contador del plan diario: lo leen la admisión (cupos restantes) y el monitor
    («generados · publicados / objetivo»). `clase='contenido'` excluye tareas.
    """
    con = _conectar()
    try:
        # `cat`: la categoría persistida o, como red de seguridad para filas anteriores a la
        # normalización (o de escritores externos), 'evergreen' derivada del flujo.
        filas = con.execute(
            "SELECT CASE WHEN c.categoria <> '' THEN c.categoria ELSE 'evergreen' END AS cat, "
            "COUNT(*) AS generados, "
            "SUM(CASE WHEN EXISTS (SELECT 1 FROM pieza p "
            "WHERE p.publicacion_id = c.id AND p.estado = 'publicado') THEN 1 ELSE 0 END) "
            "AS publicados "
            "FROM publicacion c "
            "WHERE c.marca = ? AND c.clase = 'contenido' "
            "AND (c.categoria <> '' OR c.flujo = 'evergreen') "
            # Solo temas con contenido REAL: al menos una pieza por red (no el tema colgado
            # promovido cuyo copy nunca se generó). NO se filtra por es_publicacion: las
            # reemisiones evergreen del banco nacen con es_publicacion=0 y deben contar.
            "AND EXISTS (SELECT 1 FROM pieza p "
            "WHERE p.publicacion_id = c.id) "
            "AND c.creado >= ? GROUP BY 1",
            (marca, desde_iso),
        ).fetchall()
    finally:
        con.close()
    return {
        str(f["cat"]): {"generados": int(f["generados"]), "publicados": int(f["publicados"] or 0)}
        for f in filas
    }


def contar_publicacion_origen_desde(marca: str, origen: str, desde_iso: str) -> int:
    """Nº de items del tablero de `marca` con `origen` creados desde `desde_iso` (ISO inclusivo).

    Consulta de COUNT ligera para el tope diario del auto-feed: cuántas piezas `origen='autofeed'`
    se han creado hoy para una marca, para restarlo del cap. `clase='contenido'` excluye tareas.
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM publicacion "
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
          `pieza`, ventana de 90 dias). Match exacto de URL canonica -> True
          (señal mas fuerte que el titulo: la MISMA fuente ya salio). Si no hay URL o no casa,
          cae a la rama (b).
      (b) por TITULO: trae los titulos del contenido de la marca con alguna plataforma en
          estado 'publicado' (JOIN `contenido` x `pieza`), ventana de 90 dias,
          y aplica `dedup.es_similar` (exacto o fuzzy >= `umbral`).
    """
    try:
        cache = publicados_marca_cache(marca)
        return existe_publicado_similar_en_cache(cache, titulo, url, umbral=umbral)
    except Exception:  # noqa: BLE001 -- best-effort: el dedup nunca debe tumbar el pipeline
        # El dedup se desactiva (devuelve False) si la BD falla; lo registramos para que
        # esa degradacion silenciosa sea observable (no cambia el flujo de retorno).
        _log.warning("existe_publicado_similar falló para marca %s; se omite el dedup.", marca)
        return False


def publicados_marca_cache(marca: str) -> dict[str, Any]:
    """Snapshot REUTILIZABLE de lo publicado por `marca` (90 dias) para el dedup de un barrido.

    `existe_publicado_similar` traia TODOS los titulos/urls publicados de la marca POR CADA
    candidato del barrido (N candidatos x lectura completa). Con este snapshot el llamante
    del pipeline lee UNA vez por marca y cruza N candidatos contra el mismo set via
    `existe_publicado_similar_en_cache`. Forma: `{"urls": set[str], "titulos": set[str]}`
    (urls canonizadas con `dedup.url_canonica`; titulos como claves de `dedup.clave`).
    Puede LANZAR (no es best-effort): el llamante decide como degradar.
    """
    from ..dominio import dedup

    # Ventana de 90 dias en el canon UTC-sin-offset (los `creado` comparados son naive-UTC).
    desde = iso_utc(datetime.now(UTC) - timedelta(days=90))
    con = _conectar()
    try:
        filas_url = con.execute(
            "SELECT DISTINCT c.url_fuente FROM publicacion c "
            "JOIN pieza cp ON cp.publicacion_id = c.id "
            "WHERE c.marca = ? AND c.clase = 'contenido' "
            "AND cp.estado = 'publicado' AND c.url_fuente <> '' AND c.creado >= ?",
            (marca, desde),
        ).fetchall()
        filas = con.execute(
            "SELECT DISTINCT c.titulo FROM publicacion c "
            "JOIN pieza cp ON cp.publicacion_id = c.id "
            "WHERE c.marca = ? AND c.clase = 'contenido' "
            "AND cp.estado = 'publicado' AND c.creado >= ?",
            (marca, desde),
        ).fetchall()
    finally:
        con.close()
    urls = {dedup.url_canonica(f["url_fuente"] or "") for f in filas_url}
    urls.discard("")
    titulos = {dedup.clave(f["titulo"] or "") for f in filas}
    titulos.discard("")
    return {"urls": urls, "titulos": titulos}


def existe_publicado_similar_en_cache(
    cache: dict[str, Any], titulo: str, url: str = "", *, umbral: float = 0.85
) -> bool:
    """`existe_publicado_similar` contra un snapshot de `publicados_marca_cache` (sin BD).

    Misma semantica que la funcion original: (a) match exacto de URL canonica (señal mas
    fuerte: la MISMA fuente ya salio) y si no, (b) titulo exacto/fuzzy >= `umbral`. PURA:
    no toca la base, asi el barrido cruza N candidatos contra UNA lectura por marca.
    """
    from ..dominio import dedup

    url_canon = dedup.url_canonica(url) if url else ""
    if url_canon and url_canon in (cache.get("urls") or set()):
        return True
    return dedup.es_similar(titulo, cache.get("titulos") or set(), umbral=umbral)


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    """Un item del tablero por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PUBLICACION} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_publicacion(fila) if fila is not None else None


def actualizar_publicacion(
    publicacion_id: str,
    campos: dict[str, Any],
    *,
    version_esperada: int | None = None,
) -> dict[str, Any] | None:
    """Edita parcialmente un item; None si el id no existe. Filtra a la lista blanca.

    CONCURRENCIA OPTIMISTA (ADR 0012): cada actualizacion SUBE `version` (contador de la fila).
    Si el llamante pasa `version_esperada` (la `version` que leyo) y otra escritura ya adelanto
    el contador, el UPDATE condicional `... AND version = ?` no aplica y se levanta
    `ConflictoVersion` en vez de pisar el cambio (carrera pipeline↔humano). Sin `version_esperada`
    (por defecto) se conserva el comportamiento last-write-wins, pero el contador sube igual, de
    modo que un editor que SI lo pase detecte el cambio.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_CONTENIDO}
    if not cambios:
        return obtener_publicacion(publicacion_id)
    # Una pieza CONVERTIDA a evergreen adopta su línea del plan (si no trae una explícita y
    # no tenía ya otra): el conteo y los horarios por categoría la ven igual que una nacida
    # evergreen. No se pisa una categoría existente (p. ej. una mx reconvertida conserva mx).
    if cambios.get("flujo") == "evergreen" and "categoria" not in cambios:
        actual = obtener_publicacion(publicacion_id)
        if actual is not None and not (actual.get("categoria") or ""):
            cambios["categoria"] = "evergreen"
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    asignaciones.append("version = version + 1")  # sube SIEMPRE (token de concurrencia optimista)
    params: list[Any] = [*cambios.values(), ahora, publicacion_id]
    where = "WHERE id = ?"
    if version_esperada is not None:
        where += " AND version = ?"
        params.append(int(version_esperada))
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE publicacion SET {', '.join(asignaciones)} {where}",  # noqa: S608 -- allowlist
            tuple(params),
        )
        if cur.rowcount == 0:
            # No aplico: o el id no existe, o (con version_esperada) la version era obsoleta.
            con.rollback()
            if version_esperada is not None and obtener_publicacion(publicacion_id) is not None:
                raise ConflictoVersion(
                    f"contenido {publicacion_id}: version {version_esperada} obsoleta."
                )
            return None
        # REASIGNACION DE MARCA: si cambia la marca del padre, hay que PROPAGARLA a la marca
        # denormalizada de sus filas por plataforma; si no, el indice unico de parrilla quedaria
        # mal-scope-ado (una pieza reasignada seguiria contando contra la marca vieja). Mismo
        # connection/commit que el UPDATE del padre -> atomico.
        if "marca" in cambios:
            con.execute(
                "UPDATE pieza SET marca = ? WHERE publicacion_id = ?",
                (cambios["marca"], publicacion_id),
            )
        con.commit()
        fila = con.execute(
            f"{_SELECT_PUBLICACION} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_publicacion(fila) if fila is not None else None


def reclamar_publicacion(
    publicacion_id: str, *, responsable_id: str, responsable_nombre: str
) -> dict[str, Any] | None:
    """Asigna el contenido a un responsable SOLO si está LIBRE (claim atómico = "coger").

    `UPDATE ... WHERE id=? AND responsable_id=''` es un compare-and-set sobre una sola fila: si
    otra persona ya lo cogió, `rowcount==0` y devolvemos None (NO se pisa al primero, a
    diferencia del last-write-wins de `actualizar_publicacion`). El llamador distingue "ya cogido"
    de "no existe" releyendo con `obtener_publicacion`. Mismo patrón que `reclamar_job` de la cola.
    Devuelve el contenido ya asignado, o None si no se pudo reclamar.
    """
    ahora = ahora_iso()
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE publicacion SET responsable_id = ?, responsable_nombre = ?, actualizado = ? "
            "WHERE id = ? AND responsable_id = ''",
            (responsable_id, responsable_nombre, ahora, publicacion_id),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_PUBLICACION} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_publicacion(fila) if fila is not None else None


def borrar_publicacion(publicacion_id: str) -> bool:
    """Borra un item del tablero, SUS filas por plataforma y etiquetas (cascada). True si existia."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM pieza WHERE publicacion_id = ?", (publicacion_id,)
        )
        con.execute(
            "DELETE FROM publicacion_etiquetas WHERE publicacion_id = ?", (publicacion_id,)
        )
        cur = con.execute("DELETE FROM publicacion WHERE id = ?", (publicacion_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()

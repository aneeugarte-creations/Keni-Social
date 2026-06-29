"""Persistencia — dominio metricas. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
    config,
    datetime,
    iso_o_vacio,
    iso_utc,
    json,
    timedelta,
    uuid,
)
from ._db_json import a_json_dict

# --- Tope de puntos de las series temporales (Item: límite/downsampling) ----- #
# Las series de métricas (`serie_pieza`,
# `listar_snapshots_piezas`) alimentan gráficas; con meses de snapshots cada 4 h crecerían sin
# cota. Tope por DEFECTO de puntos devueltos, configurable por `KENI_METRICAS_SERIE_MAX` (entero;
# mín 2 para que siempre quepa una recta). DECISIÓN: cuando la serie excede el tope, se devuelven
# los ÚLTIMOS N puntos (los más recientes), NO un muestreo: así el ÚLTIMO punto —el dato actual,
# el que la UI rotula y del que cuelga la "velocidad"— SIEMPRE entra, y la curva queda visualmente
# correcta en su intervalo reciente (el más relevante para decisiones). Se implementa como
# `ORDER BY ts DESC LIMIT N` y luego se reinvierte a ASC (orden de graficado). `limite=None`
# (cap por defecto) vs `limite<=0` (SIN tope, serie COMPLETA: ruta para análisis/exportación que
# necesite todo el histórico, p. ej. la limpieza o un reporte agregado).
_METRICAS_SERIE_MAX_DEF = 500


def _tope_serie_metricas(limite: int | None) -> int | None:
    """Resuelve el tope efectivo de puntos de una serie.

    - `limite is None`  -> cap por defecto (`KENI_METRICAS_SERIE_MAX`, def 500, mín 2).
    - `limite <= 0`     -> None (SIN tope: serie completa, para callers que la necesiten).
    - `limite > 0`      -> ese tope explícito.
    """
    if limite is None:
        return config._entero("KENI_METRICAS_SERIE_MAX", _METRICAS_SERIE_MAX_DEF, minimo=2)
    return limite if limite > 0 else None



# --------------------------------------------------------------------------- #
# Histórico de metricas POR PIEZA (serie temporal general, todas las piezas)   #
# --------------------------------------------------------------------------- #
#
# `metricas_pieza_snapshots`: una fila por pieza por refresco del daemon
# (`metricas_piezas_refresco`, cada 4h) para TODAS las piezas recientes (no solo las
# del modulo comercial). Habilita analisis temporales por marca×red×formato. Relacion con
# las otras dos series: `metricas_cache` guarda el valor ACTUAL (sobrescrito); esta guarda
# la SERIE; `comercial_snapshots` sigue para el seguimiento de OBJETIVOS comerciales. Ver
# ADR 0007. El crecimiento lo acota la limpieza por retencion (`purgar_snapshots_piezas`).

# Metricas que el snapshot por pieza captura ademas de la clave (pieza/marca/red/formato/ts).
# Una sola tupla DRY mantiene alineados INSERT y SELECT: anadir una metrica = anadir aqui +
# a la columna en `_DDL_ESQUEMA`. Cada par es (columna, "int"|"float"); todas DEFAULT 0
# (dato ausente -> 0). `engagement_pct` es REAL (porcentaje); el resto enteros.
_METRICAS_PIEZA_SNAPSHOT: tuple[tuple[str, str], ...] = (
    ("visualizaciones", "int"),
    ("interacciones", "int"),
    ("alcance", "int"),
    ("engagement_pct", "float"),
    ("likes", "int"),
    ("comentarios", "int"),
    ("compartidos", "int"),
    ("guardados", "int"),
    ("video_views", "int"),
    ("tiempo_medio_vis_s", "int"),
    ("clics_enlace", "int"),
    ("seguidores_netos_atribuidos", "int"),
)
# Columnas de la clave (no-metricas) que devuelve la lectura, en orden.
_COLS_PIEZA_SNAPSHOT_CLAVE: tuple[str, ...] = ("pieza_id", "marca", "red", "formato", "ts")
_COLS_PIEZA_SNAPSHOT_LECTURA: tuple[str, ...] = (
    *_COLS_PIEZA_SNAPSHOT_CLAVE,
    *(col for col, _ in _METRICAS_PIEZA_SNAPSHOT),
)
_SELECT_PIEZA_SNAPSHOT = ", ".join(_COLS_PIEZA_SNAPSHOT_LECTURA)


def _coaccionar_metrica(valor: Any, tipo: str) -> Any:
    """Convierte un valor de metrica a su tipo (int/float), tolerando None/no parseable -> 0."""
    if valor is None:
        return 0.0 if tipo == "float" else 0
    try:
        return float(valor) if tipo == "float" else int(valor)
    except (TypeError, ValueError):
        return 0.0 if tipo == "float" else 0


def _fila_a_snapshot_pieza(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `metricas_pieza_snapshots` en un dict (clave texto, metricas tipadas)."""
    snap: dict[str, Any] = {col: fila[col] for col in _COLS_PIEZA_SNAPSHOT_CLAVE}
    # `ts` es timestamptz (migracion 0033): se re-emite al canon ISO (el resto de la clave es
    # TEXT). El front grafica la serie y el dominio la parsea con `datetime.fromisoformat`.
    snap["ts"] = iso_o_vacio(fila["ts"])
    for col, tipo in _METRICAS_PIEZA_SNAPSHOT:
        snap[col] = _coaccionar_metrica(fila[col], tipo)
    return snap


def registrar_snapshot_pieza(
    pieza_id: str,
    marca: str,
    red: str,
    formato: str,
    ts: str,
    metricas: dict[str, Any],
) -> bool:
    """Inserta un snapshot histórico de UNA pieza (idempotente por `(pieza_id, ts)`).

    Devuelve True si insertó una fila nueva, False si ya había un snapshot en ese `ts` (el
    índice ÚNICO -> `ON CONFLICT DO NOTHING` evita duplicar el mismo instante). Cada métrica
    ausente o `None` en `metricas` se persiste como 0 (defensivo). El llamante normal es el
    daemon de refresco proactivo (`metricas_pieza.recalcular` -> `repos.registrar_snapshot_pieza`).
    """
    metricas = metricas or {}
    cols = (
        "id",
        *_COLS_PIEZA_SNAPSHOT_CLAVE,
        *(col for col, _ in _METRICAS_PIEZA_SNAPSHOT),
    )
    valores = [
        # hex COMPLETO (32): esta tabla acumula una fila por pieza por refresco (volumen alto
        # y sostenido).
        uuid.uuid4().hex,
        pieza_id,
        marca or "",
        red or "",
        formato or "",
        ts,
        *(_coaccionar_metrica(metricas.get(col), tipo) for col, tipo in _METRICAS_PIEZA_SNAPSHOT),
    ]
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in cols)
        cur = con.execute(
            f"INSERT OR IGNORE INTO metricas_pieza_snapshots ({', '.join(cols)}) "
            f"VALUES ({marcadores})",
            tuple(valores),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# Filas por sentencia en el INSERT multi-fila del lote. Cada fila lleva 18 columnas; el tope
# de parámetros de un statement de Postgres es 65535, así que 1000 filas (18 000 parámetros)
# deja margen de sobra y mantiene las sentencias de tamaño razonable.
_FILAS_POR_INSERT = 1000


def _trozos(seq: list[Any], tam: int) -> Any:
    """Parte `seq` en trozos de hasta `tam` elementos (generador)."""
    for i in range(0, len(seq), tam):
        yield seq[i : i + tam]


def registrar_snapshots_piezas_lote(filas: list[dict[str, Any]], ts: str) -> int:
    """Inserta en UN lote (una conexión, una transacción) los snapshots de varias piezas.

    Todas las filas comparten el mismo instante `ts` (el `generado_en` del refresco del
    listado). Antes de insertar consulta qué `pieza_id` del lote YA tienen un snapshot en ese
    `ts` y los omite: así la inmensa mayoría de las reejecuciones (replay del backfill,
    refrescos repetidos) no llegan al INSERT. Lo que queda se escribe con un solo INSERT
    multi-fila `ON CONFLICT (pieza_id, ts) DO NOTHING` por trozo, en vez de N conexiones +
    N commits. Devuelve cuántas filas nuevas se insertaron. Idempotente por `(pieza_id, ts)`.

    Cada elemento de `filas` es `{pieza_id, marca, red, formato, metricas}` (`metricas` lleva
    las claves de `_METRICAS_PIEZA_SNAPSHOT`; las ausentes -> 0). Dentro del lote gana el
    primer registro de cada `pieza_id` (el `ON CONFLICT` lo confirma).
    """
    if not ts or not filas:
        return 0
    por_pieza: dict[str, dict[str, Any]] = {}
    for f in filas:
        pid = str(f.get("pieza_id") or "")
        if pid:
            por_pieza.setdefault(pid, f)
    if not por_pieza:
        return 0
    cols = (
        "id",
        *_COLS_PIEZA_SNAPSHOT_CLAVE,
        *(col for col, _ in _METRICAS_PIEZA_SNAPSHOT),
    )
    con = _conectar()
    try:
        candidatos = list(por_pieza)
        existentes: set[str] = set()
        for grupo in _trozos(candidatos, _FILAS_POR_INSERT):
            marcadores = ", ".join("?" for _ in grupo)
            for fila in con.execute(
                f"SELECT pieza_id FROM metricas_pieza_snapshots "
                f"WHERE ts = ? AND pieza_id IN ({marcadores})",
                (ts, *grupo),
            ).fetchall():
                existentes.add(fila["pieza_id"])
        nuevos = [por_pieza[pid] for pid in candidatos if pid not in existentes]
        if not nuevos:
            return 0
        una_fila = "(" + ", ".join("?" for _ in cols) + ")"
        escritos = 0
        for trozo in _trozos(nuevos, _FILAS_POR_INSERT):
            valores: list[Any] = []
            for f in trozo:
                metricas = f.get("metricas") or {}
                valores.extend((
                    uuid.uuid4().hex,
                    str(f.get("pieza_id") or ""),
                    f.get("marca") or "",
                    f.get("red") or "",
                    f.get("formato") or "",
                    ts,
                    *(_coaccionar_metrica(metricas.get(col), tipo) for col, tipo in _METRICAS_PIEZA_SNAPSHOT),
                ))
            grupos = ", ".join(una_fila for _ in trozo)
            cur = con.execute(
                f"INSERT INTO metricas_pieza_snapshots ({', '.join(cols)}) "
                f"VALUES {grupos} ON CONFLICT (pieza_id, ts) DO NOTHING",
                tuple(valores),
            )
            escritos += max(cur.rowcount or 0, 0)
        con.commit()
        return escritos
    finally:
        con.close()


def serie_pieza(pieza_id: str, *, limite: int | None = None) -> list[dict[str, Any]]:
    """Serie temporal histórica de UNA pieza (más antiguo primero), lista para graficar.

    Acotada por DEFECTO a los últimos `KENI_METRICAS_SERIE_MAX` puntos (el más reciente SIEMPRE
    entra; ver `_tope_serie_metricas`). `limite<=0` => serie COMPLETA.
    """
    tope = _tope_serie_metricas(limite)
    con = _conectar()
    try:
        if tope is None:
            filas = con.execute(
                f"SELECT {_SELECT_PIEZA_SNAPSHOT} FROM metricas_pieza_snapshots "
                "WHERE pieza_id = ? ORDER BY ts ASC",
                (pieza_id,),
            ).fetchall()
        else:
            # Últimos N (DESC + LIMIT, barato con `idx_metricas_pieza_snapshots_pieza`) reinvertidos
            # a ASC: el último punto, del que cuelga la "velocidad", queda garantizado en el recorte.
            filas = con.execute(
                f"SELECT {_SELECT_PIEZA_SNAPSHOT} FROM metricas_pieza_snapshots "
                "WHERE pieza_id = ? ORDER BY ts DESC LIMIT ?",
                (pieza_id, tope),
            ).fetchall()
            filas = list(reversed(filas))
    finally:
        con.close()
    return [_fila_a_snapshot_pieza(f) for f in filas]


def listar_snapshots_piezas(
    marca: str | None = None,
    red: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    *,
    limite: int | None = None,
) -> list[dict[str, Any]]:
    """Snapshots históricos por pieza FILTRADOS (para análisis agregados futuros).

    Filtros opcionales por `marca`, `red` y ventana de `ts` (`desde`/`hasta`, ISO, inclusivos).
    Devuelve las filas ordenadas por `ts` ascendente. Acotada por DEFECTO a los últimos
    `KENI_METRICAS_SERIE_MAX` puntos (el más reciente SIEMPRE entra). `limite<=0` => serie
    COMPLETA (para barridos/exportaciones que necesiten todo el rango filtrado).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if red:
        clausulas.append("red = ?")
        params.append(red)
    if desde:
        clausulas.append("ts >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("ts <= ?")
        params.append(hasta)
    where = f"WHERE {' AND '.join(clausulas)} " if clausulas else ""
    tope = _tope_serie_metricas(limite)
    con = _conectar()
    try:
        if tope is None:
            filas = con.execute(
                f"SELECT {_SELECT_PIEZA_SNAPSHOT} FROM metricas_pieza_snapshots "
                f"{where}ORDER BY ts ASC",
                tuple(params),
            ).fetchall()
        else:
            # Últimos N del conjunto filtrado (DESC + LIMIT) reinvertidos a ASC para el graficado.
            filas = con.execute(
                f"SELECT {_SELECT_PIEZA_SNAPSHOT} FROM metricas_pieza_snapshots "
                f"{where}ORDER BY ts DESC LIMIT ?",
                (*params, tope),
            ).fetchall()
            filas = list(reversed(filas))
    finally:
        con.close()
    return [_fila_a_snapshot_pieza(f) for f in filas]


def purgar_snapshots_piezas(retencion_dias: int, ahora_iso: str) -> int:
    """Borra los snapshots por pieza con `ts` < (`ahora_iso` - `retencion_dias`). Devuelve nº borrados.

    El corte se calcula a partir del `ahora_iso` que pasa el LLAMANTE (el daemon ya tiene un
    reloj): db.py NO genera la hora del sistema, para que la limpieza sea testeable de forma
    determinista. `ahora_iso` se parsea como ISO; si no parsea, no se borra nada (defensivo).
    """
    if retencion_dias <= 0:
        return 0
    try:
        corte = datetime.fromisoformat(ahora_iso) - timedelta(days=retencion_dias)
    except (TypeError, ValueError):
        return 0
    # Corte en el CANON (UTC sin offset, segundos): el `ts` comparado es TEXT y la
    # comparacion es lexicografica.
    corte_iso = iso_utc(corte)
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM metricas_pieza_snapshots WHERE ts < ?", (corte_iso,)
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()



# --------------------------------------------------------------------------- #
# Cache de metricas (combo tipo×rango×marca; lo orquesta metricas_cache.py)     #
# --------------------------------------------------------------------------- #


def leer_metricas_cache(clave: str) -> dict[str, Any] | None:
    """Lee una entrada de cache por `clave` ("{tipo}:{rango}:{marca}"), o None.

    Devuelve `{payload, fuente, generado_en}` con `payload` ya deserializado (el dict
    crudo de `keni_metricas.servicio`). None si no hay entrada o el JSON esta corrupto
    (se trata como ausencia: el llamante recalcula).
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT payload, fuente, generado_en FROM metricas_cache WHERE clave = ?",
            (clave,),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return None
    try:
        bruto = fila["payload"]
        # `dict_row` devuelve como dict/list cuando es jsonb; en BDs TEXT (o tests con str),
        # se deserializa. Un valor corrupto -> None (= ausencia).
        payload = bruto if isinstance(bruto, (dict, list)) else json.loads(bruto)
    except (ValueError, TypeError):
        return None
    return {
        "payload": payload,
        "fuente": fila["fuente"] or "muestra",
        "generado_en": fila["generado_en"],
    }


def listar_metricas_cache_por_tipo(tipos: tuple[str, ...]) -> list[dict[str, Any]]:
    """Todas las entradas de cache de los `tipos` dados: `{payload, generado_en}` por fila.

    El backfill del histórico por pieza (`metricas_pieza.backfill_historico_desde_cache`)
    recorre las entradas del listado de piezas (varias por marca×rango, cada una con un
    `generado_en` distinto) para reconstruir los puntos históricos ya capturados. `payload`
    sale ya deserializado; las filas con JSON corrupto se omiten (no rompen el barrido).
    """
    if not tipos:
        return []
    marcadores = ", ".join("?" for _ in tipos)
    con = _conectar()
    try:
        filas = con.execute(
            f"SELECT payload, generado_en FROM metricas_cache WHERE tipo IN ({marcadores})",
            tuple(tipos),
        ).fetchall()
    finally:
        con.close()
    salida: list[dict[str, Any]] = []
    for fila in filas:
        try:
            bruto = fila["payload"]
            payload = bruto if isinstance(bruto, (dict, list)) else json.loads(bruto)
        except (ValueError, TypeError):
            continue
        salida.append({"payload": payload, "generado_en": fila["generado_en"]})
    return salida


def guardar_metricas_cache(
    clave: str,
    tipo: str,
    rango: str,
    marca: str,
    payload: dict[str, Any],
    fuente: str,
    generado_en: str,
) -> None:
    """UPSERT de una entrada de cache (`payload` se serializa a JSON)."""
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO metricas_cache "
            "(clave, tipo, rango, marca, payload, fuente, generado_en) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (clave) DO UPDATE SET "
            "tipo = EXCLUDED.tipo, rango = EXCLUDED.rango, marca = EXCLUDED.marca, "
            "payload = EXCLUDED.payload, fuente = EXCLUDED.fuente, "
            "generado_en = EXCLUDED.generado_en",
            (
                clave,
                tipo,
                rango,
                marca,
                a_json_dict(payload),
                fuente,
                generado_en,
            ),
        )
        con.commit()
    finally:
        con.close()


def purgar_metricas_cache(
    prefijo_vigente: str, corte_rangos_adhoc: str, tipos: tuple[str, ...]
) -> int:
    """Borra entradas de cache muertas; devuelve cuantas filas cayeron.

    Acotado a `tipos` (los combos de `metricas_cache.py`): la tabla es COMPARTIDA con la
    cache por-pieza del tablero (`metricas_pieza.py`, tipo `pieza_contenido`, claves sin
    version), que NO debe tocarse. Dos clases de basura (las decide `metricas_cache.py`):
      - Claves que NO llevan el prefijo de version vigente (`v{N}:`): esquema viejo,
        ya nadie las lee tras subir la version.
      - Rangos AD-HOC (`rango:...`, los genera el comparador con fechas que se
        desplazan a diario) con `generado_en` anterior al corte: claves de un solo uso.
    `generado_en` es ISO canonico (UTC sin offset), asi que compara lexicograficamente.
    """
    marcas_tipos = ", ".join("?" for _ in tipos)
    con = _conectar()
    try:
        c1 = con.execute(
            f"DELETE FROM metricas_cache WHERE tipo IN ({marcas_tipos}) AND clave NOT LIKE ?",
            (*tipos, prefijo_vigente + "%"),
        )
        # El patron LIKE viaja como parametro: un '%' literal en el SQL rompe el
        # binding de psycopg (solo admite %s/%b/%t como placeholders).
        c2 = con.execute(
            f"DELETE FROM metricas_cache WHERE tipo IN ({marcas_tipos}) "
            "AND rango LIKE ? AND generado_en < ?",
            (*tipos, "rango:%", corte_rangos_adhoc),
        )
        con.commit()
        return max(c1.rowcount or 0, 0) + max(c2.rowcount or 0, 0)
    finally:
        con.close()

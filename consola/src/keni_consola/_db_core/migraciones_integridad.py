"""Migraciones de INTEGRIDAD del esquema (FKs, CHECK, version optimista, tipos jsonb).

Endurecen el esquema heredado de la era SQLite ("TEXT-para-todo, sin FKs") ahora que el
unico backend es Postgres (ADR 0004; `motor_db` solo IMITA la API de sqlite3 sobre Postgres).
Ver `docs/adr/0012` (apendice de 0004).

DISENO comun a todas estas migraciones (CRITICO porque despliegan sobre datos REALES):
  - Son IDEMPOTENTES: el patron es `DROP ... IF EXISTS` + recrear, o `ADD COLUMN IF NOT EXISTS`,
    o un cambio de tipo GUARDADO por una consulta a `information_schema`. Pueden correr dos veces
    sin fallar (y, de hecho, lo hacen en los tests: el journal `schema_migraciones` se trunca
    entre tests, asi que se re-aplican en cada arranque).
  - Cada `ADD CONSTRAINT` (FK o CHECK) va PRECEDIDO de una LIMPIEZA idempotente de las filas que
    lo violarian (sueltos para las FK; valores fuera de la allowlist para los CHECK). Sin esto,
    el `ADD CONSTRAINT` tumbaria el arranque del deploy contra una BD con datos sucios.

Se registran como migraciones POST-DDL en `migraciones.py` (corren tras el DDL declarativo, que
ya garantiza la existencia de TODAS las tablas/columnas que estas tocan).
"""
from __future__ import annotations

from typing import Any

from ._comun import _log


def _en_sql(valores: tuple[str, ...]) -> str:
    """`('a', 'b', …)` para un `IN (...)` a partir de una allowlist de slugs.

    Los valores son constantes del codigo (allowlists de dominio), no entran datos de usuario.
    Aun asi escapamos la comilla simple (defensa en profundidad; hoy ningun slug la lleva).
    """
    interior = ", ".join("'" + v.replace("'", "''") + "'" for v in valores)
    return f"({interior})"


# --------------------------------------------------------------------------- #
# Bloque 1: FOREIGN KEYS reales en las relaciones de alto valor (hub `contenido`)
# --------------------------------------------------------------------------- #
#
# Cada tupla: (tabla_hija, columna, tabla_padre, columna_padre, on_delete).
#
# SOLO referencias OBLIGATORIAS (la columna SIEMPRE lleva un id de padre real en la practica:
# una fila por plataforma SIN su `contenido`, un subtitulo SIN su composicion, etc. no tienen
# sentido). En esas, el sentinel '' (DEFAULT del esquema heredado) nunca aparece legitimamente,
# asi que tras BORRAR los sueltos la FK queda limpia y, en adelante, un '' lo RECHAZA la FK
# (detecta el bug en vez de dejar una fila colgada). Todas con ON DELETE CASCADE: la hija es
# dependiente (su vida se ata a la del padre).
#
# Eleccion del PADRE cuando la hija tiene varias columnas-referencia:
#   - `publicacion_comentarios` -> `publicacion_id` (su `pieza_id` es OPCIONAL: ''=hilo del item).
#   - `pieza_copy_versiones` / `pieza_aprobaciones` -> `pieza_id` (SIEMPRE real al
#     insertar; su `publicacion_id` se guarda como `publicacion_id or ''`, opcional). El borrado del
#     `contenido` las arrastra IGUAL por transitividad (contenido -> pieza -> …).
#   - `documento_versiones` -> `publicacion_id` (la version pertenece a la pieza del tablero).
#
# NO migradas a FK (decisiones documentadas, ver ADR 0012):
#   - `metricas_pieza_snapshots.pieza_id`: NO es un `pieza.id`. Se rellena con el
#     `id_post_metricool` (id del post en Metricool), ver `metricas_pieza._registrar_historico`.
#     Una FK a `pieza` BORRARIA en cascada/limpieza todo el historico de metricas.
#   - Referencias OPCIONALES con sentinel '' (`contenido.evento_id`, `noticias_items.publicacion_id`,
#     `noticias_items.cluster_id`): el esquema usa '' (no NULL) para "sin referencia". Una FK de
#     Postgres exige que CADA valor no-nulo exista en el padre, e '' no es NULL -> requeriria un
#     padre con id=''. Convertir '' -> NULL implica volver nullable la columna y tocar los muchos
#     call-sites que comparan/filtran por '' (riesgo alto sobre datos vivos). Se difiere.
_FKS: tuple[tuple[str, str, str, str, str], ...] = (
    ("pieza", "publicacion_id", "publicacion", "id", "CASCADE"),
    ("publicacion_comentarios", "publicacion_id", "publicacion", "id", "CASCADE"),
    ("pieza_copy_versiones", "pieza_id", "pieza", "id", "CASCADE"),
    ("pieza_aprobaciones", "pieza_id", "pieza", "id", "CASCADE"),
    ("documento_versiones", "publicacion_id", "publicacion", "id", "CASCADE"),
    ("video_subtitulos", "composicion_id", "video_composiciones", "id", "CASCADE"),
    ("insumos_item", "lote_id", "insumos_lote", "id", "CASCADE"),
)


def _nombre_fk(tabla: str, columna: str) -> str:
    return f"fk_{tabla}_{columna}"


def _migrar_fks_hub(con: Any) -> None:
    """Crea las FKs reales del hub `contenido` y afines, limpiando sueltos antes de cada una.

    Idempotente: `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT`. La limpieza previa
    (`DELETE` de las filas cuya columna-referencia no apunta a un padre existente, incluido el
    sentinel '') garantiza que el `ADD CONSTRAINT` no falle sobre una BD con sueltos.
    """
    for tabla, columna, padre, col_padre, on_delete in _FKS:
        nombre = _nombre_fk(tabla, columna)
        # Limpieza de sueltos (idempotente): borra las hijas sin padre real. Cubre el
        # sentinel '' y cualquier referencia rota por borrados que no propagaban (sin FK).
        borradas = con.execute(
            f"DELETE FROM {tabla} WHERE {columna} NOT IN (SELECT {col_padre} FROM {padre})"  # noqa: S608
        ).rowcount
        if borradas:
            _log.info(
                "FK %s: %d fila(s) suelta(s) de %s borradas antes de crear la FK.",
                nombre, borradas, tabla,
            )
        con.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {nombre}")  # noqa: S608
        con.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} "  # noqa: S608
            f"FOREIGN KEY ({columna}) REFERENCES {padre}({col_padre}) ON DELETE {on_delete}"
        )


# --------------------------------------------------------------------------- #
# Bloque 2: CHECK constraints en campos de ESTADO (allowlists de dominio)        #
# --------------------------------------------------------------------------- #
#
# Cada tupla: (tabla, columna, allowlist, valor_de_normalizacion). Las allowlists son las
# CANONICAS del codigo (`keni_shared.estados` / `keni_consola.estados`): se importan dentro de
# la fn (no a nivel de modulo: `_db_core` es la capa de persistencia y `estados` es de dominio)
# para que el CHECK y la app validen contra LA MISMA fuente, sin duplicar literales.
#
# Antes de cada CHECK, los valores FUERA de la allowlist se NORMALIZAN al valor por defecto
# (idempotente): asi el `ADD CONSTRAINT` no falla sobre datos heredados sucios. El valor de
# normalizacion SIEMPRE pertenece a la allowlist.


def _migrar_checks_dominio(con: Any) -> None:
    """Aplica CHECKs de allowlist a los campos de estado, normalizando los valores invalidos.

    Idempotente: normaliza (UPDATE) + `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT CHECK`.
    """
    from ..estados import (
        DECISIONES_APROBACION,
        ESTADOS_PUBLICACION,
        ESTADOS_PIEZA,
        ROLES_USUARIO,
        VERIFICACIONES_CONTENIDO,
    )

    # Renombres de VALOR de la verificación de fuente (ola de 3 niveles): se aplican TRAS el DROP del
    # CHECK viejo (que prohibiría los nuevos valores) y ANTES de normalizar, para NO perder las filas
    # (la normalización las mandaría a "" en vez de renombrarlas).
    renombres_vf = {"no_verificado": "verificado", "problema": "requiere_humano"}

    checks: tuple[tuple[str, str, tuple[str, ...], str, dict[str, str]], ...] = (
        ("publicacion", "estado", ESTADOS_PUBLICACION, "pendiente", {}),
        # La allowlist de pieza es (borrador/en_revision/programado/
        # publicado). El default de normalización es `borrador`: las filas con valores
        # retirados (pendiente/en_curso/aprobado) se normalizan a `borrador` ANTES de re-aplicar
        # el CHECK (vuelven a preparación; conservan sus likes en `pieza_aprobaciones`).
        # Editar este default cambia el source de la fn -> su huella cambia -> la migración 0029
        # (re_aplicar_si_cambia) se RE-APLICA en hosted con la allowlist nueva.
        ("pieza", "estado", ESTADOS_PIEZA, "borrador", {}),
        ("pieza_aprobaciones", "decision", DECISIONES_APROBACION, "pendiente", {}),
        ("usuarios", "rol", ROLES_USUARIO, "editor", {}),
        # verificación de la FUENTE: '' es valido (sin verificar). Renombra los valores legados a la
        # nomenclatura de 3 niveles antes de normalizar.
        ("publicacion", "verificacion_fuente", VERIFICACIONES_CONTENIDO, "", renombres_vf),
    )
    for tabla, columna, allowlist, normal, renombres in checks:
        nombre = f"ck_{tabla}_{columna}"
        # DROP ANTES de normalizar: el CHECK VIEJO (allowlist anterior) puede PROHIBIR el propio
        # valor de normalizacion (un valor NUEVO en la allowlist que el CHECK aun en la tabla
        # rechaza, abortando con CheckViolation el UPDATE que lo escribe). Sin
        # constraint, la normalizacion SIEMPRE entra; luego se re-aplica el CHECK nuevo.
        # FÓSIL DE NOMBRE: `publicacion` se llamó `contenido`; al renombrar la tabla, Postgres
        # conserva el NOMBRE viejo de sus CHECK (`ck_contenido_<col>`), que `ck_{tabla}_{columna}`
        # no captura. Ese fósil mantiene la allowlist vieja y rechazaría los valores renombrados
        # (p. ej. `requiere_humano`), así que hay que dropearlo también, no solo `ck_publicacion_*`.
        legados = (f"ck_contenido_{columna}",) if tabla == "publicacion" else ()
        for cn in (nombre, *legados):
            con.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {cn}")  # noqa: S608
        # Renombra los valores legados (idempotente: WHERE = viejo) ANTES de normalizar, ya sin el
        # CHECK viejo que los prohibiría.
        for viejo, nuevo in renombres.items():
            con.execute(
                f"UPDATE {tabla} SET {columna} = ? WHERE {columna} = ?",  # noqa: S608
                (nuevo, viejo),
            )
        # Normaliza los valores fuera de la allowlist al default (idempotente). El default
        # esta en la allowlist, asi que tras esto ninguna fila viola el CHECK.
        tocadas = con.execute(
            f"UPDATE {tabla} SET {columna} = ? "  # noqa: S608 -- tabla/columna son constantes
            f"WHERE {columna} NOT IN {_en_sql(allowlist)}",
            (normal,),
        ).rowcount
        if tocadas:
            _log.info(
                "CHECK %s: %d fila(s) con %s.%s invalido normalizadas a %r.",
                nombre, tocadas, tabla, columna, normal,
            )
        con.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} "  # noqa: S608
            f"CHECK ({columna} IN {_en_sql(allowlist)})"
        )

    # `noticias_clusters.verificacion_fuente` NO tiene CHECK (su set aún no está centralizado), pero
    # sus datos usan los MISMOS tokens legados: renombra también ahí para que el código (que ya solo
    # conoce la nomenclatura de 3 niveles) lea valores consistentes. Idempotente.
    for viejo, nuevo in renombres_vf.items():
        con.execute(
            "UPDATE noticias_clusters SET verificacion_fuente = ? WHERE verificacion_fuente = ?",
            (nuevo, viejo),
        )


# --------------------------------------------------------------------------- #
# Bloque 3: CONCURRENCIA OPTIMISTA (`version`) en contenido y pieza
# --------------------------------------------------------------------------- #


def _migrar_version_optimista(con: Any) -> None:
    """Anade `version INTEGER NOT NULL DEFAULT 0` a `contenido` y `pieza`.

    Para BDs ya creadas por versiones anteriores (el DDL declarativo ya la trae en las nuevas).
    Idempotente (`ADD COLUMN IF NOT EXISTS`). El cableado (incremento + comprobacion) vive en
    las funciones de actualizacion del repo (`db_publicacion`/`db_piezas`).
    """
    for tabla in ("publicacion", "pieza"):
        con.execute(
            f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0"  # noqa: S608
        )


# --------------------------------------------------------------------------- #
# Bloque 4: TIPOS — TEXT-JSON -> jsonb en las columnas que se leen enteras       #
# --------------------------------------------------------------------------- #
#
# Migracion PRAGMATICA (no las 55 tablas): solo `jobs.spec` y `metricas_cache.payload`, ambas
# TEXT con JSON serializado que se LEE ENTERO (y se querria poder consultar). Con `dict_row`,
# una columna jsonb vuelve como dict, no str; los call-sites de lectura ya se adaptaron
# (`jobspec.deserializar` y `db_metricas.leer_metricas_cache` aceptan dict-o-str). La ESCRITURA
# no cambia: la app sigue pasando el JSON serializado (str) y Postgres lo castea a jsonb.
#
# Los TIMESTAMP TEXT (series, cola, contenido.creado/actualizado, gasto_ia.dia…) NO se migran a
# `timestamptz` en esta ola: ver la nota de RIESGO en la ADR 0012 (sentinel '' incompatible con
# timestamptz, `substr()` sobre el texto, y un `datetime` no serializa a JSON en las muchas
# respuestas de API que hoy emiten estos campos como string ISO). El texto ya esta en canon UTC
# sin offset (ver `tiempo.ahora_iso` + migracion 0024), asi que el orden lexico == cronologico.

# Cada tupla: (tabla, columna). El default de seguridad ante un valor NO-JSON es '{}'.
_COLUMNAS_JSONB: tuple[tuple[str, str], ...] = (
    ("jobs", "spec"),
    ("metricas_cache", "payload"),
)


def _migrar_tipos_jsonb(con: Any) -> None:
    """Convierte `jobs.spec` y `metricas_cache.payload` de TEXT a `jsonb` (BDs existentes).

    Idempotente: GUARDADA por el tipo actual (si ya es jsonb, no hace nada). El `USING` castea
    el texto a jsonb cuando empieza por '{'/'[' (todo lo que escribe la app: `json.dumps`/
    `a_json_dict` de un dict) y degrada a '{}' cualquier valor sucio heredado, para que el
    cambio de tipo no tumbe el deploy.
    """
    for tabla, columna in _COLUMNAS_JSONB:
        tipo = con.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            (tabla, columna),
        ).fetchone()
        if tipo is not None and tipo["data_type"] == "jsonb":
            continue  # ya convertida (BD nueva via DDL, o migracion ya aplicada)
        plantilla = (
            "ALTER TABLE {tabla} ALTER COLUMN {columna} TYPE jsonb "
            "USING (CASE WHEN left(btrim({columna}), 1) IN ('{{', '[') "
            "THEN {columna}::jsonb ELSE '{{}}'::jsonb END)"
        )
        con.execute(plantilla.format(tabla=tabla, columna=columna))  # noqa: S608 -- constantes
        _log.info("Tipo: %s.%s convertida a jsonb.", tabla, columna)


# --------------------------------------------------------------------------- #
# Bloque 5: INDICE de GENERACIONES (rendimiento del listado de Actividad IA)     #
# --------------------------------------------------------------------------- #
#
# El registro de cada generacion vive en un YAML (fuente de verdad del DETALLE pesado:
# prompt/razonamiento/stream). Listar Actividad IA / Pipelines parseaba TODOS los ~2000 YAML por
# peticion (glob + parse + sort en memoria). Esta tabla replica los campos LIGEROS del listado
# para paginar por SQL sin tocar disco; el YAML se lee solo para el detalle. La mantiene
# `generaciones._almacen` (al crear/actualizar/borrar/purgar) + un backfill idempotente al primer
# uso. `payload` (jsonb) guarda el dict publico ligero (sin prompt/razonamiento) que `listar`
# devuelve, asi la forma del listado es identica con o sin indice.


def _migrar_indice_generaciones(con: Any) -> None:
    """Crea la tabla `generaciones_indice` y sus indices (BDs ya creadas; ADR 0012).

    El DDL declarativo ya la trae para BDs virgenes; esta migracion (0032) la garantiza en las
    hosted existentes. Idempotente (`CREATE TABLE/INDEX IF NOT EXISTS`). El BACKFILL desde los
    YAML existentes NO va aqui (la capa de BD no conoce el almacen de ficheros): lo hace
    `generaciones._almacen` de forma perezosa e idempotente al primer listado tras el arranque.
    """
    con.execute(
        "CREATE TABLE IF NOT EXISTS generaciones_indice ("
        "gen_id TEXT PRIMARY KEY, fecha_inicio TEXT NOT NULL DEFAULT '', "
        "estado TEXT NOT NULL DEFAULT '', tipo TEXT NOT NULL DEFAULT '', "
        "marca TEXT NOT NULL DEFAULT '', proceso TEXT NOT NULL DEFAULT '', "
        "publicacion_id TEXT NOT NULL DEFAULT '', payload jsonb NOT NULL DEFAULT '{}', "
        "actualizado TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_generaciones_indice_orden "
        "ON generaciones_indice (fecha_inicio DESC, gen_id DESC)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_generaciones_indice_marca ON generaciones_indice (marca)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_generaciones_indice_estado ON generaciones_indice (estado)"
    )


def _migrar_indice_pieza_estado_marca(con: Any) -> None:
    """Indice compuesto `(estado, marca)` en `pieza` (BDs ya creadas; rendimiento).

    El feed y las colas filtran por estado + marca (la marca esta denormalizada en `pieza`);
    el DDL declarativo ya trae este indice para BDs virgenes y esta migracion lo garantiza en
    las hosted existentes. Aditivo e idempotente (`CREATE INDEX IF NOT EXISTS`).
    """
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_pieza_estado_marca ON pieza (estado, marca)"
    )


def _migrar_tabla_daemon_barridos(con: Any) -> None:
    """Crea la tabla `daemon_barridos` y su indice (BDs ya creadas; observabilidad).

    HISTORIAL por barrido de daemon (una fila por sweep): el DDL declarativo ya la trae para
    BDs virgenes; esta migracion (0034) la garantiza en las hosted existentes. Idempotente
    (`CREATE TABLE/INDEX IF NOT EXISTS`). No hay backfill: el historial es prospectivo (lo
    llena el hook `latidos.barrido` a partir de aqui; lo viejo no existia).
    """
    con.execute(
        "CREATE TABLE IF NOT EXISTS daemon_barridos ("
        "id TEXT PRIMARY KEY, daemon TEXT NOT NULL, ts_inicio TEXT NOT NULL DEFAULT '', "
        "duracion_ms INTEGER NOT NULL DEFAULT 0, ok INTEGER NOT NULL DEFAULT 1, "
        "resumen TEXT NOT NULL DEFAULT '', error_txt TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_daemon_barridos_daemon_ts "
        "ON daemon_barridos (daemon, ts_inicio DESC, id DESC)"
    )


def _migrar_tablas_tunel(con: Any) -> None:
    """Crea las tablas del túnel keni-fotos multi-worker (BDs ya creadas; registro compartido).

    `tunel_conexiones` (registro de WebSockets vivos, cross-worker) y `tunel_rpc` (bus de
    llamadas `buscar`/`original`/`rafaga` enrutadas al worker dueño): el DDL declarativo ya las
    trae para BDs virgenes; esta migracion (0054) las garantiza en las hosted existentes. One-shot
    e idempotente (`CREATE TABLE/INDEX IF NOT EXISTS`); sin backfill (el registro es efímero/vivo).
    """
    con.execute(
        "CREATE TABLE IF NOT EXISTS tunel_conexiones ("
        "id TEXT PRIMARY KEY, worker TEXT NOT NULL DEFAULT '', usuario TEXT NOT NULL DEFAULT '', "
        "dispositivo TEXT NOT NULL DEFAULT '', version TEXT NOT NULL DEFAULT '', "
        "marcas TEXT NOT NULL DEFAULT '[]', galerias TEXT NOT NULL DEFAULT '[]', "
        "visto_en TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_tunel_conexiones_visto ON tunel_conexiones (visto_en)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS tunel_rpc ("
        "id TEXT PRIMARY KEY, tipo TEXT NOT NULL DEFAULT '', conexion_id TEXT NOT NULL DEFAULT '', "
        "payload TEXT NOT NULL DEFAULT '{}', estado TEXT NOT NULL DEFAULT 'pendiente', "
        "resultado TEXT NOT NULL DEFAULT '', creado TEXT NOT NULL DEFAULT '')"
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_tunel_rpc_estado ON tunel_rpc (estado)")


def _drop_tabla_sugerencias_editoriales(con: Any) -> None:
    """Elimina la tabla `sugerencias_editoriales` (feature retirada: agente de sugerencias).

    El daemon del digest editorial y toda su superficie (API, repos, MCP, inicializacion) se
    borraron; la tabla queda suelta. Idempotente (`DROP TABLE IF EXISTS`); los indices
    caen con la tabla. One-shot por BD: el DDL declarativo ya no la crea.
    """
    con.execute("DROP TABLE IF EXISTS sugerencias_editoriales")


def _drop_tablas_comercial_snapshots(con: Any) -> None:
    """Elimina las tablas del seguimiento por SNAPSHOTS del antiguo apartado Comercial.

    El apartado "Comercial" (selección de un post real de Metricool + captura periódica de
    snapshots + reporte) se retiró: lo reemplazó "Campañas" (filtro por hashtag sobre
    métricas vivas). Su daemon de captura, endpoints, repos y DDL se borraron; quedan sueltas
    `comercial_publicaciones` y `comercial_snapshots` en BDs ya creadas. Idempotente
    (`DROP TABLE IF EXISTS`); los índices y la FK caen con la tabla. `comercial_campanias`
    (las campañas, vivas) NO se toca. One-shot por BD: el DDL declarativo ya no las crea.
    """
    con.execute("DROP TABLE IF EXISTS comercial_snapshots")
    con.execute("DROP TABLE IF EXISTS comercial_publicaciones")


# --------------------------------------------------------------------------- #
# Bloque 6: TIPOS — fechas TEXT -> tipos NATIVOS de Postgres (timestamptz/date) #
# --------------------------------------------------------------------------- #
#
# Cierra la migracion que la ADR 0012 habia DIFERIDO (ver la nota historica que estaba sobre
# `_COLUMNAS_JSONB`): los TIMESTAMP TEXT en columnas de ALTO USO pasan a `timestamptz` y el
# `dia` del ledger de gasto a `date`. Antes se temia (a) el sentinel '' incompatible con
# timestamptz, (b) `substr()` sobre el texto y (c) que un `datetime` no serializa a JSON en las
# muchas respuestas de API que emiten estos campos como string ISO. Resuelto:
#   (a) `USING NULLIF(col,'')::<tipo>` -> '' pasa a NULL en el ALTER; las columnas quedan
#       NULLABLE (el sentinel "sin valor", p. ej. un job aun sin `claimed_at`, es ahora NULL).
#       Las dos `*.ts` de snapshots, que nunca son '' y tienen UNIQUE (..., ts), conservan NOT
#       NULL (no se relajan: ningun '' existe que NULLIF pudiera convertir).
#   (b) los call-sites con `substr(col,1,10)` pasaron a `to_char(col AT TIME ZONE 'UTC', ...)`.
#   (c) los serializadores re-emiten el canon ISO con `tiempo.iso_o_vacio` (datetime/date -> el
#       MISMO string de antes), asi que el contrato de forma de respuesta NO cambia.
# El cast a timestamptz HONRA un offset explicito si el texto legado lo trae (aware) y, para el
# texto canonico NAIVE, lo interpreta como UTC porque la sesion fija `timezone=UTC`
# (`motor_db._OPCIONES_SESION`). Verificado en prod: 0 valores no canonicos y 0 vacios en estas
# columnas, asi que el ALTER no produce NULLs en las NOT NULL ni pierde informacion.
#
# Cada tupla: (tabla, columna, tipo_destino, nullable). El cast `USING` se compone abajo.
_COLUMNAS_FECHA_NATIVA: tuple[tuple[str, str, str, bool], ...] = (
    ("publicacion", "creado", "timestamptz", True),
    ("publicacion", "actualizado", "timestamptz", True),
    ("jobs", "creado", "timestamptz", True),
    ("jobs", "claimed_at", "timestamptz", True),
    ("metricas_pieza_snapshots", "ts", "timestamptz", False),
    ("eventos_internos", "creado", "timestamptz", True),
    ("gasto_ia", "dia", "date", True),
)


def _migrar_tipos_fecha(con: Any) -> None:
    """Convierte las columnas de fecha de ALTO USO de TEXT a tipos NATIVOS (BDs existentes).

    Idempotente y GUARDADA por el tipo actual: si la columna ya NO es `text` (BD nueva via DDL,
    o migracion ya aplicada), se salta. En la conversion: se quita el DEFAULT '' (incompatible
    con timestamptz/date) ANTES del cambio de tipo; el `USING NULLIF(col,'')::<tipo>` deja '' en
    NULL; y las columnas marcadas `nullable` pierden el NOT NULL (el sentinel "sin valor" es
    ahora NULL). Ver el bloque de notas sobre `_COLUMNAS_FECHA_NATIVA`.
    """
    for tabla, columna, tipo, nullable in _COLUMNAS_FECHA_NATIVA:
        actual = con.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            (tabla, columna),
        ).fetchone()
        if actual is None or actual["data_type"] != "text":
            continue  # tabla/columna inexistente (defensivo) o ya migrada (no es text)
        # DROP DEFAULT primero: un DEFAULT '' (heredado) no castea a timestamptz/date y
        # reventaria el ALTER TYPE. Idempotente (no-op si no hay default).
        con.execute(f"ALTER TABLE {tabla} ALTER COLUMN {columna} DROP DEFAULT")  # noqa: S608
        con.execute(
            f"ALTER TABLE {tabla} ALTER COLUMN {columna} TYPE {tipo} "  # noqa: S608 -- constantes
            f"USING NULLIF({columna}, '')::{tipo}"
        )
        if nullable:
            con.execute(f"ALTER TABLE {tabla} ALTER COLUMN {columna} DROP NOT NULL")  # noqa: S608
        _log.info("Tipo: %s.%s convertida a %s.", tabla, columna, tipo)

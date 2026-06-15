"""Migraciones del MODELO de turnos/franjas de rota (el bloque grande de `_db_core`).

`_migrar_modelo_turnos`/`_migrar_modelo_franjas` y sus auxiliares (config/seed de franjas por
semana, constantes de franja). Extraido de `_db_core.py` al trocearlo por areas (refactor de
pura reubicacion); se separa de `migraciones_columnas` por tamano. Depende de `_comun` +
`estados`/`tiempo` + stdlib.
"""
from __future__ import annotations

import uuid
from typing import Any

from ..estados import (
    ESTADO_ROTA_PROPUESTO,
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
)
from ..tiempo import ahora_iso
from ._comun import (
    _columnas_existentes,
    _franja_para_hora_migracion,
    _parsear_hora_a_minutos,
    _tabla_existe,
)

# Defaults de franjas para la migracion (mismos que `rota.py`; los hardcodeamos aqui para
# no introducir dependencia ciclica db -> rota). Si la BD ya tiene config de franjas
# (`rota_config_franjas`), `_migrar_modelo_turnos` la respeta. La conversion de cobertura
# legada a turnos usa estos rangos para mapear hora del evento -> franja.
_MIGR_FRANJA_MATUTINO_INICIO_MIN = 8 * 60   # 08:00 inclusivo
_MIGR_FRANJA_MATUTINO_FIN_MIN = 16 * 60     # 16:00 exclusivo
_MIGR_FRANJA_VESPERTINO_INICIO_MIN = 16 * 60  # 16:00 inclusivo
_MIGR_FRANJA_VESPERTINO_FIN_MIN = 24 * 60   # 24:00 exclusivo


def _migrar_modelo_turnos(con: Any) -> None:
    """Migra el modelo VIEJO de turnos al NUEVO (ola back3). Idempotente.

    MODELO VIEJO (a borrar):
      - `rota_turnos` (vieja, "cobertura") = evento×miembro: (id, semana, evento_id,
        miembro_id, miembro_nombre, estado, override, motivo, creado, actualizado).
      - `rota_turnos_trabajo` (vieja, "horario") = persona×dia×franja: (id, semana, fecha,
        miembro_id, miembro_nombre, franja, estado, override, motivo, nota_relevo, creado,
        actualizado).

    MODELO NUEVO (un turno = horario de persona×dia×franja, SIN relacion con eventos):
      - `rota_turnos` con la MISMA FORMA que la vieja `rota_turnos_trabajo`.

    PASOS (todos `IF EXISTS`/idempotentes):
      1. Si la vieja `rota_turnos_trabajo` aun esta, renombrarla a `rota_turnos_v2`
         (auxiliar, para no chocar con la cobertura legada que vamos a borrar).
      2. Si la vieja `rota_turnos` (cobertura) aun esta, leer sus filas con miembro asignado
         y derivar turnos en la nueva forma (semana, fecha del evento, miembro, franja
         derivada de la hora) → INSERT en `rota_turnos_v2` con UPSERT logico (evita
         duplicados por `(semana, fecha, miembro_id, franja)`).
      3. DROP de la vieja `rota_turnos` (cobertura).
      4. RENAME `rota_turnos_v2` -> `rota_turnos`. Tras esto, el resto del codigo opera con
         la tabla `rota_turnos` que tiene la nueva forma.
      5. Renombrar indices viejos a sus equivalentes nuevos (ALTER INDEX IF EXISTS).

    Si la BD ya esta migrada (existe `rota_turnos` con columna `fecha`), no hace nada.
    """
    # Detectar estado actual: una BD ya MIGRADA tiene `rota_turnos` con `fecha`.
    # Esta migracion trabaja con la forma INTERMEDIA (`franja` literal): la migracion
    # posterior (`_migrar_modelo_franjas`) hace el salto a `franja_id`.
    cols_turnos = _columnas_existentes(con, "rota_turnos")
    if "fecha" in cols_turnos and ("franja" in cols_turnos or "franja_id" in cols_turnos):
        # Ya estamos en el modelo intermedio (o posterior); nada que hacer aqui.
        return

    # Si NO hay tabla `rota_turnos_trabajo` y `rota_turnos` no tiene `fecha`, puede ser
    # una BD virgen (sin ninguna de las dos): no hay nada que migrar. El DDL declarativo
    # creara la nueva `rota_turnos` cuando le toque.
    tiene_trabajo = _tabla_existe(con, "rota_turnos_trabajo")
    tiene_turnos_vieja = _tabla_existe(con, "rota_turnos")
    if not tiene_trabajo and not tiene_turnos_vieja:
        return

    # Caso 1: tenemos `rota_turnos_trabajo` (horario viejo) Y `rota_turnos` (cobertura vieja).
    # Caso 2: solo `rota_turnos` (cobertura) - sin trabajo (raro: la version anterior siempre
    #   creaba ambas, pero por defensa lo cubrimos).
    # Caso 3: solo `rota_turnos_trabajo` - sin cobertura (otro caso defensivo).

    # PASO 1: renombrar trabajo -> _v2 (auxiliar).
    if tiene_trabajo:
        con.execute("ALTER TABLE IF EXISTS rota_turnos_trabajo RENAME TO rota_turnos_v2")
        con.execute(
            "ALTER INDEX IF EXISTS idx_rota_turnos_trabajo_semana "
            "RENAME TO idx_rota_turnos_semana_v2"
        )
        con.execute(
            "ALTER INDEX IF EXISTS idx_rota_turnos_trabajo_miembro "
            "RENAME TO idx_rota_turnos_miembro_v2"
        )
    else:
        # No habia tabla de horario: creamos la auxiliar vacia con la forma nueva, para que
        # el resto del flujo de migracion siga siendo uniforme.
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rota_turnos_v2 (
                id             TEXT PRIMARY KEY,
                semana         TEXT NOT NULL,
                fecha          TEXT NOT NULL DEFAULT '',
                miembro_id     TEXT NOT NULL DEFAULT '',
                miembro_nombre TEXT NOT NULL DEFAULT '',
                franja         TEXT NOT NULL DEFAULT 'descanso',
                estado         TEXT NOT NULL DEFAULT 'propuesto',
                override       INTEGER NOT NULL DEFAULT 0,
                motivo         TEXT NOT NULL DEFAULT '',
                nota_relevo    TEXT NOT NULL DEFAULT '',
                creado         TEXT NOT NULL DEFAULT '',
                actualizado    TEXT NOT NULL DEFAULT ''
            )
            """
        )

    # PASO 2: inicializar la cobertura legada como turnos en _v2 (si la habia y tenia miembros).
    if tiene_turnos_vieja and "evento_id" in cols_turnos and "miembro_id" in cols_turnos:
        # Leemos las franjas configuradas (singleton id='default') o aplicamos defaults.
        mat_ini = _MIGR_FRANJA_MATUTINO_INICIO_MIN
        mat_fin = _MIGR_FRANJA_MATUTINO_FIN_MIN
        ves_ini = _MIGR_FRANJA_VESPERTINO_INICIO_MIN
        ves_fin = _MIGR_FRANJA_VESPERTINO_FIN_MIN
        if _tabla_existe(con, "rota_config_franjas"):
            fila_cfg = con.execute(
                "SELECT matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin "
                "FROM rota_config_franjas WHERE id = ?",
                ("default",),
            ).fetchone()
            if fila_cfg is not None:
                v = _parsear_hora_a_minutos(fila_cfg["matutino_inicio"])
                if v is not None:
                    mat_ini = v
                v = _parsear_hora_a_minutos(fila_cfg["matutino_fin"])
                if v is not None:
                    mat_fin = v
                v = _parsear_hora_a_minutos(fila_cfg["vespertino_inicio"])
                if v is not None:
                    ves_ini = v
                v = _parsear_hora_a_minutos(fila_cfg["vespertino_fin"])
                if v is not None:
                    ves_fin = v

        # Cobertura legada CON miembro: derivar turno.
        filas_cobertura = con.execute(
            "SELECT t.semana, t.miembro_id, t.miembro_nombre, t.override, t.motivo, "
            "       t.creado, t.actualizado, e.fecha, e.hora "
            "FROM rota_turnos t LEFT JOIN rota_eventos e ON e.id = t.evento_id "
            "WHERE t.miembro_id IS NOT NULL AND t.miembro_id <> ''"
        ).fetchall()
        ahora = ahora_iso()
        for fila in filas_cobertura:
            fecha = (fila["fecha"] or "").strip()
            if not fecha:
                # Sin fecha del evento no podemos derivar un turno coherente.
                continue
            franja = _franja_para_hora_migracion(
                (fila["hora"] or ""),
                mat_ini=mat_ini, mat_fin=mat_fin, ves_ini=ves_ini, ves_fin=ves_fin,
            )
            # Dedup logico: si ya existe un turno para (semana, fecha, miembro_id, franja), no
            # duplicar. Hacemos SELECT (no UNIQUE en la nueva tabla; preserva libertad para
            # turnos con el mismo trio cuando se quiera, p. ej. tras swap).
            existente = con.execute(
                "SELECT id FROM rota_turnos_v2 "
                "WHERE semana = ? AND fecha = ? AND miembro_id = ? AND franja = ?",
                (fila["semana"], fecha, fila["miembro_id"], franja),
            ).fetchone()
            if existente is not None:
                continue
            con.execute(
                "INSERT INTO rota_turnos_v2 (id, semana, fecha, miembro_id, miembro_nombre, "
                "franja, estado, override, motivo, nota_relevo, creado, actualizado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex[:12],
                    fila["semana"],
                    fecha,
                    fila["miembro_id"],
                    fila["miembro_nombre"] or "",
                    franja,
                    ESTADO_ROTA_PROPUESTO,
                    int(bool(fila["override"])),
                    fila["motivo"] or "",
                    "",  # sin nota_relevo en el modelo viejo
                    fila["creado"] or ahora,
                    fila["actualizado"] or ahora,
                ),
            )

    # PASO 3: drop de la vieja `rota_turnos` (cobertura). Tambien borramos sus indices.
    con.execute("DROP INDEX IF EXISTS idx_rota_turnos_semana")
    con.execute("DROP INDEX IF EXISTS idx_rota_turnos_miembro")
    con.execute("DROP INDEX IF EXISTS idx_rota_turnos_fecha")  # defensa por si existia
    con.execute("DROP TABLE IF EXISTS rota_turnos")

    # PASO 4: rename _v2 -> rota_turnos (forma final). Recrea indices con los nombres
    # canonicos del DDL declarativo (que se ejecuta justo despues; sus CREATE INDEX IF NOT
    # EXISTS no haran nada porque ya existen).
    con.execute("ALTER TABLE IF EXISTS rota_turnos_v2 RENAME TO rota_turnos")
    # Renombrar indices auxiliares -> canonicos. Si vinieron del trabajo viejo, ya estan en _v2.
    con.execute("ALTER INDEX IF EXISTS idx_rota_turnos_semana_v2 RENAME TO idx_rota_turnos_semana")
    con.execute("ALTER INDEX IF EXISTS idx_rota_turnos_miembro_v2 RENAME TO idx_rota_turnos_miembro")
    # Indice nuevo (no existia en el trabajo viejo): lo crea el DDL declarativo despues.
    # Commit para que el DDL siguiente vea el esquema renombrado.
    con.commit()


# Nombres por defecto para inicializar las 2 franjas iniciales de una semana. Coherentes con
# `estados.NOMBRE_FRANJA_*_DEFAULT` (los re-importamos arriba). Mantener una sola fuente.
_NOMBRE_FRANJA_MANANA = NOMBRE_FRANJA_MANANA_DEFAULT
_NOMBRE_FRANJA_TARDE = NOMBRE_FRANJA_TARDE_DEFAULT


def _config_franjas_template(con: Any, marca: str = "") -> tuple[str, str, str, str]:
    """Devuelve `(matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin)` para
    inicializar las 2 franjas por defecto de una semana nueva.

    GRID POR MARCA: la config de franjas es POR MARCA — `rota_config_franjas.id` guarda el id
    de la marca (antes era el singleton `'default'`). Con `marca` leemos la fila de esa marca;
    sin marca (legado / siembra pre-migracion) caemos al singleton `'default'`. Si no hay fila,
    defaults del dominio (08-16 / 16-24).
    """
    mat_ini, mat_fin = "08:00", "16:00"
    ves_ini, ves_fin = "16:00", "24:00"
    if not _tabla_existe(con, "rota_config_franjas"):
        return mat_ini, mat_fin, ves_ini, ves_fin
    fila = con.execute(
        "SELECT matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin "
        "FROM rota_config_franjas WHERE id = ?",
        (marca or "default",),
    ).fetchone()
    if fila is None:
        return mat_ini, mat_fin, ves_ini, ves_fin
    return (
        fila["matutino_inicio"] or mat_ini,
        fila["matutino_fin"] or mat_fin,
        fila["vespertino_inicio"] or ves_ini,
        fila["vespertino_fin"] or ves_fin,
    )


_NOMBRE_FRANJA_DESCANSO = "Descanso"


def _inicializar_franjas_por_defecto_en(con: Any, lunes: str, marca: str = "") -> dict[str, str]:
    """Inserta (Mañana, Tarde, Descanso) en `rota_franjas` para `(marca, lunes)` si no existen.

    Devuelve el mapa `{nombre -> id}` con las franjas vigentes (inicializadas o ya existentes) de
    ESA marca. La franja "Descanso" se siembra con `es_descanso=true`, `inicio='00:00'`/
    `fin='00:00'` (sin rango horario real: nadie cubre eventos en descanso) y un `orden` alto
    (999) para que la UI la pinte siempre al final.

    GRID POR MARCA: cada marca tiene su propia rejilla. Detectamos si la columna `marca` ya
    existe (la migracion del modelo de turnos siembra ANTES de que exista; entonces caemos al
    camino legado sin marca y `_asegurar_marca_grid_rota` backfillea esas filas a 'claro-sports').
    Con la columna presente filtramos/insertamos por marca y el ON CONFLICT va por (marca, lunes,
    nombre) (indice `idx_rota_franjas_uniq`).
    """
    if not lunes:
        return {}
    tiene_marca = "marca" in _columnas_existentes(con, "rota_franjas")
    if tiene_marca:
        existentes = con.execute(
            "SELECT id, nombre FROM rota_franjas WHERE lunes = ? AND marca = ?",
            (lunes, marca),
        ).fetchall()
    else:
        existentes = con.execute(
            "SELECT id, nombre FROM rota_franjas WHERE lunes = ?",
            (lunes,),
        ).fetchall()
    por_nombre = {f["nombre"]: f["id"] for f in existentes}
    if (
        _NOMBRE_FRANJA_MANANA in por_nombre
        and _NOMBRE_FRANJA_TARDE in por_nombre
        and _NOMBRE_FRANJA_DESCANSO in por_nombre
    ):
        return por_nombre
    mat_ini, mat_fin, ves_ini, ves_fin = _config_franjas_template(con, marca)
    # (nombre, inicio, fin, orden, es_descanso)
    inicial = [
        (_NOMBRE_FRANJA_MANANA, mat_ini, mat_fin, 0, False),
        (_NOMBRE_FRANJA_TARDE, ves_ini, ves_fin, 1, False),
        (_NOMBRE_FRANJA_DESCANSO, "00:00", "00:00", 999, True),
    ]
    for nombre, inicio, fin, orden, es_descanso in inicial:
        if nombre in por_nombre:
            continue
        nuevo_id = uuid.uuid4().hex[:12]
        if tiene_marca:
            con.execute(
                "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso, marca) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (marca, lunes, nombre) DO NOTHING",
                (nuevo_id, lunes, nombre, inicio, fin, orden, es_descanso, marca),
            )
        else:
            con.execute(
                "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (lunes, nombre) DO NOTHING",
                (nuevo_id, lunes, nombre, inicio, fin, orden, es_descanso),
            )
        por_nombre[nombre] = nuevo_id
    # Releemos para coger los `id` reales (el ON CONFLICT pudo descartar el INSERT si otra
    # transaccion inicializo a la vez): el dict en memoria puede traer un id que no esta.
    if tiene_marca:
        filas = con.execute(
            "SELECT id, nombre FROM rota_franjas WHERE lunes = ? AND marca = ?",
            (lunes, marca),
        ).fetchall()
    else:
        filas = con.execute(
            "SELECT id, nombre FROM rota_franjas WHERE lunes = ?",
            (lunes,),
        ).fetchall()
    return {f["nombre"]: f["id"] for f in filas}


def _migrar_modelo_franjas(con: Any) -> None:
    """Migra `rota_turnos.franja` (literal) -> `rota_turnos.franja_id` (FK por semana).

    Idempotente. Pasos:
      1. Asegura que `rota_franjas` tiene la columna `es_descanso` (instancias anteriores
         a la introduccion de descanso explicito la pierden).
      2. Asegura que `rota_turnos` tiene una columna `franja_id` (la crea como NULLABLE
         temporal si la BD legada solo tiene `franja`).
      3. Por cada `lunes` con turnos legados, siembra las 3 franjas por defecto (Mañana,
         Tarde, Descanso) en `rota_franjas` usando los rangos de `rota_config_franjas`
         para las dos primeras si existe.
      4. Reasigna los turnos: `franja='matutino'`->Mañana, `franja='vespertino'`->Tarde,
         `franja='descanso'`->Descanso (la franja con `es_descanso=true`).
         IMPORTANTE: los turnos de descanso SE PRESERVAN. El usuario aclaro que el descanso
         es un TURNO EXPLICITO planificado, no una ausencia implicita.
      5. Drop de la columna `franja` (si existe) y commit.

    Si la BD ya esta en el modelo nuevo (no existe `franja`, solo `franja_id` con datos
    coherentes), no toca nada de turnos, pero igual se asegura de la columna `es_descanso`.
    """
    # PASO 0: asegurar `rota_franjas`. La migracion ahora corre ANTES del DDL declarativo
    # (porque ese DDL crea un indice sobre `franja_id`, que solo existe tras este paso). En
    # bases productivas previas la tabla no estaba creada todavia, asi que la materializamos
    # aqui de forma idempotente. El DDL declarativo posterior queda como no-op.
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS rota_franjas (
            id           TEXT PRIMARY KEY,
            lunes        TEXT NOT NULL,
            nombre       TEXT NOT NULL,
            inicio       TEXT NOT NULL,
            fin          TEXT NOT NULL,
            orden        INTEGER NOT NULL DEFAULT 0,
            es_descanso  BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE (lunes, nombre)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_rota_franjas_lunes ON rota_franjas (lunes)")

    # PASO 1: columna `es_descanso` en `rota_franjas` (idempotente). Necesario antes de
    # inicializar para que el INSERT no falle en instancias legadas que crearon la tabla sin
    # ese campo (predicado defensivo: tras PASO 0 siempre existira, pero mantenemos por si
    # el CREATE IF NOT EXISTS encuentra una tabla previa).
    cols_franjas = _columnas_existentes(con, "rota_franjas")
    if cols_franjas and "es_descanso" not in cols_franjas:
        con.execute(
            "ALTER TABLE rota_franjas ADD COLUMN es_descanso BOOLEAN NOT NULL DEFAULT FALSE"
        )

    cols = _columnas_existentes(con, "rota_turnos")
    if not cols:
        # Sin tabla `rota_turnos` -> nada que migrar (BD virgen; el DDL la creara con
        # `franja_id` directamente).
        return
    tiene_franja_literal = "franja" in cols
    tiene_franja_id = "franja_id" in cols

    if not tiene_franja_literal and tiene_franja_id:
        # Ya migrado a `franja_id`: nada que mover.
        return

    # PASO 2: asegurar columna `franja_id` (nullable temporal).
    if not tiene_franja_id:
        con.execute(
            "ALTER TABLE rota_turnos ADD COLUMN franja_id TEXT NOT NULL DEFAULT ''"
        )

    # PASO 3 y 4: por cada semana con turnos legados, inicializar las 3 franjas por defecto y
    # asignar `franja_id`. Un solo SELECT de lunes distintos con cualquier franja literal
    # legada que aun no tenga `franja_id`.
    if tiene_franja_literal:
        lunes_filas = con.execute(
            "SELECT DISTINCT semana FROM rota_turnos "
            "WHERE franja IN ('matutino', 'vespertino', 'descanso') "
            "AND (franja_id = '' OR franja_id IS NULL)"
        ).fetchall()
        for fila in lunes_filas:
            lunes = (fila["semana"] or "").strip()
            if not lunes:
                continue
            mapa = _inicializar_franjas_por_defecto_en(con, lunes)
            manana_id = mapa.get(_NOMBRE_FRANJA_MANANA, "")
            tarde_id = mapa.get(_NOMBRE_FRANJA_TARDE, "")
            descanso_id = mapa.get(_NOMBRE_FRANJA_DESCANSO, "")
            if manana_id:
                con.execute(
                    "UPDATE rota_turnos SET franja_id = ? "
                    "WHERE semana = ? AND franja = 'matutino' AND (franja_id = '' OR franja_id IS NULL)",
                    (manana_id, lunes),
                )
            if tarde_id:
                con.execute(
                    "UPDATE rota_turnos SET franja_id = ? "
                    "WHERE semana = ? AND franja = 'vespertino' AND (franja_id = '' OR franja_id IS NULL)",
                    (tarde_id, lunes),
                )
            if descanso_id:
                # IMPORTANTE: el descanso es turno explicito. Lo PRESERVAMOS reasignando.
                con.execute(
                    "UPDATE rota_turnos SET franja_id = ? "
                    "WHERE semana = ? AND franja = 'descanso' AND (franja_id = '' OR franja_id IS NULL)",
                    (descanso_id, lunes),
                )

        # PASO 5: drop de la columna `franja`. En Postgres, `DROP COLUMN ... IF EXISTS`
        # es soportado.
        con.execute("ALTER TABLE rota_turnos DROP COLUMN IF EXISTS franja")

    con.commit()

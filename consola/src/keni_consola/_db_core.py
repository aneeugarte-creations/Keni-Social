"""Cimientos de persistencia: conexion, locks y esquema/migraciones (Postgres).

Extraido de `db.py` (god-module): aqui vive la FUNDACION sobre la que se apoyan
todas las entidades (conexion `_conectar` con asegurado de esquema una-vez-por-proceso,
advisory locks, el DDL `_DDL_ESQUEMA`, `_crear_esquema` y TODAS las migraciones de
columnas/modelo, hoy VERSIONADAS via el journal `schema_migraciones` + el registro
ordenado `MIGRACIONES` — ver la REGLA junto a `_DDL_SCHEMA_MIGRACIONES` y ADR 0008
antes de cambiar el esquema). NO contiene logica de entidad (CRUD): `db.py` la
re-exporta entera (`from ._db_core import (...)`) para que los consumidores sigan
usando `db.<algo>` sin cambios. Acoplamiento hacia abajo: solo `config`/`motor_db`/
`estados` + stdlib; no importa `db` (aciclico).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

# Allowlists de dominio (neutras, sin acoplar al backend): viven en `estados.py`.
from . import config, motor_db
from .estados import (
    ESTADO_ROTA_PROPUESTO,
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
)
from .motor_db import IntegrityError
from .tiempo import ahora_iso

_log = logging.getLogger("keni_consola.db")


# URLs de BD cuyo esquema YA aseguramos en ESTE proceso. El DDL (idempotente, ~89 sentencias
# `CREATE ... IF NOT EXISTS` + `ALTER ... ADD COLUMN IF NOT EXISTS`) NO necesita re-ejecutarse en
# CADA conexion: como no hay pool y cada operacion abre su propia conexion, hacerlo en cada
# `_conectar` significaba barrer el catalogo de Postgres en CADA request -> coste real en prod y,
# x16k conexiones, el coste DOMINANTE de la suite (medido: con memo la suite cae ~3.5x). Se asegura
# UNA vez por proceso y URL; tras un deploy el proceso reinicia -> el set se vacia -> se re-crea/migra.
# En tests, un fixture autouse lo limpia por test, de modo que la PRIMERA conexion de cada test
# re-asegura el esquema (preserva la auto-curacion que ejercitan los tests de "BD vieja"/on-demand).
_esquemas_asegurados: set[str] = set()
# Protege el check-then-act sobre `_esquemas_asegurados`: varios hilos daemon (refrescos,
# worker, scanners) abren su PRIMERA conexion casi a la vez al arrancar y correrian el DDL en
# paralelo. El DDL es idempotente (riesgo bajo), pero el lock evita el doble trabajo y deja el
# "asegurar una vez por proceso/URL" limpio y determinista.
_lock_esquemas = threading.Lock()


def _conectar() -> Any:
    """Abre la conexion a Postgres y asegura el esquema UNA vez por proceso/URL.

    `motor_db.conectar_cruda()` abre Postgres con `DATABASE_URL` (obligatoria, ADR 0004) y
    devuelve una conexion que IMITA la API de `sqlite3.Connection` que usan los call sites
    (`execute(sql, params)` con `?`, filas por nombre, `rowcount`, commit/close).

    El esquema (idempotente) se crea/migra la PRIMERA vez que este proceso ve una URL dada; las
    siguientes conexiones a la misma BD se saltan el DDL (ver `_esquemas_asegurados`).
    """
    con = motor_db.conectar_cruda()
    url = config.database_url() or ""
    # Lock de modulo: el check-then-act corre en varios hilos daemon al arranque (ver
    # `_lock_esquemas`). Doble-check dentro del lock para asegurar el esquema UNA sola vez.
    if url not in _esquemas_asegurados:
        with _lock_esquemas:
            if url not in _esquemas_asegurados:
                _crear_esquema(con)
                _esquemas_asegurados.add(url)
    return con


def conectar() -> Any:
    """Conexion publica al backend (mismo `_conectar`, expuesto para `auth/`).

    El esquema de `usuarios`/`sesiones` se crea aqui igual que el resto de tablas, de modo
    que `auth/` puede operar sin duplicar la creacion del esquema. Cada operacion
    abre/cierra su propia conexion.
    """
    return _conectar()


# --------------------------------------------------------------------------- #
# Locks de aplicacion CROSS-PROCESO (Postgres advisory locks)                  #
# --------------------------------------------------------------------------- #
# Sin pool de conexiones, cada operacion abre su propia conexion: el unico mutex que cruza
# procesos (back, worker, daemons, replicas) es un advisory lock de Postgres. Lo usamos para
# el SINGLE-FLIGHT de los barridos (radar/autogen/pipeline): un segundo barrido concurrente
# (deploy solapado, admin pulsando "ejecutar" mientras corre el daemon) NO debe duplicar
# items del tablero ni runs de `claude -p`, porque su dedup es leer-luego-escribir en Python.
# `pg_try_advisory_lock` es NO bloqueante: si otro ya lo tiene, devolvemos False y el segundo
# barrido sale de inmediato (no encola, no espera). El lock se suelta al cerrar la conexion
# (o explicitamente con `pg_advisory_unlock`).

# Espacio de nombres (clave alta de 32 bits del par de claves int) para no colisionar con
# advisory locks de otros subsistemas. Arbitrario pero estable.
_LOCK_NS_BARRIDO = 0x4B53  # 'KS'


def _clave_lock(nombre: str) -> int:
    """Deriva una clave estable de 32 bits (con signo) para un advisory lock a partir de texto."""
    h = int.from_bytes(hashlib.blake2b(nombre.encode("utf-8"), digest_size=4).digest(), "big")
    # Postgres usa bigint con signo; `pg_*_advisory_lock(int4, int4)` toma int de 32 bits.
    return h - 0x1_0000_0000 if h >= 0x8000_0000 else h


@contextmanager
def lock_barrido(nombre: str) -> Iterator[bool]:
    """Single-flight CROSS-PROCESO de un barrido. `with lock_barrido("autogen") as ok:`.

    Intenta tomar un advisory lock de Postgres (`pg_try_advisory_lock`, NO bloqueante) keyed
    en `nombre`. `ok` es True si ESTE proceso lo obtuvo (debe ejecutar el barrido) o False si
    otro lo retiene ahora mismo (debe abortar sin hacer nada). El lock se mantiene mientras
    dure el `with` y se suelta SIEMPRE al salir (incluso ante excepcion), sobre una conexion
    propia dedicada que no se reusa para el trabajo. Es no-op-friendly: el caller solo
    comprueba `ok`.
    """
    clave = _clave_lock(nombre)
    con = _conectar()
    obtenido = False
    try:
        fila = con.execute(
            "SELECT pg_try_advisory_lock(?, ?) AS ok", (_LOCK_NS_BARRIDO, clave)
        ).fetchone()
        con.commit()
        obtenido = bool(fila["ok"]) if fila is not None else False
        yield obtenido
    finally:
        if obtenido:
            try:
                con.execute(
                    "SELECT pg_advisory_unlock(?, ?)", (_LOCK_NS_BARRIDO, clave)
                )
                con.commit()
            except Exception:  # noqa: BLE001 -- soltar fallo: DESCARTAR la conexion (no reciclarla).
                # CRITICO con pool: si el unlock falla y la conexion VOLVIERA al pool, el lock de
                # SESION seguiria pegado a ese socket reciclado y TODOS los `lock_barrido`
                # posteriores verian ok=False hasta el reciclado (~1 h): single-flight envenenado.
                # `descartar()` cierra el socket (el servidor libera los locks de sesion) y deja
                # que el pool reponga una conexion fresca. El `close()` de abajo queda como no-op.
                _log.warning(
                    "No se pudo soltar el advisory lock de barrido %s; se descarta la conexion.",
                    nombre,
                )
                descartar = getattr(con, "descartar", None)
                if descartar is not None:
                    descartar()
        con.close()


# --------------------------------------------------------------------------- #
# Arranque de la persistencia                                                  #
# --------------------------------------------------------------------------- #


def arrancar_persistencia() -> None:
    """Crea el esquema operacional on-demand en el arranque (idempotente).

    Abre Postgres (`DATABASE_URL` obligatoria, ADR 0004) y crea/migra el esquema, de modo
    que el back arranca con las tablas listas por cualquier via. Si falta `DATABASE_URL`,
    `motor_db.conectar_cruda()` lanza un `RuntimeError` accionable (no se traga: un back sin
    Postgres no debe servir). El antiguo guardia anti-orfanamiento SQLite->Postgres se
    retiro con SQLite (ADR 0004): ya no hay un origen local que orfanar.
    """
    _conectar().close()  # crea/migra el esquema y cierra


# DDL del esquema operacional, como sentencias INDIVIDUALES (no un script multi-sentencia
# `executescript`, exclusivo de sqlite3): se ejecutan una a una via `con.execute`. El DDL
# se mantiene portable (heredado de cuando coexistia SQLite): tipos `TEXT`/`INTEGER`,
# `PRIMARY KEY`, `UNIQUE`, `NOT NULL DEFAULT ''` y `CREATE [UNIQUE] INDEX IF NOT EXISTS` son
# todos validos en Postgres 16. Los ids son TEXT generados por la app (uuid), no
# autoincrementales: no hay `AUTOINCREMENT`/`SERIAL`.
_DDL_ESQUEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS comercial_publicaciones (
        id                   TEXT PRIMARY KEY,
        url                  TEXT NOT NULL DEFAULT '',
        id_post_metricool    TEXT NOT NULL DEFAULT '',
        titulo               TEXT NOT NULL DEFAULT '',
        marca                TEXT NOT NULL DEFAULT '',
        cliente              TEXT NOT NULL DEFAULT '',
        campania             TEXT NOT NULL DEFAULT '',
        red                  TEXT NOT NULL DEFAULT '',
        formato              TEXT NOT NULL DEFAULT '',
        metrica_objetivo     TEXT NOT NULL DEFAULT 'interacciones',
        objetivo             INTEGER NOT NULL DEFAULT 0,
        estado               TEXT NOT NULL DEFAULT 'activa',
        publicado            TEXT NOT NULL DEFAULT '',
        notas                TEXT NOT NULL DEFAULT '',
        aviso_en             TEXT NOT NULL DEFAULT '',
        fecha_creacion       TEXT NOT NULL DEFAULT '',
        fecha_actualizacion  TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comercial_snapshots (
        id              TEXT PRIMARY KEY,
        publicacion_id  TEXT NOT NULL,
        ts              TEXT NOT NULL,
        interacciones   INTEGER NOT NULL DEFAULT 0,
        visualizaciones INTEGER NOT NULL DEFAULT 0,
        alcance         INTEGER NOT NULL DEFAULT 0,
        likes                          INTEGER NOT NULL DEFAULT 0,
        comentarios                    INTEGER NOT NULL DEFAULT 0,
        compartidos                    INTEGER NOT NULL DEFAULT 0,
        guardados                      INTEGER NOT NULL DEFAULT 0,
        video_views                    INTEGER NOT NULL DEFAULT 0,
        tiempo_medio_vis_s             INTEGER NOT NULL DEFAULT 0,
        clics_enlace                   INTEGER NOT NULL DEFAULT 0,
        seguidores_netos_atribuidos    INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_comercial_snapshots_pub_ts "
    "ON comercial_snapshots (publicacion_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_comercial_snapshots_pub "
    "ON comercial_snapshots (publicacion_id)",
    # Campañas comerciales: agrupan piezas por uno o varios HASHTAGS configurables, y
    # pueden abarcar VARIAS marcas (multimarca). No monitorizan piezas sueltas (eso era
    # `comercial_publicaciones`, retirado de la UI): definen un filtro (marcas + hashtags) y
    # la analítica se computa AL VUELO sobre el listado de piezas del periodo
    # (`servicio.construir_listado_piezas`, por cada marca), cruzando por los hashtags del
    # caption (`Pieza.texto`). `marcas` y `hashtags` son arrays JSON (ids de marca; tags sin
    # '#', con su casing); portables SQLite/Postgres como TEXT. La columna `marca` (singular)
    # es vestigial: queda para que las BDs antiguas conserven su valor durante la migración a
    # `marcas` (ver `_migrar_columnas_campanias`); el código solo lee/escribe `marcas`.
    """
    CREATE TABLE IF NOT EXISTS comercial_campanias (
        id                   TEXT PRIMARY KEY,
        marca                TEXT NOT NULL DEFAULT '',
        marcas               TEXT NOT NULL DEFAULT '[]',
        nombre               TEXT NOT NULL DEFAULT '',
        hashtags             TEXT NOT NULL DEFAULT '[]',
        activa               INTEGER NOT NULL DEFAULT 1,
        fecha_creacion       TEXT NOT NULL DEFAULT '',
        fecha_actualizacion  TEXT NOT NULL DEFAULT ''
    )
    """,
    # Histórico de métricas por pieza para TODAS las publicaciones (no solo el módulo
    # comercial): una fila por pieza por refresco del daemon, para análisis temporales
    # (velocidad, curvas de crecimiento, correlación) por marca×red×formato. A diferencia de
    # `metricas_cache` (valor ACTUAL, sobrescrito), esta tabla es la SERIE histórica; a
    # diferencia de `comercial_snapshots` (seguimiento de OBJETIVOS de piezas comerciales),
    # esta es GENERAL. El crecimiento lo acota la poda por retención (ADR 0007).
    """
    CREATE TABLE IF NOT EXISTS metricas_pieza_snapshots (
        id                             TEXT PRIMARY KEY,
        pieza_id                       TEXT NOT NULL,
        marca                          TEXT NOT NULL DEFAULT '',
        red                            TEXT NOT NULL DEFAULT '',
        formato                        TEXT NOT NULL DEFAULT '',
        ts                             TEXT NOT NULL,
        visualizaciones                INTEGER NOT NULL DEFAULT 0,
        interacciones                  INTEGER NOT NULL DEFAULT 0,
        alcance                        INTEGER NOT NULL DEFAULT 0,
        engagement_pct                 REAL    NOT NULL DEFAULT 0,
        likes                          INTEGER NOT NULL DEFAULT 0,
        comentarios                    INTEGER NOT NULL DEFAULT 0,
        compartidos                    INTEGER NOT NULL DEFAULT 0,
        guardados                      INTEGER NOT NULL DEFAULT 0,
        video_views                    INTEGER NOT NULL DEFAULT 0,
        tiempo_medio_vis_s             INTEGER NOT NULL DEFAULT 0,
        clics_enlace                   INTEGER NOT NULL DEFAULT 0,
        seguidores_netos_atribuidos    INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_metricas_pieza_snapshots_pieza_ts "
    "ON metricas_pieza_snapshots (pieza_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_metricas_pieza_snapshots_marca_red_ts "
    "ON metricas_pieza_snapshots (marca, red, ts)",
    "CREATE INDEX IF NOT EXISTS idx_metricas_pieza_snapshots_pieza "
    "ON metricas_pieza_snapshots (pieza_id)",
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id                     TEXT PRIMARY KEY,
        usuario                TEXT NOT NULL UNIQUE,
        rol                    TEXT NOT NULL DEFAULT 'editor',
        salt                   TEXT NOT NULL,
        hash                   TEXT NOT NULL,
        debe_cambiar_password  INTEGER NOT NULL DEFAULT 0,
        intentos_fallidos      INTEGER NOT NULL DEFAULT 0,
        bloqueo_hasta          TEXT NOT NULL DEFAULT '',
        creado                 TEXT NOT NULL DEFAULT '',
        ultimo_acceso          TEXT NOT NULL DEFAULT '',
        cargo                  TEXT NOT NULL DEFAULT '',
        cobertura              INTEGER NOT NULL DEFAULT 0,
        puede_coordinar        BOOLEAN NOT NULL DEFAULT FALSE,
        nombre                 TEXT NOT NULL DEFAULT '',
        manager_id             TEXT NOT NULL DEFAULT '',
        -- MFA PASSKEYS / WebAuthn (segundo factor, gateado por `KENI_CONSOLA_MFA`). ADITIVAS y
        -- con DEFAULT, de modo que un usuario legado nace SIN MFA (`mfa_activo=0`) y el login no
        -- cambia. Las CREDENCIALES (clave publica + sign_count) viven en `webauthn_credenciales`
        -- (1:N); aqui solo el flag derivado y los recovery.
        --   - mfa_activo: 1 = el usuario tiene >=1 passkey (se enciende al registrar la primera
        --     y se apaga al borrar la ultima o al reset admin).
        --   - mfa_recovery_codes: JSON con la lista de codigos de recuperacion HASHEADOS
        --     (scrypt, mismo hasher que la contrasena); cada uno se consume de un solo uso.
        -- (La columna TOTP `mfa_secret_cifrado` se ELIMINO al pasar a passkeys; ver
        --  `_migrar_columnas_usuarios`, que la dropa idempotentemente en BDs viejas.)
        mfa_activo             INTEGER NOT NULL DEFAULT 0,
        mfa_recovery_codes     TEXT NOT NULL DEFAULT '[]'
    )
    """,
    # Passkeys (WebAuthn/FIDO2): una credencial publica por dispositivo enrolado. Un usuario
    # puede tener VARIAS (telefono, laptop, llave). El "secreto" (clave privada) NUNCA llega
    # aqui: solo guardamos la clave PUBLICA y el contador de firmas (anti-clonado).
    #   - credential_id: id de la credencial en base64url (UNIQUE global: lo asigna el
    #     autenticador). public_key: COSE public key en base64url. transports: JSON con las
    #     pistas de transporte (["internal","hybrid"...]). sign_count: contador del autenticador.
    #     nombre: etiqueta humana que pone el usuario ("iPhone de Ana"). Borrar el usuario
    #     propaga (ON DELETE CASCADE).
    """
    CREATE TABLE IF NOT EXISTS webauthn_credenciales (
        id             TEXT PRIMARY KEY,
        usuario_id     TEXT NOT NULL,
        credential_id  TEXT NOT NULL UNIQUE,
        public_key     TEXT NOT NULL,
        sign_count     INTEGER NOT NULL DEFAULT 0,
        transports     TEXT NOT NULL DEFAULT '[]',
        nombre         TEXT NOT NULL DEFAULT '',
        creada         TEXT NOT NULL DEFAULT '',
        ultimo_uso     TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_webauthn_cred_usuario ON webauthn_credenciales (usuario_id)",
    """
    CREATE TABLE IF NOT EXISTS sesiones (
        token       TEXT PRIMARY KEY,
        usuario_id  TEXT NOT NULL,
        creada      TEXT NOT NULL,
        ultimo_uso  TEXT NOT NULL,
        expira      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones (usuario_id)",
    # Relacion N:M usuarios <-> marcas (organigrama AMX, transcripciones de Bernardo):
    # una persona puede pertenecer a varias verticales/marcas (Yustine cubre ClaroSports +
    # UnoTV + Piso 15; Bernardo a todas). `marca_id` se valida en la capa API contra el
    # catalogo canonico (`keni_shared.marcas`) — no es FK en la BD porque las marcas viven
    # en TOML/codigo, no en SQL. Borrar un usuario propaga (ON DELETE CASCADE).
    """
    CREATE TABLE IF NOT EXISTS usuarios_marcas (
        usuario_id  TEXT NOT NULL,
        marca_id    TEXT NOT NULL,
        PRIMARY KEY (usuario_id, marca_id),
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_usuarios_marcas_marca ON usuarios_marcas (marca_id)",
    # `tipo_cobertura`/`prioridad`/`cambiado`/`actualizado` (ola B): el evento ya no es
    # solo "que sacar"; lleva COMO se cubre (transmision|imagenes|no_cubrir), su PRIORIDAD
    # y si se REPROGRAMO (`cambiado`=1: hay que volver a avisar al equipo). `actualizado`
    # se refresca en cada edicion. Para bases NUEVAS se declaran aqui; las viejas las
    # migra `_migrar_columnas_eventos_rota` (idempotente, solo SQLite).
    """
    CREATE TABLE IF NOT EXISTS rota_eventos (
        id             TEXT PRIMARY KEY,
        titulo         TEXT NOT NULL,
        fecha          TEXT NOT NULL DEFAULT '',
        hora           TEXT NOT NULL DEFAULT '',
        contenido      TEXT NOT NULL DEFAULT '',
        nota           TEXT NOT NULL DEFAULT '',
        tipo_cobertura TEXT NOT NULL DEFAULT 'transmision',
        prioridad      TEXT NOT NULL DEFAULT 'media',
        cambiado       INTEGER NOT NULL DEFAULT 0,
        actualizado    TEXT NOT NULL DEFAULT '',
        creado         TEXT NOT NULL DEFAULT '',
        origen         TEXT NOT NULL DEFAULT '',
        origen_ref     TEXT NOT NULL DEFAULT '',
        marca          TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_eventos_fecha ON rota_eventos (fecha)",
    "CREATE INDEX IF NOT EXISTS idx_rota_eventos_marca ON rota_eventos (marca)",
    # FRANJAS POR SEMANA (#XYZ "Mundial"): el feedback real del piloto AMX descubrio
    # semanas con coberturas atipicas (Mundial, eventos grandes) con MAS de 2 franjas y
    # CON SOLAPES (ej. semana 24 jun 2026: 09:00-17:00, 13:00-21:00, 17:00-01:00). El
    # modelo viejo (`Franja = matutino|vespertino|descanso` literal en `rota_turnos.franja`)
    # no lo soportaba. Ahora cada SEMANA tiene sus propias franjas: nombre libre, rangos
    # HH:MM, solapes permitidos y `fin <= inicio` indica franja que cruza medianoche.
    # `rota_config_franjas` (singleton) sigue existiendo como plantilla por defecto al
    # sembrar las 2 franjas de trabajo iniciales ("Mañana", "Tarde") de una semana nueva.
    #
    # `es_descanso`: marca una franja como "no laboral" (turno planificado de descanso). El
    # usuario aclaro: el descanso NO es ausencia implicita, es un turno explicito asignado a
    # la persona ese dia. La franja descanso NO cubre ningun evento (`franjas_activas_en`
    # la EXCLUYE). Sirve para que la UI muestre una fila "Descanso" en la rejilla donde el
    # admin marca quien no trabaja ese dia (distinto de "olvido de asignacion").
    """
    CREATE TABLE IF NOT EXISTS rota_franjas (
        id           TEXT PRIMARY KEY,
        lunes        TEXT NOT NULL,
        nombre       TEXT NOT NULL,
        inicio       TEXT NOT NULL,
        fin          TEXT NOT NULL,
        orden        INTEGER NOT NULL DEFAULT 0,
        es_descanso  BOOLEAN NOT NULL DEFAULT FALSE,
        marca        TEXT NOT NULL DEFAULT ''
    )
    """,
    # GRID POR MARCA: cada marca tiene su propia rejilla (franjas, turnos, coordinacion). La
    # `marca` la sembramos/filtramos en toda lectura/escritura del grid; "" = sin marca (solo
    # filas legadas antes de la migracion, backfilled a 'claro-sports'). La unicidad del NOMBRE
    # de franja es POR (marca, lunes, nombre) — dos marcas pueden tener su propia "Mañana" la
    # misma semana — y vive como indice unico idempotente (`idx_rota_franjas_uniq`), no inline
    # (la BD vieja trae UNIQUE(lunes,nombre), que `_asegurar_marca_grid_rota` dropa).
    "CREATE INDEX IF NOT EXISTS idx_rota_franjas_lunes ON rota_franjas (lunes)",
    "CREATE INDEX IF NOT EXISTS idx_rota_franjas_marca ON rota_franjas (marca)",
    # TURNO = horario del miembro en (fecha, franja_id). NO esta atado a un evento concreto.
    # Cambio de modelo (#XYZ "franjas por semana"): el `franja` literal de tres valores
    # ('matutino'/'vespertino'/'descanso') desaparece. Ahora cada turno apunta a una
    # `franja_id` de `rota_franjas` (definidas por semana, con nombre libre y solapes).
    # El "descanso" sigue existiendo como FRANJA explicita (con `es_descanso=true`) en cada
    # semana: una persona con turno en la franja Descanso esta planificada para no trabajar
    # ese dia (distinto de "olvido de asignacion"). La migracion (`_migrar_modelo_franjas`):
    #   - siembra ("Mañana"/"Tarde"/"Descanso") en cada semana con turnos legados (usando
    #     `rota_config_franjas` como plantilla para las dos primeras),
    #   - asigna `franja_id` a los turnos PRESERVANDO los de `franja='descanso'`.
    """
    CREATE TABLE IF NOT EXISTS rota_turnos (
        id             TEXT PRIMARY KEY,
        semana         TEXT NOT NULL,
        fecha          TEXT NOT NULL DEFAULT '',
        miembro_id     TEXT NOT NULL DEFAULT '',
        miembro_nombre TEXT NOT NULL DEFAULT '',
        franja_id      TEXT NOT NULL DEFAULT '',
        estado         TEXT NOT NULL DEFAULT 'propuesto',
        override       INTEGER NOT NULL DEFAULT 0,
        motivo         TEXT NOT NULL DEFAULT '',
        nota_relevo    TEXT NOT NULL DEFAULT '',
        creado         TEXT NOT NULL DEFAULT '',
        actualizado    TEXT NOT NULL DEFAULT '',
        origen         TEXT NOT NULL DEFAULT '',
        origen_ref     TEXT NOT NULL DEFAULT '',
        marca          TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_semana ON rota_turnos (semana)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_miembro ON rota_turnos (miembro_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_fecha ON rota_turnos (fecha)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_franja_id ON rota_turnos (franja_id)",
    # GRID POR MARCA: el turno pertenece a la rejilla de UNA marca. `listar_turnos_rota`
    # filtra por (semana, marca?); en "Todas" (marca None) NO filtra y devuelve todas, que la
    # UI apila etiquetando cada turno con su marca.
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_marca ON rota_turnos (marca)",
    # Ausencias/vacaciones del horario (F4 · #144): un rango de fechas (inclusivo) en que un
    # miembro NO esta disponible. El proponedor del horario las RESPETA (excluye al miembro
    # esos dias). `tipo` es vacaciones|descanso|baja|otro.
    """
    CREATE TABLE IF NOT EXISTS rota_ausencias (
        id             TEXT PRIMARY KEY,
        miembro_id     TEXT NOT NULL DEFAULT '',
        miembro_nombre TEXT NOT NULL DEFAULT '',
        tipo           TEXT NOT NULL DEFAULT 'otro',
        desde          TEXT NOT NULL DEFAULT '',
        hasta          TEXT NOT NULL DEFAULT '',
        motivo         TEXT NOT NULL DEFAULT '',
        creado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_ausencias_miembro ON rota_ausencias (miembro_id)",
    # Piezas de la PARRILLA (#150, PARRILLA 2026.xlsx): en el Excel de Tescu cada FILA es un
    # POST individual, no un evento. Una transmision (p. ej. "LIV GOLF Andalucia R1") genera
    # varias piezas: pre-evento FB/IG/X, reel IG/TK, historia "5:15 LINK VIVO", post-evento.
    # Tambien hay campanas EVERGREEN sin evento (Alvaro Fidalgo, Real Oviedo, MUNDIAL, Paty
    # Cantu): piezas con `programa` y sin `evento_id`. El workflow de produccion del Excel
    # ("Material entregado / Contenido entregado / Publicado / Enlace") se persiste tal cual.
    # `evento_id` queda como FK textual a `rota_eventos` ("" para piezas sueltas); no hay
    # FOREIGN KEY a nivel DB (el borrado del evento NO arrastra sus piezas: la API decide).
    """
    CREATE TABLE IF NOT EXISTS rota_piezas (
        id                      TEXT PRIMARY KEY,
        evento_id               TEXT NOT NULL DEFAULT '',
        programa                TEXT NOT NULL DEFAULT '',
        red_social              TEXT NOT NULL DEFAULT '',
        tipo_pieza              TEXT NOT NULL DEFAULT '',
        contenido_sugerido      TEXT NOT NULL DEFAULT '',
        dia                     TEXT NOT NULL DEFAULT '',
        hora_post               TEXT NOT NULL DEFAULT '',
        estado                  TEXT NOT NULL DEFAULT 'pendiente',
        material_entregado      INTEGER NOT NULL DEFAULT 0,
        contenido_entregado     INTEGER NOT NULL DEFAULT 0,
        publicado               INTEGER NOT NULL DEFAULT 0,
        enlace                  TEXT NOT NULL DEFAULT '',
        responsable_id          TEXT NOT NULL DEFAULT '',
        responsable_nombre      TEXT NOT NULL DEFAULT '',
        notas                   TEXT NOT NULL DEFAULT '',
        salida                  TEXT NOT NULL DEFAULT '',
        comentarios             TEXT NOT NULL DEFAULT '',
        fecha_entrega_material  TEXT NOT NULL DEFAULT '',
        always_on               INTEGER NOT NULL DEFAULT 0,
        creado                  TEXT NOT NULL DEFAULT '',
        actualizado             TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_piezas_evento ON rota_piezas (evento_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_piezas_dia ON rota_piezas (dia)",
    "CREATE INDEX IF NOT EXISTS idx_rota_piezas_programa ON rota_piezas (programa)",
    "CREATE INDEX IF NOT EXISTS idx_rota_piezas_responsable ON rota_piezas (responsable_id)",
    # Tablero de CONTENIDO unificado (herramienta de community manager): un padre
    # `contenido` (item del tablero: importante del dia / evergreen / evento, o tarea
    # libre) y N filas `contenido_plataforma` (una por red, con su estado y checklist).
    # Una "publicacion" del flujo editorial = una fila `contenido_plataforma` unida a su
    # padre (ver `ficheros.py`/`repos.py`). Operacional; Postgres (ADR 0004).
    """
    CREATE TABLE IF NOT EXISTS contenido (
        id                  TEXT PRIMARY KEY,
        clase               TEXT NOT NULL DEFAULT 'contenido',
        flujo               TEXT NOT NULL DEFAULT '',
        titulo              TEXT NOT NULL DEFAULT '',
        descripcion         TEXT NOT NULL DEFAULT '',
        marca               TEXT NOT NULL DEFAULT '',
        evento_id           TEXT NOT NULL DEFAULT '',
        programa            TEXT NOT NULL DEFAULT '',
        prioridad           TEXT NOT NULL DEFAULT 'media',
        estado              TEXT NOT NULL DEFAULT 'pendiente',
        fecha_objetivo      TEXT NOT NULL DEFAULT '',
        hora_objetivo       TEXT NOT NULL DEFAULT '',
        fecha_entrega       TEXT NOT NULL DEFAULT '',
        responsable_id      TEXT NOT NULL DEFAULT '',
        responsable_nombre  TEXT NOT NULL DEFAULT '',
        autor_id            TEXT NOT NULL DEFAULT '',
        autor_nombre        TEXT NOT NULL DEFAULT '',
        origen              TEXT NOT NULL DEFAULT '',
        notas               TEXT NOT NULL DEFAULT '',
        tipo_contenido      TEXT NOT NULL DEFAULT 'ia',
        formato             TEXT NOT NULL DEFAULT 'foto',
        id_post_metricool   TEXT NOT NULL DEFAULT '',
        senal_viralidad     INTEGER NOT NULL DEFAULT 0,
        espejo              INTEGER NOT NULL DEFAULT 1,
        qa_veredicto        TEXT NOT NULL DEFAULT '',
        qa_hallazgos        TEXT NOT NULL DEFAULT '',
        copy_pendiente      TEXT NOT NULL DEFAULT '',
        fecha_fuente        TEXT NOT NULL DEFAULT '',
        url_fuente          TEXT NOT NULL DEFAULT '',
        fuente_nombre       TEXT NOT NULL DEFAULT '',
        creado              TEXT NOT NULL DEFAULT '',
        actualizado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_contenido_flujo ON contenido (flujo)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_marca ON contenido (marca)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_evento ON contenido (evento_id)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_responsable ON contenido (responsable_id)",
    # Orden del feed/keyset (`ORDER BY c.creado DESC, cp.id DESC` + `c.creado < ?`) y de los
    # barridos por recencia (`titulos_recientes_marca`, dedup 90d): sin este indice cada pagina
    # del feed era un scan+sort de la tabla entera.
    "CREATE INDEX IF NOT EXISTS idx_contenido_creado_id ON contenido (creado DESC, id DESC)",
    """
    CREATE TABLE IF NOT EXISTS contenido_plataforma (
        id                    TEXT PRIMARY KEY,
        contenido_id          TEXT NOT NULL DEFAULT '',
        red                   TEXT NOT NULL DEFAULT '',
        -- `marca` DENORMALIZADA del padre `contenido`: existe SOLO para que el indice unico
        -- parcial de parrilla (idx_parrilla_slot_uniq) pueda scope-arse POR MARCA sin cruzar el
        -- join (un indice parcial no puede). Se mantiene en sync en TODA escritura (insert + cambio
        -- de marca del padre). Las LECTURAS siguen tomando la marca de `c.marca` (parent), no de aqui.
        marca                 TEXT NOT NULL DEFAULT '',
        estado                TEXT NOT NULL DEFAULT 'pendiente',
        falta_copy            INTEGER NOT NULL DEFAULT 1,
        falta_imagen          INTEGER NOT NULL DEFAULT 1,
        falta_revision        INTEGER NOT NULL DEFAULT 1,
        falta_publicar        INTEGER NOT NULL DEFAULT 1,
        -- `falta_video`: checklist del asset de VIDEO (espejo de `falta_imagen`). Solo cuenta
        -- cuando la pieza padre es `formato='video'`; en piezas `foto` se mantiene en 0 (N/A).
        falta_video           INTEGER NOT NULL DEFAULT 0,
        copy                  TEXT NOT NULL DEFAULT '',
        copy_in               TEXT NOT NULL DEFAULT '',
        imagen                TEXT NOT NULL DEFAULT '',
        imagen_fuente         TEXT NOT NULL DEFAULT '',
        foto                  TEXT NOT NULL DEFAULT '',
        -- `video`: clave del asset de video en el almacen de media (`videos/<sha256>.<ext>`),
        -- espejo de `imagen`. "" = sin video adjunto. Lo usa el programador para publicar
        -- `TipoMedia.video` cuando la pieza es `formato='video'`.
        video                 TEXT NOT NULL DEFAULT '',
        veredicto             TEXT NOT NULL DEFAULT '',
        revisor_id            TEXT NOT NULL DEFAULT '',
        revisor_nombre        TEXT NOT NULL DEFAULT '',
        revisado_en           TEXT NOT NULL DEFAULT '',
        enviado_a_revision_en TEXT NOT NULL DEFAULT '',
        fecha_programada      TEXT NOT NULL DEFAULT '',
        preparado_en          TEXT NOT NULL DEFAULT '',
        id_post_metricool     TEXT NOT NULL DEFAULT '',
        enlace                TEXT NOT NULL DEFAULT '',
        evergreen             INTEGER NOT NULL DEFAULT 0,
        es_publicacion        INTEGER NOT NULL DEFAULT 0,
        copy_in_exento        INTEGER NOT NULL DEFAULT 0,
        placa_oculta          INTEGER NOT NULL DEFAULT 0,
        plantilla_diseno_id   TEXT NOT NULL DEFAULT '',
        foto_encuadre         TEXT NOT NULL DEFAULT '',
        fotos                 TEXT NOT NULL DEFAULT '',
        -- `carrusel`: slides EXTRA de una pieza `formato='carrusel'` (la portada es la
        -- imagen compuesta de siempre). JSON array `[{"tipo":"imagen"|"video","objeto":id}, …]`
        -- en el ORDEN de publicación; "" = sin slides extra (o pieza de otro formato).
        carrusel              TEXT NOT NULL DEFAULT '',
        qa_auto_hash          TEXT NOT NULL DEFAULT '',
        hora_post             TEXT NOT NULL DEFAULT '',
        creado                TEXT NOT NULL DEFAULT '',
        actualizado           TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_contenido_plat_contenido ON contenido_plataforma (contenido_id)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_plat_red ON contenido_plataforma (red)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_plat_estado ON contenido_plataforma (estado)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_plat_programada ON contenido_plataforma (fecha_programada)",
    # OLA COLABORACION (inspirada en Planable: internal notes, version history, multi-level
    # approval). Tres tablas APENDIDAS al modelo `contenido`/`contenido_plataforma`, sin
    # tocar su esquema: hilo de comentarios por pieza, historial de versiones del copy y
    # cadena de aprobacion multinivel con trazabilidad. Operacional; vive en Postgres.
    #
    # Comentarios internos: hilo de discusion de redaccion por item de `contenido` (el padre,
    # asi cubre tanto contenido publicable como tarea libre). `plataforma_id` opcional ata el
    # comentario a UNA red concreta (""=comentario del item entero). `resuelto` marca un hilo
    # cerrado sin borrarlo (trazabilidad). Borrado real solo por el autor/admin (capa API).
    """
    CREATE TABLE IF NOT EXISTS contenido_comentarios (
        id            TEXT PRIMARY KEY,
        contenido_id  TEXT NOT NULL DEFAULT '',
        plataforma_id TEXT NOT NULL DEFAULT '',
        autor_id      TEXT NOT NULL DEFAULT '',
        autor_nombre  TEXT NOT NULL DEFAULT '',
        texto         TEXT NOT NULL DEFAULT '',
        resuelto      INTEGER NOT NULL DEFAULT 0,
        creado        TEXT NOT NULL DEFAULT '',
        actualizado   TEXT NOT NULL DEFAULT '',
        -- ids de usuarios MENCIONADOS (@) en el comentario, separados por coma ("" = ninguno).
        -- Una mencion notifica a esa persona y la deja SUSCRITA a la pieza (cajon de notis).
        menciones     TEXT NOT NULL DEFAULT ''
    )
    """,
    # `menciones` se anadio despues del CREATE original: ALTER idempotente para BD existentes.
    "ALTER TABLE contenido_comentarios ADD COLUMN IF NOT EXISTS menciones TEXT NOT NULL DEFAULT ''",
    # CATEGORÍA del plan editorial con la que nació el contenido ('' = sin línea: alta manual).
    # Copiada de la HISTORIA al promover/usar ('breaking' si lo era) o 'evergreen' al reciclar:
    # la relación fuente→tipo de contenido queda EN la pieza (el GC del pool borra clusters
    # viejos y el join dejaba de contar/programar bien). La leen el conteo del plan diario y
    # los horarios por categoría.
    "ALTER TABLE contenido ADD COLUMN IF NOT EXISTS categoria TEXT NOT NULL DEFAULT ''",
    "CREATE INDEX IF NOT EXISTS idx_coment_contenido ON contenido_comentarios (contenido_id)",
    "CREATE INDEX IF NOT EXISTS idx_coment_plataforma ON contenido_comentarios (plataforma_id)",
    # Historial de versiones del COPY de una fila por plataforma. Cada vez que el copy de una
    # `contenido_plataforma` cambia (via la API de versiones), se guarda un SNAPSHOT inmutable
    # del texto ANTERIOR antes de pisarlo, con quien y cuando. `version` es un contador
    # incremental por plataforma (1, 2, 3...). Revertir = aplicar el texto de una version vieja
    # como copy actual (que a su vez genera otro snapshot del que se pisa: nunca se pierde nada).
    """
    CREATE TABLE IF NOT EXISTS contenido_copy_versiones (
        id            TEXT PRIMARY KEY,
        plataforma_id TEXT NOT NULL DEFAULT '',
        contenido_id  TEXT NOT NULL DEFAULT '',
        version       INTEGER NOT NULL DEFAULT 0,
        copy          TEXT NOT NULL DEFAULT '',
        autor_id      TEXT NOT NULL DEFAULT '',
        autor_nombre  TEXT NOT NULL DEFAULT '',
        nota          TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_copyver_plataforma ON contenido_copy_versiones (plataforma_id)",
    # Aprobacion MULTINIVEL de una fila por plataforma. La aprobacion editorial deja de ser un
    # unico "otro par de ojos" y pasa a una CADENA de niveles configurable (p. ej. edicion ->
    # coordinacion -> direccion). Cada registro es la decision de UN nivel sobre la pieza:
    # `nivel` (1-based, orden de la cadena), `etiqueta` legible, `decision`
    # (pendiente/aprobado/rechazado), quien decidio y cuando, mas un `comentario` opcional.
    # La pieza queda totalmente aprobada cuando TODOS sus niveles estan en `aprobado`; un
    # `rechazado` en cualquier nivel para la cadena. Trazabilidad completa (quien, que, cuando).
    """
    CREATE TABLE IF NOT EXISTS contenido_aprobaciones (
        id               TEXT PRIMARY KEY,
        plataforma_id    TEXT NOT NULL DEFAULT '',
        contenido_id     TEXT NOT NULL DEFAULT '',
        nivel            INTEGER NOT NULL DEFAULT 1,
        etiqueta         TEXT NOT NULL DEFAULT '',
        decision         TEXT NOT NULL DEFAULT 'pendiente',
        decisor_id       TEXT NOT NULL DEFAULT '',
        decisor_nombre   TEXT NOT NULL DEFAULT '',
        comentario       TEXT NOT NULL DEFAULT '',
        creado           TEXT NOT NULL DEFAULT '',
        decidido_en      TEXT NOT NULL DEFAULT '',
        -- Cargo del organigrama EXIGIDO para decidir este nivel ("" = sin requisito). Item C:
        -- p. ej. "Coordinación" la decide un coordinador, "Dirección" un director.
        cargo_requerido  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_aprob_plataforma ON contenido_aprobaciones (plataforma_id)",
    "CREATE INDEX IF NOT EXISTS idx_aprob_decision ON contenido_aprobaciones (decision)",
    # Programas/campanas evergreen (#150). En el Excel cada hoja evergreen ("Álvaro Fidalgo",
    # "Real Oviedo", "Anfitriones", "PATY CANTU", "MUNDIAL", "LA SELECCIÓN EN TUS MANOS",
    # "IDEAS SIN DERECHOS") es un PROGRAMA con sus propias piezas. Aqui catalogamos los
    # programas para tener color/descripcion/fechas vivas; `rota_piezas.programa` referencia
    # a este catalogo POR NOMBRE (case-sensitive) y NO por id (defensa: una pieza huerfana
    # con un programa borrado sigue mostrandose). `nombre` UNIQUE (case-insensitive lo
    # garantiza la capa API/repos). `activo` para esconder del selector sin perder histórico.
    """
    CREATE TABLE IF NOT EXISTS rota_programas (
        id           TEXT PRIMARY KEY,
        nombre       TEXT NOT NULL UNIQUE,
        descripcion  TEXT NOT NULL DEFAULT '',
        color        TEXT NOT NULL DEFAULT '',
        inicio       TEXT NOT NULL DEFAULT '',
        fin          TEXT NOT NULL DEFAULT '',
        activo       INTEGER NOT NULL DEFAULT 1,
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_programas_activo ON rota_programas (activo)",
    # Configuracion de FRANJAS (#185): los rangos horarios de matutino/vespertino son
    # editoriales del equipo y se editan desde la UI. GRID POR MARCA: una fila POR MARCA —
    # `id` guarda el id de la marca (antes era el singleton `id='default'`, reclavado a
    # 'claro-sports' por `_asegurar_marca_grid_rota`). Si no existe, los endpoints devuelven
    # los defaults del dominio.
    # Aplica al endpoint `POST /api/rota/cobertura/asignar-franja` (que llama a
    # `dominio.mapear_franja` con estos valores). Inicios INCLUSIVOS, finales EXCLUSIVOS.
    """
    CREATE TABLE IF NOT EXISTS rota_config_franjas (
        id                  TEXT PRIMARY KEY,
        matutino_inicio     TEXT NOT NULL DEFAULT '08:00',
        matutino_fin        TEXT NOT NULL DEFAULT '16:00',
        vespertino_inicio   TEXT NOT NULL DEFAULT '16:00',
        vespertino_fin      TEXT NOT NULL DEFAULT '24:00',
        actualizado         TEXT NOT NULL DEFAULT ''
    )
    """,
    # Solicitudes de cambio de turno entre compañeros (#175): cuando un CM (A) quiere
    # canjear su turno por el de otro (B) por un asunto personal, crea una solicitud en
    # estado `propuesto`; B acepta/rechaza, y si acepta, Elias (admin) aprueba o rechaza.
    # Al aprobar se ejecuta el swap en `rota_turnos` (intercambia miembro_id) y la
    # solicitud queda `aplicado`. Las ausencias de verdad (vacaciones/baja) siguen en SAP
    # y NO se gestionan aqui. Estados validos: ESTADOS_SWAP (ver `estados.py`).
    """
    CREATE TABLE IF NOT EXISTS rota_swaps_turno (
        id                       TEXT PRIMARY KEY,
        solicitante_id           TEXT NOT NULL,
        solicitante_nombre       TEXT NOT NULL DEFAULT '',
        destinatario_id          TEXT NOT NULL,
        destinatario_nombre      TEXT NOT NULL DEFAULT '',
        fecha_a                  TEXT NOT NULL,
        franja_a                 TEXT NOT NULL,
        fecha_b                  TEXT NOT NULL,
        franja_b                 TEXT NOT NULL,
        motivo                   TEXT NOT NULL DEFAULT '',
        estado                   TEXT NOT NULL DEFAULT 'propuesto',
        respuesta_destinatario   TEXT NOT NULL DEFAULT '',
        respuesta_admin          TEXT NOT NULL DEFAULT '',
        creado                   TEXT NOT NULL DEFAULT '',
        actualizado              TEXT NOT NULL DEFAULT '',
        decidido_destinatario    TEXT NOT NULL DEFAULT '',
        decidido_admin           TEXT NOT NULL DEFAULT '',
        aplicado                 TEXT NOT NULL DEFAULT '',
        marca                    TEXT NOT NULL DEFAULT ''
    )
    """,
    # GRID POR MARCA: el swap es entre turnos de la rejilla de UNA marca. `marca` se
    # DENORMALIZA al crear (del turno A) para poder filtrar las solicitudes por marca.
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_marca ON rota_swaps_turno (marca)",
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_solicitante ON rota_swaps_turno (solicitante_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_destinatario ON rota_swaps_turno (destinatario_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_estado ON rota_swaps_turno (estado)",
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_fechas ON rota_swaps_turno (fecha_a, fecha_b)",
    # COORDINADOR POR TURNO (ola "coord"): cada celda del calendario (fecha, franja_id) puede
    # tener UN coordinador asignado, INDEPENDIENTE del turno de CM. Los candidatos son los
    # usuarios con `puede_coordinar=true` (hoy Elias, Ale, Mariana; lo decide el admin desde
    # /usuarios). UNIQUE(fecha, franja_id): una celda = un coordinador. La tabla es nueva
    # (no hay migracion historica). Borrar un turno o cambiar franja NO borra la coordinacion.
    """
    CREATE TABLE IF NOT EXISTS rota_coordinacion (
        id              TEXT PRIMARY KEY,
        lunes           TEXT NOT NULL,
        fecha           TEXT NOT NULL,
        franja_id       TEXT NOT NULL,
        coordinador_id  TEXT NOT NULL,
        creado          TEXT NOT NULL DEFAULT '',
        actualizado     TEXT NOT NULL DEFAULT '',
        marca           TEXT NOT NULL DEFAULT '',
        UNIQUE (fecha, franja_id)
    )
    """,
    # GRID POR MARCA: la `franja_id` ya es propia de una marca (cada franja lleva su marca),
    # asi que UNIQUE(fecha, franja_id) ya separa por marca de hecho; `marca` se denormaliza
    # para filtrar/etiquetar la coordinacion sin join.
    "CREATE INDEX IF NOT EXISTS idx_rota_coord_lunes ON rota_coordinacion (lunes)",
    "CREATE INDEX IF NOT EXISTS idx_rota_coord_franja ON rota_coordinacion (franja_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_coord_marca ON rota_coordinacion (marca)",
    # PROPUESTA de importacion de la parrilla desde un documento (PDF/imagen/docx/xlsx/txt).
    # El usuario suelta un documento; un `claude -p` READ-ONLY lo lee y PROPONE operaciones
    # (eventos/turnos nuevos, modificaciones) como JSON. La propuesta se ESTACIONA aqui (NO se
    # aplica): el frontend la previsualiza sobre el calendario real y, al aceptar, el back
    # aplica el diff en UNA transaccion. Claude NUNCA escribe en el calendario.
    #   - `estado`: generando|pendiente|aplicada|descartada|error (ver dominio.parrilla_import).
    #   - `doc_nombre`: KEY del objeto en el almacen de media (el documento subido).
    #   - `semana`: lunes ISO de la semana objetivo (todas las ops caen en ella).
    #   - `gen_id`: id del registro de generacion (el job de claude que la produjo).
    #   - `operaciones`: lista JSON de operaciones VALIDADAS (NULL hasta que el job termina).
    #     Se guarda como TEXT/JSON serializado (mismo patron que el resto de columnas JSON del
    #     esquema, portable desde la era SQLite; la app (de)serializa con json.dumps/loads).
    """
    CREATE TABLE IF NOT EXISTS parrilla_propuesta (
        id            TEXT PRIMARY KEY,
        creado        TEXT NOT NULL DEFAULT '',
        actualizado   TEXT NOT NULL DEFAULT '',
        estado        TEXT NOT NULL DEFAULT 'generando',
        autor_id      TEXT NOT NULL DEFAULT '',
        autor_nombre  TEXT NOT NULL DEFAULT '',
        doc_nombre    TEXT NOT NULL DEFAULT '',
        doc_tipo      TEXT NOT NULL DEFAULT '',
        semana        TEXT NOT NULL DEFAULT '',
        gen_id        TEXT NOT NULL DEFAULT '',
        operaciones   TEXT NOT NULL DEFAULT '',
        resumen       TEXT NOT NULL DEFAULT '',
        error         TEXT NOT NULL DEFAULT '',
        marca         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_parrilla_propuesta_estado ON parrilla_propuesta (estado)",
    "CREATE INDEX IF NOT EXISTS idx_parrilla_propuesta_semana ON parrilla_propuesta (semana)",
    "CREATE INDEX IF NOT EXISTS idx_parrilla_propuesta_gen ON parrilla_propuesta (gen_id)",
    # Marca del workspace que disparó el import: se estampa en los `rota_eventos` creados al
    # aplicar, para que la lista de Tareas (filtrada por marca) los muestre. (Import a Tareas.)
    "ALTER TABLE parrilla_propuesta ADD COLUMN IF NOT EXISTS marca TEXT NOT NULL DEFAULT ''",
    # Cola de jobs de generacion (#130 Fase 2 / ADR 0002 Fase B): el back ENCOLA y un
    # WORKER (in-proceso en local, servicio aparte en hosted) los CLAVA y ejecuta `claude
    # -p`. La fila es el "sobre" de despacho: `gen_id` es el registro de generacion
    # (fuente de verdad del sondeo), `spec` el JSON serializable para reconstruir el job
    # (prompt + post-procesado + cwd) en el worker, `estado` el del ciclo de la cola
    # (pendiente|reclamado|terminado), `claimed_at`/`worker` para depurar y reaprovechar
    # jobs huerfanos (un worker que muere a media ejecucion). `cancelado` lo marca el back
    # al cancelar: el worker lo lee y mata el arbol (cancelacion cross-proceso).
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id          TEXT PRIMARY KEY,
        gen_id      TEXT NOT NULL,
        spec        TEXT NOT NULL,
        estado      TEXT NOT NULL DEFAULT 'pendiente',
        cancelado   INTEGER NOT NULL DEFAULT 0,
        worker      TEXT NOT NULL DEFAULT '',
        creado      TEXT NOT NULL DEFAULT '',
        claimed_at  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_estado ON jobs (estado)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_gen ON jobs (gen_id)",
    # PRIORIDAD de despacho (entero, mayor = antes): un lanzamiento MANUAL del equipo
    # (API/MCP) no debe esperar detras del lote del pipeline/autogen. `reclamar_job` ordena
    # por (prioridad DESC, creado ASC). Migracion idempotente para BDs existentes.
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS prioridad INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS idx_jobs_estado_prioridad "
    "ON jobs (estado, prioridad DESC, creado ASC)",
    # INTENTOS de ejecucion (anti crash-loop): se incrementa en cada reclamo (normal o
    # re-reclamo de huerfano). Al superar `KENI_JOBS_MAX_INTENTOS`, el re-reclamo DESCARTA
    # el job en vez de re-ejecutarlo para siempre. Migracion idempotente.
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS intentos INTEGER NOT NULL DEFAULT 0",
    # LEDGER de gasto de IA (economia de tokens, ver `presupuesto_ia.py`): una fila por
    # GENERACION CERRADA (terminal completado/error) con sus tokens/coste. La escribe el
    # hook de cierre del almacen de generaciones (UPSERT por gen_id: idempotente ante
    # re-cierres por reintentos/re-encolados; un re-cierre actualiza, no duplica). Es la
    # cuenta AUTORITATIVA del presupuesto diario (compartida por back/worker/daemons via
    # Postgres). `dia` (UTC, YYYY-MM-DD) indexado para el SUM del dia del corte automatico.
    """
    CREATE TABLE IF NOT EXISTS gasto_ia (
        gen_id      TEXT PRIMARY KEY,
        dia         TEXT NOT NULL DEFAULT '',
        tipo        TEXT NOT NULL DEFAULT '',
        marca       TEXT NOT NULL DEFAULT '',
        tokens_in   BIGINT NOT NULL DEFAULT 0,
        tokens_out  BIGINT NOT NULL DEFAULT 0,
        coste_usd   DOUBLE PRECISION NOT NULL DEFAULT 0,
        actualizado TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gasto_ia_dia ON gasto_ia (dia)",
    # Economia de CONTEXTO: tamano del prompt (chars) de cada generacion cerrada, para ver
    # la deriva del contexto por dia (prompts cada vez mas gordos). Migracion idempotente.
    "ALTER TABLE gasto_ia ADD COLUMN IF NOT EXISTS prompt_chars BIGINT NOT NULL DEFAULT 0",
    # Cache de metricas (lectura instantanea + refresco en 2o plano, ver metricas_cache.py):
    # guarda el dict CRUDO de `keni_metricas.servicio` (reporte/analisis) serializado a JSON,
    # por combo (tipo, rango, marca). La UI lee de aqui en cada apertura (instantaneo) y un
    # daemon + el boton "Actualizar" lo refrescan. `marca` = '' significa "todas".
    """
    CREATE TABLE IF NOT EXISTS metricas_cache (
        clave        TEXT PRIMARY KEY,
        tipo         TEXT NOT NULL,
        rango        TEXT NOT NULL,
        marca        TEXT NOT NULL DEFAULT '',
        payload      TEXT NOT NULL,
        fuente       TEXT NOT NULL DEFAULT 'muestra',
        generado_en  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_metricas_cache_combo "
    "ON metricas_cache (tipo, rango, marca)",
    # ----------------------------------------------------------------------- #
    # ACTIVOS REUTILIZABLES (ola "activos"): texto de medios interna.     #
    # (Las "plantillas de contenido" se retiraron por completo.)               #
    # ----------------------------------------------------------------------- #
    # Limpieza one-shot: elimina la tabla retirada `plantilla_contenido` (y sus datos) si una
    # BD vieja aun la tiene. Idempotente (IF EXISTS); no afecta a plantillas de MARCA/diseno.
    "DROP TABLE IF EXISTS plantilla_contenido CASCADE",
    # TEXTO DE MEDIOS interna (ola "activos"): catalogo editorial de imagenes/clips
    # APROBADOS y reutilizables al armar una pieza. NO publica a redes (eso es Metricool); es
    # un repositorio interno. Cada fila CATALOGA un objeto del almacen de media (`media.py` /
    # `almacen_media.py`) por su nombre (`objeto`, un uuid+ext que SIEMPRE genera el servidor)
    # mas metadatos editoriales: titulo, tipo (`imagen`|`clip`), marca, etiquetas (JSON de
    # strings para buscar/filtrar), credito/fuente y estado de aprobacion. `objeto` UNIQUE: un
    # mismo binario se cataloga una sola vez. Borrar una entrada NO borra el binario por
    # defecto (puede estar referenciado por una pieza ya armada); la API decide.
    """
    CREATE TABLE IF NOT EXISTS catalogo_media (
        id           TEXT PRIMARY KEY,
        objeto       TEXT NOT NULL UNIQUE,
        tipo         TEXT NOT NULL DEFAULT 'imagen',
        titulo       TEXT NOT NULL DEFAULT '',
        descripcion  TEXT NOT NULL DEFAULT '',
        marca        TEXT NOT NULL DEFAULT '',
        etiquetas    TEXT NOT NULL DEFAULT '[]',
        credito      TEXT NOT NULL DEFAULT '',
        aprobado     INTEGER NOT NULL DEFAULT 1,
        autor_id     TEXT NOT NULL DEFAULT '',
        autor_nombre TEXT NOT NULL DEFAULT '',
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_catalogo_media_marca ON catalogo_media (marca)",
    "CREATE INDEX IF NOT EXISTS idx_catalogo_media_tipo ON catalogo_media (tipo)",
    "CREATE INDEX IF NOT EXISTS idx_catalogo_media_aprobado ON catalogo_media (aprobado)",
    # ACTIVOS DE MARCA (editor profesional): el kit visual reutilizable de cada marca, agrupado
    # por `tipo` (logo | tipografia | arte | infografia | icono | paleta | fondo). Generaliza
    # `marca_assets.py` (que solo conocia 3 PNGs en disco) a un catalogo en Postgres + objetos en
    # S3/almacen (`objeto`, uuid+ext del servidor). `metadatos` (JSON) lleva datos por tipo (p.ej.
    # familia/peso de una tipografia, lista de hex de una paleta); `lineas` (JSON de ids de
    # `etiquetas` clase=vertical) etiqueta el activo por linea editorial. Para tipografias el
    # `objeto` es el .woff2/.ttf y `metadatos.familia` el nombre a registrar en el render.
    """
    CREATE TABLE IF NOT EXISTS marca_activos (
        id           TEXT PRIMARY KEY,
        marca        TEXT NOT NULL DEFAULT '',
        tipo         TEXT NOT NULL DEFAULT 'arte',
        nombre       TEXT NOT NULL DEFAULT '',
        objeto       TEXT NOT NULL DEFAULT '',
        metadatos    TEXT NOT NULL DEFAULT '{}',
        lineas       TEXT NOT NULL DEFAULT '[]',
        aprobado     INTEGER NOT NULL DEFAULT 1,
        autor_id     TEXT NOT NULL DEFAULT '',
        autor_nombre TEXT NOT NULL DEFAULT '',
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_marca_activos_marca ON marca_activos (marca)",
    "CREATE INDEX IF NOT EXISTS idx_marca_activos_tipo ON marca_activos (tipo)",
    # PLANTILLAS DE DISEÑO (editor profesional): N plantillas reutilizables por marca, cada una
    # un DOCUMENTO de capas completo (`documento`, JSON validado por `motores/estudio_imagen/
    # documento.py`). Se etiquetan por `categoria` (texto LIBRE normalizado a slug por la API:
    # ultima-hora | marcador | efemerides | …; "general" es el fallback y el legado "post" se trata
    # como "general") y por `lineas` (JSON de ids de `etiquetas` clase=vertical) para filtrar por
    # línea editorial.
    # `miniatura` es el objeto de media (uuid+ext) de una previa, o "". A diferencia de
    # `plantillas_marca` (1 plantilla por defecto por marca), aquí hay MUCHAS.
    # `tipo` ("foto" | "miniatura") es un eje ORTOGONAL a `categoria`: foto = plantilla para
    # fotos/imagenes; miniatura = portada/thumbnail de video. Las BDs existentes reciben el
    # DEFAULT "foto" via `_migrar_columnas_plantillas_diseno`.
    """
    CREATE TABLE IF NOT EXISTS plantillas_diseno (
        id           TEXT PRIMARY KEY,
        marca        TEXT NOT NULL DEFAULT '',
        nombre       TEXT NOT NULL DEFAULT '',
        categoria    TEXT NOT NULL DEFAULT 'general',
        tipo         TEXT NOT NULL DEFAULT 'foto',
        documento    TEXT NOT NULL DEFAULT '{}',
        miniatura    TEXT NOT NULL DEFAULT '',
        lineas       TEXT NOT NULL DEFAULT '[]',
        activo       INTEGER NOT NULL DEFAULT 1,
        rotar        INTEGER NOT NULL DEFAULT 0,
        orden        INTEGER NOT NULL DEFAULT 0,
        autor_id     TEXT NOT NULL DEFAULT '',
        autor_nombre TEXT NOT NULL DEFAULT '',
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_plantillas_diseno_marca ON plantillas_diseno (marca)",
    "CREATE INDEX IF NOT EXISTS idx_plantillas_diseno_categoria ON plantillas_diseno (categoria)",
    "CREATE INDEX IF NOT EXISTS idx_plantillas_diseno_tipo ON plantillas_diseno (tipo)",
    # Orden MANUAL del equipo dentro de cada marca (drag-and-drop de la galería). `orden`=0 es el
    # default «sin ordenar» (filas legadas y plantillas nuevas), que cae a «recientes primero» por
    # el `creado DESC` secundario; al reordenar se asignan 1..N en la secuencia exacta elegida.
    "CREATE INDEX IF NOT EXISTS idx_plantillas_diseno_orden ON plantillas_diseno (marca, orden)",
    # BLOQUES (almacén de capas reutilizables): un bloque es un GRUPO de capas con sentido propio
    # (lower-third, módulo de infografía, pleca de marca) que se suelta en cualquier documento.
    # `capas` es un JSON con la lista de capas (mismo esquema que `documento.capas`). Se etiqueta
    # por `marca` y `lineas` (ids de `etiquetas` clase=vertical). `miniatura` = objeto de media o "".
    """
    CREATE TABLE IF NOT EXISTS bloques (
        id           TEXT PRIMARY KEY,
        marca        TEXT NOT NULL DEFAULT '',
        nombre       TEXT NOT NULL DEFAULT '',
        capas        TEXT NOT NULL DEFAULT '[]',
        lineas       TEXT NOT NULL DEFAULT '[]',
        miniatura    TEXT NOT NULL DEFAULT '',
        autor_id     TEXT NOT NULL DEFAULT '',
        autor_nombre TEXT NOT NULL DEFAULT '',
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bloques_marca ON bloques (marca)",
    # VERSIONES DE DOCUMENTO (historial del editor por pieza): cada vez que se guarda el editor
    # sobre una publicación se APENDE una versión con el Documento de capas y el objeto del PNG
    # renderizado. Append-only (nunca se pisa): la última versión es el estado actual; las previas
    # permiten restaurar. Clave lógica (contenido_id, plataforma_id) -> N versiones incrementales.
    """
    CREATE TABLE IF NOT EXISTS documento_versiones (
        id            TEXT PRIMARY KEY,
        contenido_id  TEXT NOT NULL DEFAULT '',
        plataforma_id TEXT NOT NULL DEFAULT '',
        version       INTEGER NOT NULL DEFAULT 1,
        documento     TEXT NOT NULL DEFAULT '{}',
        render_objeto TEXT NOT NULL DEFAULT '',
        autor_id      TEXT NOT NULL DEFAULT '',
        autor_nombre  TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documento_versiones_pieza "
    "ON documento_versiones (contenido_id, plataforma_id, version)",
    # Webhooks SALIENTES (eventos internos del tablero): una fila por suscripcion. Cada
    # webhook escucha N tipos de evento (`eventos`, lista JSON; ""/[] = todos) y, al
    # dispararse, recibe un POST JSON a `url`. `secreto` (opcional) firma cada entrega con
    # HMAC-SHA256 en la cabecera `X-Keni-Signature` (mismo patron que Mixpost: X-Signature).
    # `formato` decide la forma del payload: `generico` (def, evento crudo) | `slack`
    # (`{"text": ...}`). SAFE BY DEFAULT: sin webhooks activos, NADA sale a la red.
    """
    CREATE TABLE IF NOT EXISTS webhooks (
        id           TEXT PRIMARY KEY,
        nombre       TEXT NOT NULL DEFAULT '',
        url          TEXT NOT NULL DEFAULT '',
        eventos      TEXT NOT NULL DEFAULT '',
        formato      TEXT NOT NULL DEFAULT 'generico',
        secreto      TEXT NOT NULL DEFAULT '',
        activo        INTEGER NOT NULL DEFAULT 1,
        ultimo_estado TEXT NOT NULL DEFAULT '',
        ultimo_en     TEXT NOT NULL DEFAULT '',
        autor_id      TEXT NOT NULL DEFAULT '',
        autor_nombre  TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT '',
        actualizado   TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_webhooks_activo ON webhooks (activo)",
    # Bitacora de eventos internos EMITIDOS (auditoria + idempotencia del barrido de
    # vencimientos: una `clave_idempotencia` ya registrada no se re-emite). `payload` es el
    # dict del evento serializado a JSON. No guarda secretos.
    """
    CREATE TABLE IF NOT EXISTS eventos_internos (
        id                  TEXT PRIMARY KEY,
        tipo                TEXT NOT NULL DEFAULT '',
        contenido_id        TEXT NOT NULL DEFAULT '',
        plataforma_id       TEXT NOT NULL DEFAULT '',
        clave_idempotencia  TEXT NOT NULL DEFAULT '',
        payload             TEXT NOT NULL DEFAULT '',
        creado              TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_eventos_internos_tipo ON eventos_internos (tipo)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_eventos_internos_idem "
    "ON eventos_internos (clave_idempotencia)",
    # Notificaciones IN-APP por usuario (el "cajon" de la campana, junto al selector de marca).
    # Una fila = una noticia para UN destinatario (`usuario_id`) sobre una pieza. `tipo` clasifica
    # el evento (mencion/comentario/aprobacion/rechazo/publicacion); `marca_id` ACOTA al workspace
    # activo (el cajon solo muestra la marca seleccionada). `actor_*` es quien lo provoco (no se
    # auto-notifica). `resumen` es la frase ya armada para la UI; `enlace` opcional para navegar.
    # `leida` se marca al abrir el cajon. Se BORRA en cascada logica? No: se purga por antiguedad
    # fuera de aqui si hace falta. Append + update de `leida`; nunca se reescribe el contenido.
    """
    CREATE TABLE IF NOT EXISTS notificaciones (
        id            TEXT PRIMARY KEY,
        usuario_id    TEXT NOT NULL DEFAULT '',
        marca_id      TEXT NOT NULL DEFAULT '',
        tipo          TEXT NOT NULL DEFAULT '',
        contenido_id  TEXT NOT NULL DEFAULT '',
        plataforma_id TEXT NOT NULL DEFAULT '',
        actor_id      TEXT NOT NULL DEFAULT '',
        actor_nombre  TEXT NOT NULL DEFAULT '',
        resumen       TEXT NOT NULL DEFAULT '',
        enlace        TEXT NOT NULL DEFAULT '',
        leida         INTEGER NOT NULL DEFAULT 0,
        creada        TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notif_buzon "
    "ON notificaciones (usuario_id, marca_id, leida, creada)",
    # Etiquetas editoriales del tablero (campaña / vertical / tipo), ola "organizacion".
    # Una etiqueta clasifica transversalmente un `contenido` (p.ej. campaña "Mundial 2026",
    # vertical "futbol", tipo "reel"). `marca` ACOTA la etiqueta a una marca/workspace
    # (UnoTV vs Claro Sports); `marca = ''` significa etiqueta GLOBAL (visible en todas las
    # marcas). `clase` distingue el eje (campania/vertical/tipo) solo para agrupar/colorear
    # en la UI — no es FK, se valida en la capa API contra una allowlist. `color` es un token
    # hex opcional para el chip. `activo` esconde del selector sin perder el historico de
    # asignaciones. `nombre` es UNIQUE por (marca, clase) — lo garantiza la capa API/repos.
    """
    CREATE TABLE IF NOT EXISTS etiquetas (
        id           TEXT PRIMARY KEY,
        nombre       TEXT NOT NULL DEFAULT '',
        clase        TEXT NOT NULL DEFAULT 'campania',
        marca        TEXT NOT NULL DEFAULT '',
        color        TEXT NOT NULL DEFAULT '',
        keywords     TEXT NOT NULL DEFAULT '',
        hashtags     TEXT NOT NULL DEFAULT '',
        activo       INTEGER NOT NULL DEFAULT 1,
        ttl_dias     INTEGER NOT NULL DEFAULT 0,
        es_evergreen     INTEGER NOT NULL DEFAULT 0,
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_etiquetas_marca ON etiquetas (marca)",
    "CREATE INDEX IF NOT EXISTS idx_etiquetas_clase ON etiquetas (clase)",
    "CREATE INDEX IF NOT EXISTS idx_etiquetas_activo ON etiquetas (activo)",
    # Relacion N:M `contenido` <-> `etiquetas`. Una pieza puede llevar varias etiquetas
    # (campaña + vertical + tipo). Cascada manual al borrar contenido o etiqueta (sin FK,
    # igual que el resto del esquema). PK compuesta evita duplicados.
    """
    CREATE TABLE IF NOT EXISTS contenido_etiquetas (
        contenido_id  TEXT NOT NULL,
        etiqueta_id   TEXT NOT NULL,
        PRIMARY KEY (contenido_id, etiqueta_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_contenido_etiquetas_etiqueta "
    "ON contenido_etiquetas (etiqueta_id)",
    # CONTENIDO editorial reutilizable que ERA file-backed (YAML + indice SQLite de rutas
    # absolutas) y cerro su rezago a Postgres (ADR 0006). Antes vivian en `ficheros.py` con un
    # `indice.sqlite` de rutas ABSOLUTAS que, al recrear contenedores, quedaba apuntando a
    # rutas viejas -> la pagina de Fuentes RSS aparecia VACIA. En Postgres no hay indice de
    # rutas que se desincronice. Mismo dialecto portable que el resto del esquema.
    #
    # Fuentes RSS: una fuente de noticias por marca, con filtros (incluir/excluir CSV),
    # redes por defecto (`redes_def` CSV) y telemetria de salud del ultimo refresco
    # (`ultima_actualizacion`/`ultimo_error`/`ultimo_conteo`). `activo` 0/1. `creado` preserva
    # el orden "recientes primero" (paridad con el indice file-backed). `fecha` = dia de alta.
    """
    CREATE TABLE IF NOT EXISTS fuentes_rss (
        id                    TEXT PRIMARY KEY,
        nombre                TEXT NOT NULL DEFAULT '',
        url                   TEXT NOT NULL DEFAULT '',
        marca                 TEXT NOT NULL DEFAULT '',
        fecha                 TEXT NOT NULL DEFAULT '',
        activo                INTEGER NOT NULL DEFAULT 1,
        incluir               TEXT NOT NULL DEFAULT '',
        excluir               TEXT NOT NULL DEFAULT '',
        redes_def             TEXT NOT NULL DEFAULT '',
        ultima_actualizacion  TEXT NOT NULL DEFAULT '',
        ultimo_error          TEXT NOT NULL DEFAULT '',
        ultimo_conteo         INTEGER NOT NULL DEFAULT 0,
        propia                INTEGER NOT NULL DEFAULT 0,
        intervalo_min         INTEGER NOT NULL DEFAULT 0,
        categoria             TEXT NOT NULL DEFAULT '',
        prioridad             INTEGER NOT NULL DEFAULT 0,
        proximo_sondeo        TEXT NOT NULL DEFAULT '',
        errores_seguidos      INTEGER NOT NULL DEFAULT 0,
        pausado_hasta         TEXT NOT NULL DEFAULT '',
        desactivado_auto      INTEGER NOT NULL DEFAULT 0,
        ultimo_filtrados      INTEGER NOT NULL DEFAULT 0,
        peso                  REAL NOT NULL DEFAULT 1.0,
        creado                TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fuentes_rss_marca ON fuentes_rss (marca)",
    "CREATE INDEX IF NOT EXISTS idx_fuentes_rss_creado ON fuentes_rss (creado)",
    # Selección de feeds VENCIDOS por el motor de ingesta (Ola A): el daemon barre las activas
    # con `proximo_sondeo` <= ahora. Indexar (activo, proximo_sondeo) hace barata esa consulta.
    "CREATE INDEX IF NOT EXISTS idx_fuentes_rss_sondeo ON fuentes_rss (activo, proximo_sondeo)",
    # Items RSS ya VISTOS/usados por fuente. Antes un mapa `{fuente_id: [clave]}` en
    # `.keni/rss-vistos.yaml` por marca; aqui una fila por (fuente_id, clave). PK compuesta
    # evita duplicados y hace `marcar_item(usado=True)` idempotente. SIN FK (igual que el
    # resto del esquema): `marcar_item` NO exige que la fuente exista (paridad con el file-backed).
    """
    CREATE TABLE IF NOT EXISTS rss_items_vistos (
        fuente_id  TEXT NOT NULL,
        clave      TEXT NOT NULL,
        PRIMARY KEY (fuente_id, clave)
    )
    """,
    # TALLER EVERGREEN / BRAINSTORMING: ideas de contenido EVERGREEN propuestas (por IA o a mano)
    # que el equipo aprueba o descarta ANTES de generar nada. La IA NO redacta a ciegas: primero
    # PROPONE ideas (`origen='ia'`, `estado='propuesta'`); una persona las marca `aprobada` o
    # `descartada`; solo para las APROBADAS se genera la pieza (`flujo='evergreen'` en el tablero)
    # y se enlaza en `contenido_id`. `generacion_id` apunta a la generacion IA que las propuso
    # (para trazar el lote). `creado` preserva el orden "recientes primero".
    """
    CREATE TABLE IF NOT EXISTS evergreen_ideas (
        id            TEXT PRIMARY KEY,
        marca         TEXT NOT NULL DEFAULT '',
        titulo        TEXT NOT NULL DEFAULT '',
        descripcion   TEXT NOT NULL DEFAULT '',
        estado        TEXT NOT NULL DEFAULT 'propuesta',
        origen        TEXT NOT NULL DEFAULT 'ia',
        generacion_id TEXT NOT NULL DEFAULT '',
        contenido_id  TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT '',
        actualizado   TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evergreen_ideas_marca ON evergreen_ideas (marca)",
    "CREATE INDEX IF NOT EXISTS idx_evergreen_ideas_estado ON evergreen_ideas (estado)",
    "CREATE INDEX IF NOT EXISTS idx_evergreen_ideas_creado ON evergreen_ideas (creado)",
    # Grupos de hashtags reutilizables (nombre + lista de tags JSON) por marca. `hashtags`
    # es un JSON serializado de strings (igual patron que `catalogo_media.etiquetas`).
    # `creado` preserva el orden "recientes primero".
    """
    CREATE TABLE IF NOT EXISTS grupos_hashtags (
        id        TEXT PRIMARY KEY,
        nombre    TEXT NOT NULL DEFAULT '',
        marca     TEXT NOT NULL DEFAULT '',
        hashtags  TEXT NOT NULL DEFAULT '[]',
        creado    TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_grupos_hashtags_marca ON grupos_hashtags (marca)",
    "CREATE INDEX IF NOT EXISTS idx_grupos_hashtags_creado ON grupos_hashtags (creado)",
    # Franjas EDITORIALES (dia_semana 0-6 + hora) por marca/red: huecos recurrentes de la
    # parrilla editorial. DISTINTAS de `rota_franjas`/`rota_config_franjas` (franjas horarias
    # del equipo). Tabla nueva `franjas_editoriales` para no colisionar con `rota_franjas`.
    """
    CREATE TABLE IF NOT EXISTS franjas_editoriales (
        id          TEXT PRIMARY KEY,
        marca       TEXT NOT NULL DEFAULT '',
        red         TEXT NOT NULL DEFAULT '',
        dia_semana  INTEGER NOT NULL DEFAULT 0,
        hora        TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_franjas_editoriales_marca ON franjas_editoriales (marca)",
    # CATEGORÍA del plan editorial a la que sirve la franja ('' = genérica, vale para todo).
    # Con el plan diario por categoría, los horarios de publicación también son por categoría
    # (p. ej. UnoTV: internacional 14:45 UTC, mx 15:45 UTC…): la pieza busca hueco en las
    # franjas de SU categoría y cae a las genéricas si no hay.
    "ALTER TABLE franjas_editoriales ADD COLUMN IF NOT EXISTS categoria TEXT NOT NULL DEFAULT ''",
    # El índice único de idempotencia ahora incluye `categoria` (dos franjas a la misma hora
    # con categorías distintas son legítimas): retira el viejo antes de crear el nuevo.
    "DROP INDEX IF EXISTS idx_franjas_editoriales_uniq",
    # CADENCIA por (marca?, red?): scheduling por MARGEN entre posts (sustituye a las
    # franjas-caja para alto volumen). margen_min = minutos entre posts; hora_inicio/fin =
    # ventana activa 24h; dias = CSV "0..6" (0=lunes). UNIQUE(marca, red): una cadencia por
    # par. `marca=''`/`red=''` = comodín (aplica a todas). Ver `dominio/cadencia.py`.
    """
    CREATE TABLE IF NOT EXISTS cadencias (
        id           TEXT PRIMARY KEY,
        marca        TEXT NOT NULL DEFAULT '',
        red          TEXT NOT NULL DEFAULT '',
        margen_min   INTEGER NOT NULL DEFAULT 60,
        hora_inicio  TEXT NOT NULL DEFAULT '08:00',
        hora_fin     TEXT NOT NULL DEFAULT '22:00',
        dias         TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
        activo       INTEGER NOT NULL DEFAULT 1,
        UNIQUE (marca, red)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cadencias_marca ON cadencias (marca)",
    # Fuentes de INTELIGENCIA DE PLATAFORMA (blogs oficiales + agregadores) que cubren
    # cambios de algoritmo y tendencias por red. DISTINTAS de `fuentes_rss` (contenido de
    # marca para generar copy): estas alimentan la pagina Algoritmos y el panel, y proponen
    # actualizaciones a la ficha editorial de cada plataforma. `plataforma` ubica la fuente
    # (meta/instagram/tiktok/youtube/x/linkedin/general); `tipo` distingue oficial vs
    # agregador (la oficial pesa mas al priorizar). Salud igual que `fuentes_rss`.
    """
    CREATE TABLE IF NOT EXISTS fuentes_algoritmo (
        id                    TEXT PRIMARY KEY,
        nombre                TEXT NOT NULL DEFAULT '',
        url                   TEXT NOT NULL DEFAULT '',
        plataforma            TEXT NOT NULL DEFAULT 'general',
        tipo                  TEXT NOT NULL DEFAULT 'agregador',
        activo                INTEGER NOT NULL DEFAULT 1,
        ultima_actualizacion  TEXT NOT NULL DEFAULT '',
        ultimo_error          TEXT NOT NULL DEFAULT '',
        ultimo_conteo         INTEGER NOT NULL DEFAULT 0,
        creado                TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fuentes_algoritmo_plataforma ON fuentes_algoritmo (plataforma)",
    "CREATE INDEX IF NOT EXISTS idx_fuentes_algoritmo_creado ON fuentes_algoritmo (creado)",
    # Noticias de algoritmo ya INGERIDAS y CLASIFICADAS (a diferencia de los items RSS, que se
    # leen en vivo y no se persisten): aqui SI se persisten para poder ordenarlas por
    # importancia, mostrarlas en el panel y enlazarlas a la texto. `importancia` es un
    # score HEURISTICO (entero comparable) y `nivel` su tramo (alta/media/baja); `senales` son
    # las palabras clave que dispararon el score (JSON, para el "por que" honesto, sin inventar).
    # `es_cambio` marca lo que parece un cambio de algoritmo confirmado (candidato a la ficha).
    # Dedup por (fuente_id, clave) — la misma identidad estable que usa el RSS.
    """
    CREATE TABLE IF NOT EXISTS noticias_algoritmo (
        id             TEXT PRIMARY KEY,
        fuente_id      TEXT NOT NULL DEFAULT '',
        fuente_nombre  TEXT NOT NULL DEFAULT '',
        plataforma     TEXT NOT NULL DEFAULT 'general',
        tipo           TEXT NOT NULL DEFAULT 'agregador',
        titulo         TEXT NOT NULL DEFAULT '',
        resumen        TEXT NOT NULL DEFAULT '',
        enlace         TEXT NOT NULL DEFAULT '',
        fecha          TEXT NOT NULL DEFAULT '',
        clave          TEXT NOT NULL DEFAULT '',
        importancia    INTEGER NOT NULL DEFAULT 0,
        nivel          TEXT NOT NULL DEFAULT 'baja',
        senales        TEXT NOT NULL DEFAULT '[]',
        es_cambio      INTEGER NOT NULL DEFAULT 0,
        aplicada       INTEGER NOT NULL DEFAULT 0,
        archivada      INTEGER NOT NULL DEFAULT 0,
        sugerida       INTEGER NOT NULL DEFAULT 0,
        creado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_noticias_algoritmo_dedup ON noticias_algoritmo (fuente_id, clave)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_algoritmo_orden ON noticias_algoritmo (importancia DESC, fecha DESC)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_algoritmo_plataforma ON noticias_algoritmo (plataforma)",
    # MOTOR DE INGESTA PERSISTENTE (Ola A): ARCHIVO a NIVEL DE ARTÍCULO. A diferencia de los
    # items RSS del Radar v1 (que se leen en VIVO por request, con tope), aqui cada artículo de
    # cada feed se PERSISTE una vez (dedup por (fuente_id, clave)) para tener cobertura
    # newsroom-grade: el Radar/Plan y la UI leen del store y la red se sondea en background por
    # el `ingesta_daemon`. `clave` = url_canonica normalizada (o hash del título si no hay url);
    # `categoria`/`marca` vienen de la fuente; `estado` nuevo|usado|descartado; `contenido_id`
    # enlaza al tablero cuando el equipo lo usa; `cluster_id` lo llena la Ola B (historias).
    """
    CREATE TABLE IF NOT EXISTS noticias_items (
        id             TEXT PRIMARY KEY,
        fuente_id      TEXT NOT NULL DEFAULT '',
        fuente_nombre  TEXT NOT NULL DEFAULT '',
        categoria      TEXT NOT NULL DEFAULT '',
        marca          TEXT NOT NULL DEFAULT '',
        titulo         TEXT NOT NULL DEFAULT '',
        resumen        TEXT NOT NULL DEFAULT '',
        cuerpo         TEXT NOT NULL DEFAULT '',
        url            TEXT NOT NULL DEFAULT '',
        url_canonica   TEXT NOT NULL DEFAULT '',
        idioma         TEXT NOT NULL DEFAULT '',
        autor          TEXT NOT NULL DEFAULT '',
        imagen         TEXT NOT NULL DEFAULT '',
        publicado_en   TEXT NOT NULL DEFAULT '',
        capturado_en   TEXT NOT NULL DEFAULT '',
        clave          TEXT NOT NULL DEFAULT '',
        cluster_id     TEXT NOT NULL DEFAULT '',
        senal          INTEGER NOT NULL DEFAULT 0,
        geo            TEXT NOT NULL DEFAULT '',
        estado         TEXT NOT NULL DEFAULT 'nuevo',
        contenido_id   TEXT NOT NULL DEFAULT '',
        fuente_peso    REAL NOT NULL DEFAULT 1.0,
        creado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_noticias_items_dedup ON noticias_items (fuente_id, clave)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_capturado ON noticias_items (capturado_en)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_marca_capturado ON noticias_items (marca, capturado_en)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_categoria ON noticias_items (categoria)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_estado ON noticias_items (estado)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_cluster ON noticias_items (cluster_id)",
    # Cruce exacto del clustering por URL canónica de CUALQUIER item del cluster (no solo la
    # clave del representativo). `text_pattern_ops`: el lookup usa igualdad y LIKE de prefijo.
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_urlcan ON noticias_items (url_canonica text_pattern_ops)",
    # HISTORIAS (Ola B): una fila por cluster = la misma noticia contada por varias fuentes y
    # en el tiempo (dedup + corroboración + score). `clave` es la clave de cluster del título
    # representativo (url canónica o hash); `n_fuentes` es la corroboración (fuentes distintas);
    # `senal` agrega la viralidad; `breaking` = muchas fuentes en poco tiempo; `score` ranking.
    # `noticias_items.cluster_id` apunta aquí. Tabla NUEVA: `CREATE TABLE IF NOT EXISTS` basta.
    """
    CREATE TABLE IF NOT EXISTS noticias_clusters (
        id            TEXT PRIMARY KEY,
        titulo        TEXT NOT NULL DEFAULT '',
        resumen       TEXT NOT NULL DEFAULT '',
        marca         TEXT NOT NULL DEFAULT '',
        categoria     TEXT NOT NULL DEFAULT '',
        geo           TEXT NOT NULL DEFAULT '',
        clave         TEXT NOT NULL DEFAULT '',
        n_items       INTEGER NOT NULL DEFAULT 0,
        n_fuentes     INTEGER NOT NULL DEFAULT 0,
        idiomas       TEXT NOT NULL DEFAULT '[]',
        senal         INTEGER NOT NULL DEFAULT 0,
        score         REAL NOT NULL DEFAULT 0,
        score_razon   TEXT NOT NULL DEFAULT '',
        score_desglose TEXT NOT NULL DEFAULT '',
        breaking      INTEGER NOT NULL DEFAULT 0,
        primer_visto  TEXT NOT NULL DEFAULT '',
        ultimo_visto  TEXT NOT NULL DEFAULT '',
        estado        TEXT NOT NULL DEFAULT 'nuevo',
        contenido_id  TEXT NOT NULL DEFAULT '',
        verificacion  TEXT NOT NULL DEFAULT 'unica_fuente',
        titulo_es     TEXT NOT NULL DEFAULT '',
        resumen_es    TEXT NOT NULL DEFAULT '',
        titulo_original TEXT NOT NULL DEFAULT '',
        idioma        TEXT NOT NULL DEFAULT '',
        traducido     INTEGER NOT NULL DEFAULT 0,
        peso_fuentes  REAL NOT NULL DEFAULT 0,
        velocidad     REAL NOT NULL DEFAULT 0,
        primera_fuente TEXT NOT NULL DEFAULT '',
        primera_fuente_nombre TEXT NOT NULL DEFAULT '',
        fuentes_detalle TEXT NOT NULL DEFAULT '',
        marca_clasificada_por_ia INTEGER NOT NULL DEFAULT 0,
        qa_veredicto  TEXT NOT NULL DEFAULT '',
        qa_hallazgos  TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT '',
        actualizado   TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_noticias_clusters_marca_score ON noticias_clusters (marca, score)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_clusters_categoria ON noticias_clusters (categoria)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_clusters_ultimo ON noticias_clusters (ultimo_visto)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_clusters_estado ON noticias_clusters (estado)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_clusters_clave ON noticias_clusters (clave)",
    # Sugerencias editoriales GENERADAS por el job diario a partir de las noticias importantes:
    # propuestas de cambio a la ficha editorial de una plataforma (`tipo='editorial'`) o a sus
    # limites (`tipo='limite'`). PROPUESTAS, no aplicadas: el equipo revisa y decide (estado
    # nueva/aplicada/descartada). `noticia_ids` (JSON) son las noticias que la motivaron;
    # `ficha_id` el doc de texto destino (p. ej. `editorial/plataformas/instagram`).
    """
    CREATE TABLE IF NOT EXISTS sugerencias_editoriales (
        id           TEXT PRIMARY KEY,
        plataforma   TEXT NOT NULL DEFAULT 'general',
        tipo         TEXT NOT NULL DEFAULT 'editorial',
        titulo       TEXT NOT NULL DEFAULT '',
        detalle      TEXT NOT NULL DEFAULT '',
        ficha_id     TEXT NOT NULL DEFAULT '',
        noticia_ids  TEXT NOT NULL DEFAULT '[]',
        estado       TEXT NOT NULL DEFAULT 'nueva',
        creado       TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sugerencias_editoriales_estado ON sugerencias_editoriales (estado)",
    "CREATE INDEX IF NOT EXISTS idx_sugerencias_editoriales_creado ON sugerencias_editoriales (creado)",
    # INSUMOS DEL DÍA (cajones): material diario del equipo de AMX procesado con Haiku.
    # `insumos_lote` = un "drop" (pegada o archivo) en uno de los 4 cajones del día.
    # `insumos_item` = cada ítem extraído por el parser. El par modela el historial por
    # día editorial para poder recuperar cualquier jornada pasada (portal/corresponsales/
    # reporteros/eventos_claro). Ver docs/maquina-contenido/01-insumos-del-dia.md.
    """
    CREATE TABLE IF NOT EXISTS insumos_lote (
        id              TEXT PRIMARY KEY,
        fecha           TEXT NOT NULL DEFAULT '',
        cajon           TEXT NOT NULL DEFAULT '',
        marca           TEXT NOT NULL DEFAULT '',
        origen_texto    TEXT NOT NULL DEFAULT '',
        origen_archivo  TEXT NOT NULL DEFAULT '',
        estado          TEXT NOT NULL DEFAULT 'listo',
        error           TEXT NOT NULL DEFAULT '',
        total_items     INTEGER NOT NULL DEFAULT 0,
        creado_por      TEXT NOT NULL DEFAULT '',
        creado          TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_insumos_lote_fecha_cajon ON insumos_lote (fecha, cajon)",
    "CREATE INDEX IF NOT EXISTS idx_insumos_lote_creado ON insumos_lote (creado)",
    """
    CREATE TABLE IF NOT EXISTS insumos_item (
        id               TEXT PRIMARY KEY,
        lote_id          TEXT NOT NULL DEFAULT '',
        fecha            TEXT NOT NULL DEFAULT '',
        cajon            TEXT NOT NULL DEFAULT '',
        marca            TEXT NOT NULL DEFAULT '',
        linea            TEXT NOT NULL DEFAULT '',
        titulo           TEXT NOT NULL DEFAULT '',
        resumen          TEXT NOT NULL DEFAULT '',
        hora             TEXT NOT NULL DEFAULT '',
        lugar            TEXT NOT NULL DEFAULT '',
        estado_material  TEXT NOT NULL DEFAULT '',
        tipo             TEXT NOT NULL DEFAULT 'nota',
        idioma           TEXT NOT NULL DEFAULT 'es',
        usado            INTEGER NOT NULL DEFAULT 0,
        contenido_id     TEXT NOT NULL DEFAULT '',
        orden            INTEGER NOT NULL DEFAULT 0,
        creado           TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_insumos_item_fecha_cajon ON insumos_item (fecha, cajon)",
    "CREATE INDEX IF NOT EXISTS idx_insumos_item_lote ON insumos_item (lote_id)",
    "CREATE INDEX IF NOT EXISTS idx_insumos_item_marca_fecha ON insumos_item (marca, fecha)",
    # MOTOR DE VIDEO (Ola VIDEO). `video_composiciones` guarda el JSON de COMPOSICION (pistas/
    # clips/overlay/subtitulos; esquema en `docs/maquina-contenido/G-video-engine.md`, validado
    # por `keni_shared.video.validar_composicion`). `documento` es el JSON; `contenido_id` la liga
    # opcionalmente a una pieza del tablero. Una composicion por video del Estudio de Video.
    """
    CREATE TABLE IF NOT EXISTS video_composiciones (
        id           TEXT PRIMARY KEY,
        contenido_id TEXT NOT NULL DEFAULT '',
        marca        TEXT NOT NULL DEFAULT '',
        titulo       TEXT NOT NULL DEFAULT '',
        estado       TEXT NOT NULL DEFAULT 'borrador',
        documento    TEXT NOT NULL DEFAULT '{}',
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_video_composiciones_marca ON video_composiciones (marca)",
    "CREATE INDEX IF NOT EXISTS idx_video_composiciones_contenido ON video_composiciones (contenido_id)",
    # `video_subtitulos`: pista de subtitulos de una composicion. `segmentos` = JSON word-level
    # del ASR (faster-whisper); `ass` = el ASS renderizado para quemar con ffmpeg. `estado` ∈
    # {pendiente, transcrito, editado, listo}. La rellena el motor de ASR (motores/transcripcion).
    """
    CREATE TABLE IF NOT EXISTS video_subtitulos (
        id            TEXT PRIMARY KEY,
        composicion_id TEXT NOT NULL DEFAULT '',
        idioma        TEXT NOT NULL DEFAULT 'es-MX',
        estado        TEXT NOT NULL DEFAULT 'pendiente',
        segmentos     TEXT NOT NULL DEFAULT '',
        ass           TEXT NOT NULL DEFAULT '',
        transcrito_en TEXT NOT NULL DEFAULT '',
        actualizado   TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_video_subtitulos_composicion ON video_subtitulos (composicion_id)",
    "CREATE INDEX IF NOT EXISTS idx_video_subtitulos_estado ON video_subtitulos (estado)",
    # PUBLICACIONES de la Biblioteca de Texto (rediseno "version publicada"): cada fila es un
    # acto de PUBLICAR un documento (`doc_id` de libtexto) fijando un `sha` git inmutable. La
    # fila MAS RECIENTE por doc_id (creado DESC, id DESC) es el puntero de PRODUCCION vigente;
    # el resto queda como audit log (quien publico que y cuando). Sin filas para un doc, los
    # pipelines caen a la working copy (migracion suave). Timestamps ISO con MICROSEGUNDOS
    # (desempatan publicaciones consecutivas; el id es uuid, no monotonico).
    """
    CREATE TABLE IF NOT EXISTS texto_publicaciones (
        id      TEXT PRIMARY KEY,
        doc_id  TEXT NOT NULL,
        sha     TEXT NOT NULL,
        autor   TEXT NOT NULL DEFAULT '',
        nota    TEXT NOT NULL DEFAULT '',
        creado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_texto_publicaciones_doc ON texto_publicaciones (doc_id, creado)",
    # SOLICITUDES de publicacion (flujo editor -> admin): un editor propone fijar `sha_propuesto`
    # como produccion de `doc_id`; un admin la aprueba (publica + marca `aprobada`) o la rechaza.
    # A lo sumo UNA solicitud `abierta` por doc (una nueva SUSTITUYE a la abierta anterior).
    # `revisor`/`comentario`/`resuelto` se rellenan al resolver ('' = aun abierta).
    """
    CREATE TABLE IF NOT EXISTS texto_solicitudes (
        id            TEXT PRIMARY KEY,
        doc_id        TEXT NOT NULL,
        sha_propuesto TEXT NOT NULL,
        autor         TEXT NOT NULL DEFAULT '',
        nota          TEXT NOT NULL DEFAULT '',
        estado        TEXT NOT NULL DEFAULT 'abierta',
        revisor       TEXT NOT NULL DEFAULT '',
        comentario    TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT '',
        resuelto      TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_texto_solicitudes_estado ON texto_solicitudes (estado, doc_id)",
    # LATIDOS de los daemons de fondo (observabilidad del panel Sistema): UNA fila por daemon,
    # upsert en cada ciclo/barrido (escritura best-effort desde `latidos.py`; un fallo aqui
    # JAMAS rompe un barrido). `visto` = ultimo ciclo del bucle (el hilo vive aunque el gate
    # este OFF); `ultimo_barrido`/`ultimo_ok`/`ultimo_error` = ejecucion real del sweep.
    # `intervalo_seg`/`tick_seg` permiten al panel juzgar si un daemon esta ATRASADO sin
    # conocer su configuracion (atrasado ~ edad(visto) >> tick). Timestamps ISO UTC (TEXT),
    # como el resto del esquema.
    """
    CREATE TABLE IF NOT EXISTS daemon_latidos (
        daemon         TEXT PRIMARY KEY,
        visto          TEXT NOT NULL DEFAULT '',
        activo         INTEGER NOT NULL DEFAULT 0,
        intervalo_seg  REAL NOT NULL DEFAULT 0,
        tick_seg       REAL NOT NULL DEFAULT 0,
        ultimo_barrido TEXT NOT NULL DEFAULT '',
        ultimo_ok      TEXT NOT NULL DEFAULT '',
        ultimo_error   TEXT NOT NULL DEFAULT '',
        error_txt      TEXT NOT NULL DEFAULT '',
        duracion_ms    INTEGER NOT NULL DEFAULT 0,
        barridos       INTEGER NOT NULL DEFAULT 0,
        errores        INTEGER NOT NULL DEFAULT 0
    )
    """,
)


def _crear_esquema(con: Any) -> None:
    """Crea las tablas operacionales si no existen (idempotente) BAJO LOCK cross-proceso.

    Ejecuta el DDL sentencia a sentencia y luego aplica las migraciones de columnas
    ampliadas (`tareas`, `rota_eventos`) y la migracion del modelo de turnos (ola back3:
    `rota_turnos` → `rota_turnos` con la nueva semantica).

    Las migraciones son NECESARIAS, no opcionales: `CREATE TABLE IF NOT EXISTS`
    NO anade columnas a una tabla que YA existe, y el Postgres hosted PERSISTE entre
    despliegues. Una tabla creada por una version anterior se quedaba sin las columnas
    nuevas (fallo real: `rota_eventos` sin `tipo_cobertura` → 500 al leer el calendario).

    LOCK CROSS-PROCESO: en un deploy, back/worker/daemons/mcp arrancan A LA VEZ y cada
    proceso corre estas ~90 sentencias + migraciones en paralelo (el memo
    `_esquemas_asegurados` es por-proceso). El DDL es idempotente pero NO es inmune al
    paralelismo (dos ALTER/CREATE INDEX simultaneos se bloquean entre si o fallan con
    duplicados transitorios). Un `pg_advisory_lock` BLOQUEANTE con clave fija serializa
    los arranques: el primero migra y los demas esperan y encuentran todo hecho.
    """
    clave = _clave_lock("esquema")
    con.execute("SELECT pg_advisory_lock(?, ?)", (_LOCK_NS_BARRIDO, clave))
    con.commit()
    try:
        _crear_esquema_bajo_lock(con)
    finally:
        try:
            con.execute("SELECT pg_advisory_unlock(?, ?)", (_LOCK_NS_BARRIDO, clave))
            con.commit()
        except Exception:  # noqa: BLE001 -- igual que lock_barrido: descartar, no reciclar.
            # Si el unlock falla, la conexion arrastra un lock de SESION sobre la clave
            # "esquema": reciclada al pool BLOQUEARIA para siempre los arranques futuros
            # (este lock es bloqueante). Descartar cierra el socket y el servidor libera
            # el lock; el caller vera el fallo en su primera operacion y reintentara.
            _log.warning("No se pudo soltar el lock de esquema; se descarta la conexion.")
            descartar = getattr(con, "descartar", None)
            if descartar is not None:
                descartar()
            raise


def _crear_esquema_bajo_lock(con: Any) -> None:
    """Cuerpo real de `_crear_esquema` (DDL + migraciones VERSIONADAS); requiere el lock.

    Orquestacion (el ORDEN importa):
      1. Journal `schema_migraciones` (debe existir antes de leerlo).
      2. Migraciones PRE-DDL pendientes (`MIGRACIONES_PRE_DDL`): transforman tablas viejas
         ANTES de que el DDL declarativo cree indices sobre columnas que aun no existen
         (cada entrada documenta su porque en la definicion del registro, al final del modulo).
      3. DDL declarativo idempotente (`_DDL_ESQUEMA`): red de seguridad y fuente de verdad
         de la FORMA del esquema; se ejecuta SIEMPRE (es barato: una vez por proceso/URL).
      4. Migraciones POST-DDL pendientes (`MIGRACIONES_POST_DDL`).
      5. Red de seguridad SIEMPRE-ON (fuera del journal, ver abajo): dedup de turnos +
         indices unicos best-effort.
    """
    con.execute(_DDL_SCHEMA_MIGRACIONES)
    con.commit()
    _aplicar_migraciones(con, MIGRACIONES_PRE_DDL)
    for sentencia in _DDL_ESQUEMA:
        con.execute(sentencia)
    con.commit()
    _aplicar_migraciones(con, MIGRACIONES_POST_DDL)
    # Limpieza de turnos duplicados ANTES del indice unico de rota (un CREATE UNIQUE INDEX
    # sobre duplicados preexistentes fallaria y dejaria la tabla sin el constraint). Corre
    # SIEMPRE (no va al journal): es el companero del retry de los indices unicos de abajo.
    _dedup_turnos_rota(con)
    # Indices UNICOS de idempotencia: AL FINAL, aislados (commit propio por indice) y SIEMPRE
    # (no van al journal A PROPOSITO): pueden fallar sobre BDs con duplicados previos sin
    # tumbar el arranque, y deben REINTENTARSE en cada arranque hasta que la limpieza manual
    # permita crearlos (journalizarlos congelaria el fallo). Ver helper.
    _crear_indices_unicos_idempotencia(con)


# --------------------------------------------------------------------------- #
# Migraciones VERSIONADAS de esquema (journal `schema_migraciones`)             #
# --------------------------------------------------------------------------- #
#
# REGLA para cambiar el esquema (leer antes de tocar nada):
#
#   1. Ajusta el DDL declarativo (`_DDL_ESQUEMA`): es la fuente de verdad de la FORMA del
#      esquema y lo que recibe una BD VIRGEN (CREATE TABLE/INDEX IF NOT EXISTS).
#   2. Anade una entrada NUEVA al final de `MIGRACIONES_POST_DDL` (o PRE_DDL solo si el DDL
#      declarativo crearia un indice/tabla que choca con la forma vieja) con NOMBRE SECUENCIAL
#      estable ("00NN-que-hace") y una funcion `fn(con)` con el ALTER/backfill para BDs ya
#      creadas. Las migraciones nuevas corren UNA SOLA VEZ por BD (quedan registradas en el
#      journal `schema_migraciones`), asi que NO necesitan ser re-ejecutables en cada arranque
#      (pero la idempotencia sigue siendo deseable: es la defensa si el registro post-commit
#      no llega a escribirse, p.ej. caida justo tras un DDL con commit interno).
#   3. NUNCA renumeres ni reordenes entradas ya publicadas: el journal las referencia por id.
#
# COMPATIBILIDAD con las migraciones LEGADAS (las `_migrar_*` historicas de este modulo):
# nacieron re-ejecutables en cada arranque y muchas se EXTIENDEN editando su tupla directora
# (`_COLUMNAS_*_AMPLIADAS`, `_COLUMNAS_TS_CANON`) o su propio cuerpo. Para conservar ese
# flujo sin journal manual, sus entradas llevan `re_aplicar_si_cambia=True`: el id registrado
# incluye una HUELLA (hash del fuente de la fn + repr de sus datos directores), de modo que
# anadir una columna a la tupla (o editar la fn) re-aplica la migracion UNA vez (son
# idempotentes) y la re-registra bajo el id nuevo. Los ids viejos quedan como filas inertes.
#
# PRIMERA EJECUCION sobre una BD ya existente (pre-journal): el journal nace vacio aunque
# las migraciones legadas ya se aplicaran de facto en arranques anteriores. Como TODAS las
# legadas son idempotentes, simplemente corren una ultima vez y quedan registradas; a partir
# de ahi cada arranque solo consulta el journal (1 SELECT) + DDL idempotente.
#
# ERRORES: si una migracion pendiente FALLA, se loguea con su id y se ABORTA el arranque sin
# registrarla (mejor caerse visible que servir con esquema a medias; mismo comportamiento que
# tenian las `_migrar_*` legadas, cuyas excepciones tumbaban `_crear_esquema`). Las legadas
# best-effort (`_normalizar_timestamps_texto`) siguen tragandose fallos POR COLUMNA dentro de
# su cuerpo, como siempre.

# Journal: una fila por migracion APLICADA. `id` = nombre estable de la entrada (con huella
# `@hash` si `re_aplicar_si_cambia`), `aplicado_en` = ISO UTC de cuando se completo. Se crea
# aqui (no en `_DDL_ESQUEMA`) porque debe existir ANTES de leer el journal, que es lo primero
# que hace el orquestador. En los tests se trunca entre tests como el resto de tablas
# (`tests/_postgres.py`), preservando la auto-curacion "BD vieja" que ejercita la suite.
_DDL_SCHEMA_MIGRACIONES = """
    CREATE TABLE IF NOT EXISTS schema_migraciones (
        id          TEXT PRIMARY KEY,
        aplicado_en TEXT NOT NULL DEFAULT ''
    )
"""


@dataclass(frozen=True)
class Migracion:
    """Entrada del registro ordenado de migraciones de esquema.

    - `nombre`: id estable y secuencial ("00NN-que-hace"). No se renumera jamas.
    - `fn`: la migracion en si; recibe la conexion (puede commitear internamente; si no lo
      hace, su trabajo y el registro en el journal entran en la MISMA transaccion).
    - `re_aplicar_si_cambia`: solo para las migraciones LEGADAS re-ejecutables (idempotentes):
      el id del journal incluye una huella de `fn`+`datos`, asi que editar la fn o su tupla
      directora la re-aplica una vez. Las migraciones NUEVAS deben dejarlo en False.
    - `datos`: datos directores de la migracion (p.ej. la tupla `_COLUMNAS_*_AMPLIADAS`),
      solo para componer la huella; la fn los lee de su modulo como siempre.
    """

    nombre: str
    fn: Callable[[Any], None]
    re_aplicar_si_cambia: bool = False
    datos: Any = None


def _id_migracion(migracion: Migracion) -> str:
    """Id con que la migracion se registra en el journal (nombre[, + huella de contenido])."""
    if not migracion.re_aplicar_si_cambia:
        return migracion.nombre
    try:
        fuente = inspect.getsource(migracion.fn)
    except (OSError, TypeError):  # sin fuente disponible: la huella cae a los datos
        fuente = migracion.fn.__qualname__
    huella = hashlib.blake2b(
        (fuente + repr(migracion.datos)).encode("utf-8"), digest_size=4
    ).hexdigest()
    return f"{migracion.nombre}@{huella}"


def _aplicar_migraciones(con: Any, migraciones: tuple[Migracion, ...]) -> None:
    """Ejecuta SOLO las migraciones aun no registradas en el journal y las registra.

    Requiere el advisory lock de esquema ya tomado (lo garantiza `_crear_esquema`): dos
    procesos arrancando a la vez se serializan ahi, asi que el primero aplica y registra y
    el segundo encuentra el journal completo y no hace nada. El INSERT lleva ademas
    `ON CONFLICT DO NOTHING` como cinturon. Si la fn NO commitea internamente, fn + registro
    + commit son UNA transaccion (o todo o nada); si commitea (DDL multi-paso legado), el
    registro va despues y la idempotencia de la fn cubre una caida entre medias.
    """
    aplicadas = {
        fila["id"] for fila in con.execute("SELECT id FROM schema_migraciones").fetchall()
    }
    for migracion in migraciones:
        id_migracion = _id_migracion(migracion)
        if id_migracion in aplicadas:
            continue
        t0 = time.monotonic()
        try:
            migracion.fn(con)
        except Exception:
            # Deja la conexion utilizable para que el finally de `_crear_esquema` pueda
            # soltar el advisory lock limpiamente (una tx abortada reventaria el unlock).
            try:
                con.rollback()
            except Exception:  # noqa: BLE001 -- best-effort: el descarte del caller cubre el resto
                pass
            _log.error(
                "La migracion de esquema %s FALLO; se aborta el arranque sin registrarla "
                "(se reintentara en el proximo arranque).",
                id_migracion,
            )
            raise
        con.execute(
            "INSERT INTO schema_migraciones (id, aplicado_en) VALUES (?, ?) "
            "ON CONFLICT (id) DO NOTHING",
            (id_migracion, ahora_iso()),
        )
        con.commit()
        _log.info(
            "Migracion de esquema %s aplicada en %.0f ms.",
            id_migracion,
            (time.monotonic() - t0) * 1000,
        )


def _migrar_renombre_catalogo_media(con: Any) -> None:
    """Renombra la tabla `biblioteca_media` (nombre viejo) a `catalogo_media` y sus índices.

    El catálogo de medios aprobados se llamaba `biblioteca_media`; se renombró a `catalogo_media`
    al purgar "biblioteca" del repo. Idempotente: solo actúa si existe la tabla vieja y aún no la
    nueva. Es el ÚNICO sitio que aún nombra la tabla vieja (la fuente del renombre).
    """
    if not _tabla_existe(con, "biblioteca_media") or _tabla_existe(con, "catalogo_media"):
        return
    con.execute("ALTER TABLE biblioteca_media RENAME TO catalogo_media")
    for viejo, nuevo in (
        ("idx_biblioteca_media_marca", "idx_catalogo_media_marca"),
        ("idx_biblioteca_media_tipo", "idx_catalogo_media_tipo"),
        ("idx_biblioteca_media_aprobado", "idx_catalogo_media_aprobado"),
    ):
        con.execute(f"ALTER INDEX IF EXISTS {viejo} RENAME TO {nuevo}")


def _migrar_columnas_noticias_algoritmo(con: Any) -> None:
    """Anade `sugerida` a `noticias_algoritmo` si una BD ya creada no la tuviera (idempotente).

    La tabla `noticias_algoritmo` se creo sin esta columna; el job de sugerencias editoriales
    la usa para no re-procesar una noticia. `ADD COLUMN IF NOT EXISTS` es seguro y no-op si ya
    esta. Solo aplica si la tabla existe (un primer arranque ya la crea con la columna).
    """
    if not _tabla_existe(con, "noticias_algoritmo"):
        return
    if "sugerida" not in _columnas_existentes(con, "noticias_algoritmo"):
        con.execute(
            "ALTER TABLE noticias_algoritmo ADD COLUMN IF NOT EXISTS sugerida INTEGER NOT NULL DEFAULT 0"
        )


def _migrar_columnas_contenido_plataforma(con: Any) -> None:
    """Anade `copy_in_exento` y `qa_auto_hash` a `contenido_plataforma` (idempotente).

    Columnas del auto-avance (Flujo: "dale el OK" automatico): `copy_in_exento` marca una
    pieza como exenta de copy-in (imagen dramatica/autoexplicativa que no lo necesita);
    `qa_auto_hash` guarda el hash del copy para el que se lanzo la QA automatica, para no
    relanzarla en cada barrido. `ADD COLUMN IF NOT EXISTS` es seguro y no-op si ya estan.
    """
    if not _tabla_existe(con, "contenido_plataforma"):
        return
    cols = _columnas_existentes(con, "contenido_plataforma")
    if "copy_in_exento" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS copy_in_exento INTEGER NOT NULL DEFAULT 0"
        )
    if "qa_auto_hash" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS qa_auto_hash TEXT NOT NULL DEFAULT ''"
        )
    # `placa_oculta`: la pieza se publica SOLO con la foto, sin la plantilla/placa de marca
    # encima ("quitar plantilla" del editor). Persiste la elección entre reaperturas.
    if "placa_oculta" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS placa_oculta INTEGER NOT NULL DEFAULT 0"
        )
    # `plantilla_diseno_id`: la plantilla del estudio (PlantillaDiseno) que la pieza usa para
    # componer su imagen. "" = sin plantilla del estudio (placa de marca por defecto).
    if "plantilla_diseno_id" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS plantilla_diseno_id TEXT NOT NULL DEFAULT ''"
        )
    # `foto_encuadre`: reencuadre manual de la foto dentro del marco 4:5 (JSON
    # `{"foco":[x,y],"zoom":z}`; "" = sin reencuadre = encuadre por defecto del path). Persiste
    # la elección humana del recorte entre reaperturas y se aplica también al render por plantilla.
    if "foto_encuadre" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS foto_encuadre TEXT NOT NULL DEFAULT ''"
        )
    # `fotos`: COLLAGE multi-hueco. JSON array `[{"objeto":media_id,"foco":[x,y],"zoom":z}, …]`,
    # un elemento por HUECO de la plantilla (en orden de `capas`). "" = sin collage; entonces el
    # hueco 0 se deriva del par legado `foto`/`foto_encuadre` (retrocompat con la foto única).
    if "fotos" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS fotos TEXT NOT NULL DEFAULT ''"
        )
    # `carrusel`: slides EXTRA de una pieza `formato='carrusel'` (JSON array
    # `[{"tipo":"imagen"|"video","objeto":id}, …]` en orden de publicación). La portada
    # sigue siendo la imagen compuesta (`foto` + plantilla -> `imagen`); estos slides van
    # EN CRUDO detrás de ella en el post multi-media (Metricool `media[]`).
    if "carrusel" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS carrusel TEXT NOT NULL DEFAULT ''"
        )
    # `video` / `falta_video` (Ola VIDEO): asset de video y su checklist, espejo de
    # `imagen`/`falta_imagen`. Una pieza `formato='video'` necesita este asset; en piezas `foto`
    # el video es N/A (`falta_video` queda en 0). ADD COLUMN IF NOT EXISTS es no-op si ya estan.
    if "video" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS video TEXT NOT NULL DEFAULT ''"
        )
    if "falta_video" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS falta_video INTEGER NOT NULL DEFAULT 0"
        )
    # `marca`: DENORMALIZADA del padre `contenido`. Habilita el indice unico parcial de parrilla
    # POR MARCA (`idx_parrilla_slot_uniq`, en `_INDICES_UNICOS_IDEMPOTENCIA`): dos marcas distintas
    # SI pueden programar la misma (red, fecha); la MISMA marca no puede doble-reservar el slot.
    # Un indice parcial no puede cruzar el join al padre, de ahi la denormalizacion. Las escrituras
    # la mantienen en sync (`crear_contenido_plataforma` la deriva del padre; `actualizar_contenido`
    # la propaga al reasignar la marca del padre). El backfill abajo la rellena en BDs ya creadas.
    if "marca" not in cols:
        con.execute(
            "ALTER TABLE contenido_plataforma "
            "ADD COLUMN IF NOT EXISTS marca TEXT NOT NULL DEFAULT ''"
        )
    # BACKFILL one-shot desde el padre: alinea TODA fila cuya `marca` denormalizada difiera de la
    # del `contenido` padre (incluye filas recien migradas con ""). La app no esta en produccion-
    # uso, asi que el volumen es minimo; un UPDATE...FROM basta. Idempotente: re-ejecutarlo no toca
    # nada si ya estan alineadas (el WHERE filtra las que difieren).
    if _tabla_existe(con, "contenido"):
        con.execute(
            "UPDATE contenido_plataforma AS cp SET marca = c.marca "
            "FROM contenido AS c WHERE cp.contenido_id = c.id AND cp.marca <> c.marca"
        )
    # Indice plano por `marca` (filtros del tablero/feed por marca denormalizada). Se crea AQUI
    # (no en el DDL declarativo) porque en BDs viejas la columna `marca` la añade esta migracion:
    # un CREATE INDEX en el DDL correria ANTES y reventaria ("column marca does not exist").
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_contenido_plataforma_marca ON contenido_plataforma (marca)"
    )


def _migrar_columnas_plantillas_diseno(con: Any) -> None:
    """Anade `tipo`/`rotar` a `plantillas_diseno` si una BD ya creada no los tuviera y alinea el
    DEFAULT de `categoria` (idempotente).

    `tipo` ("foto" | "miniatura") es un eje ortogonal a `categoria`: foto = plantilla para
    fotos/imagenes del feed; miniatura = portada/thumbnail de video. Las plantillas
    existentes reciben el DEFAULT "foto", que preserva el comportamiento previo al campo.
    """
    if not _tabla_existe(con, "plantillas_diseno"):
        return
    cols = _columnas_existentes(con, "plantillas_diseno")
    if "tipo" not in cols:
        con.execute(
            "ALTER TABLE plantillas_diseno ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'foto'"
        )
    # `rotar`: la plantilla entra en la ROTACIÓN automática de la marca (cada post nuevo se lleva
    # la siguiente del grupo; mismo color en todas las redes). Las existentes reciben 0 (sin rotar),
    # que preserva el comportamiento previo (la marca usa su plantilla por defecto/más reciente).
    if "rotar" not in cols:
        con.execute(
            "ALTER TABLE plantillas_diseno ADD COLUMN IF NOT EXISTS rotar INTEGER NOT NULL DEFAULT 0"
        )
    # `orden`: posición MANUAL del equipo dentro de la marca (drag-and-drop de la galería). Las
    # existentes reciben 0 ("sin ordenar" → recientes primero por el `creado DESC` secundario), que
    # preserva el comportamiento previo hasta que alguien las reordena a mano.
    if "orden" not in cols:
        con.execute(
            "ALTER TABLE plantillas_diseno ADD COLUMN IF NOT EXISTS orden INTEGER NOT NULL DEFAULT 0"
        )
    # `categoria` pasa de DEFAULT 'post' a 'general' (el fallback del catálogo de categorías).
    # Solo cambia el DEFAULT (metadato): las filas existentes NO se reescriben (el legado "post"
    # se trata como "general" en API y frontend). Idempotente.
    con.execute("ALTER TABLE plantillas_diseno ALTER COLUMN categoria SET DEFAULT 'general'")


def _migrar_columnas_video_composiciones(con: Any) -> None:
    """Anade `titulo`/`estado` a `video_composiciones` si una BD ya creada no las tuviera.

    Soporta DRAFTS (borradores) del Estudio de Video: `titulo` identifica la composicion en la
    lista; `estado` ∈ {borrador, listo} marca si esta lista para producir. Las composiciones
    existentes reciben los DEFAULTs (titulo vacio, estado 'borrador'), que preservan el
    comportamiento previo. Idempotente; mismo patron que `_migrar_columnas_plantillas_diseno`.
    """
    if not _tabla_existe(con, "video_composiciones"):
        return
    cols = _columnas_existentes(con, "video_composiciones")
    if "titulo" not in cols:
        con.execute(
            "ALTER TABLE video_composiciones ADD COLUMN IF NOT EXISTS titulo TEXT NOT NULL DEFAULT ''"
        )
    if "estado" not in cols:
        con.execute(
            "ALTER TABLE video_composiciones "
            "ADD COLUMN IF NOT EXISTS estado TEXT NOT NULL DEFAULT 'borrador'"
        )


def _migrar_columnas_etiquetas(con: Any) -> None:
    """Anade columnas nuevas a `etiquetas` si una BD ya creada no las tuviera (idempotente).

    - `keywords` (CSV) alimenta el auto-etiquetado de líneas (clase `vertical`) y de
      orígenes (clase `origen`) en la ingesta.
    - `ttl_dias` (INTEGER, def 0): días que un ítem de esta línea se considera fresco.
      0 = sin caducidad / evergreen.
    - `es_evergreen` (INTEGER, def 0): 1 = línea evergreen reutilizable en fines de semana.
    - `hashtags` (CSV/JSON, def ''): hashtags propios de la línea/estrategia, que se inyectan al
      final del copy de sus piezas (un único sitio para hashtags + estrategia de marca).

    Solo aplica si la tabla ya existe (un primer arranque la crea con las columnas).
    """
    if not _tabla_existe(con, "etiquetas"):
        return
    cols = _columnas_existentes(con, "etiquetas")
    if "keywords" not in cols:
        con.execute(
            "ALTER TABLE etiquetas ADD COLUMN IF NOT EXISTS keywords TEXT NOT NULL DEFAULT ''"
        )
    if "hashtags" not in cols:
        con.execute(
            "ALTER TABLE etiquetas ADD COLUMN IF NOT EXISTS hashtags TEXT NOT NULL DEFAULT ''"
        )
    if "ttl_dias" not in cols:
        con.execute(
            "ALTER TABLE etiquetas ADD COLUMN IF NOT EXISTS ttl_dias INTEGER NOT NULL DEFAULT 0"
        )
    if "es_evergreen" not in cols:
        con.execute(
            "ALTER TABLE etiquetas ADD COLUMN IF NOT EXISTS es_evergreen INTEGER NOT NULL DEFAULT 0"
        )


def _columnas_existentes(con: Any, tabla: str) -> set[str]:
    """Nombres de columnas que YA tiene `tabla` (Postgres, via `information_schema`).

    `tabla` es SIEMPRE un nombre interno de una allowlist (constantes del modulo, nunca
    entrada de usuario). El placeholder `?` lo traduce `motor_db` a `%s`.
    """
    filas = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        (tabla,),
    ).fetchall()
    return {fila["column_name"] for fila in filas}


def _tabla_existe(con: Any, tabla: str) -> bool:
    """True si `tabla` existe en el esquema actual (Postgres, `information_schema.tables`)."""
    fila = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1",
        (tabla,),
    ).fetchone()
    return fila is not None


def _migrar_green_a_evergreen(con: Any) -> None:
    """Rebrand GREEN -> EVERGREEN sobre una BD productiva (idempotente, preserva datos).

    El código pasó a `evergreen*`; este paso renombra el esquema/datos viejos para que NO
    se huérfanen. Todo guardado: en una BD fresca (sin `green*`) cada paso es no-op y el DDL
    crea ya `evergreen_ideas`/`es_evergreen`. Corre ANTES del DDL declarativo.
    """
    # Tabla green_ideas -> evergreen_ideas (+ sus índices). RENAME solo si la vieja existe y
    # la nueva no (re-ejecuciones seguras).
    if _tabla_existe(con, "green_ideas") and not _tabla_existe(con, "evergreen_ideas"):
        con.execute("ALTER TABLE green_ideas RENAME TO evergreen_ideas")
        con.execute("ALTER INDEX IF EXISTS idx_green_ideas_marca RENAME TO idx_evergreen_ideas_marca")
        con.execute("ALTER INDEX IF EXISTS idx_green_ideas_estado RENAME TO idx_evergreen_ideas_estado")
        con.execute("ALTER INDEX IF EXISTS idx_green_ideas_creado RENAME TO idx_evergreen_ideas_creado")
    # Columna etiquetas.es_green -> es_evergreen (preserva los flags ya marcados por el equipo).
    if _tabla_existe(con, "etiquetas"):
        cols = _columnas_existentes(con, "etiquetas")
        if "es_green" in cols and "es_evergreen" not in cols:
            con.execute("ALTER TABLE etiquetas RENAME COLUMN es_green TO es_evergreen")
        # Tag canónico 'green' -> 'evergreen' (contenido que el equipo ya etiquetó). Evita
        # colisión si por algún motivo ya existiera el tag 'evergreen' para esa marca.
        con.execute(
            "UPDATE etiquetas SET nombre = 'evergreen' WHERE nombre = 'green' "
            "AND NOT EXISTS (SELECT 1 FROM etiquetas e2 WHERE e2.nombre = 'evergreen' "
            "AND e2.marca = etiquetas.marca AND e2.id <> etiquetas.id)"
        )


# Defaults de franjas para la migracion (mismos que `rota.py`; los hardcodeamos aqui para
# no introducir dependencia ciclica db -> rota). Si la BD ya tiene config de franjas
# (`rota_config_franjas`), `_migrar_modelo_turnos` la respeta. La conversion de cobertura
# legada a turnos usa estos rangos para mapear hora del evento -> franja.
_MIGR_FRANJA_MATUTINO_INICIO_MIN = 8 * 60   # 08:00 inclusivo
_MIGR_FRANJA_MATUTINO_FIN_MIN = 16 * 60     # 16:00 exclusivo
_MIGR_FRANJA_VESPERTINO_INICIO_MIN = 16 * 60  # 16:00 inclusivo
_MIGR_FRANJA_VESPERTINO_FIN_MIN = 24 * 60   # 24:00 exclusivo


def _parsear_hora_a_minutos(crudo: str) -> int | None:
    """Convierte `HH:MM` (o un rango `HH:MM-HH:MM` del Excel) a minutos. None si malformado.

    Acepta sufijos del Excel real ("16:00-18:00", "16:00–18:00"): se queda con la hora de
    inicio. No lanza: la migracion debe ser tolerante con datos viejos sucios.
    """
    if not isinstance(crudo, str) or not crudo.strip():
        return None
    parte = crudo.strip().replace("–", "-").split("-", 1)[0].strip()
    partes = parte.split(":")
    if len(partes) < 2:
        return None
    try:
        h = int(partes[0])
        m = int(partes[1])
    except ValueError:
        return None
    if not (0 <= h <= 24 and 0 <= m <= 59):
        return None
    if h == 24 and m != 0:
        return None
    return h * 60 + m


def _franja_para_hora_migracion(
    hora: str, *, mat_ini: int, mat_fin: int, ves_ini: int, ves_fin: int
) -> str:
    """Mapea una hora a su franja usando rangos en MINUTOS. `descanso` si no encaja o malformado.

    Replica `rota.mapear_franja` sin tirar de el (para no introducir dep ciclica desde db.py).
    """
    minutos = _parsear_hora_a_minutos(hora)
    if minutos is None:
        return "descanso"
    if mat_ini <= minutos < mat_fin:
        return "matutino"
    if ves_ini <= minutos < ves_fin:
        return "vespertino"
    return "descanso"


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

    # PASO 2: sembrar la cobertura legada como turnos en _v2 (si la habia y tenia miembros).
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


# Nombres por defecto para sembrar las 2 franjas iniciales de una semana. Coherentes con
# `estados.NOMBRE_FRANJA_*_DEFAULT` (los re-importamos arriba). Mantener una sola fuente.
_NOMBRE_FRANJA_MANANA = NOMBRE_FRANJA_MANANA_DEFAULT
_NOMBRE_FRANJA_TARDE = NOMBRE_FRANJA_TARDE_DEFAULT


def _config_franjas_template(con: Any, marca: str = "") -> tuple[str, str, str, str]:
    """Devuelve `(matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin)` para
    sembrar las 2 franjas por defecto de una semana nueva.

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


def _sembrar_franjas_por_defecto_en(con: Any, lunes: str, marca: str = "") -> dict[str, str]:
    """Inserta (Mañana, Tarde, Descanso) en `rota_franjas` para `(marca, lunes)` si no existen.

    Devuelve el mapa `{nombre -> id}` con las franjas vigentes (sembradas o ya existentes) de
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
    semilla = [
        (_NOMBRE_FRANJA_MANANA, mat_ini, mat_fin, 0, False),
        (_NOMBRE_FRANJA_TARDE, ves_ini, ves_fin, 1, False),
        (_NOMBRE_FRANJA_DESCANSO, "00:00", "00:00", 999, True),
    ]
    for nombre, inicio, fin, orden, es_descanso in semilla:
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
    # transaccion sembro a la vez): el dict en memoria puede traer un id que no esta.
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
    # sembrar para que el INSERT no falle en instancias legadas que crearon la tabla sin
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

    # PASO 3 y 4: por cada semana con turnos legados, sembrar las 3 franjas por defecto y
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
            mapa = _sembrar_franjas_por_defecto_en(con, lunes)
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


# Columnas que se anadieron a `rota_eventos` despues de su esquema original (ola B, #144).
# Una BD creada antes no las tiene; `ALTER TABLE ... ADD COLUMN ... DEFAULT ...` es
# retrocompatible (las filas viejas quedan con el valor por defecto, sin reescribir nada):
#   - tipo_cobertura: transmision|imagenes|no_cubrir; legado -> "transmision" (sigue cubierto).
#   - prioridad: alta|media|baja; legado -> "media".
#   - cambiado: 0/1, "se reprogramo, hay que avisar"; legado -> 0 (sin reprogramar).
#   - actualizado: timestamp de la ultima edicion; legado -> "" (nunca editado tras migrar).
# Cada par es (columna, fragmento de tipo/DEFAULT) para emitir el ALTER correcto.
#   - origen/origen_ref: PROVENANCE de las filas creadas por la importacion de documentos
#     (`dominio.parrilla_import.ORIGEN == 'import-doc'`, `origen_ref` = id de la propuesta).
#     Legado -> "" (alta manual / migracion). Permite auditar y, en el futuro, deshacer.
_COLUMNAS_EVENTO_ROTA_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("tipo_cobertura", "TEXT NOT NULL DEFAULT 'transmision'"),
    ("prioridad", "TEXT NOT NULL DEFAULT 'media'"),
    ("cambiado", "INTEGER NOT NULL DEFAULT 0"),
    ("actualizado", "TEXT NOT NULL DEFAULT ''"),
    ("origen", "TEXT NOT NULL DEFAULT ''"),
    ("origen_ref", "TEXT NOT NULL DEFAULT ''"),
    ("marca", "TEXT NOT NULL DEFAULT ''"),
)

# Columnas de PROVENANCE que se anaden a `rota_turnos` para bases viejas (idempotente; el DDL
# declarativo ya las trae en bases nuevas). Mismo patron que `_COLUMNAS_EVENTO_ROTA_AMPLIADAS`.
_COLUMNAS_TURNO_ROTA_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("origen", "TEXT NOT NULL DEFAULT ''"),
    ("origen_ref", "TEXT NOT NULL DEFAULT ''"),
)


def _migrar_columnas_turnos_rota(con: Any) -> None:
    """Anade a `rota_turnos` las columnas de provenance (origen/origen_ref) si faltaran.

    Idempotente: una BD nueva ya las trae por el DDL declarativo; una vieja las recibe con
    DEFAULT '' sin reescribir nada (las filas existentes quedan como alta manual).
    """
    if not _COLUMNAS_TURNO_ROTA_AMPLIADAS:
        return
    columnas = _columnas_existentes(con, "rota_turnos")
    for columna, tipo in _COLUMNAS_TURNO_ROTA_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_turnos ADD COLUMN IF NOT EXISTS {columna} {tipo}")


# GRID POR MARCA: tablas del grid de rota que reciben la columna `marca`. Cada marca tiene su
# propia rejilla (franjas=columnas, turnos=celdas, coordinacion=coordinador por celda, swaps).
_TABLAS_GRID_ROTA_MARCA: tuple[str, ...] = (
    "rota_franjas",
    "rota_turnos",
    "rota_coordinacion",
    "rota_swaps_turno",
)

# Marca del piloto: el grid que existia antes de "grid por marca" era de Claro Sports, asi que
# las filas legadas (marca='') se backfillean a esta marca al introducir la columna.
_MARCA_PILOTO_ROTA = "claro-sports"


def _asegurar_marca_grid_rota(con: Any) -> None:
    """Añade `marca` al grid de rota y backfillea el grid legado a 'claro-sports' (idempotente).

    GRID POR MARCA: cada marca tiene su propia rejilla. Una BD nueva ya trae `marca` por el DDL;
    una vieja la recibe con DEFAULT '' y, SOLO cuando la columna no existia (= todas las filas
    son legadas), backfillea TODAS sus filas a 'claro-sports' (el piloto). Ademas:
      - retira el viejo UNIQUE(lunes,nombre) de `rota_franjas` (la unicidad pasa a
        (marca,lunes,nombre) via `idx_rota_franjas_uniq`, en los indices idempotentes),
      - reclava la config singleton `rota_config_franjas.id='default'` como la de 'claro-sports'
        (la config de franjas pasa a ser POR MARCA: `id` guarda el id de la marca).
    """
    for tabla in _TABLAS_GRID_ROTA_MARCA:
        if not _tabla_existe(con, tabla):
            continue
        if "marca" not in _columnas_existentes(con, tabla):
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN marca TEXT NOT NULL DEFAULT ''")
            # Backfill one-shot (solo al crear la columna): el grid existente era del piloto.
            con.execute(f"UPDATE {tabla} SET marca = ?", (_MARCA_PILOTO_ROTA,))  # noqa: S608 -- tabla de allowlist fija
    if _tabla_existe(con, "rota_franjas"):
        # Postgres nombra el UNIQUE inline `<tabla>_<cols>_key`; IF EXISTS lo hace no-op donde
        # no aplique (BD nueva sin ese constraint). La unicidad nueva la da el indice idempotente.
        con.execute(
            "ALTER TABLE rota_franjas DROP CONSTRAINT IF EXISTS rota_franjas_lunes_nombre_key"
        )
    if _tabla_existe(con, "rota_config_franjas"):
        # Solo si 'claro-sports' aun no tiene su fila (no pisar una config nueva por marca).
        ya = con.execute(
            "SELECT 1 FROM rota_config_franjas WHERE id = ?", (_MARCA_PILOTO_ROTA,)
        ).fetchone()
        if ya is None:
            con.execute(
                "UPDATE rota_config_franjas SET id = ? WHERE id = 'default'",
                (_MARCA_PILOTO_ROTA,),
            )


def _migrar_columnas_eventos_rota(con: Any) -> None:
    """Anade a `rota_eventos` las columnas de la ola B que una BD vieja no tuviera (idempotente).

    El `CREATE TABLE IF NOT EXISTS` ya las declara para bases NUEVAS, pero una base creada
    antes de la ampliacion (cobertura/prioridad/reprogramaciones) no las tiene. Recorre
    `_COLUMNAS_EVENTO_ROTA_AMPLIADAS` y anade solo la que falte con su DEFAULT: los eventos
    existentes quedan como `transmision`/`media`/sin reprogramar y no se pierde nada. El
    Postgres hosted persiste entre despliegues; era el origen del 500 del calendario.
    """
    columnas = _columnas_existentes(con, "rota_eventos")
    if not columnas:
        return  # tabla aún no existe: el DDL declarativo la crea fresca (con marca + índice)
    for columna, tipo in _COLUMNAS_EVENTO_ROTA_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_eventos ADD COLUMN IF NOT EXISTS {columna} {tipo}")


# Columnas de `rota_piezas` declaradas en el DDL inicial: cualquier columna que se
# anada DESPUES debera entrar aqui con `ALTER TABLE ... ADD COLUMN ... DEFAULT ...` para
# que las bases viejas la reciban (#150, PARRILLA 2026.xlsx). Mismo patron idempotente que
# `_migrar_columnas_eventos_rota`. Cada par es (columna, fragmento de tipo/DEFAULT).
#
# Ampliaciones reales del Excel (auditoria post-piloto):
#   - salida: canal MAS AMPLIO que `red_social` (en LA SELECCION EN TUS MANOS y MUNDIAL el
#     Excel registra "TV", "RADIO", "OOH", "MAILING", "PORTAL", "PROGRAMA", "YT", etc.;
#     incluye no-redes). `red_social` se reserva al detalle FB/IG/X/TK. Legado -> "".
#   - comentarios: texto LIBRE de coordinacion PRE/durante (distinto de `notas`, que es
#     post-mortem). En el Excel evergreen aparece como columna "Comentarios". Legado -> "".
#   - fecha_entrega_material: deadline INTERNO de cuando debe llegar el material a Tescu
#     antes de la fecha de publicacion. Columna "Fecha de Entrega (Material)" del Excel.
#     Legado -> "".
#   - always_on: pieza siempre activa sin fecha concreta (ej. "ALWAYS ON" de PATY CANTU,
#     teaser/promo evergreen). Si esta marcada, la fecha `dia` es opcional/ignorada por la
#     UI. Legado -> 0 (no es always-on).
_COLUMNAS_PIEZA_ROTA_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("salida", "TEXT NOT NULL DEFAULT ''"),
    ("comentarios", "TEXT NOT NULL DEFAULT ''"),
    ("fecha_entrega_material", "TEXT NOT NULL DEFAULT ''"),
    ("always_on", "INTEGER NOT NULL DEFAULT 0"),
)


def _migrar_columnas_piezas_rota(con: Any) -> None:
    """Anade a `rota_piezas` columnas ampliadas que una BD vieja no tuviera (idempotente).

    Hoy `rota_piezas` se crea entera con `CREATE TABLE IF NOT EXISTS`; esta migracion existe
    para futuras ampliaciones (mismo patron que `_migrar_columnas_eventos_rota`). Idempotente
    y segura: si no hay ampliaciones, no hace nada.
    """
    if not _COLUMNAS_PIEZA_ROTA_AMPLIADAS:
        return
    columnas = _columnas_existentes(con, "rota_piezas")
    for columna, tipo in _COLUMNAS_PIEZA_ROTA_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_piezas ADD COLUMN IF NOT EXISTS {columna} {tipo}")


# Columnas ampliadas de `contenido` / `contenido_plataforma` (tablero unificado). Hoy
# ambas tablas nacen enteras en el DDL declarativo (sin previas en produccion); estos
# hooks existen por coherencia con `_migrar_columnas_*` para futuras ampliaciones sin
# reescribir el esquema en bases hosted. Idempotentes; vacios no hacen nada.
_COLUMNAS_CONTENIDO_AMPLIADAS: tuple[tuple[str, str], ...] = (
    # Tipo de contenido (ia|galeria|fuente): de dónde sale la imagen de la pieza.
    ("tipo_contenido", "TEXT NOT NULL DEFAULT 'ia'"),
    # FORMATO de la pieza (foto|video): decide a qué redes va (regla del dueño). `foto` -> 3
    # redes (IG/X/FB); `video` -> las 5. El flujo automático crea piezas `foto`. El mapeo
    # formato->redes vive en `redes.redes_de_formato` (fuente única). BD vieja -> 'foto'.
    ("formato", "TEXT NOT NULL DEFAULT 'foto'"),
    # id_post_metricool a NIVEL pieza (Item C, métricas↔contenido): el id de Metricool
    # "principal" de la pieza, para enlazar el rendimiento de una pieza de Metricool de
    # vuelta a su `contenido` (y resolver sus etiquetas/tipo en las gráficas por serie).
    # El id REAL por red sigue viviendo en `contenido_plataforma.id_post_metricool` (una
    # pieza publica en N redes); este es un acceso directo a NIVEL contenido. Legado -> "".
    ("id_post_metricool", "TEXT NOT NULL DEFAULT ''"),
    # Señal de VIRALIDAD del Radar (Fase 5, loop de aprendizaje): el trafico aproximado REAL
    # de Google Trends (`radar.Tema.senal`) con que nacio la pieza, para que el score de
    # priorizacion (`priorizacion.peso_viralidad`) la use al ordenar la lista del dia. 0 =
    # sin señal (alta manual, RSS, o BD vieja): la pieza puntua como antes de la Fase 5.
    ("senal_viralidad", "INTEGER NOT NULL DEFAULT 0"),
    # QA de la FUENTE (pre-copy, rediseño QPC): el pipeline criba la NOTA DE ORIGEN antes de
    # generar copy. `qa_veredicto` = "no_verificado" (⚠️ OK para seguir) o "problema" (❗ algo de
    # peso: NO se generó copy). `qa_hallazgos` = JSON estructurado de lo encontrado. BD vieja -> "".
    ("qa_veredicto", "TEXT NOT NULL DEFAULT ''"),
    ("qa_hallazgos", "TEXT NOT NULL DEFAULT ''"),
    ("copy_pendiente", "TEXT NOT NULL DEFAULT ''"),
    # Fecha de la FUENTE de origen (pipeline): pubDate normalizado a ISO UTC. Las bases
    # creadas antes de esta columna la reciben aquí (idempotente). Legado -> "".
    ("fecha_fuente", "TEXT NOT NULL DEFAULT ''"),
    # URL de la NOTA DE ORIGEN (Investigador F3, dedup por URL): la URL canónica de la
    # fuente con que nació la pieza, para cruzar `existe_publicado_similar` por URL antes
    # de caer al fuzzy de título. "" si la pieza no nació de una URL (alta manual) o BD vieja.
    ("url_fuente", "TEXT NOT NULL DEFAULT ''"),
    # NOMBRE legible del MEDIO de origen ("Récord", "Reforma"…): se copia al `contenido` en
    # la promoción (CI) desde el item del cluster / la fuente RSS, porque el cluster puede
    # ser borrado por el GC de noticias y la pieza debe conservar su procedencia. La UI
    # (cabecera de grupo del feed) lo muestra junto a `fecha_fuente`; si va vacío (BD vieja,
    # alta manual) la serialización deriva el dominio de `url_fuente`. Legado -> "".
    ("fuente_nombre", "TEXT NOT NULL DEFAULT ''"),
    # ESPEJO entre redes (default ON): al editar el contenido de una pieza por red (copy,
    # copy-in, foto/collage, plantilla), los mismos campos se propagan a sus redes hermanas
    # (las piezas suelen ir parejas en todas las redes). 0 = cada red se edita por separado.
    # Lo aplica `api/publicaciones.actualizar` (no la capa db). BD vieja -> 1 (espejado).
    ("espejo", "INTEGER NOT NULL DEFAULT 1"),
)
_COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("es_publicacion", "INTEGER NOT NULL DEFAULT 0"),
    # URL de la imagen de la FUENTE original (cuando tipo_contenido='fuente'): se
    # previsualiza tal cual sin tener que descargarla a la texto de media.
    ("imagen_fuente", "TEXT NOT NULL DEFAULT ''"),
    # Media id de la FOTO CRUDA de fondo (la que el usuario sube/elige), separada de
    # `imagen` (la placa ya compuesta y publicable). Permite recomponer la placa en vivo.
    ("foto", "TEXT NOT NULL DEFAULT ''"),
    # Texto que va DENTRO de la imagen (copy-in: titular/claim sobre la placa), distinto
    # del `copy` que acompana a la publicacion. Se genera por marca con sus reglas/plantilla.
    ("copy_in", "TEXT NOT NULL DEFAULT ''"),
)


def _migrar_columnas_contenido(con: Any) -> None:
    """Anade a `contenido`/`contenido_plataforma` columnas que una BD vieja no tuviera."""
    for tabla, ampliadas in (
        ("contenido", _COLUMNAS_CONTENIDO_AMPLIADAS),
        ("contenido_plataforma", _COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS),
    ):
        if not ampliadas:
            continue
        columnas = _columnas_existentes(con, tabla)
        for columna, tipo in ampliadas:
            if columna not in columnas:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}")


# Columnas que se anaden a `contenido_aprobaciones` en bases creadas por una version
# anterior (el Postgres hosted persiste entre despliegues). `cargo_requerido` (item C: cargo
# del organigrama exigido por nivel) nace en el `CREATE TABLE` de las bases NUEVAS; este
# migrador la inyecta a las VIEJAS. Idempotente (no-op si ya esta o si la tabla no existe).
_COLUMNAS_APROBACIONES_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("cargo_requerido", "TEXT NOT NULL DEFAULT ''"),
)


def _migrar_columnas_aprobaciones(con: Any) -> None:
    """Anade a `contenido_aprobaciones` las columnas que una BD vieja no tuviera (idempotente)."""
    if not _tabla_existe(con, "contenido_aprobaciones"):
        return
    columnas = _columnas_existentes(con, "contenido_aprobaciones")
    for columna, tipo in _COLUMNAS_APROBACIONES_AMPLIADAS:
        if columna not in columnas:
            con.execute(
                f"ALTER TABLE contenido_aprobaciones ADD COLUMN IF NOT EXISTS {columna} {tipo}"
            )


# Columnas ampliadas del apartado comercial. Las bases creadas antes del paso a
# "monitorizar el post real de Metricool" no tienen `id_post_metricool` (la pieza se
# identificaba por `url`) ni `visualizaciones` en los snapshots (solo interacciones/
# alcance, de la curva sintetica). El Postgres hosted persiste entre despliegues:
# sin estos ALTER, una BD vieja reventaria al leer/escribir las columnas nuevas.
#
# Ola "metricas granulares por pieza": el snapshot pasa de 3 metricas (interacciones/
# visualizaciones/alcance) a capturar tambien el desglose que la fuente (Metricool, via
# `servicio.construir_metricas_pieza`) expone por pieza: likes, comentarios, compartidos,
# guardados, video_views, tiempo medio de visualizacion (s), clics de enlace y seguidores
# netos atribuidos. El `formato` (reel/foto/carrusel/video/link/texto) es propiedad ESTATICA
# de la pieza, no del snapshot: vive en `comercial_publicaciones`. Las columnas nacen con
# DEFAULT 0 / '' para alinear con las existentes (un dato ausente -> 0, sin ceros falsos en
# la UI, que distingue "sin dato" por `interacciones`/`encontrado`).
_COLUMNAS_COMERCIAL_PUBLICACIONES_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("id_post_metricool", "TEXT NOT NULL DEFAULT ''"),
    ("formato", "TEXT NOT NULL DEFAULT ''"),
)
_COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("visualizaciones", "INTEGER NOT NULL DEFAULT 0"),
    ("likes", "INTEGER NOT NULL DEFAULT 0"),
    ("comentarios", "INTEGER NOT NULL DEFAULT 0"),
    ("compartidos", "INTEGER NOT NULL DEFAULT 0"),
    ("guardados", "INTEGER NOT NULL DEFAULT 0"),
    ("video_views", "INTEGER NOT NULL DEFAULT 0"),
    ("tiempo_medio_vis_s", "INTEGER NOT NULL DEFAULT 0"),
    ("clics_enlace", "INTEGER NOT NULL DEFAULT 0"),
    ("seguidores_netos_atribuidos", "INTEGER NOT NULL DEFAULT 0"),
)


def _migrar_columnas_comercial(con: Any) -> None:
    """Anade al apartado comercial las columnas que una BD vieja no tuviera (idempotente)."""
    for tabla, ampliadas in (
        ("comercial_publicaciones", _COLUMNAS_COMERCIAL_PUBLICACIONES_AMPLIADAS),
        ("comercial_snapshots", _COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS),
    ):
        columnas = _columnas_existentes(con, tabla)
        for columna, tipo in ampliadas:
            if columna not in columnas:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}")


def _migrar_columnas_campanias(con: Any) -> None:
    """Migra `comercial_campanias` de marca ÚNICA a `marcas` (multimarca). Idempotente.

    Añade la columna `marcas` (array JSON) si falta y backfilla desde la `marca` (singular,
    vestigial) solo las filas aún sin migrar (`marcas = '[]'`). Para BDs nuevas es no-op: la
    tabla nace ya con `marcas` y sin filas que migrar.
    """
    columnas = _columnas_existentes(con, "comercial_campanias")
    if not columnas:
        return  # BD virgen: el DDL crea la tabla con `marcas`.
    if "marcas" not in columnas:
        con.execute(
            "ALTER TABLE comercial_campanias ADD COLUMN IF NOT EXISTS marcas TEXT NOT NULL DEFAULT '[]'"
        )
    if "marca" in columnas:
        filas = con.execute(
            "SELECT id, marca FROM comercial_campanias WHERE marcas = '[]' AND marca <> ''"
        ).fetchall()
        for fila in filas:
            con.execute(
                "UPDATE comercial_campanias SET marcas = ? WHERE id = ?",
                (json.dumps([fila["marca"]], ensure_ascii=False), fila["id"]),
            )


# Columnas que se podrian anadir a `rota_swaps_turno` en futuras ampliaciones. Hoy esta
# tupla esta VACIA: la primera version del swap nace ya con todo el esquema declarado en
# el `CREATE TABLE IF NOT EXISTS` (sin previas en produccion). Se conserva el hook por
# coherencia con el patron de `_migrar_columnas_*` (tareas, eventos): cuando aparezca una
# columna nueva, se agrega aqui como (col, tipo) y este migrador la pondra a las bases
# viejas sin reescribir nada. Idempotente.
_COLUMNAS_SWAP_AMPLIADAS: tuple[tuple[str, str], ...] = ()


def _migrar_columnas_swaps(con: Any) -> None:
    """Anade a `rota_swaps_turno` las columnas que una BD vieja no tuviera (idempotente).

    Hoy es no-op (tupla vacia): la tabla nace completa. Cuando se amplie, basta con
    declarar la columna en el `CREATE TABLE` (para bases NUEVAS) y anadir `(col, tipo)` a
    `_COLUMNAS_SWAP_AMPLIADAS` (para que las bases ANTIGUAS la reciban via ALTER). Mismo
    patron que `_migrar_columnas_eventos_rota`.
    """
    if not _COLUMNAS_SWAP_AMPLIADAS:
        return
    columnas = _columnas_existentes(con, "rota_swaps_turno")
    for columna, tipo in _COLUMNAS_SWAP_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_swaps_turno ADD COLUMN IF NOT EXISTS {columna} {tipo}")


# Columnas que se podrian anadir a `rota_programas`. Hoy esta tupla esta VACIA: la tabla
# nace completa en su primer DDL. Se conserva el hook por coherencia con el resto del
# patron `_migrar_columnas_*` (cuando aparezca una columna nueva, basta con anadirla aqui
# como `(col, tipo)` y a las bases viejas se le inyecta por ALTER sin reescribir nada).
_COLUMNAS_PROGRAMA_AMPLIADAS: tuple[tuple[str, str], ...] = ()


def _migrar_columnas_programas(con: Any) -> None:
    """Anade a `rota_programas` columnas ampliadas que una BD vieja no tuviera (idempotente).

    Hoy es no-op (tupla vacia). Mismo patron que `_migrar_columnas_swaps`.
    """
    if not _COLUMNAS_PROGRAMA_AMPLIADAS:
        return
    columnas = _columnas_existentes(con, "rota_programas")
    for columna, tipo in _COLUMNAS_PROGRAMA_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_programas ADD COLUMN IF NOT EXISTS {columna} {tipo}")


# Columnas que se anadieron a `usuarios` despues del esquema original (cargo + cobertura
# del equipo real, transcripciones AMX; `puede_coordinar` ola "coord"). Una BD creada
# antes no las tiene; legado -> `cargo=''` (sin clasificar), `cobertura=0` (no entra en
# rota), `puede_coordinar=false` (no es candidato a coordinador). Cada par es (columna,
# fragmento de tipo/DEFAULT).
#   - nombre: nombre HUMANO de la persona (Bernardo Vazquez, Elias...) para el organigrama;
#     legado -> "" (la UI cae al `usuario`/login). No es UNIQUE: dos personas pueden
#     llamarse igual, lo que identifica la cuenta sigue siendo `usuario`.
#   - manager_id: id del usuario SUPERIOR (a quien reporta) en el organigrama; legado/raiz
#     -> "" (sin superior, p.ej. el director). No es FK en la BD (ALTER ADD COLUMN no la
#     anade en SQLite y el organigrama tolera ids colgados tras un borrado); la capa API
#     valida que apunte a un usuario existente, distinto de si mismo y sin ciclos.
#   - mfa_activo / mfa_recovery_codes (segundo factor PASSKEYS/WebAuthn, gateado por
#     `KENI_CONSOLA_MFA`): ADITIVAS y con DEFAULT, asi una BD/usuario previos quedan SIN MFA
#     (`mfa_activo=0`) y el login sigue siendo identico hasta que alguien enrole una passkey.
#     La antigua columna TOTP `mfa_secret_cifrado` ya NO se anade (passkeys no guardan secreto
#     en el servidor); en BDs viejas se DROPA en `_migrar_columnas_usuarios`.
_COLUMNAS_USUARIOS_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("cargo", "TEXT NOT NULL DEFAULT ''"),
    ("cobertura", "INTEGER NOT NULL DEFAULT 0"),
    ("puede_coordinar", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("nombre", "TEXT NOT NULL DEFAULT ''"),
    ("manager_id", "TEXT NOT NULL DEFAULT ''"),
    ("mfa_activo", "INTEGER NOT NULL DEFAULT 0"),
    ("mfa_recovery_codes", "TEXT NOT NULL DEFAULT '[]'"),
)

# Columnas RETIRADAS de `usuarios` (se dropan si una BD vieja las tiene). `mfa_secret_cifrado`
# era el secreto TOTP cifrado; al migrar a passkeys (WebAuthn) ya no hay secreto del lado
# servidor, asi que la columna sobra. DROP idempotente (`IF EXISTS`).
_COLUMNAS_USUARIOS_RETIRADAS: tuple[str, ...] = ("mfa_secret_cifrado",)


def _migrar_columnas_usuarios(con: Any) -> None:
    """Anade a `usuarios` las columnas de cargo + cobertura que una BD vieja no tuviera.

    Mismo patron que `_migrar_columnas_eventos_rota`. Un usuario legado queda con cargo
    vacio y `cobertura=0` (no participa en rota hasta marcarlo).
    """
    columnas = _columnas_existentes(con, "usuarios")
    for columna, tipo in _COLUMNAS_USUARIOS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS {columna} {tipo}")
    # Migracion passkeys: dropamos la columna TOTP retirada (`mfa_secret_cifrado`) si la BD vieja
    # aun la tiene. `{columna}` viene de una allowlist del modulo (nunca entrada de usuario).
    for columna in _COLUMNAS_USUARIOS_RETIRADAS:
        if columna in columnas:
            con.execute(f"ALTER TABLE usuarios DROP COLUMN IF EXISTS {columna}")

# Columnas ampliables (mismo patron idempotente que `_migrar_columnas_*`): hoy ambas tablas
# nacen enteras en el DDL declarativo; estos hooks existen por coherencia para futuras
# ampliaciones sin reescribir el esquema en bases hosted. Vacios no hacen nada.
_COLUMNAS_FUENTES_RSS_AMPLIADAS: tuple[tuple[str, str], ...] = (
    # `propia`: la fuente es un sitio de MARCA PROPIA, así que su imagen original es
    # reutilizable. Al generar desde un item de una fuente propia, la pieza nace con la
    # imagen del artículo en `imagen_fuente` + `tipo_contenido='fuente'`.
    ("propia", "INTEGER NOT NULL DEFAULT 0"),
    # PLANIFICACIÓN del motor de ingesta persistente (Ola A). El `CREATE TABLE` ya las declara
    # para BDs nuevas; estas migran las BDs viejas (mismo patrón idempotente que
    # `_migrar_columnas_eventos_rota`). `intervalo_min`=0 -> usar el default por categoría;
    # `categoria` clasifica/ajusta la cadencia; `prioridad` mayor = más frecuente;
    # `proximo_sondeo` ISO ('' = sondear ya); `errores_seguidos`/`pausado_hasta` = backoff.
    ("intervalo_min", "INTEGER NOT NULL DEFAULT 0"),
    ("categoria", "TEXT NOT NULL DEFAULT ''"),
    ("prioridad", "INTEGER NOT NULL DEFAULT 0"),
    ("proximo_sondeo", "TEXT NOT NULL DEFAULT ''"),
    ("errores_seguidos", "INTEGER NOT NULL DEFAULT 0"),
    ("pausado_hasta", "TEXT NOT NULL DEFAULT ''"),
    # AUTO-DESACTIVADO (Ola D): el daemon pone `desactivado_auto=1` + `activo=0` cuando un feed
    # acumula `KENI_INGESTA_MAX_ERRORES` errores seguidos. Distingue "muerto por el motor" de
    # "apagado a mano" para poder reactivarlo desde /salud. En éxito se resetea.
    ("desactivado_auto", "INTEGER NOT NULL DEFAULT 0"),
    # FILTRO DE ENTRADA por vocabulario de marca: cuántos items descartó el último sondeo por
    # no casar la agenda de la marca (observabilidad del filtro de la puerta en /salud).
    ("ultimo_filtrados", "INTEGER NOT NULL DEFAULT 0"),
    # PESO editorial de la fuente: pondera la corroboración del ranking de historias
    # (potente 2.0 / normal 1.0 / baja 0.5, ver `dominio/fuentes_pesos.py`). Editable
    # desde la UI de Fuentes; el seed por host lo asigna `0026-backfill-pesos-fuente`.
    ("peso", "REAL NOT NULL DEFAULT 1.0"),
)

_COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS: tuple[tuple[str, str], ...] = ()

def _migrar_columnas_fuentes_rss(con: Any) -> None:
    """Anade a `fuentes_rss` columnas ampliadas que una BD vieja no tuviera (idempotente)."""
    if not _COLUMNAS_FUENTES_RSS_AMPLIADAS:
        return
    columnas = _columnas_existentes(con, "fuentes_rss")
    if not columnas:
        return  # tabla aún no existe: el DDL declarativo la crea fresca (con proximo_sondeo + índice)
    for columna, tipo in _COLUMNAS_FUENTES_RSS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE fuentes_rss ADD COLUMN IF NOT EXISTS {columna} {tipo}")

def _migrar_columnas_grupos_hashtags(con: Any) -> None:
    """Anade a `grupos_hashtags` columnas ampliadas que una BD vieja no tuviera (idempotente)."""
    if not _COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS:
        return
    columnas = _columnas_existentes(con, "grupos_hashtags")
    for columna, tipo in _COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE grupos_hashtags ADD COLUMN IF NOT EXISTS {columna} {tipo}")

# COBERTURA + traducción + verificación (Ola D): columnas nuevas de `noticias_clusters`. El
# `CREATE TABLE` ya las declara para BDs nuevas; estas migran las BDs viejas (mismo patrón
# idempotente). Algunas pueden existir ya (orden de despliegue de agentes en paralelo): el
# guard por `_columnas_existentes` las salta sin error.
_COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS: tuple[tuple[str, str], ...] = (
    # Auto-verificación por corroboración: corroborada / unica_fuente / dudosa.
    ("verificacion", "TEXT NOT NULL DEFAULT 'unica_fuente'"),
    # Traducción completa de historias extranjeras (best-effort, por lotes con Haiku).
    ("titulo_es", "TEXT NOT NULL DEFAULT ''"),
    ("resumen_es", "TEXT NOT NULL DEFAULT ''"),
    ("titulo_original", "TEXT NOT NULL DEFAULT ''"),
    ("idioma", "TEXT NOT NULL DEFAULT ''"),
    ("traducido", "INTEGER NOT NULL DEFAULT 0"),
    # Relevancia EXPLICABLE: la razón humana del score y su desglose por señal (JSON con
    # corroboracion/frescura/viralidad/marca/rendimiento/breaking + palabras casadas). Las
    # escribe el daemon al puntuar; la UI/el listón de promoción las muestran al equipo.
    ("score_razon", "TEXT NOT NULL DEFAULT ''"),
    ("score_desglose", "TEXT NOT NULL DEFAULT ''"),
    # TRACKING DE FUENTES (ranking ponderado): masa de corroboración (Σ peso por outlet),
    # señal de velocidad [0,1] (qué tan rápido se sumaron fuentes potentes), quién ABRIÓ la
    # historia y el timeline JSON de outlets (`clustering.fuentes_detalle`). Persistidos en
    # el cluster para que el re-score periódico no tenga que releer items.
    ("peso_fuentes", "REAL NOT NULL DEFAULT 0"),
    ("velocidad", "REAL NOT NULL DEFAULT 0"),
    ("primera_fuente", "TEXT NOT NULL DEFAULT ''"),
    ("primera_fuente_nombre", "TEXT NOT NULL DEFAULT ''"),
    ("fuentes_detalle", "TEXT NOT NULL DEFAULT ''"),
    # Encaje de marca por IA (ADR 0011): 1 si la marca de la historia la asignó el
    # clasificador Haiku (breaking sin marca), 0 si vino de los items / vocabulario.
    ("marca_clasificada_por_ia", "INTEGER NOT NULL DEFAULT 0"),
    # VERIFICACIÓN (QA de la fuente) sobre la HISTORIA, ANTES de materializar contenido de
    # producción (ADR 0011 F3): "no_verificado" (⚠️ apta, sigue a admisión) o "problema" (❗ no
    # se admite). `qa_hallazgos` = JSON estructurado de lo encontrado. Hereda al `contenido` al
    # admitir, así la frontera "QA = investigación" queda alineada con el modelo de datos. BD
    # vieja -> "" (sin veredicto: aún por cribar).
    ("qa_veredicto", "TEXT NOT NULL DEFAULT ''"),
    ("qa_hallazgos", "TEXT NOT NULL DEFAULT ''"),
)

def _migrar_columnas_noticias_clusters(con: Any) -> None:
    """Anade a `noticias_clusters` las columnas de la Ola D que una BD vieja no tuviera (idempotente)."""
    if not _tabla_existe(con, "noticias_clusters"):
        return
    columnas = _columnas_existentes(con, "noticias_clusters")
    for columna, tipo in _COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE noticias_clusters ADD COLUMN IF NOT EXISTS {columna} {tipo}")


# Columnas ampliables de `noticias_items` (mismo patrón idempotente). El CREATE TABLE ya las
# declara para BDs nuevas; esta tupla migra las BDs hosted existentes.
_COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS: tuple[tuple[str, str], ...] = (
    # PESO de la fuente del item, DENORMALIZADO al archivar (el clustering es una capa pura
    # sin BD: la señal viaja en el item, igual que `fuente_nombre`/`categoria`). Pondera la
    # corroboración del ranking de historias. Ver `dominio/fuentes_pesos.py`.
    ("fuente_peso", "REAL NOT NULL DEFAULT 1.0"),
    # CUERPO completo de la nota (content:encoded del feed). Lo escribe la ingesta y SOLO lo lee
    # el pipeline al promover (no entra en el SELECT/serializer del listado: path caliente lean).
    ("cuerpo", "TEXT NOT NULL DEFAULT ''"),
)


def _migrar_columnas_noticias_items(con: Any) -> None:
    """Anade a `noticias_items` columnas ampliadas que una BD vieja no tuviera (idempotente)."""
    if not _tabla_existe(con, "noticias_items"):
        return
    columnas = _columnas_existentes(con, "noticias_items")
    for columna, tipo in _COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE noticias_items ADD COLUMN IF NOT EXISTS {columna} {tipo}")


def _backfill_pesos_fuente(con: Any) -> None:
    """Backfill ONE-SHOT del peso editorial: seed por host en `fuentes_rss` + propagación.

    Tres pasos (cada uno idempotente; la migración corre una sola vez por BD):
      1. A cada fuente existente con peso por defecto (1.0) se le asigna el peso semilla de
         su HOST (`fuentes_pesos.peso_de_url`); los pesos ya editados a mano no se pisan.
      2. Los items archivados heredan el peso de su fuente (denormalización retroactiva).
      3. Los items de AGENCIA (`fuente_id` 'agencia-*': Reuters/AFP, sin fila en
         `fuentes_rss`) son potentes por definición.
    """
    from .dominio import fuentes_pesos  # import local: evitar ciclos en el arranque

    filas = con.execute("SELECT id, url, peso FROM fuentes_rss").fetchall()
    for fila in filas:
        if float(fila["peso"] or 1.0) != fuentes_pesos.PESO_NORMAL:
            continue  # peso ya ajustado (a mano o por un backfill previo): no pisar
        peso = fuentes_pesos.peso_de_url(fila["url"] or "")
        if peso != fuentes_pesos.PESO_NORMAL:
            con.execute("UPDATE fuentes_rss SET peso = ? WHERE id = ?", (peso, fila["id"]))
    con.execute(
        "UPDATE noticias_items SET fuente_peso = f.peso FROM fuentes_rss f "
        "WHERE noticias_items.fuente_id = f.id AND f.peso <> 1.0"
    )
    con.execute(
        # `agencia-%%`: el `%` literal va DOBLADO porque la sentencia lleva un parametro
        # (`?`->`%s`) y psycopg interpretaria un `%` suelto como inicio de placeholder. En
        # Postgres `%%`->`%` (comodin LIKE); en SQLite `%%` son dos comodines contiguos
        # (equivalentes a uno). Misma convencion que db_noticias.py (`es%%`).
        "UPDATE noticias_items SET fuente_peso = ? WHERE fuente_id LIKE 'agencia-%%'",
        (fuentes_pesos.PESO_POTENTE,),
    )

# --------------------------------------------------------------------------- #
# Normalizacion de TIMESTAMPS TEXT al canon UTC-sin-offset (ver `tiempo.py`)    #
# --------------------------------------------------------------------------- #
#
# Historicamente convivieron dos formatos en las MISMAS columnas TEXT: naive
# "YYYY-MM-DDTHH:MM:SS" (el ~80%) y aware "...+00:00" (a veces con microsegundos). Como
# estas columnas se comparan/ordenan LEXICOGRAFICAMENTE en SQL (poda de snapshots, keyset
# del feed `c.creado < ?`, dedup por `creado >=`, el UNIQUE de parrilla sobre el texto de
# `fecha_programada`), la mezcla rompia el orden. El canon es UTC SIN offset; aqui se
# normalizan los valores YA almacenados (idempotente: tras normalizar, ningun patron casa).
# Cada par es (tabla, columna, longitud_canon): 19 = segundos ("...THH:MM:SS"), 16 =
# minutos ("...THH:MM", el canon de `fecha_programada`, que generan franjas/cadencias/UI).
_COLUMNAS_TS_CANON: tuple[tuple[str, str, int], ...] = (
    ("contenido", "creado", 19),
    ("contenido", "actualizado", 19),
    ("contenido_plataforma", "creado", 19),
    ("contenido_plataforma", "actualizado", 19),
    ("contenido_plataforma", "preparado_en", 19),
    ("contenido_plataforma", "fecha_programada", 16),
    ("metricas_pieza_snapshots", "ts", 19),
    ("comercial_snapshots", "ts", 19),
    # Motor de noticias: estas columnas se comparan/ordenan como texto (ventanas 24h,
    # GC del pool, `ultimo_visto >= ?`, `capturado_en >= ?`, `proximo_sondeo <= ahora`,
    # `MAX(ultima_actualizacion)`) y se escribian con `datetime.now(UTC).isoformat()`
    # (aware + microsegundos) hasta la unificacion al canon. OJO: los `creado` de
    # DESEMPATE (fuentes_rss/fuentes_algoritmo/sugerencias_editoriales/...) NO van aqui:
    # sus microsegundos naive son intencionales y compatibles con el orden (ver tiempo.py).
    ("noticias_items", "capturado_en", 19),
    ("noticias_items", "creado", 19),
    ("noticias_items", "publicado_en", 19),
    ("noticias_clusters", "primer_visto", 19),
    ("noticias_clusters", "ultimo_visto", 19),
    ("noticias_clusters", "creado", 19),
    ("noticias_clusters", "actualizado", 19),
    ("fuentes_rss", "ultima_actualizacion", 19),
    ("fuentes_rss", "proximo_sondeo", 19),
    ("fuentes_rss", "pausado_hasta", 19),
    ("fuentes_algoritmo", "ultima_actualizacion", 19),
    # Auth: `webauthn_credenciales` se ordena por `creada` como texto; el resto se parsea
    # en Python pero compartia el formato aware de `auth/_comun.iso` (tambien unificado).
    ("usuarios", "creado", 19),
    ("usuarios", "ultimo_acceso", 19),
    ("usuarios", "bloqueo_hasta", 19),
    ("sesiones", "creada", 19),
    ("sesiones", "ultimo_uso", 19),
    ("sesiones", "expira", 19),
    ("webauthn_credenciales", "creada", 19),
    ("webauthn_credenciales", "ultimo_uso", 19),
)

# Valor ISO naive con fraccion de segundo (microsegundos de `isoformat()` sin timespec).
_RE_TS_NAIVE_FRACCION = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+$"
# Valor ISO con zona explicita (+HH:MM/-HH:MM/Z), con o sin segundos/fraccion. El patron
# es ESTRICTO a proposito: solo castea a timestamptz lo que seguro parsea (un valor
# malformado no casa y se deja tal cual, sin reventar la migracion).
_RE_TS_CON_ZONA = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:\d{2}|Z)$"


def _normalizar_timestamps_texto(con: Any) -> None:
    """Normaliza al canon (UTC sin offset) los timestamps TEXT ya almacenados (idempotente).

    Dos pasadas por columna, ambas acotadas por regex estrictas (solo toca lo que casa):
      1. naive con MICROSEGUNDOS -> truncado por texto a la longitud canon.
      2. con ZONA (+HH:MM/Z) -> cast a `timestamptz`, conversion a UTC y re-formateo
         sin offset (asi un hipotetico "-06:00" tambien queda bien, no solo "+00:00").
    Best-effort: un fallo se loguea y NO tumba el arranque (rollback y se sigue); la
    columna quedaria mixta hasta el proximo arranque, igual que antes del fix.
    """
    for tabla, col, largo in _COLUMNAS_TS_CANON:
        if not _tabla_existe(con, tabla):
            continue
        formato = "YYYY-MM-DD\"T\"HH24:MI:SS" if largo == 19 else "YYYY-MM-DD\"T\"HH24:MI"
        try:
            con.execute(
                f"UPDATE {tabla} SET {col} = left({col}, ?) WHERE {col} ~ ?",  # noqa: S608 -- allowlist fija
                (largo, _RE_TS_NAIVE_FRACCION),
            )
            # `fecha_programada` (canon minutos): tambien recorta los naive con segundos.
            if largo == 16:
                con.execute(
                    f"UPDATE {tabla} SET {col} = left({col}, 16) "  # noqa: S608 -- allowlist fija
                    f"WHERE {col} ~ ?",
                    (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$",),
                )
            con.execute(
                f"UPDATE {tabla} SET {col} = "  # noqa: S608 -- allowlist fija
                f"to_char(({col})::timestamptz AT TIME ZONE 'UTC', ?) "
                f"WHERE {col} ~ ?",
                (formato, _RE_TS_CON_ZONA),
            )
            con.commit()
        except Exception:  # noqa: BLE001 -- best-effort: no tumbar el arranque por una columna
            _log.warning(
                "No se pudo normalizar el timestamp %s.%s al canon UTC.", tabla, col,
                exc_info=True,
            )
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass


def _dedup_turnos_rota(con: Any) -> None:
    """Borra turnos DUPLICADOS en `rota_turnos` (misma marca/semana/fecha/miembro/franja).

    Limpieza previa al indice unico `idx_rota_turnos_uniq`: el check-then-insert historico
    del endpoint permitia duplicar un turno bajo carrera; un CREATE UNIQUE INDEX sobre esos
    duplicados fallaria. Conserva el turno MAS ANTIGUO (menor `(creado, id)`) de cada grupo
    y solo considera turnos con miembro asignado (el indice es parcial: `miembro_id <> ''`).
    Best-effort e idempotente.
    """
    if not _tabla_existe(con, "rota_turnos"):
        return
    try:
        con.execute(
            "DELETE FROM rota_turnos a USING rota_turnos b "
            "WHERE a.miembro_id <> '' AND a.marca = b.marca AND a.semana = b.semana "
            "AND a.fecha = b.fecha AND a.miembro_id = b.miembro_id "
            "AND a.franja_id = b.franja_id AND (a.creado, a.id) > (b.creado, b.id)"
        )
        con.commit()
    except Exception:  # noqa: BLE001 -- best-effort: el indice unico avisara si quedan duplicados
        _log.warning("No se pudieron deduplicar los turnos de rota.", exc_info=True)
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass


# Indices UNICOS que dan idempotencia a tres tablas que hoy se duplican (mismo grupo/franja/
# fuente insertados dos veces). Se crean DEFENSIVAMENTE (no en el DDL declarativo): una BD
# productiva PUEDE tener ya duplicados, y un `CREATE UNIQUE INDEX` sobre datos duplicados
# revienta. Por eso van fuera del bucle de `_DDL_ESQUEMA` (que aborta el arranque ante
# cualquier fallo) y cada uno se intenta aislado: si falla por duplicados, se loguea y se
# sigue (la tabla queda sin el constraint hasta que se limpien los duplicados a mano). El
# `IF NOT EXISTS` lo hace idempotente cuando ya existe; los INSERT correspondientes usan
# `ON CONFLICT (...) DO NOTHING` (mismo patron que `rota_franjas`), inofensivo aunque el
# indice aun no exista (sin conflicto que ignorar).
# NOTA: `fuentes_rss` NO lleva UNIQUE(url) a proposito: el producto permite registrar la
# MISMA URL en varias fuentes (distinta marca, filtros incluir/excluir o nombre). La
# deduplicacion de ITEMS ya la cubre `rss_items_vistos` (PK compuesta). Imponer UNIQUE(url)
# rompia ese caso de uso legitimo.
_INDICES_UNICOS_IDEMPOTENCIA: tuple[tuple[str, str], ...] = (
    ("idx_grupos_hashtags_uniq", "grupos_hashtags (nombre, marca)"),
    ("idx_franjas_editoriales_uniq2", "franjas_editoriales (marca, red, dia_semana, hora, categoria)"),
    # GRID POR MARCA: el NOMBRE de una franja es unico por (marca, lunes) — dos marcas pueden
    # tener su propia "Mañana" la misma semana. Sustituye al viejo UNIQUE(lunes,nombre) inline
    # (que `_asegurar_marca_grid_rota` dropa). El ON CONFLICT (marca,lunes,nombre) de la siembra
    # se apoya en este indice.
    ("idx_rota_franjas_uniq", "rota_franjas (marca, lunes, nombre)"),
    # Contador de versiones POR PIEZA: dos ediciones concurrentes calculaban `MAX(version)+1`
    # y, sin unicidad, insertaban la MISMA version (historial duplicado/roto). El indice unico
    # convierte ese choque en una UniqueViolation que el INSERT REINTENTA con el numero siguiente
    # (ver `crear_documento_version` / `registrar_copy_version`).
    ("idx_documento_versiones_uniq", "documento_versiones (contenido_id, plataforma_id, version)"),
    ("idx_copy_versiones_uniq", "contenido_copy_versiones (plataforma_id, version)"),
    # PARRILLA — doble-reserva POR MARCA (fix implementado). El slot correcto es por (marca, red,
    # fecha): dos marcas distintas SI pueden publicar en la misma red a la misma hora, pero la
    # MISMA marca no puede doble-reservar el mismo slot. Una version previa puso un UNIQUE solo por
    # (red, fecha) y hubo que retirarlo: chocaba ENTRE MARCAS porque `marca` vivia en `contenido`
    # (padre) y un indice PARCIAL no puede cruzar el join. La solucion: DENORMALIZAR `marca` en
    # `contenido_plataforma` (columna mantenida en sync en toda escritura: derivada del padre al
    # insertar, propagada al reasignar la marca del padre; ver `crear_contenido_plataforma` y
    # `actualizar_contenido`) y entonces SI cabe el UNIQUE parcial por (marca, red, fecha). El
    # predicado exige `estado='programado'` (solo lo programado reserva slot) Y `fecha_programada
    # <> ''` (borradores sin fecha no chocan entre si). El backstop+reintento de la carrera vive en
    # `api.publicaciones._encolar_en_hueco_libre` y en el PUT (`api.publicaciones.actualizar`).
    (
        "idx_parrilla_slot_uniq",
        "contenido_plataforma (marca, red, fecha_programada) "
        "WHERE estado = 'programado' AND fecha_programada <> ''",
    ),
    # ROTA — turnos duplicables (check-then-insert sin constraint): dos peticiones simultaneas
    # pasaban ambas el pre-check del endpoint e insertaban el MISMO turno. El indice parcial
    # (solo turnos con miembro asignado: los huecos sin miembro no chocan entre si) convierte
    # la carrera en IntegrityError, que el endpoint traduce a 409. La limpieza de duplicados
    # previos vive en `_dedup_turnos_rota` (corre justo antes de crear estos indices).
    (
        "idx_rota_turnos_uniq",
        "rota_turnos (marca, semana, fecha, miembro_id, franja_id) WHERE miembro_id <> ''",
    ),
)

def _crear_indices_unicos_idempotencia(con: Any) -> None:
    """Crea los indices UNICOS de idempotencia, aislando cada uno ante duplicados previos.

    Cada `CREATE UNIQUE INDEX IF NOT EXISTS` se ejecuta + commitea por separado: si una tabla
    ya tiene duplicados en prod, Postgres lanza una `UniqueViolation` (23505), que el shim de
    `motor_db` ya re-lanza como `IntegrityError` TRAS hacer rollback de la conexion. Se loguea
    un WARNING y se sigue (no rompe el arranque), pero los demas indices SI se aplican.
    Requiere limpieza manual de los duplicados para que el indice fallido entre en un arranque
    posterior. El `IF NOT EXISTS` lo hace idempotente cuando el indice ya existe.
    """
    for nombre_indice, destino in _INDICES_UNICOS_IDEMPOTENCIA:
        try:
            con.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {nombre_indice} ON {destino}")
            con.commit()
        except IntegrityError as e:
            # El shim de `motor_db` ya hizo rollback de la conexion al mapear la
            # UniqueViolation; aqui solo dejamos rastro y seguimos con el resto de indices.
            _log.warning(
                "No se pudo crear el indice unico %s ON %s (probables duplicados previos; "
                "requiere limpieza manual): %s",
                nombre_indice,
                destino,
                e,
            )


# --------------------------------------------------------------------------- #
# REGISTRO ordenado de migraciones (ver la REGLA junto a `_DDL_SCHEMA_MIGRACIONES`)
# --------------------------------------------------------------------------- #
# Definido AQUI (final del modulo) porque referencia las fns y tuplas de arriba. Todas las
# entradas actuales son las migraciones LEGADAS re-ejecutables -> `re_aplicar_si_cambia=True`
# (su id de journal lleva huella de contenido: editar la fn o su tupla directora las
# re-aplica una vez). Las migraciones NUEVAS van AL FINAL de POST_DDL con nombre secuencial
# y SIN `re_aplicar_si_cambia` (corren exactamente una vez por BD).

# PRE-DDL: transforman la forma VIEJA de una tabla ANTES de que el DDL declarativo cree
# tablas/indices que chocarian con ella (indice sobre columna aun inexistente "envenena" la
# conexion; un CREATE TABLE IF NOT EXISTS sobre un renombre pendiente huerfanaria los datos).
MIGRACIONES_PRE_DDL: tuple[Migracion, ...] = (
    # El DDL declara `rota_turnos` con la forma NUEVA (fecha/franja); una BD con el modelo
    # viejo (cobertura) debe convertirse antes (renombre + drop + renombre final).
    Migracion("0001-modelo-turnos", _migrar_modelo_turnos, re_aplicar_si_cambia=True),
    # Franjas POR SEMANA: asegura `rota_franjas` + `rota_turnos.franja_id` antes del indice
    # `idx_rota_turnos_franja_id` del DDL (en BDs viejas solo existia `franja` literal).
    Migracion("0002-modelo-franjas", _migrar_modelo_franjas, re_aplicar_si_cambia=True),
    # Columnas usadas por INDICES del DDL declarativo (idx_rota_eventos_marca,
    # idx_fuentes_rss_sondeo, idx_plantillas_diseno_tipo): se anaden antes de crearlos.
    Migracion(
        "0003-columnas-eventos-rota",
        _migrar_columnas_eventos_rota,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_EVENTO_ROTA_AMPLIADAS,
    ),
    Migracion(
        "0004-columnas-fuentes-rss",
        _migrar_columnas_fuentes_rss,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_FUENTES_RSS_AMPLIADAS,
    ),
    Migracion(
        "0005-columnas-plantillas-diseno",
        _migrar_columnas_plantillas_diseno,
        re_aplicar_si_cambia=True,
    ),
    # Renombres: deben correr antes de que el DDL cree la tabla nueva VACIA y huerfane datos.
    Migracion("0006-green-a-evergreen", _migrar_green_a_evergreen, re_aplicar_si_cambia=True),
    Migracion(
        "0007-renombre-catalogo-media", _migrar_renombre_catalogo_media, re_aplicar_si_cambia=True
    ),
    # GRID POR MARCA: anade `marca` al grid de rota antes de los indices `idx_rota_*_marca`.
    Migracion("0008-marca-grid-rota", _asegurar_marca_grid_rota, re_aplicar_si_cambia=True),
)

# POST-DDL: ALTER/backfill sobre tablas que el DDL ya garantiza (anaden columnas a BDs
# creadas por versiones anteriores; el Postgres hosted persiste entre despliegues).
MIGRACIONES_POST_DDL: tuple[Migracion, ...] = (
    Migracion(
        "0009-columnas-turnos-rota",
        _migrar_columnas_turnos_rota,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_TURNO_ROTA_AMPLIADAS,
    ),
    Migracion(
        "0010-columnas-piezas-rota",
        _migrar_columnas_piezas_rota,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_PIEZA_ROTA_AMPLIADAS,
    ),
    Migracion(
        "0011-columnas-contenido",
        _migrar_columnas_contenido,
        re_aplicar_si_cambia=True,
        datos=(_COLUMNAS_CONTENIDO_AMPLIADAS, _COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS),
    ),
    Migracion(
        "0012-columnas-aprobaciones",
        _migrar_columnas_aprobaciones,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_APROBACIONES_AMPLIADAS,
    ),
    Migracion(
        "0013-columnas-comercial",
        _migrar_columnas_comercial,
        re_aplicar_si_cambia=True,
        datos=(
            _COLUMNAS_COMERCIAL_PUBLICACIONES_AMPLIADAS,
            _COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS,
        ),
    ),
    Migracion("0014-columnas-campanias", _migrar_columnas_campanias, re_aplicar_si_cambia=True),
    Migracion(
        "0015-columnas-swaps",
        _migrar_columnas_swaps,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_SWAP_AMPLIADAS,
    ),
    Migracion(
        "0016-columnas-programas",
        _migrar_columnas_programas,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_PROGRAMA_AMPLIADAS,
    ),
    Migracion(
        "0017-columnas-usuarios",
        _migrar_columnas_usuarios,
        re_aplicar_si_cambia=True,
        datos=(_COLUMNAS_USUARIOS_AMPLIADAS, _COLUMNAS_USUARIOS_RETIRADAS),
    ),
    Migracion(
        "0018-columnas-grupos-hashtags",
        _migrar_columnas_grupos_hashtags,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS,
    ),
    Migracion(
        "0019-columnas-noticias-clusters",
        _migrar_columnas_noticias_clusters,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS,
    ),
    Migracion(
        "0020-columnas-noticias-algoritmo",
        _migrar_columnas_noticias_algoritmo,
        re_aplicar_si_cambia=True,
    ),
    Migracion("0021-columnas-etiquetas", _migrar_columnas_etiquetas, re_aplicar_si_cambia=True),
    Migracion(
        "0022-columnas-contenido-plataforma",
        _migrar_columnas_contenido_plataforma,
        re_aplicar_si_cambia=True,
    ),
    Migracion(
        "0023-columnas-video-composiciones",
        _migrar_columnas_video_composiciones,
        re_aplicar_si_cambia=True,
    ),
    # Normalizacion de TIMESTAMPS TEXT al canon UTC-sin-offset (ver `tiempo.ahora_iso`):
    # idempotente y best-effort POR COLUMNA, ANTES de los indices unicos (el de parrilla
    # compara el texto crudo de `fecha_programada`; con formatos mixtos dos reservas iguales
    # no chocan). Anadir una columna a `_COLUMNAS_TS_CANON` cambia la huella -> se re-aplica.
    Migracion(
        "0024-normalizar-timestamps",
        _normalizar_timestamps_texto,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_TS_CANON,
    ),
    # Peso editorial de fuentes (ranking ponderado): columna en `noticias_items` para BDs
    # viejas (re-aplicable: añadir columnas a la tupla cambia la huella)…
    Migracion(
        "0025-columnas-noticias-items",
        _migrar_columnas_noticias_items,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS,
    ),
    # …y backfill ONE-SHOT del seed por host + propagación a items archivados (corre una
    # sola vez por BD: los pesos editados a mano después no se vuelven a pisar).
    Migracion("0026-backfill-pesos-fuente", _backfill_pesos_fuente),
)

# Vista unica y ordenada (PRE + POST), util para tests/inspeccion.
MIGRACIONES: tuple[Migracion, ...] = MIGRACIONES_PRE_DDL + MIGRACIONES_POST_DDL


__all__ = [
    "_COLUMNAS_APROBACIONES_AMPLIADAS",
    "_COLUMNAS_COMERCIAL_PUBLICACIONES_AMPLIADAS",
    "_COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS",
    "_COLUMNAS_CONTENIDO_AMPLIADAS",
    "_COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS",
    "_COLUMNAS_EVENTO_ROTA_AMPLIADAS",
    "_COLUMNAS_FUENTES_RSS_AMPLIADAS",
    "_COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS",
    "_COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS",
    "_COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS",
    "_COLUMNAS_PIEZA_ROTA_AMPLIADAS",
    "_COLUMNAS_PROGRAMA_AMPLIADAS",
    "_COLUMNAS_SWAP_AMPLIADAS",
    "_COLUMNAS_TURNO_ROTA_AMPLIADAS",
    "_COLUMNAS_USUARIOS_AMPLIADAS",
    "_COLUMNAS_USUARIOS_RETIRADAS",
    "_DDL_ESQUEMA",
    "_DDL_SCHEMA_MIGRACIONES",
    "_INDICES_UNICOS_IDEMPOTENCIA",
    "_LOCK_NS_BARRIDO",
    "MIGRACIONES",
    "MIGRACIONES_POST_DDL",
    "MIGRACIONES_PRE_DDL",
    "Migracion",
    "_MIGR_FRANJA_MATUTINO_FIN_MIN",
    "_MIGR_FRANJA_MATUTINO_INICIO_MIN",
    "_MIGR_FRANJA_VESPERTINO_FIN_MIN",
    "_MIGR_FRANJA_VESPERTINO_INICIO_MIN",
    "_NOMBRE_FRANJA_DESCANSO",
    "_NOMBRE_FRANJA_MANANA",
    "_NOMBRE_FRANJA_TARDE",
    "_aplicar_migraciones",
    "_clave_lock",
    "_columnas_existentes",
    "_id_migracion",
    "_conectar",
    "_config_franjas_template",
    "_crear_esquema",
    "_crear_indices_unicos_idempotencia",
    "_esquemas_asegurados",
    "_franja_para_hora_migracion",
    "_lock_esquemas",
    "_migrar_columnas_aprobaciones",
    "_migrar_columnas_comercial",
    "_migrar_columnas_contenido",
    "_migrar_columnas_contenido_plataforma",
    "_migrar_columnas_etiquetas",
    "_migrar_columnas_eventos_rota",
    "_migrar_columnas_fuentes_rss",
    "_migrar_columnas_grupos_hashtags",
    "_migrar_columnas_noticias_algoritmo",
    "_migrar_columnas_noticias_clusters",
    "_migrar_columnas_piezas_rota",
    "_migrar_columnas_plantillas_diseno",
    "_migrar_columnas_programas",
    "_migrar_columnas_swaps",
    "_migrar_columnas_turnos_rota",
    "_migrar_columnas_usuarios",
    "_migrar_columnas_video_composiciones",
    "_migrar_modelo_franjas",
    "_migrar_modelo_turnos",
    "_parsear_hora_a_minutos",
    "_sembrar_franjas_por_defecto_en",
    "_tabla_existe",
    "arrancar_persistencia",
    "conectar",
    "lock_barrido",
]

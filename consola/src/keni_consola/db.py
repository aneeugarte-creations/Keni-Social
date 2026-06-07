"""Persistencia OPERACIONAL de la Consola Keni: Postgres (ADR 0004).

Cubre lo que NO es contenido editable a mano: las `tareas`, el apartado `comercial`
(seguimiento de piezas + su serie temporal de snapshots), la `rota` y, via `auth/`, los
`usuarios`/`sesiones`. El CONTENIDO editorial (publicaciones, plantillas, fuentes RSS,
hashtags, franjas, historial de skills) vive en ficheros YAML por marca (`ficheros.py`),
con un indice SQLite regenerable (`indice.py`). La fachada `repos.py` enruta cada cosa a
su almacen.

BACKEND (#130 / ADR 0004): UNICO, Postgres. `motor_db.conectar_cruda()` abre Postgres con
`DATABASE_URL` (OBLIGATORIA, local o hosted). Antes el backend se elegia segun esa var
(sin URL -> SQLite local); la ADR 0004 retira ese SQLite operacional para eliminar el drift
SQLite<->Postgres. En desarrollo no se usa Postgres local: la ejecucion/validacion se hace
en el server (CI Woodpecker / hosted); quien necesite correr en local provee su propio
`DATABASE_URL`. La privacidad del perfil local se preserva si ese Postgres corre en la
propia maquina; se pierde el "cero-config/offline por defecto".

El esquema se crea ON-DEMAND en la primera conexion (idempotente). Las funciones publicas y
la fachada `repos.py` son ESTABLES: ningun call site cambia (siguen usando `?`/`fila["col"]`,
que `motor_db` traduce a Postgres).

SEGURIDAD:
  - SIEMPRE consultas PARAMETRIZADAS (`?`), NUNCA f-strings con datos en el SQL. El
    `motor_db` traduce `?`->`%s` en Postgres sin tocar los datos.
  - Con un Postgres LOCAL ninguna fila sale de la maquina (privacidad preservada).

Tablas:
  - `tareas`(id, proyecto, titulo, detalle, estado, fecha, autor_id, autor_nombre,
    responsable_id, responsable_nombre, enlace)
    [tablero de pendientes compartido del equipo (#145): autor = quien la creo;
    responsable = a quien se le asigna; enlace = ruta/URL opcional para actuar]
  - `comercial_publicaciones`(id, url, id_post_metricool, titulo, marca, cliente,
    campania, red, metrica_objetivo, objetivo, estado, publicado, notas, aviso_en,
    fecha_creacion, fecha_actualizacion)
    [seguimiento de UNA publicacion comercial por su `id_post_metricool` (post real de
    Metricool); estado activa|pausada|cerrada]
  - `comercial_snapshots`(id, publicacion_id, ts, interacciones, visualizaciones, alcance)
    [serie temporal de cada publicacion; UNIQUE(publicacion_id, ts)]
  - `usuarios`(id, usuario UNICO, rol, salt, hash, debe_cambiar_password,
    intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso)
    [auth multiusuario (#130): el `salt`/`hash` son scrypt; NUNCA texto plano]
  - `sesiones`(token, usuario_id, creada, ultimo_uso, expira)
    [sesion server-side por cookie; el token es el de la cookie del navegador]

  La logica de auth (hashing, login, sesiones, bootstrap) vive en `auth/`, que
  reutiliza la conexion de este modulo (`conectar`). El esquema de `usuarios`/
  `sesiones` se crea aqui (on-demand, idempotente) para que exista por cualquier
  via de arranque.

Las funciones devuelven `dict`s simples (filas) o ids, sin acoplar la capa API al
backend. Cada operacion abre y cierra su propia conexion (mantenerlo simple evita estado
global y problemas de hilos con el `TestClient`; es una conexion por op).

CONCURRENCIA (servicio compartido, #130): la concurrencia multiusuario/multi-replica es
nativa de Postgres (el claim de la cola de jobs usa `FOR UPDATE SKIP LOCKED`); ese fue el
motivo de migrar y de retirar SQLite (ADR 0004).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

_log = logging.getLogger("keni_consola.db")

# Allowlists de dominio (neutras, sin acoplar al backend): viven en `estados.py`.
from . import config, motor_db, redes
from .estados import (
    CLASE_CONTENIDO,
    DECISION_APROBADO,
    DECISION_PENDIENTE,
    DECISION_RECHAZADO,
    ESTADO_COMERCIAL_ACTIVA,
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_PROPUESTO,
    ESTADOS_COMERCIAL,
    ESTADOS_CONTENIDO,
    ESTADOS_CONTENIDO_PLATAFORMA,
    ESTADOS_PIEZA,
    ESTADOS_ROTA,
    ESTADOS_SWAP,
    ESTADOS_TAREA,
    METRICAS_COMERCIAL,
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
    PRIORIDAD_CONTENIDO_DEFECTO,
    PRIORIDAD_EVENTO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPO_CONTENIDO_DEFECTO,
    TIPOS_AUSENCIA,
    TIPOS_COBERTURA,
    TIPOS_CONTENIDO,
)
from .motor_db import IntegrityError

__all__ = [
    "ESTADO_COMERCIAL_ACTIVA",
    "ESTADO_ROTA_APROBADO",
    "ESTADO_ROTA_PROPUESTO",
    "ESTADO_SWAP_PROPUESTO",
    "ESTADOS_COMERCIAL",
    "ESTADOS_PIEZA",
    "ESTADOS_ROTA",
    "ESTADOS_SWAP",
    "ESTADOS_TAREA",
    "METRICAS_COMERCIAL",
    "PRIORIDADES_EVENTO",
    "TIPOS_COBERTURA",
    "TIPOS_AUSENCIA",
    "actualizar_franja_semana",
    "actualizar_fuente_rss",
    "actualizar_grupo_hashtags",
    "actualizar_evento_rota",
    "actualizar_pieza_rota",
    "actualizar_programa_rota",
    "actualizar_publicacion_comercial",
    "actualizar_ausencia_rota",
    "actualizar_turno_rota",
    "actualizar_turnos_rota_lote",
    "aprobar_semana_rota",
    "arrancar_persistencia",
    "borrar_ausencia_rota",
    "borrar_evento_rota",
    "borrar_franja",
    "borrar_franja_semana",
    "borrar_fuente_rss",
    "borrar_grupo_hashtags",
    "borrar_pieza_rota",
    "borrar_piezas_rota_lote",
    "borrar_programa_rota",
    "borrar_publicacion_comercial",
    "borrar_swap_turno",
    "borrar_turno_rota",
    "borrar_turnos_rota_lote",
    "borrar_turnos_semana_rota",
    "cancelar_job",
    "claves_vistas",
    "conectar",
    "actualizar_fuente_algoritmo",
    "borrar_fuente_algoritmo",
    "contar_fuentes_algoritmo",
    "crear_fuente_algoritmo",
    "guardar_noticia_algoritmo",
    "listar_fuentes_algoritmo",
    "listar_noticias_algoritmo",
    "marcar_noticia_algoritmo",
    "obtener_fuente_algoritmo",
    "obtener_noticia_algoritmo",
    "registrar_salud_fuente_algoritmo",
    "actualizar_estado_sugerencia_editorial",
    "contar_sugerencias_editoriales",
    "crear_sugerencia_editorial",
    "listar_sugerencias_editoriales",
    "obtener_sugerencia_editorial",
    "contar_fuentes_rss",
    "contar_grupos_hashtags",
    "contar_piezas_por_programa",
    "copiar_turnos_rota",
    "crear_ausencia_rota",
    "crear_evento_rota",
    "crear_franja",
    "crear_franja_semana",
    "crear_fuente_rss",
    "crear_grupo_hashtags",
    "crear_pieza_rota",
    "crear_programa_rota",
    "crear_publicacion_comercial",
    "crear_swap_turno",
    "crear_turno_rota",
    "crear_turnos_rota_lote",
    "duplicar_evento_rota",
    "duplicar_pieza_rota",
    "duplicar_turno_rota",
    "encolar_job",
    "existe_programa_por_nombre",
    "existe_turno_para",
    "job_cancelado",
    "listar_ausencias_rota",
    "listar_eventos_rota",
    "listar_franjas",
    "listar_franjas_semana",
    "listar_fuentes_rss",
    "listar_grupos_hashtags",
    "listar_piezas_rota",
    "listar_programas_rota",
    "listar_publicaciones_comerciales",
    "listar_snapshots_comerciales",
    "listar_snapshots_piezas",
    "listar_swaps_turno",
    "listar_turnos_rota",
    "marcar_aviso_comercial",
    "marcar_item",
    "obtener_ausencia_rota",
    "obtener_evento_rota",
    "obtener_franja_semana",
    "obtener_fuente_rss",
    "obtener_grupo_hashtags",
    "obtener_pieza_rota",
    "obtener_programa_rota",
    "obtener_publicacion_comercial",
    "obtener_swap_turno",
    "obtener_turno_rota",
    "podar_snapshots_piezas",
    "reclamar_job",
    "reclamar_preparacion",
    "registrar_salud_fuente_rss",
    "registrar_snapshot_comercial",
    "registrar_snapshot_pieza",
    "sembrar_franjas_por_defecto",
    "serie_pieza",
    "terminar_job",
    "ultimo_snapshot_comercial",
    "actualizar_swap_turno",
    "aplicar_swap_turno",
    "listar_coordinacion_semana",
    "set_coordinador_rota",
    "quitar_coordinador_rota",
    # Agentes de investigacion (Ola 6).
    "crear_inv_brief",
    "listar_inv_briefs",
    "obtener_inv_brief",
    "actualizar_inv_brief",
    "borrar_inv_brief",
    "crear_inv_candidatos",
    "listar_inv_candidatos",
    "obtener_inv_candidato",
    "actualizar_inv_candidato",
    # Motor de ingesta persistente (Ola A).
    "crear_noticias_items",
    "listar_noticias_items",
    "obtener_noticia_item",
    "actualizar_noticia_item",
    "feeds_vencidos",
    "registrar_sondeo_feed",
    "resumen_cobertura",
    "ESTADOS_NOTICIA_ITEM",
    # Monitor de cobertura (Ola D).
    "salud_feeds",
    "conteos_items_recientes",
    # Clustering de historias (Ola B).
    "upsert_noticia_cluster",
    "listar_noticia_clusters",
    "obtener_noticia_cluster",
    "actualizar_noticia_cluster",
    "clusters_recientes",
    "items_de_cluster",
    "items_sin_cluster",
    "asignar_cluster_item",
    "marcar_items_cluster_usados",
    "ESTADOS_NOTICIA_CLUSTER",
    # Traducción + verificación de historias (Ola D).
    "clusters_extranjeros_sin_traducir",
    "marcar_cluster_traducido",
    "VERIFICACIONES_CLUSTER",
]


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
            except Exception:  # noqa: BLE001 -- soltar es best-effort; cerrar la conexion tambien libera.
                _log.warning("No se pudo soltar el advisory lock de barrido %s.", nombre)
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
        UNIQUE (lunes, nombre)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_franjas_lunes ON rota_franjas (lunes)",
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
        origen_ref     TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_semana ON rota_turnos (semana)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_miembro ON rota_turnos (miembro_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_fecha ON rota_turnos (fecha)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_franja_id ON rota_turnos (franja_id)",
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
        qa_veredicto        TEXT NOT NULL DEFAULT '',
        qa_hallazgos        TEXT NOT NULL DEFAULT '',
        copy_pendiente      TEXT NOT NULL DEFAULT '',
        fecha_fuente        TEXT NOT NULL DEFAULT '',
        url_fuente          TEXT NOT NULL DEFAULT '',
        creado              TEXT NOT NULL DEFAULT '',
        actualizado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_contenido_flujo ON contenido (flujo)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_marca ON contenido (marca)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_evento ON contenido (evento_id)",
    "CREATE INDEX IF NOT EXISTS idx_contenido_responsable ON contenido (responsable_id)",
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
    # QA EDITORIAL como APROBADOR AUTOMATICO (item D): veredicto de la skill `qa-editorial`
    # ATADO a una pieza (`contenido_plataforma`). Cada vez que se corre el QA sobre una pieza
    # concreta se guarda aqui un registro inmutable con el `verdicto` (listo/revisar/no_publicar),
    # un `resumen` legible y el `copy_hash` (hash del copy revisado en ese momento). El consumidor
    # (`repos.ultimo_veredicto_qa`) lee el ULTIMO veredicto de la pieza para resolver el nivel
    # automatico "QA Editorial" de la cadena de aprobacion; compara `copy_hash` con el copy actual
    # para INVALIDAR el veredicto si el copy cambio despues del QA (entonces el nivel queda
    # pendiente, lo decide un humano). Append-only: nunca se pisa, solo se inserta y se lee el ultimo.
    """
    CREATE TABLE IF NOT EXISTS contenido_qa_veredictos (
        id            TEXT PRIMARY KEY,
        plataforma_id TEXT NOT NULL DEFAULT '',
        contenido_id  TEXT NOT NULL DEFAULT '',
        verdicto      TEXT NOT NULL DEFAULT '',
        resumen       TEXT NOT NULL DEFAULT '',
        copy_hash     TEXT NOT NULL DEFAULT '',
        historial_id  TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_qaver_plataforma ON contenido_qa_veredictos (plataforma_id)",
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
    # editoriales del equipo y se editan desde la UI. Singleton: una sola fila con
    # `id='default'`. Si no existe, los endpoints devuelven los defaults del dominio.
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
        aplicado                 TEXT NOT NULL DEFAULT ''
    )
    """,
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
        UNIQUE (fecha, franja_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_coord_lunes ON rota_coordinacion (lunes)",
    "CREATE INDEX IF NOT EXISTS idx_rota_coord_franja ON rota_coordinacion (franja_id)",
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
        error         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_parrilla_propuesta_estado ON parrilla_propuesta (estado)",
    "CREATE INDEX IF NOT EXISTS idx_parrilla_propuesta_semana ON parrilla_propuesta (semana)",
    "CREATE INDEX IF NOT EXISTS idx_parrilla_propuesta_gen ON parrilla_propuesta (gen_id)",
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
    # ACTIVOS REUTILIZABLES (ola "activos"): biblioteca de medios interna.     #
    # (Las "plantillas de contenido" se retiraron por completo.)               #
    # ----------------------------------------------------------------------- #
    # Limpieza one-shot: elimina la tabla retirada `plantilla_contenido` (y sus datos) si una
    # BD vieja aun la tiene. Idempotente (IF EXISTS); no afecta a plantillas de MARCA/diseno.
    "DROP TABLE IF EXISTS plantilla_contenido CASCADE",
    # BIBLIOTECA DE MEDIOS interna (ola "activos"): catalogo editorial de imagenes/clips
    # APROBADOS y reutilizables al armar una pieza. NO publica a redes (eso es Metricool); es
    # un repositorio interno. Cada fila CATALOGA un objeto del almacen de media (`media.py` /
    # `almacen_media.py`) por su nombre (`objeto`, un uuid+ext que SIEMPRE genera el servidor)
    # mas metadatos editoriales: titulo, tipo (`imagen`|`clip`), marca, etiquetas (JSON de
    # strings para buscar/filtrar), credito/fuente y estado de aprobacion. `objeto` UNIQUE: un
    # mismo binario se cataloga una sola vez. Borrar una entrada NO borra el binario por
    # defecto (puede estar referenciado por una pieza ya armada); la API decide.
    """
    CREATE TABLE IF NOT EXISTS biblioteca_media (
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
    "CREATE INDEX IF NOT EXISTS idx_biblioteca_media_marca ON biblioteca_media (marca)",
    "CREATE INDEX IF NOT EXISTS idx_biblioteca_media_tipo ON biblioteca_media (tipo)",
    "CREATE INDEX IF NOT EXISTS idx_biblioteca_media_aprobado ON biblioteca_media (aprobado)",
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
    # documento.py`). Se etiquetan por `categoria` (post | historia | reel | infografia | …) y por
    # `lineas` (JSON de ids de `etiquetas` clase=vertical) para filtrar por línea editorial.
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
        categoria    TEXT NOT NULL DEFAULT 'post',
        tipo         TEXT NOT NULL DEFAULT 'foto',
        documento    TEXT NOT NULL DEFAULT '{}',
        miniatura    TEXT NOT NULL DEFAULT '',
        lineas       TEXT NOT NULL DEFAULT '[]',
        activo       INTEGER NOT NULL DEFAULT 1,
        autor_id     TEXT NOT NULL DEFAULT '',
        autor_nombre TEXT NOT NULL DEFAULT '',
        creado       TEXT NOT NULL DEFAULT '',
        actualizado  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_plantillas_diseno_marca ON plantillas_diseno (marca)",
    "CREATE INDEX IF NOT EXISTS idx_plantillas_diseno_categoria ON plantillas_diseno (categoria)",
    "CREATE INDEX IF NOT EXISTS idx_plantillas_diseno_tipo ON plantillas_diseno (tipo)",
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
        activo       INTEGER NOT NULL DEFAULT 1,
        ttl_dias     INTEGER NOT NULL DEFAULT 0,
        es_green     INTEGER NOT NULL DEFAULT 0,
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
    # TALLER GREEN / BRAINSTORMING: ideas de contenido EVERGREEN propuestas (por IA o a mano)
    # que el equipo aprueba o descarta ANTES de generar nada. La IA NO redacta a ciegas: primero
    # PROPONE ideas (`origen='ia'`, `estado='propuesta'`); una persona las marca `aprobada` o
    # `descartada`; solo para las APROBADAS se genera la pieza (`flujo='evergreen'` en el tablero)
    # y se enlaza en `contenido_id`. `generacion_id` apunta a la generacion IA que las propuso
    # (para trazar el lote). `creado` preserva el orden "recientes primero".
    """
    CREATE TABLE IF NOT EXISTS green_ideas (
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
    "CREATE INDEX IF NOT EXISTS idx_green_ideas_marca ON green_ideas (marca)",
    "CREATE INDEX IF NOT EXISTS idx_green_ideas_estado ON green_ideas (estado)",
    "CREATE INDEX IF NOT EXISTS idx_green_ideas_creado ON green_ideas (creado)",
    # Grupos de hashtags reutilizables (nombre + lista de tags JSON) por marca. `hashtags`
    # es un JSON serializado de strings (igual patron que `biblioteca_media.etiquetas`).
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
    # importancia, mostrarlas en el panel y enlazarlas a la biblioteca. `importancia` es un
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
        creado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_noticias_items_dedup ON noticias_items (fuente_id, clave)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_capturado ON noticias_items (capturado_en)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_marca_capturado ON noticias_items (marca, capturado_en)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_categoria ON noticias_items (categoria)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_estado ON noticias_items (estado)",
    "CREATE INDEX IF NOT EXISTS idx_noticias_items_cluster ON noticias_items (cluster_id)",
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
    # `ficha_id` el doc de biblioteca destino (p. ej. `editorial/plataformas/instagram`).
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
    # AGENTES DE INVESTIGACION (Ola 6): briefs reutilizables + candidatos fechados.
    # Un brief es un encargo de investigacion (marca/linea/instrucciones); una corrida
    # produce candidatos fechados (titulo/resumen/por_que/fuente/enlace/idioma). El humano
    # los filtra: aceptar -> tablero (contenido_id relleno) o descartar. NUNCA auto-publican.
    """
    CREATE TABLE IF NOT EXISTS inv_brief (
        id            TEXT PRIMARY KEY,
        nombre        TEXT NOT NULL DEFAULT '',
        marca         TEXT NOT NULL DEFAULT '',
        linea         TEXT NOT NULL DEFAULT '',
        instrucciones TEXT NOT NULL DEFAULT '',
        idiomas       TEXT NOT NULL DEFAULT '',
        activo        INTEGER NOT NULL DEFAULT 1,
        creado        TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_inv_brief_marca ON inv_brief (marca)",
    "CREATE INDEX IF NOT EXISTS idx_inv_brief_activo ON inv_brief (activo)",
    """
    CREATE TABLE IF NOT EXISTS inv_candidato (
        id           TEXT PRIMARY KEY,
        brief_id     TEXT NOT NULL DEFAULT '',
        fecha        TEXT NOT NULL DEFAULT '',
        marca        TEXT NOT NULL DEFAULT '',
        linea        TEXT NOT NULL DEFAULT '',
        titulo       TEXT NOT NULL DEFAULT '',
        resumen      TEXT NOT NULL DEFAULT '',
        por_que      TEXT NOT NULL DEFAULT '',
        fuente       TEXT NOT NULL DEFAULT '',
        enlace       TEXT NOT NULL DEFAULT '',
        idioma       TEXT NOT NULL DEFAULT 'es',
        estado       TEXT NOT NULL DEFAULT 'nuevo',
        contenido_id TEXT NOT NULL DEFAULT '',
        creado       TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_inv_candidato_fecha_marca ON inv_candidato (fecha, marca)",
    "CREATE INDEX IF NOT EXISTS idx_inv_candidato_brief ON inv_candidato (brief_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_candidato_estado ON inv_candidato (estado)",
)


def _crear_esquema(con: Any) -> None:
    """Crea las tablas operacionales si no existen (idempotente).

    Ejecuta el DDL sentencia a sentencia y luego aplica las migraciones de columnas
    ampliadas (`tareas`, `rota_eventos`) y la migracion del modelo de turnos (ola back3:
    `rota_turnos` → `rota_turnos` con la nueva semantica).

    Las migraciones son NECESARIAS, no opcionales: `CREATE TABLE IF NOT EXISTS`
    NO anade columnas a una tabla que YA existe, y el Postgres hosted PERSISTE entre
    despliegues. Una tabla creada por una version anterior se quedaba sin las columnas
    nuevas (fallo real: `rota_eventos` sin `tipo_cobertura` → 500 al leer el calendario).
    """
    # IMPORTANTE: la migracion del MODELO de turnos debe correr ANTES del DDL declarativo,
    # porque el DDL hoy declara `rota_turnos` con la NUEVA forma (con `fecha`/`franja`). Si
    # la BD vieja tiene una `rota_turnos` con el VIEJO esquema (cobertura), `CREATE TABLE IF
    # NOT EXISTS` la deja como esta -> el resto del codigo fallaria al usar columnas que no
    # existen. La migracion la convierte (renombre + drop + renombre final) y deja la BD lista
    # para que el DDL declarativo NO haga nada (la tabla ya existe con la forma correcta).
    _migrar_modelo_turnos(con)
    # Ola "franjas por semana": tiene que correr ANTES del DDL declarativo. Razon: el DDL
    # declara `CREATE INDEX ... idx_rota_turnos_franja_id ON rota_turnos (franja_id)`, y en
    # bases productivas la `rota_turnos` previa solo tiene columna `franja` (literal del
    # modelo Ω3). Crear el indice sobre una columna inexistente revienta. La migracion
    # asegura `rota_franjas` con `es_descanso`, añade `franja_id` a `rota_turnos`, mueve
    # los datos y dropa `franja`. Tras esto, el DDL declarativo es idempotente.
    _migrar_modelo_franjas(con)
    # Migraciones cuya columna usa un ÍNDICE del DDL declarativo: corren ANTES del DDL. El DDL
    # crea `idx_rota_eventos_marca`(marca) e `idx_fuentes_rss_sondeo`(proximo_sondeo); en una BD
    # VIEJA esas columnas aún no existen, así que crear el índice revienta y ENVENENA la conexión
    # (mismo motivo que turnos/franjas arriba: el calendario daba 500). Tras añadir la columna, el
    # DDL es idempotente. Guard interno: si la tabla aún no existe, no hacen nada y el DDL la crea
    # fresca con todo.
    _migrar_columnas_eventos_rota(con)
    _migrar_columnas_fuentes_rss(con)
    # Mismo motivo (columna usada por un ÍNDICE del DDL declarativo, corre ANTES): el DDL crea
    # `idx_plantillas_diseno_tipo`(tipo) y en una BD vieja `plantillas_diseno` aún no tiene `tipo`,
    # así que el índice revienta ("column tipo does not exist") y envenena la conexión (fallo real
    # en deploy). La migración añade `tipo` primero; tras ella el DDL es idempotente. Guard interno:
    # si la tabla aún no existe, no hace nada y el DDL la crea fresca con `tipo`.
    _migrar_columnas_plantillas_diseno(con)
    for sentencia in _DDL_ESQUEMA:
        con.execute(sentencia)
    _migrar_columnas_turnos_rota(con)
    _migrar_columnas_piezas_rota(con)
    _migrar_columnas_contenido(con)
    _migrar_columnas_aprobaciones(con)
    _migrar_columnas_comercial(con)
    _migrar_columnas_swaps(con)
    _migrar_columnas_programas(con)
    _migrar_columnas_usuarios(con)
    _migrar_columnas_grupos_hashtags(con)
    _migrar_columnas_noticias_clusters(con)
    _migrar_columnas_noticias_algoritmo(con)
    _migrar_columnas_etiquetas(con)
    _migrar_columnas_contenido_plataforma(con)
    con.commit()
    # Indices UNICOS de idempotencia: AL FINAL y aislados (commit propio por indice), porque
    # pueden fallar sobre BDs con duplicados previos sin tumbar el arranque (ver helper).
    _crear_indices_unicos_idempotencia(con)


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


def _migrar_columnas_plantillas_diseno(con: Any) -> None:
    """Anade `tipo` a `plantillas_diseno` si una BD ya creada no la tuviera (idempotente).

    `tipo` ("foto" | "miniatura") es un eje ortogonal a `categoria`: foto = plantilla para
    fotos/imagenes del feed; miniatura = portada/thumbnail de video. Las plantillas
    existentes reciben el DEFAULT "foto", que preserva el comportamiento previo al campo.
    """
    if not _tabla_existe(con, "plantillas_diseno"):
        return
    if "tipo" not in _columnas_existentes(con, "plantillas_diseno"):
        con.execute(
            "ALTER TABLE plantillas_diseno ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'foto'"
        )


def _migrar_columnas_etiquetas(con: Any) -> None:
    """Anade columnas nuevas a `etiquetas` si una BD ya creada no las tuviera (idempotente).

    - `keywords` (CSV) alimenta el auto-etiquetado de líneas (clase `vertical`) y de
      orígenes (clase `origen`) en la ingesta.
    - `ttl_dias` (INTEGER, def 0): días que un ítem de esta línea se considera fresco.
      0 = sin caducidad / evergreen.
    - `es_green` (INTEGER, def 0): 1 = línea evergreen reutilizable en fines de semana.

    Solo aplica si la tabla ya existe (un primer arranque la crea con las columnas).
    """
    if not _tabla_existe(con, "etiquetas"):
        return
    cols = _columnas_existentes(con, "etiquetas")
    if "keywords" not in cols:
        con.execute(
            "ALTER TABLE etiquetas ADD COLUMN IF NOT EXISTS keywords TEXT NOT NULL DEFAULT ''"
        )
    if "ttl_dias" not in cols:
        con.execute(
            "ALTER TABLE etiquetas ADD COLUMN IF NOT EXISTS ttl_dias INTEGER NOT NULL DEFAULT 0"
        )
    if "es_green" not in cols:
        con.execute(
            "ALTER TABLE etiquetas ADD COLUMN IF NOT EXISTS es_green INTEGER NOT NULL DEFAULT 0"
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
        ahora = datetime.now().isoformat(timespec="seconds")
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


def _config_franjas_template(con: Any) -> tuple[str, str, str, str]:
    """Devuelve `(matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin)` para
    sembrar las 2 franjas por defecto de una semana nueva.

    Si `rota_config_franjas` tiene una fila con `id='default'`, usamos sus rangos
    (configuracion editorial #185). Si no, defaults del dominio (08-16 / 16-24).
    """
    mat_ini, mat_fin = "08:00", "16:00"
    ves_ini, ves_fin = "16:00", "24:00"
    if not _tabla_existe(con, "rota_config_franjas"):
        return mat_ini, mat_fin, ves_ini, ves_fin
    fila = con.execute(
        "SELECT matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin "
        "FROM rota_config_franjas WHERE id = ?",
        ("default",),
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


def _sembrar_franjas_por_defecto_en(con: Any, lunes: str) -> dict[str, str]:
    """Inserta (Mañana, Tarde, Descanso) en `rota_franjas` para `lunes` si no existen.

    Devuelve el mapa `{nombre -> id}` con las franjas vigentes (sembradas o ya existentes).
    La franja "Descanso" se siembra con `es_descanso=true`, `inicio='00:00'`/`fin='00:00'`
    (sin rango horario real: nadie cubre eventos en descanso) y un `orden` alto (999) para
    que la UI la pinte siempre al final.
    """
    if not lunes:
        return {}
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
    mat_ini, mat_fin, ves_ini, ves_fin = _config_franjas_template(con)
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
        con.execute(
            "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (lunes, nombre) DO NOTHING",
            (nuevo_id, lunes, nombre, inicio, fin, orden, es_descanso),
        )
        por_nombre[nombre] = nuevo_id
    # Releemos para coger los `id` reales (el ON CONFLICT pudo descartar el INSERT si otra
    # transaccion sembro a la vez): el dict en memoria puede traer un id que no esta.
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
)
_COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("es_publicacion", "INTEGER NOT NULL DEFAULT 0"),
    # URL de la imagen de la FUENTE original (cuando tipo_contenido='fuente'): se
    # previsualiza tal cual sin tener que descargarla a la biblioteca de media.
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


# --------------------------------------------------------------------------- #
# Publicaciones comerciales (seguimiento de UNA pieza por su link)             #
# --------------------------------------------------------------------------- #
#
# A diferencia de las `publicaciones` editoriales (que viven en YAML), esto monitoriza
# el rendimiento de una pieza ya publicada: se registra su link, se le toman snapshots
# periodicos de interacciones/alcance (serie temporal) y, al llegar el KPI, se arma su
# reporte. Es dato OPERACIONAL append-only: no encaja como un fichero por entidad, por
# eso vive en SQLite.

# Columnas de `comercial_publicaciones` en orden de declaracion (reusadas en SELECT/INSERT).
_COLS_COMERCIAL = (
    "id",
    "url",
    "id_post_metricool",
    "titulo",
    "marca",
    "cliente",
    "campania",
    "red",
    "formato",
    "metrica_objetivo",
    "objetivo",
    "estado",
    "publicado",
    "notas",
    "aviso_en",
    "fecha_creacion",
    "fecha_actualizacion",
)
_SELECT_COMERCIAL = f"SELECT {', '.join(_COLS_COMERCIAL)} FROM comercial_publicaciones"

# Campos que la edicion parcial puede tocar (url y fechas/aviso son inmutables desde la API).
_CAMPOS_EDITABLES_COMERCIAL = (
    "titulo",
    "marca",
    "cliente",
    "campania",
    "red",
    "formato",
    "metrica_objetivo",
    "objetivo",
    "estado",
    "publicado",
    "notas",
)


def _fila_a_comercial(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `comercial_publicaciones` en un dict (`objetivo` como int)."""
    pub = {col: fila[col] for col in _COLS_COMERCIAL}
    pub["objetivo"] = int(fila["objetivo"] or 0)
    return pub


def crear_publicacion_comercial(
    url: str = "",
    *,
    id_post_metricool: str = "",
    titulo: str = "",
    marca: str = "",
    cliente: str = "",
    campania: str = "",
    red: str = "",
    formato: str = "",
    metrica_objetivo: str = "interacciones",
    objetivo: int = 0,
    estado: str = "activa",
    publicado: str = "",
    notas: str = "",
) -> dict[str, Any]:
    """Inserta una publicacion comercial a monitorear y la devuelve.

    La pieza se identifica por su `id_post_metricool` (el post real de Metricool); `url`
    es derivada/opcional (la trae el propio post). NO valida marca/red/estado/metrica (lo
    hace la API contra sus allowlists). `aviso_en` nace vacio; se rellena la primera vez
    que el valor supera el objetivo.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "url": url,
        "id_post_metricool": id_post_metricool,
        "titulo": titulo,
        "marca": marca,
        "cliente": cliente,
        "campania": campania,
        "red": red,
        "formato": formato or "",
        "metrica_objetivo": metrica_objetivo or "interacciones",
        "objetivo": int(objetivo or 0),
        "estado": estado or "activa",
        "publicado": publicado or date.today().isoformat(),
        "notas": notas,
        "aviso_en": "",
        "fecha_creacion": ahora,
        "fecha_actualizacion": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_COMERCIAL)
        con.execute(
            f"INSERT INTO comercial_publicaciones ({', '.join(_COLS_COMERCIAL)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_COMERCIAL),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_publicaciones_comerciales(
    estado: str | None = None,
    cliente: str | None = None,
    campania: str | None = None,
) -> list[dict[str, Any]]:
    """Publicaciones comerciales (mas recientes primero), con filtros opcionales."""
    clausulas: list[str] = []
    params: list[Any] = []
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if cliente:
        clausulas.append("cliente = ?")
        params.append(cliente)
    if campania:
        clausulas.append("campania = ?")
        params.append(campania)
    sql = _SELECT_COMERCIAL
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    # Desempate por `id` (uuid, PK presente en ambos backends) en vez del `rowid` de
    # SQLite (que Postgres no tiene). Solo influye cuando dos piezas comparten
    # `fecha_creacion` (mismo segundo): un orden estable y portable, no autoritativo.
    sql += " ORDER BY fecha_creacion DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_comercial(f) for f in filas]


def obtener_publicacion_comercial(publicacion_id: str) -> dict[str, Any] | None:
    """Una publicacion comercial por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_COMERCIAL} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comercial(fila) if fila is not None else None


def actualizar_publicacion_comercial(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una publicacion comercial; None si el id no existe.

    Solo toca los campos de `_CAMPOS_EDITABLES_COMERCIAL`; ignora el resto. Pone
    `fecha_actualizacion` a ahora. NO valida (lo hace la API).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_COMERCIAL}
    if "objetivo" in cambios:
        cambios["objetivo"] = int(cambios["objetivo"] or 0)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("fecha_actualizacion = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(publicacion_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE comercial_publicaciones SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_COMERCIAL} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comercial(fila) if fila is not None else None


def marcar_aviso_comercial(publicacion_id: str, ts: str) -> None:
    """Marca el instante en que la pieza alcanzo su objetivo (solo la PRIMERA vez).

    El `WHERE aviso_en = ''` lo hace idempotente: una vez avisada, no se re-marca.
    """
    con = _conectar()
    try:
        con.execute(
            "UPDATE comercial_publicaciones SET aviso_en = ? WHERE id = ? AND aviso_en = ''",
            (ts, publicacion_id),
        )
        con.commit()
    finally:
        con.close()


def borrar_publicacion_comercial(publicacion_id: str) -> bool:
    """Borra una publicacion comercial y sus snapshots; True si existia, False si no."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM comercial_snapshots WHERE publicacion_id = ?", (publicacion_id,)
        )
        cur = con.execute(
            "DELETE FROM comercial_publicaciones WHERE id = ?", (publicacion_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Snapshots (serie temporal de interacciones/alcance por publicacion) ------

# Metricas GRANULARES por pieza que el snapshot captura ademas de las "base"
# (interacciones/visualizaciones/alcance). Son el desglose que la fuente (Metricool, via
# `servicio.construir_metricas_pieza`) expone por pieza. Una sola tupla mantiene DRY el
# INSERT y los SELECT: anadir una metrica nueva = anadir aqui + a `_DDL_ESQUEMA` +
# `_COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS`. Todas son enteros con DEFAULT 0 (dato ausente
# -> 0; la UI distingue "sin dato" por interacciones/encontrado, no por estos ceros).
_METRICAS_GRANULARES_SNAPSHOT: tuple[str, ...] = (
    "likes",
    "comentarios",
    "compartidos",
    "guardados",
    "video_views",
    "tiempo_medio_vis_s",
    "clics_enlace",
    "seguidores_netos_atribuidos",
)
# Orden de columnas del SELECT de la serie (base + granulares).
_COLS_SNAPSHOT_LECTURA: tuple[str, ...] = (
    "ts",
    "interacciones",
    "visualizaciones",
    "alcance",
    *_METRICAS_GRANULARES_SNAPSHOT,
)
_SELECT_SNAPSHOT = ", ".join(_COLS_SNAPSHOT_LECTURA)


def _fila_a_snapshot(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `comercial_snapshots` en un dict (ts texto, resto enteros)."""
    snap: dict[str, Any] = {"ts": fila["ts"]}
    for col in _COLS_SNAPSHOT_LECTURA[1:]:
        snap[col] = int(fila[col] or 0)
    return snap


def registrar_snapshot_comercial(
    publicacion_id: str,
    ts: str,
    interacciones: int,
    alcance: int,
    visualizaciones: int = 0,
    *,
    granulares: dict[str, Any] | None = None,
) -> bool:
    """Inserta un snapshot (idempotente por `(publicacion_id, ts)`).

    Devuelve True si inserto una fila nueva, False si ya habia un snapshot en ese `ts`
    (el indice UNICO lo evita; asi re-capturar en el mismo minuto no duplica puntos).

    `granulares` (opcional) trae el desglose por pieza (likes/comentarios/compartidos/
    guardados/video_views/tiempo_medio_vis_s/clics_enlace/seguidores_netos_atribuidos);
    cada campo ausente o `None` se persiste como 0 (defensivo). El llamante normal es
    `comercial._capturar_en`, que lo arma desde el dict de `metricas_pieza.recalcular`.
    """
    granulares = granulares or {}
    cols = ("id", "publicacion_id", "ts", "interacciones", "visualizaciones", "alcance",
            *_METRICAS_GRANULARES_SNAPSHOT)
    valores = [
        uuid.uuid4().hex[:12],
        publicacion_id,
        ts,
        int(interacciones),
        int(visualizaciones),
        int(alcance),
        *(int(granulares.get(campo) or 0) for campo in _METRICAS_GRANULARES_SNAPSHOT),
    ]
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in cols)
        cur = con.execute(
            f"INSERT OR IGNORE INTO comercial_snapshots ({', '.join(cols)}) "
            f"VALUES ({marcadores})",
            tuple(valores),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Tope de puntos de las series temporales (Item: límite/downsampling) ----- #
# Las series de métricas (`listar_snapshots_comerciales`, `serie_pieza`,
# `listar_snapshots_piezas`) alimentan gráficas; con meses de snapshots cada 4 h crecerían sin
# cota. Tope por DEFECTO de puntos devueltos, configurable por `KENI_METRICAS_SERIE_MAX` (entero;
# mín 2 para que siempre quepa una recta). DECISIÓN: cuando la serie excede el tope, se devuelven
# los ÚLTIMOS N puntos (los más recientes), NO un muestreo: así el ÚLTIMO punto —el dato actual,
# el que la UI rotula y del que cuelga la "velocidad"— SIEMPRE entra, y la curva queda visualmente
# correcta en su tramo reciente (el más relevante para decisiones). Se implementa como
# `ORDER BY ts DESC LIMIT N` y luego se reinvierte a ASC (orden de graficado). `limite=None`
# (cap por defecto) vs `limite<=0` (SIN tope, serie COMPLETA: ruta para análisis/exportación que
# necesite todo el histórico, p. ej. la poda o un reporte agregado).
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


def listar_snapshots_comerciales(
    publicacion_id: str, *, limite: int | None = None
) -> list[dict[str, Any]]:
    """Serie temporal de una publicacion (mas antiguo primero), lista para graficar.

    Acotada por DEFECTO a los últimos `KENI_METRICAS_SERIE_MAX` puntos (el dato más reciente
    SIEMPRE entra; ver `_tope_serie_metricas`). `limite<=0` devuelve la serie COMPLETA (para
    callers que recorren todo el histórico, p. ej. el cruce de objetivo comercial).
    """
    tope = _tope_serie_metricas(limite)
    con = _conectar()
    try:
        if tope is None:
            filas = con.execute(
                f"SELECT {_SELECT_SNAPSHOT} FROM comercial_snapshots "
                "WHERE publicacion_id = ? ORDER BY ts ASC",
                (publicacion_id,),
            ).fetchall()
        else:
            # Trae los N más recientes (DESC + LIMIT, barato con el índice por ts) y reinvierte a
            # ASC: el orden de graficado, con el último punto garantizado dentro del recorte.
            filas = con.execute(
                f"SELECT {_SELECT_SNAPSHOT} FROM comercial_snapshots "
                "WHERE publicacion_id = ? ORDER BY ts DESC LIMIT ?",
                (publicacion_id, tope),
            ).fetchall()
            filas = list(reversed(filas))
    finally:
        con.close()
    return [_fila_a_snapshot(f) for f in filas]


def ultimo_snapshot_comercial(publicacion_id: str) -> dict[str, Any] | None:
    """El snapshot mas reciente de una publicacion (None si aun no tiene)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT {_SELECT_SNAPSHOT} FROM comercial_snapshots "
            "WHERE publicacion_id = ? ORDER BY ts DESC LIMIT 1",
            (publicacion_id,),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return None
    return _fila_a_snapshot(fila)


# --------------------------------------------------------------------------- #
# Histórico de metricas POR PIEZA (serie temporal general, todas las piezas)   #
# --------------------------------------------------------------------------- #
#
# `metricas_pieza_snapshots`: una fila por pieza por refresco del daemon
# (`metricas_piezas_refresco`, cada 4h) para TODAS las publicaciones recientes (no solo las
# del modulo comercial). Habilita analisis temporales por marca×red×formato. Relacion con
# las otras dos series: `metricas_cache` guarda el valor ACTUAL (sobrescrito); esta guarda
# la SERIE; `comercial_snapshots` sigue para el seguimiento de OBJETIVOS comerciales. Ver
# ADR 0007. El crecimiento lo acota la poda por retencion (`podar_snapshots_piezas`).

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
        uuid.uuid4().hex[:12],
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


def podar_snapshots_piezas(retencion_dias: int, ahora_iso: str) -> int:
    """Borra los snapshots por pieza con `ts` < (`ahora_iso` - `retencion_dias`). Devuelve nº borrados.

    El corte se calcula a partir del `ahora_iso` que pasa el LLAMANTE (el daemon ya tiene un
    reloj): db.py NO genera la hora del sistema, para que la poda sea testeable de forma
    determinista. `ahora_iso` se parsea como ISO; si no parsea, no se poda nada (defensivo).
    """
    if retencion_dias <= 0:
        return 0
    try:
        corte = datetime.fromisoformat(ahora_iso) - timedelta(days=retencion_dias)
    except (TypeError, ValueError):
        return 0
    corte_iso = corte.isoformat()
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
        payload = json.loads(fila["payload"])
    except (ValueError, TypeError):
        return None
    return {
        "payload": payload,
        "fuente": fila["fuente"] or "muestra",
        "generado_en": fila["generado_en"],
    }


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
                json.dumps(payload, ensure_ascii=False),
                fuente,
                generado_en,
            ),
        )
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Rota: eventos/transmisiones + turnos (horarios persona×dia×franja)            #
# --------------------------------------------------------------------------- #
#
# Sustituye el Excel manual de Elias. Dos entidades operacionales INDEPENDIENTES (ver
# comentario "cambio de modelo" en la DDL): el EVENTO (calendario de transmisiones) y el
# TURNO (horario del miembro en (fecha, franja)). Un turno NO va atado a un evento. La
# "cobertura" (quien cubre un evento) es una vista DERIVADA: para un evento, sus coberturas
# son los miembros cuyo turno coincide con la franja+fecha del evento (`mapear_franja` en
# `rota.py`). Pueden existir turnos sin eventos y eventos sin turnos.
#
# Antes el codigo tenia dos tablas: `rota_turnos` (cobertura, mal modelada) y
# `rota_turnos` (horario). El feedback del usuario aclaro que la cobertura no es un
# concepto persistido: un turno cubre todos los eventos que caen en su franja+fecha. La
# migracion (`_migrar_modelo_turnos`) convierte la cobertura legada en turnos del nuevo modelo
# y unifica todo en una unica tabla `rota_turnos`.

# Columnas de `rota_eventos`. La ola B (#144) anade tipo_cobertura/prioridad/cambiado/
# actualizado: `cambiado`/`actualizado` son GESTIONADAS POR EL SISTEMA (no editables a
# pelo: `cambiado` lo derivamos al reprogramar y `actualizado` se refresca en cada edicion),
# por eso quedan fuera de `_CAMPOS_EDITABLES_EVENTO_ROTA`.
_COLS_EVENTO_ROTA = (
    "id",
    "titulo",
    "fecha",
    "hora",
    "contenido",
    "nota",
    "tipo_cobertura",
    "prioridad",
    "cambiado",
    "actualizado",
    "creado",
    "marca",
)
_SELECT_EVENTO_ROTA = f"SELECT {', '.join(_COLS_EVENTO_ROTA)} FROM rota_eventos"
_CAMPOS_EDITABLES_EVENTO_ROTA = (
    "titulo",
    "fecha",
    "hora",
    "contenido",
    "nota",
    "tipo_cobertura",
    "prioridad",
    "marca",
)


def _fila_a_evento_rota(fila: Any) -> dict[str, Any]:
    evento = {col: fila[col] for col in _COLS_EVENTO_ROTA}
    # `cambiado` se persiste como 0/1; lo exponemos como bool para la capa API/UI.
    evento["cambiado"] = bool(fila["cambiado"])
    # Defensa retrocompatible: una fila migrada con NULL/"" cae al valor por defecto.
    evento["tipo_cobertura"] = fila["tipo_cobertura"] or TIPO_COBERTURA_TRANSMISION
    evento["prioridad"] = fila["prioridad"] or PRIORIDAD_EVENTO_DEFECTO
    # `marca` puede ser NULL en filas muy antiguas (antes de la columna); normalizar a "".
    evento["marca"] = fila["marca"] or ""
    return evento


# --- Eventos / transmisiones --------------------------------------------------


def crear_evento_rota(
    titulo: str,
    *,
    fecha: str = "",
    hora: str = "",
    contenido: str = "",
    nota: str = "",
    tipo_cobertura: str = TIPO_COBERTURA_TRANSMISION,
    prioridad: str = PRIORIDAD_EVENTO_DEFECTO,
    marca: str = "",
) -> dict[str, Any]:
    """Inserta un evento/transmision y lo devuelve. NO valida (lo hace la API).

    Nace `cambiado=0` (sin reprogramar) y con `actualizado`=`creado` (alta = primera version).
    `marca` es el id canonico de la marca a la que pertenece el evento ("" = sin marca asignada).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "titulo": titulo,
        "fecha": fecha or "",
        "hora": hora or "",
        "contenido": contenido or "",
        "nota": nota or "",
        "tipo_cobertura": tipo_cobertura if tipo_cobertura in TIPOS_COBERTURA else TIPO_COBERTURA_TRANSMISION,
        "prioridad": prioridad if prioridad in PRIORIDADES_EVENTO else PRIORIDAD_EVENTO_DEFECTO,
        "cambiado": 0,
        "actualizado": ahora,
        "creado": ahora,
        "marca": marca or "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_EVENTO_ROTA)
        con.execute(
            f"INSERT INTO rota_eventos ({', '.join(_COLS_EVENTO_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_EVENTO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["cambiado"] = bool(fila["cambiado"])
    return fila


def listar_eventos_rota(
    desde: str | None = None,
    hasta: str | None = None,
    *,
    solo_cambiados: bool = False,
    tipo_cobertura: str | None = None,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    """Eventos de la rota, en orden cronologico. Filtros opcionales (todos combinables).

    `desde`/`hasta` acotan por rango de fechas (ISO). `solo_cambiados` deja solo los
    REPROGRAMADOS (`cambiado=1`, los que Elias debe re-avisar). `tipo_cobertura` filtra por
    tipo de cobertura (transmision|imagenes|no_cubrir); la API ya valida el valor.
    `marca` filtra por id canonico de marca; None o "" -> sin filtro (devuelve todas).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if desde:
        clausulas.append("fecha >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("fecha <= ?")
        params.append(hasta)
    if solo_cambiados:
        clausulas.append("cambiado = ?")
        params.append(1)
    if tipo_cobertura:
        clausulas.append("tipo_cobertura = ?")
        params.append(tipo_cobertura)
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    sql = _SELECT_EVENTO_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY fecha ASC, hora ASC, titulo ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_evento_rota(f) for f in filas]


def obtener_evento_rota(evento_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_EVENTO_ROTA} WHERE id = ?", (evento_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evento_rota(fila) if fila is not None else None


# Campos cuya EDICION reprograma el evento: si cambia su valor, `cambiado` se pone a 1
# (hay que volver a avisar al equipo). Son los datos "logisticos" que el equipo de
# programacion mueve constantemente ("tres cambios en horarios para el fin de semana").
_CAMPOS_REPROGRAMAN_EVENTO: tuple[str, ...] = ("fecha", "hora", "tipo_cobertura")


def actualizar_evento_rota(evento_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un evento; None si el id no existe.

    Reglas de SEGUIMIENTO DE CAMBIOS (ola B, #144):
      - `actualizado` SIEMPRE se refresca (toda edicion deja marca temporal).
      - Si la edicion cambia `fecha`, `hora` o `tipo_cobertura` -> `cambiado=1` automatico
        (se reprogramo: el equipo debe re-enterarse). Solo si el valor REALMENTE cambia.
      - Si el request trae `cambiado=False` explicito (la accion "ya avisé / visto" de
        Elias) -> se LIMPIA a 0, y limpiar GANA aunque en el mismo request se hubiera
        reprogramado (Elias dice "ya está visto").
    Solo se escriben los campos editables; `cambiado`/`actualizado` los gestiona el sistema.
    """
    actual = obtener_evento_rota(evento_id)
    if actual is None:
        return None

    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_EVENTO_ROTA}

    # ¿Se reprogramo? Solo cuenta un cambio REAL de fecha/hora/tipo_cobertura.
    reprogramado = any(
        k in cambios and cambios[k] != actual.get(k) for k in _CAMPOS_REPROGRAMAN_EVENTO
    )
    nuevo_cambiado = 1 if reprogramado else int(bool(actual["cambiado"]))
    # La accion explicita "marcar avisado" (cambiado=False) limpia y GANA al reprograma.
    if "cambiado" in campos and not campos["cambiado"]:
        nuevo_cambiado = 0
    elif "cambiado" in campos and campos["cambiado"]:
        nuevo_cambiado = 1

    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("cambiado = ?")
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), nuevo_cambiado, ahora, evento_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_eventos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- columnas de allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_EVENTO_ROTA} WHERE id = ?", (evento_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evento_rota(fila) if fila is not None else None


def borrar_evento_rota(evento_id: str) -> bool:
    """Borra un evento. True si existia.

    NO arrastra cascada sobre `rota_turnos` (los turnos son horarios del miembro, viven
    independientes del evento; un evento borrado simplemente deja de cubrirse via la vista
    derivada de cobertura).
    """
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_eventos WHERE id = ?", (evento_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Turnos (horario persona×dia×franja) --------------------------------------
#
# Un TURNO es el horario que un miembro tiene en una (fecha, franja). NO va asociado a un
# evento. Cubre todos los eventos que caigan en su franja (cobertura derivada, no persistida).
# Forma identica a la antigua `rota_turnos` (modelo viejo) tras la migracion.

_COLS_TURNO_ROTA = (
    "id",
    "semana",
    "fecha",
    "miembro_id",
    "miembro_nombre",
    "franja_id",
    "estado",
    "override",
    "motivo",
    "nota_relevo",
    "creado",
    "actualizado",
)
_SELECT_TURNO_ROTA = f"SELECT {', '.join(_COLS_TURNO_ROTA)} FROM rota_turnos"

# Campos editables via `actualizar_turno_rota` (allowlist). `id`/`semana`/`creado` no son
# editables aqui (la semana se deriva de la fecha si esta cambia). `actualizado` lo gestiona
# el sistema.
_CAMPOS_EDITABLES_TURNO_ROTA: tuple[str, ...] = (
    "fecha",
    "miembro_id",
    "miembro_nombre",
    "franja_id",
    "estado",
    "override",
    "motivo",
    "nota_relevo",
)


def _fila_a_turno_rota(fila: Any) -> dict[str, Any]:
    turno = {col: fila[col] for col in _COLS_TURNO_ROTA}
    turno["override"] = bool(fila["override"])
    return turno


def crear_turno_rota(
    semana: str,
    fecha: str,
    *,
    miembro_id: str = "",
    miembro_nombre: str = "",
    franja_id: str = "",
    estado: str = ESTADO_ROTA_PROPUESTO,
    override: bool = False,
    motivo: str = "",
    nota_relevo: str = "",
    franja: str | None = None,
) -> dict[str, Any]:
    """Inserta un TURNO (horario en `(fecha, franja_id)` para `miembro_id`) y lo devuelve.

    NO valida (lo hace la API). NO comprueba unicidad (semana, fecha, miembro_id,
    franja_id); eso es responsabilidad del endpoint POST (que devuelve 409 si choca).

    RETROCOMPAT: acepta `franja` (literal 'matutino'/'vespertino'/'descanso') traduciendolo
    a `franja_id` via las franjas por defecto de la semana. Mismo contrato que el shim de
    `repos.crear_turno_rota`; codigo NUEVO debe pasar `franja_id` directamente.
    """
    if franja_id == "" and franja is not None:
        franja_norm = (franja or "").strip().lower()
        # Sembramos en la conexion local (sin pasar por `repos` para evitar ciclos).
        con_t = _conectar()
        try:
            mapa = _sembrar_franjas_por_defecto_en(con_t, semana)
            con_t.commit()
        finally:
            con_t.close()
        if franja_norm == "matutino":
            franja_id = mapa.get(_NOMBRE_FRANJA_MANANA, "")
        elif franja_norm == "vespertino":
            franja_id = mapa.get(_NOMBRE_FRANJA_TARDE, "")
        elif franja_norm == "descanso":
            franja_id = mapa.get(_NOMBRE_FRANJA_DESCANSO, "")
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "semana": semana,
        "fecha": fecha or "",
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "franja_id": franja_id or "",
        "estado": estado if estado in ESTADOS_ROTA else ESTADO_ROTA_PROPUESTO,
        "override": 1 if override else 0,
        "motivo": motivo or "",
        "nota_relevo": nota_relevo or "",
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_TURNO_ROTA)
        con.execute(
            f"INSERT INTO rota_turnos ({', '.join(_COLS_TURNO_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_TURNO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["override"] = bool(fila["override"])
    return fila


def listar_turnos_rota(semana: str | None = None) -> list[dict[str, Any]]:
    """Turnos del horario; filtro opcional por `semana` (lunes ISO)."""
    sql = _SELECT_TURNO_ROTA
    params: tuple[Any, ...] = ()
    if semana:
        sql += " WHERE semana = ?"
        params = (semana,)
    sql += " ORDER BY semana ASC, fecha ASC, franja_id ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_fila_a_turno_rota(f) for f in filas]


def obtener_turno_rota(turno_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_TURNO_ROTA} WHERE id = ?", (turno_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def existe_turno_para(
    miembro_id: str, fecha: str, franja_id: str
) -> dict[str, Any] | None:
    """Devuelve el turno actual de `(miembro_id, fecha, franja_id)`; None si no hay.

    Sirve para que el endpoint POST detecte choque (devolver 409 antes de insertar duplicado).
    """
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_TURNO_ROTA} WHERE miembro_id = ? AND fecha = ? AND franja_id = ? LIMIT 1",
            (miembro_id, fecha, franja_id),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def actualizar_turno_rota(turno_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita un turno (allowlist `_CAMPOS_EDITABLES_TURNO_ROTA`); None si el id no existe.

    Pone `actualizado` a ahora. `override` se normaliza a 0/1. Si la fecha cambia, la semana
    NO se recalcula aqui (la API decide si tambien envia `semana` ajustada cuando hace falta).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_TURNO_ROTA}
    if "override" in cambios:
        cambios["override"] = 1 if cambios["override"] else 0
    if not cambios:
        return obtener_turno_rota(turno_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(turno_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_turnos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_TURNO_ROTA} WHERE id = ?", (turno_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def borrar_turnos_semana_rota(semana: str) -> int:
    """Borra TODOS los turnos de una semana. Devuelve cuantos borro."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_turnos WHERE semana = ?", (semana,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def borrar_turno_rota(turno_id: str) -> bool:
    """Borra un turno individual; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_turnos WHERE id = ?", (turno_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_turnos_rota_lote(ids: list[str]) -> int:
    """Borra varios turnos en una sola sentencia. 0 si `ids` venia vacio."""
    if not ids:
        return 0
    marcadores = ", ".join("?" for _ in ids)
    con = _conectar()
    try:
        cur = con.execute(
            f"DELETE FROM rota_turnos WHERE id IN ({marcadores})",  # noqa: S608 -- placeholders
            tuple(ids),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def aprobar_semana_rota(semana: str) -> int:
    """Marca TODOS los turnos de una semana como `aprobado` (publica al equipo).

    Devuelve cuantos turnos quedaron aprobados. Idempotente: re-aprobar no rompe.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE rota_turnos SET estado = ?, actualizado = ? WHERE semana = ?",
            (ESTADO_ROTA_APROBADO, ahora, semana),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def desaprobar_semana_rota(semana: str) -> int:
    """Marca TODOS los turnos de una semana como `propuesto` (vuelve a borrador).

    Inverso de `aprobar_semana_rota`. Devuelve cuantos turnos quedaron en borrador.
    Idempotente.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE rota_turnos SET estado = ?, actualizado = ? WHERE semana = ?",
            (ESTADO_ROTA_PROPUESTO, ahora, semana),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def crear_turnos_rota_lote(turnos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta varios turnos en una sola transaccion. Devuelve la lista de turnos creados.

    Cada dict en `turnos` puede tener: `semana`, `fecha`, `miembro_id`, `miembro_nombre`,
    `franja`, `estado`, `override`, `motivo`, `nota_relevo`. La API valida CADA entrada
    antes de pasarla aqui; aqui solo se persiste con defensas minimas (uuid, `actualizado`).

    NO comprueba unicidad: si dos turnos chocan en (semana, fecha, miembro_id, franja), se
    persisten ambos (el endpoint lote es responsable de cribar antes). Lista vacia -> sin op.
    """
    if not turnos:
        return []
    ahora = datetime.now().isoformat(timespec="seconds")
    filas: list[dict[str, Any]] = []
    for entrada in turnos:
        estado = entrada.get("estado") or ESTADO_ROTA_PROPUESTO
        filas.append(
            {
                "id": uuid.uuid4().hex[:12],
                "semana": entrada.get("semana", ""),
                "fecha": entrada.get("fecha", "") or "",
                "miembro_id": entrada.get("miembro_id", "") or "",
                "miembro_nombre": entrada.get("miembro_nombre", "") or "",
                "franja_id": entrada.get("franja_id", "") or "",
                "estado": estado if estado in ESTADOS_ROTA else ESTADO_ROTA_PROPUESTO,
                "override": 1 if entrada.get("override") else 0,
                "motivo": entrada.get("motivo", "") or "",
                "nota_relevo": entrada.get("nota_relevo", "") or "",
                "creado": ahora,
                "actualizado": ahora,
            }
        )
    marcadores = ", ".join("?" for _ in _COLS_TURNO_ROTA)
    sql = (
        f"INSERT INTO rota_turnos ({', '.join(_COLS_TURNO_ROTA)}) VALUES ({marcadores})"
    )
    con = _conectar()
    try:
        for fila in filas:
            con.execute(sql, tuple(fila[col] for col in _COLS_TURNO_ROTA))
        con.commit()
    finally:
        con.close()
    # Devolvemos los turnos creados con `override` como bool (formato API).
    for fila in filas:
        fila["override"] = bool(fila["override"])
    return filas


def duplicar_turno_rota(
    turno_id: str,
    *,
    fecha: str | None = None,
    miembro_id: str | None = None,
    miembro_nombre: str | None = None,
    franja_id: str | None = None,
    semana: str | None = None,
) -> dict[str, Any] | None:
    """Clona un turno con overrides opcionales. None si el id no existe.

    Caso comun: "rellena la semana siguiente con el turno de Luis del lunes". El estado se
    reinicia a `propuesto` (Elias re-aprueba antes de publicar). `motivo` y `nota_relevo`
    NO viajan (son del turno ORIGINAL, no del clon).
    """
    original = obtener_turno_rota(turno_id)
    if original is None:
        return None
    return crear_turno_rota(
        semana if semana is not None else original["semana"],
        fecha if fecha is not None else original["fecha"],
        miembro_id=miembro_id if miembro_id is not None else original["miembro_id"],
        miembro_nombre=miembro_nombre if miembro_nombre is not None else original["miembro_nombre"],
        franja_id=franja_id if franja_id is not None else original["franja_id"],
        estado=ESTADO_ROTA_PROPUESTO,
        override=bool(original.get("override", False)),
        motivo="",
        nota_relevo="",
    )


# --------------------------------------------------------------------------- #
# Ausencias / vacaciones                                                       #
# --------------------------------------------------------------------------- #

_COLS_AUSENCIA_ROTA = (
    "id",
    "miembro_id",
    "miembro_nombre",
    "tipo",
    "desde",
    "hasta",
    "motivo",
    "creado",
)
_SELECT_AUSENCIA_ROTA = f"SELECT {', '.join(_COLS_AUSENCIA_ROTA)} FROM rota_ausencias"


def _fila_a_ausencia_rota(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_AUSENCIA_ROTA}


# --- Ausencias / vacaciones ---------------------------------------------------


def crear_ausencia_rota(
    miembro_id: str,
    desde: str,
    hasta: str,
    *,
    miembro_nombre: str = "",
    tipo: str = "otro",
    motivo: str = "",
) -> dict[str, Any]:
    """Inserta una ausencia (rango inclusivo) y la devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "tipo": tipo if tipo in TIPOS_AUSENCIA else "otro",
        "desde": desde or "",
        "hasta": hasta or "",
        "motivo": motivo or "",
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_AUSENCIA_ROTA)
        con.execute(
            f"INSERT INTO rota_ausencias ({', '.join(_COLS_AUSENCIA_ROTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_AUSENCIA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_ausencias_rota(
    miembro_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Ausencias de la rota, mas recientes primero. Filtros opcionales por miembro y solape de rango.

    `desde`/`hasta` filtran las ausencias que SOLAPAN con ese rango (ausencia.hasta >= desde
    AND ausencia.desde <= hasta): util para resolver las ausencias relevantes a una semana.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if miembro_id:
        clausulas.append("miembro_id = ?")
        params.append(miembro_id)
    if desde:
        clausulas.append("hasta >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("desde <= ?")
        params.append(hasta)
    sql = _SELECT_AUSENCIA_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY desde DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_ausencia_rota(f) for f in filas]


def obtener_ausencia_rota(ausencia_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def actualizar_ausencia_rota(
    ausencia_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una ausencia (tipo/desde/hasta/motivo); None si el id no existe."""
    editables = ("tipo", "desde", "hasta", "motivo")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return obtener_ausencia_rota(ausencia_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = list(cambios.values())
    params.append(ausencia_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_ausencias SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def borrar_ausencia_rota(ausencia_id: str) -> bool:
    """Borra una ausencia; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_ausencias WHERE id = ?", (ausencia_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Piezas de la parrilla (#150, PARRILLA 2026.xlsx)                              #
# --------------------------------------------------------------------------- #
#
# En el Excel de Tescu cada FILA es un POST INDIVIDUAL, no un evento. Una transmision
# como "LIV GOLF Andalucia R1" genera 4 piezas (pre-evento FB/IG/X, reel IG/TK, historia
# "5:15 LINK VIVO", post-evento). Tambien hay campanas EVERGREEN sin evento (Alvaro Fidalgo,
# Real Oviedo, MUNDIAL, Paty Cantu): piezas con `programa` y sin `evento_id`. El workflow de
# produccion del Excel (Material entregado / Contenido entregado / Publicado / Enlace) se
# persiste tal cual; la validacion (estado en allowlist, evento real, responsable real) la
# hace la capa API. `red_social`/`tipo_pieza` son campos LIBRES (Tescu pone "FB, IG, X",
# "HISTORIA", "IG, TK (REEL)", "WEB"; "IMAGEN" / "VIDEO" / "REEL" / "NOTA" / "FIJAR"): no
# encajan en una allowlist cerrada todavia.

_COLS_PIEZA_ROTA = (
    "id",
    "evento_id",
    "programa",
    "red_social",
    "tipo_pieza",
    "contenido_sugerido",
    "dia",
    "hora_post",
    "estado",
    "material_entregado",
    "contenido_entregado",
    "publicado",
    "enlace",
    "responsable_id",
    "responsable_nombre",
    "notas",
    "salida",
    "comentarios",
    "fecha_entrega_material",
    "always_on",
    "creado",
    "actualizado",
)
_SELECT_PIEZA_ROTA = f"SELECT {', '.join(_COLS_PIEZA_ROTA)} FROM rota_piezas"

# Campos editables via `actualizar_pieza_rota` (lista blanca). `id`, `creado` y
# `actualizado` no son editables; este ultimo lo gestiona el sistema. `responsable_id` y
# `responsable_nombre` se pasan como par desde la API (se valida `responsable_id` contra
# un usuario REAL antes de llegar aqui). `always_on` es booleano (0/1).
_CAMPOS_EDITABLES_PIEZA_ROTA: tuple[str, ...] = (
    "evento_id",
    "programa",
    "red_social",
    "tipo_pieza",
    "contenido_sugerido",
    "dia",
    "hora_post",
    "estado",
    "material_entregado",
    "contenido_entregado",
    "publicado",
    "enlace",
    "responsable_id",
    "responsable_nombre",
    "notas",
    "salida",
    "comentarios",
    "fecha_entrega_material",
    "always_on",
)


def _fila_a_pieza_rota(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `rota_piezas` en un dict (booleanos como bool, no 0/1)."""
    pieza: dict[str, Any] = {col: fila[col] for col in _COLS_PIEZA_ROTA}
    pieza["material_entregado"] = bool(fila["material_entregado"])
    pieza["contenido_entregado"] = bool(fila["contenido_entregado"])
    pieza["publicado"] = bool(fila["publicado"])
    pieza["always_on"] = bool(fila["always_on"])
    pieza["estado"] = fila["estado"] or "pendiente"
    return pieza


def crear_pieza_rota(
    *,
    evento_id: str = "",
    programa: str = "",
    red_social: str = "",
    tipo_pieza: str = "",
    contenido_sugerido: str = "",
    dia: str = "",
    hora_post: str = "",
    estado: str = "pendiente",
    material_entregado: bool = False,
    contenido_entregado: bool = False,
    publicado: bool = False,
    enlace: str = "",
    responsable_id: str = "",
    responsable_nombre: str = "",
    notas: str = "",
    salida: str = "",
    comentarios: str = "",
    fecha_entrega_material: str = "",
    always_on: bool = False,
) -> dict[str, Any]:
    """Inserta una pieza de la parrilla y la devuelve. NO valida (lo hace la API).

    Una pieza puede estar atada a un evento (`evento_id`) o ser SUELTA (campana evergreen),
    en cuyo caso el `evento_id` queda vacio y la identifica `programa` (p. ej. "Alvaro
    Fidalgo", "MUNDIAL"). La API obliga a que al menos uno entre `evento_id`, `programa` o
    `contenido_sugerido` este relleno para que la pieza represente algo.

    `salida` es el canal AMPLIO (TV, RADIO, OOH, PROGRAMA, YT, WEB...; distinto de
    `red_social` que es FB/IG/X/TK). `comentarios` es texto libre PRE/durante; `notas` es
    post-mortem. `fecha_entrega_material` es el deadline interno antes de `dia`. `always_on`
    marca piezas evergreen sin fecha (la `dia` se permite vacia en ese caso).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "evento_id": evento_id or "",
        "programa": programa or "",
        "red_social": red_social or "",
        "tipo_pieza": tipo_pieza or "",
        "contenido_sugerido": contenido_sugerido or "",
        "dia": dia or "",
        "hora_post": hora_post or "",
        "estado": estado if estado in ESTADOS_PIEZA else "pendiente",
        "material_entregado": 1 if material_entregado else 0,
        "contenido_entregado": 1 if contenido_entregado else 0,
        "publicado": 1 if publicado else 0,
        "enlace": enlace or "",
        "responsable_id": responsable_id or "",
        "responsable_nombre": responsable_nombre or "",
        "notas": notas or "",
        "salida": salida or "",
        "comentarios": comentarios or "",
        "fecha_entrega_material": fecha_entrega_material or "",
        "always_on": 1 if always_on else 0,
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PIEZA_ROTA)
        con.execute(
            f"INSERT INTO rota_piezas ({', '.join(_COLS_PIEZA_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PIEZA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["material_entregado"] = bool(fila["material_entregado"])
    fila["contenido_entregado"] = bool(fila["contenido_entregado"])
    fila["publicado"] = bool(fila["publicado"])
    fila["always_on"] = bool(fila["always_on"])
    return fila


def listar_piezas_rota(
    *,
    evento_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    red: str | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    responsable_id: str | None = None,
    programa: str | None = None,
) -> list[dict[str, Any]]:
    """Piezas de la parrilla, ordenadas por dia y orden de creacion. Filtros combinables.

    `desde`/`hasta` acotan por `dia` (ISO inclusivo). `red`/`tipo`/`programa` filtran texto
    EXACTO (los campos son libres; la UI manda el valor exacto). `estado` y `responsable_id`
    filtran como cabe esperar. `evento_id=""` lista las piezas SUELTAS (sin evento).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if evento_id is not None:
        clausulas.append("evento_id = ?")
        params.append(evento_id)
    if desde:
        clausulas.append("dia >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("dia <= ?")
        params.append(hasta)
    if red:
        clausulas.append("red_social = ?")
        params.append(red)
    if tipo:
        clausulas.append("tipo_pieza = ?")
        params.append(tipo)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if responsable_id is not None:
        clausulas.append("responsable_id = ?")
        params.append(responsable_id)
    if programa is not None:
        clausulas.append("programa = ?")
        params.append(programa)
    sql = _SELECT_PIEZA_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    # Por `dia` ASC (las piezas SIN fechar caen al final con DIA="") y luego por orden de
    # creacion para un orden estable (uuid corto desempata si crearon en el mismo segundo).
    sql += " ORDER BY dia ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_pieza_rota(f) for f in filas]


def obtener_pieza_rota(pieza_id: str) -> dict[str, Any] | None:
    """Una pieza por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PIEZA_ROTA} WHERE id = ?", (pieza_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_pieza_rota(fila) if fila is not None else None


def actualizar_pieza_rota(
    pieza_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una pieza; None si el id no existe.

    `campos` se filtra a `_CAMPOS_EDITABLES_PIEZA_ROTA` (defensa en profundidad: nunca se
    escriben columnas arbitrarias). Los booleanos se normalizan a 0/1. `actualizado` se
    refresca SIEMPRE que haya cambios reales. La validacion (estado en allowlist, evento
    real, responsable real, enlace acotado) la hace la capa API.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PIEZA_ROTA}
    if not cambios:
        return obtener_pieza_rota(pieza_id)
    for col in ("material_entregado", "contenido_entregado", "publicado", "always_on"):
        if col in cambios:
            cambios[col] = 1 if cambios[col] else 0
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, pieza_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_piezas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- columnas de allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_PIEZA_ROTA} WHERE id = ?", (pieza_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_pieza_rota(fila) if fila is not None else None


def borrar_pieza_rota(pieza_id: str) -> bool:
    """Borra una pieza; True si existia, False si no.

    NO arrastra cascada desde `rota_eventos`: borrar un evento NO borra sus piezas (decision
    de la API). Las piezas huerfanas tras borrar el evento siguen accesibles via su programa.
    """
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_piezas WHERE id = ?", (pieza_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_piezas_rota_lote(ids: list[str]) -> int:
    """Borra varias piezas en una sola sentencia (rowcount). 0 si la lista venia vacia."""
    if not ids:
        return 0
    marcadores = ", ".join("?" for _ in ids)
    con = _conectar()
    try:
        cur = con.execute(
            f"DELETE FROM rota_piezas WHERE id IN ({marcadores})",  # noqa: S608 -- placeholders
            tuple(ids),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def duplicar_pieza_rota(
    pieza_id: str, *, dia: str | None = None, evento_id: str | None = None
) -> dict[str, Any] | None:
    """Crea una pieza nueva clonando los campos editoriales de `pieza_id`.

    DECISION DE NEGOCIO: el clon RESETEA el WORKFLOW de produccion (material/contenido/
    publicado/enlace -> vacios y `estado` -> "pendiente"): duplicar una pieza es repetir el
    TRABAJO, no copiar la pieza ya publicada. `comentarios` y `notas` tampoco viajan (son
    contexto del POST original, no del clon). `dia`/`evento_id` se pueden sobrescribir con
    los argumentos (caso comun: "Jornada 17 -> Jornada 18"). Devuelve la pieza nueva (con id
    propio y timestamps frescos), o None si el `pieza_id` no existe.
    """
    original = obtener_pieza_rota(pieza_id)
    if original is None:
        return None
    return crear_pieza_rota(
        evento_id=evento_id if evento_id is not None else original.get("evento_id", ""),
        programa=original.get("programa", ""),
        red_social=original.get("red_social", ""),
        tipo_pieza=original.get("tipo_pieza", ""),
        contenido_sugerido=original.get("contenido_sugerido", ""),
        dia=dia if dia is not None else original.get("dia", ""),
        hora_post=original.get("hora_post", ""),
        # Workflow reset: el clon arranca como pendiente y sin material/contenido/publicado.
        estado="pendiente",
        material_entregado=False,
        contenido_entregado=False,
        publicado=False,
        enlace="",
        responsable_id=original.get("responsable_id", ""),
        responsable_nombre=original.get("responsable_nombre", ""),
        notas="",  # post-mortem del original; no aplica al clon.
        salida=original.get("salida", ""),
        comentarios="",  # contexto pre/durante del original; no aplica al clon.
        fecha_entrega_material=original.get("fecha_entrega_material", ""),
        always_on=bool(original.get("always_on", False)),
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
# Biblioteca de MEDIOS interna (ola "activos")                                  #
# --------------------------------------------------------------------------- #
# Tabla `biblioteca_media`: cataloga objetos del almacen de media (`media.py`) por su
# nombre (`objeto`, uuid+ext del servidor) con metadatos editoriales y etiquetas (JSON de
# strings). El binario lo guarda/sirve `media.py`; aqui solo el catalogo reutilizable.

_COLS_BIBLIOTECA_MEDIA = (
    "id",
    "objeto",
    "tipo",
    "titulo",
    "descripcion",
    "marca",
    "etiquetas",
    "credito",
    "aprobado",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_BIBLIOTECA_MEDIA = (
    f"SELECT {', '.join(_COLS_BIBLIOTECA_MEDIA)} FROM biblioteca_media"
)

# Campos editables via `actualizar_media_biblioteca` (lista blanca). `id`, `objeto`,
# `autor_*`, `creado` y `actualizado` no son editables (el objeto NO se reasigna; se
# cataloga uno nuevo si cambia el binario).
_CAMPOS_EDITABLES_BIBLIOTECA_MEDIA: tuple[str, ...] = (
    "tipo",
    "titulo",
    "descripcion",
    "marca",
    "etiquetas",
    "credito",
    "aprobado",
)


def _fila_a_media_biblioteca(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `biblioteca_media` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_BIBLIOTECA_MEDIA}
    item["aprobado"] = bool(fila["aprobado"])
    item["etiquetas"] = fila["etiquetas"] or "[]"
    item["tipo"] = fila["tipo"] or "imagen"
    return item


def crear_media_biblioteca(
    *,
    objeto: str,
    tipo: str = "imagen",
    titulo: str = "",
    descripcion: str = "",
    marca: str = "",
    etiquetas: str = "[]",
    credito: str = "",
    aprobado: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Cataloga un objeto de media en la biblioteca y lo devuelve. NO valida (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "objeto": objeto or "",
        "tipo": tipo or "imagen",
        "titulo": titulo or "",
        "descripcion": descripcion or "",
        "marca": marca or "",
        "etiquetas": etiquetas or "[]",
        "credito": credito or "",
        "aprobado": 1 if aprobado else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_BIBLIOTECA_MEDIA)
        con.execute(
            f"INSERT INTO biblioteca_media ({', '.join(_COLS_BIBLIOTECA_MEDIA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_BIBLIOTECA_MEDIA),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_media_biblioteca(fila)


def listar_media_biblioteca(
    *,
    marca: str | None = None,
    tipo: str | None = None,
    solo_aprobados: bool = False,
) -> list[dict[str, Any]]:
    """Items de la biblioteca de medios, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_aprobados:
        clausulas.append("aprobado = 1")
    sql = _SELECT_BIBLIOTECA_MEDIA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_media_biblioteca(f) for f in filas]


def obtener_media_biblioteca(media_id: str) -> dict[str, Any] | None:
    """Un item de la biblioteca por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_BIBLIOTECA_MEDIA} WHERE id = ?", (media_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_media_biblioteca(fila) if fila is not None else None


def existe_media_objeto(objeto: str) -> bool:
    """True si ya hay un item de biblioteca catalogando ese `objeto` (UNIQUE)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM biblioteca_media WHERE objeto = ?", (objeto,)
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def actualizar_media_biblioteca(
    media_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {
        k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_BIBLIOTECA_MEDIA
    }
    if "aprobado" in cambios:
        cambios["aprobado"] = 1 if cambios["aprobado"] else 0
    if not cambios:
        return obtener_media_biblioteca(media_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, media_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE biblioteca_media SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_BIBLIOTECA_MEDIA} WHERE id = ?", (media_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_media_biblioteca(fila) if fila is not None else None


def borrar_media_biblioteca(media_id: str) -> dict[str, Any] | None:
    """Borra un item de la biblioteca; devuelve el item borrado (para limpiar el binario) o None."""
    item = obtener_media_biblioteca(media_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM biblioteca_media WHERE id = ?", (media_id,))
        con.commit()
    finally:
        con.close()
    return item


# --------------------------------------------------------------------------- #
# Activos de marca (editor profesional: kit visual reutilizable por marca)       #
# --------------------------------------------------------------------------- #

_COLS_MARCA_ACTIVOS = (
    "id",
    "marca",
    "tipo",
    "nombre",
    "objeto",
    "metadatos",
    "lineas",
    "aprobado",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_MARCA_ACTIVOS = f"SELECT {', '.join(_COLS_MARCA_ACTIVOS)} FROM marca_activos"

# Campos editables via `actualizar_marca_activo` (lista blanca). `id`, `marca`, `objeto`,
# `autor_*` y `creado` no son editables (un activo nuevo se cataloga aparte).
_CAMPOS_EDITABLES_MARCA_ACTIVOS: tuple[str, ...] = (
    "tipo",
    "nombre",
    "metadatos",
    "lineas",
    "aprobado",
)


def _fila_a_marca_activo(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `marca_activos` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_MARCA_ACTIVOS}
    item["aprobado"] = bool(fila["aprobado"])
    item["metadatos"] = fila["metadatos"] or "{}"
    item["lineas"] = fila["lineas"] or "[]"
    item["tipo"] = fila["tipo"] or "arte"
    return item


def crear_marca_activo(
    *,
    marca: str,
    tipo: str = "arte",
    nombre: str = "",
    objeto: str = "",
    metadatos: str = "{}",
    lineas: str = "[]",
    aprobado: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Cataloga un activo de marca y lo devuelve. NO valida (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "tipo": tipo or "arte",
        "nombre": nombre or "",
        "objeto": objeto or "",
        "metadatos": metadatos or "{}",
        "lineas": lineas or "[]",
        "aprobado": 1 if aprobado else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_MARCA_ACTIVOS)
        con.execute(
            f"INSERT INTO marca_activos ({', '.join(_COLS_MARCA_ACTIVOS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_MARCA_ACTIVOS),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_marca_activo(fila)


def listar_marca_activos(
    *, marca: str | None = None, tipo: str | None = None, solo_aprobados: bool = False
) -> list[dict[str, Any]]:
    """Activos de marca, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_aprobados:
        clausulas.append("aprobado = 1")
    sql = _SELECT_MARCA_ACTIVOS
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_marca_activo(f) for f in filas]


def obtener_marca_activo(activo_id: str) -> dict[str, Any] | None:
    """Un activo de marca por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_MARCA_ACTIVOS} WHERE id = ?", (activo_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_marca_activo(fila) if fila is not None else None


def actualizar_marca_activo(activo_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_MARCA_ACTIVOS}
    if "aprobado" in cambios:
        cambios["aprobado"] = 1 if cambios["aprobado"] else 0
    if not cambios:
        return obtener_marca_activo(activo_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, activo_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE marca_activos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_MARCA_ACTIVOS} WHERE id = ?", (activo_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_marca_activo(fila) if fila is not None else None


def borrar_marca_activo(activo_id: str) -> dict[str, Any] | None:
    """Borra un activo de marca; devuelve el borrado (para limpiar el binario) o None."""
    item = obtener_marca_activo(activo_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM marca_activos WHERE id = ?", (activo_id,))
        con.commit()
    finally:
        con.close()
    return item


# --------------------------------------------------------------------------- #
# Plantillas de diseño (editor profesional: N plantillas reutilizables por marca) #
# --------------------------------------------------------------------------- #

_COLS_PLANTILLAS_DISENO = (
    "id",
    "marca",
    "nombre",
    "categoria",
    "tipo",
    "documento",
    "miniatura",
    "lineas",
    "activo",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_PLANTILLAS_DISENO = f"SELECT {', '.join(_COLS_PLANTILLAS_DISENO)} FROM plantillas_diseno"

_CAMPOS_EDITABLES_PLANTILLAS_DISENO: tuple[str, ...] = (
    "nombre",
    "categoria",
    "tipo",
    "documento",
    "miniatura",
    "lineas",
    "activo",
)


def _fila_a_plantilla_diseno(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `plantillas_diseno` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_PLANTILLAS_DISENO}
    item["activo"] = bool(fila["activo"])
    item["documento"] = fila["documento"] or "{}"
    item["lineas"] = fila["lineas"] or "[]"
    item["categoria"] = fila["categoria"] or "post"
    item["tipo"] = fila["tipo"] if fila["tipo"] in ("foto", "miniatura") else "foto"
    return item


def crear_plantilla_diseno(
    *,
    marca: str,
    nombre: str = "",
    categoria: str = "post",
    tipo: str = "foto",
    documento: str = "{}",
    miniatura: str = "",
    lineas: str = "[]",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una plantilla de diseño y la devuelve. NO valida el documento (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "nombre": nombre or "",
        "categoria": categoria or "post",
        "tipo": tipo if tipo in ("foto", "miniatura") else "foto",
        "documento": documento or "{}",
        "miniatura": miniatura or "",
        "lineas": lineas or "[]",
        "activo": 1 if activo else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PLANTILLAS_DISENO)
        con.execute(
            f"INSERT INTO plantillas_diseno ({', '.join(_COLS_PLANTILLAS_DISENO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PLANTILLAS_DISENO),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila)


def listar_plantillas_diseno(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    tipo: str | None = None,
    solo_activas: bool = False,
) -> list[dict[str, Any]]:
    """Plantillas de diseño, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if categoria:
        clausulas.append("categoria = ?")
        params.append(categoria)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_activas:
        clausulas.append("activo = 1")
    sql = _SELECT_PLANTILLAS_DISENO
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_plantilla_diseno(f) for f in filas]


def obtener_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    """Una plantilla de diseño por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_PLANTILLAS_DISENO} WHERE id = ?", (plantilla_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila) if fila is not None else None


def actualizar_plantilla_diseno(plantilla_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PLANTILLAS_DISENO}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_plantilla_diseno(plantilla_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, plantilla_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE plantillas_diseno SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_PLANTILLAS_DISENO} WHERE id = ?", (plantilla_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila) if fila is not None else None


def borrar_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    """Borra una plantilla de diseño; devuelve la borrada o None."""
    item = obtener_plantilla_diseno(plantilla_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM plantillas_diseno WHERE id = ?", (plantilla_id,))
        con.commit()
    finally:
        con.close()
    return item


# --------------------------------------------------------------------------- #
# Bloques (almacén de capas reutilizables)                                       #
# --------------------------------------------------------------------------- #

_COLS_BLOQUES = (
    "id",
    "marca",
    "nombre",
    "capas",
    "lineas",
    "miniatura",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_BLOQUES = f"SELECT {', '.join(_COLS_BLOQUES)} FROM bloques"
_CAMPOS_EDITABLES_BLOQUES: tuple[str, ...] = ("nombre", "capas", "lineas", "miniatura")


def _fila_a_bloque(fila: Any) -> dict[str, Any]:
    item: dict[str, Any] = {col: fila[col] for col in _COLS_BLOQUES}
    item["capas"] = fila["capas"] or "[]"
    item["lineas"] = fila["lineas"] or "[]"
    return item


def crear_bloque(
    *,
    marca: str = "",
    nombre: str = "",
    capas: str = "[]",
    lineas: str = "[]",
    miniatura: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea un bloque (grupo de capas reutilizable) y lo devuelve."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "nombre": nombre or "",
        "capas": capas or "[]",
        "lineas": lineas or "[]",
        "miniatura": miniatura or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_BLOQUES)
        con.execute(
            f"INSERT INTO bloques ({', '.join(_COLS_BLOQUES)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_BLOQUES),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_bloque(fila)


def listar_bloques(*, marca: str | None = None) -> list[dict[str, Any]]:
    """Bloques, filtro opcional por marca. Mas recientes primero."""
    sql = _SELECT_BLOQUES
    params: list[Any] = []
    if marca:
        sql += " WHERE marca = ?"
        params.append(marca)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_bloque(f) for f in filas]


def obtener_bloque(bloque_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_BLOQUES} WHERE id = ?", (bloque_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_bloque(fila) if fila is not None else None


def actualizar_bloque(bloque_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_BLOQUES}
    if not cambios:
        return obtener_bloque(bloque_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, bloque_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE bloques SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_BLOQUES} WHERE id = ?", (bloque_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_bloque(fila) if fila is not None else None


def borrar_bloque(bloque_id: str) -> dict[str, Any] | None:
    item = obtener_bloque(bloque_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM bloques WHERE id = ?", (bloque_id,))
        con.commit()
    finally:
        con.close()
    return item


# --------------------------------------------------------------------------- #
# Versiones de documento (historial del editor por pieza)                        #
# --------------------------------------------------------------------------- #

_COLS_DOC_VERSIONES = (
    "id",
    "contenido_id",
    "plataforma_id",
    "version",
    "documento",
    "render_objeto",
    "autor_id",
    "autor_nombre",
    "creado",
)
_SELECT_DOC_VERSIONES = f"SELECT {', '.join(_COLS_DOC_VERSIONES)} FROM documento_versiones"


def _fila_a_doc_version(fila: Any) -> dict[str, Any]:
    item: dict[str, Any] = {col: fila[col] for col in _COLS_DOC_VERSIONES}
    item["documento"] = fila["documento"] or "{}"
    return item


# Tope de reintentos del contador de versiones ante choques de version concurrentes. Cada
# choque significa que OTRA edicion gano esa version; releemos el MAX y probamos la siguiente.
# Generoso a proposito: en el peor caso de N escritores simultaneos, un escritor puede perder
# hasta ~N-1 carreras antes de clavar su numero, asi que el tope debe holgar sobre la
# concurrencia realista de editores sobre UNA misma pieza (siempre baja en este producto).
_MAX_REINTENTOS_VERSION = 32


def crear_documento_version(
    *,
    contenido_id: str,
    plataforma_id: str,
    documento: str,
    render_objeto: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
) -> dict[str, Any]:
    """Apende una versión del documento de una pieza (version = max+1 para esa pieza).

    CONTADOR SEGURO ANTE CONCURRENCIA: `MAX(version)+1` + INSERT bajo el indice UNICO
    `(contenido_id, plataforma_id, version)`. Si dos ediciones simultaneas calculan el MISMO
    numero, una gana y la otra recibe una UniqueViolation; aqui REINTENTAMOS (bucle acotado)
    recalculando el siguiente numero, en vez de duplicar la version (que rompia el historial).
    """
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila_id = id or uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        ultimo_error: Exception | None = None
        for _ in range(_MAX_REINTENTOS_VERSION):
            fila_max = con.execute(
                "SELECT COALESCE(MAX(version), 0) AS m FROM documento_versiones "
                "WHERE contenido_id = ? AND plataforma_id = ?",
                (contenido_id, plataforma_id),
            ).fetchone()
            siguiente = int(fila_max["m"]) + 1
            fila = {
                "id": fila_id,
                "contenido_id": contenido_id or "",
                "plataforma_id": plataforma_id or "",
                "version": siguiente,
                "documento": documento or "{}",
                "render_objeto": render_objeto or "",
                "autor_id": autor.get("id", "") or "",
                "autor_nombre": autor.get("usuario", "") or "",
                "creado": creado or ahora,
            }
            marcadores = ", ".join("?" for _ in _COLS_DOC_VERSIONES)
            try:
                con.execute(
                    f"INSERT INTO documento_versiones ({', '.join(_COLS_DOC_VERSIONES)}) VALUES ({marcadores})",
                    tuple(fila[col] for col in _COLS_DOC_VERSIONES),
                )
                con.commit()
                return _fila_a_doc_version(fila)
            except IntegrityError as e:
                # Choque de version (otra edicion gano la carrera): el shim ya hizo rollback;
                # reintentamos releyendo el MAX para coger el numero siguiente.
                ultimo_error = e
        raise RuntimeError(
            "No se pudo asignar una version de documento tras varios reintentos "
            f"(contenido={contenido_id}, plataforma={plataforma_id})"
        ) from ultimo_error
    finally:
        con.close()


def listar_documento_versiones(contenido_id: str, plataforma_id: str) -> list[dict[str, Any]]:
    """Versiones de una pieza, mas reciente primero."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_DOC_VERSIONES} WHERE contenido_id = ? AND plataforma_id = ? "
            "ORDER BY version DESC",
            (contenido_id, plataforma_id),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_doc_version(f) for f in filas]


def ultima_documento_version(contenido_id: str, plataforma_id: str) -> dict[str, Any] | None:
    """La última versión del documento de una pieza (None si no hay)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_DOC_VERSIONES} WHERE contenido_id = ? AND plataforma_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (contenido_id, plataforma_id),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_doc_version(fila) if fila is not None else None


# --------------------------------------------------------------------------- #
# Webhooks salientes + bitacora de eventos internos (OPERACIONAL: Postgres)      #
# --------------------------------------------------------------------------- #
# `webhooks` = suscripciones a eventos internos del tablero (pieza aprobada / contenido
# vencido). `eventos_internos` = bitacora de lo EMITIDO (auditoria + idempotencia del
# barrido de vencimientos). El reparto a la red lo hace `dominio/eventos.py`; aqui solo
# se persiste. SAFE BY DEFAULT: sin webhooks activos no sale nada a la red.

_COLS_WEBHOOK = (
    "id",
    "nombre",
    "url",
    "eventos",
    "formato",
    "secreto",
    "activo",
    "ultimo_estado",
    "ultimo_en",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_WEBHOOK = f"SELECT {', '.join(_COLS_WEBHOOK)} FROM webhooks"
# Campos editables (lista blanca). `id`/`creado`/`autor_*` no se editan; `ultimo_*` los
# estampa el repartidor, no la API.
_CAMPOS_EDITABLES_WEBHOOK: tuple[str, ...] = (
    "nombre",
    "url",
    "eventos",
    "formato",
    "secreto",
    "activo",
    "ultimo_estado",
    "ultimo_en",
)


def _fila_a_webhook(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `webhooks` en dict (`eventos` como lista, `activo` como bool).

    NUNCA expone el `secreto` (credencial): se devuelve `tiene_secreto` (bool) en su lugar.
    """
    wh: dict[str, Any] = {col: fila[col] for col in _COLS_WEBHOOK}
    wh["activo"] = bool(fila["activo"])
    try:
        eventos = json.loads(wh["eventos"]) if wh["eventos"] else []
    except (ValueError, TypeError):
        eventos = []
    wh["eventos"] = eventos if isinstance(eventos, list) else []
    wh["tiene_secreto"] = bool(wh.pop("secreto", ""))
    return wh


def crear_webhook(
    *,
    nombre: str = "",
    url: str = "",
    eventos: list[str] | None = None,
    formato: str = "generico",
    secreto: str = "",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
) -> dict[str, Any]:
    """Inserta una suscripcion de webhook y la devuelve (sin exponer el secreto). NO valida."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "url": url or "",
        "eventos": json.dumps(list(eventos or [])),
        "formato": formato or "generico",
        "secreto": secreto or "",
        "activo": 1 if activo else 0,
        "ultimo_estado": "",
        "ultimo_en": "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_WEBHOOK)
        con.execute(
            f"INSERT INTO webhooks ({', '.join(_COLS_WEBHOOK)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_WEBHOOK),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_webhook(fila)


def listar_webhooks(*, solo_activos: bool = False) -> list[dict[str, Any]]:
    """Lista las suscripciones de webhook (sin exponer secretos). Orden estable por creacion."""
    sql = _SELECT_WEBHOOK
    if solo_activos:
        sql += " WHERE activo = 1"
    sql += " ORDER BY creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql).fetchall()
    finally:
        con.close()
    return [_fila_a_webhook(f) for f in filas]


def listar_webhooks_para(evento: str) -> list[dict[str, Any]]:
    """Webhooks ACTIVOS que escuchan `evento` (lista vacia => escucha todos). Incluye el secreto.

    Uso INTERNO del repartidor: a diferencia de `listar_webhooks`, devuelve el `secreto`
    crudo (lo necesita para firmar). NO exponer este resultado por la API.
    """
    con = _conectar()
    try:
        filas = con.execute(f"{_SELECT_WEBHOOK} WHERE activo = 1").fetchall()
    finally:
        con.close()
    salida: list[dict[str, Any]] = []
    for f in filas:
        try:
            eventos = json.loads(f["eventos"]) if f["eventos"] else []
        except (ValueError, TypeError):
            eventos = []
        if eventos and evento not in eventos:
            continue
        salida.append({col: f[col] for col in _COLS_WEBHOOK})
    return salida


def obtener_webhook(webhook_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_WEBHOOK} WHERE id = ?", (webhook_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_webhook(fila) if fila is not None else None


def obtener_webhook_con_secreto(webhook_id: str) -> dict[str, Any] | None:
    """Una suscripcion por id CON su secreto crudo (uso interno: probar/repartir). None si no existe.

    A diferencia de `obtener_webhook`, expone el `secreto` para firmar la entrega. NO
    devolver este dict por la API.
    """
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_WEBHOOK} WHERE id = ?", (webhook_id,)
        ).fetchone()
    finally:
        con.close()
    return {col: fila[col] for col in _COLS_WEBHOOK} if fila is not None else None


def actualizar_webhook(
    webhook_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una suscripcion; None si no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_WEBHOOK}
    if "eventos" in cambios and isinstance(cambios["eventos"], list):
        cambios["eventos"] = json.dumps(cambios["eventos"])
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_webhook(webhook_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, webhook_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE webhooks SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_WEBHOOK} WHERE id = ?", (webhook_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_webhook(fila) if fila is not None else None


def borrar_webhook(webhook_id: str) -> bool:
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def registrar_evento_interno(
    *,
    tipo: str,
    contenido_id: str = "",
    plataforma_id: str = "",
    clave_idempotencia: str = "",
    payload: dict[str, Any] | None = None,
) -> bool:
    """Registra un evento interno en la bitacora. False si su `clave_idempotencia` ya existia.

    La clave de idempotencia (UNIQUE) evita re-emitir el mismo vencimiento en cada barrido:
    si el INSERT choca con la constraint, devolvemos False sin tocar nada. Una clave vacia
    NO desduplica (cada llamada inserta): usala para eventos de transicion (siempre unicos).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "tipo": tipo,
        "contenido_id": contenido_id or "",
        "plataforma_id": plataforma_id or "",
        # Sin clave explicita, una unica por id: nunca desduplica (cada emision se registra).
        "clave_idempotencia": clave_idempotencia or uuid.uuid4().hex,
        "payload": json.dumps(payload or {}, ensure_ascii=False),
        "creado": ahora,
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO eventos_internos "
            "(id, tipo, contenido_id, plataforma_id, clave_idempotencia, payload, creado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fila["id"], fila["tipo"], fila["contenido_id"], fila["plataforma_id"],
                fila["clave_idempotencia"], fila["payload"], fila["creado"],
            ),
        )
        con.commit()
        return True
    except IntegrityError:
        # UNIQUE (clave_idempotencia): el evento ya se emitio antes, no se repite.
        # `_ConexionPg` ya hizo rollback (paridad con el resto de call sites).
        return False
    finally:
        con.close()


def listar_eventos_internos(*, limite: int = 50) -> list[dict[str, Any]]:
    """Ultimos eventos internos emitidos (bitacora), mas recientes primero."""
    limite = max(1, min(int(limite), 500))
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, tipo, contenido_id, plataforma_id, clave_idempotencia, payload, creado "
            "FROM eventos_internos ORDER BY creado DESC, id DESC LIMIT ?",
            (limite,),
        ).fetchall()
    finally:
        con.close()
    salida: list[dict[str, Any]] = []
    for f in filas:
        try:
            payload = json.loads(f["payload"]) if f["payload"] else {}
        except (ValueError, TypeError):
            payload = {}
        salida.append(
            {
                "id": f["id"],
                "tipo": f["tipo"],
                "contenido_id": f["contenido_id"],
                "plataforma_id": f["plataforma_id"],
                "payload": payload,
                "creado": f["creado"],
            }
        )
    return salida


# --------------------------------------------------------------------------- #
# CONTENIDO editorial reutilizable migrado de FICHEROS a Postgres (ADR 0006)    #
# --------------------------------------------------------------------------- #
# Fuentes RSS (+ items vistos + salud), grupos de hashtags y franjas editoriales eran los
# ULTIMOS rezagados file-backed (YAML + indice SQLite de rutas absolutas). Su indice de
# rutas se desincronizaba al recrear contenedores (Fuentes RSS aparecia vacia). Aqui viven
# en Postgres (ADR 0004/0006). Los dicts devueltos CONSERVAN las mismas claves que la capa
# de ficheros para no romper `api/rss.py`/`hashtags.py`/`franjas.py` ni el frontend. db.py
# NO valida (lo hace la API); `?` lo traduce `motor_db` a `%s`.

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
)


def _migrar_columnas_noticias_clusters(con: Any) -> None:
    """Anade a `noticias_clusters` las columnas de la Ola D que una BD vieja no tuviera (idempotente)."""
    if not _tabla_existe(con, "noticias_clusters"):
        return
    columnas = _columnas_existentes(con, "noticias_clusters")
    for columna, tipo in _COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE noticias_clusters ADD COLUMN IF NOT EXISTS {columna} {tipo}")


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
    ("idx_franjas_editoriales_uniq", "franjas_editoriales (marca, red, dia_semana, hora)"),
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


# --- Fuentes RSS ----------------------------------------------------------- #
# El dict publico (paridad con `ficheros._parsear_fuente`) NO incluye `creado` (orden
# interno): solo `id, nombre, url, marca, fecha, activo(bool), incluir, excluir, redes_def,
# ultima_actualizacion, ultimo_error, ultimo_conteo(int)`.
_COLS_FUENTE_RSS = (
    "id",
    "nombre",
    "url",
    "marca",
    "fecha",
    "activo",
    "incluir",
    "excluir",
    "redes_def",
    "ultima_actualizacion",
    "ultimo_error",
    "ultimo_conteo",
    "propia",
    "intervalo_min",
    "categoria",
    "prioridad",
    "proximo_sondeo",
    "errores_seguidos",
    "pausado_hasta",
    "desactivado_auto",
    "creado",
)
_SELECT_FUENTE_RSS = f"SELECT {', '.join(_COLS_FUENTE_RSS)} FROM fuentes_rss"
_CAMPOS_EDITABLES_FUENTE_RSS: tuple[str, ...] = (
    "nombre", "url", "marca", "activo", "incluir", "excluir", "redes_def", "propia",
    "intervalo_min", "categoria", "prioridad",
    # Ola D: reactivar un feed auto-desactivado (resetear estado del motor de ingesta).
    "desactivado_auto", "errores_seguidos", "proximo_sondeo", "pausado_hasta",
)


def _fila_a_fuente_rss(fila: Any) -> dict[str, Any]:
    """Fila de `fuentes_rss` -> dict publico (sin `creado`; `activo` bool, `ultimo_conteo` int)."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"] or "",
        "url": fila["url"] or "",
        "marca": fila["marca"] or "",
        "fecha": fila["fecha"] or "",
        "activo": bool(fila["activo"]),
        "incluir": fila["incluir"] or "",
        "excluir": fila["excluir"] or "",
        "redes_def": fila["redes_def"] or "",
        "ultima_actualizacion": fila["ultima_actualizacion"] or "",
        "ultimo_error": fila["ultimo_error"] or "",
        "ultimo_conteo": int(fila["ultimo_conteo"] or 0),
        # Sitio de marca PROPIA: habilita reutilizar la imagen original del artículo.
        "propia": bool(fila["propia"]),
        # Planificación del motor de ingesta (Ola A).
        "intervalo_min": int(fila["intervalo_min"] or 0),
        "categoria": fila["categoria"] or "",
        "prioridad": int(fila["prioridad"] or 0),
        "proximo_sondeo": fila["proximo_sondeo"] or "",
        "errores_seguidos": int(fila["errores_seguidos"] or 0),
        "pausado_hasta": fila["pausado_hasta"] or "",
        # Auto-desactivado por el motor (Ola D): True si el daemon lo apagó por errores seguidos.
        "desactivado_auto": bool(fila["desactivado_auto"]),
    }


def listar_fuentes_rss(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Fuentes RSS (mas recientes primero), con paginacion opcional."""
    sql = _SELECT_FUENTE_RSS + " ORDER BY creado DESC, fecha DESC, id DESC"
    params: list[Any] = []
    if limite is not None:
        sql += " LIMIT ?"
        params.append(int(limite))
    if desplazamiento:
        sql += " OFFSET ?"
        params.append(int(desplazamiento))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_fuente_rss(f) for f in filas]


def contar_fuentes_rss() -> int:
    """Total de fuentes RSS (para el `total` de paginacion)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT COUNT(*) AS n FROM fuentes_rss").fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_fuente_rss(fuente_id: str) -> dict[str, Any] | None:
    """Una fuente RSS por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_FUENTE_RSS} WHERE id = ?", (fuente_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_fuente_rss(fila) if fila is not None else None


def crear_fuente_rss(
    nombre: str,
    url: str,
    marca: str = "",
    *,
    incluir: str = "",
    excluir: str = "",
    redes_def: str = "",
    propia: bool = False,
    categoria: str = "",
    prioridad: int = 0,
    intervalo_min: int = 0,
) -> dict[str, Any]:
    """Crea una fuente RSS (activa, salud vacia) y la devuelve.

    `categoria`/`prioridad`/`intervalo_min` alimentan la planificación del motor de ingesta
    (Ola A); `proximo_sondeo` nace '' para que el primer barrido la sondee de inmediato.
    """
    # Microsegundos (no segundos): el listado ordena por `creado DESC` y dos fuentes creadas
    # en el mismo segundo empataban, dejando el orden al `id` (uuid aleatorio) -> test flaky.
    ahora = datetime.now().isoformat(timespec="microseconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "url": url or "",
        "marca": marca or "",
        "fecha": date.today().isoformat(),
        "activo": 1,
        "incluir": incluir or "",
        "excluir": excluir or "",
        "redes_def": redes_def or "",
        "ultima_actualizacion": "",
        "ultimo_error": "",
        "ultimo_conteo": 0,
        "propia": 1 if propia else 0,
        "intervalo_min": int(intervalo_min or 0),
        "categoria": categoria or "",
        "prioridad": int(prioridad or 0),
        "proximo_sondeo": "",
        "errores_seguidos": 0,
        "pausado_hasta": "",
        "desactivado_auto": 0,
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_FUENTE_RSS)
        # Sin ON CONFLICT: se permite la MISMA URL en varias fuentes (distinta marca/filtros/
        # nombre). Ver nota en `_INDICES_UNICOS_IDEMPOTENCIA`.
        con.execute(
            f"INSERT INTO fuentes_rss ({', '.join(_COLS_FUENTE_RSS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_FUENTE_RSS),
        )
        con.commit()
    finally:
        con.close()
    return obtener_fuente_rss(fila["id"]) or _fila_a_fuente_rss(fila)


def actualizar_fuente_rss(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una fuente (nombre/url/marca/activo/incluir/excluir/redes_def)."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_FUENTE_RSS}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if "propia" in cambios:
        cambios["propia"] = 1 if cambios["propia"] else 0
    if "desactivado_auto" in cambios:
        cambios["desactivado_auto"] = 1 if cambios["desactivado_auto"] else 0
    if not cambios:
        return obtener_fuente_rss(fuente_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), fuente_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE fuentes_rss SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_fuente_rss(fuente_id)


def registrar_salud_fuente_rss(fuente_id: str, *, conteo: int, error: str = "") -> None:
    """Anota la salud de una fuente (fecha de hoy + conteo + error). Best-effort."""
    con = _conectar()
    try:
        con.execute(
            "UPDATE fuentes_rss SET ultima_actualizacion = ?, ultimo_conteo = ?, "
            "ultimo_error = ? WHERE id = ?",
            (date.today().isoformat(), int(conteo), error or "", fuente_id),
        )
        con.commit()
    finally:
        con.close()


def borrar_fuente_rss(fuente_id: str) -> bool:
    """Borra una fuente RSS y sus items vistos; True si existia, False si no."""
    con = _conectar()
    try:
        con.execute("DELETE FROM rss_items_vistos WHERE fuente_id = ?", (fuente_id,))
        cur = con.execute("DELETE FROM fuentes_rss WHERE id = ?", (fuente_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def marcar_item(fuente_id: str, clave: str, usado: bool) -> None:
    """Marca/desmarca un item de una fuente como usado (idempotente).

    NO exige que la fuente exista (paridad con el file-backed): es una tabla de claves
    vistas sin FK. `usado=True` inserta (ON CONFLICT DO NOTHING); `usado=False` borra.
    """
    con = _conectar()
    try:
        if usado:
            con.execute(
                "INSERT INTO rss_items_vistos (fuente_id, clave) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING",
                (fuente_id, clave),
            )
        else:
            con.execute(
                "DELETE FROM rss_items_vistos WHERE fuente_id = ? AND clave = ?",
                (fuente_id, clave),
            )
        con.commit()
    finally:
        con.close()


def claves_vistas(fuente_id: str) -> set[str]:
    """Conjunto de claves ya marcadas como usadas para una fuente (vacio si ninguna)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT clave FROM rss_items_vistos WHERE fuente_id = ?", (fuente_id,)
        ).fetchall()
    finally:
        con.close()
    return {f["clave"] for f in filas}


# --------------------------------------------------------------------------- #
# MOTOR DE INGESTA PERSISTENTE (Ola A): archivo a nivel de artículo            #
# --------------------------------------------------------------------------- #
# `noticias_items` es el ARCHIVO: una fila por artículo de feed, persistido una vez (dedup por
# (fuente_id, clave)). Lo alimenta el `ingesta_daemon` en background; el Radar/Plan y la UI
# leen de aqui. El bulk-insert usa `ON CONFLICT DO NOTHING` sobre el indice unico, asi
# re-ingerir el mismo artículo es inofensivo. La planificación de feeds (`feeds_vencidos`,
# `registrar_sondeo_feed`) vive en las columnas de `fuentes_rss` (mismas conexiones).

_COLS_NOTICIA_ITEM: tuple[str, ...] = (
    "id",
    "fuente_id",
    "fuente_nombre",
    "categoria",
    "marca",
    "titulo",
    "resumen",
    "url",
    "url_canonica",
    "idioma",
    "autor",
    "imagen",
    "publicado_en",
    "capturado_en",
    "clave",
    "cluster_id",
    "senal",
    "geo",
    "estado",
    "contenido_id",
    "creado",
)
_SELECT_NOTICIA_ITEM = f"SELECT {', '.join(_COLS_NOTICIA_ITEM)} FROM noticias_items"
# Estados validos de un item de archivo.
ESTADOS_NOTICIA_ITEM: tuple[str, ...] = ("nuevo", "usado", "descartado")


def _fila_a_noticia_item(fila: Any) -> dict[str, Any]:
    """Fila de `noticias_items` -> dict publico (snake_case, tipos saneados)."""
    return {
        "id": fila["id"],
        "fuente_id": fila["fuente_id"] or "",
        "fuente_nombre": fila["fuente_nombre"] or "",
        "categoria": fila["categoria"] or "",
        "marca": fila["marca"] or "",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "url": fila["url"] or "",
        "url_canonica": fila["url_canonica"] or "",
        "idioma": fila["idioma"] or "",
        "autor": fila["autor"] or "",
        "imagen": fila["imagen"] or "",
        "publicado_en": fila["publicado_en"] or "",
        "capturado_en": fila["capturado_en"] or "",
        "clave": fila["clave"] or "",
        "cluster_id": fila["cluster_id"] or "",
        "senal": int(fila["senal"] or 0),
        "geo": fila["geo"] or "",
        "estado": fila["estado"] or "nuevo",
        "contenido_id": fila["contenido_id"] or "",
        "creado": fila["creado"] or "",
    }


def crear_noticias_items(items: list[dict[str, Any]]) -> int:
    """Inserta en bloque items de archivo; ignora duplicados ((fuente_id, clave)).

    Cada dict debe traer al menos `clave` (sin ella no hay identidad estable: se omite). Los
    campos ausentes caen a su default. Devuelve cuántas filas se INSERTARON realmente
    (`ON CONFLICT DO NOTHING` no cuenta los duplicados). Idempotente: re-ingerir es inofensivo.
    """
    candidatos = [it for it in items if (it.get("clave") or "").strip()]
    if not candidatos:
        return 0
    ahora = datetime.now(UTC).isoformat()
    marcadores = ", ".join("?" for _ in _COLS_NOTICIA_ITEM)
    insertadas = 0
    con = _conectar()
    try:
        for it in candidatos:
            fila = {
                "id": it.get("id") or uuid.uuid4().hex[:12],
                "fuente_id": it.get("fuente_id") or "",
                "fuente_nombre": it.get("fuente_nombre") or "",
                "categoria": it.get("categoria") or "",
                "marca": it.get("marca") or "",
                "titulo": it.get("titulo") or "",
                "resumen": it.get("resumen") or "",
                "url": it.get("url") or "",
                "url_canonica": it.get("url_canonica") or "",
                "idioma": it.get("idioma") or "",
                "autor": it.get("autor") or "",
                "imagen": it.get("imagen") or "",
                "publicado_en": it.get("publicado_en") or "",
                "capturado_en": it.get("capturado_en") or ahora,
                "clave": (it.get("clave") or "").strip(),
                "cluster_id": it.get("cluster_id") or "",
                "senal": int(it.get("senal") or 0),
                "geo": it.get("geo") or "",
                "estado": it.get("estado") or "nuevo",
                "contenido_id": it.get("contenido_id") or "",
                "creado": it.get("creado") or ahora,
            }
            cur = con.execute(
                f"INSERT INTO noticias_items ({', '.join(_COLS_NOTICIA_ITEM)}) "
                f"VALUES ({marcadores}) "
                "ON CONFLICT (fuente_id, clave) DO NOTHING",
                tuple(fila[col] for col in _COLS_NOTICIA_ITEM),
            )
            if cur.rowcount and cur.rowcount > 0:
                insertadas += 1
        con.commit()
    finally:
        con.close()
    return insertadas


def listar_noticias_items(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    desde: str | None = None,
    q: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Items de archivo filtrables, MÁS NUEVOS primero (`capturado_en` desc) + total.

    Filtros: `marca` ('' / None = todas), `categoria`, `desde` (ISO; `capturado_en >= desde`),
    `q` (subcadena insensible sobre titulo+resumen), `estado`. Devuelve `(items, total)` donde
    `total` cuenta los que pasan los filtros (para la paginación), no solo la página.
    """
    condiciones: list[str] = []
    params: list[Any] = []
    if marca:
        condiciones.append("marca = ?")
        params.append(marca)
    if categoria:
        condiciones.append("categoria = ?")
        params.append(categoria)
    if desde:
        condiciones.append("capturado_en >= ?")
        params.append(desde)
    if estado:
        condiciones.append("estado = ?")
        params.append(estado)
    if q and q.strip():
        condiciones.append("(LOWER(titulo) LIKE ? OR LOWER(resumen) LIKE ?)")
        patron = f"%{q.strip().lower()}%"
        params.extend([patron, patron])
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    sql = (
        f"{_SELECT_NOTICIA_ITEM}{where} "
        "ORDER BY capturado_en DESC, creado DESC, id DESC LIMIT ? OFFSET ?"
    )
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- condiciones de allowlist; valores parametrizados
            sql, (*params, max(1, int(limite)), max(0, int(desplazamiento)))
        ).fetchall()
        fila_total = con.execute(  # noqa: S608 -- idem
            f"SELECT COUNT(*) AS n FROM noticias_items{where}", tuple(params)
        ).fetchone()
    finally:
        con.close()
    total = int(fila_total["n"]) if fila_total is not None else 0
    return [_fila_a_noticia_item(f) for f in filas], total


def obtener_noticia_item(item_id: str) -> dict[str, Any] | None:
    """Un item de archivo por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_NOTICIA_ITEM} WHERE id = ?", (item_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_item(fila) if fila is not None else None


def actualizar_noticia_item(
    item_id: str,
    *,
    estado: str | None = None,
    contenido_id: str | None = None,
    cluster_id: str | None = None,
) -> dict[str, Any] | None:
    """Edita `estado` / `contenido_id` / `cluster_id` de un item (None si no existe)."""
    cambios: dict[str, Any] = {}
    if estado is not None:
        cambios["estado"] = estado
    if contenido_id is not None:
        cambios["contenido_id"] = contenido_id
    if cluster_id is not None:
        cambios["cluster_id"] = cluster_id
    if not cambios:
        return obtener_noticia_item(item_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), item_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE noticias_items SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_item(item_id)


def feeds_vencidos(ahora: str, limite: int) -> list[dict[str, Any]]:
    """Feeds RSS ACTIVOS listos para sondear AHORA (planificación del motor de ingesta).

    Un feed está vencido si `activo=1`, `proximo_sondeo` está vacío ('' = sondear ya) o es
    `<= ahora`, y NO está pausado por backoff (`pausado_hasta` vacío o `<= ahora`). Se ordena
    por `prioridad DESC` (las prioritarias primero) y luego por `proximo_sondeo` (las más
    atrasadas antes). `ahora` es un ISO comparable lexicográficamente con las columnas ISO.
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_FUENTE_RSS} WHERE activo = 1 "
            "AND (proximo_sondeo = '' OR proximo_sondeo <= ?) "
            "AND (pausado_hasta = '' OR pausado_hasta <= ?) "
            "ORDER BY prioridad DESC, proximo_sondeo ASC, creado ASC LIMIT ?",
            (ahora, ahora, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_fuente_rss(f) for f in filas]


def registrar_sondeo_feed(
    feed_id: str,
    *,
    conteo: int = 0,
    error: str = "",
    proximo_sondeo: str = "",
    errores_seguidos: int = 0,
    pausado_hasta: str = "",
    activo: bool | None = None,
    desactivado_auto: bool | None = None,
) -> None:
    """Anota el resultado de un sondeo de feed (salud + planificación). Best-effort.

    Actualiza la salud (`ultima_actualizacion`/`ultimo_conteo`/`ultimo_error`) y la
    planificación (`proximo_sondeo`/`errores_seguidos`/`pausado_hasta`) en una sola escritura.
    El daemon calcula los valores (intervalo por categoría, backoff exponencial) y los pasa ya
    resueltos; aquí solo se persisten.

    AUTO-DESACTIVADO (Ola D): si el daemon decide apagar el feed por errores seguidos, pasa
    `activo=False` + `desactivado_auto=True`; si se recupera, NO los pasa (None = no tocar). Solo
    se incluyen en el UPDATE cuando no son None, así un sondeo normal no pisa el `activo`.
    """
    asignaciones = [
        "ultima_actualizacion = ?", "ultimo_conteo = ?", "ultimo_error = ?",
        "proximo_sondeo = ?", "errores_seguidos = ?", "pausado_hasta = ?",
    ]
    params: list[Any] = [
        datetime.now(UTC).isoformat(),
        int(conteo),
        error or "",
        proximo_sondeo or "",
        int(errores_seguidos or 0),
        pausado_hasta or "",
    ]
    if activo is not None:
        asignaciones.append("activo = ?")
        params.append(1 if activo else 0)
    if desactivado_auto is not None:
        asignaciones.append("desactivado_auto = ?")
        params.append(1 if desactivado_auto else 0)
    params.append(feed_id)
    con = _conectar()
    try:
        con.execute(
            f"UPDATE fuentes_rss SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
    finally:
        con.close()


def resumen_cobertura() -> dict[str, Any]:
    """Resumen de salud del motor de ingesta (para `/api/noticias/cobertura`).

    Devuelve nº de feeds activos, feeds con error (último sondeo falló), items capturados en
    las últimas 24h por categoría, total de items, y el último sondeo registrado. Todo en una
    conexión, sin tocar la red.
    """
    hace_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    con = _conectar()
    try:
        feeds_activos = int(
            (con.execute(
                "SELECT COUNT(*) AS n FROM fuentes_rss WHERE activo = 1"
            ).fetchone() or {"n": 0})["n"] or 0
        )
        feeds_error = int(
            (con.execute(
                "SELECT COUNT(*) AS n FROM fuentes_rss WHERE activo = 1 AND ultimo_error <> ''"
            ).fetchone() or {"n": 0})["n"] or 0
        )
        total_items = int(
            (con.execute("SELECT COUNT(*) AS n FROM noticias_items").fetchone() or {"n": 0})["n"]
            or 0
        )
        filas_cat = con.execute(
            "SELECT categoria, COUNT(*) AS n FROM noticias_items "
            "WHERE capturado_en >= ? GROUP BY categoria ORDER BY n DESC",
            (hace_24h,),
        ).fetchall()
        fila_ultimo = con.execute(
            "SELECT MAX(ultima_actualizacion) AS u FROM fuentes_rss "
            "WHERE ultima_actualizacion <> ''"
        ).fetchone()
    finally:
        con.close()
    items_24h_por_categoria = {
        (f["categoria"] or "(sin categoría)"): int(f["n"] or 0) for f in filas_cat
    }
    return {
        "feeds_activos": feeds_activos,
        "feeds_con_error": feeds_error,
        "items_total": total_items,
        "items_24h": sum(items_24h_por_categoria.values()),
        "items_24h_por_categoria": items_24h_por_categoria,
        "ultimo_sondeo": (fila_ultimo["u"] if fila_ultimo is not None else "") or "",
    }


def salud_feeds(marca: str | None = None) -> list[dict[str, Any]]:
    """Salud por feed para `/api/noticias/salud` (Ola D): un dict por feed con frescura + items 24h.

    Para cada `fuentes_rss` (opcionalmente filtrada por `marca`) devuelve sus campos públicos
    MÁS dos agregados calculados de `noticias_items`:
      - `items_24h`: nº de items capturados en las últimas 24h con ese `fuente_id`.
      - `ultimo_item`: `MAX(capturado_en)` de ese feed ('' si nunca capturó nada).
    El daemon/API derivan `frescura_min` y `stale` de `ultimo_item`. Una sola conexión; sin red.
    Incluye feeds inactivos/auto-desactivados (la UI los muestra para reactivar).
    """
    hace_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    cond = ""
    params: list[Any] = []
    if marca:
        cond = " WHERE marca = ?"
        params.append(marca)
    con = _conectar()
    try:
        feeds = con.execute(  # noqa: S608 -- cond de allowlist; valor parametrizado
            f"{_SELECT_FUENTE_RSS}{cond} ORDER BY creado DESC, id DESC", tuple(params)
        ).fetchall()
        filas_24h = con.execute(
            "SELECT fuente_id, COUNT(*) AS n FROM noticias_items "
            "WHERE capturado_en >= ? GROUP BY fuente_id",
            (hace_24h,),
        ).fetchall()
        filas_ult = con.execute(
            "SELECT fuente_id, MAX(capturado_en) AS u FROM noticias_items GROUP BY fuente_id"
        ).fetchall()
    finally:
        con.close()
    por_24h = {f["fuente_id"]: int(f["n"] or 0) for f in filas_24h}
    por_ult = {f["fuente_id"]: (f["u"] or "") for f in filas_ult}
    salida: list[dict[str, Any]] = []
    for f in feeds:
        d = _fila_a_fuente_rss(f)
        d["items_24h"] = por_24h.get(d["id"], 0)
        d["ultimo_item"] = por_ult.get(d["id"], "")
        salida.append(d)
    return salida


def conteos_items_recientes(
    marca: str | None = None, *, horas: int = 24
) -> dict[str, dict[str, int]]:
    """Distribuciones de items recientes para `/salud`: por categoría y por idioma (Ola D).

    Cuenta los `noticias_items` capturados en las últimas `horas` (opcionalmente filtrados por
    `marca`) agrupados por `categoria` y por `idioma`. Sirve para `por_categoria`/`por_idioma`
    del resumen y para detectar HUECOS (categorías/regiones esperadas sin items frescos).
    Devuelve `{"por_categoria": {cat: n}, "por_idioma": {lang: n}}`.
    """
    desde = (datetime.now(UTC) - timedelta(hours=max(1, int(horas)))).isoformat()
    cond = "capturado_en >= ?"
    params: list[Any] = [desde]
    if marca:
        cond += " AND marca = ?"
        params.append(marca)
    con = _conectar()
    try:
        filas_cat = con.execute(  # noqa: S608 -- cond de allowlist; valores parametrizados
            f"SELECT categoria, COUNT(*) AS n FROM noticias_items WHERE {cond} "
            "GROUP BY categoria ORDER BY n DESC",
            tuple(params),
        ).fetchall()
        filas_idi = con.execute(  # noqa: S608 -- idem
            f"SELECT idioma, COUNT(*) AS n FROM noticias_items WHERE {cond} "
            "GROUP BY idioma ORDER BY n DESC",
            tuple(params),
        ).fetchall()
    finally:
        con.close()
    por_categoria = {
        (f["categoria"] or "(sin categoría)"): int(f["n"] or 0) for f in filas_cat
    }
    por_idioma = {(f["idioma"] or "(sin idioma)"): int(f["n"] or 0) for f in filas_idi}
    return {"por_categoria": por_categoria, "por_idioma": por_idioma}


# --- Clustering de HISTORIAS (Ola B): noticias_clusters -------------------- #
# Una historia = la misma noticia contada por varias fuentes y en el tiempo. El daemon de
# ingesta asigna `cluster_id` a los items recién insertados y `upsert`ea el cluster recalculado.
ESTADOS_NOTICIA_CLUSTER: tuple[str, ...] = ("nuevo", "usado", "descartado")

_COLS_NOTICIA_CLUSTER: tuple[str, ...] = (
    "id",
    "titulo",
    "resumen",
    "marca",
    "categoria",
    "geo",
    "clave",
    "n_items",
    "n_fuentes",
    "idiomas",
    "senal",
    "score",
    "breaking",
    "primer_visto",
    "ultimo_visto",
    "estado",
    "contenido_id",
    "verificacion",
    "titulo_es",
    "resumen_es",
    "titulo_original",
    "idioma",
    "traducido",
    "creado",
    "actualizado",
)
_SELECT_NOTICIA_CLUSTER = f"SELECT {', '.join(_COLS_NOTICIA_CLUSTER)} FROM noticias_clusters"
# Verificación por corroboración (Ola D): valores válidos de `noticias_clusters.verificacion`.
VERIFICACIONES_CLUSTER: tuple[str, ...] = ("corroborada", "unica_fuente", "dudosa")


def _fila_a_noticia_cluster(fila: Any) -> dict[str, Any]:
    """Fila de `noticias_clusters` -> dict publico (snake_case; `idiomas` deserializado)."""
    try:
        idiomas = json.loads(fila["idiomas"] or "[]")
        if not isinstance(idiomas, list):
            idiomas = []
    except (ValueError, TypeError):
        idiomas = []
    return {
        "id": fila["id"],
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "marca": fila["marca"] or "",
        "categoria": fila["categoria"] or "",
        "geo": fila["geo"] or "",
        "clave": fila["clave"] or "",
        "n_items": int(fila["n_items"] or 0),
        "n_fuentes": int(fila["n_fuentes"] or 0),
        "idiomas": idiomas,
        "senal": int(fila["senal"] or 0),
        "score": float(fila["score"] or 0.0),
        "breaking": int(fila["breaking"] or 0),
        "primer_visto": fila["primer_visto"] or "",
        "ultimo_visto": fila["ultimo_visto"] or "",
        "estado": fila["estado"] or "nuevo",
        "contenido_id": fila["contenido_id"] or "",
        # Auto-verificación por corroboración (Ola D).
        "verificacion": fila["verificacion"] or "unica_fuente",
        # Traducción completa de historias extranjeras (Ola D).
        "titulo_es": fila["titulo_es"] or "",
        "resumen_es": fila["resumen_es"] or "",
        "titulo_original": fila["titulo_original"] or "",
        "idioma": fila["idioma"] or "",
        "traducido": bool(fila["traducido"]),
        "creado": fila["creado"] or "",
        "actualizado": fila["actualizado"] or "",
    }


def upsert_noticia_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    """Crea o actualiza un cluster por `id` (idempotente). Devuelve el cluster persistido.

    Si falta `id`, lo genera. `idiomas` se serializa a JSON. `creado` se fija solo en el alta;
    `actualizado` siempre se sella al instante actual. Los agregados (`n_items`/`n_fuentes`/
    `senal`/`score`/`breaking`/`titulo`/...) los calcula el dominio (`clustering`) y aquí solo
    se persisten. `estado`/`contenido_id` NO se pisan en un upsert salvo que vengan en el dict.
    """
    ahora = datetime.now(UTC).isoformat()
    cid = (cluster.get("id") or "").strip() or uuid.uuid4().hex[:12]
    idiomas = cluster.get("idiomas") or []
    if not isinstance(idiomas, list):
        idiomas = []
    fila = {
        "id": cid,
        "titulo": (cluster.get("titulo") or "")[:300],
        "resumen": (cluster.get("resumen") or "")[:2000],
        "marca": cluster.get("marca") or "",
        "categoria": cluster.get("categoria") or "",
        "geo": cluster.get("geo") or "",
        "clave": cluster.get("clave") or "",
        "n_items": int(cluster.get("n_items") or 0),
        "n_fuentes": int(cluster.get("n_fuentes") or 0),
        "idiomas": json.dumps(idiomas, ensure_ascii=False),
        "senal": int(cluster.get("senal") or 0),
        "score": float(cluster.get("score") or 0.0),
        "breaking": int(cluster.get("breaking") or 0),
        "primer_visto": cluster.get("primer_visto") or "",
        "ultimo_visto": cluster.get("ultimo_visto") or "",
        "estado": cluster.get("estado") or "nuevo",
        "contenido_id": cluster.get("contenido_id") or "",
        # Verificación: la recalcula el clustering en cada upsert (sí entra al SET de conflicto).
        "verificacion": cluster.get("verificacion") or "unica_fuente",
        # Traducción: el ALTA la nace vacía; el paso de traducción la escribe aparte
        # (`marcar_cluster_traducido`). NO entra al SET de conflicto, así un recalc del cluster
        # NO pisa una traducción ya hecha (best-effort, persistente entre barridos).
        "titulo_es": cluster.get("titulo_es") or "",
        "resumen_es": cluster.get("resumen_es") or "",
        "titulo_original": cluster.get("titulo_original") or "",
        "idioma": cluster.get("idioma") or "",
        "traducido": 1 if cluster.get("traducido") else 0,
        "creado": cluster.get("creado") or ahora,
        "actualizado": ahora,
    }
    # En conflicto por id, actualiza casi todo MENOS `id`/`creado` y los campos de TRADUCCIÓN
    # (que escribe `marcar_cluster_traducido` y no deben perderse al recalcular el cluster).
    _NO_PISAR = ("id", "creado", "titulo_es", "resumen_es", "titulo_original", "idioma", "traducido")
    actualizables = [c for c in _COLS_NOTICIA_CLUSTER if c not in _NO_PISAR]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in actualizables)
    marcadores = ", ".join("?" for _ in _COLS_NOTICIA_CLUSTER)
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO noticias_clusters ({', '.join(_COLS_NOTICIA_CLUSTER)}) "
            f"VALUES ({marcadores}) "
            f"ON CONFLICT (id) DO UPDATE SET {set_clause}",  # noqa: S608 -- columnas de allowlist
            tuple(fila[c] for c in _COLS_NOTICIA_CLUSTER),
        )
        con.commit()
    finally:
        con.close()
    return obtener_noticia_cluster(cid) or _fila_a_noticia_cluster(fila)


def listar_noticia_clusters(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    desde: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Historias filtrables, MÁS RELEVANTES primero (`score` desc) + total.

    Filtros: `marca` ('' / None = todas), `categoria`, `desde` (ISO; `ultimo_visto >= desde`),
    `estado`. Orden `score DESC, ultimo_visto DESC`. Devuelve `(clusters, total)`.
    """
    condiciones: list[str] = []
    params: list[Any] = []
    if marca:
        condiciones.append("marca = ?")
        params.append(marca)
    if categoria:
        condiciones.append("categoria = ?")
        params.append(categoria)
    if desde:
        condiciones.append("ultimo_visto >= ?")
        params.append(desde)
    if estado:
        condiciones.append("estado = ?")
        params.append(estado)
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    sql = (
        f"{_SELECT_NOTICIA_CLUSTER}{where} "
        "ORDER BY score DESC, ultimo_visto DESC, id DESC LIMIT ? OFFSET ?"
    )
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- condiciones de allowlist; valores parametrizados
            sql, (*params, max(1, int(limite)), max(0, int(desplazamiento)))
        ).fetchall()
        fila_total = con.execute(  # noqa: S608 -- idem
            f"SELECT COUNT(*) AS n FROM noticias_clusters{where}", tuple(params)
        ).fetchone()
    finally:
        con.close()
    total = int(fila_total["n"]) if fila_total is not None else 0
    return [_fila_a_noticia_cluster(f) for f in filas], total


def obtener_noticia_cluster(cluster_id: str) -> dict[str, Any] | None:
    """Una historia por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_NOTICIA_CLUSTER} WHERE id = ?", (cluster_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_cluster(fila) if fila is not None else None


def actualizar_noticia_cluster(
    cluster_id: str,
    *,
    estado: str | None = None,
    contenido_id: str | None = None,
) -> dict[str, Any] | None:
    """Edita `estado` / `contenido_id` de una historia (None si no existe)."""
    cambios: dict[str, Any] = {}
    if estado is not None:
        cambios["estado"] = estado
    if contenido_id is not None:
        cambios["contenido_id"] = contenido_id
    if not cambios:
        return obtener_noticia_cluster(cluster_id)
    cambios["actualizado"] = datetime.now(UTC).isoformat()
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), cluster_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE noticias_clusters SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_cluster(cluster_id)


def clusters_recientes(ventana_h: int, marca: str | None = None) -> list[dict[str, Any]]:
    """Clusters cuya `ultimo_visto` cae dentro de la ventana reciente (para asignación).

    El daemon de ingesta carga estos para decidir a cuál unir un item nuevo (clustering
    incremental ACOTADO por la ventana: nunca re-cluster el archivo entero). Excluye los
    `descartado` (no se reabren). `marca` opcional acota a una marca. Orden `ultimo_visto` desc.
    """
    corte = (datetime.now(UTC) - timedelta(hours=max(1, int(ventana_h)))).isoformat()
    condiciones = ["ultimo_visto >= ?", "estado <> 'descartado'"]
    params: list[Any] = [corte]
    if marca:
        condiciones.append("marca = ?")
        params.append(marca)
    where = " WHERE " + " AND ".join(condiciones)
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- condiciones de allowlist; valores parametrizados
            f"{_SELECT_NOTICIA_CLUSTER}{where} ORDER BY ultimo_visto DESC",
            tuple(params),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_cluster(f) for f in filas]


def clusters_extranjeros_sin_traducir(
    ventana_h: int, *, min_score: float = 0.0, limite: int = 40
) -> list[dict[str, Any]]:
    """Clusters EXTRANJEROS recientes aún sin traducir (Ola D), para el paso de traducción.

    Selecciona clusters con `traducido = 0`, `idioma` no vacío y distinto de español
    (no empieza por 'es'), `score >= min_score`, `ultimo_visto` dentro de la ventana, y estado
    distinto de `descartado`. MÁS RELEVANTES primero (`score DESC`), `limite` acota el lote por
    barrido (el backlog se procesa en barridos sucesivos; sin tope artificial). PURA salvo I/O.
    """
    corte = (datetime.now(UTC) - timedelta(hours=max(1, int(ventana_h)))).isoformat()
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_NOTICIA_CLUSTER} WHERE traducido = 0 AND idioma <> '' "
            "AND idioma NOT LIKE 'es%' AND score >= ? AND ultimo_visto >= ? "
            "AND estado <> 'descartado' "
            "ORDER BY score DESC, ultimo_visto DESC LIMIT ?",
            (float(min_score), corte, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_cluster(f) for f in filas]


def marcar_cluster_traducido(
    cluster_id: str,
    *,
    titulo_es: str,
    resumen_es: str,
    titulo_original: str = "",
) -> dict[str, Any] | None:
    """Guarda la traducción ES de un cluster y lo marca `traducido=1` (Ola D). Best-effort.

    Conserva `idioma` (ya fijado por el clustering) y guarda el `titulo_original` para mostrar
    "traducido de {idioma}". No toca los agregados ni el estado. None si el cluster no existe.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE noticias_clusters SET titulo_es = ?, resumen_es = ?, titulo_original = ?, "
            "traducido = 1, actualizado = ? WHERE id = ?",
            (
                (titulo_es or "")[:300],
                (resumen_es or "")[:2000],
                (titulo_original or "")[:300],
                datetime.now(UTC).isoformat(),
                cluster_id,
            ),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_cluster(cluster_id)


def items_de_cluster(cluster_id: str, *, limite: int = 200) -> list[dict[str, Any]]:
    """Items de archivo de una historia, MÁS RECIENTES primero (`capturado_en` desc)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_NOTICIA_ITEM} WHERE cluster_id = ? "
            "ORDER BY capturado_en DESC, creado DESC, id DESC LIMIT ?",
            (cluster_id, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_item(f) for f in filas]


def items_sin_cluster(desde: str, limite: int) -> list[dict[str, Any]]:
    """Items de archivo recientes SIN cluster asignado (para el paso de clustering del daemon).

    Filtra `cluster_id = ''` y `capturado_en >= desde` (ventana reciente: clustering acotado,
    nunca el archivo entero). MÁS ANTIGUOS primero, para agrupar en orden cronológico (el
    primero de una historia funda el cluster; los siguientes se unen). `limite` acota el trabajo.
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_NOTICIA_ITEM} WHERE cluster_id = '' AND capturado_en >= ? "
            "ORDER BY capturado_en ASC, creado ASC, id ASC LIMIT ?",
            (desde, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_item(f) for f in filas]


def asignar_cluster_item(item_id: str, cluster_id: str) -> None:
    """Fija `noticias_items.cluster_id` de un item (best-effort, una escritura)."""
    con = _conectar()
    try:
        con.execute(
            "UPDATE noticias_items SET cluster_id = ? WHERE id = ?",
            (cluster_id, item_id),
        )
        con.commit()
    finally:
        con.close()


def marcar_items_cluster_usados(cluster_id: str, contenido_id: str) -> None:
    """Marca TODOS los items de un cluster como `usado` + enlaza el `contenido_id` (una escritura)."""
    con = _conectar()
    try:
        con.execute(
            "UPDATE noticias_items SET estado = 'usado', contenido_id = ? "
            "WHERE cluster_id = ? AND estado <> 'descartado'",
            (contenido_id, cluster_id),
        )
        con.commit()
    finally:
        con.close()


# --- Tipos de fuente (catálogo) ------------------------------------------- #
# `fuentes_rss` es la ÚNICA tabla de fuentes (la fuente de verdad del motor de ingesta); la
# API la presenta como catálogo de tipo 'rss'. Esta allowlist deja la puerta a otros tipos de
# aportación (idea/enlace/...) que hoy producen items del tablero, no filas de fuente.
_TIPOS_FUENTE: tuple[str, ...] = ("rss", "api", "galeria", "idea", "interna")


# --- Fuentes de algoritmo (inteligencia de plataforma) --------------------- #
# Mismo patron que `fuentes_rss` pero con `plataforma`/`tipo` en vez de marca/filtros: son
# fuentes de INDUSTRIA (blogs oficiales + agregadores), no de contenido de marca.
_COLS_FUENTE_ALGO = (
    "id", "nombre", "url", "plataforma", "tipo", "activo",
    "ultima_actualizacion", "ultimo_error", "ultimo_conteo", "creado",
)
_SELECT_FUENTE_ALGO = f"SELECT {', '.join(_COLS_FUENTE_ALGO)} FROM fuentes_algoritmo"
_CAMPOS_EDITABLES_FUENTE_ALGO: tuple[str, ...] = ("nombre", "url", "plataforma", "tipo", "activo")


def _fila_a_fuente_algo(fila: Any) -> dict[str, Any]:
    """Fila de `fuentes_algoritmo` -> dict publico (sin `creado`; `activo` bool)."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"] or "",
        "url": fila["url"] or "",
        "plataforma": fila["plataforma"] or "general",
        "tipo": fila["tipo"] or "agregador",
        "activo": bool(fila["activo"]),
        "ultima_actualizacion": fila["ultima_actualizacion"] or "",
        "ultimo_error": fila["ultimo_error"] or "",
        "ultimo_conteo": int(fila["ultimo_conteo"] or 0),
    }


def listar_fuentes_algoritmo() -> list[dict[str, Any]]:
    """Fuentes de algoritmo (mas recientes primero)."""
    con = _conectar()
    try:
        filas = con.execute(
            _SELECT_FUENTE_ALGO + " ORDER BY creado DESC, id DESC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_fuente_algo(f) for f in filas]


def contar_fuentes_algoritmo() -> int:
    """Total de fuentes de algoritmo (para decidir si sembrar las semilla)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT COUNT(*) AS n FROM fuentes_algoritmo").fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_fuente_algoritmo(fuente_id: str) -> dict[str, Any] | None:
    """Una fuente de algoritmo por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_FUENTE_ALGO} WHERE id = ?", (fuente_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_fuente_algo(fila) if fila is not None else None


def crear_fuente_algoritmo(
    nombre: str, url: str, *, plataforma: str = "general", tipo: str = "agregador"
) -> dict[str, Any]:
    """Crea una fuente de algoritmo (activa, salud vacia) y la devuelve."""
    ahora = datetime.now().isoformat(timespec="microseconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "url": url or "",
        "plataforma": plataforma or "general",
        "tipo": tipo or "agregador",
        "activo": 1,
        "ultima_actualizacion": "",
        "ultimo_error": "",
        "ultimo_conteo": 0,
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_FUENTE_ALGO)
        con.execute(
            f"INSERT INTO fuentes_algoritmo ({', '.join(_COLS_FUENTE_ALGO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_FUENTE_ALGO),
        )
        con.commit()
    finally:
        con.close()
    return obtener_fuente_algoritmo(fila["id"]) or _fila_a_fuente_algo(fila)


def actualizar_fuente_algoritmo(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una fuente (nombre/url/plataforma/tipo/activo)."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_FUENTE_ALGO}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_fuente_algoritmo(fuente_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), fuente_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE fuentes_algoritmo SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_fuente_algoritmo(fuente_id)


def registrar_salud_fuente_algoritmo(fuente_id: str, *, conteo: int, error: str = "") -> None:
    """Anota la salud de una fuente de algoritmo (fecha de hoy + conteo + error)."""
    con = _conectar()
    try:
        con.execute(
            "UPDATE fuentes_algoritmo SET ultima_actualizacion = ?, ultimo_conteo = ?, "
            "ultimo_error = ? WHERE id = ?",
            (date.today().isoformat(), int(conteo), error or "", fuente_id),
        )
        con.commit()
    finally:
        con.close()


def borrar_fuente_algoritmo(fuente_id: str) -> bool:
    """Borra una fuente de algoritmo y sus noticias; True si existia."""
    con = _conectar()
    try:
        con.execute("DELETE FROM noticias_algoritmo WHERE fuente_id = ?", (fuente_id,))
        cur = con.execute("DELETE FROM fuentes_algoritmo WHERE id = ?", (fuente_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Noticias de algoritmo (items ingeridos + clasificados) ---------------- #
_COLS_NOTICIA_ALGO = (
    "id", "fuente_id", "fuente_nombre", "plataforma", "tipo", "titulo", "resumen",
    "enlace", "fecha", "clave", "importancia", "nivel", "senales", "es_cambio",
    "aplicada", "archivada", "sugerida", "creado",
)
_SELECT_NOTICIA_ALGO = f"SELECT {', '.join(_COLS_NOTICIA_ALGO)} FROM noticias_algoritmo"


def _fila_a_noticia_algo(fila: Any) -> dict[str, Any]:
    """Fila de `noticias_algoritmo` -> dict publico (`senales` como lista; flags bool)."""
    try:
        senales = json.loads(fila["senales"] or "[]")
    except (json.JSONDecodeError, ValueError, TypeError):
        senales = []
    return {
        "id": fila["id"],
        "fuente_id": fila["fuente_id"] or "",
        "fuente_nombre": fila["fuente_nombre"] or "",
        "plataforma": fila["plataforma"] or "general",
        "tipo": fila["tipo"] or "agregador",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "enlace": fila["enlace"] or "",
        "fecha": fila["fecha"] or "",
        "clave": fila["clave"] or "",
        "importancia": int(fila["importancia"] or 0),
        "nivel": fila["nivel"] or "baja",
        "senales": senales if isinstance(senales, list) else [],
        "es_cambio": bool(fila["es_cambio"]),
        "aplicada": bool(fila["aplicada"]),
        "archivada": bool(fila["archivada"]),
        "sugerida": bool(fila["sugerida"]),
        "creado": fila["creado"] or "",
    }


def guardar_noticia_algoritmo(noticia: dict[str, Any]) -> str:
    """Inserta o ACTUALIZA una noticia clasificada (dedup por fuente_id+clave).

    Recibe una noticia YA clasificada (la clasificacion vive en `algoritmos.py`, no aqui).
    Si ya existe (misma fuente+clave) refresca la clasificacion y los textos, pero PRESERVA
    `id`/`creado` y las marcas humanas (`aplicada`/`archivada`). Devuelve "insertada" o
    "actualizada". Exige `clave` no vacia (sin identidad estable no se puede deduplicar)."""
    clave = (noticia.get("clave") or "").strip()
    fuente_id = noticia.get("fuente_id") or ""
    if not clave:
        return "omitida"
    senales = noticia.get("senales") or []
    senales_json = json.dumps(senales) if isinstance(senales, list) else "[]"
    con = _conectar()
    try:
        existente = con.execute(
            "SELECT id FROM noticias_algoritmo WHERE fuente_id = ? AND clave = ?",
            (fuente_id, clave),
        ).fetchone()
        if existente is not None:
            con.execute(
                "UPDATE noticias_algoritmo SET fuente_nombre = ?, plataforma = ?, tipo = ?, "
                "titulo = ?, resumen = ?, enlace = ?, fecha = ?, importancia = ?, nivel = ?, "
                "senales = ?, es_cambio = ? WHERE id = ?",
                (
                    noticia.get("fuente_nombre") or "",
                    noticia.get("plataforma") or "general",
                    noticia.get("tipo") or "agregador",
                    noticia.get("titulo") or "",
                    noticia.get("resumen") or "",
                    noticia.get("enlace") or "",
                    noticia.get("fecha") or "",
                    int(noticia.get("importancia") or 0),
                    noticia.get("nivel") or "baja",
                    senales_json,
                    1 if noticia.get("es_cambio") else 0,
                    existente["id"],
                ),
            )
            con.commit()
            return "actualizada"
        fila = {
            "id": uuid.uuid4().hex[:12],
            "fuente_id": fuente_id,
            "fuente_nombre": noticia.get("fuente_nombre") or "",
            "plataforma": noticia.get("plataforma") or "general",
            "tipo": noticia.get("tipo") or "agregador",
            "titulo": noticia.get("titulo") or "",
            "resumen": noticia.get("resumen") or "",
            "enlace": noticia.get("enlace") or "",
            "fecha": noticia.get("fecha") or "",
            "clave": clave,
            "importancia": int(noticia.get("importancia") or 0),
            "nivel": noticia.get("nivel") or "baja",
            "senales": senales_json,
            "es_cambio": 1 if noticia.get("es_cambio") else 0,
            "aplicada": 0,
            "archivada": 0,
            "sugerida": 0,
            "creado": datetime.now().isoformat(timespec="microseconds"),
        }
        marcadores = ", ".join("?" for _ in _COLS_NOTICIA_ALGO)
        con.execute(
            f"INSERT INTO noticias_algoritmo ({', '.join(_COLS_NOTICIA_ALGO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_NOTICIA_ALGO),
        )
        con.commit()
        return "insertada"
    finally:
        con.close()


def listar_noticias_algoritmo(
    *,
    plataforma: str | None = None,
    nivel: str | None = None,
    solo_cambios: bool = False,
    solo_no_sugeridas: bool = False,
    incluir_archivadas: bool = False,
    limite: int | None = None,
) -> list[dict[str, Any]]:
    """Noticias de algoritmo ordenadas por importancia (luego fecha, luego ingesta)."""
    sql = _SELECT_NOTICIA_ALGO
    condiciones: list[str] = []
    params: list[Any] = []
    if not incluir_archivadas:
        condiciones.append("archivada = 0")
    if plataforma:
        condiciones.append("plataforma = ?")
        params.append(plataforma)
    if nivel:
        condiciones.append("nivel = ?")
        params.append(nivel)
    if solo_cambios:
        condiciones.append("es_cambio = 1")
    if solo_no_sugeridas:
        condiciones.append("sugerida = 0")
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY importancia DESC, fecha DESC, creado DESC, id DESC"
    if limite is not None:
        sql += " LIMIT ?"
        params.append(int(limite))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()  # noqa: S608 -- condiciones de allowlist
    finally:
        con.close()
    return [_fila_a_noticia_algo(f) for f in filas]


def obtener_noticia_algoritmo(noticia_id: str) -> dict[str, Any] | None:
    """Una noticia de algoritmo por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_NOTICIA_ALGO} WHERE id = ?", (noticia_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_algo(fila) if fila is not None else None


def marcar_noticia_algoritmo(
    noticia_id: str,
    *,
    aplicada: bool | None = None,
    archivada: bool | None = None,
    sugerida: bool | None = None,
) -> dict[str, Any] | None:
    """Marca una noticia como aplicada-a-biblioteca / archivada / ya-sugerida (None si no existe)."""
    cambios: dict[str, Any] = {}
    if aplicada is not None:
        cambios["aplicada"] = 1 if aplicada else 0
    if archivada is not None:
        cambios["archivada"] = 1 if archivada else 0
    if sugerida is not None:
        cambios["sugerida"] = 1 if sugerida else 0
    if not cambios:
        return obtener_noticia_algoritmo(noticia_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), noticia_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE noticias_algoritmo SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_algoritmo(noticia_id)


# --- Sugerencias editoriales (generadas por el job diario) ----------------- #
_COLS_SUGERENCIA_EDITORIAL = (
    "id", "plataforma", "tipo", "titulo", "detalle", "ficha_id", "noticia_ids", "estado", "creado",
)
_SELECT_SUGERENCIA_EDITORIAL = (
    f"SELECT {', '.join(_COLS_SUGERENCIA_EDITORIAL)} FROM sugerencias_editoriales"
)
ESTADOS_SUGERENCIA_EDITORIAL = ("nueva", "aplicada", "descartada")


def _fila_a_sugerencia_editorial(fila: Any) -> dict[str, Any]:
    """Fila de `sugerencias_editoriales` -> dict publico (`noticia_ids` como lista)."""
    try:
        ids = json.loads(fila["noticia_ids"] or "[]")
    except (json.JSONDecodeError, ValueError, TypeError):
        ids = []
    return {
        "id": fila["id"],
        "plataforma": fila["plataforma"] or "general",
        "tipo": fila["tipo"] or "editorial",
        "titulo": fila["titulo"] or "",
        "detalle": fila["detalle"] or "",
        "ficha_id": fila["ficha_id"] or "",
        "noticia_ids": ids if isinstance(ids, list) else [],
        "estado": fila["estado"] or "nueva",
        "creado": fila["creado"] or "",
    }


def crear_sugerencia_editorial(
    *,
    plataforma: str,
    tipo: str,
    titulo: str,
    detalle: str,
    ficha_id: str = "",
    noticia_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Crea una sugerencia editorial (estado 'nueva') y la devuelve."""
    fila = {
        "id": uuid.uuid4().hex[:12],
        "plataforma": plataforma or "general",
        "tipo": tipo or "editorial",
        "titulo": titulo or "",
        "detalle": detalle or "",
        "ficha_id": ficha_id or "",
        "noticia_ids": json.dumps(noticia_ids or []),
        "estado": "nueva",
        "creado": datetime.now().isoformat(timespec="microseconds"),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_SUGERENCIA_EDITORIAL)
        con.execute(
            f"INSERT INTO sugerencias_editoriales ({', '.join(_COLS_SUGERENCIA_EDITORIAL)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_SUGERENCIA_EDITORIAL),
        )
        con.commit()
    finally:
        con.close()
    return obtener_sugerencia_editorial(fila["id"]) or _fila_a_sugerencia_editorial(fila)


def listar_sugerencias_editoriales(
    *, estado: str | None = None, limite: int | None = None
) -> list[dict[str, Any]]:
    """Sugerencias editoriales (mas recientes primero), filtrables por estado."""
    sql = _SELECT_SUGERENCIA_EDITORIAL
    params: list[Any] = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    sql += " ORDER BY creado DESC, id DESC"
    if limite is not None:
        sql += " LIMIT ?"
        params.append(int(limite))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()  # noqa: S608 -- estado de allowlist
    finally:
        con.close()
    return [_fila_a_sugerencia_editorial(f) for f in filas]


def contar_sugerencias_editoriales(*, estado: str | None = None) -> int:
    """Total de sugerencias editoriales (para el contador del panel), filtrable por estado."""
    sql = "SELECT COUNT(*) AS n FROM sugerencias_editoriales"
    params: list[Any] = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    con = _conectar()
    try:
        fila = con.execute(sql, tuple(params)).fetchone()  # noqa: S608 -- estado de allowlist
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_sugerencia_editorial(sugerencia_id: str) -> dict[str, Any] | None:
    """Una sugerencia editorial por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_SUGERENCIA_EDITORIAL} WHERE id = ?", (sugerencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_sugerencia_editorial(fila) if fila is not None else None


def actualizar_estado_sugerencia_editorial(
    sugerencia_id: str, estado: str
) -> dict[str, Any] | None:
    """Cambia el estado de una sugerencia (nueva/aplicada/descartada). None si no existe."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE sugerencias_editoriales SET estado = ? WHERE id = ?",
            (estado, sugerencia_id),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_sugerencia_editorial(sugerencia_id)


# --- Grupos de hashtags ---------------------------------------------------- #
# `hashtags` se almacena como JSON serializado; el dict publico lo devuelve como lista de
# strings (paridad con `ficheros._parsear_grupo`, que NO incluye `creado`/`fecha_creacion`).
_COLS_GRUPO_HASHTAGS = ("id", "nombre", "marca", "hashtags", "creado")
_SELECT_GRUPO_HASHTAGS = f"SELECT {', '.join(_COLS_GRUPO_HASHTAGS)} FROM grupos_hashtags"


def _normalizar_hashtags(valor: Any) -> list[str]:
    """Lista de strings desde una lista o un JSON serializado (degrada a [])."""
    if isinstance(valor, str):
        try:
            valor = json.loads(valor) if valor.strip() else []
        except (ValueError, TypeError):
            return []
    if not isinstance(valor, list):
        return []
    return [t for t in valor if isinstance(t, str)]


def _fila_a_grupo_hashtags(fila: Any) -> dict[str, Any]:
    """Fila de `grupos_hashtags` -> dict publico (`hashtags` lista; sin `creado`)."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"] or "",
        "marca": fila["marca"] or "",
        "hashtags": _normalizar_hashtags(fila["hashtags"]),
    }


def listar_grupos_hashtags(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Grupos de hashtags (mas recientes primero), con paginacion opcional."""
    sql = _SELECT_GRUPO_HASHTAGS + " ORDER BY creado DESC, id DESC"
    params: list[Any] = []
    if limite is not None:
        sql += " LIMIT ?"
        params.append(int(limite))
    if desplazamiento:
        sql += " OFFSET ?"
        params.append(int(desplazamiento))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_grupo_hashtags(f) for f in filas]


def contar_grupos_hashtags() -> int:
    """Total de grupos de hashtags (para el `total` de paginacion)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT COUNT(*) AS n FROM grupos_hashtags").fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    """Un grupo de hashtags por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_GRUPO_HASHTAGS} WHERE id = ?", (grupo_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_grupo_hashtags(fila) if fila is not None else None


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    """Crea un grupo de hashtags y lo devuelve."""
    tags = _normalizar_hashtags(hashtags or [])
    grupo_id = uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        # ON CONFLICT (nombre, marca) DO NOTHING: idempotente frente a un alta repetida del
        # mismo grupo en la misma marca (mismo patron que `rota_franjas`). Requiere el indice
        # unico `idx_grupos_hashtags_uniq` (lo crea `_crear_indices_unicos_idempotencia`);
        # PRECONDICION: una BD con duplicados previos impide crearlo -> limpiar antes.
        con.execute(
            "INSERT INTO grupos_hashtags (id, nombre, marca, hashtags, creado) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (nombre, marca) DO NOTHING",
            (
                grupo_id,
                nombre or "",
                marca or "",
                json.dumps(tags, ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        con.commit()
    finally:
        con.close()
    return {"id": grupo_id, "nombre": nombre or "", "marca": marca or "", "hashtags": tags}


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente un grupo (nombre/marca/hashtags); None si no existe."""
    editables = ("nombre", "marca", "hashtags")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if "hashtags" in cambios:
        cambios["hashtags"] = json.dumps(
            _normalizar_hashtags(cambios["hashtags"]), ensure_ascii=False
        )
    if not cambios:
        return obtener_grupo_hashtags(grupo_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), grupo_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE grupos_hashtags SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_grupo_hashtags(grupo_id)


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    """Borra un grupo de hashtags; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM grupos_hashtags WHERE id = ?", (grupo_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Franjas editoriales --------------------------------------------------- #
# Dict publico (paridad con `ficheros._leer_franjas_marca`): `id, marca, red, dia_semana, hora`.
_COLS_FRANJA_EDIT = ("id", "marca", "red", "dia_semana", "hora")
_SELECT_FRANJA_EDIT = f"SELECT {', '.join(_COLS_FRANJA_EDIT)} FROM franjas_editoriales"


def _fila_a_franja(fila: Any) -> dict[str, Any]:
    """Fila de `franjas_editoriales` -> dict publico."""
    return {
        "id": fila["id"],
        "marca": fila["marca"] or "",
        "red": fila["red"] or "",
        "dia_semana": int(fila["dia_semana"] or 0),
        "hora": fila["hora"] or "",
    }


def listar_franjas() -> list[dict[str, Any]]:
    """Todas las franjas editoriales, ordenadas por dia/hora/id (determinista)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_FRANJA_EDIT} ORDER BY dia_semana ASC, hora ASC, id ASC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_franja(f) for f in filas]


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    """Crea una franja editorial y la devuelve."""
    franja = {
        "id": uuid.uuid4().hex[:12],
        "marca": marca or "",
        "red": red or "",
        "dia_semana": int(dia_semana),
        "hora": hora or "",
    }
    con = _conectar()
    try:
        # ON CONFLICT (marca, red, dia_semana, hora) DO NOTHING: idempotente frente a un alta
        # repetida de la misma franja (mismo patron que `rota_franjas`). Requiere el indice
        # unico `idx_franjas_editoriales_uniq` (lo crea `_crear_indices_unicos_idempotencia`);
        # PRECONDICION: una BD con duplicados previos impide crearlo -> limpiar antes.
        con.execute(
            "INSERT INTO franjas_editoriales (id, marca, red, dia_semana, hora) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (marca, red, dia_semana, hora) DO NOTHING",
            (franja["id"], franja["marca"], franja["red"], franja["dia_semana"], franja["hora"]),
        )
        con.commit()
    finally:
        con.close()
    return franja


def borrar_franja(franja_id: str) -> bool:
    """Borra una franja editorial; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM franjas_editoriales WHERE id = ?", (franja_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Cadencias por (marca?, red?): scheduling por MARGEN entre posts               #
# --------------------------------------------------------------------------- #

_COLS_CADENCIA = ("id", "marca", "red", "margen_min", "hora_inicio", "hora_fin", "dias", "activo")
_SELECT_CADENCIA = f"SELECT {', '.join(_COLS_CADENCIA)} FROM cadencias"


def _fila_a_cadencia(fila: Any) -> dict[str, Any]:
    """Fila de `cadencias` -> dict publico (`dias` como lista de int, `activo` bool)."""
    crudo = fila["dias"] or ""
    dias = [int(p) for p in crudo.split(",") if p.strip() != ""]
    return {
        "id": fila["id"],
        "marca": fila["marca"] or "",
        "red": fila["red"] or "",
        "margen_min": int(fila["margen_min"] or 0),
        "hora_inicio": fila["hora_inicio"] or "",
        "hora_fin": fila["hora_fin"] or "",
        "dias": dias,
        "activo": bool(fila["activo"]),
    }


def listar_cadencias() -> list[dict[str, Any]]:
    """Todas las cadencias, ordenadas por marca/red/id (determinista)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_CADENCIA} ORDER BY marca ASC, red ASC, id ASC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_cadencia(f) for f in filas]


def guardar_cadencia(
    *,
    marca: str,
    red: str,
    margen_min: int,
    hora_inicio: str,
    hora_fin: str,
    dias: list[int],
    activo: bool,
) -> dict[str, Any]:
    """UPSERT de la cadencia de (marca, red) (UNIQUE). Devuelve la fila resultante."""
    dias_csv = ",".join(str(int(d)) for d in dias)
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO cadencias (id, marca, red, margen_min, hora_inicio, hora_fin, dias, activo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (marca, red) DO UPDATE SET "
            "margen_min=excluded.margen_min, hora_inicio=excluded.hora_inicio, "
            "hora_fin=excluded.hora_fin, dias=excluded.dias, activo=excluded.activo",
            (
                uuid.uuid4().hex[:12],
                marca or "",
                red or "",
                int(margen_min),
                hora_inicio,
                hora_fin,
                dias_csv,
                1 if activo else 0,
            ),
        )
        con.commit()
        fila = con.execute(
            f"{_SELECT_CADENCIA} WHERE marca = ? AND red = ?", (marca or "", red or "")
        ).fetchone()
    finally:
        con.close()
    return _fila_a_cadencia(fila)


def borrar_cadencia(cadencia_id: str) -> bool:
    """Borra una cadencia; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM cadencias WHERE id = ?", (cadencia_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


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
    "es_green",
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
    "es_green",
)


def _fila_a_etiqueta(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `etiquetas` en dict (con `activo`/`es_green` como bool)."""
    et: dict[str, Any] = {col: fila[col] for col in _COLS_ETIQUETA}
    et["activo"] = bool(fila["activo"])
    et["ttl_dias"] = int(fila["ttl_dias"] or 0)
    et["es_green"] = bool(fila["es_green"])
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
    es_green: bool = False,
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
        "es_green": 1 if es_green else 0,
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
    if "es_green" in cambios:
        cambios["es_green"] = 1 if cambios["es_green"] else 0
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


# --------------------------------------------------------------------------- #
# Taller GREEN / brainstorming: ideas evergreen (propuesta -> aprobada/descartada)
# --------------------------------------------------------------------------- #
# La IA PROPONE ideas evergreen; una persona las aprueba o descarta; solo para las
# aprobadas se genera la pieza (`flujo='evergreen'` en el tablero). NO valida aqui
# (lo hace `api/green`); este modulo es persistencia pura. Mismo patron que etiquetas.

_COLS_GREEN_IDEA = (
    "id",
    "marca",
    "titulo",
    "descripcion",
    "estado",
    "origen",
    "generacion_id",
    "contenido_id",
    "creado",
    "actualizado",
)
_SELECT_GREEN_IDEA = f"SELECT {', '.join(_COLS_GREEN_IDEA)} FROM green_ideas"
_CAMPOS_EDITABLES_GREEN_IDEA: tuple[str, ...] = (
    "titulo",
    "descripcion",
    "estado",
    "contenido_id",
)


def _fila_a_green_idea(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `green_ideas` en dict."""
    return {col: fila[col] for col in _COLS_GREEN_IDEA}


def crear_green_idea(
    *,
    marca: str = "",
    titulo: str = "",
    descripcion: str = "",
    estado: str = "propuesta",
    origen: str = "ia",
    generacion_id: str = "",
    contenido_id: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Inserta una idea de contenido evergreen y la devuelve. NO valida (lo hace la API)."""
    # Precisión de MICROSEGUNDOS en `creado`: el listado ordena por `creado DESC, id DESC`,
    # pero `id` es un uuid aleatorio (no monotónico), así que dos ideas creadas en el MISMO
    # segundo quedaban en orden indefinido ("recientes primero" no determinista). Los
    # microsegundos desempatan creaciones consecutivas sin añadir un campo de secuencia.
    ahora = datetime.now().isoformat(timespec="microseconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "titulo": titulo or "",
        "descripcion": descripcion or "",
        "estado": estado or "propuesta",
        "origen": origen or "ia",
        "generacion_id": generacion_id or "",
        "contenido_id": contenido_id or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_GREEN_IDEA)
        con.execute(
            f"INSERT INTO green_ideas ({', '.join(_COLS_GREEN_IDEA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_GREEN_IDEA),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_green_ideas(
    *, marca: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    """Lista ideas evergreen, recientes primero. Filtros opcionales por `marca`/`estado`."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    sql = _SELECT_GREEN_IDEA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_green_idea(f) for f in filas]


def obtener_green_idea(idea_id: str) -> dict[str, Any] | None:
    """Una idea evergreen por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_GREEN_IDEA} WHERE id = ?", (idea_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_green_idea(fila) if fila is not None else None


def actualizar_green_idea(idea_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente una idea; None si no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_GREEN_IDEA}
    if not cambios:
        return obtener_green_idea(idea_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, idea_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE green_ideas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_GREEN_IDEA} WHERE id = ?", (idea_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_green_idea(fila) if fila is not None else None


def borrar_green_idea(idea_id: str) -> bool:
    """Borra una idea evergreen. True si existia."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM green_ideas WHERE id = ?", (idea_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def asignar_etiqueta(contenido_id: str, etiqueta_id: str) -> None:
    """Asigna una etiqueta a un contenido (idempotente: ignora si ya existe)."""
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO contenido_etiquetas (contenido_id, etiqueta_id) VALUES (?, ?) "
            "ON CONFLICT DO NOTHING",
            (contenido_id, etiqueta_id),
        )
        con.commit()
    finally:
        con.close()


def quitar_etiqueta(contenido_id: str, etiqueta_id: str) -> bool:
    """Quita una etiqueta de un contenido. True si estaba asignada."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM contenido_etiquetas WHERE contenido_id = ? AND etiqueta_id = ?",
            (contenido_id, etiqueta_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def etiquetas_por_contenido() -> dict[str, list[str]]:
    """Mapa `contenido_id -> [etiqueta_id, ...]` de TODAS las asignaciones (una lectura)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT contenido_id, etiqueta_id FROM contenido_etiquetas"
        ).fetchall()
    finally:
        con.close()
    mapa: dict[str, list[str]] = {}
    for f in filas:
        mapa.setdefault(f["contenido_id"], []).append(f["etiqueta_id"])
    return mapa


def ids_contenido_con_etiqueta(etiqueta_id: str) -> set[str]:
    """Ids de contenido que llevan la etiqueta dada (para filtrar el tablero)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT contenido_id FROM contenido_etiquetas WHERE etiqueta_id = ?",
            (etiqueta_id,),
        ).fetchall()
    finally:
        con.close()
    return {f["contenido_id"] for f in filas}


# --------------------------------------------------------------------------- #
# Ola COLABORACION: comentarios internos por pieza                             #
# --------------------------------------------------------------------------- #
# Hilo de discusion de redaccion atado a un item de `contenido` (padre). Modelo
# CRUD plano: crear, listar (por contenido, opcionalmente filtrando una plataforma),
# marcar resuelto/reabrir, editar texto, borrar. Aditivo: NO toca `contenido`.

_COLS_COMENTARIO = (
    "id",
    "contenido_id",
    "plataforma_id",
    "autor_id",
    "autor_nombre",
    "texto",
    "resuelto",
    "creado",
    "actualizado",
    "menciones",
)
_SELECT_COMENTARIO = f"SELECT {', '.join(_COLS_COMENTARIO)} FROM contenido_comentarios"


def _fila_a_comentario(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `contenido_comentarios` en dict (`resuelto` bool, `menciones` lista)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_COMENTARIO}
    item["resuelto"] = bool(fila["resuelto"])
    item["menciones"] = [m for m in (fila["menciones"] or "").split(",") if m]
    return item


def crear_comentario(
    *,
    contenido_id: str,
    plataforma_id: str = "",
    texto: str,
    autor: dict[str, str] | None = None,
    menciones: list[str] | None = None,
) -> dict[str, Any]:
    """Inserta un comentario en el hilo de un contenido y lo devuelve. NO valida.

    `menciones` son ids de usuarios etiquetados con @ (se guardan separados por coma); los
    devolvemos como lista en el dict de salida (ver `_fila_a_comentario`).
    """
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "contenido_id": contenido_id,
        "plataforma_id": plataforma_id or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "texto": texto or "",
        "resuelto": 0,
        "creado": ahora,
        "actualizado": ahora,
        "menciones": ",".join(menciones or []),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_COMENTARIO)
        con.execute(
            f"INSERT INTO contenido_comentarios ({', '.join(_COLS_COMENTARIO)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_COMENTARIO),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_comentario(fila)


def listar_comentarios(
    contenido_id: str, plataforma_id: str | None = None
) -> list[dict[str, Any]]:
    """Comentarios de un contenido, mas antiguos primero. `plataforma_id` filtra una red."""
    sql = f"{_SELECT_COMENTARIO} WHERE contenido_id = ?"
    params: list[Any] = [contenido_id]
    if plataforma_id is not None:
        sql += " AND plataforma_id = ?"
        params.append(plataforma_id)
    sql += " ORDER BY creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_comentario(f) for f in filas]


def obtener_comentario(comentario_id: str) -> dict[str, Any] | None:
    """Un comentario por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_COMENTARIO} WHERE id = ?", (comentario_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comentario(fila) if fila is not None else None


def actualizar_comentario(
    comentario_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita `texto` y/o `resuelto` de un comentario; None si no existe."""
    cambios = {k: v for k, v in campos.items() if k in ("texto", "resuelto")}
    if not cambios:
        return obtener_comentario(comentario_id)
    if "resuelto" in cambios:
        cambios["resuelto"] = 1 if cambios["resuelto"] else 0
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, comentario_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE contenido_comentarios SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_COMENTARIO} WHERE id = ?", (comentario_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comentario(fila) if fila is not None else None


def borrar_comentario(comentario_id: str) -> bool:
    """Borra un comentario; True si existia."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM contenido_comentarios WHERE id = ?", (comentario_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Notificaciones IN-APP (el "cajon" de la campana)                             #
# --------------------------------------------------------------------------- #
# Una fila = una noticia para UN destinatario. Append + update de `leida`. El reparto
# (a quien notificar) vive en `dominio/notificaciones.py`; aqui solo se persiste/lee.

_COLS_NOTIFICACION = (
    "id",
    "usuario_id",
    "marca_id",
    "tipo",
    "contenido_id",
    "plataforma_id",
    "actor_id",
    "actor_nombre",
    "resumen",
    "enlace",
    "leida",
    "creada",
)
_SELECT_NOTIFICACION = f"SELECT {', '.join(_COLS_NOTIFICACION)} FROM notificaciones"


def _fila_a_notificacion(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `notificaciones` en dict (`leida` como bool)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_NOTIFICACION}
    item["leida"] = bool(fila["leida"])
    return item


def crear_notificacion(
    *,
    usuario_id: str,
    marca_id: str,
    tipo: str,
    contenido_id: str = "",
    plataforma_id: str = "",
    actor: dict[str, str] | None = None,
    resumen: str = "",
    enlace: str = "",
) -> dict[str, Any]:
    """Inserta UNA notificacion para un destinatario y la devuelve. NO valida ni filtra."""
    actor = actor or {}
    fila = {
        "id": uuid.uuid4().hex[:12],
        "usuario_id": usuario_id or "",
        "marca_id": marca_id or "",
        "tipo": tipo or "",
        "contenido_id": contenido_id or "",
        "plataforma_id": plataforma_id or "",
        "actor_id": actor.get("id", "") or "",
        "actor_nombre": actor.get("usuario", "") or actor.get("nombre", "") or "",
        "resumen": resumen or "",
        "enlace": enlace or "",
        "leida": 0,
        "creada": datetime.now().isoformat(timespec="seconds"),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_NOTIFICACION)
        con.execute(
            f"INSERT INTO notificaciones ({', '.join(_COLS_NOTIFICACION)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_NOTIFICACION),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_notificacion(fila)


def listar_notificaciones(
    usuario_id: str, marca_id: str | None = None, limite: int = 50
) -> list[dict[str, Any]]:
    """Notificaciones de un usuario (mas recientes primero). `marca_id` filtra el workspace."""
    sql = f"{_SELECT_NOTIFICACION} WHERE usuario_id = ?"
    params: list[Any] = [usuario_id]
    if marca_id:
        sql += " AND marca_id = ?"
        params.append(marca_id)
    sql += " ORDER BY creada DESC, id DESC LIMIT ?"
    params.append(max(1, min(limite, 200)))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_notificacion(f) for f in filas]


def contar_notificaciones_no_leidas(usuario_id: str, marca_id: str | None = None) -> int:
    """Cuenta las notificaciones SIN leer de un usuario (filtro opcional por marca)."""
    sql = "SELECT COUNT(*) AS n FROM notificaciones WHERE usuario_id = ? AND leida = 0"
    params: list[Any] = [usuario_id]
    if marca_id:
        sql += " AND marca_id = ?"
        params.append(marca_id)
    con = _conectar()
    try:
        fila = con.execute(sql, tuple(params)).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def marcar_notificacion_leida(notificacion_id: str, usuario_id: str) -> bool:
    """Marca UNA notificacion como leida (solo si es del usuario). True si existia."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE notificaciones SET leida = 1 WHERE id = ? AND usuario_id = ?",
            (notificacion_id, usuario_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def marcar_notificaciones_leidas(usuario_id: str, marca_id: str | None = None) -> int:
    """Marca como leidas TODAS las del usuario (opcionalmente solo las de una marca)."""
    sql = "UPDATE notificaciones SET leida = 1 WHERE usuario_id = ? AND leida = 0"
    params: list[Any] = [usuario_id]
    if marca_id:
        sql += " AND marca_id = ?"
        params.append(marca_id)
    con = _conectar()
    try:
        cur = con.execute(sql, tuple(params))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Ola COLABORACION: historial de versiones del copy                            #
# --------------------------------------------------------------------------- #
# Snapshots inmutables del copy de una fila por plataforma. Cada cambio del copy
# guarda el texto ANTERIOR (con quien/cuando/nota); revertir aplica un texto viejo
# como copy actual y vuelve a snapshotear lo que se pisa: nunca se pierde nada.

_COLS_COPY_VERSION = (
    "id",
    "plataforma_id",
    "contenido_id",
    "version",
    "copy",
    "autor_id",
    "autor_nombre",
    "nota",
    "creado",
)
_SELECT_COPY_VERSION = f"SELECT {', '.join(_COLS_COPY_VERSION)} FROM contenido_copy_versiones"


def _fila_a_copy_version(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_COPY_VERSION}


def registrar_copy_version(
    *,
    plataforma_id: str,
    contenido_id: str,
    copy: str,
    autor: dict[str, str] | None = None,
    nota: str = "",
) -> dict[str, Any]:
    """Guarda un snapshot del copy de una plataforma con `version` autoincremental (1-based).

    El numero de version se calcula como `MAX(version)+1` sobre esa plataforma (1 si es el
    primero). NO valida: la API decide cuando snapshotear (antes de pisar el copy vivo).

    CONTADOR SEGURO ANTE CONCURRENCIA: bajo el indice UNICO `(plataforma_id, version)`, dos
    snapshots simultaneos no pueden compartir version. Si chocan, una gana y la otra REINTENTA
    (bucle acotado) recalculando el siguiente numero (en vez de duplicar la version).
    """
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila_id = uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        ultimo_error: Exception | None = None
        for _ in range(_MAX_REINTENTOS_VERSION):
            fila_max = con.execute(
                "SELECT MAX(version) AS m FROM contenido_copy_versiones WHERE plataforma_id = ?",
                (plataforma_id,),
            ).fetchone()
            siguiente = (fila_max["m"] or 0) + 1 if fila_max is not None else 1
            fila = {
                "id": fila_id,
                "plataforma_id": plataforma_id,
                "contenido_id": contenido_id or "",
                "version": siguiente,
                "copy": copy or "",
                "autor_id": autor.get("id", "") or "",
                "autor_nombre": autor.get("usuario", "") or "",
                "nota": nota or "",
                "creado": ahora,
            }
            marcadores = ", ".join("?" for _ in _COLS_COPY_VERSION)
            try:
                con.execute(
                    f"INSERT INTO contenido_copy_versiones ({', '.join(_COLS_COPY_VERSION)}) "
                    f"VALUES ({marcadores})",
                    tuple(fila[col] for col in _COLS_COPY_VERSION),
                )
                con.commit()
                return _fila_a_copy_version(fila)
            except IntegrityError as e:
                ultimo_error = e  # otra version gano la carrera; el shim ya hizo rollback.
        raise RuntimeError(
            "No se pudo asignar una version de copy tras varios reintentos "
            f"(plataforma={plataforma_id})"
        ) from ultimo_error
    finally:
        con.close()


def listar_copy_versiones(plataforma_id: str) -> list[dict[str, Any]]:
    """Historial de versiones del copy de una plataforma, mas RECIENTE primero."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_COPY_VERSION} WHERE plataforma_id = ? ORDER BY version DESC, id DESC",
            (plataforma_id,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_copy_version(f) for f in filas]


def obtener_copy_version(version_id: str) -> dict[str, Any] | None:
    """Una version del copy por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_COPY_VERSION} WHERE id = ?", (version_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_copy_version(fila) if fila is not None else None


# --------------------------------------------------------------------------- #
# Ola COLABORACION: aprobacion multinivel por pieza                            #
# --------------------------------------------------------------------------- #
# Cadena de niveles de aprobacion de una fila por plataforma. Cada fila es la
# decision de UN nivel; la pieza esta aprobada cuando todos sus niveles lo estan.

_COLS_APROBACION = (
    "id",
    "plataforma_id",
    "contenido_id",
    "nivel",
    "etiqueta",
    "decision",
    "decisor_id",
    "decisor_nombre",
    "comentario",
    "creado",
    "decidido_en",
    "cargo_requerido",
)
_SELECT_APROBACION = f"SELECT {', '.join(_COLS_APROBACION)} FROM contenido_aprobaciones"


def _fila_a_aprobacion(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_APROBACION}


def crear_cadena_aprobacion(
    *,
    plataforma_id: str,
    contenido_id: str,
    etiquetas: list[str],
    cargos: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Crea (o RECREA) la cadena de aprobacion de una plataforma a partir de `etiquetas`.

    Borra cualquier cadena previa de esa plataforma y crea un nivel `pendiente` por cada
    etiqueta, en orden (nivel 1-based). `cargos` (opcional, paralela a `etiquetas`) sella el
    `cargo_requerido` de cada nivel (item C); "" o lista corta -> sin requisito en ese nivel.
    Devuelve la cadena nueva. NO valida.
    """
    cargos = cargos or []
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM contenido_aprobaciones WHERE plataforma_id = ?", (plataforma_id,)
        )
        creados: list[dict[str, Any]] = []
        for indice, etiqueta in enumerate(etiquetas, start=1):
            cargo = cargos[indice - 1] if indice - 1 < len(cargos) else ""
            fila = {
                "id": uuid.uuid4().hex[:12],
                "plataforma_id": plataforma_id,
                "contenido_id": contenido_id or "",
                "nivel": indice,
                "etiqueta": etiqueta or f"Nivel {indice}",
                "decision": "pendiente",
                "decisor_id": "",
                "decisor_nombre": "",
                "comentario": "",
                "creado": ahora,
                "decidido_en": "",
                "cargo_requerido": cargo or "",
            }
            marcadores = ", ".join("?" for _ in _COLS_APROBACION)
            con.execute(
                f"INSERT INTO contenido_aprobaciones ({', '.join(_COLS_APROBACION)}) "
                f"VALUES ({marcadores})",
                tuple(fila[col] for col in _COLS_APROBACION),
            )
            creados.append(_fila_a_aprobacion(fila))
        con.commit()
    finally:
        con.close()
    return creados


def listar_aprobaciones(plataforma_id: str) -> list[dict[str, Any]]:
    """Cadena de aprobacion de una plataforma, por nivel ascendente."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_APROBACION} WHERE plataforma_id = ? ORDER BY nivel ASC, id ASC",
            (plataforma_id,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_aprobacion(f) for f in filas]


def obtener_aprobacion(aprobacion_id: str) -> dict[str, Any] | None:
    """Un nivel de la cadena por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_APROBACION} WHERE id = ?", (aprobacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_aprobacion(fila) if fila is not None else None


def actualizar_aprobacion(
    aprobacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Aplica una decision a un nivel (`decision`/`decisor_*`/`comentario`/`decidido_en`).

    CAS DE LA MAQUINA DE ESTADOS (concurrencia): si los `campos` mueven el nivel a una decision
    TERMINAL (`aprobado`/`rechazado`), el UPDATE solo prospera si el nivel SEGUIA `pendiente`
    (`AND decision = 'pendiente'`). Asi dos peticiones simultaneas (doble-click, dos revisores a
    la vez, aprobar-tras-rechazar) NO se pisan: la primera gana y la segunda ve `rowcount == 0`
    y recibe `None` (el caller lo traduce a 409 "ya fue decidido"). Resetear a `pendiente`
    (deshacer) o tocar solo metadatos NO lleva guardia (no es una transicion de estado que se
    pueda perder). El camino normal/no contendido se comporta IGUAL que antes (rowcount 1).
    Devuelve el nivel actualizado, o None si no existia o si el CAS no aplico (ya decidido).
    """
    permitidos = ("decision", "decisor_id", "decisor_nombre", "comentario", "decidido_en")
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return obtener_aprobacion(aprobacion_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), aprobacion_id]
    # Guardia CAS solo al pasar a una decision terminal: la transicion pendiente->aprobado/
    # rechazado es la unica que se puede "perder" si dos la aplican a la vez.
    decision_nueva = cambios.get("decision")
    where_cas = ""
    if decision_nueva in (DECISION_APROBADO, DECISION_RECHAZADO):
        where_cas = " AND decision = ?"
        params.append(DECISION_PENDIENTE)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE contenido_aprobaciones SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
            f"WHERE id = ?{where_cas}",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_APROBACION} WHERE id = ?", (aprobacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_aprobacion(fila) if fila is not None else None


def decidir_nivel_aprobacion_tx(
    plataforma_id: str,
    nivel_id: str,
    validar: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Decide UN nivel de la cadena RE-VALIDANDO bajo bloqueo, en una sola transaccion.

    Cierra la condicion de carrera de INVARIANTE CRUZADO ENTRE FILAS que el CAS por-fila no
    cubre: el "dos OK = dos personas distintas" (y el orden de la cadena) se comprueba contra
    el ESTADO de toda la cadena, no de un solo nivel. Dos decisiones simultaneas de la MISMA
    persona sobre niveles distintos podrian, leyendo cada una un snapshot donde la otra aun no
    consta, pasar las dos el chequeo de "decisor distinto" y dejar a una persona dando los dos
    OK. Aqui:

      1) Bloqueamos las filas de la cadena (`SELECT ... FOR UPDATE`) de `plataforma_id`: la otra
         decision concurrente sobre la misma cadena ESPERA aqui (no lee un snapshot obsoleto).
      2) Re-leemos la cadena ya consistente y llamamos `validar(nivel_actual, cadena)` —la regla
         PURA del dominio (`colaboracion.decidir`)— sobre datos frescos. Devuelve `(campos, None)`
         o `(None, error)`.
      3) Si valida, aplicamos el UPDATE con la MISMA guardia CAS (`AND decision='pendiente'`) y
         confirmamos. Todo bajo una sola conexion/transaccion.

    Devuelve `(nivel_decidido, None)` con el nivel ya actualizado, o `(None, error)` si la
    validacion lo rechaza (texto legible para 409) o si el CAS no aplico (decidido en paralelo).
    `validar` recibe `(nivel_actual_dict | None, cadena_list)` y debe ser una funcion PURA.
    """
    con = _conectar()
    try:
        # 1) Bloqueo de la cadena: serializa las decisiones concurrentes de la MISMA pieza.
        con.execute(
            "SELECT id FROM contenido_aprobaciones WHERE plataforma_id = ? "
            "ORDER BY nivel ASC, id ASC FOR UPDATE",
            (plataforma_id,),
        ).fetchall()
        # 2) Re-lectura consistente de la cadena + del nivel objetivo.
        filas = con.execute(
            f"{_SELECT_APROBACION} WHERE plataforma_id = ? ORDER BY nivel ASC, id ASC",
            (plataforma_id,),
        ).fetchall()
        cadena = [_fila_a_aprobacion(f) for f in filas]
        nivel = next((n for n in cadena if n.get("id") == nivel_id), None)
        if nivel is None:
            con.commit()
            return None, "Ese nivel ya no existe."
        campos, error = validar(nivel, cadena)
        if error is not None:
            con.commit()
            return None, error
        # 3) Escritura con la misma guardia CAS (defensa en profundidad bajo el lock).
        permitidos = ("decision", "decisor_id", "decisor_nombre", "comentario", "decidido_en")
        cambios = {k: v for k, v in (campos or {}).items() if k in permitidos}
        asignaciones = [f"{k} = ?" for k in cambios]
        params: list[Any] = [*cambios.values(), nivel_id, DECISION_PENDIENTE]
        cur = con.execute(
            f"UPDATE contenido_aprobaciones SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
            "WHERE id = ? AND decision = ?",
            tuple(params),
        )
        if cur.rowcount == 0:
            con.commit()
            return None, "Este nivel ya fue decidido (el estado cambió)."
        fila = con.execute(
            f"{_SELECT_APROBACION} WHERE id = ?", (nivel_id,)
        ).fetchone()
        con.commit()
    finally:
        con.close()
    return (_fila_a_aprobacion(fila) if fila is not None else None), None


# --------------------------------------------------------------------------- #
# QA editorial atado a la pieza (aprobador automatico, item D)                  #
# --------------------------------------------------------------------------- #
_COLS_QA_VEREDICTO = (
    "id",
    "plataforma_id",
    "contenido_id",
    "verdicto",
    "resumen",
    "copy_hash",
    "historial_id",
    "creado",
)
_SELECT_QA_VEREDICTO = (
    f"SELECT {', '.join(_COLS_QA_VEREDICTO)} FROM contenido_qa_veredictos"
)


def registrar_veredicto_qa(
    *,
    plataforma_id: str,
    contenido_id: str,
    verdicto: str,
    resumen: str = "",
    copy_hash: str = "",
    historial_id: str = "",
) -> str:
    """Persiste un veredicto del QA editorial ATADO a una pieza y devuelve su id (item A/D).

    Append-only: inserta un registro inmutable; el consumidor lee el ULTIMO por `creado`.
    `copy_hash` es el hash del copy revisado en ese instante (para invalidar el veredicto si
    el copy cambia despues). No valida el veredicto (lo normaliza la capa de dominio).
    """
    qid = uuid.uuid4().hex[:12]
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": qid,
        "plataforma_id": plataforma_id or "",
        "contenido_id": contenido_id or "",
        "verdicto": verdicto or "",
        "resumen": (resumen or "")[:1000],
        "copy_hash": copy_hash or "",
        "historial_id": historial_id or "",
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_QA_VEREDICTO)
        con.execute(
            f"INSERT INTO contenido_qa_veredictos ({', '.join(_COLS_QA_VEREDICTO)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_QA_VEREDICTO),
        )
        con.commit()
    finally:
        con.close()
    return qid


def ultimo_veredicto_qa(
    plataforma_id: str, contenido_id: str = ""
) -> dict[str, Any] | None:
    """Ultimo veredicto del QA editorial de una pieza por `creado` (None si no hay).

    Devuelve el dict crudo del registro (incluido `copy_hash` y `creado`) para que la capa
    `repos` decida si sigue siendo VALIDO (no invalidado por un cambio de copy posterior).
    `contenido_id` se acepta por simetria de firma con `repos.ultimo_veredicto_qa`; el lookup
    se hace por `plataforma_id` (clave 1:1 de la pieza), asi que aqui no se usa.
    """
    if not plataforma_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_QA_VEREDICTO} WHERE plataforma_id = ? "
            "ORDER BY creado DESC, id DESC LIMIT 1",
            (plataforma_id,),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return None
    return {col: fila[col] for col in _COLS_QA_VEREDICTO}


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

    Conserva la firma de `ficheros.crear_publicacion` (+ `id`/`fecha_creacion` opcionales
    para PRESERVAR identidad al migrar desde YAML). El `estado` editorial se traduce al de
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


# --------------------------------------------------------------------------- #
# Catalogo de programas (#150, PARRILLA 2026.xlsx)                              #
# --------------------------------------------------------------------------- #
#
# En el Excel cada HOJA evergreen ("Álvaro Fidalgo", "Real Oviedo", "Anfitriones", "PATY
# CANTU", "MUNDIAL", "LA SELECCIÓN EN TUS MANOS", "IDEAS SIN DERECHOS") es un PROGRAMA.
# Hasta ahora `rota_piezas.programa` era texto libre; pasamos a un catalogo con color y
# fechas de campana (inicio/fin) para que la UI pueda colorear y filtrar la parrilla.
#
# IMPORTANTE: las piezas siguen referenciando al programa POR NOMBRE (no por id) para que
# una pieza huerfana de un programa borrado siga apareciendo en la parrilla con su texto
# original. Al RENOMBRAR un programa, la API ejecuta una cascada (UPDATE rota_piezas SET
# programa = ? WHERE programa = ?) en la MISMA transaccion: ver `actualizar_programa_rota`.

_COLS_PROGRAMA_ROTA = (
    "id",
    "nombre",
    "descripcion",
    "color",
    "inicio",
    "fin",
    "activo",
    "creado",
    "actualizado",
)
_SELECT_PROGRAMA_ROTA = f"SELECT {', '.join(_COLS_PROGRAMA_ROTA)} FROM rota_programas"

# Campos editables via `actualizar_programa_rota` (allowlist; `id`/`creado`/`actualizado`
# los gestiona el sistema). `nombre` es editable pero exige cascada en `rota_piezas`.
_CAMPOS_EDITABLES_PROGRAMA_ROTA: tuple[str, ...] = (
    "nombre",
    "descripcion",
    "color",
    "inicio",
    "fin",
    "activo",
)


def _fila_a_programa_rota(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `rota_programas` en dict (`activo` como bool)."""
    p: dict[str, Any] = {col: fila[col] for col in _COLS_PROGRAMA_ROTA}
    p["activo"] = bool(fila["activo"])
    return p


def _programa_por_nombre(con: Any, nombre: str) -> dict[str, Any] | None:
    """Busca un programa por nombre EXACTO (case-insensitive). None si no hay.

    Usa LOWER(nombre) en SQL para que "MUNDIAL" no choque con "Mundial". La capa API
    impone la unicidad case-insensitive antes de insertar.
    """
    fila = con.execute(
        f"{_SELECT_PROGRAMA_ROTA} WHERE LOWER(nombre) = LOWER(?)", (nombre,)
    ).fetchone()
    return _fila_a_programa_rota(fila) if fila is not None else None


def existe_programa_por_nombre(nombre: str) -> bool:
    """True si hay un programa con ese nombre (case-insensitive). Util para la API."""
    if not nombre:
        return False
    con = _conectar()
    try:
        return _programa_por_nombre(con, nombre) is not None
    finally:
        con.close()


def contar_piezas_por_programa(nombre: str) -> int:
    """Cuantas piezas en `rota_piezas` referencian ese `programa` (case-insensitive)."""
    if not nombre:
        return 0
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM rota_piezas WHERE LOWER(programa) = LOWER(?)",
            (nombre,),
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"] or 0) if fila is not None else 0


def crear_programa_rota(
    nombre: str,
    *,
    descripcion: str = "",
    color: str = "",
    inicio: str = "",
    fin: str = "",
    activo: bool = True,
) -> dict[str, Any]:
    """Inserta un programa nuevo y lo devuelve. NO valida (lo hace la API).

    `nombre` se persiste tal cual lo manda la API; la unicidad case-insensitive la
    garantiza la capa API antes de llegar aqui (un INSERT chocaria con el UNIQUE del
    DDL en caso de duplicado exacto).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "descripcion": descripcion or "",
        "color": color or "",
        "inicio": inicio or "",
        "fin": fin or "",
        "activo": 1 if activo else 0,
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PROGRAMA_ROTA)
        con.execute(
            f"INSERT INTO rota_programas ({', '.join(_COLS_PROGRAMA_ROTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PROGRAMA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["activo"] = bool(fila["activo"])
    return fila


def listar_programas_rota(*, activo: bool | None = None) -> list[dict[str, Any]]:
    """Programas del catalogo, ordenados por nombre. `activo` filtra; None = todos."""
    sql = _SELECT_PROGRAMA_ROTA
    params: tuple[Any, ...] = ()
    if activo is not None:
        sql += " WHERE activo = ?"
        params = (1 if activo else 0,)
    sql += " ORDER BY LOWER(nombre) ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_fila_a_programa_rota(f) for f in filas]


def obtener_programa_rota(programa_id: str) -> dict[str, Any] | None:
    """Un programa por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PROGRAMA_ROTA} WHERE id = ?", (programa_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_programa_rota(fila) if fila is not None else None


def actualizar_programa_rota(
    programa_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente un programa; None si el id no existe.

    Si el cambio incluye `nombre` y es distinto al actual, hace CASCADA sobre
    `rota_piezas` (UPDATE `programa` por el nombre antiguo) en LA MISMA TRANSACCION:
    ningun escenario deja piezas referenciando a un nombre que ya no existe.

    NOTA: la unicidad case-insensitive y el control de existencia los valida la capa API
    ANTES de llamar (defensa en profundidad: el UNIQUE del DDL es el ultimo cerrojo).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PROGRAMA_ROTA}
    if not cambios:
        return obtener_programa_rota(programa_id)
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, programa_id]
    con = _conectar()
    try:
        # 1) Cargar el nombre ACTUAL para detectar el rename y disparar la cascada.
        fila_actual = con.execute(
            "SELECT nombre FROM rota_programas WHERE id = ?", (programa_id,)
        ).fetchone()
        if fila_actual is None:
            return None
        nombre_actual = fila_actual["nombre"]
        nuevo_nombre = cambios.get("nombre")
        # 2) UPDATE del programa.
        con.execute(
            f"UPDATE rota_programas SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        # 3) Cascada en piezas si el nombre cambio realmente.
        if isinstance(nuevo_nombre, str) and nuevo_nombre and nuevo_nombre != nombre_actual:
            con.execute(
                "UPDATE rota_piezas SET programa = ?, actualizado = ? WHERE programa = ?",
                (nuevo_nombre, ahora, nombre_actual),
            )
        con.commit()
        fila = con.execute(
            f"{_SELECT_PROGRAMA_ROTA} WHERE id = ?", (programa_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_programa_rota(fila) if fila is not None else None


def borrar_programa_rota(programa_id: str) -> bool:
    """Borra un programa; True si existia, False si no.

    NO arrastra cascada sobre `rota_piezas`: la capa API decide si bloquea el borrado
    cuando hay piezas usando el nombre (con `?forzar=true` se permite igualmente y las
    piezas siguen mostrando el nombre textual). Esto vive en `api/rota.py`.
    """
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_programas WHERE id = ?", (programa_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Franjas por semana (#XYZ "Mundial"): CRUD de `rota_franjas`                  #
# --------------------------------------------------------------------------- #
#
# Cada semana tiene sus propias franjas (nombre libre, rangos HH:MM, solapes permitidos,
# soporte a franjas que cruzan medianoche). Se siembran 2 por defecto ("Mañana", "Tarde")
# la primera vez que la API lee la semana; admin puede anadir, editar o borrar mas.

_COLS_FRANJA_SEMANA = ("id", "lunes", "nombre", "inicio", "fin", "orden", "es_descanso")
_SELECT_FRANJA_SEMANA = (
    f"SELECT {', '.join(_COLS_FRANJA_SEMANA)} FROM rota_franjas"
)


def _fila_a_franja_semana(fila: Any) -> dict[str, Any]:
    fila_dict = {col: fila[col] for col in _COLS_FRANJA_SEMANA}
    # Normaliza `es_descanso` a bool (Postgres devuelve True/False, sqlite-fake 0/1).
    fila_dict["es_descanso"] = bool(fila_dict.get("es_descanso", False))
    return fila_dict


def listar_franjas_semana(lunes: str) -> list[dict[str, Any]]:
    """Franjas de la semana cuyo lunes es `lunes`, ordenadas por `orden` ASC."""
    if not lunes:
        return []
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_FRANJA_SEMANA} WHERE lunes = ? ORDER BY orden ASC, nombre ASC",
            (lunes,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_franja_semana(f) for f in filas]


def obtener_franja_semana(franja_id: str) -> dict[str, Any] | None:
    """Una franja por id, None si no existe."""
    if not franja_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_FRANJA_SEMANA} WHERE id = ?", (franja_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_franja_semana(fila) if fila is not None else None


def crear_franja_semana(
    lunes: str,
    nombre: str,
    inicio: str,
    fin: str,
    *,
    orden: int = 0,
    es_descanso: bool = False,
) -> dict[str, Any] | None:
    """Inserta una franja en `rota_franjas`. Devuelve la franja creada o None si
    ya existe una con el mismo `(lunes, nombre)` (UNIQUE).

    NO valida formato (lo hace la API): aqui solo persistimos lo que llega. La franja con
    `es_descanso=true` se trata como "no laboral": no cubre eventos (ver
    `rota.franjas_activas_en`), pero el turno existe (y puede asignarse a un miembro).
    """
    fila = {
        "id": uuid.uuid4().hex[:12],
        "lunes": lunes,
        "nombre": nombre,
        "inicio": inicio,
        "fin": fin,
        "orden": int(orden),
        "es_descanso": bool(es_descanso),
    }
    con = _conectar()
    try:
        try:
            con.execute(
                "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    fila["id"],
                    fila["lunes"],
                    fila["nombre"],
                    fila["inicio"],
                    fila["fin"],
                    fila["orden"],
                    fila["es_descanso"],
                ),
            )
            con.commit()
        except IntegrityError:
            # UNIQUE violation (lunes, nombre) -> ya existe. `_ConexionPg` ya hizo rollback.
            return None
    finally:
        con.close()
    return fila


def actualizar_franja_semana(
    franja_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita campos de una franja (allowlist `nombre/inicio/fin/orden`); None si no existe.

    NOTA: `es_descanso` NO se edita (cambiarlo a posteriori dejaria turnos de descanso
    "convertidos" en laborales o viceversa: una incoherencia silenciosa). Si se quiere
    "renombrar" una franja de descanso, se borra y se crea una nueva.
    """
    editables = ("nombre", "inicio", "fin", "orden")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return obtener_franja_semana(franja_id)
    if "orden" in cambios:
        cambios["orden"] = int(cambios["orden"])
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), franja_id]
    con = _conectar()
    try:
        try:
            cur = con.execute(
                f"UPDATE rota_franjas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
                tuple(params),
            )
            con.commit()
        except IntegrityError:
            # UNIQUE violation (otra franja con el mismo nombre en la semana).
            return None
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_FRANJA_SEMANA} WHERE id = ?", (franja_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_franja_semana(fila) if fila is not None else None


def contar_turnos_de_franja(franja_id: str) -> int:
    """Numero de turnos que tienen esa `franja_id` (para el 409 al borrar)."""
    if not franja_id:
        return 0
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM rota_turnos WHERE franja_id = ?",
            (franja_id,),
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def borrar_franja_semana(franja_id: str, *, forzar: bool = False) -> dict[str, Any]:
    """Borra una franja. Devuelve `{borrada: bool, turnos_borrados: int, turnos_asociados: int}`.

    Si hay turnos asociados y `forzar=False`, no borra y devuelve
    `{borrada: False, turnos_asociados: N, turnos_borrados: 0}` para que la API responda
    con 409. Con `forzar=True`, borra los turnos en cascada y la franja despues.
    """
    if not franja_id:
        return {"borrada": False, "turnos_asociados": 0, "turnos_borrados": 0}
    con = _conectar()
    try:
        fila_count = con.execute(
            "SELECT COUNT(*) AS n FROM rota_turnos WHERE franja_id = ?",
            (franja_id,),
        ).fetchone()
        asociados = int(fila_count["n"]) if fila_count is not None else 0
        if asociados > 0 and not forzar:
            return {
                "borrada": False,
                "turnos_asociados": asociados,
                "turnos_borrados": 0,
            }
        turnos_borrados = 0
        if asociados > 0 and forzar:
            cur_t = con.execute(
                "DELETE FROM rota_turnos WHERE franja_id = ?", (franja_id,)
            )
            turnos_borrados = cur_t.rowcount
        cur_f = con.execute("DELETE FROM rota_franjas WHERE id = ?", (franja_id,))
        con.commit()
        return {
            "borrada": cur_f.rowcount > 0,
            "turnos_asociados": asociados,
            "turnos_borrados": turnos_borrados,
        }
    finally:
        con.close()


def sembrar_franjas_por_defecto(lunes: str) -> list[dict[str, Any]]:
    """Idempotente: siembra ("Mañana", "Tarde") en `rota_franjas` para `lunes` si faltan.

    Devuelve la lista de franjas de la semana tras el sembrado (orden ASC). Si ya hay 2 o
    mas y "Mañana"/"Tarde" estan presentes, no toca nada.
    """
    if not lunes:
        return []
    con = _conectar()
    try:
        _sembrar_franjas_por_defecto_en(con, lunes)
        con.commit()
    finally:
        con.close()
    return listar_franjas_semana(lunes)


# --------------------------------------------------------------------------- #
# Solicitudes de cambio de turno entre companeros (#175)                       #
# --------------------------------------------------------------------------- #
#
# Cuando un CM (solicitante A) necesita cubrir un asunto personal le pide a un
# companero (B) intercambiar el turno de un dia por el de otro. B acepta/rechaza, y si
# acepta, Elias (admin) aprueba o rechaza. La aprobacion EJECUTA el swap en
# `rota_turnos` (intercambia `miembro_id` de las dos franjas) y la solicitud
# pasa a `aplicado`. Las ausencias REALES (vacaciones, baja) viven en SAP, no aqui.
#
# IMPORTANTE: tras la migracion a "franjas por semana", las columnas `franja_a`/`franja_b`
# de `rota_swaps_turno` referencian `rota_franjas.id` (NO strings 'matutino'/'vespertino').
# Es un cambio de SEMANTICA del DATO, no de columna: los call sites deben pasar el
# `franja_id` real al crear el swap y al re-validarlo en el aprobado.

_COLS_SWAP_TURNO = (
    "id",
    "solicitante_id",
    "solicitante_nombre",
    "destinatario_id",
    "destinatario_nombre",
    "fecha_a",
    "franja_a",
    "fecha_b",
    "franja_b",
    "motivo",
    "estado",
    "respuesta_destinatario",
    "respuesta_admin",
    "creado",
    "actualizado",
    "decidido_destinatario",
    "decidido_admin",
    "aplicado",
)
_SELECT_SWAP_TURNO = f"SELECT {', '.join(_COLS_SWAP_TURNO)} FROM rota_swaps_turno"

# Campos editables del swap (allowlist DEFENSIVA: la API valida transiciones; aqui se
# garantiza que `actualizar_swap_turno` solo toca columnas de estado/timestamps/respuestas
# y nunca el solicitante/destinatario/turnos originales).
_CAMPOS_EDITABLES_SWAP = (
    "estado",
    "respuesta_destinatario",
    "respuesta_admin",
    "decidido_destinatario",
    "decidido_admin",
    "aplicado",
)


def _fila_a_swap_turno(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_SWAP_TURNO}


# --------------------------------------------------------------------------- #
# Config de franjas (#185): singleton id='default'                              #
# --------------------------------------------------------------------------- #


_COLS_CONFIG_FRANJAS = (
    "matutino_inicio",
    "matutino_fin",
    "vespertino_inicio",
    "vespertino_fin",
    "actualizado",
)


def obtener_franjas_config() -> dict[str, str]:
    """Lee la config singleton de franjas. Si no existe, devuelve los DEFAULTS del dominio.

    No SELECT-INSERT race: si la fila aun no esta, la app no la crea aqui; la crea el
    PATCH del admin. Mientras tanto, `mapear_franja` usa los defaults de rota.py.
    """
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT {', '.join(_COLS_CONFIG_FRANJAS)} FROM rota_config_franjas "
            "WHERE id = ?",
            ("default",),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return {
            "matutino_inicio": "08:00",
            "matutino_fin": "16:00",
            "vespertino_inicio": "16:00",
            "vespertino_fin": "24:00",
            "actualizado": "",
        }
    return {col: fila[col] for col in _COLS_CONFIG_FRANJAS}


def guardar_franjas_config(
    matutino_inicio: str,
    matutino_fin: str,
    vespertino_inicio: str,
    vespertino_fin: str,
) -> dict[str, str]:
    """Hace UPSERT del singleton de franjas. Devuelve la fila resultante."""
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        # INSERT ... ON CONFLICT DO UPDATE (Postgres): si la fila existe, actualiza.
        con.execute(
            "INSERT INTO rota_config_franjas "
            "(id, matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin, "
            " actualizado) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET "
            "matutino_inicio = EXCLUDED.matutino_inicio, "
            "matutino_fin = EXCLUDED.matutino_fin, "
            "vespertino_inicio = EXCLUDED.vespertino_inicio, "
            "vespertino_fin = EXCLUDED.vespertino_fin, "
            "actualizado = EXCLUDED.actualizado",
            (
                "default",
                matutino_inicio,
                matutino_fin,
                vespertino_inicio,
                vespertino_fin,
                ahora,
            ),
        )
        con.commit()
    finally:
        con.close()
    return obtener_franjas_config()


def crear_swap_turno(
    solicitante_id: str,
    destinatario_id: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    *,
    solicitante_nombre: str = "",
    destinatario_nombre: str = "",
    motivo: str = "",
) -> dict[str, Any]:
    """Inserta una solicitud de swap (estado `propuesto`) y la devuelve.

    NO valida (lo hace la API): que los miembros existan, que sean distintos, que las
    fechas sean ISO y que las franjas pertenezcan a `FRANJAS_TURNO`. La validacion de
    que existen turnos reales en `rota_turnos` que coinciden con (A, fecha_a,
    franja_a) y (B, fecha_b, franja_b) tambien la hace la API.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "solicitante_id": solicitante_id or "",
        "solicitante_nombre": solicitante_nombre or "",
        "destinatario_id": destinatario_id or "",
        "destinatario_nombre": destinatario_nombre or "",
        "fecha_a": fecha_a or "",
        "franja_a": franja_a or "",
        "fecha_b": fecha_b or "",
        "franja_b": franja_b or "",
        "motivo": motivo or "",
        "estado": ESTADO_SWAP_PROPUESTO,
        "respuesta_destinatario": "",
        "respuesta_admin": "",
        "creado": ahora,
        "actualizado": ahora,
        "decidido_destinatario": "",
        "decidido_admin": "",
        "aplicado": "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_SWAP_TURNO)
        con.execute(
            f"INSERT INTO rota_swaps_turno ({', '.join(_COLS_SWAP_TURNO)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_SWAP_TURNO),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_swaps_turno(
    estado: str | None = None,
    solicitante_id: str | None = None,
    destinatario_id: str | None = None,
    *,
    mio_id: str | None = None,
) -> list[dict[str, Any]]:
    """Solicitudes de swap, mas recientes primero. Filtros opcionales combinables.

    `mio_id` es un atajo para "swaps que me involucran": filas en las que `mio_id` es
    solicitante O destinatario. La API lo usa cuando el cliente pide `?mio=true` y hay
    sesion activa.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if solicitante_id:
        clausulas.append("solicitante_id = ?")
        params.append(solicitante_id)
    if destinatario_id:
        clausulas.append("destinatario_id = ?")
        params.append(destinatario_id)
    if mio_id:
        clausulas.append("(solicitante_id = ? OR destinatario_id = ?)")
        params.append(mio_id)
        params.append(mio_id)
    sql = _SELECT_SWAP_TURNO
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_swap_turno(f) for f in filas]


def obtener_swap_turno(swap_id: str) -> dict[str, Any] | None:
    """Una solicitud de swap por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


def actualizar_swap_turno(
    swap_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Actualiza campos de un swap (allowlist `_CAMPOS_EDITABLES_SWAP`); None si no existe.

    Refresca `actualizado` SIEMPRE. La API es responsable de las TRANSICIONES validas
    (no se valida aqui). Devuelve el swap actualizado, o None si el id no existe.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_SWAP}
    if not cambios:
        return obtener_swap_turno(swap_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(swap_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_swaps_turno SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


def borrar_swap_turno(swap_id: str) -> bool:
    """Borra un swap (uso administrativo; el flujo normal es marcar `cancelado`)."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_swaps_turno WHERE id = ?", (swap_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def aplicar_swap_turno(
    swap_id: str,
    *,
    solicitante_id: str,
    solicitante_nombre: str,
    destinatario_id: str,
    destinatario_nombre: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    respuesta_admin: str = "",
) -> dict[str, Any] | None:
    """Aprueba+ejecuta un swap en UNA transaccion: intercambia los miembros y marca `aplicado`.

    Re-VALIDA dentro de la misma conexion que las franjas actuales en `rota_turnos`
    siguen siendo las del swap original (otro usuario podria haberlas reasignado a mano).
    Si NO coinciden, devuelve `{"error": "no_coinciden", "esperado": {...}, "actual": {...}}`
    y NO toca nada. Si todo cuadra, intercambia los `miembro_id`+`miembro_nombre` de las
    dos filas, marca el swap como `aplicado` con el `respuesta_admin` y los timestamps
    correspondientes, y devuelve el swap actualizado.

    Estados de salida posibles:
      - dict del swap (claves de `_COLS_SWAP_TURNO`) si se aplico,
      - {"error": "no_coinciden", "esperado": ..., "actual": ...} si las franjas no
        coinciden con lo solicitado en este momento,
      - None si el `swap_id` no existe.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        # 1) El swap debe existir. Lo BLOQUEAMOS (`FOR UPDATE`) para serializar dos aplicaciones
        #    concurrentes del MISMO swap: la segunda espera aqui y, al leer ya `aplicado`, sale
        #    sin re-intercambiar (un doble-swap volveria los turnos a su sitio: corrupcion).
        swap = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ? FOR UPDATE", (swap_id,)
        ).fetchone()
        if swap is None:
            con.commit()
            return None
        # Idempotencia: si ya esta aplicado (otra peticion gano la carrera), devolvemos el swap
        # tal cual SIN tocar los turnos. El caller lo renderiza igual (no es un error).
        if swap["estado"] == "aplicado":
            con.commit()
            return _fila_a_swap_turno(swap)
        # 2) Las dos franjas reales (por miembro + fecha + franja) deben existir y
        #    seguir asignadas a quien dijo el swap. Buscamos por (fecha, franja) y
        #    comprobamos el miembro actual (asi detectamos el caso 409 con detalle).
        #    Las BLOQUEAMOS (`FOR UPDATE`) para que el intercambio sea atomico frente a otra
        #    reasignacion concurrente de los mismos turnos.
        fila_a = con.execute(
            "SELECT id, miembro_id, miembro_nombre, fecha, franja_id FROM rota_turnos "
            "WHERE fecha = ? AND franja_id = ? AND miembro_id = ? FOR UPDATE",
            (fecha_a, franja_a, solicitante_id),
        ).fetchone()
        fila_b = con.execute(
            "SELECT id, miembro_id, miembro_nombre, fecha, franja_id FROM rota_turnos "
            "WHERE fecha = ? AND franja_id = ? AND miembro_id = ? FOR UPDATE",
            (fecha_b, franja_b, destinatario_id),
        ).fetchone()
        if fila_a is None or fila_b is None:
            # Buscamos el detalle ACTUAL (sin filtrar por miembro) para informar.
            actual_a = con.execute(
                "SELECT miembro_id, miembro_nombre FROM rota_turnos "
                "WHERE fecha = ? AND franja_id = ?",
                (fecha_a, franja_a),
            ).fetchone()
            actual_b = con.execute(
                "SELECT miembro_id, miembro_nombre FROM rota_turnos "
                "WHERE fecha = ? AND franja_id = ?",
                (fecha_b, franja_b),
            ).fetchone()
            con.commit()  # suelta los locks FOR UPDATE; no tocamos nada (caso 409).
            return {
                "error": "no_coinciden",
                "esperado": {
                    "a": {
                        "fecha": fecha_a,
                        "franja": franja_a,
                        "miembro_id": solicitante_id,
                        "miembro_nombre": solicitante_nombre,
                    },
                    "b": {
                        "fecha": fecha_b,
                        "franja": franja_b,
                        "miembro_id": destinatario_id,
                        "miembro_nombre": destinatario_nombre,
                    },
                },
                "actual": {
                    "a": {
                        "fecha": fecha_a,
                        "franja": franja_a,
                        "miembro_id": actual_a["miembro_id"] if actual_a else "",
                        "miembro_nombre": actual_a["miembro_nombre"] if actual_a else "",
                    },
                    "b": {
                        "fecha": fecha_b,
                        "franja": franja_b,
                        "miembro_id": actual_b["miembro_id"] if actual_b else "",
                        "miembro_nombre": actual_b["miembro_nombre"] if actual_b else "",
                    },
                },
            }
        # 3) Intercambiamos los miembros + nombre + actualizado de ambas filas y marcamos
        #    el swap como `aplicado`. Todo bajo la misma conexion (Postgres autocommit
        #    desactivado por defecto en nuestro driver -> la `con.commit()` final lo encierra
        #    como una transaccion).
        con.execute(
            "UPDATE rota_turnos SET miembro_id = ?, miembro_nombre = ?, "
            "actualizado = ? WHERE id = ?",
            (destinatario_id, destinatario_nombre, ahora, fila_a["id"]),
        )
        con.execute(
            "UPDATE rota_turnos SET miembro_id = ?, miembro_nombre = ?, "
            "actualizado = ? WHERE id = ?",
            (solicitante_id, solicitante_nombre, ahora, fila_b["id"]),
        )
        # Guardia de estado (defensa en profundidad, ademas del FOR UPDATE): el swap solo se
        # marca `aplicado` si AUN no lo estaba. Bajo el lock esto siempre prospera; el guard
        # protege ante cualquier via que entrara sin pasar por el lock.
        con.execute(
            "UPDATE rota_swaps_turno SET estado = ?, respuesta_admin = ?, "
            "decidido_admin = ?, aplicado = ?, actualizado = ? "
            "WHERE id = ? AND estado <> ?",
            ("aplicado", respuesta_admin or "", ahora, ahora, ahora, swap_id, "aplicado"),
        )
        con.commit()
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


# --------------------------------------------------------------------------- #
# Asignacion flexible (rama rota-asignacion-flexible): helpers de lote + copiar #
# --------------------------------------------------------------------------- #
#
# Soporte para las herramientas de la consola sobre asignacion a mano: edicion
# masiva de turnos (multi-select), copia de la semana anterior, y panel de carga.
# La asignacion es 100% manual; ningun algoritmo de reparto vive aqui.


def actualizar_turnos_rota_lote(
    ids: list[str], campos: dict[str, Any]
) -> tuple[int, list[dict[str, Any]]]:
    """UPDATE masivo sobre `rota_turnos` para los `ids` dados. Devuelve `(n, turnos)`.

    `campos` solo aplica las claves editables (mismas que `actualizar_turno_rota`). `n`
    es el rowcount del UPDATE; `turnos` son los registros tras el cambio (SELECT por ids,
    para que la API devuelva el estado fresco sin tirar de los call sites uno a uno).

    Si `ids` viene vacio o no hay campos editables, no toca BD y devuelve `(0, [])`.
    """
    if not ids:
        return 0, []
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_TURNO_ROTA}
    if not cambios:
        return 0, []
    if "override" in cambios:
        cambios["override"] = 1 if cambios["override"] else 0
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    marcadores = ", ".join("?" for _ in ids)
    sql_update = (
        f"UPDATE rota_turnos SET {', '.join(asignaciones)} "
        f"WHERE id IN ({marcadores})"  # noqa: S608 -- columnas de allowlist
    )
    sql_select = f"{_SELECT_TURNO_ROTA} WHERE id IN ({marcadores})"  # noqa: S608
    con = _conectar()
    try:
        cur = con.execute(sql_update, tuple(params) + tuple(ids))
        con.commit()
        filas = con.execute(sql_select, tuple(ids)).fetchall()
    finally:
        con.close()
    return cur.rowcount, [_fila_a_turno_rota(f) for f in filas]


def copiar_turnos_rota(
    de_lunes: str, a_lunes: str, *, reemplazar: bool = False
) -> int:
    """Copia los turnos (horario persona×dia×franja) de `de_lunes` a `a_lunes`.

    Para cada turno de la semana origen, crea uno nuevo en la semana destino con `fecha`
    desplazada +N dias (N = `a_lunes - de_lunes`). Tambien CLONA las definiciones de
    franjas de la semana origen a la destino (mismo nombre/inicio/fin/orden) si la semana
    destino aun no tiene una franja con ese nombre — asi los turnos clonados se enlazan a
    una franja real en la semana destino. Los IDs son nuevos (uuid); el `estado` arranca
    como `propuesto` (Elias re-aprueba antes de publicar). Si `reemplazar=True`, primero
    borra los turnos existentes de `a_lunes` (las franjas NO se borran: no son turnos).

    Devuelve cuantas filas de turnos se crearon. Si `de_lunes` o `a_lunes` no son fechas
    validas, devuelve 0 sin tocar BD.
    """
    try:
        d_de = date.fromisoformat(de_lunes)
        d_a = date.fromisoformat(a_lunes)
    except (ValueError, TypeError):
        return 0
    delta = (d_a - d_de).days
    con = _conectar()
    try:
        # PASO 1: clonar las definiciones de franjas a la semana destino (si no estan ya).
        # Las franjas son "plantilla" de cobertura por semana; al copiar la semana entera,
        # las franjas viajan tambien con su nombre/inicio/fin/orden. El mapeo es por
        # NOMBRE: si la semana destino ya tiene "Mañana", reusamos su id.
        franjas_origen = con.execute(
            "SELECT id, nombre, inicio, fin, orden, es_descanso FROM rota_franjas "
            "WHERE lunes = ? ORDER BY orden ASC, nombre ASC",
            (de_lunes,),
        ).fetchall()
        franjas_destino = con.execute(
            "SELECT id, nombre FROM rota_franjas WHERE lunes = ?",
            (a_lunes,),
        ).fetchall()
        id_destino_por_nombre = {f["nombre"]: f["id"] for f in franjas_destino}
        # Mapeo id_origen -> id_destino (insertando las que falten).
        id_dest_por_origen: dict[str, str] = {}
        for fo in franjas_origen:
            if fo["nombre"] in id_destino_por_nombre:
                id_dest_por_origen[fo["id"]] = id_destino_por_nombre[fo["nombre"]]
                continue
            nuevo_id = uuid.uuid4().hex[:12]
            con.execute(
                "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (lunes, nombre) DO NOTHING",
                (
                    nuevo_id,
                    a_lunes,
                    fo["nombre"],
                    fo["inicio"],
                    fo["fin"],
                    fo["orden"],
                    bool(fo["es_descanso"]),
                ),
            )
            id_dest_por_origen[fo["id"]] = nuevo_id
            id_destino_por_nombre[fo["nombre"]] = nuevo_id

        if reemplazar:
            con.execute(
                "DELETE FROM rota_turnos WHERE semana = ?", (a_lunes,)
            )
        filas = con.execute(
            f"{_SELECT_TURNO_ROTA} WHERE semana = ? ORDER BY fecha ASC, franja_id ASC",
            (de_lunes,),
        ).fetchall()
        creadas = 0
        ahora = datetime.now().isoformat(timespec="seconds")
        marcadores = ", ".join("?" for _ in _COLS_TURNO_ROTA)
        for f in filas:
            fila = _fila_a_turno_rota(f)
            # Desplaza la fecha +delta dias; si no parsea, salta esa fila.
            try:
                nueva_fecha = (date.fromisoformat(fila["fecha"]) + timedelta(days=delta)).isoformat()
            except (ValueError, TypeError):
                continue
            franja_id_dest = id_dest_por_origen.get(fila["franja_id"], "")
            if not franja_id_dest:
                # Sin franja destino no podemos enlazar el turno: lo saltamos (defensa).
                continue
            nuevo = {
                "id": uuid.uuid4().hex[:12],
                "semana": a_lunes,
                "fecha": nueva_fecha,
                "miembro_id": fila["miembro_id"],
                "miembro_nombre": fila["miembro_nombre"],
                "franja_id": franja_id_dest,
                "estado": ESTADO_ROTA_PROPUESTO,
                "override": 1 if fila["override"] else 0,
                "motivo": fila["motivo"],
                "nota_relevo": fila["nota_relevo"],
                "creado": ahora,
                "actualizado": ahora,
            }
            con.execute(
                f"INSERT INTO rota_turnos ({', '.join(_COLS_TURNO_ROTA)}) "
                f"VALUES ({marcadores})",
                tuple(nuevo[col] for col in _COLS_TURNO_ROTA),
            )
            creadas += 1
        con.commit()
    finally:
        con.close()
    return creadas


# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (#130 Fase 2 / ADR 0002 Fase B)                    #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA (`encolar_job`) y devuelve de inmediato; un WORKER (in-proceso en local,
# servicio aparte en hosted) CLAVA un pendiente (`reclamar_job`) y corre `claude -p`. La
# reclamacion es CONCURRENTE-SEGURA en Postgres con `FOR UPDATE SKIP LOCKED`: varios workers
# no clavan el mismo job. La cancelacion viaja por la columna `cancelado` (el back la marca;
# el worker la lee y mata el arbol), de modo que funciona AUNQUE el worker sea otro proceso.

# Estados del ciclo de la cola (distintos de los del registro de generacion).
JOB_PENDIENTE = "pendiente"
JOB_RECLAMADO = "reclamado"
JOB_TERMINADO = "terminado"

# Margen sobre el wall-timeout tras el cual un job `reclamado` se considera HUERFANO (su
# worker murio a mitad: reinicio/deploy/OOM) y OTRO worker lo RE-RECLAMA para que el trabajo
# complete solo, sin que el usuario relance. Debe SUPERAR el wall-timeout + el margen terminal
# del worker (~60 s), asi un worker VIVO que aun esta cerrando su job nunca pierde la fila
# (a esa edad la fila ya seria `terminado`, no `reclamado`). El reaper de generaciones (TTL
# 1 h) sigue como red de ultimo recurso si el re-reclamo tampoco lo saca adelante.
_RECLAIM_STALE_MARGEN_S = 300


def encolar_job(gen_id: str, spec: str) -> str:
    """Encola un job de generacion para el `gen_id` dado con su `spec` (JSON). Devuelve el job id.

    `spec` es el JSON serializable que el worker usa para reconstruir el trabajo (prompt +
    post-procesado + cwd). Idempotente por `gen_id` (indice UNICO): re-encolar el mismo
    registro no duplica filas. El back lo llama dentro de la peticion y responde al instante.

    Devuelve SIEMPRE el job id REAL de la fila (no el generado a la ligera): en un re-encolar
    del mismo `gen_id` el INSERT no inserta nada (`ON CONFLICT DO NOTHING`) y la fila viva
    conserva su id previo; devolver el id recien generado dejaria al worker actualizando un id
    inexistente (UPDATE de 0 filas). SQL estandar Postgres (NO `INSERT OR IGNORE`, que el shim
    de `motor_db` no sabe combinar con `RETURNING`): `ON CONFLICT (gen_id) DO NOTHING RETURNING
    id`; si el RETURNING viene vacio (hubo conflicto), se relee el id real con un SELECT.
    """
    job_id = uuid.uuid4().hex[:12]
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        fila = con.execute(
            "INSERT INTO jobs (id, gen_id, spec, estado, creado) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (gen_id) DO NOTHING RETURNING id",
            (job_id, gen_id, spec, JOB_PENDIENTE, ahora),
        ).fetchone()
        if fila is None:
            # Hubo conflicto (gen_id ya encolado): el INSERT no inserto. Releemos el id REAL
            # de la fila viva para que el llamante/worker operen sobre la fila correcta.
            fila = con.execute(
                "SELECT id FROM jobs WHERE gen_id = ?", (gen_id,)
            ).fetchone()
        con.commit()
    finally:
        con.close()
    return fila["id"] if fila is not None else job_id


def reclamar_job(worker: str = "") -> dict[str, Any] | None:
    """Clava UN job de forma CONCURRENTE-SEGURA y lo devuelve (None si no hay).

    `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` dentro de la transaccion + UPDATE a
    `reclamado`: otro worker que corra a la vez SALTA esa fila (no la doble-ejecuta).
    Devuelve `{id, gen_id, spec}` del job clavado.

    RE-RECLAMO DE HUERFANOS: ademas de los `pendiente`, clava los `reclamado` cuyo
    `claimed_at` es mas viejo que `wall-timeout + _RECLAIM_STALE_MARGEN_S` — su worker murio
    a mitad (reinicio/deploy/OOM) y nadie lo sacaria adelante (antes quedaba `reclamado` para
    siempre y el registro `ejecutando` -> la UI mostraba "Generando..." sin fin). El umbral
    supera el tiempo maximo que un worker VIVO retiene la fila, asi nunca se roba un job en
    curso. El UPDATE re-sella `worker`/`claimed_at`, asi un segundo abandono se vuelve a cubrir.

    GUARDIA ANTI-DUPLICADO (re-reclamo de huerfanos): un worker puede haber MUERTO DESPUES de
    fijar el estado terminal del registro (y de correr su post-procesado: `crear_borrador` es un
    INSERT fresco, NO idempotente) pero ANTES de llamar a `terminar_job` — el job queda
    `reclamado`. Re-ejecutarlo DUPLICARIA el borrador. Por eso, al re-reclamar un HUERFANO,
    consultamos el registro de generaciones: si su `gen_id` YA esta en un estado TERMINAL
    (`completado`/`error`), NO se relanza: se marca el job `terminado` y se pasa al siguiente
    (su trabajo ya se hizo). Solo afecta al re-reclamo de huerfanos; un `pendiente` nunca corrio.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    limite_huerfano = (
        datetime.now() - timedelta(seconds=config.claude_timeout() + _RECLAIM_STALE_MARGEN_S)
    ).isoformat(timespec="seconds")
    con = _conectar()
    try:
        # Acotamos los saltos: descartamos huerfanos ya-terminados (terminando su job) y
        # seguimos buscando, sin reintentar para siempre.
        for _ in range(_MAX_SALTOS_RECLAMO):
            fila = con.execute(
                "SELECT id, gen_id, spec, estado FROM jobs "
                "WHERE estado = ? OR (estado = ? AND claimed_at IS NOT NULL AND claimed_at < ?) "
                "ORDER BY creado ASC, id ASC LIMIT 1 FOR UPDATE SKIP LOCKED",
                (JOB_PENDIENTE, JOB_RECLAMADO, limite_huerfano),
            ).fetchone()
            if fila is None:
                con.commit()
                return None
            # Solo un HUERFANO (estado `reclamado`) pudo haber corrido ya su post-procesado.
            if fila["estado"] == JOB_RECLAMADO and _gen_ya_terminal(fila["gen_id"]):
                # El registro ya alcanzo estado terminal: el trabajo se hizo. Cerramos el job
                # SIN relanzarlo (evita el borrador duplicado) y buscamos el siguiente.
                con.execute(
                    "UPDATE jobs SET estado = ? WHERE id = ?", (JOB_TERMINADO, fila["id"])
                )
                con.commit()
                continue
            con.execute(
                "UPDATE jobs SET estado = ?, worker = ?, claimed_at = ? WHERE id = ?",
                (JOB_RECLAMADO, worker, ahora, fila["id"]),
            )
            con.commit()
            return {"id": fila["id"], "gen_id": fila["gen_id"], "spec": fila["spec"]}
        con.commit()
        return None
    finally:
        con.close()


# Tope de huerfanos-ya-terminados que `reclamar_job` descarta de una tirada antes de rendirse
# (cota dura para que el barrido nunca gire indefinidamente). Si hubiera mas, el siguiente
# `reclamar` los sigue limpiando.
_MAX_SALTOS_RECLAMO = 50


def _gen_ya_terminal(gen_id: str) -> bool:
    """True si el registro de generacion `gen_id` ya esta en estado TERMINAL (no `ejecutando`).

    Lee el almacen de generaciones (YAML, fuente del estado terminal que fija el worker). Import
    perezoso para no acoplar `db` con `generaciones` a nivel de modulo. Best-effort: ante
    cualquier fallo de lectura devuelve False (preferimos re-ejecutar a tragarnos un job).
    """
    try:
        from . import generaciones

        g = generaciones.obtener(gen_id)
    except Exception:  # noqa: BLE001 -- si no se puede leer el registro, no bloqueamos el reclamo.
        return False
    if g is None:
        return False
    return g.get("estado") in (generaciones.ESTADO_COMPLETADO, generaciones.ESTADO_ERROR)


def terminar_job(job_id: str) -> None:
    """Marca un job como terminado (el worker ya fijo el estado terminal del registro)."""
    con = _conectar()
    try:
        con.execute("UPDATE jobs SET estado = ? WHERE id = ?", (JOB_TERMINADO, job_id))
        con.commit()
    finally:
        con.close()


def cancelar_job(gen_id: str) -> bool:
    """Marca el job de un `gen_id` como cancelado (cross-proceso). True si habia un job.

    El back lo llama al cancelar; el worker LEE `cancelado` y mata el arbol. Tambien
    cubre el caso de un job AUN pendiente (no reclamado): el worker, al clavarlo, ve el
    flag y lo finaliza como cancelado sin lanzar `claude`. Devuelve False si no hay job
    (ya terminado o nunca encolado): el llamante cae a la cancelacion in-memoria.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE jobs SET cancelado = 1 WHERE gen_id = ? AND estado <> ?",
            (gen_id, JOB_TERMINADO),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def job_cancelado(job_id: str) -> bool:
    """True si el job esta marcado como cancelado (lo sondea el worker en ejecucion)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT cancelado FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        con.close()
    return bool(fila["cancelado"]) if fila is not None else False


# --------------------------------------------------------------------------- #
# Coordinador por turno (ola "coord"): CRUD de `rota_coordinacion`             #
# --------------------------------------------------------------------------- #
#
# Cada celda del calendario (combinacion fecha + franja_id) puede tener UN coordinador.
# Los candidatos son los usuarios con `puede_coordinar=true` (la API lo valida; aqui solo
# persistimos). UNIQUE(fecha, franja_id): un upsert reemplaza el coordinador previo.
# La coordinacion es INDEPENDIENTE del turno de CM: borrar un turno o cambiar franja NO
# borra la coordinacion (el admin la mantiene aparte).

_COLS_COORDINACION = (
    "id", "lunes", "fecha", "franja_id", "coordinador_id", "creado", "actualizado",
)
_SELECT_COORDINACION = f"SELECT {', '.join(_COLS_COORDINACION)} FROM rota_coordinacion"


def _fila_a_coordinacion(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_COORDINACION}


def listar_coordinacion_semana(lunes: str) -> list[dict[str, Any]]:
    """Coordinaciones de la semana cuyo lunes es `lunes`, ordenadas por fecha y franja."""
    if not lunes:
        return []
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_COORDINACION} WHERE lunes = ? ORDER BY fecha ASC, franja_id ASC",
            (lunes,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_coordinacion(f) for f in filas]


def set_coordinador_rota(
    lunes: str, fecha: str, franja_id: str, coordinador_id: str
) -> dict[str, Any]:
    """UPSERT por (fecha, franja_id): asigna `coordinador_id` a la celda; devuelve la fila.

    Si ya hay coordinador en esa celda, se REEMPLAZA (actualiza `coordinador_id` y
    `actualizado`). Si no hay, se crea con `creado` = `actualizado` = ahora. La capa API
    valida que `coordinador_id` corresponda a un usuario con `puede_coordinar=true`.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        fila_existente = con.execute(
            "SELECT id FROM rota_coordinacion WHERE fecha = ? AND franja_id = ?",
            (fecha, franja_id),
        ).fetchone()
        if fila_existente is not None:
            con.execute(
                "UPDATE rota_coordinacion SET coordinador_id = ?, lunes = ?, "
                "actualizado = ? WHERE id = ?",
                (coordinador_id, lunes, ahora, fila_existente["id"]),
            )
            con.commit()
            fila = con.execute(
                f"{_SELECT_COORDINACION} WHERE id = ?", (fila_existente["id"],)
            ).fetchone()
            return _fila_a_coordinacion(fila)
        nuevo_id = uuid.uuid4().hex[:12]
        con.execute(
            "INSERT INTO rota_coordinacion "
            "(id, lunes, fecha, franja_id, coordinador_id, creado, actualizado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nuevo_id, lunes, fecha, franja_id, coordinador_id, ahora, ahora),
        )
        con.commit()
        fila = con.execute(
            f"{_SELECT_COORDINACION} WHERE id = ?", (nuevo_id,)
        ).fetchone()
        return _fila_a_coordinacion(fila)
    finally:
        con.close()


def quitar_coordinador_rota(fecha: str, franja_id: str) -> bool:
    """Borra la coordinacion de la celda (fecha, franja_id). True si habia algo que borrar."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM rota_coordinacion WHERE fecha = ? AND franja_id = ?",
            (fecha, franja_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# PARRILLA: propuestas de importacion desde documento (#parrilla-import)        #
# --------------------------------------------------------------------------- #
#
# Una `parrilla_propuesta` es el resultado ESTACIONADO de un `claude -p` que leyo un documento
# y propuso operaciones (eventos/turnos nuevos, modificaciones). NO se aplica hasta que el
# usuario acepta: entonces `aplicar_propuesta_parrilla` aplica TODO el diff en UNA transaccion
# reusando las MISMAS tablas (`rota_eventos`/`rota_turnos`) que los endpoints de la rota.

_COLS_PROPUESTA = (
    "id",
    "creado",
    "actualizado",
    "estado",
    "autor_id",
    "autor_nombre",
    "doc_nombre",
    "doc_tipo",
    "semana",
    "gen_id",
    "operaciones",
    "resumen",
    "error",
)
_SELECT_PROPUESTA = f"SELECT {', '.join(_COLS_PROPUESTA)} FROM parrilla_propuesta"

# Campos editables via `actualizar_propuesta_parrilla` (allowlist). `id`/`creado` no se tocan;
# `actualizado` lo gestiona el sistema.
_CAMPOS_EDITABLES_PROPUESTA: tuple[str, ...] = (
    "estado",
    "operaciones",
    "resumen",
    "error",
    "doc_nombre",
    "doc_tipo",
    "gen_id",
)


def _fila_a_propuesta(fila: Any) -> dict[str, Any]:
    """Fila de `parrilla_propuesta` -> dict publico. `operaciones` se deserializa de JSON.

    `operaciones` vive como TEXT JSON ("" si el job aun no termino); lo exponemos como lista
    (o None si esta vacio) para que la API no tenga que (de)serializar.
    """
    p = {col: fila[col] for col in _COLS_PROPUESTA}
    crudo = p.get("operaciones") or ""
    if crudo:
        try:
            cargado = json.loads(crudo)
            p["operaciones"] = cargado if isinstance(cargado, list) else None
        except (json.JSONDecodeError, ValueError):
            p["operaciones"] = None
    else:
        p["operaciones"] = None
    return p


def crear_propuesta_parrilla(
    *,
    semana: str,
    doc_nombre: str,
    doc_tipo: str = "",
    gen_id: str = "",
    autor_id: str = "",
    autor_nombre: str = "",
    estado: str = "generando",
) -> dict[str, Any]:
    """Crea una propuesta en estado `generando` y la devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex,
        "creado": ahora,
        "actualizado": ahora,
        "estado": estado,
        "autor_id": autor_id or "",
        "autor_nombre": autor_nombre or "",
        "doc_nombre": doc_nombre or "",
        "doc_tipo": doc_tipo or "",
        "semana": semana or "",
        "gen_id": gen_id or "",
        "operaciones": "",
        "resumen": "",
        "error": "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PROPUESTA)
        con.execute(
            f"INSERT INTO parrilla_propuesta ({', '.join(_COLS_PROPUESTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PROPUESTA),
        )
        con.commit()
    finally:
        con.close()
    fila["operaciones"] = None
    return fila


def obtener_propuesta_parrilla(propuesta_id: str) -> dict[str, Any] | None:
    """Una propuesta por id; None si no existe."""
    if not propuesta_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PROPUESTA} WHERE id = ?", (propuesta_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_propuesta(fila) if fila is not None else None


def listar_propuestas_parrilla(
    *, estado: str | None = None, limite: int = 100
) -> list[dict[str, Any]]:
    """Propuestas mas recientes primero; filtro opcional por `estado`."""
    sql = _SELECT_PROPUESTA
    params: list[Any] = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    sql += " ORDER BY creado DESC, id DESC LIMIT ?"
    params.append(int(limite))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_propuesta(f) for f in filas]


def actualizar_propuesta_parrilla(
    propuesta_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita una propuesta (allowlist `_CAMPOS_EDITABLES_PROPUESTA`); None si el id no existe.

    `operaciones` puede llegar como lista (se serializa a JSON) o como str ya serializado.
    Pone `actualizado` a ahora.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PROPUESTA}
    if "operaciones" in cambios and not isinstance(cambios["operaciones"], str):
        cambios["operaciones"] = json.dumps(cambios["operaciones"] or [], ensure_ascii=False)
    if not cambios:
        return obtener_propuesta_parrilla(propuesta_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(propuesta_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE parrilla_propuesta SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_PROPUESTA} WHERE id = ?", (propuesta_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_propuesta(fila) if fila is not None else None


def aplicar_propuesta_parrilla(
    propuesta_id: str,
    operaciones: list[dict[str, Any]],
    *,
    nombres_miembros: dict[str, str],
    origen: str = "import-doc",
) -> dict[str, Any]:
    """Aplica TODAS las `operaciones` (ya validadas) en UNA transaccion y marca aplicada.

    Reusa las MISMAS tablas que la rota (`rota_eventos`/`rota_turnos`) con un SOLO `_conectar()`
    para que el diff sea atomico (todo o nada): si algo revienta, `_ConexionPg` hace rollback y
    NADA queda escrito. Cada fila creada se etiqueta con `origen`/`origen_ref` (provenance).
    `nombres_miembros` resuelve el nombre vivo del miembro (el snapshot de la op puede estar
    desactualizado). Devuelve un resumen `{eventos_creados, turnos_creados, turnos_modificados,
    ids:{...}}`. NO re-valida (la API ya lo hizo contra la BD viva ANTES de llamar aqui).

    RANGO / FRANJA POR NOMBRE (PERMISIVO): cada `crear_turno` trae `franja` (NOMBRE de slot,
    p.ej. "Mañana") y una fecha cualquiera. Calcula su semana (`lunes`) y resuelve el NOMBRE ->
    el `franja_id` de esa semana (match normalizado case/space-insensitive). Si el nombre NO
    existe esa semana, CREA la franja en la misma transaccion (un día puede tener 3+ franjas y
    el documento puede traer slots nuevos), con el horario `franja_inicio/fin` del documento si
    vino. NO rechaza por plantilla. Cacheamos el mapa nombre->id por semana.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    eventos_creados: list[str] = []
    turnos_creados: list[str] = []
    turnos_modificados: list[str] = []
    # Cache por semana del mapa {nombre_normalizado -> franja_id} (siembra defaults una vez).
    franjas_por_semana: dict[str, dict[str, str]] = {}

    def _franja_id_de(
        con: Any, semana: str, nombre: str, *, inicio: str = "", fin: str = ""
    ) -> str:
        """Resuelve `nombre` de slot -> `franja_id` de `semana`. PERMISIVO: si el nombre no
        existe en esa semana, CREA la franja (un día puede tener 3+ franjas y el documento
        puede traer slots nuevos), usando `inicio`/`fin` si vienen o un horario por defecto.
        `es_descanso` se infiere del nombre. No rechaza nada por plantilla."""
        if semana not in franjas_por_semana:
            # Cargamos las franjas YA existentes de la semana (sin sembrar: no imponemos la
            # plantilla por defecto; solo creamos las que el documento realmente use).
            filas = con.execute(
                "SELECT id, nombre FROM rota_franjas WHERE lunes = ?", (semana,)
            ).fetchall()
            franjas_por_semana[semana] = {
                str(f["nombre"]).strip().lower(): f["id"] for f in filas
            }
        clave = (nombre or "").strip().lower()
        fid = franjas_por_semana[semana].get(clave)
        if fid:
            return fid
        # No existe: la creamos en ESTA transacción (orden = nº de franjas ya en la semana).
        nuevo_id = uuid.uuid4().hex[:12]
        es_descanso = "descanso" in clave
        con.execute(
            "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                nuevo_id,
                semana,
                nombre.strip(),
                (inicio or "").strip() or "00:00",
                (fin or "").strip() or "23:59",
                len(franjas_por_semana[semana]),
                es_descanso,
            ),
        )
        franjas_por_semana[semana][clave] = nuevo_id
        return fid or nuevo_id

    con = _conectar()
    try:
        for op in operaciones:
            tipo = op.get("tipo")
            if tipo == "crear_evento":
                eid = uuid.uuid4().hex[:12]
                con.execute(
                    "INSERT INTO rota_eventos "
                    "(id, titulo, fecha, hora, contenido, nota, tipo_cobertura, prioridad, "
                    "cambiado, actualizado, creado, origen, origen_ref) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        eid,
                        str(op.get("titulo", "")),
                        str(op.get("fecha", "")),
                        str(op.get("hora") or ""),
                        str(op.get("contenido") or ""),
                        str(op.get("nota") or ""),
                        str(op.get("tipo_cobertura") or "transmision"),
                        str(op.get("prioridad") or "media"),
                        0,
                        ahora,
                        ahora,
                        origen,
                        propuesta_id,
                    ),
                )
                eventos_creados.append(eid)
            elif tipo == "crear_turno":
                tid = uuid.uuid4().hex[:12]
                miembro_id = str(op.get("miembro_id", ""))
                semana = _lunes_iso_de(op.get("fecha", ""))
                # Resuelve el NOMBRE de slot -> franja_id de ESA semana (CREA la franja si no
                # existe, con el horario del documento si vino).
                franja_id = _franja_id_de(
                    con,
                    semana,
                    str(op.get("franja", "")),
                    inicio=str(op.get("franja_inicio") or ""),
                    fin=str(op.get("franja_fin") or ""),
                )
                con.execute(
                    "INSERT INTO rota_turnos "
                    "(id, semana, fecha, miembro_id, miembro_nombre, franja_id, estado, "
                    "override, motivo, nota_relevo, creado, actualizado, origen, origen_ref) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tid,
                        semana,
                        str(op.get("fecha", "")),
                        miembro_id,
                        nombres_miembros.get(miembro_id, str(op.get("miembro_nombre") or "")),
                        franja_id,
                        ESTADO_ROTA_PROPUESTO,
                        0,
                        str(op.get("motivo") or ""),
                        str(op.get("nota_relevo") or ""),
                        ahora,
                        ahora,
                        origen,
                        propuesta_id,
                    ),
                )
                turnos_creados.append(tid)
            elif tipo == "modificar_turno":
                turno_id = str(op.get("turno_id", ""))
                cambios_op = op.get("cambios") or {}
                asignaciones: list[str] = []
                valores: list[Any] = []
                if cambios_op.get("miembro_id") not in (None, ""):
                    mid = str(cambios_op["miembro_id"])
                    asignaciones.append("miembro_id = ?")
                    valores.append(mid)
                    asignaciones.append("miembro_nombre = ?")
                    valores.append(
                        nombres_miembros.get(mid, str(cambios_op.get("miembro_nombre") or ""))
                    )
                elif cambios_op.get("miembro_nombre") not in (None, ""):
                    asignaciones.append("miembro_nombre = ?")
                    valores.append(str(cambios_op["miembro_nombre"]))
                if cambios_op.get("estado") not in (None, ""):
                    asignaciones.append("estado = ?")
                    valores.append(str(cambios_op["estado"]))
                if cambios_op.get("override") is not None:
                    asignaciones.append("override = ?")
                    valores.append(1 if cambios_op["override"] else 0)
                if cambios_op.get("motivo") is not None:
                    asignaciones.append("motivo = ?")
                    valores.append(str(cambios_op["motivo"]))
                if cambios_op.get("nota_relevo") is not None:
                    asignaciones.append("nota_relevo = ?")
                    valores.append(str(cambios_op["nota_relevo"]))
                # Provenance del cambio (no toca filas de alta manual: solo las que tocamos aqui).
                asignaciones.append("origen = ?")
                valores.append(origen)
                asignaciones.append("origen_ref = ?")
                valores.append(propuesta_id)
                asignaciones.append("actualizado = ?")
                valores.append(ahora)
                valores.append(turno_id)
                con.execute(
                    f"UPDATE rota_turnos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
                    tuple(valores),
                )
                turnos_modificados.append(turno_id)
        # Marca la propuesta como aplicada DENTRO de la misma transaccion (atomico con el diff).
        con.execute(
            "UPDATE parrilla_propuesta SET estado = ?, actualizado = ? WHERE id = ?",
            ("aplicada", ahora, propuesta_id),
        )
        con.commit()
    finally:
        con.close()
    return {
        "eventos_creados": len(eventos_creados),
        "turnos_creados": len(turnos_creados),
        "turnos_modificados": len(turnos_modificados),
        "ids": {
            "eventos": eventos_creados,
            "turnos": turnos_creados,
            "turnos_modificados": turnos_modificados,
        },
    }


def _lunes_iso_de(fecha_iso: str) -> str:
    """Lunes (ISO) de la semana que contiene `fecha_iso`; "" si no parsea. Sin dep a `rota`."""
    try:
        d = date.fromisoformat(fecha_iso)
    except (ValueError, TypeError):
        return ""
    return (d - timedelta(days=d.weekday())).isoformat()


# --------------------------------------------------------------------------- #
# Insumos del día (cajones) — tabla `insumos_lote` + `insumos_item`            #
# Contrato: docs/maquina-contenido/01-insumos-del-dia.md                       #
# --------------------------------------------------------------------------- #

_COLS_INSUMO_LOTE = (
    "id", "fecha", "cajon", "marca", "origen_texto", "origen_archivo",
    "estado", "error", "total_items", "creado_por", "creado",
)
_SELECT_INSUMO_LOTE = f"SELECT {', '.join(_COLS_INSUMO_LOTE)} FROM insumos_lote"

_COLS_INSUMO_ITEM = (
    "id", "lote_id", "fecha", "cajon", "marca", "linea",
    "titulo", "resumen", "hora", "lugar", "estado_material",
    "tipo", "idioma", "usado", "contenido_id", "orden", "creado",
)
_SELECT_INSUMO_ITEM = f"SELECT {', '.join(_COLS_INSUMO_ITEM)} FROM insumos_item"

_CAMPOS_EDITABLES_INSUMO_ITEM: tuple[str, ...] = (
    "titulo", "resumen", "marca", "linea", "hora", "lugar", "estado_material", "tipo",
)


def _fila_a_insumo_lote(fila: Any) -> dict[str, Any]:
    """Fila de `insumos_lote` -> dict público (`usado` y enteros normalizados)."""
    return {
        "id": fila["id"],
        "fecha": fila["fecha"] or "",
        "cajon": fila["cajon"] or "",
        "marca": fila["marca"] or "",
        "origen_texto": fila["origen_texto"] or "",
        "origen_archivo": fila["origen_archivo"] or "",
        "estado": fila["estado"] or "listo",
        "error": fila["error"] or "",
        "total_items": int(fila["total_items"] or 0),
        "creado_por": fila["creado_por"] or "",
        "creado": fila["creado"] or "",
    }


def _fila_a_insumo_item(fila: Any) -> dict[str, Any]:
    """Fila de `insumos_item` -> dict público (`usado` como bool)."""
    return {
        "id": fila["id"],
        "lote_id": fila["lote_id"] or "",
        "fecha": fila["fecha"] or "",
        "cajon": fila["cajon"] or "",
        "marca": fila["marca"] or "",
        "linea": fila["linea"] or "",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "hora": fila["hora"] or "",
        "lugar": fila["lugar"] or "",
        "estado_material": fila["estado_material"] or "",
        "tipo": fila["tipo"] or "nota",
        "idioma": fila["idioma"] or "es",
        "usado": bool(fila["usado"]),
        "contenido_id": fila["contenido_id"] or "",
        "orden": int(fila["orden"] or 0),
        "creado": fila["creado"] or "",
    }


def crear_insumo_lote(
    *,
    fecha: str,
    cajon: str,
    marca: str = "",
    origen_texto: str = "",
    origen_archivo: str = "",
    estado: str = "listo",
    error: str = "",
    total_items: int = 0,
    creado_por: str = "",
) -> dict[str, Any]:
    """Crea un lote de insumos y lo devuelve."""
    ahora = datetime.now().isoformat(timespec="microseconds")
    lote_id = uuid.uuid4().hex[:16]
    fila = {
        "id": lote_id,
        "fecha": fecha or "",
        "cajon": cajon or "",
        "marca": marca or "",
        "origen_texto": origen_texto or "",
        "origen_archivo": origen_archivo or "",
        "estado": estado or "listo",
        "error": error or "",
        "total_items": int(total_items),
        "creado_por": creado_por or "",
        "creado": ahora,
    }
    marcadores = ", ".join("?" for _ in _COLS_INSUMO_LOTE)
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO insumos_lote ({', '.join(_COLS_INSUMO_LOTE)}) VALUES ({marcadores})",
            tuple(fila[c] for c in _COLS_INSUMO_LOTE),
        )
        con.commit()
    finally:
        con.close()
    return obtener_insumo_lote(lote_id) or _fila_a_insumo_lote(fila)


def actualizar_insumo_lote(lote_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un lote (estado/error/total_items). None si no existe."""
    permitidos = {"estado", "error", "total_items"}
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return obtener_insumo_lote(lote_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), lote_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE insumos_lote SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_lote(lote_id)


def obtener_insumo_lote(lote_id: str) -> dict[str, Any] | None:
    """Un lote por id; None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INSUMO_LOTE} WHERE id = ?", (lote_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_insumo_lote(fila) if fila is not None else None


def borrar_insumo_lote(lote_id: str) -> bool:
    """Borra el lote y todos sus ítems; True si existía, False si no."""
    con = _conectar()
    try:
        con.execute("DELETE FROM insumos_item WHERE lote_id = ?", (lote_id,))
        cur = con.execute("DELETE FROM insumos_lote WHERE id = ?", (lote_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def crear_insumo_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta múltiples ítems en lote (bulk); devuelve los dicts insertados.

    Cada dict debe contener al menos: `lote_id`, `fecha`, `cajon`, `titulo`.
    Los campos ausentes reciben sus valores por defecto.
    """
    ahora = datetime.now().isoformat(timespec="microseconds")
    marcadores = ", ".join("?" for _ in _COLS_INSUMO_ITEM)
    insertados: list[dict[str, Any]] = []
    con = _conectar()
    try:
        for i, item in enumerate(items):
            item_id = uuid.uuid4().hex[:16]
            fila = {
                "id": item_id,
                "lote_id": item.get("lote_id") or "",
                "fecha": item.get("fecha") or "",
                "cajon": item.get("cajon") or "",
                "marca": item.get("marca") or "",
                "linea": item.get("linea") or "",
                "titulo": item.get("titulo") or "",
                "resumen": item.get("resumen") or "",
                "hora": item.get("hora") or "",
                "lugar": item.get("lugar") or "",
                "estado_material": item.get("estado_material") or "",
                "tipo": item.get("tipo") or "nota",
                "idioma": item.get("idioma") or "es",
                "usado": 0,
                "contenido_id": "",
                "orden": item.get("orden", i),
                "creado": ahora,
            }
            con.execute(
                f"INSERT INTO insumos_item ({', '.join(_COLS_INSUMO_ITEM)}) VALUES ({marcadores})",
                tuple(fila[c] for c in _COLS_INSUMO_ITEM),
            )
            insertados.append(_fila_a_insumo_item(fila))
        con.commit()
    finally:
        con.close()
    return insertados


def listar_insumo_items(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
    marca: str | None = None,
    lote_id: str | None = None,
) -> list[dict[str, Any]]:
    """Lista ítems con filtros opcionales, ordenados por (orden ASC, creado ASC)."""
    sql = _SELECT_INSUMO_ITEM
    params: list[Any] = []
    condiciones: list[str] = []
    if fecha is not None:
        condiciones.append("fecha = ?")
        params.append(fecha)
    if cajon is not None:
        condiciones.append("cajon = ?")
        params.append(cajon)
    if marca is not None:
        condiciones.append("marca = ?")
        params.append(marca)
    if lote_id is not None:
        condiciones.append("lote_id = ?")
        params.append(lote_id)
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY orden ASC, creado ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_insumo_item(f) for f in filas]


def obtener_insumo_item(item_id: str) -> dict[str, Any] | None:
    """Un ítem por id; None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INSUMO_ITEM} WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_insumo_item(fila) if fila is not None else None


def actualizar_insumo_item(item_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un ítem (campos editables del contrato). None si no existe."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_INSUMO_ITEM}
    if not cambios:
        return obtener_insumo_item(item_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), item_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE insumos_item SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_item(item_id)


def marcar_insumo_item_usado(
    item_id: str, *, contenido_id: str
) -> dict[str, Any] | None:
    """Marca un ítem como usado y guarda el `contenido_id`. None si no existe."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE insumos_item SET usado = 1, contenido_id = ? WHERE id = ?",
            (contenido_id, item_id),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_item(item_id)


def listar_lotes(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
) -> list[dict[str, Any]]:
    """Lista lotes con filtros opcionales (fecha/cajón), más recientes primero."""
    sql = _SELECT_INSUMO_LOTE
    params: list[Any] = []
    condiciones: list[str] = []
    if fecha is not None:
        condiciones.append("fecha = ?")
        params.append(fecha)
    if cajon is not None:
        condiciones.append("cajon = ?")
        params.append(cajon)
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY creado DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_insumo_lote(f) for f in filas]


def dias_con_insumos() -> list[dict[str, Any]]:
    """Fechas distintas con insumos + total de ítems y desglose por cajón.

    Devuelve lista de dicts `{fecha, total, por_cajon:{portal,corresponsales,reporteros,eventos_claro}}`,
    ordenada por fecha desc. Cuenta ítems (no lotes) para reflejar el volumen editorial real.
    """
    cajones_fijos = ("portal", "corresponsales", "reporteros", "eventos_claro")
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT fecha, cajon, COUNT(*) AS n FROM insumos_item GROUP BY fecha, cajon"
        ).fetchall()
    finally:
        con.close()

    # Agrupa por fecha.
    por_fecha: dict[str, dict[str, int]] = {}
    for f in filas:
        fecha = f["fecha"] or ""
        cajon = f["cajon"] or ""
        n = int(f["n"] or 0)
        if fecha not in por_fecha:
            por_fecha[fecha] = {}
        por_fecha[fecha][cajon] = por_fecha[fecha].get(cajon, 0) + n

    resultado: list[dict[str, Any]] = []
    for fecha in sorted(por_fecha.keys(), reverse=True):
        conteos = por_fecha[fecha]
        por_cajon = {c: conteos.get(c, 0) for c in cajones_fijos}
        resultado.append({
            "fecha": fecha,
            "total": sum(por_cajon.values()),
            "por_cajon": por_cajon,
        })
    return resultado


# --------------------------------------------------------------------------- #
# Agentes de investigacion (Ola 6): briefs + candidatos                        #
# --------------------------------------------------------------------------- #

_COLS_INV_BRIEF = (
    "id", "nombre", "marca", "linea", "instrucciones", "idiomas", "activo", "creado",
)
_SELECT_INV_BRIEF = f"SELECT {', '.join(_COLS_INV_BRIEF)} FROM inv_brief"
_CAMPOS_EDITABLES_INV_BRIEF: tuple[str, ...] = (
    "nombre", "marca", "linea", "instrucciones", "idiomas", "activo",
)

_COLS_INV_CANDIDATO = (
    "id", "brief_id", "fecha", "marca", "linea", "titulo", "resumen",
    "por_que", "fuente", "enlace", "idioma", "estado", "contenido_id", "creado",
)
_SELECT_INV_CANDIDATO = f"SELECT {', '.join(_COLS_INV_CANDIDATO)} FROM inv_candidato"


def _fila_a_inv_brief(fila: Any) -> dict[str, Any]:
    """Fila de `inv_brief` -> dict publico."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"] or "",
        "marca": fila["marca"] or "",
        "linea": fila["linea"] or "",
        "instrucciones": fila["instrucciones"] or "",
        "idiomas": fila["idiomas"] or "",
        "activo": bool(int(fila["activo"] or 0)),
        "creado": fila["creado"] or "",
    }


def _fila_a_inv_candidato(fila: Any) -> dict[str, Any]:
    """Fila de `inv_candidato` -> dict publico."""
    return {
        "id": fila["id"],
        "brief_id": fila["brief_id"] or "",
        "fecha": fila["fecha"] or "",
        "marca": fila["marca"] or "",
        "linea": fila["linea"] or "",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "por_que": fila["por_que"] or "",
        "fuente": fila["fuente"] or "",
        "enlace": fila["enlace"] or "",
        "idioma": fila["idioma"] or "es",
        "estado": fila["estado"] or "nuevo",
        "contenido_id": fila["contenido_id"] or "",
        "creado": fila["creado"] or "",
    }


def crear_inv_brief(
    *,
    nombre: str,
    marca: str = "",
    linea: str = "",
    instrucciones: str,
    idiomas: str = "",
) -> dict[str, Any]:
    """Crea un brief de investigacion (activo=1) y lo devuelve."""
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "marca": marca or "",
        "linea": linea or "",
        "instrucciones": instrucciones or "",
        "idiomas": idiomas or "",
        "activo": 1,
        "creado": datetime.now().isoformat(timespec="microseconds"),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_INV_BRIEF)
        con.execute(
            f"INSERT INTO inv_brief ({', '.join(_COLS_INV_BRIEF)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_INV_BRIEF),
        )
        con.commit()
    finally:
        con.close()
    return obtener_inv_brief(fila["id"]) or _fila_a_inv_brief(fila)


def listar_inv_briefs(*, solo_activos: bool = False) -> list[dict[str, Any]]:
    """Briefs de investigacion (mas recientes primero), opcionalmente solo los activos."""
    sql = _SELECT_INV_BRIEF
    params: list[Any] = []
    if solo_activos:
        sql += " WHERE activo = 1"
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_inv_brief(f) for f in filas]


def obtener_inv_brief(brief_id: str) -> dict[str, Any] | None:
    """Un brief de investigacion por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INV_BRIEF} WHERE id = ?", (brief_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_inv_brief(fila) if fila is not None else None


def actualizar_inv_brief(brief_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un brief. None si no existe."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_INV_BRIEF}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_inv_brief(brief_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), brief_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE inv_brief SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_inv_brief(brief_id)


def borrar_inv_brief(brief_id: str) -> bool:
    """Borra un brief; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM inv_brief WHERE id = ?", (brief_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def crear_inv_candidatos(candidatos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta una lista de candidatos en bloque y devuelve los insertados (con id del SELECT).

    Cada dict debe traer las claves de `_COLS_INV_CANDIDATO` menos `id` y `creado`
    (que se generan aqui). El orden de insercion se preserva; un error en un item
    individual no aborta los restantes (best-effort, loguea y continua).
    """
    ahora = datetime.now().isoformat(timespec="microseconds")
    ids: list[str] = []
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_INV_CANDIDATO)
        for cand in candidatos:
            cand_id = uuid.uuid4().hex[:12]
            fila = {
                "id": cand_id,
                "brief_id": str(cand.get("brief_id") or ""),
                "fecha": str(cand.get("fecha") or ""),
                "marca": str(cand.get("marca") or ""),
                "linea": str(cand.get("linea") or ""),
                "titulo": str(cand.get("titulo") or ""),
                "resumen": str(cand.get("resumen") or ""),
                "por_que": str(cand.get("por_que") or ""),
                "fuente": str(cand.get("fuente") or ""),
                "enlace": str(cand.get("enlace") or ""),
                "idioma": str(cand.get("idioma") or "es"),
                "estado": str(cand.get("estado") or "nuevo"),
                "contenido_id": str(cand.get("contenido_id") or ""),
                "creado": ahora,
            }
            try:
                con.execute(
                    f"INSERT INTO inv_candidato ({', '.join(_COLS_INV_CANDIDATO)}) "
                    f"VALUES ({marcadores})",
                    tuple(fila[col] for col in _COLS_INV_CANDIDATO),
                )
                ids.append(cand_id)
            except Exception:  # noqa: BLE001 -- un candidato malo no tumba el lote
                _log.warning("crear_inv_candidatos: error insertando candidato; se omite.")
        con.commit()
    finally:
        con.close()
    # Recupera los insertados del SELECT (orden natural por creado).
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    con2 = _conectar()
    try:
        filas = con2.execute(
            f"{_SELECT_INV_CANDIDATO} WHERE id IN ({placeholders}) "  # noqa: S608 -- ids generados internamente
            "ORDER BY creado ASC, id ASC",
            tuple(ids),
        ).fetchall()
    finally:
        con2.close()
    return [_fila_a_inv_candidato(f) for f in filas]


def listar_inv_candidatos(
    *,
    fecha: str | None = None,
    marca: str | None = None,
    estado: str | None = None,
    brief_id: str | None = None,
) -> list[dict[str, Any]]:
    """Candidatos de investigacion (mas recientes primero), filtrables."""
    sql = _SELECT_INV_CANDIDATO
    params: list[Any] = []
    condiciones: list[str] = []
    if fecha:
        condiciones.append("fecha = ?")
        params.append(fecha)
    if marca:
        condiciones.append("marca = ?")
        params.append(marca)
    if estado:
        condiciones.append("estado = ?")
        params.append(estado)
    if brief_id:
        condiciones.append("brief_id = ?")
        params.append(brief_id)
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()  # noqa: S608 -- params parametrizados
    finally:
        con.close()
    return [_fila_a_inv_candidato(f) for f in filas]


def obtener_inv_candidato(candidato_id: str) -> dict[str, Any] | None:
    """Un candidato de investigacion por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INV_CANDIDATO} WHERE id = ?", (candidato_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_inv_candidato(fila) if fila is not None else None


def actualizar_inv_candidato(
    candidato_id: str,
    *,
    estado: str | None = None,
    contenido_id: str | None = None,
) -> dict[str, Any] | None:
    """Actualiza estado y/o contenido_id de un candidato. None si no existe."""
    cambios: dict[str, Any] = {}
    if estado is not None:
        cambios["estado"] = estado
    if contenido_id is not None:
        cambios["contenido_id"] = contenido_id
    if not cambios:
        return obtener_inv_candidato(candidato_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), candidato_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE inv_candidato SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_inv_candidato(candidato_id)

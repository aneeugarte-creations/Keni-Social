"""DDL del esquema operacional y orquestacion de creacion/migracion (bajo advisory lock).

`_DDL_ESQUEMA` (fuente de verdad de la FORMA del esquema), `_crear_esquema`/
`_crear_esquema_bajo_lock` (DDL + migraciones VERSIONADAS PRE/POST) y `arrancar_persistencia`.
Extraido de `_db_core.py` al trocearlo por areas (refactor de pura reubicacion). Lee
`MIGRACIONES_PRE_DDL`/`MIGRACIONES_POST_DDL` a traves del paquete (`_nucleo`) para que el
monkeypatch de los tests sobre `_db_core.MIGRACIONES_POST_DDL` siga surtiendo efecto.
"""
from __future__ import annotations

from typing import Any

import keni_consola._db_core as _nucleo

from ._comun import _log
from .conexion import _LOCK_NS_BARRIDO, _clave_lock, _conectar
from .migraciones import _DDL_SCHEMA_MIGRACIONES, _aplicar_migraciones
from .migraciones_columnas import _crear_indices_unicos_idempotencia, _dedup_turnos_rota

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
        ts              timestamptz NOT NULL,
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
        ts                             timestamptz NOT NULL,
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
        -- FECHAS NATIVAS (migracion 0033): timestamptz, UTC. Vuelven como `datetime` aware con
        -- `dict_row`; el serializador `_fila_a_contenido` las re-emite al canon ISO via
        -- `tiempo.iso_o_vacio` (contrato TEXT historico intacto). El keyset del feed compara
        -- `creado` de forma nativa; el repo siempre escribe un valor (nunca el sentinel vacio).
        creado              timestamptz,
        actualizado         timestamptz,
        -- CONCURRENCIA OPTIMISTA (ADR 0012): contador que sube en CADA escritura del repo
        -- (`actualizar_contenido`/transiciones). El cliente puede pasar la `version` que leyo;
        -- si llego obsoleta (otra escritura adelanto el contador), la actualizacion se rechaza
        -- con `ConflictoVersion` en vez de pisar el cambio (p. ej. el pipeline pisando un
        -- rechazo humano). Para BDs existentes lo anade la migracion 0030.
        version             INTEGER NOT NULL DEFAULT 0
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
        actualizado           TEXT NOT NULL DEFAULT '',
        -- CONCURRENCIA OPTIMISTA (ADR 0012): ver el comentario en `contenido.version`. Sube en
        -- cada `actualizar_contenido_plataforma`/`transicionar_estado_publicacion`. Migracion 0030.
        version               INTEGER NOT NULL DEFAULT 0
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
        -- `spec`: JSON del job (prompt + post-procesado + cwd). `jsonb` (ADR 0012): se lee ENTERO
        -- y se querria poder consultar; con `dict_row` vuelve ya como dict. La app sigue pasando
        -- el JSON serializado (str) al insertar (Postgres lo castea) y `jobspec.deserializar`
        -- acepta dict-o-str. Para BDs existentes lo convierte la migracion 0031.
        spec        jsonb NOT NULL,
        estado      TEXT NOT NULL DEFAULT 'pendiente',
        cancelado   INTEGER NOT NULL DEFAULT 0,
        worker      TEXT NOT NULL DEFAULT '',
        -- FECHAS NATIVAS (migracion 0033): timestamptz, UTC. `creado` ordena el despacho
        -- (FIFO por prioridad); `claimed_at` es NULL mientras el job no se ha reclamado (antes
        -- el sentinel ''). El re-reclamo de huerfanos compara `claimed_at` de forma nativa.
        creado      timestamptz,
        claimed_at  timestamptz
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
        -- DIA NATIVO (migracion 0033): `date` (YYYY-MM-DD, UTC). Vuelve como `date` con
        -- `dict_row`; `gasto_ia_por_dia` lo re-emite con `iso_o_vacio`. El SUM del corte de
        -- presupuesto agrupa/filtra por `dia` de forma nativa (params en formato YYYY-MM-DD).
        dia         date,
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
    # PROMPT CACHING: tokens leidos de cache y de creacion de cache de cada generacion cerrada,
    # para medir si el caching ocurre y el ahorro que produce (un cache_read alto = mucho contexto
    # reutilizado sin re-cobrar). Migracion idempotente (mismo patron que prompt_chars).
    "ALTER TABLE gasto_ia ADD COLUMN IF NOT EXISTS cache_read BIGINT NOT NULL DEFAULT 0",
    "ALTER TABLE gasto_ia ADD COLUMN IF NOT EXISTS cache_creation BIGINT NOT NULL DEFAULT 0",
    # Modelo concreto que gastó (id del proveedor). Para imagenes permite estimar el coste
    # medio por imagen POR MODELO; legados/claude => '' (cae a la media global). Idempotente.
    "ALTER TABLE gasto_ia ADD COLUMN IF NOT EXISTS modelo TEXT NOT NULL DEFAULT ''",
    # INDICE de GENERACIONES (ADR 0012, rendimiento): el registro de cada generacion vive en un
    # YAML (fuente de verdad del DETALLE: prompt/razonamiento/stream). Listar Actividad IA /
    # Pipelines parseaba TODOS los ~2000 YAML por peticion. Este indice replica los campos LIGEROS
    # del listado para paginar por SQL sin tocar disco; el YAML se lee solo para el detalle. Lo
    # mantiene `generaciones._almacen` al crear/actualizar/borrar/podar (best-effort; el YAML
    # manda) y un backfill idempotente al primer uso. `payload` (jsonb) = el dict publico ligero
    # (sin prompt/razonamiento) que devuelve `listar`. Migracion 0032 para BDs ya creadas.
    """
    CREATE TABLE IF NOT EXISTS generaciones_indice (
        gen_id        TEXT PRIMARY KEY,
        fecha_inicio  TEXT NOT NULL DEFAULT '',
        estado        TEXT NOT NULL DEFAULT '',
        tipo          TEXT NOT NULL DEFAULT '',
        marca         TEXT NOT NULL DEFAULT '',
        proceso       TEXT NOT NULL DEFAULT '',
        contenido_id  TEXT NOT NULL DEFAULT '',
        payload       jsonb NOT NULL DEFAULT '{}',
        actualizado   TEXT NOT NULL DEFAULT ''
    )
    """,
    # Orden del listado (recientes primero, desempate por id) -> paginacion por SQL.
    "CREATE INDEX IF NOT EXISTS idx_generaciones_indice_orden "
    "ON generaciones_indice (fecha_inicio DESC, gen_id DESC)",
    # Filtro por marca (Actividad IA por marca) y por estado (reaper de `ejecutando`).
    "CREATE INDEX IF NOT EXISTS idx_generaciones_indice_marca ON generaciones_indice (marca)",
    "CREATE INDEX IF NOT EXISTS idx_generaciones_indice_estado ON generaciones_indice (estado)",
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
        -- `payload`: dict CRUDO de metricas serializado. `jsonb` (ADR 0012): se lee entero y se
        -- querria consultar; con `dict_row` vuelve como dict (`leer_metricas_cache` acepta
        -- dict-o-str). El UPSERT sigue pasando el JSON serializado. Migracion 0031 en BDs viejas.
        payload      jsonb NOT NULL,
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
        -- FECHA NATIVA (migracion 0033): timestamptz, UTC. Ordena la bitacora (recientes
        -- primero); el serializador de `listar_eventos_internos` la re-emite con `iso_o_vacio`.
        creado              timestamptz
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
    # como el resto del esquema. `barrido_solicitado` (ISO o '') es el FLAG cross-proceso de
    # "barre YA": lo escribe el back (POST /api/sistema/daemons/{d}/barrer) y lo consume el
    # bucle del daemon en su siguiente tick (`daemon_util.bucle_gateado`), que ejecuta el
    # barrido de inmediato y lo limpia.
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
        errores        INTEGER NOT NULL DEFAULT 0,
        barrido_solicitado TEXT NOT NULL DEFAULT ''
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
    _aplicar_migraciones(con, _nucleo.MIGRACIONES_PRE_DDL)
    for sentencia in _DDL_ESQUEMA:
        con.execute(sentencia)
    con.commit()
    _aplicar_migraciones(con, _nucleo.MIGRACIONES_POST_DDL)
    # Limpieza de turnos duplicados ANTES del indice unico de rota (un CREATE UNIQUE INDEX
    # sobre duplicados preexistentes fallaria y dejaria la tabla sin el constraint). Corre
    # SIEMPRE (no va al journal): es el companero del retry de los indices unicos de abajo.
    _dedup_turnos_rota(con)
    # Indices UNICOS de idempotencia: AL FINAL, aislados (commit propio por indice) y SIEMPRE
    # (no van al journal A PROPOSITO): pueden fallar sobre BDs con duplicados previos sin
    # tumbar el arranque, y deben REINTENTARSE en cada arranque hasta que la limpieza manual
    # permita crearlos (journalizarlos congelaria el fallo). Ver helper.
    _crear_indices_unicos_idempotencia(con)

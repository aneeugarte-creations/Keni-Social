"""Migraciones de COLUMNAS y datos: ALTER/backfill/normalizacion sobre tablas ya creadas.

Todas las `_migrar_*` de columnas (mas renombres, backfills, normalizacion de timestamps,
dedup de turnos y los indices unicos de idempotencia) que el registro de `migraciones` invoca.
Extraido de `_db_core.py` al trocearlo por areas (refactor de pura reubicacion). Depende solo
de `_comun` + `motor_db`/`tiempo` + stdlib (el bloque de MODELO de turnos/franjas vive en
`migraciones_modelo`).
"""
from __future__ import annotations

import json
from typing import Any

from ..motor_db import IntegrityError
from ._comun import _columnas_existentes, _log, _tabla_existe


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


# Columnas ampliables de `daemon_latidos` (mismo patrón idempotente). El CREATE TABLE ya las
# declara para BDs nuevas; esta tupla migra las BDs hosted existentes.
_COLUMNAS_DAEMON_LATIDOS_AMPLIADAS: tuple[tuple[str, str], ...] = (
    # FLAG de barrido forzado (ISO de la solicitud o ''): cross-proceso back -> daemons.
    # Lo escribe POST /api/sistema/daemons/{d}/barrer; lo consume `bucle_gateado` en su
    # siguiente tick (ejecuta el sweep YA y lo limpia con un UPDATE atomico).
    ("barrido_solicitado", "TEXT NOT NULL DEFAULT ''"),
)


def _migrar_columnas_daemon_latidos(con: Any) -> None:
    """Anade a `daemon_latidos` columnas ampliadas que una BD vieja no tuviera (idempotente)."""
    if not _tabla_existe(con, "daemon_latidos"):
        return
    columnas = _columnas_existentes(con, "daemon_latidos")
    for columna, tipo in _COLUMNAS_DAEMON_LATIDOS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE daemon_latidos ADD COLUMN IF NOT EXISTS {columna} {tipo}")


def _backfill_pesos_fuente(con: Any) -> None:
    """Backfill ONE-SHOT del peso editorial: seed por host en `fuentes_rss` + propagación.

    Tres pasos (cada uno idempotente; la migración corre una sola vez por BD):
      1. A cada fuente existente con peso por defecto (1.0) se le asigna el peso semilla de
         su HOST (`fuentes_pesos.peso_de_url`); los pesos ya editados a mano no se pisan.
      2. Los items archivados heredan el peso de su fuente (denormalización retroactiva).
      3. Los items de AGENCIA (`fuente_id` 'agencia-*': Reuters/AFP, sin fila en
         `fuentes_rss`) son potentes por definición.
    """
    from ..dominio import fuentes_pesos  # import local: evitar ciclos en el arranque

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


def _backfill_gasto_ia_proceso(con: Any) -> None:
    """Backfill ONE-SHOT de `gasto_ia.proceso` desde el indice de generaciones (idempotente).

    La columna nace con DEFAULT 'produccion' (todas las filas existentes => produccion al
    instante). Este backfill REFINA las de INVESTIGACION cruzando por `gen_id` con
    `generaciones_indice.proceso` (que sella/deduce `proceso_de` al indexar). Las filas sin
    match en el indice (o sin proceso valido) se quedan en 'produccion' (la maquina de
    contenido, default deliberado). Idempotente: solo toca filas cuyo proceso difiere del
    indice; correr dos veces no cambia nada.
    """
    if not _tabla_existe(con, "gasto_ia") or not _tabla_existe(con, "generaciones_indice"):
        return
    con.execute(
        "UPDATE gasto_ia g SET proceso = gi.proceso FROM generaciones_indice gi "
        "WHERE g.gen_id = gi.gen_id AND gi.proceso IN ('investigacion', 'produccion') "
        "AND g.proceso <> gi.proceso"
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
    # OJO: `contenido.creado`/`actualizado`, `metricas_pieza_snapshots.ts` y
    # `comercial_snapshots.ts` YA NO van aqui: la migracion 0033 las convirtio a tipos NATIVOS
    # de Postgres (timestamptz), que ordenan/comparan por valor (no por texto). Normalizar TEXT
    # sobre ellas (`left()`, `~`) reventaria (ya no son text); su correctitud temporal la
    # garantiza el tipo nativo. Aqui solo quedan las columnas que SIGUEN siendo TEXT.
    ("contenido_plataforma", "creado", 19),
    ("contenido_plataforma", "actualizado", 19),
    ("contenido_plataforma", "preparado_en", 19),
    ("contenido_plataforma", "fecha_programada", 16),
    # Motor de noticias: estas columnas se comparan/ordenan como texto (ventanas 24h,
    # GC del pool, `ultimo_visto >= ?`, `capturado_en >= ?`, `proximo_sondeo <= ahora`,
    # `MAX(ultima_actualizacion)`) y se escribian con `datetime.now(UTC).isoformat()`
    # (aware + microsegundos) hasta la unificacion al canon. OJO: los `creado` de
    # DESEMPATE (fuentes_rss/fuentes_algoritmo/...) NO van aqui:
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

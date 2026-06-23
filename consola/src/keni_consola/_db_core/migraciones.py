"""Framework de migraciones VERSIONADAS de esquema (journal `schema_migraciones`) + registro.

`Migracion`, `_id_migracion`, `_aplicar_migraciones` (el runner) y el REGISTRO ordenado
(`MIGRACIONES_PRE_DDL`/`MIGRACIONES_POST_DDL`/`MIGRACIONES`), que referencia las `_migrar_*` de
`migraciones_columnas`/`migraciones_modelo`. Extraido de `_db_core.py` al trocearlo por areas
(refactor de pura reubicacion). Ver la REGLA junto a `_DDL_SCHEMA_MIGRACIONES` y ADR 0008.
"""
from __future__ import annotations

import hashlib
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..tiempo import ahora_iso
from ._comun import _log
from .migraciones_columnas import (
    _COLUMNAS_APROBACIONES_AMPLIADAS,
    _COLUMNAS_CONFIG_FRANJAS_AMPLIADAS,
    _COLUMNAS_PUBLICACION_AMPLIADAS,
    _COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS,
    _COLUMNAS_DAEMON_LATIDOS_AMPLIADAS,
    _COLUMNAS_EVENTO_ROTA_AMPLIADAS,
    _COLUMNAS_FUENTES_RSS_AMPLIADAS,
    _COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS,
    _COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS,
    _COLUMNAS_PIEZA_ROTA_AMPLIADAS,
    _COLUMNAS_PROGRAMA_AMPLIADAS,
    _COLUMNAS_SWAP_AMPLIADAS,
    _COLUMNAS_TS_CANON,
    _COLUMNAS_TURNO_ROTA_AMPLIADAS,
    _COLUMNAS_USUARIOS_AMPLIADAS,
    _COLUMNAS_USUARIOS_RETIRADAS,
    _asegurar_marca_grid_rota,
    _backfill_gasto_ia_proceso,
    _backfill_pesos_fuente,
    _forzar_reset_password_existentes,
    _materializar_passkey_requerido_existentes,
    _migrar_columnas_aprobaciones,
    _migrar_columnas_campanias,
    _migrar_columnas_config_franjas,
    _migrar_columnas_publicacion,
    _migrar_columnas_pieza,
    _migrar_columnas_daemon_latidos,
    _migrar_columnas_etiquetas,
    _migrar_columnas_eventos_rota,
    _migrar_columnas_fuentes_rss,
    _migrar_columnas_noticias_algoritmo,
    _migrar_columnas_noticias_clusters,
    _migrar_columnas_noticias_items,
    _migrar_columnas_piezas_rota,
    _migrar_columnas_plantillas_diseno,
    _migrar_columnas_programas,
    _migrar_columnas_swaps,
    _migrar_columnas_turnos_rota,
    _migrar_columnas_usuarios,
    _migrar_columnas_video_composiciones,
    _migrar_etiquetas_etapas_verbos,
    _migrar_green_a_evergreen,
    _migrar_renombre_catalogo_media,
    _migrar_renombre_columnas_etapas,
    _migrar_renombre_columnas_veredicto,
    _normalizar_timestamps_texto,
    _recuperar_campanias_de_comercial,
    _migrar_renombre_entidades,
    _renombrar_comercial_campanias_a_campanias,
    _resanear_traduccion_envenenada,
)
from .migraciones_integridad import (
    _COLUMNAS_FECHA_NATIVA,
    _COLUMNAS_JSONB,
    _FKS,
    _drop_tabla_sugerencias_editoriales,
    _drop_tablas_comercial_snapshots,
    _migrar_checks_dominio,
    _migrar_fks_hub,
    _migrar_indice_generaciones,
    _migrar_indice_pieza_estado_marca,
    _migrar_tabla_daemon_barridos,
    _migrar_tipos_fecha,
    _migrar_tipos_jsonb,
    _migrar_version_optimista,
)
from .migraciones_modelo import _migrar_modelo_franjas, _migrar_modelo_turnos

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
# conexion; un CREATE TABLE IF NOT EXISTS sobre un renombre pendiente dejaria sueltos los datos).
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
    # Renombres: deben correr antes de que el DDL cree la tabla nueva VACIA y deje sueltos los datos.
    Migracion("0006-green-a-evergreen", _migrar_green_a_evergreen, re_aplicar_si_cambia=True),
    Migracion(
        "0007-renombre-catalogo-media", _migrar_renombre_catalogo_media, re_aplicar_si_cambia=True
    ),
    # GRID POR MARCA: anade `marca` al grid de rota antes de los indices `idx_rota_*_marca`.
    Migracion("0008-marca-grid-rota", _asegurar_marca_grid_rota, re_aplicar_si_cambia=True),
    # ETAPAS CON NOMBRE DE VERBO (Fase 2): renombra las columnas de etapa legacy `qa_*` ->
    # `verificar_*` en `contenido`/`noticias_clusters` (piloto AMX), preservando datos. PRE-DDL
    # a proposito: debe correr ANTES de que las migraciones de ADD COLUMN re-aplicables (0011/
    # 0019, cuya tupla cambio de `qa_*` a `verificar_*`) re-evaluen y, al no ver aun la columna
    # nueva, crearian una columna vacia suelta (mismo motivo que el renombre green->evergreen).
    # One-shot pero idempotente (RENAME guardado por la existencia de la columna).
    Migracion("0037-renombre-columnas-etapas", _migrar_renombre_columnas_etapas),
    # ETAPAS CON NOMBRE PROPIO (limpieza de jerga `veredicto`): renombra los verdict sobrecargados
    # a su etapa: `verificar_veredicto` -> `verificacion_fuente` (VERIFICAR; en `contenido` y
    # `noticias_clusters`) y `pieza.veredicto` -> `revision` (REVISAR). PRE-DDL por
    # el mismo motivo que 0037: debe correr ANTES de que las ADD COLUMN re-aplicables (0011/0019,
    # cuya tupla ya apunta a `verificacion_fuente`) re-evaluen y creen una columna vacia suelta.
    # One-shot pero idempotente (RENAME guardado por la existencia de la columna).
    Migracion("0039-renombre-columnas-veredicto", _migrar_renombre_columnas_veredicto),
    # RECUPERA Campañas: el rename `comercial_campanias`->`campanias` se publicó en POST_DDL
    # (0040) a la vez que el DDL pasaba a crear `campanias` directamente; el DDL creaba la tabla
    # nueva VACIA antes del rename, que entonces quedaba inerte y dejaba las campañas varadas en
    # `comercial_campanias` (0040 igualmente se registró aplicado, así que su id no las rescata).
    # En PRE-DDL renombra/fusiona ANTES de que el DDL recree `campanias` vacía; deja 0040 inerte.
    # One-shot pero idempotente (tras correr, `comercial_campanias` ya no existe -> no-op).
    Migracion("0041-recuperar-campanias", _recuperar_campanias_de_comercial),
    # RENOMBRE de ENTIDADES (contenido->publicacion, contenido_plataforma->pieza + tablas
    # dependientes y columnas FK). PRE-DDL OBLIGATORIO: renombra ANTES de que el DDL cree las
    # tablas nuevas vacías (mismo motivo que 0041-recuperar-campanias). Idempotente, guardada.
    Migracion("0042-renombre-entidades", _migrar_renombre_entidades),
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
        _migrar_columnas_publicacion,
        re_aplicar_si_cambia=True,
        datos=(_COLUMNAS_PUBLICACION_AMPLIADAS, _COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS),
    ),
    Migracion(
        "0012-columnas-aprobaciones",
        _migrar_columnas_aprobaciones,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_APROBACIONES_AMPLIADAS,
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
        _migrar_columnas_pieza,
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
    # Flag de barrido forzado de daemons (`barrido_solicitado`) para BDs hosted existentes.
    Migracion(
        "0027-columnas-daemon-latidos",
        _migrar_columnas_daemon_latidos,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_DAEMON_LATIDOS_AMPLIADAS,
    ),
    # INTEGRIDAD (ADR 0012, apendice de 0004): FKs reales en las relaciones de alto valor del
    # hub `contenido` y afines, con limpieza previa de sueltos. Es re-ejecutable e idempotente
    # (DROP IF EXISTS + ADD), asi que la dejamos `re_aplicar_si_cambia=True`: editar `_FKS`
    # (anadir/quitar una relacion) cambia la huella y re-aplica la migracion una vez.
    Migracion("0028-fks-hub-contenido", _migrar_fks_hub, re_aplicar_si_cambia=True, datos=_FKS),
    # INTEGRIDAD (ADR 0012): CHECK de allowlist en los campos de estado (estado de contenido y
    # de la fila por plataforma, decision de aprobacion, rol de usuario, verificacion_fuente), con
    # normalizacion previa de valores invalidos. Re-aplicable (idempotente): editar una
    # allowlist de dominio cambia la huella y re-normaliza + recrea el CHECK una vez.
    Migracion("0029-checks-dominio", _migrar_checks_dominio, re_aplicar_si_cambia=True),
    # INTEGRIDAD (ADR 0012): columna `version` para concurrencia optimista en `contenido` y
    # `pieza` (BDs existentes; las nuevas la traen del DDL). One-shot.
    Migracion("0030-version-optimista", _migrar_version_optimista),
    # TIPOS (ADR 0012): TEXT-JSON -> jsonb en `jobs.spec` y `metricas_cache.payload` (BDs
    # existentes; las nuevas ya nacen jsonb por el DDL). Idempotente (guardada por el tipo
    # actual): editar `_COLUMNAS_JSONB` cambia la huella y re-evalua.
    Migracion("0031-tipos-jsonb", _migrar_tipos_jsonb, re_aplicar_si_cambia=True, datos=_COLUMNAS_JSONB),
    # RENDIMIENTO (ADR 0012): tabla `generaciones_indice` para paginar Actividad IA / Pipelines
    # por SQL en vez de parsear ~2000 YAML por peticion (BDs existentes; las nuevas la traen del
    # DDL). One-shot e idempotente (CREATE TABLE/INDEX IF NOT EXISTS); el backfill desde los YAML
    # lo hace `generaciones._almacen` perezosamente al primer listado.
    Migracion("0032-indice-generaciones", _migrar_indice_generaciones),
    # TIPOS (ADR 0012, ola diferida): fechas TEXT de ALTO USO -> tipos NATIVOS de Postgres
    # (`timestamptz` para contenido.creado/actualizado, jobs.creado/claimed_at, *_snapshots.ts,
    # eventos_internos.creado; `date` para gasto_ia.dia). One-shot por BD (las nuevas ya nacen
    # con el tipo nativo via DDL); idempotente (GUARDADA por el tipo actual). Los call-sites
    # (substr->to_char, serializacion ISO via `tiempo.iso_o_vacio`, claimed_at NULL) se
    # adaptaron en el mismo commit. Ver `_migrar_tipos_fecha`.
    Migracion(
        "0033-tipos-fecha-nativa",
        _migrar_tipos_fecha,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_FECHA_NATIVA,
    ),
    # OBSERVABILIDAD: tabla `daemon_barridos` (historial por barrido de cada daemon) para BDs
    # existentes (las nuevas la traen del DDL). One-shot e idempotente (CREATE TABLE/INDEX IF
    # NOT EXISTS); sin backfill (el historial es prospectivo). Ver `db_latidos.registrar_barrido`.
    Migracion("0034-tabla-daemon-barridos", _migrar_tabla_daemon_barridos),
    # ECONOMIA: backfill de `gasto_ia.proceso` (la columna la trae el DDL con DEFAULT
    # 'produccion'). Refina las filas de INVESTIGACION desde `generaciones_indice`; lo demas
    # queda en 'produccion'. One-shot e idempotente. Ver `_backfill_gasto_ia_proceso`.
    Migracion("0035-backfill-gasto-ia-proceso", _backfill_gasto_ia_proceso),
    # LIMPIEZA: la feature "agente de sugerencias editoriales" (daemon del digest diario) se
    # retiro por completo (API, repos, MCP, inicializacion, DDL). Esta migracion elimina su tabla
    # suelta en BDs ya creadas. One-shot e idempotente (`DROP TABLE IF EXISTS`).
    Migracion("0036-drop-sugerencias-editoriales", _drop_tabla_sugerencias_editoriales),
    # ETAPAS CON NOMBRE DE VERBO (Fase 2): reescribe los MARCADORES de etapa persistidos en
    # `generaciones_indice.payload->>'etiqueta'` con los prefijos viejos (CI/verificación/CD/ARTE) y las
    # frases del pool ("Fusión de historias"/"Encaje editorial") a sus verbos nuevos (ADMITIR/
    # VERIFICAR/REDACTAR/ILUSTRAR, Fusionar/Priorizar). One-shot e idempotente (solo reescribe
    # las filas que aun tengan el prefijo/frase viejo). Ver `_migrar_etiquetas_etapas_verbos`.
    Migracion("0038-etiquetas-etapas-verbos", _migrar_etiquetas_etapas_verbos),
    # LIMPIEZA: el apartado "Comercial" (seguimiento por snapshots) se retiró por completo
    # (daemon de captura, endpoints, repos, DDL); lo reemplazó "Campañas" (hashtags sobre
    # métricas vivas). Esta migración elimina sus tablas sueltas en BDs ya creadas. One-shot e
    # idempotente (`DROP TABLE IF EXISTS`). `comercial_campanias` (vivas) NO se toca.
    Migracion("0039-drop-comercial-snapshots", _drop_tablas_comercial_snapshots),
    # RENAME: `comercial_campanias` -> `campanias` (las campañas dejan de colgar del namespace
    # "comercial", retirado). Corre tras 0014 (que ya añadió `marcas` a la tabla vieja). One-shot
    # e idempotente (RENAME solo si la vieja existe y la nueva no). Ver `_renombrar_comercial_campanias_a_campanias`.
    Migracion("0040-rename-campanias", _renombrar_comercial_campanias_a_campanias),
    # COLUMNAS DE `rota_config_franjas`: `franjas` (lista JSON) hace que la plantilla con que se
    # siembra cada semana nueva sea una lista de N franjas (se puede añadir "Nocturna") en vez de
    # 2 columnas fijas matutino/vespertino; `mostrar_horas_equipo` controla si la vista "Equipo"
    # del calendario pinta el rango horario. Re-aplicable al cambiar `datos`; idempotente (ADD
    # COLUMN IF NOT EXISTS); NO destructivo (`franjas` vacío => deriva de las columnas legadas al
    # leer; el toggle nace FALSE). Ver `_migrar_columnas_config_franjas`.
    Migracion(
        "0041-columnas-config-franjas",
        _migrar_columnas_config_franjas,
        re_aplicar_si_cambia=True,
        datos=_COLUMNAS_CONFIG_FRANJAS_AMPLIADAS,
    ),
    # RENDIMIENTO: indice compuesto `(estado, marca)` en `pieza` para el filtro caliente del
    # feed/colas (BDs existentes; las nuevas lo traen del DDL). One-shot e idempotente.
    Migracion("0042-indice-pieza-estado-marca", _migrar_indice_pieza_estado_marca),
    # SANEO DE DATOS: clusters marcados `traducido=1` con el título extranjero
    # pegado en `titulo_es` (== `titulo`), residuo de traducciones donde Haiku no tradujo. Se
    # devuelven a `traducido=0` para que Traducir los reintente (la mesa dejaría de mostrarlos en
    # idioma original). One-shot e idempotente.
    Migracion("0043-resanear-traduccion-envenenada", _resanear_traduccion_envenenada),
    # SEGURIDAD: fuerza a TODOS los usuarios existentes a
    # fijar una contrasena nueva (bajo la politica reforzada) en su proximo acceso —las viejas no
    # se pueden auditar (solo hay hash)—. Junto al MFA obligatorio para todos, la primera vuelta a
    # entrar de cada persona cambia contrasena + inscribe passkey. One-shot; no-op en BD vacia/tests.
    Migracion("0044-forzar-reset-password-existentes", _forzar_reset_password_existentes),
    # SEGURIDAD: el «passkey obligatorio para todo el equipo» pasó de override global a acción
    # masiva sobre `mfa_requerido`. Para no des-forzar al equipo actual en el deploy, materializa
    # ese estado marcando `mfa_requerido=1` en las cuentas existentes. One-shot; no-op en BD vacía/tests.
    Migracion("0045-materializar-passkey-requerido", _materializar_passkey_requerido_existentes),
)

# Vista unica y ordenada (PRE + POST), util para tests/inspeccion.
MIGRACIONES: tuple[Migracion, ...] = MIGRACIONES_PRE_DDL + MIGRACIONES_POST_DDL


def hay_migraciones_pendientes(con: Any) -> bool:
    """True si, con el journal actual, el arranque aplicaria AL MENOS una migracion.

    Comparte la MISMA logica de id (`_id_migracion`) y el MISMO conjunto que el runner
    (`MIGRACIONES` = PRE + POST, el orden real del arranque): una migracion esta "pendiente"
    exactamente cuando su id NO esta en el journal `schema_migraciones` -> la condicion con
    que `_aplicar_migraciones` decide ejecutarla. Asi "pendiente" no diverge de lo que se aplica.

    El deploy lo usa para decidir si un cutover blue-green es seguro (sin solape sobre un
    esquema que el back viejo aun no conoce). Exige que el journal ya exista (lo crea el
    arranque antes de leerlo); si la tabla no existe, `con.execute` lanza y el caller lo trata
    como fail-safe (asumir pendientes -> stop-the-world).
    """
    aplicadas = {
        fila["id"] for fila in con.execute("SELECT id FROM schema_migraciones").fetchall()
    }
    return any(_id_migracion(m) not in aplicadas for m in MIGRACIONES)

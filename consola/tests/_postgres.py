"""Ayuda compartida de los tests con backend POSTGRES (skip si no hay Postgres).

CONTRATO de CI (lo importante): los tests de Postgres SE SALTAN con un mensaje claro si no
hay un Postgres disponible, de modo que un CI SIN Postgres sigue verde y, donde SI lo haya
(servicio `postgres` del runner), se ejecutan de verdad.

COMO se decide "hay Postgres": la env var `KENI_TEST_DATABASE_URL` apunta al Postgres de
pruebas. Si esta, los tests la usan (la copian a `DATABASE_URL`, que es lo que `motor_db`
lee). Si NO esta, `requiere_postgres()` hace `pytest.skip`.

  # POLITICA (CLAUDE.md > Tests y CI): por DEFECTO NO se corre la suite ni se levanta Postgres
  # en local; se empuja a la rama/main y se valida que el CI salga VERDE en el servidor (alli
  # hay un service `postgres` que exporta KENI_TEST_DATABASE_URL). El contenedor de abajo es un
  # ESCAPE puntual para depurar un test concreto, NO el flujo normal (ojo: tu reloj/zona local
  # puede hacer fallar tests sensibles a la hora que en CI pasan):
  #   docker run -d --name pg -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:16
  #   export KENI_TEST_DATABASE_URL=postgresql://postgres:x@127.0.0.1:55432/postgres
  #   pytest consola/tests/test_db_postgres.py

AISLAMIENTO: `limpiar_postgres()` hace TRUNCATE de las tablas operacionales entre tests
(rapido y sin recrear el esquema). El esquema se crea on-demand al primera conexion.
"""

from __future__ import annotations

import os

import pytest

# Nombre de la env var que activa los tests de Postgres (apunta al Postgres de pruebas).
ENV_TEST_DATABASE_URL = "KENI_TEST_DATABASE_URL"

# Tablas operacionales que se truncan entre tests (todas las del esquema de `db.py`).
# `usuarios_marcas` (N:M del organigrama del cliente) se trunca via `usuarios CASCADE` pero la
# listamos explicitamente por defensa (truncar a la cabeza ahorra el cascade impredecible
# si el orden de las tablas cambiara).
_TABLAS = (
    "usuarios_marcas",
    "webauthn_credenciales",
    "sesiones",
    "usuarios",
    "campanias",
    "gasto_ia",
    "metricas_pieza_snapshots",
    "rota_turnos",
    "rota_franjas",
    "rota_ausencias",
    "rota_piezas",
    "rota_programas",
    "rota_eventos",
    "rota_evento_series",
    "rota_swaps_turno",
    "rota_coordinacion",
    "rota_config_franjas",
    "parrilla_propuesta",
    # Sub-tablas del tablero de contenido (olas organizacion/colaboracion): se truncan
    # ANTES que sus padres `contenido`/`pieza` (CASCADE igual las cubre,
    # pero a la cabeza evita sorpresas de orden).
    "publicacion_etiquetas",
    "publicacion_comentarios",
    "pieza_copy_versiones",
    "pieza_aprobaciones",
    "pieza",
    "publicacion",
    # Catálogos/activos operacionales independientes (olas organizacion/activos/automatizacion).
    "etiquetas",
    "catalogo_media",
    "marca_activos",
    "plantillas_diseno",
    "etiquetas_plantilla",
    "bloques",
    "documento_versiones",
    "webhooks",
    "eventos_internos",
    "jobs",
    # Indice del listado de generaciones (cache derivado del almacen YAML; rendimiento).
    "generaciones_indice",
    "metricas_cache",
    # CONTENIDO editorial reutilizable migrado de ficheros a Postgres (ADR 0006).
    "rss_items_vistos",
    "fuentes_rss",
    "franjas_editoriales",
    # Inteligencia de plataforma (cambios de algoritmo + tendencias): noticias antes que
    # fuentes (sin FK, pero a la cabeza evita sorpresas de orden).
    "noticias_algoritmo",
    "fuentes_algoritmo",
    # Motor de ingesta de noticias (Ola A): archivo de artículos + clusters. Sin truncar,
    # acumulaban filas entre tests y reventaban counts de test_api_noticias/historias.
    "noticias_items",
    "noticias_clusters",
    # Taller Evergreen: ideas de contenido evergreen (propuesta/aprobada/descartada). Sin esto,
    # las ideas se acumulan entre tests del mismo worker y rompen el aislamiento.
    "evergreen_ideas",
    # Kanban de auto-desarrollo: sugerencias del equipo. Sin truncar, se acumulan entre tests
    # del mismo worker y rompen el aislamiento del listado.
    "sugerencias",
    # Insumos del día (cajones): ítems antes que lotes. Sin esto, los ítems se acumulan entre
    # tests del mismo worker (misma fecha+cajón) y rompen el aislamiento del listado por día.
    "insumos_item",
    "insumos_lote",
    # Motor de video (Ola VIDEO): subtitulos antes que composiciones (a la cabeza evita
    # sorpresas de orden; sin FK declarada). Sin truncar, acumularian filas entre tests.
    "video_subtitulos",
    "video_composiciones",
    # Gestor de audio (audio→texto): artefactos antes que transcripciones. Sin truncar, acumularian.
    "audio_artefactos",
    "audio_transcripciones",
    # Latidos de daemons (observabilidad): sin truncar, un latido de un test contamina las
    # aserciones de estado/contadores del siguiente.
    "daemon_latidos",
    # Historial por barrido de daemons (observabilidad): sin truncar, las filas de un test
    # contaminan el listado/purga del siguiente.
    "daemon_barridos",
    # Piezas y solicitudes de la Prompts de Texto (modelo "versión publicada").
    # Sin truncar, un puntero de producción de un test contaminaría el `produccion`/
    # `sin_publicar` (y el ensamblaje) del siguiente.
    "texto_publicaciones",
    "texto_solicitudes",
    # Journal de migraciones VERSIONADAS de esquema (`_db_core.MIGRACIONES`). Truncarlo entre
    # tests es DELIBERADO: vacia el journal, de modo que la primera conexion de cada test
    # re-aplica las migraciones (idempotentes) y se preserva la auto-curacion "BD vieja" que
    # ejercita la suite (tests que recrean tablas legadas y esperan que `db.*` las migre).
    "schema_migraciones",
)


def url_postgres_de_pruebas() -> str | None:
    """URL del Postgres de pruebas (`KENI_TEST_DATABASE_URL`), o None si no esta."""
    return os.environ.get(ENV_TEST_DATABASE_URL) or None


# Aislamiento por worker de xdist: los workers corren EN PARALELO, asi que NO pueden compartir
# una misma BD (un TRUNCATE de uno borraria datos de otro). A cada worker le damos su PROPIA base
# `<base>_<worker>` (creada on-demand). En serie (sin xdist) se usa la BD base tal cual. Ademas,
# a la BD efectiva le ponemos `synchronous_commit=off` (commits sin esperar el flush del WAL;
# seguro en una BD desechable de tests, gran recorte con miles de commits). Todo esto UNA vez por
# proceso (memo): cada worker es un proceso aparte y entra aqui una sola vez.
_url_efectiva_cache: str | None = None


def _con_db(url: str, dbname: str) -> str:
    """`url` con su nombre de base de datos reemplazado por `dbname`."""
    from urllib.parse import urlsplit, urlunsplit

    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, f"/{dbname}", p.query, p.fragment))


def _nombre_db(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).path.lstrip("/") or "postgres"


def _preparar_db_efectiva(base_url: str) -> str:
    """Crea (si hay xdist) la BD por-worker, le fija synchronous_commit=off y devuelve su URL."""
    import psycopg

    worker = os.environ.get("PYTEST_XDIST_WORKER")
    destino = base_url if not worker else _con_db(base_url, f"{_nombre_db(base_url)}_{worker}")
    db_destino = _nombre_db(destino)
    # Conexion de mantenimiento a la BD `postgres` del MISMO server (CREATE DATABASE / ALTER no
    # pueden correr contra la propia BD destino ni dentro de una transaccion -> autocommit).
    with psycopg.connect(_con_db(base_url, "postgres"), autocommit=True) as con:
        if worker:
            existe = con.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_destino,)).fetchone()
            if not existe:
                con.execute(f'CREATE DATABASE "{db_destino}"')  # noqa: S608 -- nombre derivado del worker
        con.execute(f'ALTER DATABASE "{db_destino}" SET synchronous_commit TO off')  # noqa: S608
    return destino


def requiere_postgres() -> str:
    """Devuelve la URL de pruebas (por-worker si hay xdist) o `pytest.skip` si no hay Postgres.

    Usar al inicio de cada test de Postgres (o via la fixture `pg`). El skip es el
    comportamiento esperado en CI sin Postgres.
    """
    global _url_efectiva_cache
    base = url_postgres_de_pruebas()
    if not base:
        pytest.skip(
            f"sin Postgres de pruebas: exporta {ENV_TEST_DATABASE_URL} para ejecutar los "
            "tests del backend Postgres (CI sin Postgres los salta)."
        )
    if _url_efectiva_cache is None:
        _url_efectiva_cache = _preparar_db_efectiva(base)
    return _url_efectiva_cache


def limpiar_postgres(url: str) -> None:
    """TRUNCATE de todas las tablas operacionales (aislamiento entre tests).

    Tolerante a tablas inexistentes (primer uso, antes de crear el esquema).
    """
    import psycopg

    # Cierra el pool de conexiones de ESTE proceso (cliente) ANTES de tocar el servidor. POR QUE
    # (medido, root-cause de la lentitud del pool en la suite): el `pg_terminate_backend` de abajo
    # mata las conexiones del pool DESDE EL SERVIDOR; en el siguiente `getconn` el pool las
    # encuentra muertas, las descarta y reconstruye, pero psycopg_pool reconstruye una conexion
    # CAIDA con un BACKOFF de ~1 s (un connect limpio son ~8 ms). Con el pool ON eso es ~22
    # reconexiones x ~1 s por test -> la suite -n6 saltaba de ~4 a ~12 min. Cerrarlo aqui suelta
    # los sockets LIMPIAMENTE: el pool se reabre perezoso en la siguiente `conectar_cruda` con una
    # conexion fresca (~8 ms), sin backoff. Con el pool OFF (camino directo) es un no-op barato.
    # Asi el pool puede ir ON en la suite (reusa conexiones -> sin agotar puertos efimeros del CI)
    # y ademas MAS rapido que sin pool (medido: 124 s vs 211 s, -n6).
    try:
        from keni_consola import motor_db

        motor_db.cerrar_pool()
    except Exception:  # noqa: BLE001 -- best-effort; sin pool/import seguimos igual.
        pass

    # UN solo TRUNCATE multi-tabla (Postgres lo permite) en vez de N round-trips: esta
    # funcion corre 2x por test sobre ~1000 tests, asi que pasar de ~30 sentencias a 1
    # recorta el coste dominante de la suite en CI. Fallback per-tabla SOLO en el primer
    # uso, cuando aun no existe el esquema (un TRUNCATE batch falla entero si una tabla no
    # existe; el loop tolerante lo absorbe). Tras ese primer uso siempre va el camino rapido.
    lista = ", ".join(_TABLAS)
    with psycopg.connect(url, autocommit=True) as con:
        # Mata conexiones rezagadas a ESTA BD antes de truncar (hilos daemon stray). Tras cerrar
        # el pool arriba, esto ya NO mata el pool sano del proceso (esa era la causa del 3x), solo
        # strays reales: un hilo de fondo "idle in transaction" reteniendo locks cuyo cierre, bajo
        # xdist, se solaparia con este TRUNCATE -> deadlock. BD de test desechable: es seguro.
        con.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid()"
        )
        try:
            con.execute(f"TRUNCATE TABLE {lista} CASCADE")  # noqa: S608 -- allowlist fija
        except psycopg.errors.UndefinedTable:
            for tabla in _TABLAS:
                try:
                    con.execute(f"TRUNCATE TABLE {tabla} CASCADE")  # noqa: S608 -- allowlist fija
                except psycopg.errors.UndefinedTable:
                    pass


@pytest.fixture
def pg(monkeypatch):
    """Activa el Postgres de pruebas para el test (o lo salta si no hay Postgres).

    Fija `DATABASE_URL` (lo que lee `motor_db`) al Postgres de pruebas, limpia las tablas
    antes del test y las vuelve a limpiar despues. Devuelve la URL.

    Tras la ADR 0004 la fixture `entorno` tambien fija `DATABASE_URL`; `pg` se mantiene como
    fixture mas LIGERA (sin tocar el resto de env vars de la app) util para los tests del
    backend de DB puro (`test_db_postgres.py`, `test_migracion.py`).
    """
    url = requiere_postgres()
    limpiar_postgres(url)
    monkeypatch.setenv("DATABASE_URL", url)
    yield url
    limpiar_postgres(url)

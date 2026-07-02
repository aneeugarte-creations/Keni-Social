"""Config — accesores del dominio hosted. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._comun import (
    _VERDADEROS,
    DB_POOL_MAX_DEF,
    DB_POOL_MIN_DEF,
    ENV_DATABASE_URL,
    ENV_DB_POOL,
    ENV_DB_POOL_MAX,
    ENV_DB_POOL_MIN,
    ENV_PG_DB,
    ENV_PG_HOST,
    ENV_PG_PASSWORD,
    ENV_PG_PORT,
    ENV_PG_USER,
    ENV_S3_ACCESS_KEY,
    ENV_S3_BUCKET,
    ENV_S3_ENDPOINT,
    ENV_S3_REGION,
    ENV_S3_SECRET_KEY,
    ENV_VIDEO_MAX_MB,
    S3_BUCKET_DEF,
    S3_REGION_DEF,
    VIDEO_MAX_MB_DEF,
    Path,
    _crudo,
    _entero,
    _leer_secreto_fichero,
    os,
    quote,
)

# --------------------------------------------------------------------------- #
# Accesores: persistencia hosted (Postgres + object storage S3/Garage)         #
# --------------------------------------------------------------------------- #
#
# La media (S3) sigue siendo opcional: sin endpoint+credenciales S3 -> disco. La DB
# operacional, en cambio, es Postgres OBLIGATORIO (ADR 0004): `database_url()` puede
# devolver None, pero `motor_db.conectar_cruda()` exige la URL y falla con un mensaje claro.


def database_url() -> str | None:
    """URL de Postgres del back; None si no esta fijada (ni la URL ni los componentes).

    La operacional (tareas/comercial/rota/usuarios/sesiones/jobs) va SIEMPRE a Postgres
    (ADR 0004): esta funcion resuelve la URL, y `motor_db.conectar_cruda()` la EXIGE (un
    None alli es un error de arranque con mensaje accionable, no un fallback a SQLite).

    PRECEDENCIA (anti-drift):
      1. `DATABASE_URL` explicita -> se devuelve TAL CUAL (override; p. ej. un Postgres
         externo o un DSN con parametros especiales).
      2. Si no hay `DATABASE_URL` pero estan `POSTGRES_USER`+`POSTGRES_PASSWORD`+
         `POSTGRES_DB`, se DERIVA la URL de esos componentes. Asi la URL NO puede
         desincronizarse de la password (incidente de prod: la password embebida en
         `DATABASE_URL` dejo de coincidir con `POSTGRES_PASSWORD`). `host` default `db`
         (nombre del servicio en compose), `port` default `5432`. Usuario y password se
         %-codifican (`quote(..., safe="")`) porque una password base64 puede llevar
         `+`/`/`/`=`, que romperian el parseo de la URL.
      3. Si no hay ni URL ni componentes -> None (sin Postgres configurado: `conectar_cruda`
         lanzara el error obligatorio).
    """
    explicita = _crudo(ENV_DATABASE_URL)
    if explicita:
        return explicita
    usuario = _crudo(ENV_PG_USER)
    password = _crudo(ENV_PG_PASSWORD)
    db = _crudo(ENV_PG_DB)
    if usuario and password and db:
        host = _crudo(ENV_PG_HOST) or "db"
        port = _crudo(ENV_PG_PORT) or "5432"
        return (
            f"postgresql://{quote(usuario, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{db}"
        )
    return None


def db_pool_activado() -> bool:
    """¿Usar el pool de conexiones Postgres? (`KENI_DB_POOL`, def **ON**).

    Interruptor de UN SOLO flag: por defecto el pool ESTA ON (reutiliza conexiones, evita el
    handshake TCP+auth en el camino caliente). Con `KENI_DB_POOL=0` (o `false`/`no`/`off`) se
    vuelve al camino historico "una conexion psycopg por operacion".

    POR QUE ON es SEGURO (validado a fondo contra Postgres real, ver `test_motor_db_pool`):
    casi todos los call sites de `db.py` ya usan `try/finally` (254/258), asi que devuelven la
    lease incluso ante un `raise`; y para los pocos sin `try/finally`, la red `__del__` de
    `motor_db._ConexionPg` recupera la lease por refcount al caer de scope. Probado: 1800 ops
    normales, ruta de error, y el PATRON DE FUGA exacto (raise sin close) — incluso 6 hilos en
    paralelo con max_size=8 — sin agotar el pool. NO hay fuga en produccion.

    En la SUITE tambien va ON (reusa conexiones -> sin agotar puertos efimeros del CI, y mas
    rapido: medido -n6 124 s vs 211 s sin pool). Requiere que `tests/_postgres.limpiar_postgres`
    cierre el pool del proceso ANTES de su `pg_terminate_backend`/TRUNCATE: si no, el pool
    descubre sus conexiones muertas server-side y psycopg_pool las reconstruye con ~1 s de backoff
    cada una (esa era la causa de que la suite con pool fuese 3x mas lenta, ya arreglada).
    """
    crudo = _crudo(ENV_DB_POOL)
    if not crudo:
        return True  # def ON — seguro en prod (try/finally + red __del__), validado contra PG real
    return crudo.lower() in _VERDADEROS


def db_pool_min() -> int:
    """Conexiones minimas que el pool mantiene abiertas (`KENI_DB_POOL_MIN`, def 2, min 0)."""
    return _entero(ENV_DB_POOL_MIN, DB_POOL_MIN_DEF, minimo=0)


def db_pool_max() -> int:
    """Conexiones maximas del pool (`KENI_DB_POOL_MAX`, def 12).

    DEBE superar las conexiones de larga duracion concurrentes (cada `lock_barrido` retiene
    una conexion entera durante su barrido) + las leases por request + los daemons, o el
    resto se quedaria esperando una conexion libre. Se fuerza `>= min` para que el pool sea
    coherente aunque alguien fije un MAX por debajo del MIN.
    """
    return max(db_pool_min(), _entero(ENV_DB_POOL_MAX, DB_POOL_MAX_DEF, minimo=1))


def video_max_mb() -> int:
    """Tamano maximo (MB) de un video subido a una pieza (`KENI_VIDEO_MAX_MB`, def 300).

    Lo aplica `media.guardar_video_subida`. Minimo 1 MB (defensivo ante un valor absurdo).
    """
    return _entero(ENV_VIDEO_MAX_MB, VIDEO_MAX_MB_DEF, minimo=1)


def s3_endpoint() -> str | None:
    """Endpoint S3/Garage (`S3_ENDPOINT`); None si no esta."""
    return _crudo(ENV_S3_ENDPOINT) or None


def s3_region() -> str:
    """Region S3 (`S3_REGION`, def `garage`)."""
    return _crudo(ENV_S3_REGION) or S3_REGION_DEF


def s3_bucket() -> str:
    """Bucket de media S3 (`S3_BUCKET`, def `keni-media`)."""
    return _crudo(ENV_S3_BUCKET) or S3_BUCKET_DEF


def s3_access_key() -> str | None:
    """Access key S3 (`S3_ACCESS_KEY`); None si no esta."""
    return _crudo(ENV_S3_ACCESS_KEY) or None


def s3_secret_key() -> str | None:
    """Secret key S3 (`S3_SECRET_KEY`); None si no esta. SIN strip: puede ser sensible.

    A diferencia del resto, NO recortamos: una clave S3 puede (en teoria) llevar
    espacios significativos. Devuelve None solo si la var no esta o esta vacia.
    """
    valor = os.environ.get(ENV_S3_SECRET_KEY)
    if not valor:
        valor = _leer_secreto_fichero(ENV_S3_SECRET_KEY)
    return valor if valor else None


def s3_configurado() -> bool:
    """True si HAY object storage S3 cableado (endpoint + ambas credenciales).

    Es el conmutador de `media.py`: con S3 cableado, la media va al bucket; si no
    (perfil local/privado), sigue en disco. Exige endpoint y AMBAS credenciales para
    no intentar hablar S3 a medio configurar.
    """
    return bool(s3_endpoint() and s3_access_key() and s3_secret_key())



# --------------------------------------------------------------------------- #
# Accesor: override de RUTA especifica de un recurso                           #
# --------------------------------------------------------------------------- #


def override_ruta(nombre: str) -> Path | None:
    """Override de ruta especifico de un recurso (`KENI_CONSOLA_*` de estado).

    Es el override de MAXIMA prioridad de cada modulo de ruta (db, indice, media, ...):
    si la var esta puesta, se usa tal cual (expandiendo `~`). Si no, el modulo cae a
    `rutas.dir_config()`/`rutas.raiz_proyectos()`, que componen el fallback
    `KENI_DATA_DIR` > `${XDG_CONFIG_HOME:-~/.config}`.

    `nombre` es una de las constantes `ENV_*` de ruta de este modulo (p.ej. `ENV_INDICE`).
    """
    crudo = os.environ.get(nombre)
    if crudo:
        return Path(crudo).expanduser()
    return None

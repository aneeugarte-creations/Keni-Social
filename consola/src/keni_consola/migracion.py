"""Migracion one-shot del cutover hosted: SQLite -> Postgres y disco -> S3/Garage (#130).

Es la herramienta que el HUMANO corre UNA vez al pasar el back de SQLite+disco (perfil
local) a Postgres+S3 (perfil hosted). NO la corre la app sola en cada arranque (eso lo
decide el guardia de arranque en `db.arrancar_persistencia`); esto es el copiado explicito
de datos del cutover.

    python -m keni_consola.migracion            # migra DB y media (lee el entorno)
    python -m keni_consola.migracion --solo-db
    python -m keni_consola.migracion --solo-media
    python -m keni_consola.migracion --dry-run  # cuenta sin escribir

QUE COPIA:
  - DB: todas las tablas operacionales (tareas, comercial_publicaciones,
    comercial_snapshots, usuarios, sesiones, rota_eventos, rota_turnos) del `consola.db`
    SQLite al Postgres de `DATABASE_URL`.
  - Media: todos los objetos del dir de media en disco al bucket S3 (`S3_*`).

IDEMPOTENTE: re-ejecutar no duplica ni pisa. La DB inserta con conflicto -> NO-OP por PK /
indice UNIQUE (se respeta lo que ya este en Postgres). La media salta el objeto si la key
ya existe en el bucket. Asi se puede correr de nuevo sin miedo si algo se interrumpio.

ALCANCE (lo que NO migra, a proposito): el almacen YAML de publicaciones/historial
(`ficheros.py`, `<raiz>/<marca>/...`) y su indice regenerable (`indice.py`) NO se tocan: el
cutover de #130 es DB operacional + media. El contenido editorial viaja con su volumen
(`keni-data`/`KENI_DATA_DIR`) como hasta ahora; migrarlo es trabajo futuro aparte.

SEGURIDAD: no corre nada contra el servidor por su cuenta; lee el ENTORNO (las mismas vars
que el back) y opera sobre los almacenes que esas vars apuntan. El operador es quien fija el
entorno (`DATABASE_URL`/`S3_*`) y ejecuta el comando en la ventana de cutover.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field

from . import almacen_media, config, db, motor_db

# Orden de migracion: las tablas SIN dependencias primero. Hoy no hay FKs declaradas
# (los borrados en cascada se hacen a mano en `db.py`), asi que el orden solo busca un
# log legible; ON CONFLICT DO NOTHING evita problemas aunque el orden cambie.
_TABLAS: tuple[str, ...] = (
    "usuarios",
    "sesiones",
    "tareas",
    "comercial_publicaciones",
    "comercial_snapshots",
    "rota_eventos",
    "rota_turnos",
)


@dataclass
class ResumenMigracion:
    """Conteos del cutover, para el log y para los tests."""

    filas_por_tabla: dict[str, int] = field(default_factory=dict)
    objetos_media_copiados: int = 0
    objetos_media_saltados: int = 0

    @property
    def total_filas(self) -> int:
        return sum(self.filas_por_tabla.values())


# --------------------------------------------------------------------------- #
# DB: SQLite -> Postgres                                                       #
# --------------------------------------------------------------------------- #


def _columnas_sqlite(con_sqlite: sqlite3.Connection, tabla: str) -> list[str]:
    """Nombres de columna de una tabla SQLite, en orden de declaracion."""
    filas = con_sqlite.execute(f"PRAGMA table_info({tabla})").fetchall()
    return [f["name"] for f in filas]


def migrar_db(*, dry_run: bool = False) -> dict[str, int]:
    """Copia las tablas operacionales del SQLite local al Postgres de `DATABASE_URL`.

    Idempotente: cada fila se inserta con `INSERT OR IGNORE` (que el `motor_db` traduce a
    `ON CONFLICT DO NOTHING` en Postgres), asi que re-correr no duplica ni pisa lo que ya
    este en Postgres. Devuelve {tabla: filas_insertadas_o_vistas}.

    Exige `DATABASE_URL` (destino Postgres) y que exista el `consola.db` (origen). En
    `dry_run` solo CUENTA las filas del origen sin escribir en el destino.
    """
    if config.database_url() is None:
        raise SystemExit(
            "DATABASE_URL no esta fijado: no hay Postgres destino. Exporta DATABASE_URL "
            "(el del back hosted) antes de migrar."
        )
    ruta_origen = motor_db.ruta_db()
    if not ruta_origen.is_file():
        raise SystemExit(
            f"No existe el SQLite de origen ({ruta_origen}). Nada que migrar; ¿es el primer "
            "despliegue? Entonces no hay cutover que hacer."
        )

    con_sqlite = sqlite3.connect(str(ruta_origen))
    con_sqlite.row_factory = sqlite3.Row
    conteos: dict[str, int] = {}
    try:
        # El esquema en Postgres se crea on-demand al abrir la conexion destino.
        con_pg = None if dry_run else db.conectar()
        try:
            for tabla in _TABLAS:
                if not _tabla_existe_sqlite(con_sqlite, tabla):
                    conteos[tabla] = 0
                    continue
                filas = con_sqlite.execute(f"SELECT * FROM {tabla}").fetchall()  # noqa: S608 -- tabla de allowlist
                conteos[tabla] = len(filas)
                if dry_run or not filas:
                    continue
                columnas = _columnas_sqlite(con_sqlite, tabla)
                cols_sql = ", ".join(columnas)
                marcadores = ", ".join("?" for _ in columnas)
                sql = (
                    f"INSERT OR IGNORE INTO {tabla} ({cols_sql}) VALUES ({marcadores})"  # noqa: S608 -- columnas de allowlist
                )
                for fila in filas:
                    con_pg.execute(sql, tuple(fila[c] for c in columnas))
            if con_pg is not None:
                con_pg.commit()
        finally:
            if con_pg is not None:
                con_pg.close()
    finally:
        con_sqlite.close()
    return conteos


def _tabla_existe_sqlite(con_sqlite: sqlite3.Connection, tabla: str) -> bool:
    """True si la tabla existe en el SQLite de origen (una BD vieja puede no tenerla)."""
    fila = con_sqlite.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
    ).fetchone()
    return fila is not None


# --------------------------------------------------------------------------- #
# Media: disco -> S3/Garage                                                    #
# --------------------------------------------------------------------------- #


def migrar_media(*, dry_run: bool = False) -> tuple[int, int]:
    """Copia los objetos del dir de media en disco al bucket S3. Idempotente.

    Devuelve (copiados, saltados): salta el objeto cuya key YA existe en el bucket (asi
    re-correr no re-sube ni pisa). Exige S3 cableado (`S3_*`); si el dir de media no
    existe, no hay nada que migrar.
    """
    if not config.s3_configurado():
        raise SystemExit(
            "S3 no esta cableado (faltan S3_ENDPOINT/S3_ACCESS_KEY/S3_SECRET_KEY): no hay "
            "destino de objetos. Cablea las S3_* antes de migrar la media."
        )
    dir_origen = almacen_media.dir_media()
    if not dir_origen.is_dir():
        return (0, 0)

    copiados = 0
    saltados = 0
    cliente = None if dry_run else almacen_media._s3()  # noqa: SLF001 -- cliente interno del almacen
    bucket = config.s3_bucket()
    for ruta in sorted(dir_origen.iterdir()):
        if not ruta.is_file():
            continue
        nombre = ruta.name
        if dry_run:
            copiados += 1
            continue
        if _objeto_existe_s3(cliente, bucket, nombre):
            saltados += 1
            continue
        datos = ruta.read_bytes()
        cliente.put_object(
            Bucket=bucket,
            Key=nombre,
            Body=datos,
            ContentType=media_mime(nombre),
        )
        copiados += 1
    return (copiados, saltados)


def media_mime(nombre: str) -> str:
    """Mime de un objeto de media por su extension (delega en `media.mime_de`)."""
    from . import media

    return media.mime_de(nombre)


def _objeto_existe_s3(cliente, bucket: str, key: str) -> bool:  # noqa: ANN001
    """True si la key ya existe en el bucket (HEAD). False si no existe o no se puede saber."""
    try:
        cliente.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # noqa: BLE001 -- 404/NoSuchKey => no existe; cualquier otro => re-subimos
        return False


# --------------------------------------------------------------------------- #
# Orquestacion + CLI                                                           #
# --------------------------------------------------------------------------- #


def migrar(*, solo_db: bool = False, solo_media: bool = False, dry_run: bool = False) -> ResumenMigracion:
    """Ejecuta la migracion segun las banderas y devuelve el resumen de conteos."""
    resumen = ResumenMigracion()
    if not solo_media:
        resumen.filas_por_tabla = migrar_db(dry_run=dry_run)
    if not solo_db:
        copiados, saltados = migrar_media(dry_run=dry_run)
        resumen.objetos_media_copiados = copiados
        resumen.objetos_media_saltados = saltados
    return resumen


def _imprimir_resumen(resumen: ResumenMigracion, *, dry_run: bool) -> None:
    prefijo = "[dry-run] " if dry_run else ""
    if resumen.filas_por_tabla:
        print(f"{prefijo}DB (SQLite -> Postgres):")
        for tabla, n in resumen.filas_por_tabla.items():
            print(f"  {tabla:<24} {n}")
        print(f"  {'TOTAL filas':<24} {resumen.total_filas}")
    if resumen.objetos_media_copiados or resumen.objetos_media_saltados:
        print(
            f"{prefijo}Media (disco -> S3): {resumen.objetos_media_copiados} copiados, "
            f"{resumen.objetos_media_saltados} ya existian (saltados)."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m keni_consola.migracion",
        description="Cutover hosted: copia SQLite->Postgres y media de disco->S3 (idempotente).",
    )
    parser.add_argument("--solo-db", action="store_true", help="Migra solo la base de datos.")
    parser.add_argument("--solo-media", action="store_true", help="Migra solo la media (S3).")
    parser.add_argument(
        "--dry-run", action="store_true", help="Cuenta lo que migraria, sin escribir."
    )
    args = parser.parse_args(argv)
    if args.solo_db and args.solo_media:
        parser.error("--solo-db y --solo-media son mutuamente excluyentes.")

    resumen = migrar(solo_db=args.solo_db, solo_media=args.solo_media, dry_run=args.dry_run)
    _imprimir_resumen(resumen, dry_run=args.dry_run)
    print("Migracion completada." if not args.dry_run else "Dry-run completado (no se escribio nada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

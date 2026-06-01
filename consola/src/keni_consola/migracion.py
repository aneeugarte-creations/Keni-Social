"""Migracion one-shot del cutover hosted: media disco -> S3/Garage (#130).

HISTORICO (ADR 0004): originalmente este modulo orquestaba tambien el cutover de datos
SQLite -> Postgres. Tras retirar SQLite de la persistencia operacional, la DB ya solo es
Postgres y NO hay nada que copiar entre bases. `--solo-db` se conserva como NO-OP que
GARANTIZA el esquema en Postgres (idempotente) para que `deploy/deploy.sh` siga llamando
al mismo comando sin romper. La copia de media disco -> bucket S3 SI tiene sentido todavia
en clientes que aun guardan la media en disco.

Uso:

    python -m keni_consola.migracion            # asegura esquema + migra media
    python -m keni_consola.migracion --solo-db  # solo asegura esquema (compat. deploy.sh)
    python -m keni_consola.migracion --solo-media
    python -m keni_consola.migracion --dry-run  # cuenta sin escribir

IDEMPOTENTE: re-ejecutar no duplica ni pisa. La media salta el objeto si la key ya existe
en el bucket. Asi se puede correr de nuevo sin miedo si algo se interrumpio.

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
import sys
from dataclasses import dataclass, field

from . import almacen_media, config, db


@dataclass
class ResumenMigracion:
    """Conteos del cutover, para el log y para los tests."""

    db_lista: bool = False
    objetos_media_copiados: int = 0
    objetos_media_saltados: int = 0
    # CONTENIDO editorial reutilizable file -> Postgres (ADR 0006): copiado de los YAML
    # legados a las tablas nuevas (fuentes RSS, grupos de hashtags, franjas). Idempotente.
    editorial_migrado: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# DB: no-op (Postgres, ADR 0004) -> asegura el esquema                         #
# --------------------------------------------------------------------------- #


def asegurar_esquema(*, dry_run: bool = False) -> bool:
    """Asegura que el esquema Postgres existe (idempotente). Devuelve True si OK.

    Sustituto del antiguo `migrar_db` (SQLite -> Postgres): tras la ADR 0004 ya no hay
    fuente SQLite; lo unico que queda por hacer del lado de la DB es que el esquema este
    creado. Lo creamos abriendo una conexion (lo dispara `db._conectar`). En `dry_run` no
    abre conexion, solo informa.

    Exige `DATABASE_URL` (la conexion fallaria si falta): se delega en `motor_db` para que
    el mensaje sea el unico y accionable de toda la app.
    """
    if config.database_url() is None:
        raise SystemExit(
            "DATABASE_URL no esta fijada: la operacional vive en Postgres (ADR 0004). "
            "Exporta DATABASE_URL antes de correr la migracion."
        )
    if dry_run:
        return True
    db.arrancar_persistencia()  # crea/migra el esquema; no orfana nada
    return True


# --------------------------------------------------------------------------- #
# CONTENIDO editorial reutilizable: ficheros YAML -> Postgres (ADR 0006)        #
# --------------------------------------------------------------------------- #


def migrar_editorial_file_a_pg(*, dry_run: bool = False) -> dict[str, int]:
    """Copia las 3 entidades editoriales rezagadas de los YAML legados a Postgres. Idempotente.

    Lee el origen file-backed (`ficheros`) y SOLO inserta lo que falte (por id), preservando
    identidad. Re-ejecutar no duplica. El origen YAML NO se destruye (queda de respaldo). En
    `dry_run` no escribe: cuenta lo que MIGRARIA (las filas aun no presentes en Postgres).

    Va dentro del paso `--solo-db` del deploy (deploy.sh [4/5]) para que el cutover sea
    DETERMINISTA (no solo via el hook best-effort del arranque del back).
    """
    from . import migrar_contenido

    if dry_run:
        # Cuenta lo que falta sin escribir (no abre transaccion de escritura).
        from . import ficheros, repos

        faltan_f = sum(
            1 for f in ficheros.listar_fuentes_rss() if repos.obtener_fuente_rss(f["id"]) is None
        )
        faltan_g = sum(
            1 for g in ficheros.listar_grupos_hashtags()
            if repos.obtener_grupo_hashtags(g["id"]) is None
        )
        ids_pg = {fr["id"] for fr in repos.listar_franjas()}
        faltan_fr = sum(1 for fr in ficheros.listar_franjas() if fr["id"] not in ids_pg)
        return {"fuentes_rss": faltan_f, "grupos_hashtags": faltan_g, "franjas": faltan_fr}

    return {
        "fuentes_rss": migrar_contenido.migrar_fuentes_rss(),
        "grupos_hashtags": migrar_contenido.migrar_grupos_hashtags(),
        "franjas": migrar_contenido.migrar_franjas(),
    }


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
    """Ejecuta la migracion segun las banderas y devuelve el resumen."""
    resumen = ResumenMigracion()
    if not solo_media:
        resumen.db_lista = asegurar_esquema(dry_run=dry_run)
        # Tras asegurar el esquema, copia las 3 entidades editoriales rezagadas (ADR 0006).
        # Va en el paso DB (corre con `--solo-db` del deploy). Idempotente.
        resumen.editorial_migrado = migrar_editorial_file_a_pg(dry_run=dry_run)
    if not solo_db:
        copiados, saltados = migrar_media(dry_run=dry_run)
        resumen.objetos_media_copiados = copiados
        resumen.objetos_media_saltados = saltados
    return resumen


def _imprimir_resumen(resumen: ResumenMigracion, *, dry_run: bool) -> None:
    prefijo = "[dry-run] " if dry_run else ""
    if resumen.db_lista:
        print(f"{prefijo}DB: esquema Postgres asegurado (idempotente; ADR 0004).")
    if resumen.editorial_migrado:
        total = sum(resumen.editorial_migrado.values())
        print(
            f"{prefijo}Editorial (YAML -> Postgres, ADR 0006): {total} filas nuevas "
            f"{resumen.editorial_migrado}."
        )
    if resumen.objetos_media_copiados or resumen.objetos_media_saltados:
        print(
            f"{prefijo}Media (disco -> S3): {resumen.objetos_media_copiados} copiados, "
            f"{resumen.objetos_media_saltados} ya existian (saltados)."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m keni_consola.migracion",
        description="Cutover hosted: asegura esquema Postgres y copia media disco->S3 (idempotente).",
    )
    parser.add_argument(
        "--solo-db",
        action="store_true",
        help="Solo asegura el esquema Postgres (no-op tras ADR 0004; compat. deploy.sh).",
    )
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

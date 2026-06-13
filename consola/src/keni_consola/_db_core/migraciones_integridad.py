"""Migraciones de INTEGRIDAD del esquema (FKs, CHECK, version optimista, tipos jsonb).

Endurecen el esquema heredado de la era SQLite ("TEXT-para-todo, sin FKs") ahora que el
unico backend es Postgres (ADR 0004; `motor_db` solo IMITA la API de sqlite3 sobre Postgres).
Ver `docs/adr/0012` (apendice de 0004).

DISENO comun a todas estas migraciones (CRITICO porque despliegan sobre datos REALES):
  - Son IDEMPOTENTES: el patron es `DROP ... IF EXISTS` + recrear, o `ADD COLUMN IF NOT EXISTS`,
    o un cambio de tipo GUARDADO por una consulta a `information_schema`. Pueden correr dos veces
    sin fallar (y, de hecho, lo hacen en los tests: el journal `schema_migraciones` se trunca
    entre tests, asi que se re-aplican en cada arranque).
  - Cada `ADD CONSTRAINT` (FK o CHECK) va PRECEDIDO de una LIMPIEZA idempotente de las filas que
    lo violarian (huerfanos para las FK; valores fuera de la allowlist para los CHECK). Sin esto,
    el `ADD CONSTRAINT` tumbaria el arranque del deploy contra una BD con datos sucios.

Se registran como migraciones POST-DDL en `migraciones.py` (corren tras el DDL declarativo, que
ya garantiza la existencia de TODAS las tablas/columnas que estas tocan).
"""
from __future__ import annotations

from typing import Any

from ._comun import _log


def _en_sql(valores: tuple[str, ...]) -> str:
    """`('a', 'b', …)` para un `IN (...)` a partir de una allowlist de slugs.

    Los valores son constantes del codigo (allowlists de dominio), no entran datos de usuario.
    Aun asi escapamos la comilla simple (defensa en profundidad; hoy ningun slug la lleva).
    """
    interior = ", ".join("'" + v.replace("'", "''") + "'" for v in valores)
    return f"({interior})"


# --------------------------------------------------------------------------- #
# Bloque 1: FOREIGN KEYS reales en las relaciones de alto valor (hub `contenido`)
# --------------------------------------------------------------------------- #
#
# Cada tupla: (tabla_hija, columna, tabla_padre, columna_padre, on_delete).
#
# SOLO referencias OBLIGATORIAS (la columna SIEMPRE lleva un id de padre real en la practica:
# una fila por plataforma SIN su `contenido`, un subtitulo SIN su composicion, etc. no tienen
# sentido). En esas, el sentinel '' (DEFAULT del esquema heredado) nunca aparece legitimamente,
# asi que tras BORRAR los huerfanos la FK queda limpia y, en adelante, un '' lo RECHAZA la FK
# (caza el bug en vez de dejar una fila colgada). Todas con ON DELETE CASCADE: la hija es
# dependiente (su vida se ata a la del padre).
#
# Eleccion del PADRE cuando la hija tiene varias columnas-referencia:
#   - `contenido_comentarios` -> `contenido_id` (su `plataforma_id` es OPCIONAL: ''=hilo del item).
#   - `contenido_copy_versiones` / `contenido_aprobaciones` -> `plataforma_id` (SIEMPRE real al
#     insertar; su `contenido_id` se guarda como `contenido_id or ''`, opcional). El borrado del
#     `contenido` las arrastra IGUAL por transitividad (contenido -> contenido_plataforma -> …).
#   - `documento_versiones` -> `contenido_id` (la version pertenece a la pieza del tablero).
#
# NO migradas a FK (decisiones documentadas, ver ADR 0012):
#   - `metricas_pieza_snapshots.pieza_id`: NO es un `contenido_plataforma.id`. Se rellena con el
#     `id_post_metricool` (id del post en Metricool), ver `metricas_pieza._registrar_historico`.
#     Una FK a `contenido_plataforma` BORRARIA en cascada/limpieza todo el historico de metricas.
#   - Referencias OPCIONALES con sentinel '' (`contenido.evento_id`, `noticias_items.contenido_id`,
#     `noticias_items.cluster_id`): el esquema usa '' (no NULL) para "sin referencia". Una FK de
#     Postgres exige que CADA valor no-nulo exista en el padre, e '' no es NULL -> requeriria un
#     padre con id=''. Convertir '' -> NULL implica volver nullable la columna y tocar los muchos
#     call-sites que comparan/filtran por '' (riesgo alto sobre datos vivos). Se difiere.
_FKS: tuple[tuple[str, str, str, str, str], ...] = (
    ("contenido_plataforma", "contenido_id", "contenido", "id", "CASCADE"),
    ("contenido_comentarios", "contenido_id", "contenido", "id", "CASCADE"),
    ("contenido_copy_versiones", "plataforma_id", "contenido_plataforma", "id", "CASCADE"),
    ("contenido_aprobaciones", "plataforma_id", "contenido_plataforma", "id", "CASCADE"),
    ("documento_versiones", "contenido_id", "contenido", "id", "CASCADE"),
    ("video_subtitulos", "composicion_id", "video_composiciones", "id", "CASCADE"),
    ("insumos_item", "lote_id", "insumos_lote", "id", "CASCADE"),
    ("comercial_snapshots", "publicacion_id", "comercial_publicaciones", "id", "CASCADE"),
)


def _nombre_fk(tabla: str, columna: str) -> str:
    return f"fk_{tabla}_{columna}"


def _migrar_fks_hub(con: Any) -> None:
    """Crea las FKs reales del hub `contenido` y afines, limpiando huerfanos antes de cada una.

    Idempotente: `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT`. La limpieza previa
    (`DELETE` de las filas cuya columna-referencia no apunta a un padre existente, incluido el
    sentinel '') garantiza que el `ADD CONSTRAINT` no falle sobre una BD con huerfanos.
    """
    for tabla, columna, padre, col_padre, on_delete in _FKS:
        nombre = _nombre_fk(tabla, columna)
        # Limpieza de huerfanos (idempotente): borra las hijas sin padre real. Cubre el
        # sentinel '' y cualquier referencia rota por borrados que no propagaban (sin FK).
        borradas = con.execute(
            f"DELETE FROM {tabla} WHERE {columna} NOT IN (SELECT {col_padre} FROM {padre})"  # noqa: S608
        ).rowcount
        if borradas:
            _log.info(
                "FK %s: %d fila(s) huerfana(s) de %s borradas antes de crear la FK.",
                nombre, borradas, tabla,
            )
        con.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {nombre}")  # noqa: S608
        con.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} "  # noqa: S608
            f"FOREIGN KEY ({columna}) REFERENCES {padre}({col_padre}) ON DELETE {on_delete}"
        )

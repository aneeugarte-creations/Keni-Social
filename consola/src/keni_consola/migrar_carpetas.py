"""Migración one-shot: organiza el almacén de media EXISTENTE en CARPETAS por tipo + repunta refs.

Desde el cutover a carpetas, las subidas/composiciones NUEVAS ya caen en su subcarpeta
(`fotos/`, `logos/`, `plantillas/`, `render/`, `documentos/`, `biblioteca/`). Esta migración
recoloca los objetos VIEJOS (keys planas en la raíz) en su carpeta y actualiza la referencia en
Postgres, para que el bucket quede dividido por tipo y se pueda limpiar a mano.

SEGURIDAD (COPIA, no mueve): cada objeto se COPIA a su carpeta (idempotente: si ya está, no
re-sube) y la referencia se repunta a la nueva key. NO se borra el objeto plano original: así
ninguna referencia queda colgando en ningún momento (las versiones de documento y el media
embebido en plantillas, que NO migramos, siguen apuntando —y resolviéndose— a la key plana).
Una vez verificado, el equipo puede vaciar a mano los objetos planos sobrantes de la raíz desde
el explorador (Sistema → S3), o re-correr con `--purgar-planos` para borrar los que ya no
referencia ninguna de las columnas que migramos.

Columnas que migra (DIRECTAS + el array `fotos[]`):
  - contenido_plataforma.foto            -> fotos/
  - contenido_plataforma.fotos[].objeto  -> fotos/
  - contenido_plataforma.imagen          -> render/   (composite horneado / cache)
  - marca_activos.objeto                 -> logos/
  - biblioteca_media.objeto              -> biblioteca/
  - plantillas_diseno.miniatura          -> plantillas/
  - parrilla_propuesta.doc_nombre        -> documentos/

NO migra (se quedan en la raíz, plano; siguen sirviéndose con normalidad):
  - el media EMBEBIDO en documentos de capas (plantillas_diseno.documento, bloques.capas,
    documento_versiones.documento) y documento_versiones.render_objeto. Son histórico/derivable
    y su repunte exige reescribir JSON anidado; queda fuera de esta migración conservadora.

Se ejecuta A MANO en el servidor. DRY-RUN por defecto (no toca nada): imprime el plan.

    docker compose exec -T back python -m keni_consola.migrar_carpetas            # dry-run
    docker compose exec -T back python -m keni_consola.migrar_carpetas --aplicar  # migra de verdad
    docker compose exec -T back python -m keni_consola.migrar_carpetas --aplicar --purgar-planos
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from . import almacen_media, repos


def _migrable(valor: Any) -> bool:
    """True si `valor` es una key PLANA (sin carpeta) de un objeto que EXISTE en el almacén.

    Descarta vacíos, URLs externas (`imagen_fuente`), keys ya en carpeta y referencias colgadas.
    """
    if not isinstance(valor, str) or not valor:
        return False
    if almacen_media.categoria_de(valor) is not None:
        return False  # ya está en una carpeta
    return almacen_media.objeto_existe(valor)


class _Plan:
    """Acumula el plan de migración y (si `aplicar`) lo ejecuta objeto a objeto."""

    def __init__(self, *, aplicar: bool) -> None:
        self.aplicar = aplicar
        self.cuentas: Counter[str] = Counter()
        self.referenciados_planos: set[str] = set()  # keys planas que SIGUEN referenciadas

    def migrar_ref(self, valor: Any, categoria: str) -> str | None:
        """Planifica (y aplica) la migración de UNA referencia. Devuelve la nueva key o None.

        None = no hay nada que migrar (ya en carpeta, vacío, URL o inexistente): en ese caso, si
        el valor era una key plana que sigue viva, la anota para no purgarla luego.
        """
        if not _migrable(valor):
            if isinstance(valor, str) and valor and almacen_media.categoria_de(valor) is None:
                self.referenciados_planos.add(valor)
            return None
        destino = almacen_media.componer_clave(categoria, valor)
        self.cuentas[categoria] += 1
        if self.aplicar:
            # COPIA idempotente del objeto a su carpeta (no borra el plano original).
            almacen_media.promover_objeto(valor, categoria)
        return destino

    def purgar_planos(self) -> None:
        """Borra los objetos PLANOS de la raíz que ya no referencia ninguna columna migrada.

        Solo en `--aplicar --purgar-planos`. Un objeto plano se borra SOLO si fue migrado a una
        carpeta y NINGUNA referencia viva sigue apuntando a su key plana (las que dejamos sin
        migrar —media embebido en documentos— lo mantienen vivo).
        """
        if not self.aplicar:
            return
        for clave, _mtime in almacen_media.listar_objetos():
            if almacen_media.categoria_de(clave) is not None:
                continue  # ya en carpeta
            if clave in self.referenciados_planos:
                continue  # algo sin migrar lo sigue usando: no tocar
            almacen_media.borrar_objeto(clave)
            self.cuentas["purgados"] += 1


def _migrar_contenido(plan: _Plan) -> None:
    """contenido_plataforma: foto -> fotos, imagen -> render, fotos[].objeto -> fotos."""
    for fila in repos.listar_publicaciones():
        pid = fila.get("id")
        if not pid:
            continue
        campos: dict[str, Any] = {}

        nueva_foto = plan.migrar_ref(fila.get("foto"), "fotos")
        if nueva_foto:
            campos["foto"] = nueva_foto

        nueva_img = plan.migrar_ref(fila.get("imagen"), "render")
        if nueva_img:
            campos["imagen"] = nueva_img

        fotos_json = fila.get("fotos")
        nuevas_fotos, cambio = _migrar_fotos_array(plan, fotos_json)
        if cambio:
            campos["fotos"] = json.dumps(nuevas_fotos, ensure_ascii=False)

        if campos and plan.aplicar:
            repos.actualizar_contenido_plataforma(pid, campos)


def _migrar_fotos_array(plan: _Plan, fotos_json: Any) -> tuple[list[dict[str, Any]], bool]:
    """Migra el array `fotos` (`[{objeto, foco, zoom}, ...]`). Devuelve (array, hubo_cambio)."""
    if not isinstance(fotos_json, str) or not fotos_json.strip():
        return ([], False)
    try:
        items = json.loads(fotos_json)
    except (ValueError, TypeError):
        return ([], False)
    if not isinstance(items, list):
        return ([], False)
    cambio = False
    salida: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            nueva = plan.migrar_ref(item.get("objeto"), "fotos")
            if nueva:
                item = {**item, "objeto": nueva}
                cambio = True
        salida.append(item)
    return (salida, cambio)


def _migrar_simple(plan: _Plan, filas, campo: str, categoria: str, actualizar) -> None:
    """Patrón común: una columna DIRECTA (`campo`) en cada fila de `filas` -> `categoria`."""
    for fila in filas:
        fid = fila.get("id")
        if not fid:
            continue
        nueva = plan.migrar_ref(fila.get(campo), categoria)
        if nueva and plan.aplicar:
            actualizar(fid, {campo: nueva})


def migrar(*, aplicar: bool = False, purgar_planos: bool = False) -> dict[str, Any]:
    """Ejecuta (o planifica, si `aplicar=False`) la migración. Devuelve el reporte de cuentas."""
    plan = _Plan(aplicar=aplicar)

    _migrar_contenido(plan)
    _migrar_simple(
        plan, repos.listar_marca_activos(), "objeto", "logos", repos.actualizar_marca_activo
    )
    _migrar_simple(
        plan, repos.listar_media_biblioteca(), "objeto", "biblioteca",
        repos.actualizar_media_biblioteca,
    )
    _migrar_simple(
        plan, repos.listar_plantillas_diseno(), "miniatura", "plantillas",
        repos.actualizar_plantilla_diseno,
    )
    _migrar_simple(
        plan, repos.listar_propuestas_parrilla(), "doc_nombre", "documentos",
        repos.actualizar_propuesta_parrilla,
    )

    if purgar_planos:
        plan.purgar_planos()

    return {
        "aplicado": aplicar,
        "purgar_planos": purgar_planos and aplicar,
        "por_categoria": dict(plan.cuentas),
        "total_refs": sum(v for k, v in plan.cuentas.items() if k != "purgados"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Organiza el almacén de media en carpetas por tipo.")
    parser.add_argument(
        "--aplicar", action="store_true",
        help="Aplica los cambios (por defecto: dry-run, no toca nada).",
    )
    parser.add_argument(
        "--purgar-planos", action="store_true",
        help="Tras migrar, borra los objetos planos de la raíz que ya nadie referencia.",
    )
    args = parser.parse_args()

    reporte = migrar(aplicar=args.aplicar, purgar_planos=args.purgar_planos)

    modo = "APLICADO" if reporte["aplicado"] else "DRY-RUN (no se tocó nada)"
    print(f"== Migración de carpetas de media: {modo} ==")
    print(f"Referencias a migrar: {reporte['total_refs']}")
    for categoria, n in sorted(reporte["por_categoria"].items()):
        print(f"  {categoria:12} {n}")
    if not reporte["aplicado"]:
        print("\nNada se modificó. Re-ejecuta con --aplicar para migrar de verdad.")


if __name__ == "__main__":
    main()

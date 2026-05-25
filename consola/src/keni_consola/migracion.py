"""Migracion ONE-SHOT del contenido de SQLite (`consola.db`) a ficheros YAML.

Lee cada fila de las tablas de CONTENIDO del `consola.db` y la vuelca a su YAML en
el backend de ficheros (`ficheros.py`), CONSERVANDO el `id` original. Convierte
CSV/JSON->listas, 0/1->bool, preserva `publicacion.origen` (-> historial) e
`imagen` (-> media), agrupa franjas por marca y traslada los items RSS vistos.

`tareas` NO se migra (sigue viviendo en SQLite). Al terminar, renombra
`consola.db` -> `consola.db.bak` (las tareas se quedan; ver nota mas abajo).

IDEMPOTENTE y BEST-EFFORT: si una fila ya esta en disco (mismo id) no se duplica;
cualquier fila corrupta se omite con log y NO rompe la migracion ni el arranque.

NOTA sobre el .bak: como las tareas siguen en SQLite, NO borramos `consola.db`;
solo dejamos una COPIA `.bak` como respaldo del estado pre-migracion. El propio
`consola.db` permanece operativo para las tareas.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db, ficheros, indice

_log = logging.getLogger("keni_consola.migracion")


def _con_lectura(ruta: Path) -> sqlite3.Connection | None:
    """Abre el consola.db en SOLO LECTURA logica (no crea esquema). None si no existe."""
    if not ruta.exists():
        return None
    con = sqlite3.connect(str(ruta))
    con.row_factory = sqlite3.Row
    return con


def _tabla_existe(con: sqlite3.Connection, nombre: str) -> bool:
    """True si la tabla existe en la base (evita fallar en bases parciales)."""
    fila = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (nombre,)
    ).fetchone()
    return fila is not None


def _filas(con: sqlite3.Connection, tabla: str) -> list[sqlite3.Row]:
    """Filas de una tabla (vacio si la tabla no existe)."""
    if not _tabla_existe(con, tabla):
        return []
    return con.execute(f"SELECT * FROM {tabla}").fetchall()  # noqa: S608 -- nombre interno fijo


def _existe_ids(tipo: str) -> set[str]:
    """Ids ya presentes en disco para un tipo (para no duplicar; idempotencia)."""
    return {e["id"] for e in indice.listar(tipo)}


def _json_a_lista(crudo: Any) -> list[str]:
    """Convierte un JSON de lista de strings en lista (vacio si invalido)."""
    if not isinstance(crudo, str) or not crudo.strip():
        return []
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return []
    return [x for x in datos if isinstance(x, str)] if isinstance(datos, list) else []


def _fecha_creacion_con_hora(fila_fecha: Any) -> str:
    """Deriva una `fecha_creacion` con hora a partir de un dia (orden determinista).

    Si la fecha ya trae hora (ISO con 'T'), se respeta. Si es solo dia, se le pone
    medianoche (`T00:00:00`). Vacia => cadena vacia.
    """
    fecha = fila_fecha if isinstance(fila_fecha, str) else ""
    if not fecha:
        return ""
    if "T" in fecha:
        return fecha
    return f"{fecha}T00:00:00"


# --------------------------------------------------------------------------- #
# Volcado por entidad (conservando id; escribiendo directo el YAML)            #
# --------------------------------------------------------------------------- #


def _migrar_publicaciones(con: sqlite3.Connection) -> int:
    """Vuelca `publicaciones` a `<marca>/publicaciones/<id>.yaml` (preserva origen/imagen)."""
    existentes = _existe_ids("publicacion")
    n = 0
    for f in _filas(con, "publicaciones"):
        pub_id = f["id"]
        if pub_id in existentes:
            continue
        marca = f["marca"] or ""
        fecha_creacion = _fecha_creacion_con_hora(f["fecha_creacion"])
        cuerpo = {
            "titulo": f["titulo"] or "",
            "red": f["red"] or "",
            "estado": f["estado"] or "borrador",
            "veredicto": f["veredicto"] or "",
            "evergreen": bool(f["evergreen"]) if "evergreen" in f.keys() else False,
            "fecha_creacion": fecha_creacion,
            "fecha_actualizacion": _fecha_creacion_con_hora(f["fecha_actualizacion"]),
            "fecha_programada": f["fecha_programada"] or "",
            "origen": (f["origen"] or "") if "origen" in f.keys() else "",
            "imagen": (f["imagen"] or "") if "imagen" in f.keys() else "",
            "contenido": f["contenido"] or "",
        }
        ruta = ficheros._subcarpeta(marca, "publicacion") / f"{pub_id}.yaml"
        ficheros._escribir_yaml(ruta, cuerpo)
        ficheros._indexar("publicacion", marca, ruta, cuerpo)
        n += 1
    return n


def _migrar_plantillas(con: sqlite3.Connection) -> int:
    """Vuelca `plantillas` a `<marca>/plantillas/<id>.yaml`."""
    existentes = _existe_ids("plantilla")
    n = 0
    for f in _filas(con, "plantillas"):
        pid = f["id"]
        if pid in existentes:
            continue
        marca = f["marca"] or ""
        cuerpo = {
            "nombre": f["nombre"] or "",
            "red": f["red"] or "",
            "fecha": f["fecha"] or "",
            "fecha_creacion": _fecha_creacion_con_hora(f["fecha"]),
            "contenido": f["contenido"] or "",
        }
        ruta = ficheros._subcarpeta(marca, "plantilla") / f"{pid}.yaml"
        ficheros._escribir_yaml(ruta, cuerpo)
        ficheros._indexar("plantilla", marca, ruta, cuerpo)
        n += 1
    return n


def _migrar_fuentes_rss(con: sqlite3.Connection) -> int:
    """Vuelca `fuentes_rss` a `<marca>/fuentes-rss/<id>.yaml` (CSV/JSON->listas, 0/1->bool)."""
    existentes = _existe_ids("fuente_rss")
    n = 0
    for f in _filas(con, "fuentes_rss"):
        fid = f["id"]
        if fid in existentes:
            continue
        marca = f["marca"] or ""
        claves = f.keys()
        cuerpo = {
            "nombre": f["nombre"] or "",
            "url": f["url"] or "",
            "fecha": f["fecha"] or "",
            "fecha_creacion": _fecha_creacion_con_hora(f["fecha"]),
            "activo": bool(f["activo"]) if "activo" in claves else True,
            # incluir/excluir eran CSV; se conservan como CSV (la API los re-parte).
            "incluir": (f["incluir"] or "") if "incluir" in claves else "",
            "excluir": (f["excluir"] or "") if "excluir" in claves else "",
            # redes_def era un JSON de ids; se conserva como JSON (la API lo parsea).
            "redes_def": (f["redes_def"] or "") if "redes_def" in claves else "",
            "ultima_actualizacion": (f["ultima_actualizacion"] or "")
            if "ultima_actualizacion" in claves
            else "",
            "ultimo_error": (f["ultimo_error"] or "") if "ultimo_error" in claves else "",
            "ultimo_conteo": int(f["ultimo_conteo"] or 0) if "ultimo_conteo" in claves else 0,
        }
        ruta = ficheros._subcarpeta(marca, "fuente_rss") / f"{fid}.yaml"
        ficheros._escribir_yaml(ruta, cuerpo)
        ficheros._indexar("fuente_rss", marca, ruta, cuerpo)
        n += 1
    return n


def _migrar_grupos_hashtags(con: sqlite3.Connection) -> int:
    """Vuelca `grupos_hashtags` a `<marca>/hashtags/<id>.yaml` (JSON->lista nativa)."""
    existentes = _existe_ids("grupo_hashtags")
    n = 0
    for f in _filas(con, "grupos_hashtags"):
        gid = f["id"]
        if gid in existentes:
            continue
        marca = f["marca"] or ""
        cuerpo = {
            "nombre": f["nombre"] or "",
            "fecha_creacion": "",
            "hashtags": _json_a_lista(f["hashtags"]),
        }
        ruta = ficheros._subcarpeta(marca, "grupo_hashtags") / f"{gid}.yaml"
        ficheros._escribir_yaml(ruta, cuerpo)
        ficheros._indexar("grupo_hashtags", marca, ruta, cuerpo)
        n += 1
    return n


def _migrar_franjas(con: sqlite3.Connection) -> int:
    """Agrupa `franjas` POR MARCA en un `<marca>/franjas.yaml` (fusiona con lo existente)."""
    if not _tabla_existe(con, "franjas"):
        return 0
    por_marca: dict[str, list[dict[str, Any]]] = {}
    for f in _filas(con, "franjas"):
        marca = f["marca"] or ""
        por_marca.setdefault(marca, []).append(
            {
                "id": f["id"],
                "marca": marca,
                "red": f["red"] or "",
                "dia_semana": int(f["dia_semana"] or 0),
                "hora": f["hora"] or "",
            }
        )
    n = 0
    for marca, nuevas in por_marca.items():
        existentes = ficheros._leer_franjas_marca(ficheros._slug_marca(marca))
        ids_existentes = {x["id"] for x in existentes}
        fusion = existentes + [x for x in nuevas if x["id"] not in ids_existentes]
        ficheros._escribir_franjas_marca(marca, fusion)
        n += sum(1 for x in nuevas if x["id"] not in ids_existentes)
    return n


def _migrar_historial(con: sqlite3.Connection) -> int:
    """Vuelca `skill_historial` a `<marca>/historial/<YYYY>/<MM>/<id>.yaml`."""
    existentes = _existe_ids("historial")
    n = 0
    for f in _filas(con, "skill_historial"):
        hid = f["id"]
        if hid in existentes:
            continue
        marca = f["marca"] or ""
        fecha = f["fecha"] or ""
        piezas_crudo = f["piezas"] if "piezas" in f.keys() else ""
        piezas = db._parsear_piezas_historial(piezas_crudo)
        cuerpo = {
            "skill": f["skill"] or "",
            "fecha": fecha,
            "fecha_creacion": _fecha_creacion_con_hora(fecha),
            "titulo": (f["titulo"] or "") if "titulo" in f.keys() else "",
            "piezas": piezas,
            "resultado": f["resultado"] or "",
        }
        anio, mes = _anio_mes(fecha)
        carpeta = ficheros.carpeta_marca(marca) / "historial" / anio / mes
        ruta = carpeta / f"{hid}.yaml"
        ficheros._escribir_yaml(ruta, cuerpo)
        ficheros._indexar("historial", marca, ruta, cuerpo)
        n += 1
    return n


def _anio_mes(fecha: str) -> tuple[str, str]:
    """(YYYY, MM) de una fecha ISO; cae al ano/mes actuales si no parsea."""
    try:
        dt = datetime.fromisoformat(fecha)
        return f"{dt.year:04d}", f"{dt.month:02d}"
    except (ValueError, TypeError):
        hoy = datetime.now()
        return f"{hoy.year:04d}", f"{hoy.month:02d}"


def _migrar_rss_vistos(con: sqlite3.Connection) -> int:
    """Traslada `rss_items_vistos` al `.keni/rss-vistos.yaml` de la marca de cada fuente."""
    if not _tabla_existe(con, "rss_items_vistos"):
        return 0
    # Mapa fuente_id -> marca (a partir de las fuentes ya en disco).
    marca_de: dict[str, str] = {}
    for slug in ficheros._marcas_en_disco():
        base = ficheros.raiz_datos() / slug / ficheros._SUBDIR["fuente_rss"]
        if base.is_dir():
            for p in base.glob("*.yaml"):
                marca_de[p.stem] = ficheros._marca_de_slug(slug)
    n = 0
    for f in _filas(con, "rss_items_vistos"):
        fuente_id = f["fuente_id"]
        clave = f["clave"]
        if not (isinstance(fuente_id, str) and isinstance(clave, str) and clave):
            continue
        marca = marca_de.get(fuente_id, "")
        vistos = ficheros._leer_vistos(marca)
        claves = set(vistos.get(fuente_id, []))
        if clave not in claves:
            claves.add(clave)
            vistos[fuente_id] = sorted(claves)
            ficheros._escribir_vistos(marca, vistos)
            n += 1
    return n


# --------------------------------------------------------------------------- #
# Orquestacion                                                                #
# --------------------------------------------------------------------------- #


def migrar_a_ficheros(*, hacer_bak: bool = True) -> dict[str, int]:
    """Migra TODO el contenido de `consola.db` a ficheros YAML (idempotente, best-effort).

    Devuelve un dict `{entidad: nº filas migradas}`. Si no hay `consola.db`, devuelve
    contadores en cero (nada que migrar). Tras migrar, si `hacer_bak`, deja una COPIA
    `consola.db.bak` como respaldo (las tareas siguen usando `consola.db`).
    """
    ruta = db.ruta_db()
    conteos = {
        "publicaciones": 0,
        "plantillas": 0,
        "fuentes_rss": 0,
        "grupos_hashtags": 0,
        "franjas": 0,
        "skill_historial": 0,
        "rss_items_vistos": 0,
    }
    con = _con_lectura(ruta)
    if con is None:
        return conteos
    try:
        # El orden importa: fuentes ANTES que rss_vistos (para resolver su marca).
        conteos["publicaciones"] = _migrar_publicaciones(con)
        conteos["plantillas"] = _migrar_plantillas(con)
        conteos["fuentes_rss"] = _migrar_fuentes_rss(con)
        conteos["grupos_hashtags"] = _migrar_grupos_hashtags(con)
        conteos["franjas"] = _migrar_franjas(con)
        conteos["skill_historial"] = _migrar_historial(con)
        conteos["rss_items_vistos"] = _migrar_rss_vistos(con)
    except Exception:  # noqa: BLE001 -- best-effort: una fila mala no rompe el arranque
        _log.exception("Fallo durante la migracion a ficheros (best-effort).")
    finally:
        con.close()

    if hacer_bak:
        try:
            shutil.copy2(str(ruta), str(ruta) + ".bak")
        except OSError:
            _log.warning("No se pudo crear el respaldo .bak de %s", ruta)
    return conteos


def _texto_resumen(conteos: dict[str, int]) -> str:
    """Resumen humano de la migracion para imprimir por consola."""
    lineas = ["Migracion a ficheros YAML completada:"]
    for entidad, n in conteos.items():
        lineas.append(f"  - {entidad}: {n}")
    return "\n".join(lineas)

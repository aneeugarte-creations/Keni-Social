#!/usr/bin/env python3
"""brief-matutino: lee lo que la marca YA TRABAJÓ (publicaciones) para el cruce.

Para la junta de las 11:30 el equipo necesita separar los TEMAS CALIENTES del día
de lo que NOSOTROS YA TRABAJAMOS. Este script aporta el segundo lado: lee el
historial editorial de la Consola (las publicaciones que la marca ya creó, sea
borrador, aprobado, programado o publicado) dentro de una ventana de días, y lo
imprime como markdown escaneable por stdout. La skill (Claude) cruza esos títulos
contra las señales del día (`buscar.py`) para marcar cada tema como "ya trabajado"
o "pendiente".

Este script NO decide nada ni inventa: solo LEE los ficheros que la Consola ya
escribió. Si no hay almacén o está vacío, lo dice con honestidad (degradación) y
la skill trata TODOS los temas como pendientes, sin fingir cobertura.

Dónde vive el historial (igual resolución que la Consola, `rutas.raiz_proyectos` +
`ficheros.raiz_datos`), de mayor a menor prioridad:
  1. --raiz RUTA            (override explícito, p. ej. en pruebas)
  2. $KENI_CONSOLA_RAIZ     (override de la Consola)
  3. $KENI_DATA_DIR/keni-proyectos   (despliegue en contenedor)
  4. ~/keni-proyectos       (local, por defecto)
y dentro: <raiz>/<marca>/publicaciones/<id>.yaml

Uso:
    python3 publicado.py --marca claro-sports --dias 4
    python3 publicado.py --marca unotv --raiz /ruta/a/keni-proyectos

Solo stdlib salvo PyYAML, que es OPCIONAL: si está, se usa; si falta, un lector
mínimo extrae los campos escalares de cabecera (suficiente para el brief). Nunca
revienta con un traceback: ante cualquier fallo de un fichero, lo omite y sigue.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Sub-carpeta de contenido por marca (espejo de keni_consola.rutas.SUBDIR_PROYECTOS)
# y de la sub-carpeta de publicaciones (keni_consola.ficheros._SUBDIR["publicacion"]).
_SUBDIR_PROYECTOS = "keni-proyectos"
_SUBDIR_PUBLICACIONES = "publicaciones"

# Estados editoriales conocidos (espejo de keni_consola.estados.ESTADOS_PUBLICACION).
# Si un fichero trae otra cosa, la mostramos igual: aquí solo leemos, no validamos.
_ESTADOS = ("borrador", "aprobado", "programado", "publicado")


# --------------------------------------------------------------------------- #
# Resolución de la raíz de datos (espejo de la Consola)                        #
# --------------------------------------------------------------------------- #


def raiz_datos(override: str | None = None) -> Path:
    """Raíz del contenido editorial por marca, con la misma prioridad que la Consola."""
    if override:
        return Path(override).expanduser()
    if entorno := os.environ.get("KENI_CONSOLA_RAIZ"):
        return Path(entorno).expanduser()
    if datadir := os.environ.get("KENI_DATA_DIR"):
        return Path(datadir).expanduser() / _SUBDIR_PROYECTOS
    return Path.home() / _SUBDIR_PROYECTOS


def _carpeta_publicaciones(raiz: Path, marca: str) -> Path:
    """`<raiz>/<marca>/publicaciones/` (la marca ya es un slug-guion, p. ej. claro-sports)."""
    return raiz / (marca or "_sin-marca") / _SUBDIR_PUBLICACIONES


# --------------------------------------------------------------------------- #
# Lectura del YAML (PyYAML si está; si no, lector mínimo de cabecera)          #
# --------------------------------------------------------------------------- #

# Campos de cabecera que necesitamos para el brief; el cuerpo (`contenido`) se ignora.
_CAMPOS = ("titulo", "red", "estado", "fecha_creacion", "fecha_actualizacion", "origen")


def _leer_yaml_minimo(texto: str) -> dict[str, str]:
    """Extrae los escalares de cabecera sin PyYAML (fallback honesto).

    Lee `clave: valor` de las líneas de primer nivel hasta el primer bloque
    literal (`clave: |`), que es donde empieza el `contenido` multilínea. No
    pretende ser un parser de YAML completo: solo los pocos campos escalares que
    el brief usa, que la Consola siempre escribe como `clave: valor` en una línea.
    """
    datos: dict[str, str] = {}
    for linea in texto.splitlines():
        if not linea or linea[0] in " \t#":
            continue  # cuerpo indentado, línea en blanco o comentario
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave = clave.strip()
        valor = valor.strip()
        if valor in ("|", "|-", ">", ">-"):
            break  # empieza un bloque literal (el contenido): paramos
        if clave in _CAMPOS:
            datos[clave] = valor.strip("'\"")
    return datos


def _cargar(ruta: Path) -> dict[str, str] | None:
    """Carga una publicación como dict de strings; None si no se puede leer."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        import yaml  # opcional

        datos = yaml.safe_load(texto)
        if not isinstance(datos, dict):
            return None
        return {c: str(datos.get(c, "") or "") for c in _CAMPOS}
    except ImportError:
        return _leer_yaml_minimo(texto)
    except Exception:  # noqa: BLE001 -- YAML corrupto: lo omitimos, no reventamos
        return None


# --------------------------------------------------------------------------- #
# Antigüedad                                                                   #
# --------------------------------------------------------------------------- #


def _parsear_fecha(valor: str) -> datetime | None:
    """Parsea una fecha ISO (`YYYY-MM-DDTHH:MM:SS` o `YYYY-MM-DD`). None si no se puede."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _edad(fecha: datetime | None, ahora: datetime) -> tuple[float, str]:
    """De una fecha de creación saca (horas_de_antiguedad, texto legible)."""
    if fecha is None:
        return float("inf"), "fecha desconocida"
    horas = (ahora - fecha).total_seconds() / 3600
    if horas < 0:
        horas = 0.0
    if horas < 1:
        return horas, "hace <1 h"
    if horas < 24:
        return horas, f"hace {int(horas)} h"
    dias, resto = divmod(int(horas), 24)
    return horas, f"hace {dias} d {resto} h"


# --------------------------------------------------------------------------- #
# Recolección                                                                  #
# --------------------------------------------------------------------------- #


def trabajado(
    marca: str, *, dias: int, raiz: Path, ahora: datetime | None = None
) -> tuple[list[dict], str | None]:
    """Publicaciones de `marca` creadas/actualizadas dentro de `dias`.

    Devuelve `(items, aviso)`. `items` viene ordenado de lo más reciente a lo más
    viejo; cada uno es `{titulo, red, estado, edad, horas, origen}`. `aviso` es un
    mensaje de degradación honesta (sin almacén / vacío) o None si hubo datos.
    """
    ahora = ahora or datetime.now()
    carpeta = _carpeta_publicaciones(raiz, marca)
    if not carpeta.is_dir():
        return [], (
            f"No hay almacén de publicaciones para «{marca}» en {carpeta}. "
            "Trata todos los temas como PENDIENTES (sin historial que cruzar)."
        )

    ventana_horas = max(dias, 0) * 24
    items: list[dict] = []
    leidos = 0
    for ruta in sorted(carpeta.glob("*.yaml")):
        datos = _cargar(ruta)
        if datos is None:
            continue
        leidos += 1
        # Usamos la fecha más reciente (creación o actualización) para la ventana:
        # un borrador retocado hoy es trabajo de hoy aunque naciera ayer.
        f_creacion = _parsear_fecha(datos.get("fecha_creacion", ""))
        f_actual = _parsear_fecha(datos.get("fecha_actualizacion", ""))
        fecha = max([f for f in (f_creacion, f_actual) if f], default=None)
        horas, legible = _edad(fecha, ahora)
        if ventana_horas and horas > ventana_horas:
            continue
        items.append(
            {
                "titulo": datos.get("titulo", "") or "(sin título)",
                "red": datos.get("red", "") or "—",
                "estado": datos.get("estado", "") or "—",
                "edad": legible,
                "horas": horas,
                "origen": datos.get("origen", "") or "",
            }
        )

    items.sort(key=lambda d: d["horas"])
    if leidos == 0:
        return [], (
            f"El almacén de «{marca}» existe pero no tiene publicaciones legibles. "
            "Trata todos los temas como PENDIENTES."
        )
    if not items:
        return [], (
            f"«{marca}» tiene publicaciones, pero ninguna dentro de los últimos "
            f"{dias} día(s). No hay trabajo reciente que cruzar; trata los temas como PENDIENTES."
        )
    return items, None


# --------------------------------------------------------------------------- #
# Salida                                                                        #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Lee lo que la marca YA TRABAJÓ (publicaciones) para el cruce del brief."
    )
    ap.add_argument("--marca", required=True, help="Id de la marca (slug-guion, p. ej. claro-sports).")
    ap.add_argument("--dias", type=int, default=4, help="Ventana en días hacia atrás, def. 4.")
    ap.add_argument("--raiz", default="", help="Override de la raíz de datos (def: la de la Consola).")
    args = ap.parse_args(argv)

    raiz = raiz_datos(args.raiz or None)
    ahora = datetime.now()
    print(f"# Ya trabajado por nosotros (publicado.py · {ahora:%Y-%m-%d %H:%M} · marca {args.marca} · ≤ {args.dias} d)\n")

    items, aviso = trabajado(args.marca, dias=args.dias, raiz=raiz, ahora=ahora)
    if aviso:
        print(f"> {aviso}")
        return 0

    print(f"Encontradas {len(items)} pieza(s) recientes en el historial editorial:\n")
    for it in items:
        origen = f" · vía {it['origen']}" if it["origen"] else ""
        print(f"- **{it['titulo']}** · {it['red']} · {it['estado']} · {it['edad']}{origen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

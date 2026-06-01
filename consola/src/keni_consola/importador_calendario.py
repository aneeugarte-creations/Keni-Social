"""Importador de calendario editorial (Excel/CSV) al tablero de contenido.

PROBLEMA QUE RESUELVE
=====================
El equipo planifica su calendario (temas + fechas + compromisos) en hojas de Excel/CSV. Hoy
NO hay forma de meter ese plan en el tablero: habria que teclear cada item a mano. Este modulo
parsea un archivo `.xlsx`/`.csv` y crea contenido del tablero (`repos.crear_contenido`), de modo
que el plan del equipo entra de golpe a la "lista viva" y se ordena con el resto de fuentes
(Radar, RSS, alta manual). Es la pieza H1 de `docs/contexto/2026-05-31-lista-viva-angel.md`.

DOS CAPAS (como `radar_auto`):
  - SELECCION/PARSEO es PURO y testeable (`parsear`, `_filas_desde_tabla`): bytes -> filas
    normalizadas + lista de errores honesta (una fila mala se reporta, NO rompe la importacion).
  - ESCRITURA (`importar_a_tablero`) reutiliza el MISMO camino que `desde_radar` /
    `radar_auto.promover_temas`: `repos.crear_contenido(origen='import-calendario', ...)`. Los
    contenidos marcados "obligatorio" se etiquetan `compromiso` (sin tocar el enum de `flujo`).

CONSERVADOR:
  - Mapeo de cabeceras flexible (sinonimos es/en) y tolerante a acentos/espacios.
  - Marca que no existe en el catalogo -> contenido SIN marca (no se inventa, no se rompe).
  - Redes desconocidas se descartan en silencio; el resto se conserva.
  - Dedup por (titulo normalizado + fecha) contra lo ya importado por este modulo.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from . import marcas, redes, repos

_log = logging.getLogger("keni_consola.importador_calendario")

# Origen reservado de los contenidos creados por este modulo (para dedup y para que la UI
# distinga el origen "calendario" del manual / radar / rss).
ORIGEN = "import-calendario"

# Etiqueta con la que se marca un contenido "obligatorio por compromiso".
ETIQUETA_COMPROMISO = "compromiso"

# Limites defensivos (un calendario real no tiene millones de filas).
_MAX_FILAS = 5000
_MAX_TITULO = 300
_MAX_TEXTO = 8000

# Sinonimos de cabecera -> campo canonico. Las claves se comparan ya normalizadas
# (minusculas, sin acentos, espacios colapsados).
_SINONIMOS: dict[str, set[str]] = {
    "titulo": {"titulo", "tema", "asunto", "contenido", "title", "topic", "nombre", "post"},
    "fecha": {
        "fecha", "dia", "date", "fecha objetivo", "fecha de publicacion",
        "publicar", "publicacion", "cuando",
    },
    "marca": {"marca", "cuenta", "brand", "cliente", "account"},
    "redes": {
        "red", "redes", "plataforma", "plataformas", "network", "networks",
        "canal", "canales", "social",
    },
    "prioridad": {"prioridad", "priority", "importancia"},
    "compromiso": {
        "compromiso", "obligatorio", "obligatoria", "mandatory", "commitment", "fijo",
    },
    "notas": {"notas", "nota", "detalle", "descripcion", "comentarios", "notes", "comment"},
}

# Strings que cuentan como "si" para el campo booleano `compromiso`.
_VERDADEROS = {"si", "sí", "x", "true", "verdadero", "1", "obligatorio", "yes", "y"}

# Mapeo de texto de prioridad -> valor canonico ('alta'|'media'|'baja').
_PRIORIDAD_ALTA = {"alta", "high", "urgente", "urgent", "1", "p1"}
_PRIORIDAD_BAJA = {"baja", "low", "2", "3", "p3"}


@dataclass
class FilaCalendario:
    """Una fila del calendario, ya normalizada y lista para crear contenido."""

    titulo: str
    fecha: str = ""  # ISO YYYY-MM-DD, o "" si no se pudo interpretar
    marca_id: str = ""  # id canonico del catalogo, o "" si no se reconocio
    redes: list[str] = field(default_factory=list)  # ids canonicos de red
    prioridad: str = "media"
    compromiso: bool = False
    notas: str = ""


# --------------------------------------------------------------------------- #
# Normalizacion (puro)                                                         #
# --------------------------------------------------------------------------- #


def _normaliza(texto: object) -> str:
    """Minusculas, sin acentos, espacios colapsados. Para comparar cabeceras/valores."""
    s = "" if texto is None else str(texto)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.strip().lower().split())


def _mapa_cabeceras(cabeceras: list[str]) -> dict[str, int]:
    """Mapea campo canonico -> indice de columna a partir de la fila de cabeceras."""
    mapa: dict[str, int] = {}
    for idx, bruta in enumerate(cabeceras):
        norm = _normaliza(bruta)
        for campo, sinonimos in _SINONIMOS.items():
            if campo in mapa:
                continue
            if norm in sinonimos:
                mapa[campo] = idx
    return mapa


def _marcas_por_nombre() -> dict[str, str]:
    """Indice nombre/etiqueta/id normalizado -> id canonico, para reconocer la marca del Excel."""
    indice: dict[str, str] = {}
    for marca_id, etiqueta in marcas.opciones():
        indice[_normaliza(marca_id)] = marca_id
        indice[_normaliza(etiqueta)] = marca_id
    return indice


def _redes_por_nombre() -> dict[str, str]:
    """Indice nombre/id normalizado -> id canonico de red (+ el canal extra 'web')."""
    indice: dict[str, str] = {"web": "web"}
    for red_id in redes.ids():
        indice[_normaliza(red_id)] = red_id
        indice[_normaliza(redes.nombre_por_id(red_id))] = red_id
    return indice


def _parse_fecha(valor: object) -> str:
    """Interpreta una fecha (datetime de openpyxl o texto) a ISO YYYY-MM-DD; "" si no se puede."""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = ("" if valor is None else str(valor)).strip()
    if not texto:
        return ""
    # ISO (admite hora detras) primero.
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", texto)
    if m:
        return _fecha_segura(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # dd/mm/yyyy o dd-mm-yyyy (formato MX habitual). Acepta año de 2 o 4 cifras.
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", texto)
    if m:
        dia, mes, anio = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if anio < 100:
            anio += 2000
        return _fecha_segura(anio, mes, dia)
    return ""


def _fecha_segura(anio: int, mes: int, dia: int) -> str:
    """ISO de (anio, mes, dia) si es una fecha real; "" si no (p.ej. 31/02)."""
    try:
        return date(anio, mes, dia).isoformat()
    except ValueError:
        return ""


def _parse_prioridad(valor: object, *, compromiso: bool) -> str:
    """Texto -> 'alta'|'media'|'baja'. Un compromiso sin prioridad explicita sube a 'alta'."""
    norm = _normaliza(valor)
    if norm in _PRIORIDAD_ALTA:
        return "alta"
    if norm in _PRIORIDAD_BAJA:
        return "baja"
    if not norm and compromiso:
        return "alta"
    return "media"


def _parse_redes(valor: object, indice: dict[str, str]) -> list[str]:
    """Divide 'IG, X / TikTok' en ids canonicos; descarta lo que no reconoce. Sin duplicados."""
    texto = "" if valor is None else str(valor)
    crudas = re.split(r"[,;/|]+", texto)
    salida: list[str] = []
    for cruda in crudas:
        red = indice.get(_normaliza(cruda))
        if red and red not in salida:
            salida.append(red)
    return salida


def _es_verdadero(valor: object) -> bool:
    return _normaliza(valor) in _VERDADEROS


# --------------------------------------------------------------------------- #
# Lectura de la tabla cruda (CSV / XLSX)                                       #
# --------------------------------------------------------------------------- #


def _tabla_desde_csv(data: bytes) -> list[list[Any]]:
    """Bytes de un CSV -> filas de celdas (texto). Tolera BOM y latin-1."""
    try:
        texto = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = data.decode("latin-1", errors="replace")
    sample = texto[:4096]
    try:
        dialecto: Any = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    return [list(fila) for fila in csv.reader(io.StringIO(texto), dialecto)]


def _tabla_desde_xlsx(data: bytes) -> list[list[Any]]:
    """Bytes de un .xlsx -> filas de celdas (valores) de la PRIMERA hoja."""
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - dependencia declarada en pyproject
        raise ImportError(
            "Falta 'openpyxl' para leer .xlsx. Instala las dependencias de la consola."
        ) from exc
    libro = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        hoja = libro.worksheets[0]
        return [list(fila) for fila in hoja.iter_rows(values_only=True)]
    finally:
        libro.close()


def _leer_tabla(data: bytes, *, nombre: str) -> list[list[Any]]:
    """Despacha por extension/firma del archivo. .xlsx (ZIP 'PK') vs CSV/texto."""
    nombre_norm = (nombre or "").lower()
    if nombre_norm.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        return _tabla_desde_xlsx(data)
    return _tabla_desde_csv(data)


# --------------------------------------------------------------------------- #
# Tabla cruda -> filas normalizadas (puro)                                     #
# --------------------------------------------------------------------------- #


def _primera_no_vacia(tabla: list[list[Any]]) -> int:
    for idx, fila in enumerate(tabla):
        if any(_normaliza(c) for c in fila):
            return idx
    return -1


def _filas_desde_tabla(
    tabla: list[list[Any]],
) -> tuple[list[FilaCalendario], list[dict[str, Any]]]:
    """Filas crudas -> (filas validas, errores). PURO y determinista.

    La primera fila no vacia es la CABECERA. Cada fila siguiente con titulo es una pieza; las
    filas sin titulo (o sin cabecera 'titulo' reconocida) se reportan como error, no rompen.
    """
    errores: list[dict[str, Any]] = []
    idx_cab = _primera_no_vacia(tabla)
    if idx_cab < 0:
        return [], [{"fila": 0, "motivo": "El archivo no tiene filas con datos."}]

    cabeceras = [("" if c is None else str(c)) for c in tabla[idx_cab]]
    mapa = _mapa_cabeceras(cabeceras)
    if "titulo" not in mapa:
        return [], [{
            "fila": idx_cab + 1,
            "motivo": "No se encontro una columna de titulo/tema. Cabeceras: "
            + ", ".join(h for h in cabeceras if h.strip()),
        }]

    idx_marcas = _marcas_por_nombre()
    idx_redes = _redes_por_nombre()

    def celda(fila: list[Any], campo: str) -> Any:
        pos = mapa.get(campo)
        if pos is None or pos >= len(fila):
            return None
        return fila[pos]

    filas: list[FilaCalendario] = []
    for desplazamiento, fila in enumerate(tabla[idx_cab + 1 :], start=idx_cab + 2):
        if len(filas) >= _MAX_FILAS:
            errores.append({
                "fila": desplazamiento,
                "motivo": f"Se superó el máximo de {_MAX_FILAS} filas; el resto se omitió.",
            })
            break
        if not any(_normaliza(c) for c in fila):
            continue  # fila en blanco: se ignora en silencio
        titulo = ("" if celda(fila, "titulo") is None else str(celda(fila, "titulo"))).strip()
        if not titulo:
            errores.append({"fila": desplazamiento, "motivo": "Fila sin título; se omitió."})
            continue
        compromiso = _es_verdadero(celda(fila, "compromiso"))
        marca_norm = _normaliza(celda(fila, "marca"))
        notas = ("" if celda(fila, "notas") is None else str(celda(fila, "notas"))).strip()
        filas.append(
            FilaCalendario(
                titulo=titulo[:_MAX_TITULO],
                fecha=_parse_fecha(celda(fila, "fecha")),
                marca_id=idx_marcas.get(marca_norm, ""),
                redes=_parse_redes(celda(fila, "redes"), idx_redes),
                prioridad=_parse_prioridad(celda(fila, "prioridad"), compromiso=compromiso),
                compromiso=compromiso,
                notas=notas[:_MAX_TEXTO],
            )
        )
    return filas, errores


def parsear(data: bytes, *, nombre: str) -> tuple[list[FilaCalendario], list[dict[str, Any]]]:
    """Bytes de un .xlsx/.csv -> (filas normalizadas, errores). No escribe nada."""
    tabla = _leer_tabla(data, nombre=nombre)
    return _filas_desde_tabla(tabla)


# --------------------------------------------------------------------------- #
# Escritura al tablero (mismo camino que radar_auto / desde_radar)             #
# --------------------------------------------------------------------------- #


def _clave(titulo: str, fecha: str) -> str:
    return f"{_normaliza(titulo)}|{(fecha or '').strip()}"


def claves_ya_importadas() -> set[str]:
    """Claves (titulo+fecha) de lo ya importado por este modulo, para no duplicar."""
    try:
        items = repos.listar_contenido()
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar la importacion
        return set()
    return {
        _clave(it.get("titulo", ""), it.get("fecha_objetivo", ""))
        for it in items
        if (it.get("origen") or "") == ORIGEN
    }


def _id_etiqueta_compromiso() -> str:
    """Id de la etiqueta 'compromiso' (la crea si no existe). Best-effort idempotente."""
    for et in repos.listar_etiquetas():
        if _normaliza(et.get("nombre", "")) == ETIQUETA_COMPROMISO:
            return et.get("id", "")
    return repos.crear_etiqueta(nombre=ETIQUETA_COMPROMISO).get("id", "")


def importar_a_tablero(
    filas: list[FilaCalendario],
    *,
    autor: dict[str, str] | None = None,
    marca_defecto: str = "",
) -> dict[str, Any]:
    """Crea contenido del tablero a partir de filas ya parseadas. Devuelve un resumen.

    Espeja `radar_auto.promover_temas`: `repos.crear_contenido(origen='import-calendario', ...)`
    + filas por plataforma + etiqueta `compromiso` cuando aplica. Dedup por (titulo+fecha).
    `marca_defecto` (id canonico) se aplica a las filas sin marca reconocida.
    """
    ya = claves_ya_importadas()
    defecto = marca_defecto if marcas.es_marca(marca_defecto) else ""
    etiqueta_compromiso_id = ""
    creados: list[dict[str, Any]] = []
    omitidos: list[dict[str, Any]] = []

    for fila in filas:
        clave = _clave(fila.titulo, fila.fecha)
        if clave in ya:
            omitidos.append({"titulo": fila.titulo, "motivo": "Ya importado (mismo título y fecha)."})
            continue
        ya.add(clave)
        item = repos.crear_contenido(
            clase="contenido",
            flujo="",
            titulo=fila.titulo[:_MAX_TITULO],
            descripcion=fila.notas[:_MAX_TEXTO],
            marca=fila.marca_id or defecto,
            prioridad=fila.prioridad,
            fecha_objetivo=fila.fecha,
            autor=autor,
            origen=ORIGEN,
        )
        for red in fila.redes:
            repos.crear_contenido_plataforma(contenido_id=item["id"], red=red)
        if fila.compromiso:
            if not etiqueta_compromiso_id:
                etiqueta_compromiso_id = _id_etiqueta_compromiso()
            if etiqueta_compromiso_id:
                repos.asignar_etiqueta(item["id"], etiqueta_compromiso_id)
        creados.append(item)

    if creados:
        _log.info("Import calendario: %d contenido(s) creado(s), %d omitido(s).", len(creados), len(omitidos))
    return {"creados": creados, "omitidos": omitidos}

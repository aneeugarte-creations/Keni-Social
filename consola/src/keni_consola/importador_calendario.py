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
    contenidos marcados "obligatorio" se etiquetan `compromiso` y los de la "evergreen list" del
    equipo se etiquetan `evergreen` (sin tocar el enum de `flujo`).

CONSERVADOR:
  - Mapeo de cabeceras flexible (sinonimos es/en) y tolerante a acentos/espacios.
  - Marca que no existe en el catalogo -> contenido SIN marca (no se inventa, no se rompe).
  - Redes desconocidas se descartan en silencio; el resto se conserva.
  - Dedup por (titulo normalizado + fecha) contra lo ya importado por este modulo.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections.abc import Callable
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

# Etiqueta con la que se marca un contenido de la "evergreen list" (lista del equipo).
ETIQUETA_EVERGREEN = "evergreen"

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
    "evergreen": {
        # Terminología evergreen + sinónimos ES/EN…
        "evergreen", "evergreen list", "lista evergreen", "verde", "lista verde",
        # …y RETROCOMPAT: el equipo de AMX ya escribe "green"/"green list" en sus calendarios.
        "green", "green list", "lista green", "greenlist",
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
    evergreen: bool = False
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
        evergreen = _es_verdadero(celda(fila, "evergreen"))
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
                evergreen=evergreen,
                notas=notas[:_MAX_TEXTO],
            )
        )
    return filas, errores


def parsear(data: bytes, *, nombre: str) -> tuple[list[FilaCalendario], list[dict[str, Any]]]:
    """Bytes de un .xlsx/.csv -> (filas normalizadas, errores). No escribe nada."""
    tabla = _leer_tabla(data, nombre=nombre)
    return _filas_desde_tabla(tabla)


# --------------------------------------------------------------------------- #
# Extracción AGNÓSTICA de formato con Claude (cualquier archivo: PDF, imagen,  #
# captura, Word, Excel raro, texto…). El parser rígido de arriba es el camino  #
# RÁPIDO y determinista para .xlsx/.csv bien formados; cuando no saca filas    #
# (formato no tabular o cabeceras irreconocibles), la API cae a esto: deja que #
# Claude LEA el archivo y devuelva el mismo calendario en JSON. El normalizado #
# posterior (marca→id, redes, fecha, prioridad) reusa los helpers PUROS de     #
# arriba, así que un registro de Claude pasa por las MISMAS reglas que una     #
# fila de Excel.                                                               #
# --------------------------------------------------------------------------- #

# Wall-timeout del subproceso `claude` (s). La importación es una acción que el
# usuario inicia y espera; topamos para no colgar la petición indefinidamente.
_CLAUDE_TIMEOUT_S = 180

# Ejecutor de `claude` inyectable: (prompt, dir_permitido) -> texto final. El default es
# el subproceso real; los tests inyectan uno falso para no depender del binario.
Ejecutor = Callable[[str, str], str]


def _filas_desde_registros(
    registros: list[Any],
) -> tuple[list[FilaCalendario], list[dict[str, Any]]]:
    """Lista de dicts (de Claude) -> (filas válidas, errores). PURO.

    Cada registro lleva las MISMAS claves que una columna del Excel
    (titulo/fecha/marca/redes/prioridad/compromiso/evergreen/notas) y pasa por los mismos
    normalizadores. Un registro sin título se reporta como error, no rompe el resto.
    """
    errores: list[dict[str, Any]] = []
    idx_marcas = _marcas_por_nombre()
    idx_redes = _redes_por_nombre()
    filas: list[FilaCalendario] = []
    for i, reg in enumerate(registros, start=1):
        if len(filas) >= _MAX_FILAS:
            errores.append({"fila": i, "motivo": f"Se superó el máximo de {_MAX_FILAS} filas; el resto se omitió."})
            break
        if not isinstance(reg, dict):
            errores.append({"fila": i, "motivo": "Registro no es un objeto; se omitió."})
            continue
        titulo = str(reg.get("titulo") or reg.get("tema") or "").strip()
        if not titulo:
            errores.append({"fila": i, "motivo": "Registro sin título; se omitió."})
            continue
        compromiso = _es_verdadero(reg.get("compromiso"))
        evergreen = _es_verdadero(reg.get("evergreen"))
        redes_val = reg.get("redes")
        if isinstance(redes_val, list):
            redes_val = ",".join(str(x) for x in redes_val)
        notas = str(reg.get("notas") or "").strip()
        filas.append(
            FilaCalendario(
                titulo=titulo[:_MAX_TITULO],
                fecha=_parse_fecha(reg.get("fecha")),
                marca_id=idx_marcas.get(_normaliza(reg.get("marca")), ""),
                redes=_parse_redes(redes_val, idx_redes),
                prioridad=_parse_prioridad(reg.get("prioridad"), compromiso=compromiso),
                compromiso=compromiso,
                evergreen=evergreen,
                notas=notas[:_MAX_TEXTO],
            )
        )
    return filas, errores


def _extraer_json(texto: str) -> list[Any] | None:
    """Saca la lista de filas del texto de Claude. Tolera ```json fences y `{"filas":[…]}`."""
    if not texto or not texto.strip():
        return None
    s = texto.strip()
    cerca = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if cerca:
        s = cerca.group(1).strip()
    data: Any = None
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        inicio = next((i for i, c in enumerate(s) if c in "[{"), -1)
        if inicio < 0:
            return None
        try:
            data = json.loads(s[inicio:])
        except (json.JSONDecodeError, ValueError):
            return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for clave in ("filas", "rows", "calendario", "items"):
            if isinstance(data.get(clave), list):
                return data[clave]
    return None


def parsear_respuesta_claude(texto: str) -> tuple[list[FilaCalendario], list[dict[str, Any]]]:
    """Texto de salida de Claude -> (filas normalizadas, errores). PURO."""
    registros = _extraer_json(texto)
    if registros is None:
        return [], [{"fila": 0, "motivo": "El asistente no devolvió un calendario en JSON legible."}]
    return _filas_desde_registros(registros)


# La plantilla vive en la Biblioteca de Texto como prompt EDITABLE (pestaña «Prompts»). Se
# insertan la RUTA del archivo y las listas (catálogo) de MARCAS y REDES en sus marcadores.
# `_SCAFFOLD` es la red por si fallara la lectura.
_PROMPT_ID = "prompt/importacion/calendario"
_SCAFFOLD = (
    "Eres un extractor de calendarios de contenido para redes sociales. Lee el archivo "
    "en la ruta {{RUTA}} (puede ser Excel, CSV, PDF, Word, una imagen/captura o texto) y "
    'devuelve EXCLUSIVAMENTE un objeto JSON con la forma {"filas": [ ... ]}, sin ningún '
    "texto adicional ni explicación. Cada elemento de `filas` es un objeto con estas claves:\n"
    '- "titulo": el tema o post (OBLIGATORIO).\n'
    '- "fecha": fecha de publicación en ISO YYYY-MM-DD, o "" si no la hay.\n'
    '- "marca": una de estas marcas por su nombre exacto, o "": {{MARCAS}}.\n'
    '- "redes": lista de redes (subconjunto de): {{REDES}}.\n'
    '- "prioridad": "alta", "media" o "baja".\n'
    '- "compromiso": true si la fila está marcada como obligatoria/comprometida.\n'
    '- "evergreen": true si está marcada como evergreen/verde.\n'
    '- "notas": cualquier detalle adicional, o "".\n'
    "Si el archivo no contiene un calendario, devuelve {\"filas\": []}."
)


def _plantilla() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > semilla); `_SCAFFOLD` si falla."""
    try:
        from . import libtexto

        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar la extracción sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or _SCAFFOLD


def _prompt_extraccion(ruta: str) -> str:
    """Prompt para que Claude LEA el archivo y devuelva el calendario en JSON (plantilla editable).

    Inserta la RUTA y el catálogo vigente de MARCAS/REDES en sus marcadores; si el equipo quitó
    el marcador de la ruta, la adjunta al final para no perderla.
    """
    lista_marcas = ", ".join(etiqueta for _id, etiqueta in marcas.opciones()) or "(ninguna)"
    lista_redes = ", ".join(redes.nombre_por_id(r) for r in redes.ids()) or "(ninguna)"
    plantilla = _plantilla().replace("{{MARCAS}}", lista_marcas).replace("{{REDES}}", lista_redes)
    if "{{RUTA}}" in plantilla:
        return plantilla.replace("{{RUTA}}", ruta)
    return f"{plantilla}\n\nArchivo a leer: {ruta}"


def _ejecutar_claude_json(prompt: str, dir_permitido: str) -> str:
    """Corre `claude -p <prompt> --output-format json --add-dir <dir>` y devuelve el texto final.

    Síncrono y acotado por `_CLAUDE_TIMEOUT_S`. Hereda el entorno (incluido el
    `CLAUDE_CODE_OAUTH_TOKEN` de la máquina). No tocar en tests: se inyecta un falso.
    """
    from .dominio import stream  # import perezoso: evita ciclo importador<->dominio

    if shutil.which("claude") is None:
        raise RuntimeError("El asistente (claude) no está disponible en el servidor.")
    argv = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--add-dir",
        dir_permitido,
        *stream.arg_skip_permisos(),
    ]
    res = subprocess.run(  # noqa: S603 -- argv fijo, sin shell; prompt va como argumento
        argv,
        capture_output=True,
        text=True,
        timeout=_CLAUDE_TIMEOUT_S,
        check=False,
        env=dict(os.environ),
    )
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "claude terminó con error").strip()[:300])
    try:
        envelope = json.loads(res.stdout or "{}")
    except (json.JSONDecodeError, ValueError):
        return res.stdout or ""
    if isinstance(envelope, dict):
        return str(envelope.get("result") or "")
    return res.stdout or ""


def extraer_con_claude(
    data: bytes, *, nombre: str, ejecutor: Ejecutor | None = None
) -> tuple[list[FilaCalendario], list[dict[str, Any]]]:
    """Bytes de CUALQUIER archivo -> (filas, errores) usando Claude. No escribe en el tablero.

    Vuelca el archivo a un temporal, deja que Claude lo lea y normaliza su JSON con las
    mismas reglas que el parser rígido. `ejecutor` es inyectable (tests).
    """
    correr = ejecutor or _ejecutar_claude_json
    salida = ""
    with tempfile.TemporaryDirectory(prefix="keni-import-") as carpeta:
        nombre_seguro = os.path.basename(nombre or "") or "archivo"
        ruta = os.path.join(carpeta, nombre_seguro)
        with open(ruta, "wb") as fh:
            fh.write(data)
        try:
            salida = correr(_prompt_extraccion(ruta), carpeta)
        except Exception as e:  # noqa: BLE001 -- cualquier fallo del asistente => error legible
            _log.warning("extraer_con_claude falló: %s", e)
            return [], [{"fila": 0, "motivo": f"No se pudo interpretar el archivo con IA: {e}"}]
    return parsear_respuesta_claude(salida)


# --------------------------------------------------------------------------- #
# Post-procesado para el WORKER (#desacoplo del back)                          #
# --------------------------------------------------------------------------- #
#
# El back NO ejecuta `claude -p` (no tiene binario ni token; solo el worker/daemons). El camino
# tabular (.xlsx/.csv) sigue siendo SINCRONO en el back (`parsear`, sin claude). Solo el camino
# AGNOSTICO (PDF/Word/imagen/captura), que antes corria `extraer_con_claude` en la peticion, se
# ENCOLA como un job de generacion (Haiku); el WORKER corre claude y luego este
# `procesar(salida, metricas)` parsea su salida (`parsear_respuesta_claude`) e IMPORTA al
# tablero (`importar_a_tablero`). Es la factory que `jobspec.reconstruir_procesar` arma a partir
# del spec `PROC_IMPORT_CALENDARIO` (mismo patron que `insumos_parse.construir_procesar_insumos`).


def construir_procesar_import(
    *, marca_defecto: str = "", autor: dict[str, str] | None = None
):  # noqa: ANN201 -- generaciones.Procesar (evita ciclo de tipos)
    """Devuelve el callback `procesar(salida, metricas) -> dict` de la importacion IA (worker).

    Parsea la salida de Haiku (`parsear_respuesta_claude`) e IMPORTA al tablero
    (`importar_a_tablero`) con las MISMAS reglas que el camino tabular. Devuelve un resumen
    `{creados, omitidos, errores}` (los items quedan como borradores en el tablero, que es la
    superficie de revision). Reusa la logica pura, solo cambia el lugar de EJECUCION.
    """

    def procesar(salida: str, _metricas: object) -> dict[str, Any]:
        filas, errores = parsear_respuesta_claude(salida or "")
        resumen = importar_a_tablero(filas, autor=autor, marca_defecto=marca_defecto or "")
        return {
            "creados": len(resumen["creados"]),
            "omitidos": resumen["omitidos"],
            "errores": errores,
        }

    return procesar


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


def _id_etiqueta(nombre: str) -> str:
    """Id de la etiqueta `nombre` (la crea si no existe). Best-effort idempotente."""
    for et in repos.listar_etiquetas():
        if _normaliza(et.get("nombre", "")) == nombre:
            return et.get("id", "")
    return repos.crear_etiqueta(nombre=nombre).get("id", "")


def _id_etiqueta_compromiso() -> str:
    """Id de la etiqueta 'compromiso' (la crea si no existe). Best-effort idempotente."""
    return _id_etiqueta(ETIQUETA_COMPROMISO)


def _id_etiqueta_evergreen() -> str:
    """Id de la etiqueta 'evergreen' (la crea si no existe). Best-effort idempotente."""
    return _id_etiqueta(ETIQUETA_EVERGREEN)


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
    etiqueta_evergreen_id = ""
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
        if fila.evergreen:
            if not etiqueta_evergreen_id:
                etiqueta_evergreen_id = _id_etiqueta_evergreen()
            if etiqueta_evergreen_id:
                repos.asignar_etiqueta(item["id"], etiqueta_evergreen_id)
        creados.append(item)

    if creados:
        _log.info("Import calendario: %d contenido(s) creado(s), %d omitido(s).", len(creados), len(omitidos))
    return {"creados": creados, "omitidos": omitidos}

"""Almacen EDITABLE de ajustes de funcionalidad de la Consola Keni (flags + tuning).

Permite a un admin cambiar EN CALIENTE, desde la UI, los flags de automatizacion y los
parametros de afinado que hoy solo se fijaban por variable de entorno (catalogo en
`ajustes_catalogo.py`). El store persiste pares `clave -> valor` (ambos `str`, igual que
una env var) en un TOML, y `config._crudo` lo consulta ANTES que `os.environ`, dando la
precedencia STORE > ENV > DEFECTO. Solo se escriben claves del catalogo; el resto del
codigo sigue cayendo a env como hasta hoy.

El archivo vive en `KENI_CONSOLA_AJUSTES` (override de maxima prioridad; tests y deploy)
o, si no, cuelga de la raiz de estado unica (`rutas.dir_config()/ajustes.toml`). Escritura
ATOMICA (temp + os.replace), mismo patron defensivo que `preferencias.py`/`secretos.py`.
NO contiene secretos.

CICLO DE IMPORT: este modulo NO importa `config` a nivel de modulo (config importa este
modulo de forma PEREZOSA dentro de `_crudo`). Usa `rutas` directamente para resolver la
ruta y lee `KENI_CONSOLA_AJUSTES` de `os.environ` aqui mismo.

CACHE: el store se consulta MUY seguido (cada `config._crudo`, que a su vez lo llaman los
accesores en caliente). Cacheamos la lectura y la invalidamos por mtime del fichero (un
escritor distinto —otro proceso/daemon que comparte el volumen— se nota por mtime).
"""

from __future__ import annotations

import os
import threading
import tomllib
from pathlib import Path

from . import rutas
from .io_atomico import escribir_atomico

# Nombre de la env var que sobreescribe la ruta del store (override de maxima prioridad;
# tests y deploy multi-proceso). Se declara TAMBIEN en `config.ENV_AJUSTES` (fuente unica
# de los nombres `KENI_*`); aqui no importamos `config` para evitar el ciclo de import.
ENV_AJUSTES = "KENI_CONSOLA_AJUSTES"

_CABECERA = (
    "# Ajustes EDITABLES de la Consola Keni (flags + tuning). Los gestiona\n"
    "# keni_consola.ajustes via la API admin (no editar a mano).\n"
)

# Cache de la ultima lectura, invalidada por (ruta, mtime). `_CACHE_MTIME = -1` => sin cache.
# `_CACHE_LOCK` (reentrante) protege el estado de modulo del check-then-act de `leer()` y la
# invalidacion de `_escribir()`: la cache la leen/escriben varios hilos (cada `config._crudo`).
_CACHE_LOCK = threading.RLock()
_CACHE_DATOS: dict[str, str] = {}
_CACHE_RUTA: str | None = None
_CACHE_MTIME: float = -1.0


def ruta_ajustes() -> Path:
    """Ruta del archivo de ajustes.

    `KENI_CONSOLA_AJUSTES` la sobreescribe (override de maxima prioridad; tests y deploy
    multi-proceso). Si no, cuelga de la raiz de estado unica (`rutas.dir_config()`): local
    `${XDG_CONFIG_HOME:-~/.config}/keni-social/ajustes.toml`, o bajo `KENI_DATA_DIR`.
    """
    crudo = os.environ.get(ENV_AJUSTES)
    if crudo:
        return Path(crudo).expanduser()
    return rutas.dir_config() / "ajustes.toml"


# --------------------------------------------------------------------------- #
# Lectura / escritura del almacen                                             #
# --------------------------------------------------------------------------- #


def _leer_disco(ruta: Path) -> dict[str, str]:
    """Lee el TOML de ajustes de disco (o {} si no existe / esta corrupto). Solo lectura.

    Normaliza a `dict[str, str]`: solo claves de nivel raiz cuyo valor sea texto (lo que
    escribimos). Cualquier otra forma se ignora (lectura tolerante).
    """
    try:
        crudo = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {k: v for k, v in crudo.items() if isinstance(v, str)}


def leer() -> dict[str, str]:
    """Pares `clave -> valor` (ambos str) del store, con cache invalidada por mtime.

    Devuelve una COPIA (mutarla no toca la cache). {} si el fichero no existe o esta
    corrupto. Se consulta muy seguido (lo llama `config._crudo`): por eso cacheamos y solo
    releemos el disco cuando cambia el mtime (o la ruta, p.ej. al cambiar la env en tests).
    """
    global _CACHE_DATOS, _CACHE_RUTA, _CACHE_MTIME
    ruta = ruta_ajustes()
    ruta_str = str(ruta)
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        mtime = None
    # check-then-act sobre el estado de modulo: atomico bajo lock (varios hilos lo tocan).
    with _CACHE_LOCK:
        if mtime is None:
            # No existe: cachea vacio (mtime -1) para no golpear el disco en cada llamada.
            if _CACHE_RUTA != ruta_str or _CACHE_MTIME != -1.0:
                _CACHE_DATOS = {}
                _CACHE_RUTA = ruta_str
                _CACHE_MTIME = -1.0
            return dict(_CACHE_DATOS)
        if _CACHE_RUTA != ruta_str or _CACHE_MTIME != mtime:
            _CACHE_DATOS = _leer_disco(ruta)
            _CACHE_RUTA = ruta_str
            _CACHE_MTIME = mtime
        return dict(_CACHE_DATOS)


def _toml_str(valor: str) -> str:
    """Escapa una cadena para un TOML basic string (comillas dobles)."""
    escapado = (
        valor.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escapado}"'


def _escribir(datos: dict[str, str]) -> None:
    """Escribe los ajustes como TOML de forma atomica (temp + os.replace) e invalida cache."""
    global _CACHE_MTIME
    # La clave TAMBIEN va entrecomillada: las claves por-marca (`KENI_PIPELINE_COPY::unotv`)
    # llevan `::`, invalido en una clave TOML desnuda -> el fichero entero se vuelve
    # imparseable y `_leer_disco` devolveria {} (perdiendo TODAS las claves en el siguiente
    # guardado). Una basic-string key es valida y los nombres simples siguen parseando igual.
    lineas = [f"{_toml_str(clave)} = {_toml_str(valor)}" for clave, valor in sorted(datos.items())]
    contenido = _CABECERA + ("\n".join(lineas) + "\n" if lineas else "")
    escribir_atomico(
        ruta_ajustes(), contenido, prefijo=".ajustes-", sufijo=".toml.tmp"
    )
    # Fuerza relectura en la proxima `leer()` (el mtime nuevo no siempre difiere al instante).
    with _CACHE_LOCK:
        _CACHE_MTIME = -1.0


# --------------------------------------------------------------------------- #
# API publica: pares clave -> valor                                           #
# --------------------------------------------------------------------------- #


def obtener(clave: str) -> str | None:
    """Valor (str) guardado para `clave`, o None si no esta en el store.

    Lo consume `config._crudo` para dar precedencia al store sobre `os.environ`.
    """
    return leer().get(clave)


def guardar(clave: str, valor: str) -> None:
    """Guarda `clave -> valor` (ambos str) en el store (escritura atomica).

    Sobrescribe el valor previo si lo hubiera. NO valida: la validacion (tipo/min/max/
    catalogo) la hace `ajustes_catalogo.validar_valor` antes, en la API.
    """
    datos = leer()
    datos[clave] = valor
    _escribir(datos)


def borrar(clave: str) -> None:
    """Borra `clave` del store (vuelve a env/defecto). No-op si no estaba."""
    datos = leer()
    if clave in datos:
        datos.pop(clave, None)
        _escribir(datos)


# --------------------------------------------------------------------------- #
# Migracion de claves RENOMBRADAS (renames de env sin retrocompat en caliente) #
# --------------------------------------------------------------------------- #
#
# Los renames "limpios" de las etapas del pipeline (consolidacion etapa = variable = toggle)
# dejaron SUELTAS las claves ya guardadas en el store: el toggle que el equipo encendio con
# el nombre viejo (p. ej. `KENI_QA::unotv = 1`) dejaba de leerse y la etapa aparecia APAGADA
# aunque la UI la hubiera mostrado encendida. Esta tabla viejo -> nuevo permite migrar el store
# al arranque. Cubre tambien las variantes por marca (`VIEJO::marca` -> `NUEVO::marca`).
#
# ORDEN: ante una CADENA de renames hacia el mismo destino (perfil/ranking previos ->
# KENI_PRIORIZAR_PERFIL_IA), va PRIMERO el alias mas RECIENTE (gana la intencion mas nueva;
# el alias mas viejo solo aplica si el destino sigue ausente tras migrar el reciente).
CLAVES_LEGADO: tuple[tuple[str, str], ...] = (
    # Verbos C (lo MAS reciente: etapa = verbo de accion). El store del piloto guardo las
    # claves bajo el nombre PREVIO de cada gate; estas las migran al verbo. Van primero.
    ("KENI_RANKING_PERFIL_IA", "KENI_PRIORIZAR_PERFIL_IA"),
    ("KENI_PIPELINE_FUSION", "KENI_PIPELINE_FUSIONAR"),
    ("KENI_PIPELINE_SELECCION", "KENI_PIPELINE_RECOLECTAR"),
    ("KENI_PIPELINE_VALIDACION", "KENI_PIPELINE_VERIFICAR"),
    ("KENI_PIPELINE_COPY", "KENI_PIPELINE_REDACTAR"),
    ("KENI_PIPELINE_ARTE", "KENI_PIPELINE_ILUSTRAR"),
    ("KENI_PIPELINE_CALIDAD", "KENI_PIPELINE_REVISAR"),
    # Renames anteriores: el RHS apunta YA al destino FINAL (el verbo), sin encadenar.
    ("KENI_PIPELINE_EDITORIAL", "KENI_PRIORIZAR_PERFIL_IA"),
    ("KENI_PIPELINE_RANKING", "KENI_PRIORIZAR_PERFIL_IA"),
    ("KENI_PERFIL_EDITORIAL", "KENI_PRIORIZAR_PERFIL_IA"),
    ("KENI_FUSION_SEMANTICA", "KENI_PIPELINE_FUSIONAR"),
    ("KENI_INGESTA", "KENI_PIPELINE_RECOLECTAR"),
    ("KENI_QA", "KENI_PIPELINE_VERIFICAR"),
    ("KENI_PIPELINE", "KENI_PIPELINE_REDACTAR"),
    ("KENI_AUTOGEN_ARTE", "KENI_PIPELINE_ILUSTRAR"),
)

# Separador de las claves por-marca (`KENI_PIPELINE_COPY::unotv`). Literal a proposito: es el
# mismo `config.SEP_MARCA`, pero este modulo no puede importar `config` (ciclo de import).
_SEP_MARCA = "::"


def migrar_claves_legado() -> int:
    """Migra al nombre NUEVO las claves del store guardadas bajo un nombre RENOMBRADO.

    Para cada par (viejo, nuevo) de `CLAVES_LEGADO`, mueve la clave global `VIEJO` y cada
    variante por marca `VIEJO::marca`:
      - si el destino NO existe en el store, copia el valor (se conserva la intencion del
        equipo: lo que estaba encendido sigue encendido bajo el nombre nuevo);
      - si el destino YA existe, NO lo pisa (lo escrito con el nombre nuevo es mas reciente);
      - en ambos casos BORRA la clave legada (el store queda sin claves sueltas que confundan).

    OJO con los prefijos: `KENI_PIPELINE` es prefijo de los nombres nuevos, por eso el match
    es EXACTO o `VIEJO + "::"` (nunca un startswith del nombre desnudo). Idempotente (la
    segunda pasada no encuentra claves legadas). Devuelve cuantas claves MOVIO (no cuenta
    las legadas descartadas por destino ya escrito).
    """
    datos = leer()
    if not datos:
        return 0
    movidas = 0
    cambiado = False
    for viejo, nuevo in CLAVES_LEGADO:
        for clave in list(datos):
            if clave != viejo and not clave.startswith(viejo + _SEP_MARCA):
                continue
            valor = datos.pop(clave)
            cambiado = True
            destino = nuevo + clave[len(viejo):]
            if destino not in datos:
                datos[destino] = valor
                movidas += 1
    if cambiado:
        _escribir(datos)
    return movidas


# --------------------------------------------------------------------------- #
# Purga de claves OBSOLETAS (eliminadas, no renombradas)                       #
# --------------------------------------------------------------------------- #
#
# A diferencia de CLAVES_LEGADO (rename viejo->nuevo, que MIGRA el valor), estas claves se
# ELIMINARON: su accesor ya no existe, así que el valor guardado no lo lee nadie. Quedan como
# dato huérfano en el store (visibles/editables en la UI de ajustes sin efecto). Se purgan al
# arrancar para no confundir. Cubre también las variantes por marca (`CLAVE::marca`).
CLAVES_OBSOLETAS: tuple[str, ...] = (
    # Tope GLOBAL único de tokens/día: sustituido por los topes POR MOTOR (investigación/
    # producción, IN/OUT, ADR 0011) + el cap de USD. Su accesor se eliminó; el valor guardado
    # (p. ej. `KENI_PRESUPUESTO_TOKENS_DIA=1500000`) no corta nada.
    "KENI_PRESUPUESTO_TOKENS_DIA",
)


def purgar_claves_obsoletas() -> int:
    """Borra del store las claves de `CLAVES_OBSOLETAS` (y sus variantes `::marca`).

    Idempotente (la segunda pasada no encuentra nada). Devuelve cuántas borró. La llama el
    arranque junto a `migrar_claves_legado`, sobre el mismo volumen compartido.
    """
    datos = leer()
    if not datos:
        return 0
    borradas = 0
    for obsoleta in CLAVES_OBSOLETAS:
        for clave in list(datos):
            if clave == obsoleta or clave.startswith(obsoleta + _SEP_MARCA):
                datos.pop(clave, None)
                borradas += 1
    if borradas:
        _escribir(datos)
    return borradas

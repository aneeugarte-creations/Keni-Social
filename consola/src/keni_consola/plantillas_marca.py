"""Store EDITABLE de la "Plantilla de marca" del Estudio (override por marca, file-as-truth).

El compositor determinista (`motores/estudio_imagen/render_node`) estampa logo + pleca +
titular por marca leyendo un catalogo (`marcas.json`). Hoy ese catalogo es estatico y solo
trae `unotv`/`claro-sports`, con `logo:""` (sin assets) -> cae a un wordmark de texto. Este
modulo permite que el EQUIPO edite la plantilla por marca desde la app (colores, pleca por
defecto, flags de titular, posicion del logo, wordmark) y suba el logo/simbolo REAL.

Patron `secretos.py`: la verdad vive en FICHERO (un JSON por marca), no en BD. Cada marca
guarda SOLO un OVERRIDE de los campos editables; al leer, los defaults de la marca (de
`marcas.json` para las visuales, o genericos para el resto) se fusionan con ese override.

Layout: `<raiz>/plantillas_marca/<marca>.json`, donde `<raiz>` es `KENI_PLANTILLAS_MARCA_DIR`
(override de maxima prioridad; util en tests) o `rutas.dir_config()`. Escritura ATOMICA
(`io_atomico.escribir_atomico`), igual que el resto del estado de la consola.

Campos EDITABLES (subconjunto del schema de marca de `marcas.json`):
  - `rojo`, `tinta`, `blanco`   color hex `#RRGGBB`.
  - `etiqueta_default`          texto de la pleca por defecto (str).
  - `titular_mayusculas`        fuerza el titular a MAYUSCULAS (bool).
  - `titular_condensada`        usa fuente condensada para el titular (bool).
  - `logo`                      id del objeto de media subido (o "" para wordmark).
  - `logo_posicion`             esquina del logo (uno de `_POSICIONES`).
  - `wordmark`                  texto de respaldo cuando no hay logo (str).

Los campos NO editables del schema (`nombre`, `id_metricas`, `marca_agua`,
`overlay_breaking`, `verificar`) NO se persisten aqui: los aporta el dominio al construir el
cfg completo para el motor.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from . import marcas, rutas
from .io_atomico import escribir_atomico
from .motores.estudio_imagen import spec_plantilla

# Clave (en el JSON por marca) del SPEC de capas del editor visual. Convive con los campos
# planos (legacy/seed): el render usa el spec; los planos inicializan el spec por defecto.
SPEC_KEY = "spec"

# Variable de entorno que sobreescribe la raiz del store (override de maxima prioridad; tests).
ENV_PLANTILLAS_MARCA_DIR = "KENI_PLANTILLAS_MARCA_DIR"

# Sub-carpeta bajo la raiz de config donde cuelga un JSON por marca.
_SUBDIR = "plantillas_marca"

# Campos editables que se persisten (y se devuelven). Orden estable para serializar.
CAMPOS = (
    "rojo",
    "tinta",
    "blanco",
    "etiqueta_default",
    "titular_mayusculas",
    "titular_condensada",
    "logo",
    "logo_posicion",
    "wordmark",
)

# Posiciones validas del logo (las 4 esquinas, respetando zonas seguras + margen).
POSICIONES = (
    "superior-izquierda",
    "superior-derecha",
    "inferior-izquierda",
    "inferior-derecha",
)

# Validacion de color hex `#RRGGBB` (6 digitos, con almohadilla).
_RE_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Defaults genericos para las marcas SIN sistema de diseno propio en `marcas.json`.
_ROJO_GENERICO = "#E30613"
_TINTA_GENERICA = "#111315"
_BLANCO_GENERICO = "#FFFFFF"


class PlantillaMarcaError(ValueError):
    """Error de validacion de una plantilla de marca, con mensaje en espanol para la UI."""


# --------------------------------------------------------------------------- #
# Rutas del store                                                             #
# --------------------------------------------------------------------------- #


def _raiz() -> Path:
    """Raiz del store: `KENI_PLANTILLAS_MARCA_DIR` o `rutas.dir_config()/plantillas_marca`."""
    if (env := os.environ.get(ENV_PLANTILLAS_MARCA_DIR)):
        return Path(env).expanduser()
    return rutas.dir_config() / _SUBDIR


def _ruta_marca(marca: str) -> Path:
    """Ruta del JSON de override de una marca (el nombre es el id canonico, ya validado)."""
    return _raiz() / f"{marca}.json"


# --------------------------------------------------------------------------- #
# Defaults por marca                                                          #
# --------------------------------------------------------------------------- #


def _marcas_json() -> dict[str, Any]:
    """Lee `motores/estudio_imagen/marcas.json` (catalogo estatico) -> {} si falla."""
    ruta = (
        Path(__file__).resolve().parent
        / "motores" / "estudio_imagen" / "marcas.json"
    )
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _solo_editables(cfg: dict[str, Any]) -> dict[str, Any]:
    """Proyecta un cfg de marca (schema de marcas.json) a SOLO los campos editables."""
    return {
        "rojo": str(cfg.get("rojo", _ROJO_GENERICO)),
        "tinta": str(cfg.get("tinta", _TINTA_GENERICA)),
        "blanco": str(cfg.get("blanco", _BLANCO_GENERICO)),
        "etiqueta_default": str(cfg.get("etiqueta_default", "")),
        "titular_mayusculas": bool(cfg.get("titular_mayusculas", False)),
        "titular_condensada": bool(cfg.get("titular_condensada", False)),
        "logo": str(cfg.get("logo", "")),
        "logo_posicion": str(cfg.get("logo_posicion", POSICIONES[0])),
        "wordmark": str(cfg.get("wordmark", "")),
    }


def DEFECTOS(marca: str) -> dict[str, Any]:  # noqa: N802 -- nombre publico pedido por el contrato
    """Plantilla por DEFECTO de una marca (sin override): defaults editables.

    Para `unotv`/`claro-sports`/`fundacion` toma los valores del catalogo estatico
    `motores/estudio_imagen/marcas.json`. Para las demas marcas del catalogo
    (`nacion-gamer`, `piso-15`) usa genericos, con `wordmark` = etiqueta humana.
    """
    visuales = _marcas_json().get("marcas", {})
    if marca in visuales:
        return _solo_editables(visuales[marca])
    return {
        "rojo": _ROJO_GENERICO,
        "tinta": _TINTA_GENERICA,
        "blanco": _BLANCO_GENERICO,
        "etiqueta_default": "",
        "titular_mayusculas": False,
        "titular_condensada": False,
        "logo": "",
        "logo_posicion": POSICIONES[0],
        "wordmark": marcas.etiqueta_de(marca),
    }


# --------------------------------------------------------------------------- #
# Lectura / escritura del override                                            #
# --------------------------------------------------------------------------- #


def _leer_override(marca: str) -> dict[str, Any]:
    """Lee el JSON de override de una marca (o {} si no existe / esta corrupto)."""
    ruta = _ruta_marca(marca)
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def obtener(marca: str) -> dict[str, Any]:
    """Plantilla EFECTIVA de una marca: defaults ⊕ override guardado (el override gana).

    Solo devuelve los campos editables (`CAMPOS`). Si la marca no se conoce, lanza
    `PlantillaMarcaError` (la API la traduce a 4xx en espanol).
    """
    if not marcas.es_marca(marca):
        raise PlantillaMarcaError(f"Marca desconocida: {marca}.")
    base = DEFECTOS(marca)
    for clave, valor in _leer_override(marca).items():
        if clave in base:
            base[clave] = valor
    return base


def listar() -> dict[str, dict[str, Any]]:
    """Plantilla efectiva de TODAS las marcas del catalogo (`marcas.opciones()`)."""
    return {mid: obtener(mid) for mid in marcas.ids()}


# --------------------------------------------------------------------------- #
# Validacion + guardado                                                       #
# --------------------------------------------------------------------------- #


def _validar(datos: dict[str, Any]) -> dict[str, Any]:
    """Valida y normaliza los campos editables presentes en `datos` -> dict limpio.

    Solo se consideran las claves de `CAMPOS`; las demas se ignoran. Lanza
    `PlantillaMarcaError` (espanol) ante un valor invalido.
    """
    if not isinstance(datos, dict):
        raise PlantillaMarcaError("La plantilla debe ser un objeto JSON.")
    limpio: dict[str, Any] = {}
    for clave in ("rojo", "tinta", "blanco"):
        if clave in datos:
            valor = datos[clave]
            if not isinstance(valor, str) or not _RE_HEX.match(valor):
                raise PlantillaMarcaError(
                    f"El color '{clave}' debe ser un hex de la forma #RRGGBB."
                )
            limpio[clave] = valor
    if "etiqueta_default" in datos:
        valor = datos["etiqueta_default"]
        if not isinstance(valor, str):
            raise PlantillaMarcaError("La etiqueta por defecto debe ser texto.")
        limpio["etiqueta_default"] = valor
    for clave in ("titular_mayusculas", "titular_condensada"):
        if clave in datos:
            valor = datos[clave]
            if not isinstance(valor, bool):
                raise PlantillaMarcaError(f"El campo '{clave}' debe ser verdadero o falso.")
            limpio[clave] = valor
    if "logo" in datos:
        valor = datos["logo"]
        if not isinstance(valor, str):
            raise PlantillaMarcaError("El logo debe ser el id de una imagen subida (o vacío).")
        limpio["logo"] = valor
    if "logo_posicion" in datos:
        valor = datos["logo_posicion"]
        if valor not in POSICIONES:
            raise PlantillaMarcaError(
                "La posición del logo debe ser una de: " + ", ".join(POSICIONES) + "."
            )
        limpio["logo_posicion"] = valor
    if "wordmark" in datos:
        valor = datos["wordmark"]
        if not isinstance(valor, str):
            raise PlantillaMarcaError("El wordmark debe ser texto.")
        limpio["wordmark"] = valor
    return limpio


def guardar(marca: str, datos: dict[str, Any]) -> dict[str, Any]:
    """Persiste el OVERRIDE de una marca (solo campos editables, escritura atomica).

    Valida la marca y cada campo; lanza `PlantillaMarcaError` (espanol) si algo no encaja.
    Devuelve la plantilla EFECTIVA resultante (defaults ⊕ override ya guardado).
    """
    if not marcas.es_marca(marca):
        raise PlantillaMarcaError(f"Marca desconocida: {marca}.")
    limpio = _validar(datos)
    previo = _leer_override(marca)
    # Fusiona con el override previo para que un PUT parcial no borre campos no enviados.
    fusionado = {**previo, **limpio}
    # Persiste los campos editables conocidos + conserva el SPEC si ya existía (no lo borra
    # un guardado de campos planos).
    a_guardar = {c: fusionado[c] for c in CAMPOS if c in fusionado}
    if SPEC_KEY in previo:
        a_guardar[SPEC_KEY] = previo[SPEC_KEY]
    _escribir_override(marca, a_guardar)
    return obtener(marca)


def _escribir_override(marca: str, datos: dict[str, Any]) -> None:
    """Escritura atómica del JSON de override de una marca."""
    escribir_atomico(
        _ruta_marca(marca),
        json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        prefijo=".plantilla-",
        sufijo=".json.tmp",
    )


def obtener_spec(marca: str) -> dict[str, Any]:
    """SPEC de capas EFECTIVO de una marca: el guardado (validado) o uno por defecto.

    Si el override trae un `spec` válido, se valida+migra y se devuelve. Si no, se DERIVA desde
    los campos planos efectivos (`obtener`) para que toda marca tenga spec sin migración previa.
    """
    if not marcas.es_marca(marca):
        raise PlantillaMarcaError(f"Marca desconocida: {marca}.")
    crudo = _leer_override(marca).get(SPEC_KEY)
    if isinstance(crudo, dict) and crudo.get("formatos"):
        try:
            return spec_plantilla.migrar(spec_plantilla.validar(crudo))
        except spec_plantilla.SpecError:
            pass  # spec corrupto -> cae al derivado (nunca deja a la marca sin plantilla)
    return spec_plantilla.spec_por_defecto(marca, obtener(marca))


def tiene_spec_guardado(marca: str) -> bool:
    """True si la marca tiene un SPEC de capas GUARDADO (diseñado en el editor visual).

    Distingue una marca CON plantilla configurada (override con `spec` válido) de una marca
    del catálogo SIN diseño propio (que solo tendría un spec DERIVADO de defaults genéricos).
    No deriva nada: solo mira el override persistido. Marca desconocida -> False.
    """
    if not marcas.es_marca(marca):
        return False
    crudo = _leer_override(marca).get(SPEC_KEY)
    return isinstance(crudo, dict) and bool(crudo.get("formatos"))


def guardar_spec(marca: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Persiste el SPEC de capas de una marca (validado), conservando los campos planos."""
    if not marcas.es_marca(marca):
        raise PlantillaMarcaError(f"Marca desconocida: {marca}.")
    try:
        limpio = spec_plantilla.validar(spec)
    except spec_plantilla.SpecError as e:
        raise PlantillaMarcaError(str(e)) from e
    previo = _leer_override(marca)
    previo[SPEC_KEY] = limpio
    a_guardar = {c: previo[c] for c in CAMPOS if c in previo}
    a_guardar[SPEC_KEY] = limpio
    _escribir_override(marca, a_guardar)
    return obtener_spec(marca)

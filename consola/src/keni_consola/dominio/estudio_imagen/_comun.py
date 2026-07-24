"""Estudio de imagen — núcleo COMÚN: imports, constantes, error de dominio y helpers de bajo nivel.

Pieza interna del paquete `dominio.estudio_imagen` (split por responsabilidad; la superficie
pública la re-exporta el barrel `__init__.py`). Aquí vive lo que comparten los submódulos de
área (motores deterministas/IA, composición Node, documento de capas, set multi-formato y
revisión): constantes de formato, `EstudioError`, materialización de media a temporales y los
lanzadores de subproceso (`_correr_motor`, `_correr_render_node`, `_correr_render_documento`).

SEGURIDAD: sin shell (argv como lista); la imagen de entrada se materializa en un temporal que
se borra al terminar; los nombres en el almacen los genera el servidor (uuid); los errores salen
como texto en espanol (los recoge `lanzar_job_imagen`).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from ... import media, plantillas_marca

_log = logging.getLogger("keni_consola.estudio_imagen")

__all__ = [
    "REGLAS_IMAGEN",
    "FORMATOS",
    "ASPECTOS",
    "OPS_EDITAR",
    "_MARCAS_VISUALES",
    "_TIMEOUT_EDITAR_S",
    "_TIMEOUT_COMPONER_S",
    "_FORMATOS_COMPONER",
    "_FORMATO_POR_RED",
    "_ENV_NODE_BIN",
    "EstudioError",
    "marca_tiene_plantilla",
    "formato_por_red",
    "_ruta_motor",
    "_materializar",
    "_correr_motor",
    "_importar_salidas",
    "_resultado",
    "_node_bin",
    "_ruta_render_node",
    "_ruta_render_documento",
    "_nombre_local_plano",
    "_materializar_logo",
    "_correr_render_node",
    "_correr_render_documento",
]

# Reglas de imagen (Texto): editorial de reglas que `dominio/generar.adjuntos_copy` adjunta al
# COPY (el modelo redacta el copy-in de la placa) y que el render de marca respeta.
REGLAS_IMAGEN = "editorial/reglas/imagen"

# Formatos de red soportados (espejo de `motores/estudio_imagen/editar.py:FORMATOS`). FUENTE de
# identidad de formato compartida con `formatos_red` (matriz red->lienzo).
FORMATOS = ("vertical", "feed", "cuadrado", "horizontal")
ASPECTOS = {"vertical": "9:16", "feed": "4:5", "cuadrado": "1:1", "horizontal": "16:9"}

# Operaciones DETERMINISTAS del motor `editar.py` (sin IA, sin coste).
OPS_EDITAR = ("recortar", "redimensionar", "comprimir", "extender", "placa")

# Marcas con tokens de diseno PRECARGADOS en `motores/estudio_imagen/marcas.json`
# (colores/pleca afinados). Es el conjunto que admite la PLACA de texto legacy (`editar.py
# placa`, Pillow). NO limita la PLANTILLA por SPEC: esa funciona para toda marca del catalogo
# (el spec se deriva de los campos planos, que existen para cualquier marca; ver
# `marca_tiene_plantilla`).
_MARCAS_VISUALES = ("unotv", "claro-sports", "fundacion")

# Wall-timeout del motor determinista `editar.py` (rapido; sin red).
_TIMEOUT_EDITAR_S = 60
# Componer es determinista (Pillow), como editar: rapido, sin red.
_TIMEOUT_COMPONER_S = 60

# Formatos que ENTIENDE el compositor (`render_node`, via SPEC de capas): TODOS los de
# FORMATOS, incluido `horizontal` (16:9, lienzo de X). El spec deriva el layout (logo +
# pleca + titular) para cada lienzo desde la geometria de `spec_plantilla.FORMATOS`, asi
# que el 16:9 sale con la marca aplicada como los demas (no se mapea a `feed`).
_FORMATOS_COMPONER = ("vertical", "feed", "cuadrado", "horizontal")


class EstudioError(RuntimeError):
    """Error de dominio del Estudio, con mensaje en espanol listo para la UI."""


def marca_tiene_plantilla(marca: str) -> bool:
    """True si la marca tiene una PLANTILLA REALMENTE configurada (logo + pleca + titular).

    Cualquier marca del catalogo PUEDE tener plantilla (el editor visual diseña y guarda su
    SPEC de capas), pero solo se auto-compone cuando hay un diseño concreto, no por el mero
    hecho de existir en el catalogo. Dos casos cuentan como "configurada":
      - tokens de diseño PRECARGADOS (`_MARCAS_VISUALES`: unotv / claro-sports / fundacion), o
      - un SPEC guardado en el editor visual (`plantillas_marca.tiene_spec_guardado`).
    Una marca del catalogo SIN ninguno de los dos (p. ej. piso-15 o nacion-gamer hasta que se
    le diseñe spec) NO compone: el integrar-foto devuelve la foto tal cual y la auto-gen omite
    la placa. Asi evitamos componer una placa generica para toda marca por defecto.
    """
    if marca in _MARCAS_VISUALES:
        return True
    return plantillas_marca.tiene_spec_guardado(marca)


# Formato de placa por red para POSTS DE FOTO. Regla de producto: toda foto que el equipo
# publica va en 4:5 (`feed`, 1080x1350) sea cual sea la red — es el encuadre canonico del post.
# Solo el video nativo vertical (tiktok) cae a `vertical` 9:16; los reels/stories/shorts no pasan
# por esta placa de foto, los genera el set multi-formato (`formatos_red.MATRIZ`). Red desconocida
# -> `feed`.
_FORMATO_POR_RED = {
    "tiktok": "vertical",
    "instagram": "feed",
    "facebook": "feed",
    "x": "feed",
    "youtube": "feed",
}


def formato_por_red(red: str) -> str:
    """Formato de placa (`vertical|feed|cuadrado`) para una red; `feed` si no se conoce."""
    return _FORMATO_POR_RED.get(red, "feed")


# --------------------------------------------------------------------------- #
# Motores relocalizados (subproceso, patron `api/verificaciones`)             #
# --------------------------------------------------------------------------- #


def _ruta_motor(nombre: str) -> Path:
    """Ruta a un motor relocalizado bajo `keni_consola/motores/estudio_imagen/`."""
    return Path(__file__).resolve().parent.parent.parent / "motores" / "estudio_imagen" / nombre


def _materializar(imagen: str, destino: Path) -> Path:
    """Vuelca el objeto de media `imagen` a un archivo en `destino` y devuelve su ruta.

    El motor lee de disco (`--foto`); con backend S3 el objeto no esta en local, asi que
    SIEMPRE materializamos desde `media.leer_media` (bytes). Conserva la extension del objeto.
    """
    datos = media.leer_media(imagen)
    if datos is None:
        raise EstudioError("Esa imagen no existe en el almacen.")
    ext = Path(imagen).suffix.lower() or ".png"
    foto = destino / f"origen{ext}"
    foto.write_bytes(datos)
    return foto


def _correr_motor(cmd: list[str], *, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Corre un motor del Estudio y devuelve el bloque `DATOS <json>` de su stdout.

    Modulo-nivel para que los tests lo monkeypatcheen y NO ejecuten Pillow/OpenRouter.
    """
    try:
        proc = subprocess.run(  # noqa: S603 -- argv lista, sin shell; rutas controladas por el server
            cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env
        )
    except subprocess.TimeoutExpired as e:
        raise EstudioError(f"La operacion tardo demasiado (mas de {timeout} s) y se cancelo.") from e

    datos: dict[str, Any] | None = None
    for linea in proc.stdout.splitlines():
        if linea.startswith("DATOS "):
            try:
                cargado = json.loads(linea[len("DATOS "):])
            except json.JSONDecodeError:
                cargado = None
            if isinstance(cargado, dict):
                datos = cargado
    if datos is None:
        detalle = (proc.stderr or "").strip()[-300:]
        raise EstudioError(
            "El motor de imagen no produjo un resultado. " + (detalle or "Revisa la imagen de entrada.")
        )
    return datos


def _importar_salidas(info: dict[str, Any]) -> list[dict[str, str]]:
    """Importa al almacen de media cada `salida` del bloque DATOS -> lista `{id, url}`."""
    salidas = info.get("salidas")
    rutas = [s.get("salida") for s in salidas if isinstance(s, dict)] if isinstance(salidas, list) else []
    importadas: list[dict[str, str]] = []
    for ruta in rutas:
        if not isinstance(ruta, str) or not ruta:
            continue
        try:
            nombre = media.importar_imagen(ruta)
        except media.MediaError as e:
            raise EstudioError(str(e)) from e
        importadas.append({"id": nombre, "url": f"/api/media/{nombre}"})
    if not importadas:
        raise EstudioError("El motor de imagen no devolvio ninguna imagen utilizable.")
    return importadas


def _resultado(importadas: list[dict[str, str]], info: dict[str, Any]) -> dict[str, Any]:
    """Forma uniforme del resultado: `url`/`id` primario + `imagenes` (todas) + `info`."""
    principal = importadas[0]
    info_publica = {k: info.get(k) for k in ("op", "marca", "formato", "encaje", "modelo") if k in info}
    return {"id": principal["id"], "url": principal["url"], "imagenes": importadas, "info": info_publica}


# --------------------------------------------------------------------------- #
# Render por SPEC / documento (motor Node): binario, rutas y materializacion   #
# --------------------------------------------------------------------------- #


# Render de la plantilla: motor ÚNICO = Node (lee el SPEC de capas; lo diseñado en el editor =
# lo que sale). `KENI_NODE_BIN` apunta al binario de node (def. `node`).
_ENV_NODE_BIN = "KENI_NODE_BIN"


def _node_bin() -> str:
    return (os.environ.get(_ENV_NODE_BIN) or "node").strip() or "node"


def _ruta_render_node() -> Path:
    return _ruta_motor("render_node") / "componer.mjs"


def _ruta_render_documento() -> Path:
    return _ruta_motor("render_node") / "render_documento.mjs"


def _nombre_local_plano(clave: str) -> str:
    """Aplana una key de almacen (`<categoria>/<nombre>`) a un nombre de fichero local PLANO.

    Desde que el almacen se divide en carpetas por tipo (`logos/`, `plantillas/`, ...), la key
    de un objeto trae un `/`. Al materializarla a un temporal NO podemos pegarla cruda en el
    nombre del fichero: el `/` la convertiria en una subcarpeta que nadie crea (FileNotFoundError).
    Sustituimos el separador por `-` para conservar un nombre unico y plano dentro de la carpeta.
    """
    return clave.replace("/", "-")


def _materializar_logo(logo_id: str, carpeta: Path) -> str:
    """Vuelca un objeto de media (logo/fondo) a un PNG temporal; '' si no hay o no existe.

    Una key que ya no está en el almacén se avisa por log: el renderer descarta esa capa sin
    error y la pieza saldría (y se publicaría) sin su logo, que de otro modo pasa inadvertido.
    """
    logo_id = (logo_id or "").strip()
    if not logo_id:
        return ""
    datos = media.leer_media(logo_id)
    if datos is None:
        _log.warning(
            "Render: la capa referencia %r y ese objeto no está en el almacén; "
            "se compone SIN esa capa.",
            logo_id,
        )
        return ""
    ruta = carpeta / f"asset-{_nombre_local_plano(logo_id)}.png"
    ruta.write_bytes(datos)
    return str(ruta)


def _correr_render_node(payload: dict[str, Any], out: Path) -> None:
    """Corre el renderer Node con `payload` por stdin y `--salida out`. Lanza EstudioError si falla.

    Módulo-nivel para que los tests lo monkeypatcheen sin ejecutar Node real.
    """
    cmd = [_node_bin(), str(_ruta_render_node()), "--salida", str(out)]
    try:
        proc = subprocess.run(  # noqa: S603 -- argv lista, sin shell; payload por stdin
            cmd, input=json.dumps(payload), capture_output=True, text=True,
            timeout=_TIMEOUT_COMPONER_S, check=False,
        )
    except FileNotFoundError as e:  # node no instalado
        raise EstudioError("El renderer de plantilla (Node) no está disponible.") from e
    except subprocess.TimeoutExpired as e:
        raise EstudioError(
            f"La composición tardó demasiado (más de {_TIMEOUT_COMPONER_S} s) y se canceló."
        ) from e
    if proc.returncode != 0 or not out.is_file():
        detalle = (proc.stderr or "").strip()[-300:]
        raise EstudioError("El renderer de plantilla no produjo un resultado. " + detalle)


def _correr_render_documento(payload: dict[str, Any], out: Path) -> None:
    """Corre `render_documento.mjs` con `payload` por stdin y `--salida out`.

    Módulo-nivel para que los tests lo monkeypatcheen sin ejecutar Node real. Espeja
    `_correr_render_node` (mismo timeout y manejo de errores en español).
    """
    cmd = [_node_bin(), str(_ruta_render_documento()), "--salida", str(out)]
    try:
        proc = subprocess.run(  # noqa: S603 -- argv lista, sin shell; payload por stdin
            cmd, input=json.dumps(payload), capture_output=True, text=True,
            timeout=_TIMEOUT_COMPONER_S, check=False,
        )
    except FileNotFoundError as e:  # node no instalado
        raise EstudioError("El renderer del editor (Node) no está disponible.") from e
    except subprocess.TimeoutExpired as e:
        raise EstudioError(
            f"El render del documento tardó demasiado (más de {_TIMEOUT_COMPONER_S} s) y se canceló."
        ) from e
    if proc.returncode != 0 or not out.is_file():
        detalle = (proc.stderr or "").strip()[-300:]
        raise EstudioError("El renderer del editor no produjo un resultado. " + detalle)

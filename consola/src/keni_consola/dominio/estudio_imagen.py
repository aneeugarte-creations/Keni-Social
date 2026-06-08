"""Estudio de imagen — dominio: componer prompt + correr los motores relocalizados.

Superficie de primera clase que reemplaza a la skill `estudio-imagen` (borrada con el
resto del sistema de skills). El arte PERTENECE a la pieza: una imagen es un objeto del
almacen de media (`<uuid>.png`) y se asocia a la publicacion por `publicacion.imagen`
(mismo seam A->C que ya usa la generacion de copy).

Tres capacidades, todas reutilizando la infra existente (sin red en tests):
  - GENERAR variantes (IA)   -> `media.generar_imagen` (un solo punto de red, mockeable).
  - EDITAR (determinista)    -> motor `motores/estudio_imagen/editar.py` por subproceso
                                (Pillow, sin coste: recortar/redimensionar/comprimir/
                                extender/placa). Patron identico a `api/verificaciones`.
  - EXPANDIR (outpainting IA)-> motor `motores/estudio_imagen/expandir.py` por subproceso,
                                con la clave del proveedor inyectada via `_entorno_generacion`.

SEGURIDAD: sin shell (argv como lista); la imagen de entrada se materializa en un
temporal que se borra al terminar; los nombres en el almacen los genera el servidor
(uuid); los errores salen como texto en espanol (los recoge `lanzar_job_imagen`).
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .. import (
    libtexto,
    formatos_red,
    generaciones,
    marca_assets,
    marcas,
    media,
    plantillas_marca,
    repos,
)
from ..motores.estudio_imagen import documento as doc_capas
from ..motores.estudio_imagen import spec_plantilla
from . import generar, jobspec

# Reglas de imagen (Texto) que se adjuntan a la revision legal/editorial.
REGLAS_IMAGEN = "editorial/reglas/imagen"

# Formatos de red soportados (espejo de `motores/estudio_imagen/editar.py:FORMATOS`).
FORMATOS = ("vertical", "feed", "cuadrado", "horizontal")
ASPECTOS = {"vertical": "9:16", "feed": "4:5", "cuadrado": "1:1", "horizontal": "16:9"}

# Operaciones DETERMINISTAS del motor `editar.py` (sin IA, sin coste).
OPS_EDITAR = ("recortar", "redimensionar", "comprimir", "extender", "placa")

# Prompt base de imagen en la Texto (editable por el equipo; cae a "" si falta).
PROMPT_IMAGEN_DEFECTO = "prompt/imagen/ilustracion-fondo"

# Marcas con tokens de diseno PRECARGADOS en `motores/estudio_imagen/marcas.json`
# (colores/pleca afinados). Es el conjunto que admite la PLACA de texto legacy (`editar.py
# placa`, Pillow). NO limita la PLANTILLA por SPEC: esa funciona para toda marca del catalogo
# (el spec se deriva de los campos planos, que existen para cualquier marca; ver
# `marca_tiene_plantilla`).
_MARCAS_VISUALES = ("unotv", "claro-sports", "fundacion")

# Nota de estilo por marca para el prompt generativo (referencia corta; la guia completa
# vive como documento editorial en la Texto). Replica `motores/.../generar.ESTILO_MARCA`.
_ESTILO_MARCA = {
    "unotv": "Estilo UnoTV: noticias, sobrio, creible, alto contraste, rojo #E30613 como acento puntual.",
    "claro-sports": "Estilo Claro Sports: deportivo, energia, alto contraste, rojo #CF2E2E de marca.",
    "fundacion": "Estilo Fundación: social y humano, calido y cercano, esperanzador; tono sensible y respetuoso, acento ambar #D97706.",
}

# Wall-timeouts: editar es determinista (rapido); expandir/retocar llaman al proveedor (lento).
_TIMEOUT_EDITAR_S = 60
_TIMEOUT_EXPANDIR_S = 240
_TIMEOUT_RETOCAR_S = 240
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
# -> `feed`. (Antes IG iba a `cuadrado` 1:1, lo que descuadraba el post: ya no.)
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
# Composicion del prompt generativo                                            #
# --------------------------------------------------------------------------- #


def componer_prompt(
    prompt: str, marca: str = "", formato: str = "feed", prompt_id: str = PROMPT_IMAGEN_DEFECTO
) -> str:
    """Arma el prompt de imagen: base de la Texto + lo pedido + estilo de marca + aspecto.

    El estilo de marca (hoy una constante) pasa a ser editable: si la Texto tiene el
    prompt base (`prompt/imagen/...`) gana esa version; la nota de marca es un complemento
    corto. NO volcamos la linea editorial de copy (voz) en un prompt de imagen: seria ruido.
    """
    formato = formato if formato in FORMATOS else "feed"
    base = libtexto.cuerpo_efectivo(prompt_id) or ""
    estilo = _ESTILO_MARCA.get(marca, "")
    aspecto = ASPECTOS[formato]
    partes = [
        base.strip(),
        (prompt or "").strip(),
        estilo,
        f"Formato {formato}, relacion de aspecto {aspecto}.",
    ]
    return "\n\n".join(p for p in partes if p)


def generar_variante(prompt_final: str) -> dict[str, Any]:
    """Genera UNA imagen con el proveedor y la guarda en el almacen -> `{id, url}`.

    Es el callable que corre `lanzar_job_imagen`. La red la toca SOLO `media.generar_imagen`
    (`_PROVEEDOR`, mockeable): los tests nunca salen a internet.
    """
    crudos = media.generar_imagen(prompt_final)
    nombre = media.guardar_bytes(crudos, ext="png")
    return {"id": nombre, "url": f"/api/media/{nombre}"}


# --------------------------------------------------------------------------- #
# Motores relocalizados (subproceso, patron `api/verificaciones`)             #
# --------------------------------------------------------------------------- #


def _ruta_motor(nombre: str) -> Path:
    """Ruta a un motor relocalizado bajo `keni_consola/motores/estudio_imagen/`."""
    return Path(__file__).resolve().parent.parent / "motores" / "estudio_imagen" / nombre


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


def _argv_editar(op: str, foto: Path | None, out: Path, params: dict[str, Any]) -> list[str]:
    """Construye el argv de `editar.py <op> ...` segun la operacion (valores ya validados)."""
    motor = _ruta_motor("editar.py")
    cmd = [sys.executable, str(motor), op]
    if foto is not None:
        cmd += ["--foto", str(foto)]
    cmd += ["--salida", str(out)]
    if op == "recortar":
        cmd += ["--formato", params["formato"]]
    elif op == "redimensionar":
        cmd += ["--max", str(params["max"])]
    elif op == "comprimir":
        cmd += ["--peso-max-mb", str(params["peso_max_mb"]), "--formato-archivo", params["formato_archivo"]]
    elif op == "extender":
        cmd += ["--formato", params["formato"], "--metodo", params["metodo"]]
        if params.get("forzar"):
            cmd += ["--forzar"]
    elif op == "placa":
        cmd += ["--texto", params["texto"], "--marca", params["marca"], "--formato", params["formato"]]
        if params.get("fuente_cita"):
            cmd += ["--fuente-cita", params["fuente_cita"]]
    return cmd


def editar(imagen: str, op: str, params: dict[str, Any]) -> dict[str, Any]:
    """Operacion DETERMINISTA (Pillow) sobre un objeto de media -> resultado uniforme.

    `placa` puede no llevar foto de fondo; el resto requiere `imagen`. Sin coste, sin red.
    """
    if op not in OPS_EDITAR:
        raise EstudioError(f"Operacion de edicion no soportada: {op}.")
    ext = ".jpg" if op == "comprimir" and params.get("formato_archivo") == "jpg" else ".png"
    if op == "comprimir" and params.get("formato_archivo") == "webp":
        ext = ".webp"
    with tempfile.TemporaryDirectory(prefix="keni-estudio-") as tmp:
        carpeta = Path(tmp)
        foto: Path | None = None
        if imagen:
            foto = _materializar(imagen, carpeta)
        elif op != "placa":
            raise EstudioError("Falta la imagen de entrada para esta operacion.")
        out = carpeta / f"salida{ext}"
        cmd = _argv_editar(op, foto, out, params)
        info = _correr_motor(cmd, timeout=_TIMEOUT_EDITAR_S)
        return _resultado(_importar_salidas(info), info)


def expandir(
    imagen: str, *, formato: str = "feed", marca: str = "", strength: float | None = None, lado: str = "auto"
) -> dict[str, Any]:
    """Outpainting GENERATIVO fiel (el sujeto no se toca) a un formato -> resultado uniforme.

    Requiere proveedor configurado: la clave viaja al subproceso via `_entorno_generacion`.
    """
    if not imagen:
        raise EstudioError("Falta la imagen de entrada para expandir.")
    formato = formato if formato in FORMATOS else "feed"
    with tempfile.TemporaryDirectory(prefix="keni-estudio-") as tmp:
        carpeta = Path(tmp)
        foto = _materializar(imagen, carpeta)
        out = carpeta / "salida.png"
        motor = _ruta_motor("expandir.py")
        cmd = [sys.executable, str(motor), "--foto", str(foto), "--formato", formato, "--salida", str(out)]
        if marca:
            cmd += ["--marca", marca]
        if strength is not None:
            cmd += ["--strength", str(strength)]
        if lado and lado != "auto":
            cmd += ["--lado", lado]
        info = _correr_motor(cmd, timeout=_TIMEOUT_EXPANDIR_S, env=generaciones._entorno_generacion())
        return _resultado(_importar_salidas(info), info)


def retocar(imagen: str, instruccion: str, *, strength: float | None = None) -> dict[str, Any]:
    """Retoque GENERATIVO por INSTRUCCION ("oscurece el cielo") -> resultado uniforme.

    A diferencia de `expandir` (outpainting fiel: solo rellena una banda), `retocar` reinterpreta
    TODA la imagen segun la instruccion. Es generativo (coste + timeout como expandir); requiere
    proveedor configurado (la clave viaja al subproceso via `_entorno_generacion`).
    """
    if not imagen:
        raise EstudioError("Falta la imagen de entrada para retocar.")
    if not (instruccion or "").strip():
        raise EstudioError("Escribe qué retoque quieres aplicar.")
    with tempfile.TemporaryDirectory(prefix="keni-estudio-") as tmp:
        carpeta = Path(tmp)
        foto = _materializar(imagen, carpeta)
        out = carpeta / "salida.png"
        motor = _ruta_motor("retocar.py")
        cmd = [
            sys.executable, str(motor), "--foto", str(foto),
            "--instruccion", instruccion.strip(), "--salida", str(out),
        ]
        if strength is not None:
            cmd += ["--strength", str(strength)]
        info = _correr_motor(cmd, timeout=_TIMEOUT_RETOCAR_S, env=generaciones._entorno_generacion())
        return _resultado(_importar_salidas(info), info)


# --------------------------------------------------------------------------- #
# Composicion de marca DETERMINISTA (plantilla: logo + pleca + titular)        #
# --------------------------------------------------------------------------- #


# Render de la plantilla: motor ÚNICO = Node (lee el SPEC de capas; lo diseñado en el editor =
# lo que sale). `KENI_NODE_BIN` apunta al binario de node (def. `node`).
_ENV_NODE_BIN = "KENI_NODE_BIN"


def _node_bin() -> str:
    return (os.environ.get(_ENV_NODE_BIN) or "node").strip() or "node"


def _ruta_render_node() -> Path:
    return _ruta_motor("render_node") / "componer.mjs"


def _nombre_local_plano(clave: str) -> str:
    """Aplana una key de almacen (`<categoria>/<nombre>`) a un nombre de fichero local PLANO.

    Desde que el almacen se divide en carpetas por tipo (`logos/`, `plantillas/`, ...), la key
    de un objeto trae un `/`. Al materializarla a un temporal NO podemos pegarla cruda en el
    nombre del fichero: el `/` la convertiria en una subcarpeta que nadie crea (FileNotFoundError).
    Sustituimos el separador por `-` para conservar un nombre unico y plano dentro de la carpeta.
    """
    return clave.replace("/", "-")


def _materializar_logo(logo_id: str, carpeta: Path) -> str:
    """Vuelca un objeto de media (logo/fondo) a un PNG temporal; '' si no hay o no existe."""
    logo_id = (logo_id or "").strip()
    if not logo_id:
        return ""
    datos = media.leer_media(logo_id)
    if datos is None:
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


def _componer_node_bytes(
    imagen: str, *, marca: str, fmt: str, titular: str, etiqueta: str | None,
    logo_path: str | None = None,
) -> tuple[bytes, bool]:
    """Render por SPEC con el motor Node y devuelve `(png_bytes, placeholder)` SIN persistir.

    Render PURO a memoria: materializa los assets en un temporal, corre Node y devuelve los
    bytes del PNG. NO escribe en el almacén de media (lo usa el render ON-DEMAND, que sirve los
    bytes por HTTP sin generar objetos). `logo_path` sustituye al logo del spec (flujo de arte).
    """
    plana = plantillas_marca.obtener(marca)
    spec = plantillas_marca.obtener_spec(marca)
    formato_spec = spec.get("formatos", {}).get(fmt)
    if not formato_spec:
        raise EstudioError(f"El spec de la marca no tiene el formato '{fmt}'.")
    placeholder = not (imagen or "").strip()
    # Pleca efectiva (contrato de `etiqueta`): None=default de marca; ""=omitir; texto=ese.
    etiqueta_efectiva = plana.get("etiqueta_default", "") if etiqueta is None else etiqueta

    with tempfile.TemporaryDirectory(prefix="keni-render-") as tmp:
        carpeta = Path(tmp)
        foto = None if placeholder else str(_materializar(imagen, carpeta))
        logo_cfg = formato_spec.get("logo") or {}
        ruta_logo = logo_path or _materializar_logo(logo_cfg.get("media_id", ""), carpeta)
        fondo_cfg = formato_spec.get("fondo") or {}
        ruta_fondo = ""
        if fondo_cfg.get("tipo") == "imagen":
            ruta_fondo = _materializar_logo((fondo_cfg.get("imagen") or {}).get("media_id", ""), carpeta)

        out = carpeta / "salida.png"
        payload = {
            "spec": spec,
            "formato": fmt,
            "placeholder": placeholder,
            "foto": foto,
            "assets": {"logo": ruta_logo or None, "fondo": ruta_fondo or None},
            "bindings": {"copy_in": titular or "", "etiqueta_default": etiqueta_efectiva or ""},
        }
        _correr_render_node(payload, out)
        return out.read_bytes(), placeholder


def _componer_node(
    imagen: str, *, marca: str, fmt: str, titular: str, etiqueta: str | None,
    logo_path: str | None = None,
) -> dict[str, Any]:
    """Render por SPEC que PERSISTE el PNG (content-addressed) y devuelve `{id,url,imagenes,info}`.

    Lo usan los flujos que necesitan un asset DURABLE referenciado (bake del editor pro, arte
    multi-formato, materialización al PUBLICAR). El render on-demand usa `_componer_node_bytes`
    (sin persistir). `logo_path` sustituye al logo del spec.
    """
    datos, placeholder = _componer_node_bytes(
        imagen, marca=marca, fmt=fmt, titular=titular, etiqueta=etiqueta, logo_path=logo_path
    )
    try:
        nombre = media.guardar_bytes_contenido(datos, ext="png")
    except media.MediaError as e:
        raise EstudioError(str(e)) from e
    return {
        "id": nombre, "url": f"/api/media/{nombre}",
        "imagenes": [{"id": nombre, "url": f"/api/media/{nombre}"}],
        "info": {"op": "componer", "marca": marca, "formato": fmt,
                 "placeholder": placeholder, "motor": "node"},
    }


def componer_bytes(
    imagen: str, *, marca: str, formato: str = "feed", titular: str = "",
    etiqueta: str | None = None, logo_path: str | None = None,
) -> bytes:
    """Compone la placa de marca y devuelve los BYTES del PNG SIN persistir (render on-demand).

    Misma firma que `componer` pero efímero: no escribe en el almacén. Valida marca y formato.
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    if formato not in _FORMATOS_COMPONER:
        raise EstudioError(
            "Formato no soportado para componer. Usa: " + ", ".join(_FORMATOS_COMPONER) + "."
        )
    datos, _ = _componer_node_bytes(
        imagen, marca=marca, fmt=formato, titular=titular, etiqueta=etiqueta, logo_path=logo_path
    )
    return datos


def previsualizar_spec_bytes(
    spec: dict[str, Any], formato: str, *, titular: str = "", etiqueta_default: str = "",
) -> bytes:
    """Renderiza un SPEC en EDICIÓN (sin guardar) en placeholder y devuelve los BYTES, SIN persistir.

    Lo usa el editor visual del diseñador para ver "lo que sale" mientras se diseña. La previa es
    función pura del spec en edición: NO se almacena (se sirve por HTTP, efímera). Valida el spec,
    renderiza con Node (placeholder, sin foto) con un titular/pleca de muestra y devuelve el PNG.
    """
    fmt = formato
    if fmt not in _FORMATOS_COMPONER:
        raise EstudioError("Formato no soportado. Usa: " + ", ".join(_FORMATOS_COMPONER) + ".")
    try:
        spec_ok = spec_plantilla.validar(spec)
    except spec_plantilla.SpecError as exc:
        raise EstudioError(str(exc)) from exc
    if fmt not in spec_ok.get("formatos", {}):
        raise EstudioError(f"El spec no tiene el formato '{fmt}'.")

    with tempfile.TemporaryDirectory(prefix="keni-preview-") as tmp:
        carpeta = Path(tmp)
        logo_cfg = spec_ok["formatos"][fmt].get("logo") or {}
        ruta_logo = _materializar_logo(logo_cfg.get("media_id", ""), carpeta)
        fondo_cfg = spec_ok["formatos"][fmt].get("fondo") or {}
        ruta_fondo = ""
        if fondo_cfg.get("tipo") == "imagen":
            ruta_fondo = _materializar_logo((fondo_cfg.get("imagen") or {}).get("media_id", ""), carpeta)
        out = carpeta / "preview.png"
        payload = {
            "spec": spec_ok, "formato": fmt, "placeholder": True, "foto": None,
            "assets": {"logo": ruta_logo or None, "fondo": ruta_fondo or None},
            "bindings": {"copy_in": titular or "Titular de ejemplo",
                         "etiqueta_default": etiqueta_default or ""},
        }
        _correr_render_node(payload, out)
        return out.read_bytes()


def componer(
    imagen: str,
    *,
    marca: str,
    formato: str = "feed",
    titular: str = "",
    etiqueta: str | None = None,
    autor: dict[str, str] | None = None,
    logo_path: str | None = None,
) -> dict[str, Any]:
    """Compone la PLANTILLA de marca y devuelve `{id,url,imagenes,info}` (firma estable).

    Render por SPEC con el motor **Node** (`render_node`, único motor: lo diseñado en el editor
    es lo que sale). Si Node falla, lanza `EstudioError` (los llamantes lo manejan: la auto-gen
    de copy es tolerante y omite la placa; la API devuelve 4xx).

    `imagen`: id de media de la foto; `""` => PLANTILLA con el hueco de foto vacío (placeholder
    "Sube una foto"). `etiqueta`: `None` => etiqueta_default de la marca; `""` => sin pleca;
    texto => esa pleca. `formato`: `vertical|feed|cuadrado|horizontal` (cada uno tiene su SPEC).
    `logo_path`: ruta de disco a un logo (asset de marca mock/oficial) que sustituye al del
    spec; `None` usa el logo de la plantilla (comportamiento normal).
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    fmt = formato
    if fmt not in _FORMATOS_COMPONER:
        raise EstudioError(
            "Formato no soportado para componer. Usa: " + ", ".join(_FORMATOS_COMPONER) + "."
        )
    return _componer_node(
        imagen, marca=marca, fmt=fmt, titular=titular, etiqueta=etiqueta, logo_path=logo_path
    )


# --------------------------------------------------------------------------- #
# Render del DOCUMENTO de capas (editor profesional)                           #
# --------------------------------------------------------------------------- #


def _ruta_render_documento() -> Path:
    return _ruta_motor("render_node") / "render_documento.mjs"


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


def _refs_imagenes(capas: list[dict[str, Any]]) -> set[str]:
    """Ids de media referenciados por las capas (imagen.objeto + logo.media_id), recursivo en grupos."""
    refs: set[str] = set()
    for c in capas:
        if c.get("tipo") == "imagen" and (c.get("objeto") or "").strip():
            refs.add(c["objeto"])
        elif c.get("tipo") == "logo" and c.get("tipo_logo") == "imagen" and (c.get("media_id") or "").strip():
            refs.add(c["media_id"])
        elif c.get("tipo") == "grupo":
            refs |= _refs_imagenes(c.get("capas") or [])
    return refs


def _fuentes_extra_de_marca(marca: str, carpeta: Path) -> dict[str, str]:
    """Tipografías propias de la marca (activos tipo 'tipografia') -> {familia: ruta_archivo}.

    Materializa cada fuente subida (.woff2/.ttf) para que el renderer Node la registre y el PNG
    final use la fuente real. La familia es `metadatos.familia` o, si falta, el `nombre` del activo
    (mismo nombre con el que el editor la registra en cliente vía FontFace -> coinciden).
    """
    if not (marca or "").strip():
        return {}
    extra: dict[str, str] = {}
    for activo in repos.listar_marca_activos(marca=marca, tipo="tipografia"):
        objeto = (activo.get("objeto") or "").strip()
        if not objeto:
            continue
        try:
            meta = json.loads(activo.get("metadatos") or "{}")
        except (ValueError, TypeError):
            meta = {}
        familia = ((meta.get("familia") if isinstance(meta, dict) else "") or activo.get("nombre") or "").strip()
        if not familia:
            continue
        datos = media.leer_media(objeto)
        if datos is None:
            continue
        ruta = carpeta / f"fuente-{_nombre_local_plano(objeto)}"
        ruta.write_bytes(datos)
        extra[familia] = str(ruta)
    return extra


def renderizar_documento_bytes(
    documento: dict[str, Any], *, bindings: dict[str, str] | None = None,
) -> bytes:
    """Valida y renderiza un DOCUMENTO de capas a los BYTES del PNG (motor Node), SIN persistir.

    Materializa cada imagen referenciada a un temporal y corre Node; devuelve los bytes. Lo usa el
    render ON-DEMAND (sirve por HTTP sin generar objetos). Lanza `EstudioError` si no valida/falla.
    """
    try:
        doc = doc_capas.validar(documento)
    except doc_capas.DocumentoError as exc:
        raise EstudioError(str(exc)) from exc

    with tempfile.TemporaryDirectory(prefix="keni-doc-") as tmp:
        carpeta = Path(tmp)
        assets: dict[str, str] = {}
        refs = _refs_imagenes(doc["capas"])
        fondo = doc.get("fondo") or {}
        if fondo.get("tipo") == "imagen":
            mid = (fondo.get("imagen") or {}).get("media_id", "")
            if mid:
                refs.add(mid)
        for ref in refs:
            ruta = _materializar_logo(ref, carpeta)
            if ruta:
                assets[ref] = ruta

        fuentes_extra = _fuentes_extra_de_marca(doc.get("marca", ""), carpeta)

        out = carpeta / "salida.png"
        payload = {
            "documento": doc,
            "assets": assets,
            "fuentes": doc.get("fuentes"),
            "fuentes_extra": fuentes_extra,
            "bindings": bindings or {},
        }
        _correr_render_documento(payload, out)
        return out.read_bytes()


def renderizar_documento(
    documento: dict[str, Any], *, bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Renderiza un DOCUMENTO de capas y PERSISTE el PNG (content-addressed) -> `{id, url}`.

    Para flujos con asset DURABLE referenciado (bake del editor pro). El render on-demand usa
    `renderizar_documento_bytes` (sin persistir).
    """
    datos = renderizar_documento_bytes(documento, bindings=bindings)
    try:
        nombre = media.guardar_bytes_contenido(datos, ext="png")
    except media.MediaError as e:
        raise EstudioError(str(e)) from e
    return {"id": nombre, "url": f"/api/media/{nombre}"}


def _fotos_de(
    fotos: list[dict[str, Any]] | None,
    foto: str,
    foco: tuple[float, float] | list[float] | None,
    zoom: float,
) -> list[dict[str, Any]]:
    """Normaliza la entrada de fotos: si llega la lista de COLLAGE (`fotos`) se usa tal cual; si no,
    se construye una lista de UN elemento con la foto única + su reencuadre (retrocompat)."""
    if fotos:
        return fotos
    return [{"objeto": foto or "", "foco": foco, "zoom": zoom}]


def _doc_plantilla_con_fotos(
    documento: dict[str, Any] | str,
    fotos: list[dict[str, Any]],
) -> dict[str, Any]:
    """Inyecta UNA foto por HUECO (`es_foto`) del documento, en orden de `capas`.

    Devuelve una COPIA del documento lista para renderizar. `documento` puede ser dict o JSON
    string (lo que guarda `PlantillaDiseno`). `fotos[i]` (`{objeto, foco:[x,y]|None, zoom}`) va al
    hueco i; los huecos sin foto correspondiente quedan vacíos (placeholder). Las plantillas de solo
    texto/gráfica no tienen hueco y no reciben nada.
    """
    if isinstance(documento, str):
        try:
            documento = json.loads(documento or "{}")
        except (ValueError, TypeError) as exc:
            raise EstudioError("La plantilla no tiene un documento válido.") from exc
    doc = copy.deepcopy(documento)
    huecos = doc_capas.capas_foto(doc)
    for i, hueco in enumerate(huecos):
        spec = fotos[i] if i < len(fotos) else None
        if not isinstance(spec, dict):
            continue
        hueco["objeto"] = str(spec.get("objeto") or "")
        foco = spec.get("foco")
        if isinstance(foco, (list, tuple)) and len(foco) == 2:
            hueco["foco"] = [float(foco[0]), float(foco[1])]
        zoom = spec.get("zoom")
        if zoom and float(zoom) > 0:
            hueco["zoom"] = float(zoom)
    return doc


def componer_desde_plantilla(
    documento: dict[str, Any] | str,
    *,
    copy_in: str = "",
    foto: str = "",
    foco: tuple[float, float] | list[float] | None = None,
    zoom: float = 0.0,
    fotos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Renderiza la plantilla con la(s) foto(s)+copy_in de la pieza y PERSISTE el PNG -> `{id, url}`.

    Inyecta UNA foto por hueco (`es_foto`) y el `copy_in` como binding del titular. `fotos` (collage)
    tiene prioridad; si no llega, usa la foto única (`foto`/`foco`/`zoom`) en el primer hueco.
    """
    doc = _doc_plantilla_con_fotos(documento, _fotos_de(fotos, foto, foco, zoom))
    return renderizar_documento(doc, bindings={"copy_in": copy_in})


def componer_desde_plantilla_bytes(
    documento: dict[str, Any] | str,
    *,
    copy_in: str = "",
    foto: str = "",
    foco: tuple[float, float] | list[float] | None = None,
    zoom: float = 0.0,
    fotos: list[dict[str, Any]] | None = None,
) -> bytes:
    """Como `componer_desde_plantilla` pero devuelve los BYTES del PNG SIN persistir (on-demand)."""
    doc = _doc_plantilla_con_fotos(documento, _fotos_de(fotos, foto, foco, zoom))
    return renderizar_documento_bytes(doc, bindings={"copy_in": copy_in})


def parsear_encuadre(encuadre: str) -> tuple[list[float] | None, float]:
    """Parsea el JSON de reencuadre de una pieza (`{"foco":[x,y],"zoom":z}`).

    Devuelve `(foco | None, zoom)`. Tolerante: "" o JSON inválido → `(None, 0.0)` (sin
    reencuadre). El foco se recorta a [0,1] y el zoom a [1, 6] para no romper el render.
    """
    if not (encuadre or "").strip():
        return None, 0.0
    try:
        datos = json.loads(encuadre)
    except (ValueError, TypeError):
        return None, 0.0
    if not isinstance(datos, dict):
        return None, 0.0
    foco_bruto = datos.get("foco")
    foco: list[float] | None = None
    if isinstance(foco_bruto, (list, tuple)) and len(foco_bruto) == 2:
        try:
            foco = [
                min(1.0, max(0.0, float(foco_bruto[0]))),
                min(1.0, max(0.0, float(foco_bruto[1]))),
            ]
        except (ValueError, TypeError):
            foco = None
    try:
        zoom = float(datos.get("zoom") or 0.0)
    except (ValueError, TypeError):
        zoom = 0.0
    if zoom:
        zoom = min(6.0, max(1.0, zoom))
    return foco, zoom


def validar_documento(documento: dict[str, Any]) -> dict[str, Any]:
    """Valida y normaliza un Documento de capas -> dict normalizado. Lanza EstudioError si falla.

    Lo usan las APIs que PERSISTEN un documento (plantillas de diseño, bloques) para no guardar
    JSON inválido. Mantiene la frontera API->dominio (la API no importa motores directamente).
    """
    try:
        return doc_capas.validar(documento)
    except doc_capas.DocumentoError as exc:
        raise EstudioError(str(exc)) from exc


def documento_tiene_hueco(documento: dict[str, Any]) -> bool:
    """True si el documento declara un hueco de foto explícito (`es_foto`). Frontera API->dominio."""
    return doc_capas.tiene_hueco_explicito(documento)


def validar_capas(capas: Any) -> list[dict[str, Any]]:
    """Valida una LISTA de capas (para bloques reutilizables) -> lista normalizada.

    Reusa el validador del Documento envolviendo las capas en un documento mínimo. Lanza
    EstudioError si alguna capa no valida.
    """
    doc = validar_documento({"formato": {"w": 1, "h": 1}, "capas": capas})
    return doc["capas"]


def documento_desde_plantilla(marca: str, formato: str) -> dict[str, Any]:
    """Documento de capas EDITABLE derivado de la plantilla de marca (punto de partida del editor).

    Toma el spec efectivo de la marca y adapta el formato pedido a un documento de capas. Así el
    editor abre una marca con su layout actual (foto + overlay + textos + logo) ya como capas.
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    if formato not in _FORMATOS_COMPONER:
        raise EstudioError("Formato no soportado. Usa: " + ", ".join(_FORMATOS_COMPONER) + ".")
    spec = plantillas_marca.obtener_spec(marca)
    try:
        return doc_capas.desde_spec(spec, formato)
    except doc_capas.DocumentoError as exc:
        raise EstudioError(str(exc)) from exc


# --------------------------------------------------------------------------- #
# Set multi-formato "de un tiro" desde UNA imagen aportada (Fase 3)            #
# --------------------------------------------------------------------------- #


def _logo_de_marca(marca: str) -> str | None:
    """Ruta de disco al logo (asset de marca, mock/oficial) o `None` si no hay/falla.

    `None` deja a `componer` usar el logo del spec (wordmark de texto por defecto): el flujo
    NUNCA se queda sin placa por falta de asset.
    """
    try:
        ruta = marca_assets.ruta_asset(marca, marca_assets.TIPO_LOGO)
    except marca_assets.MarcaAssetError:
        return None
    return ruta or None


def _encajar_a_lienzo(imagen: str, lienzo: str) -> str:
    """Encaja la imagen aportada al lienzo (DETERMINISTA) y devuelve el id de media resultante.

    Prefiere EXTENDER el fondo uniforme (no recorta al sujeto); si ningun borde es uniforme,
    el motor `extender` cae solo al recorte cubriente. Sin coste, sin IA. Devuelve el id del
    nuevo objeto de media ya encajado al lienzo, listo para estampar la marca encima.
    """
    res = editar(imagen, "extender", {"formato": lienzo, "metodo": "borde", "forzar": False})
    return res["id"]


def generar_set_formatos(
    imagen: str,
    *,
    marca: str,
    red: str = "",
    titular: str = "",
    etiqueta: str | None = None,
    aplicar_marca: bool = True,
) -> dict[str, Any]:
    """Desde UNA imagen aportada, produce el SET de formatos de una red (o todos los lienzos).

    Es el "de un tiro" de la Fase 3: el equipo trae la foto y la IA la encaja a TODOS los
    lienzos de la red destino (matriz `formatos_red`) y le aplica la identidad de marca,
    por via DETERMINISTA (Pillow, gratis, exacto). La generacion por IA NO interviene aqui.

    Flujo por lienzo (todo determinista):
      1. ENCAJAR la foto al lienzo extendiendo el fondo uniforme si se puede (no recorta al
         sujeto); si no, recorte cubriente.
      2. (si `aplicar_marca`) ESTAMPAR la plantilla de marca (logo del asset de la casa +
         pleca + titular) con `componer`. TODOS los lienzos llevan placa, incluido
         `horizontal` (16:9 de X): el SPEC deriva su layout en 1600×900 igual que los demas,
         asi que el formato de X sale `marcado:true` como feed/vertical/cuadrado.

    `red`: si es una red conocida, usa SUS lienzos (`formatos_red.lienzos_de`); si esta vacia
    o no se conoce, usa el set MAXIMO de lienzos canonicos. `etiqueta`: contrato de `componer`
    (None=default de marca, ""=sin pleca, texto=esa pleca).

    Devuelve `{red, marca, formatos:[{lienzo, aspecto, marcado, id, url}], imagenes:[...]}`.
    Los objetos intermedios (encajes sin marca) quedan como huerfanos del almacen (los recoge
    el GC de media, como las variantes no elegidas del Estudio).
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    if not (imagen or "").strip():
        raise EstudioError("Falta la imagen aportada para generar el set de formatos.")

    lienzos = formatos_red.lienzos_de(red) if red else []
    if not lienzos:
        lienzos = formatos_red.lienzos_canonicos()

    logo_path = _logo_de_marca(marca) if aplicar_marca else None
    resultados: list[dict[str, Any]] = []
    for lienzo in lienzos:
        encajada = _encajar_a_lienzo(imagen, lienzo)
        marcado = False
        salida_id, salida_url = encajada, f"/api/media/{encajada}"
        # El compositor por SPEC entiende todos los lienzos de FORMATOS (incl. `horizontal`,
        # 16:9 de X): cada uno estampa su placa con su layout derivado del spec.
        if aplicar_marca and lienzo in _FORMATOS_COMPONER:
            comp = componer(
                encajada, marca=marca, formato=lienzo, titular=titular,
                etiqueta=etiqueta, logo_path=logo_path,
            )
            salida_id, salida_url = comp["id"], comp["url"]
            marcado = True
        resultados.append(
            {
                "lienzo": lienzo,
                "aspecto": formatos_red.ASPECTOS.get(lienzo, ASPECTOS.get(lienzo, "")),
                "marcado": marcado,
                "id": salida_id,
                "url": salida_url,
            }
        )

    return {
        "red": red,
        "marca": marca,
        "formatos": resultados,
        "imagenes": [{"id": r["id"], "url": r["url"]} for r in resultados],
    }


# --------------------------------------------------------------------------- #
# Revision legal/editorial (job `claude` que VE la imagen)                     #
# --------------------------------------------------------------------------- #


def _instruccion_revision(archivo: str) -> str:
    """Instruccion al revisor: mira la imagen adjunta y devuelve un checklist; NO aprueba."""
    return (
        f"Revisa la imagen adjunta `{archivo}` contra estas reglas de imagen y devuelve un "
        "checklist con un emoji por cada punto (✅ cumple · ⚠️ revisar · ❌ incumple), citando "
        "concretamente lo que VES en la imagen que justifica cada marca. No apruebes tu: tu "
        "salida es un INFORME para que un humano decida si publica. Si algo no se puede "
        "comprobar con la imagen, marcalo como ⚠️ y dilo, no lo inventes."
    )


def revisar(imagen: str, *, marca: str = "", autor: dict[str, str] | None = None) -> dict[str, Any]:
    """Pasa un objeto de media por una revision legal/editorial con `claude -p` -> registro.

    Es el gate humano (opcion §3.5.a del diseno): NO bloquea publicar. `claude` VE la imagen
    via `--add-dir` (materializada en un temporal) y aplica las reglas de imagen de la
    Texto (`editorial/reglas/imagen`); devuelve un checklist ✅/⚠️/❌. El texto en vivo
    queda en `salida` del registro (el frontend lo sondea). El post-procesado es IDENTIDAD
    (`PROC_PROMPT`): no crea piezas ni artefactos.

    El temporal NO lo borramos aqui: `generar.lanzar` lo pasa como `--add-dir` y lo limpia al
    terminar el job (igual que las subidas de copy/clip).
    """
    datos = media.leer_media(imagen)
    if datos is None:
        raise EstudioError("Esa imagen no existe en el almacen.")

    # Materializa la imagen en un temporal PERSISTENTE (sin context manager): `generar.lanzar`
    # lo borra al terminar el job. Conserva la extension para que `claude` la abra bien.
    carpeta = Path(tempfile.mkdtemp(prefix="keni-revision-"))
    ext = Path(imagen).suffix.lower() or ".png"
    archivo = f"imagen{ext}"
    (carpeta / archivo).write_bytes(datos)

    reglas = libtexto.cuerpo_efectivo(REGLAS_IMAGEN) or ""
    prompt = generar.componer(
        _instruccion_revision(archivo),
        [],
        ("REGLAS DE IMAGEN:\n\n" + reglas) if reglas else "",
    )

    return generar.lanzar(
        tipo="qa-editorial",
        titulo="Revisión de imagen",
        marca=marca,
        prompt=prompt,
        procesar=jobspec.reconstruir_procesar({"procesar": jobspec.construir_prompt_lib()}),
        procesar_spec=jobspec.construir_prompt_lib(),
        dir_temporal=carpeta,
        autor=autor,
    )

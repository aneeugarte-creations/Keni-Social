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
                                con la clave del proveedor inyectada via `_entorno_skill`.

SEGURIDAD: sin shell (argv como lista); la imagen de entrada se materializa en un
temporal que se borra al terminar; los nombres en el almacen los genera el servidor
(uuid); los errores salen como texto en espanol (los recoge `lanzar_job_imagen`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .. import biblioteca, generaciones, marcas, media, plantillas_marca
from ..motores.estudio_imagen import spec_plantilla
from . import generar, jobspec

# Reglas de imagen (Biblioteca) que se adjuntan a la revision legal/editorial.
REGLAS_IMAGEN = "editorial/reglas/imagen"

# Formatos de red soportados (espejo de `motores/estudio_imagen/editar.py:FORMATOS`).
FORMATOS = ("vertical", "feed", "cuadrado", "horizontal")
ASPECTOS = {"vertical": "9:16", "feed": "4:5", "cuadrado": "1:1", "horizontal": "16:9"}

# Operaciones DETERMINISTAS del motor `editar.py` (sin IA, sin coste).
OPS_EDITAR = ("recortar", "redimensionar", "comprimir", "extender", "placa")

# Prompt base de imagen en la Biblioteca (editable por el equipo; cae a "" si falta).
PROMPT_IMAGEN_DEFECTO = "prompt/imagen/ilustracion-fondo"

# Marcas con identidad visual definida en `motores/estudio_imagen/marcas.json` (placa/breaking).
_MARCAS_VISUALES = ("unotv", "claro-sports")

# Nota de estilo por marca para el prompt generativo (referencia corta; la guia completa
# vive como documento editorial en la Biblioteca). Replica `motores/.../generar.ESTILO_MARCA`.
_ESTILO_MARCA = {
    "unotv": "Estilo UnoTV: noticias, sobrio, creible, alto contraste, rojo #E30613 como acento puntual.",
    "claro-sports": "Estilo Claro Sports: deportivo, energia, alto contraste, rojo #CF2E2E de marca.",
}

# Wall-timeouts: editar es determinista (rapido); expandir llama al proveedor (lento).
_TIMEOUT_EDITAR_S = 60
_TIMEOUT_EXPANDIR_S = 240
# Componer es determinista (Pillow), como editar: rapido, sin red.
_TIMEOUT_COMPONER_S = 60

# Formatos que ENTIENDE el compositor (`componer.py`): subconjunto de FORMATOS sin
# `horizontal`. `horizontal` (16:9) NO es un formato de breaking del compositor, asi que
# se MAPEA a `feed` (4:5): es el encaje editorial mas cercano para una pieza de feed/post.
_FORMATOS_COMPONER = ("vertical", "feed", "cuadrado")


class EstudioError(RuntimeError):
    """Error de dominio del Estudio, con mensaje en espanol listo para la UI."""


def marca_tiene_plantilla(marca: str) -> bool:
    """True si la marca tiene identidad visual de placa (tokens en `marcas.json`).

    Solo esas marcas pueden auto-componer la imagen-plantilla (logo + pleca + titular). Las
    demas del catalogo no tienen tokens todavia, asi que se omiten (no se compone nada).
    """
    return marca in _MARCAS_VISUALES


# Formato de placa por red. El compositor solo entiende vertical|feed|cuadrado; se elige el
# encaje editorial mas cercano al aspecto de cada red (tiktok 9:16 -> vertical; ig 1:1 ->
# cuadrado; el resto -> feed 4:5). Una red desconocida cae a `feed`.
_FORMATO_POR_RED = {
    "tiktok": "vertical",
    "instagram": "cuadrado",
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
    """Arma el prompt de imagen: base de la Biblioteca + lo pedido + estilo de marca + aspecto.

    El estilo de marca (hoy una constante) pasa a ser editable: si la Biblioteca tiene el
    prompt base (`prompt/imagen/...`) gana esa version; la nota de marca es un complemento
    corto. NO volcamos la linea editorial de copy (voz) en un prompt de imagen: seria ruido.
    """
    formato = formato if formato in FORMATOS else "feed"
    base = biblioteca.cuerpo_efectivo(prompt_id) or ""
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

    Requiere proveedor configurado: la clave viaja al subproceso via `_entorno_skill`.
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
        info = _correr_motor(cmd, timeout=_TIMEOUT_EXPANDIR_S, env=generaciones._entorno_skill())
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


def _materializar_logo(logo_id: str, carpeta: Path) -> str:
    """Vuelca un objeto de media (logo/fondo) a un PNG temporal; '' si no hay o no existe."""
    logo_id = (logo_id or "").strip()
    if not logo_id:
        return ""
    datos = media.leer_media(logo_id)
    if datos is None:
        return ""
    ruta = carpeta / f"asset-{logo_id}.png"
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


def _componer_node(
    imagen: str, *, marca: str, fmt: str, titular: str, etiqueta: str | None,
) -> dict[str, Any]:
    """Render por SPEC con el motor Node (lo que se diseña en el editor = lo que sale)."""
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
        ruta_logo = _materializar_logo(logo_cfg.get("media_id", ""), carpeta)
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
        try:
            nombre = media.importar_imagen(str(out))
        except media.MediaError as e:
            raise EstudioError(str(e)) from e
        return {
            "id": nombre, "url": f"/api/media/{nombre}",
            "imagenes": [{"id": nombre, "url": f"/api/media/{nombre}"}],
            "info": {"op": "componer", "marca": marca, "formato": fmt,
                     "placeholder": placeholder, "motor": "node"},
        }


def previsualizar_spec(
    spec: dict[str, Any], formato: str, *, titular: str = "", etiqueta_default: str = "",
) -> dict[str, Any]:
    """Renderiza un SPEC en EDICIÓN (sin guardar) en modo placeholder -> `{id, url}`.

    Lo usa el editor visual para mostrar "lo que sale" mientras se diseña. Valida el spec, lo
    renderiza con el motor Node (placeholder, sin foto) usando un titular/pleca de muestra, e
    importa el PNG a media. Fuerza Node (sin fallback Pillow: el editor previsualiza el spec real).
    """
    fmt = "feed" if formato == "horizontal" else formato
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
        try:
            nombre = media.importar_imagen(str(out))
        except media.MediaError as exc:
            raise EstudioError(str(exc)) from exc
        return {"id": nombre, "url": f"/api/media/{nombre}"}


def componer(
    imagen: str,
    *,
    marca: str,
    formato: str = "feed",
    titular: str = "",
    etiqueta: str | None = None,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compone la PLANTILLA de marca y devuelve `{id,url,imagenes,info}` (firma estable).

    Render por SPEC con el motor **Node** (`render_node`, único motor: lo diseñado en el editor
    es lo que sale). Si Node falla, lanza `EstudioError` (los llamantes lo manejan: la auto-gen
    de copy es tolerante y omite la placa; la API devuelve 4xx).

    `imagen`: id de media de la foto; `""` => PLANTILLA con el hueco de foto vacío (placeholder
    "Sube una foto"). `etiqueta`: `None` => etiqueta_default de la marca; `""` => sin pleca;
    texto => esa pleca. `formato`: `vertical|feed|cuadrado`; `horizontal` se mapea a `feed`.
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    fmt = "feed" if formato == "horizontal" else formato
    if fmt not in _FORMATOS_COMPONER:
        raise EstudioError(
            "Formato no soportado para componer. Usa: " + ", ".join(_FORMATOS_COMPONER) + "."
        )
    return _componer_node(imagen, marca=marca, fmt=fmt, titular=titular, etiqueta=etiqueta)


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
    Biblioteca (`editorial/reglas/imagen`); devuelve un checklist ✅/⚠️/❌. El texto en vivo
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

    reglas = biblioteca.cuerpo_efectivo(REGLAS_IMAGEN) or ""
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

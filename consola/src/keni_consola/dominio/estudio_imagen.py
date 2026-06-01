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
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .. import biblioteca, generaciones, marcas, media, plantillas_marca
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


def _formatos_base() -> dict[str, Any]:
    """Bloque `formatos` del catalogo estatico `motores/.../marcas.json` (w/h/zonas seguras)."""
    ruta = _ruta_motor("marcas.json")
    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    formatos = cfg.get("formatos")
    if not isinstance(formatos, dict) or not formatos:
        raise EstudioError("No se pudo leer la configuración de formatos del compositor.")
    return formatos


def _cfg_marca(marca: str, plantilla: dict[str, Any], ruta_logo: str) -> dict[str, Any]:
    """Construye un cfg COMPLETO de marca (schema de marcas.json) desde la plantilla editable.

    Fusiona los campos editables de la plantilla con los campos NO editables que el motor
    espera (`nombre`, `id_metricas`, overlays vacios, `verificar`). `logo` se materializa a
    una RUTA de disco (PNG temporal) si la plantilla referencia un objeto de media; si no,
    queda "" para que el motor caiga al wordmark.
    """
    return {
        "nombre": marcas.etiqueta_de(marca),
        "id_metricas": marcas.id_metricas_de(marca),
        "rojo": plantilla["rojo"],
        "tinta": plantilla["tinta"],
        "blanco": plantilla["blanco"],
        "etiqueta_default": plantilla["etiqueta_default"],
        "titular_mayusculas": bool(plantilla["titular_mayusculas"]),
        "titular_condensada": bool(plantilla["titular_condensada"]),
        "logo": ruta_logo,
        "marca_agua": "",
        "overlay_breaking": "",
        "logo_posicion": plantilla["logo_posicion"],
        "wordmark": plantilla["wordmark"],
        "verificar": "",
    }


def componer(
    imagen: str,
    *,
    marca: str,
    formato: str = "feed",
    titular: str = "",
    etiqueta: str | None = None,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Estampa la PLANTILLA de marca (logo + pleca + titular) sobre una foto -> resultado uniforme.

    Determinista (Pillow, sin red): corre `motores/estudio_imagen/componer.py` por subproceso
    con un `marcas.json` TEMPORAL construido desde la plantilla editable de la marca
    (`plantillas_marca.obtener`). El `logo` referenciado (objeto de media) se materializa a un
    PNG temporal; si no hay logo, el motor cae al wordmark de respaldo.

    `imagen`: id de media de la foto; si es `""`, se compone una PLANTILLA con el HUECO DE LA
    FOTO VACÍO (placeholder gris "Sube una foto") — pensada para auto-generarse al crear el copy
    y recomponerse luego al subir la foto real.

    `etiqueta`: `None` => usa la `etiqueta_default` de la plantilla; `""` => omite la pleca;
    un texto => esa pleca. `formato`: `vertical|feed|cuadrado`; `horizontal` se mapea a `feed`.
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    fmt = "feed" if formato == "horizontal" else formato
    if fmt not in _FORMATOS_COMPONER:
        raise EstudioError(
            "Formato no soportado para componer. Usa: " + ", ".join(_FORMATOS_COMPONER) + "."
        )

    try:
        plantilla = plantillas_marca.obtener(marca)
    except plantillas_marca.PlantillaMarcaError as e:
        raise EstudioError(str(e)) from e

    placeholder = not (imagen or "").strip()

    with tempfile.TemporaryDirectory(prefix="keni-componer-") as tmp:
        carpeta = Path(tmp)
        foto = None if placeholder else _materializar(imagen, carpeta)

        # Materializa el logo (objeto de media) a un PNG temporal; "" si no hay o no existe.
        ruta_logo = ""
        logo_id = (plantilla.get("logo") or "").strip()
        if logo_id:
            datos_logo = media.leer_media(logo_id)
            if datos_logo is not None:
                logo_path = carpeta / "logo.png"
                logo_path.write_bytes(datos_logo)
                ruta_logo = str(logo_path)

        # marcas.json TEMPORAL: solo esta marca + los formatos base copiados del catalogo.
        cfg = {"marcas": {marca: _cfg_marca(marca, plantilla, ruta_logo)}, "formatos": _formatos_base()}
        cfg_path = carpeta / "marcas.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

        out = carpeta / "salida.png"
        motor = _ruta_motor("componer.py")
        cmd = [
            sys.executable, str(motor),
            "--marca", marca,
            "--formato", fmt,
            "--salida", str(out),
            "--config", str(cfg_path),
        ]
        cmd += ["--placeholder"] if placeholder else ["--foto", str(foto)]
        if titular:
            cmd += ["--titular", titular]
        if etiqueta is not None:  # None = etiqueta_default; "" = sin pleca; texto = esa pleca
            cmd += ["--etiqueta", etiqueta]

        # TÚ pasas --salida: no hay que parsear "DATOS"; basta returncode 0 + archivo creado.
        try:
            proc = subprocess.run(  # noqa: S603 -- argv lista, sin shell; rutas controladas por el server
                cmd, capture_output=True, text=True, timeout=_TIMEOUT_COMPONER_S, check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise EstudioError(
                f"La composición tardó demasiado (más de {_TIMEOUT_COMPONER_S} s) y se canceló."
            ) from e
        if proc.returncode != 0 or not out.is_file():
            detalle = (proc.stderr or "").strip()[-300:]
            raise EstudioError(
                "El compositor de marca no produjo un resultado. " + (detalle or "Revisa la imagen de entrada.")
            )

        try:
            nombre = media.importar_imagen(str(out))
        except media.MediaError as e:
            raise EstudioError(str(e)) from e

        importada = {"id": nombre, "url": f"/api/media/{nombre}"}
        info = {"op": "componer", "marca": marca, "formato": fmt, "placeholder": placeholder}
        return {"id": nombre, "url": importada["url"], "imagenes": [importada], "info": info}


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

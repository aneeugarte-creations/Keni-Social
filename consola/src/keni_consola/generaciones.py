"""Dominio GENERACIONES: trabajos de IA en SEGUNDO PLANO, seguibles en vivo.

TODA generacion de IA de la consola (copy desde nota, copy desde RSS, hashtags,
imagen) corre como un TRABAJO en segundo plano en vez de bloquear la peticion HTTP:

  1. El endpoint valida, crea un registro `{estado: "ejecutando"}` y lanza el trabajo
     EN BACKGROUND (Popen + hilo lector para claude; un hilo simple para imagen).
  2. El POST responde de INMEDIATO con el registro (no bloquea, no hay timeout de 180 s
     en la peticion). El trabajo sigue aunque el usuario cambie de pestana o de pagina.
  3. El hilo avanza el registro de forma incremental y ATOMICA: para los trabajos de
     claude persiste el TEXTO en vivo (stream token a token con `--include-partial-
     messages`) + metricas parciales (turnos/tokens). Al terminar fija el estado
     terminal (`completado` con el `resultado` ya procesado, o `error`).
  4. El frontend SONDEA `GET /api/generaciones/{id}` hasta el estado terminal.

El registro YAML es la FUENTE DE VERDAD del sondeo. Los ARTEFACTOS durables (historial
de skills, publicaciones, imagenes) se guardan en su sitio de siempre; el registro de
generacion es estado de ejecucion (efimero, inspeccionable), por eso vive aparte de los
datos editoriales:

    <KENI_CONSOLA_GENERACIONES>/<id>.yaml         (def ~/.config/keni-social/generaciones)

LANZADORES INYECTABLES: `lanzar_job_claude` y `lanzar_job_imagen` son funciones a nivel
de modulo; `crear_app(...)` las reasigna y los tests pasan fakes que NO usan Popen ni
red (NUNCA se llama a `claude` ni a un proveedor de imagen real en tests). El
`procesar` (callback que parsea la salida y crea los artefactos) SI corre en los tests
(con una salida canned), asi se cubre el post-procesado real.

SEGURIDAD: escritura atomica (tmp + os.replace); el id de un registro se sanea contra
traversal al leer; sin shell (argv como lista). Errores en espanol, sin tracebacks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from . import preferencias

# Estados terminales e intermedio de un trabajo.
ESTADO_EJECUTANDO = "ejecutando"
ESTADO_COMPLETADO = "completado"
ESTADO_ERROR = "error"

# Tipos de trabajo (para que el frontend sepa como renderizar el resultado).
TIPOS = ("copy", "rss", "hashtags", "imagen", "verificacion")

# Wall-timeout (segundos) de un trabajo de claude en background. Override por
# `KENI_CLAUDE_TIMEOUT`. Sustituye al viejo timeout de 180 s de la peticion sincrona.
_TIMEOUT_DEF = 600

# Registro EN MEMORIA de trabajos en vuelo (id -> handle). El YAML es la fuente de
# verdad para el sondeo; esto solo permite inspeccionar/cancelar localmente.
_HANDLES: dict[str, dict[str, object]] = {}
_HANDLES_LOCK = threading.Lock()

# Numero de generaciones recientes que devuelve el listado.
_LISTADO_MAX = 50


def _timeout() -> int:
    """Wall-timeout (s) de un trabajo de claude; `KENI_CLAUDE_TIMEOUT` lo sobreescribe."""
    crudo = (os.environ.get("KENI_CLAUDE_TIMEOUT") or "").strip()
    if crudo:
        try:
            valor = int(crudo)
        except ValueError:
            return _TIMEOUT_DEF
        if valor > 0:
            return valor
    return _TIMEOUT_DEF


def nuevo_id() -> str:
    """Nuevo id de generacion (12 hex)."""
    return uuid.uuid4().hex[:12]


def ahora_iso() -> str:
    """Fecha-hora ISO a segundos (orden determinista de las generaciones)."""
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Localizacion del almacen + escritura atomica                                #
# --------------------------------------------------------------------------- #


def raiz() -> Path:
    """Dir donde viven los registros de generacion. `KENI_CONSOLA_GENERACIONES` lo fija."""
    env = os.environ.get("KENI_CONSOLA_GENERACIONES")
    if env:
        return Path(env)
    return Path.home() / ".config" / "keni-social" / "generaciones"


def _ruta(gen_id: str) -> Path:
    """Ruta `<raiz>/<id>.yaml` saneada (solo el nombre base; anti-traversal)."""
    base = raiz()
    seguro = Path(gen_id).name
    if not seguro or seguro != gen_id or seguro in (".", ".."):
        raise ValueError("Identificador de generación no válido.")
    destino = (base / f"{seguro}.yaml").resolve()
    if destino.parent != base.resolve():
        raise ValueError("Ruta de generación fuera del almacén.")
    return destino


def _escribir_yaml_atomico(ruta_fichero: Path, datos: dict[str, Any]) -> None:
    """Escribe un dict como YAML de forma ATOMICA (tmp en el mismo dir + os.replace)."""
    ruta_fichero.parent.mkdir(parents=True, exist_ok=True)
    texto = yaml.safe_dump(
        datos, default_flow_style=False, allow_unicode=True, sort_keys=False, width=4096
    )
    fd, tmp_nombre = tempfile.mkstemp(
        dir=str(ruta_fichero.parent), prefix=".tmp-", suffix=".yaml"
    )
    tmp = Path(tmp_nombre)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(texto)
        os.replace(tmp, ruta_fichero)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _leer_yaml(ruta_fichero: Path) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa."""
    try:
        texto = ruta_fichero.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return datos


# --------------------------------------------------------------------------- #
# Normalizacion + CRUD del registro                                           #
# --------------------------------------------------------------------------- #


def _publico(datos: dict[str, Any], gen_id: str) -> dict[str, Any]:
    """Reconstruye el dict PUBLICO de una generacion (forma estable para la API/UI)."""
    metricas = datos.get("metricas")
    if not isinstance(metricas, dict) or not metricas:
        metricas = None
    resultado = datos.get("resultado")
    if not isinstance(resultado, dict) or not resultado:
        resultado = None

    def _str(clave: str) -> str:
        valor = datos.get(clave)
        return valor if isinstance(valor, str) else ""

    return {
        "id": gen_id,
        "tipo": _str("tipo"),
        "marca": _str("marca"),
        "etiqueta": _str("etiqueta"),
        "estado": _str("estado"),
        "motivo": _str("motivo"),
        "salida": _str("salida"),
        "error": _str("error"),
        "metricas": metricas,
        "resultado": resultado,
        "fecha_inicio": _str("fecha_inicio"),
        "fecha_fin": _str("fecha_fin"),
    }


def crear(datos: dict[str, Any]) -> dict[str, Any]:
    """Crea un registro de generacion y lo escribe (atomico). Devuelve el dict publico.

    `datos` debe traer al menos `tipo`, `marca`, `etiqueta`. Si no trae `id`/`estado`/
    `fecha_inicio`, se rellenan (`estado="ejecutando"`, fecha = ahora).
    """
    gen_id = datos.get("id") or nuevo_id()
    completo = {
        "estado": ESTADO_EJECUTANDO,
        "fecha_inicio": ahora_iso(),
        **datos,
        "id": gen_id,
    }
    pub = _publico(completo, gen_id)
    _escribir_yaml_atomico(_ruta(gen_id), _cuerpo(pub))
    return pub


def actualizar(gen_id: str, cambios: dict[str, Any]) -> dict[str, Any]:
    """Mezcla `cambios` sobre el registro existente y lo reescribe (atomico)."""
    ruta_fichero = _ruta(gen_id)
    actual = _leer_yaml(ruta_fichero) or {}
    fusion = {**actual, **cambios}
    pub = _publico(fusion, gen_id)
    _escribir_yaml_atomico(ruta_fichero, _cuerpo(pub))
    return pub


def _cuerpo(pub: dict[str, Any]) -> dict[str, Any]:
    """Cuerpo YAML de una generacion: el dict publico sin `id` y sin claves vacias."""
    return {
        k: v
        for k, v in pub.items()
        if k != "id" and v not in ("", None)
    }


def obtener(gen_id: str) -> dict[str, Any] | None:
    """Una generacion por id (None si no existe / id invalido / YAML corrupto)."""
    if not isinstance(gen_id, str) or not gen_id:
        return None
    try:
        ruta_fichero = _ruta(gen_id)
    except ValueError:
        return None
    if not ruta_fichero.is_file():
        return None
    datos = _leer_yaml(ruta_fichero)
    if datos is None:
        return None
    return _publico(datos, gen_id)


def listar(limite: int = _LISTADO_MAX) -> list[dict[str, Any]]:
    """Generaciones recientes primero (por `fecha_inicio` desc, luego id)."""
    base = raiz()
    if not base.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for ruta_fichero in base.glob("*.yaml"):
        if ruta_fichero.name.startswith(".tmp-"):
            continue
        datos = _leer_yaml(ruta_fichero)
        if datos is None:
            continue
        items.append(_publico(datos, ruta_fichero.stem))
    items.sort(key=lambda g: (g["fecha_inicio"], g["id"]), reverse=True)
    return items[: max(0, limite)]


# --------------------------------------------------------------------------- #
# Lanzador de trabajos de CLAUDE (stream-json + parciales) — INYECTABLE        #
# --------------------------------------------------------------------------- #

# `procesar(salida, metricas) -> dict`: parsea la salida final de claude y crea los
# artefactos (historial, publicaciones, hashtags…), devolviendo el `resultado` que se
# guarda en el registro. Corre en el hilo del trabajo al COMPLETARSE con exito.
Procesar = Callable[[str, Any], dict[str, Any]]


def _argv_claude(prompt: str) -> list[str]:
    """argv de `claude -p <prompt> --output-format stream-json --verbose
    --include-partial-messages [--effort N] [--max-budget-usd N]`.

    `--include-partial-messages` es lo que habilita el STREAMING token a token (eventos
    `stream_event`/`text_delta`). `--verbose` es obligatorio para stream-json. `--effort`
    se añade solo si hay un nivel guardado en preferencias (si no, el predeterminado del
    modelo). Sin shell.
    """
    from .api import skills  # import local: evita el ciclo generaciones<->api.skills

    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        *preferencias.arg_esfuerzo(),
        *skills._arg_presupuesto(),
    ]


def lanzar_job_claude(
    gen_id: str,
    *,
    prompt: str,
    cwd: Path,
    procesar: Procesar,
    dir_temporal: Path | None = None,
) -> None:
    """Lanza un trabajo de claude EN SEGUNDO PLANO (Popen + hilo lector). NO bloquea.

    El hilo lee el NDJSON (stream-json + parciales), persiste `salida` (texto en vivo) y
    metricas parciales en el registro, y al cerrar fija el estado terminal:
      - exito  -> `completado`, `resultado = procesar(texto_final, metricas_finales)`.
      - error/budget/timeout -> `error` (mensaje en espanol).
    Si `dir_temporal` viene (archivo subido), se borra al terminar. INYECTABLE: los tests
    reemplazan esta funcion por una fake que llama a `procesar` con una salida canned.
    """
    from .api import skills  # import local (ver _argv_claude)

    acumulador = skills.AcumuladorStream()
    timeout = _timeout()

    def _avance() -> None:
        try:
            actualizar(
                gen_id,
                {
                    "estado": ESTADO_EJECUTANDO,
                    "salida": acumulador.texto,
                    "metricas": skills.metricas_a_dict(acumulador.metricas_parciales()),
                },
            )
        except Exception:  # noqa: BLE001 -- el avance nunca debe romper el hilo
            pass

    def _finalizar(timed_out: bool, returncode: int | None) -> None:
        # OJO: el `dir_temporal` se borra al FINAL (no aqui), porque el post-procesado
        # `procesar` puede necesitar los ARCHIVOS que la skill dejo ahi: las skills de
        # imagen (estudio-imagen) escriben los .png derivados junto a la foto subida y
        # `procesar` los importa al media para previsualizarlos. Borrarlo antes los
        # perderia. La limpieza va en el `finally`, asi corre pase lo que pase.
        fecha_fin = ahora_iso()
        try:
            if timed_out:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "motivo": "timeout",
                    "error": f"El asistente tardó demasiado (más de {timeout} s) y se canceló.",
                    "metricas": skills.metricas_a_dict(acumulador.metricas_parciales()),
                    "fecha_fin": fecha_fin,
                })
                return
            if acumulador.error:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "error": acumulador.mensaje_error,
                    "fecha_fin": fecha_fin,
                })
                return
            if acumulador.terminado:
                try:
                    resultado = procesar(acumulador.texto, acumulador.final)
                except Exception:  # noqa: BLE001 -- fallo del post-procesado -> error claro
                    actualizar(gen_id, {
                        "estado": ESTADO_ERROR,
                        "error": "Se generó el contenido pero no se pudo procesar el resultado.",
                        "salida": acumulador.texto,
                        "metricas": skills.metricas_a_dict(acumulador.final),
                        "fecha_fin": fecha_fin,
                    })
                    return
                actualizar(gen_id, {
                    "estado": ESTADO_COMPLETADO, "salida": acumulador.texto,
                    "metricas": skills.metricas_a_dict(acumulador.final),
                    "resultado": resultado, "fecha_fin": fecha_fin,
                })
                return
            detalle = "El asistente terminó sin devolver un resultado."
            if returncode not in (0, None):
                detalle = "El asistente terminó con error."
            actualizar(gen_id, {
                "estado": ESTADO_ERROR, "error": detalle,
                "metricas": skills.metricas_a_dict(acumulador.metricas_parciales()),
                "fecha_fin": fecha_fin,
            })
        except Exception:  # noqa: BLE001 -- el cierre nunca debe propagar
            pass
        finally:
            # Limpieza del temporal de la subida: DESPUES de `procesar` (ver nota arriba).
            if dir_temporal is not None:
                shutil.rmtree(dir_temporal, ignore_errors=True)

    if shutil.which("claude") is None:
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        actualizar(gen_id, {
            "estado": ESTADO_ERROR,
            "error": (
                "No se encontró el asistente en este equipo. Instala Claude Code para "
                "generar desde la consola."
            ),
            "fecha_fin": ahora_iso(),
        })
        return

    try:
        proc = subprocess.Popen(  # noqa: S603 -- argv lista, sin shell; prompt como argumento
            _argv_claude(prompt),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except (OSError, ValueError):
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        actualizar(gen_id, {
            "estado": ESTADO_ERROR, "error": "No se pudo iniciar la generación.",
            "fecha_fin": ahora_iso(),
        })
        return

    def _ciclo() -> None:
        _leer_stream(proc, acumulador, _avance)
        timed_out = _esperar(proc, timeout)
        # Fijamos el estado terminal ANTES de soltar el handle: asi un sondeo que ya no ve
        # el handle nunca lee un estado "ejecutando" obsoleto.
        _finalizar(timed_out, proc.returncode)
        with _HANDLES_LOCK:
            _HANDLES.pop(gen_id, None)

    hilo = threading.Thread(target=_ciclo, name=f"gen-{gen_id}", daemon=True)
    with _HANDLES_LOCK:
        _HANDLES[gen_id] = {"proc": proc, "hilo": hilo}
    hilo.start()


# Cada cuanto (segundos) persistimos el avance: con parciales llegan MUCHOS eventos por
# segundo; throttlear evita martillear el disco sin perder la sensacion de "en vivo".
_THROTTLE_S = 0.4


def _leer_stream(proc: subprocess.Popen, acumulador: Any, on_avance: Callable[[], None]) -> None:
    """Hilo lector: alimenta el acumulador con el NDJSON y persiste el avance (throttled).

    Persiste al cambiar de turno (hito) o cada `_THROTTLE_S` s; nunca en la linea terminal
    (`result`), porque el cierre fija el estado final con la salida/metricas definitivas.
    """
    import time

    if proc.stdout is None:
        return
    ultimo = 0.0
    ultimo_turno = -1
    try:
        for linea in proc.stdout:
            acumulador.procesar_linea(linea)
            if acumulador.terminado:
                continue
            ahora = time.monotonic()
            if acumulador.turnos != ultimo_turno or (ahora - ultimo) >= _THROTTLE_S:
                ultimo, ultimo_turno = ahora, acumulador.turnos
                on_avance()
    except Exception:  # noqa: BLE001 -- el lector nunca propaga; el cierre fija el estado
        pass


def _esperar(proc: subprocess.Popen, timeout: int) -> bool:
    """Espera al proceso con wall-timeout; si lo supera lo mata y devuelve True (timeout)."""
    try:
        proc.wait(timeout=timeout)
        return False
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001 -- best-effort; ya marcamos timeout
            pass
        return True


# --------------------------------------------------------------------------- #
# Lanzador de trabajos de IMAGEN (HTTP a un proveedor) — INYECTABLE            #
# --------------------------------------------------------------------------- #


def lanzar_job_imagen(gen_id: str, *, generar: Callable[[], dict[str, Any]]) -> None:
    """Lanza un trabajo de imagen EN SEGUNDO PLANO (un hilo simple; sin Popen).

    `generar()` hace la llamada al proveedor y guarda la imagen, devolviendo el
    `resultado` (`{id, url}`). No es un stream: el registro pasa de `ejecutando` a
    `completado` (con `resultado`) o `error`. INYECTABLE para tests (sin red).
    """

    def _ciclo() -> None:
        try:
            resultado = generar()
        except Exception as e:  # noqa: BLE001 -- mensaje en espanol; sin traceback al cliente
            mensaje = str(e) if str(e) else "No se pudo generar la imagen."
            actualizar(gen_id, {"estado": ESTADO_ERROR, "error": mensaje, "fecha_fin": ahora_iso()})
        else:
            actualizar(gen_id, {
                "estado": ESTADO_COMPLETADO, "resultado": resultado, "fecha_fin": ahora_iso(),
            })
        # Soltamos el handle DESPUES de fijar el estado terminal (ver `lanzar_job_claude`).
        with _HANDLES_LOCK:
            _HANDLES.pop(gen_id, None)

    hilo = threading.Thread(target=_ciclo, name=f"gen-img-{gen_id}", daemon=True)
    with _HANDLES_LOCK:
        _HANDLES[gen_id] = {"hilo": hilo}
    hilo.start()

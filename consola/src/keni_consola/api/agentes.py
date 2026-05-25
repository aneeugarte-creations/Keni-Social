"""API Agentes: un agente = una marca = su carpeta (contexto + runs).

La Ola 2a dejo el contenido por MARCA en `<KENI_CONSOLA_RAIZ>/<marca>/`. Esta API
expone ese mismo espacio como un AGENTE: la lista de agentes ES la lista de marcas
del catalogo unico (`marcas.opciones()`); cada agente tiene su `CLAUDE.md`
(contexto principal), sub-contextos opcionales (`contexto/*.md`) y RUNS
(ejecuciones de un prompt en su carpeta, `runs/<id>.yaml`). La logica de dominio
(localizar/crear la carpeta, leer/escribir contexto y runs, todo DEFENSIVO) vive en
`consola.agentes`; aqui solo se orquestan los endpoints JSON.

NO hay "crear agente" arbitrario: los agentes SON las marcas. Cada endpoint valida
el `marca_id` contra el catalogo (404 si no existe); nunca se aceptan rutas crudas.

RUNS:
  - `headless`: corre `claude -p <prompt> --output-format stream-json --verbose` con
    cwd = carpeta del agente, EN SEGUNDO PLANO (subprocess.Popen + un hilo lector que
    parsea el NDJSON). El POST devuelve de INMEDIATO con `estado="ejecutando"`; el hilo
    actualiza el YAML del run de forma incremental y atomica (metricas parciales
    mientras corre; `completado`/`error` al terminar). El YAML es la FUENTE DE VERDAD
    para el sondeo (`GET .../runs/{id}`). El lanzador (`lanzar_run_background`) es una
    funcion modulo-nivel INYECTABLE: los tests la parchean por una fake que escribe
    estados/medidas SIN Popen ni red.
  - `interactivo`: delega en `lanzador.abrir_en_claude_code(carpeta, prompt=...)` y
    guarda el run con `estado="lanzado"`. El lanzador es inyectable (mock en tests).

SEGURIDAD: marca ∈ catalogo; escritura atomica y defensiva (dentro de la carpeta
del agente); sin shell=True; bind local; errores en espanol, sin tracebacks crudos.
NUNCA se llama a `claude` real en tests (se parchea `lanzar_run_background`/el lanzador).
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import agentes, lanzador, marcas
from .._http_json import leer_json
from . import skills

# Inyectable: el lanzador interactivo (como en `api.proyectos`). `crear_app(abrir=...)`
# lo reasigna; los tests pasan un mock para NO lanzar nada real.
abrir_en_claude_code = lanzador.abrir_en_claude_code

# Numero de runs recientes que devuelve el detalle del agente.
_RUNS_EN_DETALLE = 20

# Wall-timeout (segundos) de un run headless en background: si lo supera, matamos el
# Popen y marcamos el run en error con motivo "timeout".
_TIMEOUT_RUN_DEF = 600

# Registro EN MEMORIA de los runs en vuelo: run_id -> handle (Popen + hilo). El YAML
# del run es la fuente de verdad para el sondeo; esto solo permite cancelar/inspeccionar
# localmente. Concurrencia local: un proceso, varios hilos lectores.
_HANDLES: dict[str, dict[str, object]] = {}
_HANDLES_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _agente_o_404(marca_id: object) -> str | JSONResponse:
    """Valida el `marca_id` contra el catalogo; 404 JSON si no es una marca."""
    if not isinstance(marca_id, str) or not marca_id:
        return JSONResponse({"error": "Falta el identificador del agente."}, status_code=404)
    if not marcas.es_marca(marca_id):
        return JSONResponse({"error": "Agente (marca) no encontrado."}, status_code=404)
    return marca_id


# --------------------------------------------------------------------------- #
# Endpoints: listado / detalle                                                #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Lista los agentes (= marcas) con su resumen (sin materializar carpetas)."""
    return JSONResponse({"agentes": agentes.listar_agentes()})


async def detalle(request: Request) -> Response:
    """Detalle de un agente: CLAUDE.md + sub-contextos + runs recientes. 404 si no es marca."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    resumen = agentes.resumen_agente(marca_id)
    claude_md = agentes.leer_claude_md(marca_id)
    sub_contextos = agentes.listar_contextos(marca_id)  # nombre + contenido (la UI edita desde aquí)
    runs = agentes.listar_runs(marca_id)[:_RUNS_EN_DETALLE]
    runs_breves = [
        {
            "id": r["id"],
            "prompt": r["prompt"],
            "modo": r["modo"],
            "estado": r["estado"],
            "motivo": r.get("motivo", ""),
            "fecha_inicio": r["fecha_inicio"],
            "metricas": r.get("metricas"),
        }
        for r in runs
    ]
    return JSONResponse(
        {
            "id": marca_id,
            "nombre": resumen["nombre"],
            "ruta": resumen["ruta"],
            "claude_md": claude_md,
            "sub_contextos": sub_contextos,
            "runs": runs_breves,
        }
    )


# --------------------------------------------------------------------------- #
# Endpoints: CLAUDE.md                                                         #
# --------------------------------------------------------------------------- #


async def guardar_claude_md(request: Request) -> Response:
    """Escribe `<marca>/CLAUDE.md` (defensivo). JSON `{contenido}` -> `{mensaje}`."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    datos = await leer_json(request)
    contenido = datos.get("contenido")
    if not isinstance(contenido, str):
        return JSONResponse({"error": "Falta el contenido del CLAUDE.md."}, status_code=400)
    try:
        agentes.guardar_claude_md(marca_id, contenido)
    except (ValueError, OSError):
        return JSONResponse(
            {"error": "No se pudo guardar el CLAUDE.md del agente."}, status_code=400
        )
    return JSONResponse({"mensaje": "CLAUDE.md guardado."})


# --------------------------------------------------------------------------- #
# Endpoints: sub-contextos (`contexto/*.md`)                                  #
# --------------------------------------------------------------------------- #


async def listar_contextos(request: Request) -> Response:
    """Sub-contextos del agente con su contenido. -> `{sub_contextos:[{nombre, contenido}]}`."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    return JSONResponse({"sub_contextos": agentes.listar_contextos(marca_id)})


async def guardar_contexto(request: Request) -> Response:
    """Escribe un sub-contexto `*.md` (saneado, dentro de `contexto/`). JSON `{contenido}`."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    nombre = request.path_params.get("nombre")
    datos = await leer_json(request)
    contenido = datos.get("contenido")
    if not isinstance(contenido, str):
        return JSONResponse({"error": "Falta el contenido del contexto."}, status_code=400)
    try:
        agentes.guardar_contexto(marca_id, nombre, contenido)
    except agentes.NombreContextoInvalido as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except (ValueError, OSError):
        return JSONResponse({"error": "No se pudo guardar el contexto."}, status_code=400)
    return JSONResponse({"mensaje": "Contexto guardado."})


async def borrar_contexto(request: Request) -> Response:
    """Borra un sub-contexto del agente. -> `{mensaje}` (404 si no existe el fichero)."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    nombre = request.path_params.get("nombre")
    try:
        borrado = agentes.borrar_contexto(marca_id, nombre)
    except agentes.NombreContextoInvalido as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError:
        return JSONResponse({"error": "No se pudo borrar el contexto."}, status_code=400)
    if not borrado:
        return JSONResponse({"error": "No se encontró ese contexto."}, status_code=404)
    return JSONResponse({"mensaje": "Contexto borrado."})


# --------------------------------------------------------------------------- #
# Endpoints: runs                                                             #
# --------------------------------------------------------------------------- #


def _argv_stream(prompt: str) -> list[str]:
    """argv de `claude -p <prompt> --output-format stream-json --verbose [--max-budget-usd N]`.

    `--verbose` es OBLIGATORIO para que `stream-json` emita los eventos por linea.
    Reutiliza `skills._arg_presupuesto` para el tope `--max-budget-usd` (de
    `KENI_CLAUDE_MAX_USD`). Sin shell: el prompt viaja como argumento de la lista argv.
    """
    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        *skills._arg_presupuesto(),
    ]


def _leer_stream(
    marca_id: str, run_id: str, proc: subprocess.Popen, acumulador: skills.AcumuladorStream
) -> None:
    """Hilo lector: parsea el NDJSON de `proc.stdout` linea a linea y avanza el YAML.

    Por cada linea actualiza el acumulador y persiste `estado="ejecutando"` con las
    metricas PARCIALES (turnos/tokens hasta ahora). Es la fuente de verdad del sondeo.
    Tolerante: una linea no JSON se ignora; cualquier fallo se refleja como run en error
    (en espanol), nunca un traceback crudo.
    """
    try:
        if proc.stdout is not None:
            for linea in proc.stdout:
                acumulador.procesar_linea(linea)
                if acumulador.terminado:
                    continue
                agentes.actualizar_run(
                    marca_id,
                    run_id,
                    {
                        "estado": "ejecutando",
                        "metricas": skills.metricas_a_dict(acumulador.metricas_parciales()),
                    },
                )
    except Exception:  # noqa: BLE001 -- el lector nunca debe propagar; el cierre fija el estado
        pass


def _finalizar_run(
    marca_id: str, run_id: str, proc: subprocess.Popen, acumulador: skills.AcumuladorStream
) -> None:
    """Espera a que el Popen termine (con wall-timeout) y fija el estado TERMINAL del run.

    - timeout -> mata el proceso y marca `estado="error", motivo="timeout"`.
    - evento `result` de error -> `estado="error"` con el mensaje en espanol.
    - rc != 0 sin `result` -> `estado="error"` generico.
    - exito -> `estado="completado"`, `salida` = texto del `result`, metricas finales.
    """
    timed_out = False
    try:
        proc.wait(timeout=_TIMEOUT_RUN_DEF)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001 -- best-effort; ya marcamos error por timeout
            pass
    finally:
        with _HANDLES_LOCK:
            _HANDLES.pop(run_id, None)

    fecha_fin = agentes.ahora_iso()
    if timed_out:
        agentes.actualizar_run(
            marca_id, run_id,
            {
                "estado": "error",
                "motivo": "timeout",
                "salida": f"El asistente tardó demasiado (más de {_TIMEOUT_RUN_DEF} s) y se canceló.",
                "metricas": skills.metricas_a_dict(acumulador.metricas_parciales()),
                "fecha_fin": fecha_fin,
            },
        )
        return

    if acumulador.error:
        agentes.actualizar_run(
            marca_id, run_id,
            {"estado": "error", "salida": acumulador.mensaje_error, "fecha_fin": fecha_fin},
        )
        return

    if acumulador.terminado:
        agentes.actualizar_run(
            marca_id, run_id,
            {
                "estado": "completado",
                "salida": acumulador.texto or "",
                "metricas": skills.metricas_a_dict(acumulador.final),
                "fecha_fin": fecha_fin,
            },
        )
        return

    # Termino sin un evento `result` (rc!=0, stream cortado, etc.).
    detalle = "El asistente terminó sin devolver un resultado."
    if proc.returncode not in (0, None):
        detalle = "El asistente terminó con error."
    agentes.actualizar_run(
        marca_id, run_id,
        {
            "estado": "error",
            "salida": detalle,
            "metricas": skills.metricas_a_dict(acumulador.metricas_parciales()),
            "fecha_fin": fecha_fin,
        },
    )


def lanzar_run_background(marca_id: str, run_id: str, prompt: str, *, cwd: Path) -> None:
    """Lanza el run headless EN SEGUNDO PLANO (Popen + hilo lector). NO bloquea.

    Esta es LA funcion que toca el binario `claude`; los tests la PARCHEAN por una fake
    que escribe estados/medidas en el YAML SIN Popen ni red. Si `claude` no esta o no se
    puede lanzar, degrada: marca el run en error (en espanol) sin romper. El hilo lee el
    NDJSON, persiste metricas parciales y, al cerrar, fija el estado terminal del run.
    """
    if shutil.which("claude") is None:
        agentes.actualizar_run(
            marca_id, run_id,
            {
                "estado": "error",
                "salida": (
                    "No se encontró el asistente en este equipo. Instala Claude Code para "
                    "ejecutar runs desde la consola."
                ),
                "fecha_fin": agentes.ahora_iso(),
            },
        )
        return
    try:
        proc = subprocess.Popen(  # noqa: S603 -- argv lista, sin shell; prompt como argumento
            _argv_stream(prompt),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except (OSError, ValueError):
        agentes.actualizar_run(
            marca_id, run_id,
            {
                "estado": "error",
                "salida": "No se pudo iniciar el run.",
                "fecha_fin": agentes.ahora_iso(),
            },
        )
        return

    acumulador = skills.AcumuladorStream()

    def _ciclo() -> None:
        _leer_stream(marca_id, run_id, proc, acumulador)
        _finalizar_run(marca_id, run_id, proc, acumulador)

    hilo = threading.Thread(target=_ciclo, name=f"run-{run_id}", daemon=True)
    with _HANDLES_LOCK:
        _HANDLES[run_id] = {"proc": proc, "hilo": hilo}
    hilo.start()


async def crear_run(request: Request) -> Response:
    """Lanza un run en la carpeta del agente. JSON `{prompt, modo}` -> el run | mensaje.

    - `headless`: lanza `claude` EN SEGUNDO PLANO (stream-json) y devuelve de INMEDIATO
      el run con `estado="ejecutando"` (no bloquea). El hilo lector avanza el YAML con
      metricas parciales y fija el estado terminal; el frontend SONDEA `GET .../runs/{id}`.
    - `interactivo`: abre Claude Code en la carpeta con el prompt como texto inicial,
      guarda el run con `estado="lanzado"` y devuelve un mensaje.
    """
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    datos = await leer_json(request)
    prompt = datos.get("prompt")
    modo = datos.get("modo", "headless")
    if not isinstance(prompt, str) or not prompt.strip():
        return JSONResponse({"error": "Falta el prompt del run."}, status_code=400)
    if modo not in agentes.MODOS_RUN:
        return JSONResponse(
            {"error": "Modo de run no permitido (usa 'headless' o 'interactivo')."},
            status_code=400,
        )
    prompt = prompt.strip()
    carpeta = agentes.carpeta_agente(marca_id)
    fecha_inicio = agentes.ahora_iso()

    if modo == "interactivo":
        try:
            mensaje = abrir_en_claude_code(carpeta, prompt=prompt)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        run = agentes.guardar_run(
            marca_id,
            {
                "prompt": prompt,
                "modo": "interactivo",
                "estado": "lanzado",
                "salida": "",
                "fecha_inicio": fecha_inicio,
                "fecha_fin": agentes.ahora_iso(),
            },
        )
        return JSONResponse({"mensaje": mensaje, "run": run})

    # headless: persiste el run como "ejecutando" y lanza el background ANTES de
    # responder. El POST no bloquea: el hilo lector avanza el YAML (fuente de verdad).
    run_id = agentes.nuevo_run_id()
    run = agentes.guardar_run(
        marca_id,
        {
            "id": run_id,
            "prompt": prompt,
            "modo": "headless",
            "estado": "ejecutando",
            "salida": "",
            "fecha_inicio": fecha_inicio,
            "fecha_fin": "",
        },
    )
    try:
        lanzar_run_background(marca_id, run_id, prompt, cwd=carpeta)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; reflejamos error en el run
        run = agentes.actualizar_run(
            marca_id, run_id,
            {
                "estado": "error",
                "salida": "No se pudo iniciar el run.",
                "fecha_fin": agentes.ahora_iso(),
            },
        )
    # Devolvemos el estado ACTUAL del run (puede haber avanzado ya con un lanzador fake).
    actual = agentes.obtener_run(marca_id, run_id)
    return JSONResponse({"run": actual or run})


async def listar_runs(request: Request) -> Response:
    """Runs del agente (recientes primero). -> `{runs:[...]}`."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    return JSONResponse({"runs": agentes.listar_runs(marca_id)})


async def obtener_run(request: Request) -> Response:
    """Un run del agente por id (run completo). 404 si no existe."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    run_id = request.path_params.get("run_id")
    run = agentes.obtener_run(marca_id, run_id)
    if run is None:
        return JSONResponse({"error": "No se encontró ese run."}, status_code=404)
    return JSONResponse({"run": run})


# --------------------------------------------------------------------------- #
# Endpoints: monitorizacion de runs (global + agregados)                      #
# --------------------------------------------------------------------------- #


async def listar_runs_globales(request: Request) -> Response:
    """Runs de TODOS los agentes, recientes primero. -> `{runs:[...]}`.

    Cada run: `{id, agente, agente_nombre, prompt, modo, estado, fecha_inicio, metricas}`.
    """
    runs = [
        {
            "id": r["id"],
            "agente": r["agente"],
            "agente_nombre": r["agente_nombre"],
            "prompt": r["prompt"],
            "modo": r["modo"],
            "estado": r["estado"],
            "motivo": r.get("motivo", ""),
            "fecha_inicio": r["fecha_inicio"],
            "metricas": r.get("metricas"),
        }
        for r in agentes.listar_runs_globales()
    ]
    return JSONResponse({"runs": runs})


async def agregados_runs(request: Request) -> Response:
    """Totales de coste/tokens/runs: `{total, por_agente, por_dia}`."""
    return JSONResponse(agentes.agregados_runs())


RUTAS = [
    Route("/api/runs", listar_runs_globales, methods=["GET"]),
    Route("/api/runs/agregados", agregados_runs, methods=["GET"]),
    Route("/api/agentes", listar, methods=["GET"]),
    Route("/api/agentes/{agente_id}", detalle, methods=["GET"]),
    Route("/api/agentes/{agente_id}/claude-md", guardar_claude_md, methods=["PUT"]),
    Route("/api/agentes/{agente_id}/contextos", listar_contextos, methods=["GET"]),
    Route("/api/agentes/{agente_id}/contextos/{nombre}", guardar_contexto, methods=["PUT"]),
    Route("/api/agentes/{agente_id}/contextos/{nombre}", borrar_contexto, methods=["DELETE"]),
    Route("/api/agentes/{agente_id}/runs", crear_run, methods=["POST"]),
    Route("/api/agentes/{agente_id}/runs", listar_runs, methods=["GET"]),
    Route("/api/agentes/{agente_id}/runs/{run_id}", obtener_run, methods=["GET"]),
]

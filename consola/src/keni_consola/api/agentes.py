"""API Agentes: conjunto ABIERTO de agentes (marcas de serie + genericos).

La Ola 2a dejo el contenido por MARCA en `<KENI_CONSOLA_RAIZ>/<marca>/`. Esta API
expone ese espacio como AGENTES y abre el conjunto: las 5 MARCAS vienen de serie
(`es_marca=True`; producen copy/publicaciones/metricas; NO se borran ni se
renombran) y, ademas, se pueden CREAR/CONECTAR/RENOMBRAR/BORRAR agentes GENERICOS
(carpeta + manifiesto `.keni/agente.yaml` + CLAUDE.md + runs; `es_marca=False`).
Cada agente tiene su `CLAUDE.md` (contexto principal), sub-contextos opcionales
(`contexto/*.md`) y RUNS (`runs/<id>.yaml`). La logica de dominio (descubrir, crear,
conectar, renombrar, borrar, leer/escribir contexto y runs, todo DEFENSIVO) vive en
`consola.agentes`; aqui solo se orquestan los endpoints JSON.

Cada endpoint resuelve el `agente_id` contra el conjunto vivo (marca del catalogo O
generico con manifiesto): 404 si no resuelve. Nunca se aceptan rutas crudas; el slug
de un generico se deriva/valida en el dominio (anti-escape de `api.carpetas`).

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

from .. import agentes, lanzador, preferencias
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


def _agente_o_404(agente_id: object) -> str | JSONResponse:
    """Resuelve el `agente_id` contra el conjunto vivo (marca O generico); 404 JSON si no.

    Acepta TANTO un id de marca del catalogo COMO el slug de un agente generico ya
    registrado (con manifiesto `.keni/agente.yaml`). Nunca acepta rutas crudas: el
    dominio (`agentes.es_agente`) hace la validacion anti-escape contra la raiz.
    """
    if not isinstance(agente_id, str) or not agente_id:
        return JSONResponse({"error": "Falta el identificador del agente."}, status_code=404)
    if not agentes.es_agente(agente_id):
        return JSONResponse({"error": "Agente no encontrado."}, status_code=404)
    return agente_id


# --------------------------------------------------------------------------- #
# Endpoints: listado / detalle                                                #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Lista los agentes (marcas + genericos) con su resumen (sin materializar carpetas)."""
    return JSONResponse({"agentes": agentes.listar_agentes()})


async def crear(request: Request) -> Response:
    """Crea un agente GENERICO. JSON `{nombre, tipo?}` -> `{agente}` (400 si nombre/slug invalido).

    Deriva un slug seguro del nombre, crea la carpeta + manifiesto + CLAUDE.md desde la
    plantilla `tipo` (def "general"). 400 si el nombre esta vacio / no da slug valido o
    si el slug choca con una marca o con un agente/carpeta existente.
    """
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str):
        return JSONResponse({"error": "Falta el nombre del agente."}, status_code=400)
    tipo = datos.get("tipo")
    tipo = tipo if isinstance(tipo, str) else "general"
    try:
        agente = agentes.crear_agente(nombre, tipo)
    except (agentes.NombreAgenteInvalido, agentes.AgenteExistente) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError:
        return JSONResponse({"error": "No se pudo crear el agente."}, status_code=400)
    return JSONResponse({"agente": agente})


async def conectar(request: Request) -> Response:
    """Conecta una subcarpeta EXISTENTE de la raiz como agente generico.

    JSON `{carpeta}` -> `{agente}`. 400 si no existe bajo la raiz, ya es agente/marca,
    o si `carpeta` intenta escapar (solo el nombre de una subcarpeta, anti-traversal).
    """
    datos = await leer_json(request)
    carpeta = datos.get("carpeta")
    if not isinstance(carpeta, str):
        return JSONResponse({"error": "Falta la carpeta a conectar."}, status_code=400)
    try:
        agente = agentes.conectar_agente(carpeta)
    except (agentes.NombreAgenteInvalido, agentes.AgenteExistente) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError:
        return JSONResponse({"error": "No se pudo conectar la carpeta."}, status_code=400)
    return JSONResponse({"agente": agente})


async def renombrar(request: Request) -> Response:
    """Renombra el DISPLAY de un agente GENERICO. JSON `{nombre}` -> `{agente}`.

    400 si el agente es una marca, no existe, o el nombre queda vacio.
    """
    agente_id = request.path_params.get("agente_id")
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str):
        return JSONResponse({"error": "Falta el nuevo nombre del agente."}, status_code=400)
    try:
        agente = agentes.renombrar_agente(agente_id, nombre)
    except (agentes.OperacionNoPermitida, agentes.AgenteInvalido, agentes.NombreAgenteInvalido) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError:
        return JSONResponse({"error": "No se pudo renombrar el agente."}, status_code=400)
    return JSONResponse({"agente": agente})


async def borrar(request: Request) -> Response:
    """Borra un agente GENERICO (su carpeta). -> `{mensaje}`. 400 si es marca; 404 si no existe."""
    agente_id = request.path_params.get("agente_id")
    try:
        agentes.borrar_agente(agente_id)
    except agentes.OperacionNoPermitida as e:  # es una marca de serie -> 400
        return JSONResponse({"error": str(e)}, status_code=400)
    except agentes.AgenteInvalido:  # no es un generico registrado -> 404
        return JSONResponse({"error": "Agente no encontrado."}, status_code=404)
    except OSError:
        return JSONResponse({"error": "No se pudo borrar el agente."}, status_code=400)
    return JSONResponse({"mensaje": "Agente borrado."})


async def detalle(request: Request) -> Response:
    """Detalle de un agente: CLAUDE.md + sub-contextos + runs recientes. 404 si no resuelve."""
    agente_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(agente_id, JSONResponse):
        return agente_id
    resumen = agentes.resumen_agente(agente_id)
    claude_md = agentes.leer_claude_md(agente_id)
    sub_contextos = agentes.listar_contextos(agente_id)  # nombre + contenido (la UI edita desde aquí)
    runs = agentes.listar_runs(agente_id)[:_RUNS_EN_DETALLE]
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
            "id": agente_id,
            "nombre": resumen["nombre"],
            "ruta": resumen["ruta"],
            "es_marca": resumen["es_marca"],
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
    """argv de `claude -p <prompt> --output-format stream-json --verbose
    --include-partial-messages [--max-budget-usd N]`.

    `--verbose` es OBLIGATORIO para `stream-json`; `--include-partial-messages` habilita
    el STREAMING token a token (eventos `stream_event`/`text_delta`) para ver el texto en
    vivo. `--effort` se añade solo si hay un nivel guardado en preferencias. Reutiliza
    `skills._arg_presupuesto` para `--max-budget-usd` (de `KENI_CLAUDE_MAX_USD`). Sin
    shell: el prompt viaja como argumento de la lista argv.
    """
    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        *preferencias.arg_esfuerzo(),
        *skills._arg_presupuesto(),
    ]


# Cada cuanto (s) persistimos el avance: con parciales llegan muchos eventos por segundo;
# throttlear evita martillear el disco sin perder la sensacion de "en vivo".
_THROTTLE_S = 0.4


def _leer_stream(
    marca_id: str, run_id: str, proc: subprocess.Popen, acumulador: skills.AcumuladorStream
) -> None:
    """Hilo lector: parsea el NDJSON de `proc.stdout` linea a linea y avanza el YAML.

    Por cada avance persiste `estado="ejecutando"`, el TEXTO en vivo (`acumulador.texto`,
    que va creciendo token a token) y las metricas PARCIALES (turnos/tokens). Es la fuente
    de verdad del sondeo. Persiste al cambiar de turno (hito) o cada `_THROTTLE_S` s; nunca
    en la linea terminal (`result`): el cierre fija el estado final. Tolerante: una linea
    no JSON se ignora; cualquier fallo se traga (nunca un traceback crudo).
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
                agentes.actualizar_run(
                    marca_id,
                    run_id,
                    {
                        "estado": "ejecutando",
                        "salida": acumulador.texto,
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
    Route("/api/agentes", crear, methods=["POST"]),
    # `conectar` ANTES de `/{agente_id}` para que no lo capture el comodin del detalle.
    Route("/api/agentes/conectar", conectar, methods=["POST"]),
    Route("/api/agentes/{agente_id}", detalle, methods=["GET"]),
    Route("/api/agentes/{agente_id}", renombrar, methods=["PATCH"]),
    Route("/api/agentes/{agente_id}", borrar, methods=["DELETE"]),
    Route("/api/agentes/{agente_id}/claude-md", guardar_claude_md, methods=["PUT"]),
    Route("/api/agentes/{agente_id}/contextos", listar_contextos, methods=["GET"]),
    Route("/api/agentes/{agente_id}/contextos/{nombre}", guardar_contexto, methods=["PUT"]),
    Route("/api/agentes/{agente_id}/contextos/{nombre}", borrar_contexto, methods=["DELETE"]),
    Route("/api/agentes/{agente_id}/runs", crear_run, methods=["POST"]),
    Route("/api/agentes/{agente_id}/runs", listar_runs, methods=["GET"]),
    Route("/api/agentes/{agente_id}/runs/{run_id}", obtener_run, methods=["GET"]),
]

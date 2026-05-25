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
  - `headless`: corre `claude -p <prompt>` con cwd = carpeta del agente, reutilizando
    la MECANICA de `_runner` de `api.skills` (argv, timeout, sin shell; runner
    inyectable). Guarda el run con `estado` "completado"/"error" + `salida`.
  - `interactivo`: delega en `lanzador.abrir_en_claude_code(carpeta, prompt=...)` y
    guarda el run con `estado="lanzado"`. El lanzador es inyectable (mock en tests).

SEGURIDAD: marca ∈ catalogo; escritura atomica y defensiva (dentro de la carpeta
del agente); sin shell=True; errores en espanol, sin tracebacks crudos. NUNCA se
llama a `claude` real en tests (se parchea `_runner`/el lanzador).
"""

from __future__ import annotations

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
    sub_contextos = [{"nombre": c["nombre"]} for c in agentes.listar_contextos(marca_id)]
    runs = agentes.listar_runs(marca_id)[:_RUNS_EN_DETALLE]
    runs_breves = [
        {
            "id": r["id"],
            "prompt": r["prompt"],
            "modo": r["modo"],
            "estado": r["estado"],
            "fecha_inicio": r["fecha_inicio"],
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
    """Sub-contextos del agente con su contenido. -> `{contextos:[{nombre, contenido}]}`."""
    marca_id = _agente_o_404(request.path_params.get("agente_id"))
    if isinstance(marca_id, JSONResponse):
        return marca_id
    return JSONResponse({"contextos": agentes.listar_contextos(marca_id)})


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


def _ejecutar_headless(carpeta: Path, prompt: str) -> dict[str, str]:
    """Corre `claude -p <prompt>` con cwd = carpeta del agente (reusa `_runner` de skills).

    Llama a `skills._runner` POR REFERENCIA al modulo (no por nombre importado) para
    que los tests que parchean `skills._runner` surtan efecto y NUNCA toquen `claude`
    real. Devuelve `{estado, salida}`: "completado"+stdout si sale bien; "error"+mensaje
    en espanol si el asistente falla (binario ausente, timeout, rc!=0). No relanza.
    """
    try:
        salida = skills._runner(prompt, cwd=carpeta, timeout=skills._TIMEOUT_DEF)
    except skills.SkillError as e:
        return {"estado": "error", "salida": str(e)}
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; lo reflejamos como error del run
        return {"estado": "error", "salida": "No se pudo ejecutar el run."}
    return {"estado": "completado", "salida": salida or ""}


async def crear_run(request: Request) -> Response:
    """Lanza un run en la carpeta del agente. JSON `{prompt, modo}` -> el run | mensaje.

    - `headless`: corre `claude -p <prompt>` (cwd = carpeta), guarda el run con
      `estado` "completado"/"error" + `salida`, y lo devuelve.
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

    # headless
    resultado = _ejecutar_headless(carpeta, prompt)
    run = agentes.guardar_run(
        marca_id,
        {
            "prompt": prompt,
            "modo": "headless",
            "estado": resultado["estado"],
            "salida": resultado["salida"],
            "fecha_inicio": fecha_inicio,
            "fecha_fin": agentes.ahora_iso(),
        },
    )
    return JSONResponse({"run": run})


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


RUTAS = [
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

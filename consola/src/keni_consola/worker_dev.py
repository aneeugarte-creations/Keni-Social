"""WORKER de AUTO-DESARROLLO: carril `dev` de la cola, `claude -p` SIN sandbox sobre el repo.

Gemelo de `worker.py` (NO lo edita) pero para el carril `dev`: reclama SOLO jobs cuyo
`jobspec.carril(spec) == "dev"` y, en vez de correr `claude` en un cwd neutro con las
herramientas vetadas, lo corre con permisos AMPLIOS (Bash/Write/Edit) sobre un WORKTREE git
por sugerencia, para que el agente pueda leer y modificar código.

Ciclo de un job dev:
  1. Asegura un worktree+rama por sugerencia (`dev/sug-<id>`) creado desde `origin/main`.
  2. Corre `claude -p` (no sandbox) con el modelo de la fase, cwd = worktree.
  3. Reconstruye el post-procesado del spec (`jobspec.reconstruir_procesar`) y lo aplica:
     actualiza la fila `sugerencias` (SPEC/plan/diff/estado).
  4. Encadena la siguiente fase del pipeline si la sugerencia sigue en `building` (no llegó a
     un checkpoint humano).

Pool de `KENI_MAX_JOBS_DEV` hilos (def 2). Entry-point: `python -m keni_consola.worker_dev`.
El worker de CONTENIDO (`worker.py`) EXCLUYE el carril `dev` al reclamar (lo cabla el
orquestador); ver el informe de BACK-DEV para el fragmento exacto.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from . import cola, config, generaciones, sugerencias
from .dominio import desarrollo, jobspec

_log = logging.getLogger("keni_consola.worker_dev")

# Carriles que ESTE worker reclama: solo desarrollo (jamás contenido).
_CARRILES_DEV: set[str] = {jobspec.CARRIL_DEV}


def _max_jobs_dev() -> int:
    """Cupo de hilos del carril dev (`KENI_MAX_JOBS_DEV`, def 2, mínimo 1)."""
    crudo = os.environ.get("KENI_MAX_JOBS_DEV")
    if crudo is None:
        return 2
    try:
        return max(1, int(str(crudo).strip()))
    except (TypeError, ValueError):
        return 2


def _repo() -> Path:
    """Clon git del repo sobre el que trabaja el motor (`KENI_DEV_REPO`, def `/repo`)."""
    return Path(os.environ.get("KENI_DEV_REPO", "/repo"))


def _dir_worktrees() -> Path:
    """Directorio donde viven los worktrees por sugerencia (junto al repo)."""
    d = _repo().parent / "keni-dev-worktrees"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _git(*args: str, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Corre `git` y devuelve el proceso completado (sin lanzar; el llamante decide)."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True, text=True, timeout=timeout,
    )


def _asegurar_worktree(sugerencia_id: str) -> tuple[Path, str]:
    """Crea (o reutiliza) el worktree+rama de una sugerencia. Devuelve `(worktree, rama)`.

    La rama `dev/sug-<id>` nace de `origin/main` fresco. Si el worktree ya existe, se reutiliza
    (las fases del pipeline trabajan sobre el MISMO árbol acumulando el cambio).
    """
    repo = _repo()
    rama = f"dev/sug-{sugerencia_id}"
    wt = _dir_worktrees() / f"sug-{sugerencia_id}"
    if wt.is_dir():
        return wt, rama
    _git("fetch", "origin", "main", cwd=repo)
    res = _git("worktree", "add", "-B", rama, str(wt), "origin/main", cwd=repo)
    if res.returncode != 0:
        _log.error("worker_dev: no se pudo crear el worktree de %s: %s", sugerencia_id, res.stderr)
        raise RuntimeError("no se pudo preparar el worktree de desarrollo")
    return wt, rama


def _diff_resumen(worktree: Path) -> str:
    """Resumen (`--stat`) del cambio del worktree frente a `origin/main`. Best-effort."""
    res = _git("diff", "origin/main", "--stat", cwd=worktree)
    return (res.stdout or "").strip()


def _argv_claude(prompt: str, modelo: str) -> list[str]:
    """argv de `claude -p` SIN sandbox: permisos amplios, sin `--disallowed-tools`.

    A diferencia del worker de contenido, el agente de desarrollo SÍ necesita Bash/Write/Edit
    (leer y modificar código). Usa `--output-format json` (un único objeto de resultado al
    final, fácil de parsear) y `--model` el de la fase.
    """
    argv = ["claude", "-p", prompt, "--output-format", "json", "--verbose"]
    if config.claude_skip_permisos():
        argv.append("--dangerously-skip-permissions")
    if modelo:
        argv += ["--model", modelo]
    return argv


def _correr_claude(prompt: str, cwd: Path, modelo: str) -> tuple[str, float, bool]:
    """Corre `claude -p` en `cwd` y devuelve `(texto, coste_usd, ok)`.

    Parsea el JSON de `--output-format json` (`result`/`total_cost_usd`); si no es JSON
    legible, cae al stdout crudo. `ok` refleja el returncode del proceso.
    """
    try:
        proc = subprocess.run(
            _argv_claude(prompt, modelo),
            cwd=str(cwd), capture_output=True, text=True,
            timeout=config.claude_timeout(),
        )
    except subprocess.TimeoutExpired:
        return ("La fase de desarrollo superó el tiempo máximo.", 0.0, False)
    salida = proc.stdout or ""
    texto, coste = salida.strip(), 0.0
    try:
        datos = json.loads(salida)
        if isinstance(datos, dict):
            texto = str(datos.get("result") or "").strip() or texto
            coste = float(datos.get("total_cost_usd") or 0)
    except (ValueError, TypeError):
        pass
    return (texto, coste, proc.returncode == 0)


def _procesar_job(job: dict) -> None:
    """Ejecuta UN job dev ya clavado: worktree → claude → post-procesado → encadenado."""
    job_id, gen_id, spec = job["id"], job["gen_id"], job.get("spec")
    if not isinstance(spec, dict):
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar la fase de desarrollo.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        cola.terminar(job_id)
        return

    p = spec.get("procesar") or {}
    kind = p.get("kind", "")
    sugerencia_id = p.get("sugerencia_id", "")
    fase = p.get("fase", "")
    modelo = p.get("modelo", "")
    prompt = spec.get("prompt", "")
    try:
        worktree, rama = _asegurar_worktree(sugerencia_id)
        sugerencias.actualizar_avance(
            sugerencia_id, {"rama": rama, "worktree": str(worktree)}
        )
        texto, coste, ok = _correr_claude(prompt, worktree, modelo)
        procesar = jobspec.reconstruir_procesar(spec)
        procesar(texto, None)
        # Diff real del worktree para las fases que construyen/revisan, y acumula coste.
        avance: dict[str, object] = {}
        if kind == jobspec.PROC_DEV_FASE and fase in (desarrollo.FASE_BUILD, desarrollo.FASE_REVIEW):
            avance["diff_resumen"] = _diff_resumen(worktree)
        if coste:
            sug = sugerencias.obtener(sugerencia_id) or {}
            avance["coste_usd"] = float(sug.get("coste_usd") or 0) + coste
        if avance:
            sugerencias.actualizar_avance(sugerencia_id, avance)
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_COMPLETADO if ok else generaciones.ESTADO_ERROR,
            "salida": texto,
            "error": "" if ok else "La fase de desarrollo terminó con error.",
            "fecha_fin": generaciones.ahora_iso(),
        })
    except Exception:  # noqa: BLE001 -- fallo de la fase: error claro, sin traceback al cliente
        _log.exception("worker_dev: falló la fase %s de la sugerencia %s", fase, sugerencia_id)
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_ERROR, "error": "No se pudo completar la fase de desarrollo.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        if kind == jobspec.PROC_DEV_FASE and sugerencia_id:
            try:
                sugerencias.cambiar_estado(sugerencia_id, "fallida")
            except sugerencias.TransicionInvalida:
                pass
        cola.terminar(job_id)
        return
    cola.terminar(job_id)

    # ENCADENADO: si una fase terminó y el pipeline sigue (estado `building`, no checkpoint),
    # lanza la siguiente fase. El discovery NO encadena (lo dispara una persona vía /construir).
    if kind == jobspec.PROC_DEV_FASE and sugerencia_id:
        sug = sugerencias.obtener(sugerencia_id)
        if sug is not None and sug["estado"] == "building":
            siguiente = desarrollo.siguiente_fase(sug.get("complejidad", ""), fase)
            if siguiente is not None:
                try:
                    sugerencias.lanzar_fase(sugerencia_id, siguiente)
                except Exception:  # noqa: BLE001 -- el encadenado nunca rompe el cierre del job
                    _log.exception("worker_dev: no se pudo encadenar la fase tras %s", fase)


def _bucle(parar: threading.Event, worker_id: str) -> None:
    """Bucle de un hilo del pool dev: reclama un job del carril `dev` y lo procesa."""
    sondeo = config.worker_sondeo_segundos()
    while not parar.is_set():
        try:
            job = cola.reclamar(worker_id, carriles=_CARRILES_DEV)
        except Exception:  # noqa: BLE001 -- un fallo de la cola no debe matar el worker
            _log.exception("worker_dev: fallo al reclamar un job dev")
            if parar.wait(sondeo):
                return
            continue
        if job is None:
            if parar.wait(sondeo):
                return
            continue
        if parar.is_set():
            return
        try:
            _procesar_job(job)
        except Exception:  # noqa: BLE001 -- un fallo de UN job no debe matar el worker
            _log.exception("worker_dev: fallo al procesar el job %s", job.get("id"))


def main() -> int:
    """Entry-point del servicio `worker-dev`: corre el POOL hasta SIGTERM/Ctrl-C."""
    from .observabilidad import configurar_logging

    configurar_logging()
    from . import repos

    repos.arrancar_persistencia()

    parar = threading.Event()
    hilos = [
        threading.Thread(
            target=_bucle, args=(parar, f"dev-{uuid.uuid4().hex[:8]}"),
            name=f"worker-dev-{i}", daemon=True,
        )
        for i in range(_max_jobs_dev())
    ]

    def _al_apagar(signum: int, _frame: object) -> None:
        _log.warning("worker_dev: señal de apagado %s recibida; deteniendo el pool", signum)
        parar.set()

    signal.signal(signal.SIGTERM, _al_apagar)
    signal.signal(signal.SIGINT, _al_apagar)
    for h in hilos:
        h.start()
    _log.info("worker_dev iniciado: pool de %d hilos (carril dev).", len(hilos))
    try:
        while not parar.wait(timeout=1.0):
            pass
    except (KeyboardInterrupt, SystemExit):
        parar.set()
    for h in hilos:
        h.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

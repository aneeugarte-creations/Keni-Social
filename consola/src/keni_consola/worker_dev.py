"""WORKER de AUTO-DESARROLLO: carril `dev` de la cola, `claude -p` SIN sandbox sobre el repo.

Gemelo de `worker.py` (NO lo edita) pero para el carril `dev`: reclama SOLO jobs cuyo
`jobspec.carril(spec) == "dev"` y, en vez de correr `claude` en un cwd neutro con las
herramientas vetadas, lo corre con permisos AMPLIOS (Bash/Write/Edit) sobre un WORKTREE git
por sugerencia, para que el agente pueda leer y modificar código.

Ciclo de un job dev:
  1. Asegura el clon `/repo` (lo clona con `gh` si falta) y un worktree+rama por sugerencia
     (`dev/sug-<id>`) creado desde `origin/main`.
  2. Corre `claude -p` (no sandbox) con el modelo de la fase, cwd = worktree, en STREAMING
     token a token (`--output-format stream-json --include-partial-messages`): el avance
     parcial se persiste en el registro de la generación igual que un copy (acumulador +
     callback throttled), con vigía de cancelación cross-proceso y reintentos de transitorios.
  3. Reconstruye el post-procesado del spec (`jobspec.reconstruir_procesar`) y lo aplica:
     actualiza la fila `sugerencias` (SPEC/plan/diff/estado).
  4. Encadena la siguiente fase del pipeline si la sugerencia sigue en `building` (no llegó a
     un checkpoint humano).

Además levanta un LISTENER de control (`dev_control`) en `KENI_DEV_PORT` (def 8772) para la
PROMOCIÓN REAL a `main` (`promover_sugerencia`): el `back` lo proxea admin-gated.

Pool de `KENI_MAX_JOBS_DEV` hilos (def 2). Entry-point: `python -m keni_consola.worker_dev`.
El worker de CONTENIDO (`worker.py`) EXCLUYE el carril `dev` al reclamar.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import signal
import subprocess
import threading
import uuid
from pathlib import Path

from . import almacen_media, cola, config, generaciones, presupuesto_ia, sugerencias
from .dominio import desarrollo, jobspec, runner, stream
from .generaciones import _lanzadores as _gl

_log = logging.getLogger("keni_consola.worker_dev")

# Carriles que ESTE worker reclama: solo desarrollo (jamás contenido).
_CARRILES_DEV: set[str] = {jobspec.CARRIL_DEV}

# Prefijo de los bundles de preview en el almacen de media (`previews/sug-<id>/...`).
_PREFIJO_PREVIEW = "previews/"

# Estados de los que YA no nace trabajo: el reaper puede limpiar sus restos sin riesgo.
_ESTADOS_TERMINALES_DEV: set[str] = {"hecha", "descartada"}

# Cada cuanto barre el reaper de fondo restos de sugerencias terminadas (s).
_INTERVALO_REAPER_S = 600.0

# Repositorio que el carril dev clona/empuja (slug de GitHub).
_REPO_SLUG = "kenitech-io/keni-social"

# Cuanto sondea el vigía de cancelación el flag de la cola (s): mismo equilibrio que `worker.py`.
_SONDEO_CANCELACION_S = 1.5

# Tope del backoff del sondeo de la cola cuando lleva vacía / cortada por presupuesto (s).
_SONDEO_MAX_S = 5.0


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
    return Path(os.environ.get("KENI_DEV_REPO", config.dev_repo()))


def _dir_worktrees() -> Path:
    """Directorio ESCRIBIBLE donde viven los worktrees por sugerencia.

    `$KENI_DATA_DIR/dev-worktrees` en el servidor (el padre de `/repo` es la raíz, no escribible
    por el uid no-root); junto al repo si no hay `KENI_DATA_DIR` (tests/local)."""
    raiz = os.environ.get("KENI_DATA_DIR")
    base = (Path(raiz) / "dev-worktrees") if raiz else (_repo().parent / "keni-dev-worktrees")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _git(*args: str, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Corre `git` y devuelve el proceso completado (sin lanzar; el llamante decide)."""
    return subprocess.run(  # noqa: S603 -- argv lista, sin shell
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True, text=True, timeout=timeout,
    )


# --------------------------------------------------------------------------- #
# Siembra del clon + credenciales git (gh)                                     #
# --------------------------------------------------------------------------- #


def _setup_git_credenciales() -> None:
    """`gh auth setup-git`: que `git push` use la credencial de la cuenta gh de la maquina.

    Best-effort: tolera que `gh` aún no esté conectado/instalado (el panel Sistema conecta la
    cuenta más tarde; al promover se vuelve a intentar). Idempotente."""
    try:
        res = subprocess.run(  # noqa: S603 -- argv lista, sin shell
            ["gh", "auth", "setup-git"], capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("worker_dev: gh auth setup-git no disponible aún: %s", e)
        return
    if res.returncode != 0:
        _log.warning("worker_dev: gh auth setup-git devolvió error: %s", (res.stderr or "").strip())


def _es_repo_git(repo: Path) -> bool:
    """True si `repo` es un clon git utilizable (tiene `.git`)."""
    return (repo / ".git").exists()


def _asegurar_repo(repo: Path) -> None:
    """Asegura que `/repo` sea un clon git; si falta, lo clona con `gh` (perezoso).

    Best-effort en arranque, pero AL CREAR EL PRIMER WORKTREE es necesario: si el clon no se
    puede materializar (gh aún no conectado), SUBE la excepción para que el job quede en error
    legible en vez de fallar oscuramente en `git worktree add`."""
    if _es_repo_git(repo):
        return
    _setup_git_credenciales()
    repo.parent.mkdir(parents=True, exist_ok=True)
    try:
        res = subprocess.run(  # noqa: S603 -- argv lista, sin shell
            ["gh", "repo", "clone", _REPO_SLUG, str(repo)],
            capture_output=True, text=True, timeout=600,
        )
    except FileNotFoundError as e:
        raise RuntimeError("gh no está disponible para clonar el repositorio") from e
    except subprocess.SubprocessError as e:
        raise RuntimeError(f"no se pudo clonar el repositorio: {e}") from e
    if res.returncode != 0 or not _es_repo_git(repo):
        detalle = (res.stderr or res.stdout or "").strip()[:200]
        raise RuntimeError(
            "no se pudo clonar el repositorio (¿está conectada la cuenta de GitHub?): "
            + (detalle or "fallo de gh")
        )


def _arbol_limpio(worktree: Path) -> bool:
    """True si el worktree no tiene cambios sin commitear (seguro para rebasar)."""
    res = _git("status", "--porcelain", cwd=worktree)
    return res.returncode == 0 and not (res.stdout or "").strip()


_PROMPT_RESOLVER_REBASE = (
    "Estás dentro de un `git rebase origin/main` PAUSADO por conflictos en este repositorio git. "
    "Resuélvelos tú: por cada fichero en conflicto, edítalo conservando la intención de AMBOS "
    "lados (el cambio de esta rama y el de main) y quita los marcadores "
    "`<<<<<<<`/`=======`/`>>>>>>>`; luego `git add` los ficheros resueltos y `git rebase "
    "--continue`. Repite hasta que el rebase TERMINE del todo. NO hagas `git push` ni "
    "`git rebase --abort`. Mantén verdes los tests que toques."
)


def _resolver_rebase_con_agente(worktree: Path, modelo: str = "sonnet") -> bool:
    """Lanza `claude -p` (Sonnet) para resolver un `git rebase origin/main` PAUSADO por conflictos.

    El agente edita los ficheros en conflicto conservando ambas intenciones, hace `git add` y
    `git rebase --continue` hasta terminar (sin push ni abort). No streaming, acotado por el
    wall-timeout de claude. Devuelve True SOLO si tras correr quedó un rebase COMPLETO y limpio
    sobre origin/main. Best-effort: cualquier fallo (no arranca, timeout, sin resolver) -> False.
    """
    argv = ["claude", "-p", _PROMPT_RESOLVER_REBASE]
    if config.claude_skip_permisos():
        argv.append("--dangerously-skip-permissions")
    if modelo:
        argv += ["--model", modelo]
    try:
        subprocess.run(  # noqa: S603 -- argv lista, sin shell
            argv, cwd=str(worktree), capture_output=True, text=True,
            timeout=config.claude_timeout(), env=_gl._entorno_generacion(),
        )
    except (OSError, subprocess.SubprocessError):
        _log.warning("worker_dev: el agente de resolución de conflictos falló o agotó el tiempo", exc_info=True)
    # Éxito SOLO si el rebase quedó completo (origin/main es ancestro de HEAD) y el árbol limpio
    # (sin ficheros sin mergear ni rebase a medias).
    en_main = _git("merge-base", "--is-ancestor", "origin/main", "HEAD", cwd=worktree).returncode == 0
    return en_main and _arbol_limpio(worktree)


def _rebasar_sobre_main(worktree: Path, *, resolver_conflictos: bool = False) -> tuple[bool, str]:
    """fetch `origin main` + rebase `origin/main` dentro de `worktree`. No lanza.

    La misma disciplina que `scripts/promover-main.sh`: traer lo último de main y rebasar encima
    ANTES de empujar/construir, para que la rama nunca quede vieja. La credencial gh la cablea el
    llamante. Devuelve `(True, "")` si la rama quedó sobre origin/main.

    En conflicto: si `resolver_conflictos`, un agente Opus intenta resolverlo (lo usa la
    promoción, para que «meter a main» nunca falle por una rama vieja); si no lo logra (o no se
    pidió agente) hace `rebase --abort` y devuelve `(False, motivo)`.
    """
    fetch = _git("fetch", "origin", "main", cwd=worktree)
    if fetch.returncode != 0:
        return False, f"No se pudo actualizar desde origin: {(fetch.stderr or '').strip()[:200]}"
    rebase = _git("rebase", "origin/main", cwd=worktree)
    if rebase.returncode == 0:
        return True, ""
    if resolver_conflictos and _resolver_rebase_con_agente(worktree):
        return True, "Conflictos de rebase resueltos por un agente Opus."
    _git("rebase", "--abort", cwd=worktree)
    return False, "El rebase sobre origin/main tiene conflictos que no se pudieron resolver."


def _asegurar_worktree(sugerencia_id: str) -> tuple[Path, str]:
    """Crea (o reutiliza) el worktree+rama de una sugerencia. Devuelve `(worktree, rama)`.

    La rama `dev/sug-<id>` nace de `origin/main` fresco. Si el worktree ya existe, se reutiliza
    (las fases del pipeline trabajan sobre el MISMO árbol acumulando el cambio) y se REBASA sobre
    `origin/main` antes de seguir: «pull siempre», para que ninguna fase parta de una rama vieja
    (la causa de previews/promociones que fallan). Best-effort: solo si el árbol está limpio
    (los agentes commitean su trabajo), y un conflicto/fallo no bloquea la fase —se loguea y se
    sigue; el rebase manual y la guardia de la promoción cubren el resto.
    """
    repo = _repo()
    _asegurar_repo(repo)
    rama = f"dev/sug-{sugerencia_id}"
    wt = _dir_worktrees() / f"sug-{sugerencia_id}"
    if wt.is_dir():
        if _arbol_limpio(wt):
            _setup_git_credenciales()
            ok, detalle = _rebasar_sobre_main(wt)
            if not ok:
                _log.warning("worker_dev: no se pudo rebasar el worktree de %s: %s", sugerencia_id, detalle)
        else:
            _log.info("worker_dev: worktree de %s con cambios sin commitear; no rebaso", sugerencia_id)
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


def _correr_cmd(argv: list[str], *, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """Corre un comando (npm/npx) y devuelve el proceso. Helper aparte de `_git` para parchearlo en tests."""
    return subprocess.run(  # noqa: S603 -- argv lista, sin shell
        argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
    )


def _construir_preview(worktree: Path, sugerencia_id: str) -> bool:
    """Compila el frontend de la rama y sube el bundle a `previews/sug-<id>/`. Devuelve si quedo listo.

    El bundle se compila con `base=/api/preview/<id>/` para que sus assets y su cliente API
    cuelguen de ese prefijo (lo sirve `api/preview.py`, que mapea ese `<id>` a la clave de
    almacen `previews/sug-<id>/`). NO lanza: un fallo de build/instalacion se loguea y devuelve
    False (el preview es un extra, no debe tumbar la fase). Reupload limpio: borra el prefijo
    antes de subir para que un bundle que encoge no deje assets viejos.
    """
    front = worktree / "consola" / "frontend"
    if not (front / "package.json").is_file():
        return False
    salida = front / "dist-preview"
    base = f"/api/preview/{sugerencia_id}/"
    try:
        if not (front / "node_modules").is_dir():
            dep = _correr_cmd(["npm", "ci", "--prefer-offline", "--no-audit"], cwd=front, timeout=1200)
            if dep.returncode != 0:
                _log.warning("preview: npm ci falló (%s): %s", sugerencia_id, (dep.stderr or "")[:300])
                return False
        build = _correr_cmd(
            ["npx", "vite", "build", "--base", base, "--outDir", str(salida), "--emptyOutDir"],
            cwd=front, timeout=900,
        )
        if build.returncode != 0:
            _log.warning("preview: vite build falló (%s): %s", sugerencia_id, (build.stderr or "")[:300])
            return False
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("preview: no se pudo construir el bundle de %s: %s", sugerencia_id, e)
        return False

    almacen_media.borrar_prefijo(f"{_PREFIJO_PREVIEW}sug-{sugerencia_id}/")
    subidos = 0
    for fichero in salida.rglob("*"):
        if not fichero.is_file():
            continue
        rel = fichero.relative_to(salida).as_posix()
        ct = mimetypes.guess_type(rel)[0] or "application/octet-stream"
        try:
            almacen_media.guardar_crudo(
                f"{_PREFIJO_PREVIEW}sug-{sugerencia_id}/{rel}", fichero.read_bytes(), content_type=ct
            )
            subidos += 1
        except Exception:  # noqa: BLE001 -- un fichero que falla no aborta el bundle
            _log.warning("preview: no se pudo subir %s de %s", rel, sugerencia_id, exc_info=True)
    shutil.rmtree(salida, ignore_errors=True)
    return subidos > 0


def _teardown(sugerencia_id: str) -> None:
    """Elimina TODO rastro de una sugerencia: worktree, rama local y preview en S3/disco.

    Idempotente y best-effort: cada paso tolera que ya no exista, y un fallo de uno no aborta
    los demas (la promocion NUNCA debe romperse por la limpieza; el reaper reintenta lo que
    quede). Lo llaman la promocion (sincrona, tras el push OK) y el reaper de fondo.
    """
    repo = _repo()
    rama = f"dev/sug-{sugerencia_id}"
    wt = _dir_worktrees() / f"sug-{sugerencia_id}"
    try:
        if wt.exists():
            res = _git("worktree", "remove", "--force", str(wt), cwd=repo)
            if res.returncode != 0 and wt.exists():
                shutil.rmtree(wt, ignore_errors=True)
        _git("worktree", "prune", cwd=repo)
        _git("branch", "-D", rama, cwd=repo)
    except Exception:  # noqa: BLE001 -- limpieza best-effort; el reaper reintenta
        _log.warning("worker_dev: fallo al limpiar worktree/rama de %s", sugerencia_id, exc_info=True)
    try:
        almacen_media.borrar_prefijo(f"{_PREFIJO_PREVIEW}sug-{sugerencia_id}/")
    except Exception:  # noqa: BLE001 -- limpieza best-effort
        _log.warning("worker_dev: fallo al borrar el preview de %s", sugerencia_id, exc_info=True)
    try:
        sugerencias.actualizar_avance(sugerencia_id, {"worktree": "", "preview_listo": False})
    except Exception:  # noqa: BLE001 -- reflejar el campo es secundario
        _log.warning("worker_dev: fallo al limpiar el campo worktree de %s", sugerencia_id, exc_info=True)


# --------------------------------------------------------------------------- #
# Promoción REAL a main (la ejecuta el listener `dev_control`)                  #
# --------------------------------------------------------------------------- #


def promover_sugerencia(sugerencia_id: str) -> dict[str, object]:
    """Promueve a `main` la rama de una sugerencia: fetch → rebase → push (real).

    Corre DENTRO del worktree de la sugerencia en `/repo`, con la credencial gh
    (`gh auth setup-git`). Devuelve `{ok, detalle, rama}`; ante cualquier fallo devuelve
    `{ok:false, detalle}` legible (nunca propaga). Lo invoca el listener de control de
    worker-dev, que el `back` proxea admin-gated.
    """
    sug = sugerencias.obtener(sugerencia_id)
    if sug is None:
        return {"ok": False, "detalle": "Esa sugerencia ya no existe."}
    if sug.get("estado") != "revision":
        return {"ok": False, "detalle": "La sugerencia no está lista para promover."}
    rama = str(sug.get("rama") or f"dev/sug-{sugerencia_id}")
    wt_crudo = str(sug.get("worktree") or (_dir_worktrees() / f"sug-{sugerencia_id}"))
    worktree = Path(wt_crudo)
    if not worktree.is_dir():
        return {"ok": False, "detalle": "No se encontró el worktree de la sugerencia para promover."}

    # La credencial gh debe estar cableada en git para que `git push` autentique.
    _setup_git_credenciales()

    # Rebase SIEMPRE sobre origin/main antes de empujar (disciplina del script local); si hay
    # conflictos, un agente Opus los resuelve para que «meter a main» no falle por rama vieja.
    ok, detalle = _rebasar_sobre_main(worktree, resolver_conflictos=True)
    if not ok:
        return {"ok": False, "detalle": detalle, "rama": rama}

    push = _git("push", "origin", f"{rama}:main", cwd=worktree, timeout=300)
    if push.returncode != 0:
        return {"ok": False, "detalle": f"El push a main falló: {(push.stderr or '').strip()[:300]}", "rama": rama}

    # Promovida: el cambio ya vive en `main`. Limpia el worktree, la rama local y el preview
    # para no dejar artefactos huerfanos en el worker ni en S3.
    _teardown(sugerencia_id)
    return {"ok": True, "detalle": f"Rama «{rama}» promovida a main.", "rama": rama}


# --------------------------------------------------------------------------- #
# Preview: detección de desfase respecto a main + reconstrucción                #
# --------------------------------------------------------------------------- #


def _worktree_de(sug: dict, sugerencia_id: str) -> Path:
    """Path del worktree de una sugerencia (de la fila o el convencional `sug-<id>`)."""
    return Path(str(sug.get("worktree") or (_dir_worktrees() / f"sug-{sugerencia_id}")))


def preview_desfasado(sugerencia_id: str) -> dict[str, object]:
    """¿El preview de una sugerencia se quedó viejo respecto a `main`? No lanza.

    El preview se compila de la rama; si `main` avanzó con commits que la rama no incluye, el
    bundle está DESFASADO (puede no enrutar/arrancar). Lo detecta en el worktree: `fetch
    origin main` y luego `merge-base --is-ancestor origin/main HEAD` (returncode 0 = la rama ya
    contiene main = al día; !=0 = desfasada). Devuelve `{ok, desfasado, detalle}`; sin worktree
    o sin preview devuelve `desfasado=False` (no hay nada que comparar).
    """
    sug = sugerencias.obtener(sugerencia_id)
    if sug is None:
        return {"ok": False, "desfasado": False, "detalle": "Esa sugerencia ya no existe."}
    if not sug.get("preview_listo"):
        return {"ok": True, "desfasado": False, "detalle": "No hay preview."}
    worktree = _worktree_de(sug, sugerencia_id)
    if not worktree.is_dir():
        return {"ok": True, "desfasado": False, "detalle": "No hay worktree para comparar."}
    _setup_git_credenciales()
    fetch = _git("fetch", "origin", "main", cwd=worktree)
    if fetch.returncode != 0:
        return {"ok": False, "desfasado": False, "detalle": "No se pudo consultar origin/main."}
    al_dia = _git("merge-base", "--is-ancestor", "origin/main", "HEAD", cwd=worktree).returncode == 0
    return {
        "ok": True,
        "desfasado": not al_dia,
        "detalle": "El preview está desfasado respecto a main." if not al_dia else "Preview al día.",
    }


def reconstruir_preview(sugerencia_id: str) -> dict[str, object]:
    """Rebasa la rama sobre `origin/main` y RECONSTRUYE el preview (sin push). No lanza.

    Para refrescar un preview desfasado (p.ej. compilado de un `main` anterior) sin re-correr el
    pipeline. fetch → rebase `origin/main`; si hay conflictos, `--abort` y error legible. Tras un
    rebase OK recompila el bundle. No toca el kanban. Rechaza si hay una fase en curso o no hay
    worktree.
    """
    sug = sugerencias.obtener(sugerencia_id)
    if sug is None:
        return {"ok": False, "detalle": "Esa sugerencia ya no existe."}
    if sug.get("estado") == "building":
        return {"ok": False, "detalle": "Hay una fase en curso; espera a que termine."}
    worktree = _worktree_de(sug, sugerencia_id)
    if not worktree.is_dir():
        return {"ok": False, "detalle": "No se encontró el worktree de la sugerencia."}

    _setup_git_credenciales()
    ok, detalle = _rebasar_sobre_main(worktree)
    if not ok:
        return {"ok": False, "detalle": detalle}
    listo = _construir_preview(worktree, sugerencia_id)
    sugerencias.actualizar_avance(sugerencia_id, {"preview_listo": listo})
    return {
        "ok": listo,
        "detalle": "Preview reconstruido sobre main." if listo else "No se pudo reconstruir el preview.",
        "preview_listo": listo,
    }


# --------------------------------------------------------------------------- #
# Reaper de fondo: purga restos de sugerencias terminadas (descartes/crashes)  #
# --------------------------------------------------------------------------- #


def _ids_con_restos() -> set[str]:
    """IDs de sugerencias con algun resto material: worktree, rama local o preview en S3.

    Une las tres fuentes para que el reaper alcance restos parciales (p.ej. una rama cuyo
    worktree ya se borro, o un preview sin worktree). Best-effort: una fuente que falle no
    impide enumerar las demas.
    """
    ids: set[str] = set()
    try:
        for d in _dir_worktrees().glob("sug-*"):
            if d.is_dir():
                ids.add(d.name[len("sug-"):])
    except OSError:
        pass
    try:
        res = _git("branch", "--list", "dev/sug-*", cwd=_repo())
        for linea in (res.stdout or "").splitlines():
            nombre = linea.replace("*", "").strip()
            if nombre.startswith("dev/sug-"):
                ids.add(nombre[len("dev/sug-"):])
    except Exception:  # noqa: BLE001 -- enumeracion best-effort
        pass
    try:
        pref = f"{_PREFIJO_PREVIEW}sug-"
        for clave, _mtime in almacen_media.listar_objetos():
            if clave.startswith(pref):
                sid = clave[len(pref):].split("/", 1)[0]
                if sid:
                    ids.add(sid)
    except Exception:  # noqa: BLE001 -- enumeracion best-effort
        pass
    return ids


def _reapear() -> int:
    """Una pasada del reaper: limpia restos de sugerencias terminadas o ya inexistentes.

    Una sugerencia en estado terminal (`hecha`/`descartada`) o que ya no existe en BD no va a
    generar mas trabajo, asi que su worktree/rama/preview son basura. Las que siguen vivas
    (building, revision, ...) se RESPETAN. Devuelve cuantas limpio.
    """
    limpiadas = 0
    for sid in _ids_con_restos():
        try:
            sug = sugerencias.obtener(sid)
        except Exception:  # noqa: BLE001 -- un fallo por id no detiene al resto
            continue
        estado = sug.get("estado") if isinstance(sug, dict) else None
        if sug is None or estado in _ESTADOS_TERMINALES_DEV:
            _teardown(sid)
            limpiadas += 1
    return limpiadas


def _bucle_reaper(parar: threading.Event) -> None:
    """Reaper de fondo: cada `_INTERVALO_REAPER_S` purga restos huerfanos.

    Backstop de la limpieza sincrona de la promocion: cubre descartes, borrados y crashes a
    medio camino. Corre una pasada al arrancar y luego en bucle hasta el apagado.
    """
    while True:
        try:
            n = _reapear()
            if n:
                _log.info("worker_dev: reaper limpio %d sugerencia(s) terminada(s).", n)
        except Exception:  # noqa: BLE001 -- el reaper nunca debe morir por una pasada
            _log.warning("worker_dev: fallo en la pasada del reaper", exc_info=True)
        if parar.wait(_INTERVALO_REAPER_S):
            return


# --------------------------------------------------------------------------- #
# Ejecución de `claude -p` en STREAMING (token a token) con cancel + reintento  #
# --------------------------------------------------------------------------- #


def _argv_claude(prompt: str, modelo: str) -> list[str]:
    """argv de `claude -p` SIN sandbox: STREAMING token a token y permisos AMPLIOS.

    `--output-format stream-json --verbose --include-partial-messages` habilita el streaming
    en vivo (eventos `stream_event`/`text_delta`) que la UI muestra igual que un copy. A
    diferencia del worker de contenido, el agente de desarrollo SÍ necesita Bash/Write/Edit:
    NO se pasa `--disallowed-tools`. `--model` el de la fase.
    """
    argv = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
    ]
    if config.claude_skip_permisos():
        argv.append("--dangerously-skip-permissions")
    if modelo:
        argv += ["--model", modelo]
    return argv


def _correr_claude(job_id: str, gen_id: str, prompt: str, cwd: Path, modelo: str) -> dict[str, object]:
    """Corre `claude -p` en streaming en `cwd` persistiendo el avance en el registro `gen_id`.

    Persiste el texto en vivo (acumulador + callback throttled) igual que `worker.py`, con un
    VIGÍA de cancelación cross-proceso (sondea `cola.cancelado` y mata el árbol) y REINTENTOS
    ante fallos transitorios (529/overloaded/crash) con backoff, igual que `_lanzadores`.

    Devuelve `{texto, coste, ok, cancelado, timed_out, mensaje_error, metricas}`.
    """
    timeout = config.claude_timeout()
    caja: dict[str, stream.AcumuladorStream] = {"acum": stream.AcumuladorStream()}
    cancelado = threading.Event()
    proc_holder: dict[str, subprocess.Popen] = {}

    def _avance() -> None:
        acum = caja["acum"]
        try:
            generaciones.actualizar(gen_id, {
                "estado": generaciones.ESTADO_EJECUTANDO,
                "fase": acum.fase(),
                "salida": acum.texto,
                "razonamiento": acum.razonamiento,
                "metricas": stream.metricas_a_dict(acum.metricas_parciales()),
            })
        except Exception:  # noqa: BLE001 -- el avance nunca debe romper el hilo
            _log.warning("worker_dev: fallo al persistir avance parcial de %s", gen_id, exc_info=True)

    parar_vigia = threading.Event()

    def _vigilar() -> None:
        while not parar_vigia.wait(_SONDEO_CANCELACION_S):
            try:
                if cola.cancelado(job_id):
                    cancelado.set()
                    proc = proc_holder.get("proc")
                    if proc is not None:
                        runner.matar_arbol(proc)
                    return
            except Exception:  # noqa: BLE001 -- el vigía nunca debe romper el job
                _log.warning("worker_dev: fallo al sondear cancelación de %s", job_id, exc_info=True)

    vigia = threading.Thread(target=_vigilar, name=f"dev-cancel-{job_id}", daemon=True)
    vigia.start()

    max_reintentos = _gl._reintentos_maximos()
    intento = 0
    timed_out = False
    try:
        while True:
            caja["acum"] = stream.AcumuladorStream()
            acum = caja["acum"]
            try:
                proc = runner.lanzar_proc(
                    _argv_claude(prompt, modelo), cwd=str(cwd), env=_gl._entorno_generacion(),
                )
            except (OSError, ValueError):
                _log.exception("worker_dev: no se pudo lanzar claude para %s", gen_id)
                return {
                    "texto": "", "coste": 0.0, "ok": False, "cancelado": False,
                    "timed_out": False, "mensaje_error": "No se pudo iniciar la fase de desarrollo.",
                    "metricas": None,
                }
            proc_holder["proc"] = proc
            if cancelado.is_set():
                runner.matar_arbol(proc)
            runner.leer_stream(proc, acum, _avance)
            timed_out = runner.esperar(proc, timeout)
            if (
                not cancelado.is_set()
                and not timed_out
                and intento < max_reintentos
                and _gl._es_fallo_transitorio(acum, proc.returncode)
                and _gl._presupuesto_permite_reintento()
            ):
                intento += 1
                espera = _gl._backoff_s(intento)
                _log.warning(
                    "worker_dev: fallo transitorio (%s); reintento %d/%d tras %.1fs",
                    acum.mensaje_error or f"rc={proc.returncode}", intento, max_reintentos, espera,
                )
                if cancelado.wait(espera):
                    break
                continue
            break
    finally:
        parar_vigia.set()

    acum = caja["acum"]
    coste = 0.0
    if acum.final is not None and acum.final.total_cost_usd:
        coste = float(acum.final.total_cost_usd)
    if cancelado.is_set():
        return {
            "texto": acum.texto, "coste": coste, "ok": False, "cancelado": True,
            "timed_out": False, "mensaje_error": "La fase de desarrollo fue cancelada.",
            "metricas": stream.metricas_a_dict(acum.metricas_parciales()),
        }
    if timed_out:
        return {
            "texto": acum.texto, "coste": coste, "ok": False, "cancelado": False,
            "timed_out": True,
            "mensaje_error": f"La fase de desarrollo superó el tiempo máximo ({timeout} s).",
            "metricas": stream.metricas_a_dict(acum.metricas_parciales()),
        }
    if acum.error:
        return {
            "texto": acum.texto, "coste": coste, "ok": False, "cancelado": False,
            "timed_out": False, "mensaje_error": acum.mensaje_error or "La fase de desarrollo terminó con error.",
            "metricas": stream.metricas_a_dict(acum.metricas_parciales()),
        }
    if acum.terminado:
        return {
            "texto": acum.texto, "coste": coste, "ok": True, "cancelado": False,
            "timed_out": False, "mensaje_error": "", "metricas": stream.metricas_a_dict(acum.final),
        }
    return {
        "texto": acum.texto, "coste": coste, "ok": False, "cancelado": False,
        "timed_out": False, "mensaje_error": "La fase de desarrollo terminó sin resultado.",
        "metricas": stream.metricas_a_dict(acum.metricas_parciales()),
    }


def _procesar_job(job: dict) -> None:
    """Ejecuta UN job dev ya clavado: worktree → claude (streaming) → post-procesado → encadenado."""
    job_id, gen_id, spec = job["id"], job["gen_id"], job.get("spec")
    if not isinstance(spec, dict):
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar la fase de desarrollo.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        cola.terminar(job_id)
        return

    # Job ya cancelado antes de clavarlo: finalizar SIN lanzar claude.
    if cola.cancelado(job_id):
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_ERROR, "motivo": generaciones.MOTIVO_CANCELADO,
            "error": "La fase de desarrollo fue cancelada.", "fecha_fin": generaciones.ahora_iso(),
        })
        cola.terminar(job_id)
        return

    p = spec.get("procesar") or {}
    kind = p.get("kind", "")
    sugerencia_id = p.get("sugerencia_id", "")
    fase = p.get("fase", "")
    modelo = p.get("modelo", "")
    prompt = spec.get("prompt", "")
    resultado: dict[str, object] = {}
    try:
        worktree, rama = _asegurar_worktree(sugerencia_id)
        sugerencias.actualizar_avance(
            sugerencia_id, {"rama": rama, "worktree": str(worktree)}
        )
        resultado = _correr_claude(job_id, gen_id, prompt, worktree, modelo)
        ok = bool(resultado["ok"])
        texto = str(resultado["texto"])
        if ok:
            procesar = jobspec.reconstruir_procesar(spec)
            procesar(texto, None)
            # Diff real del worktree para las fases que construyen/revisan, y acumula coste.
            avance: dict[str, object] = {}
            if kind == jobspec.PROC_DEV_FASE and fase in (desarrollo.FASE_BUILD, desarrollo.FASE_REVIEW):
                avance["diff_resumen"] = _diff_resumen(worktree)
            coste = float(resultado["coste"] or 0)
            if coste:
                sug = sugerencias.obtener(sugerencia_id) or {}
                avance["coste_usd"] = float(sug.get("coste_usd") or 0) + coste
            if avance:
                sugerencias.actualizar_avance(sugerencia_id, avance)
            # Tras construir, compila el frontend de la rama y publica un preview navegable.
            if kind == jobspec.PROC_DEV_FASE and fase == desarrollo.FASE_BUILD:
                listo = _construir_preview(worktree, sugerencia_id)
                sugerencias.actualizar_avance(sugerencia_id, {"preview_listo": listo})
            generaciones.actualizar(gen_id, {
                "estado": generaciones.ESTADO_COMPLETADO, "fase": generaciones.FASE_COMPLETADO,
                "salida": texto, "metricas": resultado["metricas"], "error": "",
                "fecha_fin": generaciones.ahora_iso(),
            })
        else:
            cambios: dict[str, object] = {
                "estado": generaciones.ESTADO_ERROR, "salida": texto,
                "error": str(resultado["mensaje_error"]) or "La fase de desarrollo terminó con error.",
                "metricas": resultado["metricas"], "fecha_fin": generaciones.ahora_iso(),
            }
            if resultado["cancelado"]:
                cambios["motivo"] = generaciones.MOTIVO_CANCELADO
            elif resultado["timed_out"]:
                cambios["motivo"] = generaciones.MOTIVO_TIMEOUT
            generaciones.actualizar(gen_id, cambios)
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

    # Una fase que terminó en error (no excepción) también marca la sugerencia `fallida`.
    if kind == jobspec.PROC_DEV_FASE and sugerencia_id and not resultado.get("ok"):
        try:
            sugerencias.cambiar_estado(sugerencia_id, "fallida")
        except sugerencias.TransicionInvalida:
            pass

    cola.terminar(job_id)

    # ENCADENADO: si una fase terminó y el pipeline sigue (estado `building`, no checkpoint),
    # lanza la siguiente fase. El discovery NO encadena (lo dispara una persona vía /construir).
    if kind == jobspec.PROC_DEV_FASE and sugerencia_id and resultado.get("ok"):
        sug = sugerencias.obtener(sugerencia_id)
        if sug is not None and sug["estado"] == "building":
            siguiente = desarrollo.siguiente_fase(sug.get("complejidad", ""), fase)
            if siguiente is not None:
                try:
                    sugerencias.lanzar_fase(sugerencia_id, siguiente)
                except Exception:  # noqa: BLE001 -- el encadenado nunca rompe el cierre del job
                    _log.exception("worker_dev: no se pudo encadenar la fase tras %s", fase)


def _bucle(parar: threading.Event, worker_id: str) -> None:
    """Bucle de un hilo del pool dev: reclama un job del carril `dev` y lo procesa.

    GATE DE ECONOMÍA (presupuesto_ia): igual que `worker._bucle`, antes de reclamar se consulta
    el presupuesto. El carril dev SÍ gasta tokens claude, así que pausado (kill switch) o
    agotado no reclama NADA (lo encolado queda pendiente); en solo-manual solo reclama
    prioridad >= MANUAL (los jobs dev se encolan como MANUAL, así que no se quedan sin servir).
    """
    sondeo = config.worker_sondeo_segundos()
    espera = sondeo
    while not parar.is_set():
        try:
            nivel = presupuesto_ia.nivel()
        except Exception:  # noqa: BLE001 -- ante un fallo del gate, preferimos NO cortar
            _log.warning("worker_dev: fallo el gate de presupuesto; sigo sin corte", exc_info=True)
            nivel = presupuesto_ia.NIVEL_NORMAL
        if presupuesto_ia.bloqueo_admision(nivel, gasta_tokens=True, es_fondo=False) is not None:
            if parar.wait(espera):
                return
            espera = min(espera * 1.5, max(sondeo, _SONDEO_MAX_S))
            continue
        solo_manual = (
            presupuesto_ia.bloqueo_admision(nivel, gasta_tokens=True, es_fondo=True) is not None
        )
        prioridad_minima = jobspec.PRIORIDAD_MANUAL if solo_manual else None
        try:
            job = cola.reclamar(
                worker_id, prioridad_minima=prioridad_minima, carriles=_CARRILES_DEV,
            )
        except Exception:  # noqa: BLE001 -- un fallo de la cola no debe matar el worker
            _log.exception("worker_dev: fallo al reclamar un job dev")
            if parar.wait(espera):
                return
            continue
        if job is None:
            if parar.wait(espera):
                return
            espera = min(espera * 1.5, max(sondeo, _SONDEO_MAX_S))
            continue
        espera = sondeo
        if parar.is_set():
            return
        try:
            _procesar_job(job)
        except Exception:  # noqa: BLE001 -- un fallo de UN job no debe matar el worker
            _log.exception("worker_dev: fallo al procesar el job %s", job.get("id"))


def main() -> int:
    """Entry-point del servicio `worker-dev`: siembra el repo, levanta el listener y corre el pool."""
    from .observabilidad import configurar_logging

    configurar_logging()
    from . import repos

    repos.arrancar_persistencia()

    # Siembra best-effort del clon + credenciales git (tolera gh aún sin conectar; el primer
    # worktree lo reintenta). El listener de promoción se levanta SIEMPRE (no depende del clon).
    try:
        _setup_git_credenciales()
        repo = _repo()
        if not _es_repo_git(repo):
            _asegurar_repo(repo)
    except Exception as e:  # noqa: BLE001 -- siembra best-effort; el primer worktree reintenta
        _log.warning("worker_dev: clon inicial no disponible (se reintenta perezosamente): %s", e)

    from . import dev_control

    dev_control.iniciar_control_dev()

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
    reaper = threading.Thread(target=_bucle_reaper, args=(parar,), name="dev-reaper", daemon=True)
    for h in hilos:
        h.start()
    reaper.start()
    _log.info("worker_dev iniciado: pool de %d hilos (carril dev) + reaper de limpieza.", len(hilos))
    try:
        while not parar.wait(timeout=1.0):
            pass
    except (KeyboardInterrupt, SystemExit):
        parar.set()
    for h in hilos:
        h.join(timeout=5.0)
    reaper.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

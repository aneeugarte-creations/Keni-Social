"""Tests OFFLINE del worker del carril dev: argv de streaming, cupo, config y promoción.

Sin BD ni subprocess reales: `_git` y `sugerencias.obtener` se parchean; `claude`/`gh` nunca
se invocan. Cubre las partes deterministas de `worker_dev` (el camino de ejecución con `claude`
real no se testea, como el gestor de Ralph).
"""

from __future__ import annotations

import subprocess

from keni_consola import config, worker_dev


# --------------------------------------------------------------------------- #
# argv de `claude -p` (STREAMING, permisos amplios)                            #
# --------------------------------------------------------------------------- #


def test_argv_claude_streaming_y_permisos_amplios():
    argv = worker_dev._argv_claude("PROMPT", "opus")
    # Streaming token a token (NO `--output-format json`).
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--include-partial-messages" in argv
    assert "--verbose" in argv
    # Permisos AMPLIOS: el agente dev necesita Bash/Write/Edit -> NO se vetan herramientas.
    assert "--disallowed-tools" not in argv
    # Modelo de la fase.
    assert "--model" in argv and argv[argv.index("--model") + 1] == "opus"
    # El prompt viaja como argumento (sin shell).
    assert "PROMPT" in argv


def test_argv_claude_sin_modelo_no_pasa_model():
    argv = worker_dev._argv_claude("p", "")
    assert "--model" not in argv


# --------------------------------------------------------------------------- #
# Cupo de hilos del carril dev                                                 #
# --------------------------------------------------------------------------- #


def test_max_jobs_dev_default_y_override(monkeypatch):
    monkeypatch.delenv("KENI_MAX_JOBS_DEV", raising=False)
    assert worker_dev._max_jobs_dev() == 2
    monkeypatch.setenv("KENI_MAX_JOBS_DEV", "5")
    assert worker_dev._max_jobs_dev() == 5
    monkeypatch.setenv("KENI_MAX_JOBS_DEV", "0")
    assert worker_dev._max_jobs_dev() == 1  # mínimo 1
    monkeypatch.setenv("KENI_MAX_JOBS_DEV", "basura")
    assert worker_dev._max_jobs_dev() == 2


# --------------------------------------------------------------------------- #
# Config del listener de promoción                                             #
# --------------------------------------------------------------------------- #


def test_config_dev_puerto_y_url(monkeypatch):
    monkeypatch.delenv("KENI_DEV_PORT", raising=False)
    monkeypatch.delenv("KENI_DEV_URL", raising=False)
    assert config.dev_puerto() == 8772
    assert config.dev_url() == "http://worker-dev:8772"
    monkeypatch.setenv("KENI_DEV_PORT", "9999")
    monkeypatch.setenv("KENI_DEV_URL", "http://otro:1234")
    assert config.dev_puerto() == 9999
    assert config.dev_url() == "http://otro:1234"


# --------------------------------------------------------------------------- #
# Promoción REAL a main (git parcheado)                                        #
# --------------------------------------------------------------------------- #


class _FakeGit:
    """Registra las llamadas a `git` y falla las que tengan el subcomando en `fallos`."""

    def __init__(self, fallos=()):
        self.llamadas: list[tuple[str, ...]] = []
        self.fallos = set(fallos)

    def __call__(self, *args, cwd=None, timeout=120):
        self.llamadas.append(args)
        rc = 1 if (args and args[0] in self.fallos) else 0
        return subprocess.CompletedProcess(
            args=list(args), returncode=rc, stdout="", stderr=("boom" if rc else ""),
        )


def _parchear(monkeypatch, sug, tmp_path, fallos=()):
    # En el servidor KENI_DATA_DIR siempre está; sin él, `_dir_worktrees()` cae a una ruta no
    # escribible. Lo anclamos en tmp para que la limpieza tras el push opere en un dir real.
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    fake = _FakeGit(fallos)
    monkeypatch.setattr(worker_dev, "_git", fake)
    monkeypatch.setattr(worker_dev, "_setup_git_credenciales", lambda: None)
    monkeypatch.setattr(worker_dev.sugerencias, "obtener", lambda _id: sug)
    # La promocion limpia tras el push: neutraliza los efectos colaterales (S3 + BD).
    monkeypatch.setattr(worker_dev.almacen_media, "borrar_prefijo", lambda *_a, **_k: 0)
    monkeypatch.setattr(worker_dev.sugerencias, "actualizar_avance", lambda *_a, **_k: None)
    return fake


def test_promover_sugerencia_ok(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    fake = _parchear(monkeypatch, sug, tmp_path)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is True
    assert res["rama"] == "dev/sug-x"
    # Hizo fetch -> rebase -> push, en ese orden, antes de cualquier limpieza.
    subcomandos = [c[0] for c in fake.llamadas]
    assert subcomandos[:3] == ["fetch", "rebase", "push"]
    assert fake.llamadas[2] == ("push", "origin", "dev/sug-x:main")
    # Tras el push OK limpia el worktree (prune) y borra la rama local.
    assert ("worktree", "prune") in fake.llamadas
    assert ("branch", "-D", "dev/sug-x") in fake.llamadas


def test_promover_sugerencia_no_revision(monkeypatch, tmp_path):
    sug = {"estado": "building", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    _parchear(monkeypatch, sug, tmp_path)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "lista para promover" in res["detalle"]


def test_promover_sugerencia_sin_worktree(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path / "no-existe")}
    _parchear(monkeypatch, sug, tmp_path)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "worktree" in res["detalle"].lower()


def test_promover_sugerencia_inexistente(monkeypatch):
    monkeypatch.setattr(worker_dev.sugerencias, "obtener", lambda _id: None)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False


def test_promover_sugerencia_rebase_conflicto(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    fake = _parchear(monkeypatch, sug, tmp_path, fallos={"rebase"})
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "rebase" in res["detalle"].lower()
    # Abortó el rebase y NO empujó.
    subcomandos = [c[0] for c in fake.llamadas]
    assert "push" not in subcomandos
    assert ("rebase", "--abort") in fake.llamadas


def test_promover_sugerencia_push_falla(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    _parchear(monkeypatch, sug, tmp_path, fallos={"push"})
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "push" in res["detalle"].lower()


# --------------------------------------------------------------------------- #
# Teardown: borra worktree + rama local + preview                              #
# --------------------------------------------------------------------------- #


def test_teardown_borra_worktree_rama_y_preview(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    wt = tmp_path / "dev-worktrees" / "sug-z"
    wt.mkdir(parents=True)
    fake = _FakeGit()
    monkeypatch.setattr(worker_dev, "_git", fake)
    prefijos: list[str] = []
    monkeypatch.setattr(worker_dev.almacen_media, "borrar_prefijo", lambda p: prefijos.append(p) or 0)
    avances: list[tuple] = []
    monkeypatch.setattr(
        worker_dev.sugerencias, "actualizar_avance", lambda sid, c: avances.append((sid, c))
    )

    worker_dev._teardown("z")

    assert ("worktree", "remove", "--force", str(wt)) in fake.llamadas
    assert ("branch", "-D", "dev/sug-z") in fake.llamadas
    assert prefijos == ["previews/sug-z/"]
    assert avances == [("z", {"worktree": "", "preview_listo": False})]


def test_teardown_idempotente_sin_worktree(monkeypatch, tmp_path):
    """Sin worktree en disco no intenta `worktree remove`, pero sí poda y borra rama/preview."""
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    fake = _FakeGit()
    monkeypatch.setattr(worker_dev, "_git", fake)
    monkeypatch.setattr(worker_dev.almacen_media, "borrar_prefijo", lambda _p: 0)
    monkeypatch.setattr(worker_dev.sugerencias, "actualizar_avance", lambda *_a, **_k: None)

    worker_dev._teardown("nada")

    subcomandos = [c[:2] for c in fake.llamadas]
    assert ("worktree", "remove") not in subcomandos
    assert ("worktree", "prune") in subcomandos
    assert ("branch", "-D") in subcomandos


# --------------------------------------------------------------------------- #
# Reaper: limpia terminales/huérfanas, respeta las vivas                       #
# --------------------------------------------------------------------------- #


def test_reaper_limpia_terminales_e_inexistentes_respeta_vivas(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    base = tmp_path / "dev-worktrees"
    for sid in ("a", "b", "c"):
        (base / f"sug-{sid}").mkdir(parents=True)
    # `branch --list` y el listado de previews no aportan ids nuevos en este caso.
    monkeypatch.setattr(worker_dev, "_git", _FakeGit())
    monkeypatch.setattr(worker_dev.almacen_media, "listar_objetos", lambda: [])
    estados = {"a": {"estado": "hecha"}, "b": {"estado": "building"}}  # 'c' -> None (ya no existe)
    monkeypatch.setattr(worker_dev.sugerencias, "obtener", lambda sid: estados.get(sid))
    limpiadas: list[str] = []
    monkeypatch.setattr(worker_dev, "_teardown", lambda sid: limpiadas.append(sid))

    n = worker_dev._reapear()

    assert n == 2
    assert set(limpiadas) == {"a", "c"}  # terminal + inexistente; 'b' (building) se respeta


def test_ids_con_restos_une_worktrees_ramas_y_previews(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    (tmp_path / "dev-worktrees" / "sug-a").mkdir(parents=True)

    class _GitRamas:
        def __call__(self, *args, cwd=None, timeout=120):
            salida = "  dev/sug-b\n* dev/sug-a\n" if args[:2] == ("branch", "--list") else ""
            return subprocess.CompletedProcess(args=list(args), returncode=0, stdout=salida, stderr="")

    monkeypatch.setattr(worker_dev, "_git", _GitRamas())
    monkeypatch.setattr(
        worker_dev.almacen_media, "listar_objetos", lambda: [("previews/sug-c/index.html", 0.0)]
    )

    assert worker_dev._ids_con_restos() == {"a", "b", "c"}


# --------------------------------------------------------------------------- #
# Construcción del preview: vite build -> sube el bundle a previews/sug-<id>/  #
# --------------------------------------------------------------------------- #


def _preparar_front(tmp_path):
    front = tmp_path / "consola" / "frontend"
    (front / "node_modules").mkdir(parents=True)  # evita el npm ci
    (front / "package.json").write_text("{}")
    return front


def test_construir_preview_compila_y_sube_el_bundle(monkeypatch, tmp_path):
    front = _preparar_front(tmp_path)

    def fake_cmd(argv, *, cwd, timeout=900):
        if argv[:2] == ["npx", "vite"]:
            # vite build con --base correcto (id pelado) escribe el bundle en dist-preview.
            assert "--base" in argv and argv[argv.index("--base") + 1] == "/api/preview/z/"
            (front / "dist-preview" / "assets").mkdir(parents=True)
            (front / "dist-preview" / "index.html").write_text("<html>")
            (front / "dist-preview" / "assets" / "app.js").write_text("//js")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(worker_dev, "_correr_cmd", fake_cmd)
    monkeypatch.setattr(worker_dev.almacen_media, "borrar_prefijo", lambda _p: 0)
    subidos: dict[str, str] = {}
    monkeypatch.setattr(
        worker_dev.almacen_media, "guardar_crudo",
        lambda clave, datos, *, content_type: subidos.__setitem__(clave, content_type),
    )

    assert worker_dev._construir_preview(tmp_path, "z") is True
    assert "previews/sug-z/index.html" in subidos
    assert "previews/sug-z/assets/app.js" in subidos


def test_construir_preview_build_falla_devuelve_false(monkeypatch, tmp_path):
    _preparar_front(tmp_path)
    monkeypatch.setattr(
        worker_dev, "_correr_cmd",
        lambda argv, *, cwd, timeout=900: subprocess.CompletedProcess(argv, 1, "", "boom"),
    )
    assert worker_dev._construir_preview(tmp_path, "z") is False


def test_construir_preview_sin_frontend_devuelve_false(tmp_path):
    assert worker_dev._construir_preview(tmp_path, "z") is False

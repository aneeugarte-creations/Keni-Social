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


def _parchear(monkeypatch, sug, fallos=()):
    fake = _FakeGit(fallos)
    monkeypatch.setattr(worker_dev, "_git", fake)
    monkeypatch.setattr(worker_dev, "_setup_git_credenciales", lambda: None)
    monkeypatch.setattr(worker_dev.sugerencias, "obtener", lambda _id: sug)
    return fake


def test_promover_sugerencia_ok(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    fake = _parchear(monkeypatch, sug)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is True
    assert res["rama"] == "dev/sug-x"
    # Hizo fetch -> rebase -> push, en ese orden.
    subcomandos = [c[0] for c in fake.llamadas]
    assert subcomandos == ["fetch", "rebase", "push"]
    assert fake.llamadas[-1] == ("push", "origin", "dev/sug-x:main")


def test_promover_sugerencia_no_revision(monkeypatch, tmp_path):
    sug = {"estado": "building", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    _parchear(monkeypatch, sug)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "lista para promover" in res["detalle"]


def test_promover_sugerencia_sin_worktree(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path / "no-existe")}
    _parchear(monkeypatch, sug)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "worktree" in res["detalle"].lower()


def test_promover_sugerencia_inexistente(monkeypatch):
    monkeypatch.setattr(worker_dev.sugerencias, "obtener", lambda _id: None)
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False


def test_promover_sugerencia_rebase_conflicto(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    fake = _parchear(monkeypatch, sug, fallos={"rebase"})
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "rebase" in res["detalle"].lower()
    # Abortó el rebase y NO empujó.
    subcomandos = [c[0] for c in fake.llamadas]
    assert "push" not in subcomandos
    assert ("rebase", "--abort") in fake.llamadas


def test_promover_sugerencia_push_falla(monkeypatch, tmp_path):
    sug = {"estado": "revision", "rama": "dev/sug-x", "worktree": str(tmp_path)}
    _parchear(monkeypatch, sug, fallos={"push"})
    res = worker_dev.promover_sugerencia("x")
    assert res["ok"] is False
    assert "push" in res["detalle"].lower()

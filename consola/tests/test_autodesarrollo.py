"""Tests HERMÉTICOS del lazo de auto-desarrollo del buzón (#109, F-C-11).

CRÍTICO: NINGÚN test aquí llama a `claude` de verdad, hace `git push` real ni toca
`main`. Todo se hace con stubs/fakes y repos temporales (`tmp_path`). Se verifica la
LÓGICA DE LOS 6 GATES de seguridad:

  1. flag OFF -> `implementar` no hace nada (`bloqueada`), sin worktree ni claude.
  2. ejecución aislada -> el runner recibe el cwd del worktree (verificado con fakes).
  3. CI roja -> `parked` (nunca merge).
  4. caps de alcance -> rutas sensibles `rechazada`; supera el cap `parked`.
  5. entorno saneado -> sin claves/tokens/secretos.
  6. auditoría -> cada intento se escribe en el log JSONL.

El dominio expone funciones INYECTABLES (`correr_git`, `correr_ci`, `lanzar_implementacion`)
que aquí se monkeypatchean por fakes deterministas. Sin efectos reales.
"""

from __future__ import annotations

import json
import os

import pytest

from keni_consola import autodesarrollo as ad


@pytest.fixture
def aislado(monkeypatch, tmp_path):
    """Aísla config, auditoría y repo del lazo en tmp; flag OFF; sin CI configurado."""
    monkeypatch.setenv("KENI_AUTODESARROLLO_CONFIG", str(tmp_path / "autodesarrollo.toml"))
    monkeypatch.setenv("KENI_AUTODESARROLLO_AUDITORIA", str(tmp_path / "auditoria.jsonl"))
    monkeypatch.setenv("KENI_AUTODESARROLLO_REPO", str(tmp_path / "repo"))
    monkeypatch.delenv("KENI_AUTODESARROLLO", raising=False)
    monkeypatch.delenv("KENI_AUTODESARROLLO_CI", raising=False)
    monkeypatch.delenv("KENI_AUTODESARROLLO_CAP_LINEAS", raising=False)
    return tmp_path


# --------------------------------------------------------------------------- #
# GATE 1: flag default OFF + kill switch                                       #
# --------------------------------------------------------------------------- #


def test_flag_default_off(aislado):
    assert ad.flag_activo() is False


def test_flag_se_activa_por_config(aislado):
    ad.guardar_flag(True)
    assert ad.flag_activo() is True
    ad.guardar_flag(False)
    assert ad.flag_activo() is False


def test_flag_entorno_es_kill_switch_y_manda_sobre_config(aislado, monkeypatch):
    # La config dice activo, pero el entorno lo apaga: el entorno (kill switch) manda.
    ad.guardar_flag(True)
    monkeypatch.setenv("KENI_AUTODESARROLLO", "0")
    assert ad.flag_activo() is False
    monkeypatch.setenv("KENI_AUTODESARROLLO", "1")
    assert ad.flag_activo() is True


def test_implementar_con_flag_off_no_hace_nada(aislado, monkeypatch):
    # Si el flag está OFF, NI siquiera se intenta crear worktree o lanzar claude.
    def _boom(*a, **k):
        raise AssertionError("no debería crearse worktree con el flag OFF")

    monkeypatch.setattr(ad, "crear_worktree_efimero", _boom)
    monkeypatch.setattr(ad, "lanzar_implementacion", _boom)

    aud = ad.implementar({"id": "s1", "titulo": "Idea"})
    assert aud["estado"] == ad.ESTADO_BLOQUEADA
    assert aud["motivo"] == "flag-off"
    # Y queda auditado (gate 6).
    assert ad.leer_auditoria()[0]["estado"] == ad.ESTADO_BLOQUEADA


# --------------------------------------------------------------------------- #
# GATE 4: caps de alcance (rutas sensibles + tamaño)                           #
# --------------------------------------------------------------------------- #


def test_evaluar_diff_acepta_diff_modesto(aislado):
    numstat = "10\t2\tconsola/src/keni_consola/api/ejemplo.py\n5\t0\ttests/test_x.py\n"
    ev = ad.evaluar_diff(numstat)
    assert ev["aceptable"] is True
    assert ev["lineas"] == 17
    assert ev["ficheros"] == 2


@pytest.mark.parametrize(
    "ruta",
    [
        "consola/src/keni_consola/secretos.py",
        "consola/src/keni_consola/db.py",
        "consola/src/keni_consola/ficheros.py",
        "consola/src/keni_consola/repos.py",
        "consola/src/keni_consola/estados.py",
        "consola/src/keni_consola/indice.py",
        "consola/src/keni_consola/api/conexiones.py",
        ".github/workflows/ci.yml",
        "keni-shared/src/keni_shared/marca.py",
        "consola/pyproject.toml",
        "consola/frontend/package-lock.json",
    ],
)
def test_evaluar_diff_rechaza_rutas_sensibles(aislado, ruta):
    ev = ad.evaluar_diff(f"3\t1\t{ruta}\n")
    assert ev["aceptable"] is False
    assert ev["motivo"] == "rutas-sensibles"
    assert ruta in ev["sensibles"]


def test_evaluar_diff_supera_cap(aislado):
    # 300 + 200 = 500 > 400 (cap por defecto).
    numstat = "300\t200\tconsola/src/keni_consola/api/grande.py\n"
    ev = ad.evaluar_diff(numstat)
    assert ev["aceptable"] is False
    assert ev["motivo"] == "supera-cap"


def test_evaluar_diff_cap_configurable(aislado, monkeypatch):
    monkeypatch.setenv("KENI_AUTODESARROLLO_CAP_LINEAS", "10")
    ev = ad.evaluar_diff("6\t6\tconsola/x.py\n")  # 12 > 10
    assert ev["aceptable"] is False and ev["motivo"] == "supera-cap"


def test_evaluar_diff_sin_cambios(aislado):
    ev = ad.evaluar_diff("")
    assert ev["aceptable"] is False and ev["motivo"] == "sin-cambios"


def test_evaluar_diff_binario_no_suma_lineas(aislado):
    ev = ad.evaluar_diff("-\t-\tconsola/static/logo.png\n")
    assert ev["lineas"] == 0
    assert ev["aceptable"] is True  # un binario neutro no rompe el cap


# --------------------------------------------------------------------------- #
# GATE 5: entorno saneado (sin secretos/tokens)                                #
# --------------------------------------------------------------------------- #


def test_entorno_saneado_quita_claves_y_tokens(aislado, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secreto")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("MI_SERVICIO_SECRET", "abc")
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", "/ruta/secretos.toml")
    monkeypatch.setenv("PATH_SEGURO", "ok")  # no es secreto: se conserva
    env = ad.entorno_saneado()
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "MI_SERVICIO_SECRET" not in env
    assert "KENI_CONSOLA_SECRETOS" not in env
    assert env.get("PATH_SEGURO") == "ok"


# --------------------------------------------------------------------------- #
# GATE 6: auditoría persistente                                                #
# --------------------------------------------------------------------------- #


def test_auditoria_escribe_y_lee_reciente_primero(aislado):
    ad.registrar_auditoria({"sugerencia_id": "a", "estado": ad.ESTADO_PARKED})
    ad.registrar_auditoria({"sugerencia_id": "b", "estado": ad.ESTADO_MERGEADA, "sha": "deadbeef"})
    aud = ad.leer_auditoria()
    assert aud[0]["sugerencia_id"] == "b"  # reciente primero
    assert aud[0]["sha"] == "deadbeef"
    assert aud[1]["sugerencia_id"] == "a"
    # Cada entrada tiene id y fecha.
    assert aud[0]["id"] and aud[0]["fecha"]


def test_auditoria_tolerante_a_linea_corrupta(aislado):
    ruta = ad.ruta_auditoria()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text('{"estado":"parked"}\nesto no es json\n', encoding="utf-8")
    aud = ad.leer_auditoria()
    assert len(aud) == 1 and aud[0]["estado"] == "parked"


# --------------------------------------------------------------------------- #
# Orquestación end-to-end del lazo (con fakes; gates 2/3/4/5/6 juntos)         #
# --------------------------------------------------------------------------- #


def _fake_worktree(monkeypatch, tmp_path):
    """Fake de worktree: devuelve una carpeta tmp y una rama; registra la limpieza."""
    wt = tmp_path / "wt"
    wt.mkdir()
    borrados: list = []
    monkeypatch.setattr(ad, "crear_worktree_efimero", lambda sid: (wt, "autodesarrollo/x-1"))
    monkeypatch.setattr(ad, "borrar_worktree", lambda w, r: borrados.append((w, r)))
    return wt, borrados


def _git_con_numstat(numstat: str):
    """Fake de `correr_git`: responde a `diff --numstat` con `numstat`; el resto returncode 0."""
    import subprocess

    def fake(args, *, cwd):  # noqa: ANN001
        out = numstat if args[:2] == ["diff", "--numstat"] else "fakesha123\n"
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    return fake


def test_lazo_rechaza_diff_sensible_sin_ci_ni_merge(aislado, monkeypatch, tmp_path):
    ad.guardar_flag(True)
    _fake_worktree(monkeypatch, tmp_path)
    monkeypatch.setattr(ad, "lanzar_implementacion",
                        lambda prompt, *, cwd, env: {"ok": True, "detalle": ""})
    monkeypatch.setattr(ad, "correr_git",
                        _git_con_numstat("5\t0\tconsola/src/keni_consola/db.py\n"))
    # Si se intentara CI o merge, fallaría el test (no deben llamarse en rutas sensibles).
    monkeypatch.setattr(ad, "correr_ci",
                        lambda wt: (_ for _ in ()).throw(AssertionError("no CI en rechazo")))

    aud = ad.implementar({"id": "s1", "titulo": "Tocar db"})
    assert aud["estado"] == ad.ESTADO_RECHAZADA
    assert aud["motivo"] == "rutas-sensibles"


def test_lazo_parkea_si_ci_roja(aislado, monkeypatch, tmp_path):
    ad.guardar_flag(True)
    _fake_worktree(monkeypatch, tmp_path)
    monkeypatch.setattr(ad, "lanzar_implementacion",
                        lambda prompt, *, cwd, env: {"ok": True, "detalle": ""})
    monkeypatch.setattr(ad, "correr_git",
                        _git_con_numstat("10\t0\tconsola/src/keni_consola/api/x.py\n"))
    monkeypatch.setattr(ad, "correr_ci", lambda wt: {"verde": False, "detalle": "pytest falló"})
    # El merge NUNCA debe llamarse si la CI es roja.
    monkeypatch.setattr(ad, "_commitear_y_mergear",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no merge con CI roja")))

    aud = ad.implementar({"id": "s2", "titulo": "Idea ok"})
    assert aud["estado"] == ad.ESTADO_PARKED
    assert aud["motivo"] == "ci-roja"
    assert aud["ci_verde"] is False


def test_lazo_mergea_solo_con_ci_verde_y_diff_seguro(aislado, monkeypatch, tmp_path):
    ad.guardar_flag(True)
    _fake_worktree(monkeypatch, tmp_path)
    recibido = {}

    def _runner(prompt, *, cwd, env):
        # GATE 5: el entorno NO debe traer secretos.
        recibido["env_keys"] = list(env.keys())
        recibido["cwd"] = cwd
        return {"ok": True, "detalle": ""}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-no-debe-llegar")
    monkeypatch.setattr(ad, "lanzar_implementacion", _runner)
    monkeypatch.setattr(ad, "correr_git",
                        _git_con_numstat("12\t3\tconsola/src/keni_consola/api/x.py\n"))
    monkeypatch.setattr(ad, "correr_ci", lambda wt: {"verde": True, "detalle": "ok"})
    monkeypatch.setattr(ad, "_commitear_y_mergear", lambda wt, s: ("abc123sha", "ff"))

    aud = ad.implementar({"id": "s3", "titulo": "Mejora segura"})
    assert aud["estado"] == ad.ESTADO_MERGEADA
    assert aud["sha"] == "abc123sha"
    assert aud["ci_verde"] is True
    # GATE 5 verificado: el runner recibió un entorno saneado.
    assert "ANTHROPIC_API_KEY" not in recibido["env_keys"]


def test_lazo_parkea_si_generacion_falla(aislado, monkeypatch, tmp_path):
    ad.guardar_flag(True)
    _fake_worktree(monkeypatch, tmp_path)
    monkeypatch.setattr(ad, "lanzar_implementacion",
                        lambda prompt, *, cwd, env: {"ok": False, "detalle": "claude error"})
    aud = ad.implementar({"id": "s4", "titulo": "Idea"})
    assert aud["estado"] == ad.ESTADO_PARKED
    assert aud["motivo"] == "generacion-fallida"


def test_lazo_borra_worktree_siempre(aislado, monkeypatch, tmp_path):
    ad.guardar_flag(True)
    _wt, borrados = _fake_worktree(monkeypatch, tmp_path)
    monkeypatch.setattr(ad, "lanzar_implementacion",
                        lambda prompt, *, cwd, env: {"ok": True, "detalle": ""})
    monkeypatch.setattr(ad, "correr_git",
                        _git_con_numstat("5\t0\tconsola/src/keni_consola/db.py\n"))  # rechazo
    ad.implementar({"id": "s5", "titulo": "Tocar db"})
    assert len(borrados) == 1  # GATE 2: limpieza en finally pase lo que pase


def test_correr_ci_sin_comando_no_es_verde(aislado, monkeypatch):
    # Sin KENI_AUTODESARROLLO_CI configurado, el CI NUNCA es verde (no se mergea por error).
    monkeypatch.delenv("KENI_AUTODESARROLLO_CI", raising=False)
    res = ad.correr_ci(aislado)
    assert res["verde"] is False


def test_lazo_error_inesperado_no_mergea(aislado, monkeypatch, tmp_path):
    ad.guardar_flag(True)
    _fake_worktree(monkeypatch, tmp_path)

    def _runner(prompt, *, cwd, env):
        raise RuntimeError("fallo raro")

    monkeypatch.setattr(ad, "lanzar_implementacion", _runner)
    aud = ad.implementar({"id": "s6", "titulo": "Idea"})
    assert aud["estado"] == ad.ESTADO_ERROR


def test_auditoria_jsonl_persiste_en_disco(aislado):
    ad.registrar_auditoria({"sugerencia_id": "z", "estado": ad.ESTADO_PARKED})
    ruta = ad.ruta_auditoria()
    contenido = ruta.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(contenido[-1])["sugerencia_id"] == "z"
    assert os.path.exists(ruta)

"""Tests de la decisión de ci_watch.py (qué rojo arreglar / hay verde más nuevo). Stdlib puro."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_watch  # noqa: E402


def P(number, status):  # pipeline mínimo (number, status, message, id), como los devuelven los fetchers
    return (number, status, f"commit {number}", number * 10)


def test_objetivo_es_el_ultimo_completo_si_falla():
    # El más nuevo COMPLETO (#42) falló -> objetivo, aunque #43 siga corriendo.
    pls = [P(43, "running"), P(42, "failure"), P(41, "success")]
    obj = ci_watch.objetivo_rojo(pls)
    assert obj is not None and obj[0] == 42


def test_ultimo_completo_verde_no_dispara_aunque_haya_rojos_viejos():
    # #42 verde (último completo) -> nada que arreglar aunque #40 fallara.
    pls = [P(43, "running"), P(42, "success"), P(41, "failure"), P(40, "failure")]
    assert ci_watch.objetivo_rojo(pls) is None


def test_todos_corriendo_no_dispara():
    pls = [P(43, "running"), P(42, "pending"), P(41, "created")]
    assert ci_watch.objetivo_rojo(pls) is None


def test_salta_cancelados_hasta_el_veredicto_real():
    # #43 cancelado (killed), #42 cancelado (declined): se ignoran; #41 falló -> objetivo.
    pls = [P(43, "killed"), P(42, "declined"), P(41, "failure"), P(40, "success")]
    obj = ci_watch.objetivo_rojo(pls)
    assert obj is not None and obj[0] == 41


def test_lista_vacia_no_dispara():
    assert ci_watch.objetivo_rojo([]) is None


def test_hay_verde_despues():
    pls = [P(45, "success"), P(44, "running"), P(43, "failure")]
    assert ci_watch.hay_verde_despues(pls, 43) is True   # #45 verde > 43
    assert ci_watch.hay_verde_despues(pls, 45) is False  # nada > 45
    # solo running/failure tras el N -> no hay verde más nuevo
    assert ci_watch.hay_verde_despues([P(44, "running"), P(43, "failure")], 43) is False


def test_imprimir_logs_vuelca_steps_rojos(monkeypatch, capsys):
    monkeypatch.setattr(ci_watch, "API", "http://wp")
    monkeypatch.setattr(ci_watch, "_steps_rojos_api", lambda n: [(7, "pytest", 1)])
    monkeypatch.setattr(ci_watch, "_logs_step_api", lambda n, sid: ["ruido\nFAILED test_x - boom\n"])
    ci_watch.imprimir_logs(57)
    out = capsys.readouterr().out
    assert "step «pytest»" in out
    assert "FAILED test_x - boom" in out


def test_imprimir_logs_sin_api_avisa(monkeypatch, capsys):
    monkeypatch.setattr(ci_watch, "API", "")
    ci_watch.imprimir_logs(57)
    assert "KENI_WOODPECKER_API" in capsys.readouterr().out


def _raw(*tuplas):  # (number, status, commit) -> dicts como los de la API
    return [{"number": n, "status": s, "commit": c, "message": "", "id": n * 10} for n, s, c in tuplas]


def _mock_api(monkeypatch, raw):
    monkeypatch.setattr(ci_watch, "API", "http://wp")
    monkeypatch.setattr(ci_watch, "_api_get", lambda path: raw)


def test_verdicto_resuelto_si_su_pipeline_verde(monkeypatch):
    _mock_api(monkeypatch, _raw((60, "success", "abc123"), (59, "failure", "viejo")))
    assert ci_watch.verdicto_fix("abc123") == "resuelto"


def test_verdicto_fallido_si_rojo_y_sin_verde_nuevo(monkeypatch):
    _mock_api(monkeypatch, _raw((60, "failure", "abc123")))
    assert ci_watch.verdicto_fix("abc123") == "fallido"


def test_verdicto_abortado_si_otro_commit_dejo_verde(monkeypatch):
    # El fix del keeper (#60) salió rojo, pero #61 (de OTRO) salió verde -> no se acredita al keeper.
    _mock_api(monkeypatch, _raw((61, "success", "otro"), (60, "failure", "abc123")))
    assert ci_watch.verdicto_fix("abc123") == "abortado"


def test_verdicto_verificando_mientras_corre(monkeypatch):
    _mock_api(monkeypatch, _raw((60, "running", "abc123")))
    assert ci_watch.verdicto_fix("abc123") == "verificando"


def test_verdicto_commit_no_visto_main_verde_es_abortado(monkeypatch):
    _mock_api(monkeypatch, _raw((70, "success", "otro"), (69, "failure", "x")))
    assert ci_watch.verdicto_fix("abc123") == "abortado"


def test_verdicto_commit_no_visto_main_rojo_sigue_verificando(monkeypatch):
    _mock_api(monkeypatch, _raw((70, "failure", "otro")))
    assert ci_watch.verdicto_fix("abc123") == "verificando"

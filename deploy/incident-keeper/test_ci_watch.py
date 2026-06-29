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


def test_ultimo_completado_es_la_salud_de_main():
    # El #63 corre; el último con VEREDICTO es el #62 (verde) -> esa es la salud de main.
    assert ci_watch.ultimo_completado([P(63, "running"), P(62, "success"), P(61, "failure")])[0] == 62
    assert ci_watch.ultimo_completado([P(63, "running"), P(62, "pending")]) is None


def test_origen_rojo_es_el_primer_rojo_de_la_racha():
    # #66 y #65 rojos, #64 verde: el ORIGEN es #65 (el primero tras el verde), NO el último #66.
    pls = [P(68, "running"), P(67, "running"), P(66, "failure"), P(65, "failure"), P(64, "success")]
    obj = ci_watch.origen_rojo(pls)
    assert obj is not None and obj[0] == 65


def test_origen_rojo_un_solo_rojo():
    # Una sola racha de un rojo: el origen es ese mismo.
    assert ci_watch.origen_rojo([P(43, "running"), P(42, "failure"), P(41, "success")])[0] == 42


def test_origen_rojo_main_verde_es_none():
    # El último completo está verde -> main sano, no hay racha que arreglar (aunque haya rojos viejos).
    assert ci_watch.origen_rojo([P(43, "success"), P(42, "failure"), P(41, "failure")]) is None


def test_origen_rojo_ignora_cancelados_entre_medias():
    # Los killed/declined no son veredicto: la racha roja real es #66<-#65; #64 verde corta -> #65.
    pls = [P(67, "killed"), P(66, "failure"), P(65, "failure"), P(64, "success"), P(63, "failure")]
    assert ci_watch.origen_rojo(pls)[0] == 65


def test_origen_rojo_ventana_toda_roja():
    # Sin ningún verde en la ventana: devuelve el más viejo disponible (mejor aproximación al origen).
    assert ci_watch.origen_rojo([P(66, "failure"), P(65, "failure"), P(64, "failure")])[0] == 64


def test_origen_rojo_lista_vacia():
    assert ci_watch.origen_rojo([]) is None


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


def test_huella_estable_e_independiente_del_orden():
    # Mismo CONJUNTO de fallos (en otro orden, con duplicados) -> misma huella.
    h1 = ci_watch.huella_fallos(["[pytest] FAILED a", "[pytest] FAILED b"])
    h2 = ci_watch.huella_fallos(["[pytest] FAILED b", "[pytest] FAILED a", "[pytest] FAILED a"])
    assert h1 and h1 == h2
    # Conjuntos distintos -> huellas distintas; vacío -> "".
    assert ci_watch.huella_fallos(["FAILED x"]) != ci_watch.huella_fallos(["FAILED y"])
    assert ci_watch.huella_fallos([]) == ""

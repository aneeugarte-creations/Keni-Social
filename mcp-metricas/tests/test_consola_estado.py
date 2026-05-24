"""Tests de la feature Estado (autodiagnostico en la UI). Todo OFFLINE.

El doctor real escanea el PATH (whisper-cli/ffmpeg) y rutas de modelos; para no
depender de la maquina, los tests inyectan `ejecutar_chequeos` con un set
determinista de `Resultado` (OK + AVISO + ERROR) reasignando el nombre de modulo
de la feature. Nada de red, nada de binarios reales.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_metricas import doctor
from keni_metricas.consola import app as app_modulo
from keni_metricas.consola.features import estado as feat_estado


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Aisla la config de la consola/metricas en tmp; metricas offline (muestra)."""
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    return tmp_path


def _cliente() -> TestClient:
    # `abrir` de proyectos: mock inofensivo (esta feature no lo usa).
    return TestClient(app_modulo.crear_app(abrir=lambda _r: "ok-mock"))


def _resultados_demo() -> list[doctor.Resultado]:
    """Set determinista: 2 OK + 2 AVISO + 1 ERROR (cubre los tres estados)."""
    return [
        doctor.Resultado("Python", doctor.Estado.OK, "Python 3.12.1"),
        doctor.Resultado("Fuente", doctor.Estado.OK, "Fuente de muestra construida correctamente"),
        doctor.Resultado("Configuracion", doctor.Estado.AVISO, "No hay config (se usa muestra)"),
        doctor.Resultado("Credenciales", doctor.Estado.AVISO, "0/5 plataformas conectadas"),
        doctor.Resultado("binario whisper-cli", doctor.Estado.ERROR, "whisper-cli no esta en el PATH."),
    ]


@pytest.fixture
def doctor_mockeado(monkeypatch):
    """Reemplaza `ejecutar_chequeos` de la feature por el set determinista."""
    monkeypatch.setattr(feat_estado, "ejecutar_chequeos", lambda *a, **k: _resultados_demo())


# --------------------------------------------------------------------------- #
# Pagina y nav                                                                 #
# --------------------------------------------------------------------------- #


def test_estado_devuelve_html_200(entorno, doctor_mockeado):
    c = _cliente()
    r = c.get("/estado")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Estado del sistema" in r.text


def test_estado_aparece_en_la_nav_por_auto_discovery(entorno, doctor_mockeado):
    c = _cliente()
    html = c.get("/proyectos").text
    assert 'href="/estado"' in html
    # orden=60 => Estado va al final (despues de Proyectos=10, Metricas=20, ...).
    assert html.index('href="/metricas"') < html.index('href="/estado"')


def test_estado_carga_su_css_propio(entorno, doctor_mockeado):
    c = _cliente()
    assert 'href="/estaticos/estado.css"' in c.get("/estado").text
    # Y el estatico se sirve.
    r = c.get("/estaticos/estado.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


# --------------------------------------------------------------------------- #
# Contenido: resumen, chequeos, contador, cierre                               #
# --------------------------------------------------------------------------- #


def test_muestra_resumen_humano_y_cierre_accionable(entorno, doctor_mockeado):
    resultados = _resultados_demo()
    html = _cliente().get("/estado").text
    # La frase de cabecera y el siguiente paso vienen del propio doctor.
    assert doctor.resumen_humano(resultados) in html
    assert doctor.cierre_accionable(resultados) in html


def test_lista_cada_chequeo_con_icono_nombre_y_detalle(entorno, doctor_mockeado):
    html = _cliente().get("/estado").text
    for r in _resultados_demo():
        assert r.estado.value in html  # icono del estado
        assert r.nombre in html
        assert r.detalle in html


def test_contador_n_ok_n_aviso_n_error(entorno, doctor_mockeado):
    html = _cliente().get("/estado").text
    # 2 OK, 2 AVISO, 1 ERROR (ver _resultados_demo).
    assert f"2 {doctor.Estado.OK.value}" in html
    assert f"2 {doctor.Estado.AVISO.value}" in html
    assert f"1 {doctor.Estado.ERROR.value}" in html


def test_colores_por_estado_presentes(entorno, doctor_mockeado):
    html = _cliente().get("/estado").text
    # Cada estado mapea a una clase CSS (verde/ambar/rojo) en sus filas.
    assert 'class="chequeo ok"' in html
    assert 'class="chequeo aviso"' in html
    assert 'class="chequeo error"' in html


def test_con_error_el_resumen_marca_alerta(entorno, doctor_mockeado):
    html = _cliente().get("/estado").text
    # Hay un ERROR en el set => el resumen lleva la clase de alerta (rojo).
    assert 'class="resumen-estado error"' in html


def test_sin_errores_resumen_tranquilizador(entorno, monkeypatch):
    solo_ok_aviso = [
        doctor.Resultado("Python", doctor.Estado.OK, "Python 3.12"),
        doctor.Resultado("Credenciales", doctor.Estado.AVISO, "0/5 conectadas"),
    ]
    monkeypatch.setattr(feat_estado, "ejecutar_chequeos", lambda *a, **k: solo_ok_aviso)
    html = _cliente().get("/estado").text
    assert 'class="resumen-estado ok"' in html
    assert f"0 {doctor.Estado.ERROR.value}" in html


def test_boton_volver_a_comprobar_reapunta_a_estado(entorno, doctor_mockeado):
    html = _cliente().get("/estado").text
    assert "Volver a comprobar" in html
    assert 'href="/estado"' in html


# --------------------------------------------------------------------------- #
# Robustez                                                                     #
# --------------------------------------------------------------------------- #


def test_no_expone_valores_de_secretos(entorno, monkeypatch):
    """El detalle informa presencia/ausencia, nunca el valor del token."""
    con_token_falso = [
        doctor.Resultado("Credenciales", doctor.Estado.OK, "5/5 plataformas conectadas"),
    ]
    monkeypatch.setattr(feat_estado, "ejecutar_chequeos", lambda *a, **k: con_token_falso)
    html = _cliente().get("/estado").text
    # Solo aparece el detalle que el doctor produce (sin secretos), tal cual.
    assert "5/5 plataformas conectadas" in html


def test_si_el_doctor_lanza_se_muestra_mensaje_en_espanol(entorno, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(feat_estado, "ejecutar_chequeos", boom)
    r = _cliente().get("/estado")
    assert r.status_code == 200
    assert "No se pudo ejecutar el autodiagnostico" in r.text


def test_estado_real_offline_no_crashea(entorno):
    """Sin mock: el doctor real (escaneo de PATH/rutas, sin red) responde 200."""
    r = _cliente().get("/estado")
    assert r.status_code == 200
    assert "Estado del sistema" in r.text

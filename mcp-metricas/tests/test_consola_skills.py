"""Tests de la feature Skills (Generar copy) de la Consola Keni. Todo OFFLINE.

NUNCA se llama a `claude` real: el runner que invoca al binario se PARCHEA en cada
test (o se inyecta). Se verifica: GET /skills lista skills + marcas; POST ejecutar
con runner mockeado devuelve el resultado y se llamo con el prompt/marca correctos;
skill (y marca) fuera de allowlist -> 400; fallos del runner -> mensaje en espanol.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_metricas.consola import app as app_modulo
from keni_metricas.consola.features import skills as feat_skills


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Config aislada en tmp; fuerza un cwd de skills valido (no toca el real)."""
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    monkeypatch.setenv("KENI_SKILLS_CWD", str(tmp_path))
    return tmp_path


def _cliente() -> TestClient:
    return TestClient(app_modulo.crear_app())


# --------------------------------------------------------------------------- #
# GET /skills: pagina, allowlist visible, aviso, sin recursos externos         #
# --------------------------------------------------------------------------- #


def test_get_skills_devuelve_html_200(entorno):
    c = _cliente()
    r = c.get("/skills")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_get_skills_lista_todas_las_skills_de_la_allowlist(entorno):
    c = _cliente()
    texto = c.get("/skills").text
    for s in feat_skills.SKILLS:
        assert s.id in texto
        assert s.nombre in texto
        assert s.descripcion in texto


def test_get_skills_lista_todas_las_marcas(entorno):
    c = _cliente()
    texto = c.get("/skills").text
    for mid, mnombre in feat_skills.MARCAS:
        assert mid in texto
        assert mnombre in texto


def test_get_skills_muestra_nombre_humano_no_solo_slug(entorno):
    """La ETIQUETA visible es el nombre humano legible; el VALUE sigue siendo el slug.

    UX1 (QA #69): el equipo ve los mismos nombres de marca en Skills y Metricas.
    """
    c = _cliente()
    texto = c.get("/skills").text
    # Etiqueta humana visible (con acentos donde toca).
    assert "Claro Sports" in texto
    assert "Nación Gamer" in texto
    assert "Fundación" in texto
    # El value interno (slug-guion) que Skills envia a Claude se mantiene.
    assert 'value="claro-sports"' in texto
    assert 'value="nacion-gamer"' in texto
    assert 'value="fundacion"' in texto


def test_marcas_usan_acentos_en_la_etiqueta(entorno):
    """El mapeo de marcas trae nombres humanos legibles (no slugs crudos)."""
    nombres = dict(feat_skills.MARCAS)
    assert nombres["nacion-gamer"] == "Nación Gamer"
    assert nombres["fundacion"] == "Fundación"
    assert nombres["claro-sports"] == "Claro Sports"


def test_get_skills_muestra_aviso_no_publica(entorno):
    c = _cliente()
    texto = c.get("/skills").text
    assert "Nada se publica" in texto


def test_skills_aparece_en_la_nav(entorno):
    c = _cliente()
    # Su pestana aparece en la nav de otras paginas, sin tocar app.py.
    assert 'href="/skills"' in c.get("/proyectos").text
    assert "Generar copy" in c.get("/skills").text


def test_skills_no_referencia_recursos_externos(entorno):
    c = _cliente()
    texto = c.get("/skills").text.lower()
    assert "https://" not in texto
    assert "cdn" not in texto


def test_skills_ofrece_copiar_y_descargar_el_borrador(entorno):
    """Tras generar, la UI ofrece Copiar (portapapeles) y Descargar (Blob en cliente)."""
    c = _cliente()
    texto = c.get("/skills").text
    assert 'id="skills-copiar"' in texto
    assert "Copiar" in texto
    assert 'id="skills-descargar"' in texto
    assert "Descargar" in texto
    # La logica de copiar/descargar vive en el JS propio de skills (cliente).
    js = c.get("/estaticos/skills.js").text
    assert "navigator.clipboard" in js
    assert "Blob" in js


def test_estaticos_propios_de_skills_servidos(entorno):
    c = _cliente()
    css = c.get("/estaticos/skills.css")
    js = c.get("/estaticos/skills.js")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]


# --------------------------------------------------------------------------- #
# POST /api/skills/ejecutar: runner MOCKEADO (jamas claude real)               #
# --------------------------------------------------------------------------- #


def test_ejecutar_con_runner_mockeado_devuelve_resultado_y_prompt_correcto(entorno, monkeypatch):
    llamadas = []

    def ejecutar_mock(skill, marca, texto, **kw):
        llamadas.append((skill, marca, texto))
        # Validamos que el prompt se construye como espera el contrato.
        prompt = feat_skills.construir_prompt(skill, marca, texto)
        assert prompt == "usa copy-desde-nota con la siguiente nota, marca unotv:\n\nMi nota original."
        return "BORRADOR GENERADO (mock)"

    monkeypatch.setattr(feat_skills, "ejecutar_skill", ejecutar_mock)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "Mi nota original."},
    )
    assert r.status_code == 200
    assert r.json()["resultado"] == "BORRADOR GENERADO (mock)"
    assert llamadas == [("copy-desde-nota", "unotv", "Mi nota original.")]


def test_ejecutar_llama_al_runner_inyectado_con_el_prompt(entorno):
    """Probamos `ejecutar_skill` directamente con un runner inyectado (sin claude)."""
    capturado = {}

    def runner_mock(prompt, *, cwd, timeout):
        capturado["prompt"] = prompt
        capturado["timeout"] = timeout
        return "salida del runner"

    resultado = feat_skills.ejecutar_skill(
        "nota-a-hilo", "claro-sports", "texto de prueba", runner=runner_mock
    )
    assert resultado == "salida del runner"
    assert capturado["prompt"] == "usa nota-a-hilo con la siguiente nota, marca claro-sports:\n\ntexto de prueba"
    assert capturado["timeout"] > 0


def test_runner_real_no_se_invoca_en_ningun_test():
    """El runner por defecto solo se usa si NO se inyecta; aqui inyectamos siempre."""
    centinela = {"llamado": False}

    def runner_mock(prompt, *, cwd, timeout):
        centinela["llamado"] = True
        return "ok"

    feat_skills.ejecutar_skill("clip-a-copy", "piso-15", "x", runner=runner_mock)
    assert centinela["llamado"] is True


# --------------------------------------------------------------------------- #
# Allowlist + validacion: skill/marca invalidas -> 400 (sin ejecutar nada)     #
# --------------------------------------------------------------------------- #


def test_skill_fuera_de_allowlist_da_400_sin_ejecutar(entorno, monkeypatch):
    llamadas = []
    monkeypatch.setattr(feat_skills, "ejecutar_skill", lambda *a, **k: llamadas.append(a) or "x")
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar",
        json={"skill": "rm-rf-todo", "marca": "unotv", "texto": "hola"},
    )
    assert r.status_code == 400
    assert "no permitida" in r.json()["error"].lower()
    assert llamadas == []  # NO se intento ejecutar nada


def test_marca_fuera_de_allowlist_da_400(entorno):
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "marca-falsa", "texto": "hola"},
    )
    assert r.status_code == 400
    assert "no permitida" in r.json()["error"].lower()


def test_texto_vacio_da_400(entorno):
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "   "},
    )
    assert r.status_code == 400
    assert "nota" in r.json()["error"].lower()


def test_faltan_campos_da_400(entorno):
    c = _cliente()
    r = c.post("/api/skills/ejecutar", json={"skill": "copy-desde-nota"})
    assert r.status_code == 400
    assert "faltan" in r.json()["error"].lower()


def test_ejecutar_skill_valida_allowlist_directamente():
    with pytest.raises(feat_skills.SkillError, match="Skill no permitida"):
        feat_skills.ejecutar_skill("inventada", "unotv", "x", runner=lambda *a, **k: "y")
    with pytest.raises(feat_skills.SkillError, match="Marca no permitida"):
        feat_skills.ejecutar_skill("copy-desde-nota", "ninguna", "x", runner=lambda *a, **k: "y")


# --------------------------------------------------------------------------- #
# Manejo de errores del motor: el runner falla -> mensaje en espanol, no traza #
# --------------------------------------------------------------------------- #


def test_runner_lanza_error_devuelve_mensaje_espanol_500(entorno, monkeypatch):
    def ejecutar_explota(skill, marca, texto, **kw):
        raise feat_skills.SkillError("Claude termino con error: detalle tecnico.")

    monkeypatch.setattr(feat_skills, "ejecutar_skill", ejecutar_explota)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "hola"},
    )
    assert r.status_code == 500
    cuerpo = r.json()
    assert "error" in cuerpo
    assert "Claude termino con error" in cuerpo["error"]
    # Nunca un traceback crudo.
    assert "Traceback" not in cuerpo["error"]


def test_error_inesperado_no_filtra_traceback(entorno, monkeypatch):
    def ejecutar_revienta(skill, marca, texto, **kw):
        raise RuntimeError("boom interno con detalles feos")

    monkeypatch.setattr(feat_skills, "ejecutar_skill", ejecutar_revienta)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "hola"},
    )
    assert r.status_code == 500
    assert r.json()["error"] == "No se pudo generar el borrador."


def test_runner_timeout_da_mensaje_espanol(monkeypatch):
    """Simula el timeout del subprocess sin llamar a claude: parchea subprocess.run."""
    import subprocess

    def fake_which(_name):
        return "/usr/bin/claude"

    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=k.get("timeout", 1))

    monkeypatch.setattr(feat_skills.shutil, "which", fake_which)
    monkeypatch.setattr(feat_skills.subprocess, "run", fake_run)
    with pytest.raises(feat_skills.SkillError, match="tardo demasiado"):
        feat_skills.ejecutar_skill("copy-desde-nota", "unotv", "hola", timeout=1)


def test_claude_no_encontrado_da_mensaje_espanol(monkeypatch):
    """Si `claude` no esta en el PATH, mensaje claro en espanol (sin ejecutar)."""
    monkeypatch.setattr(feat_skills.shutil, "which", lambda _n: None)
    with pytest.raises(feat_skills.SkillError, match="No se encontro el comando 'claude'"):
        feat_skills.ejecutar_skill("copy-desde-nota", "unotv", "hola")


def test_runner_rc_distinto_de_cero_da_mensaje(monkeypatch):
    """rc != 0 => error en espanol con el stderr, sin shell, sin traceback."""

    class FakeProc:
        returncode = 2
        stdout = ""
        stderr = "algo fallo en la skill"

    monkeypatch.setattr(feat_skills.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(feat_skills.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(feat_skills.SkillError, match="Claude termino con error"):
        feat_skills.ejecutar_skill("copy-desde-nota", "unotv", "hola")


def test_runner_usa_argv_sin_shell(monkeypatch):
    """Verifica que el binario se invoca con lista argv (sin shell=True)."""
    capturado = {}

    class FakeProc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kw):
        capturado["cmd"] = cmd
        capturado["shell"] = kw.get("shell", False)
        return FakeProc()

    monkeypatch.setattr(feat_skills.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(feat_skills.subprocess, "run", fake_run)
    feat_skills.ejecutar_skill("copy-desde-nota", "unotv", "una nota; rm -rf /")
    assert isinstance(capturado["cmd"], list)
    assert capturado["cmd"][0] == "claude"
    assert capturado["cmd"][1] == "-p"
    # El texto peligroso va como UN argumento, nunca interpretado por shell.
    assert "una nota; rm -rf /" in capturado["cmd"][2]
    assert capturado["shell"] is False

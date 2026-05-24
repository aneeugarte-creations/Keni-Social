"""Tests de la feature Skills (Generar copy) de la Consola Keni. Todo OFFLINE.

NUNCA se llama a `claude` real: el runner que invoca al binario se PARCHEA en cada
test (o se inyecta). Se verifica: GET /skills lista skills + marcas; POST ejecutar
con runner mockeado devuelve el resultado y se llamo con el prompt/marca correctos;
skill (y marca) fuera de allowlist -> 400; fallos del runner -> mensaje en espanol.
"""

from __future__ import annotations

from pathlib import Path

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


def test_get_skills_incluye_youtube_metadata(entorno):
    """El tipo de contenido `youtube-metadata` esta curado y visible en la lista."""
    ids = {s.id for s in feat_skills.SKILLS}
    assert "youtube-metadata" in ids
    c = _cliente()
    texto = c.get("/skills").text
    assert 'value="youtube-metadata"' in texto
    # Su nombre humano (de-jergonizado) aparece, no el slug crudo a secas.
    info = next(s for s in feat_skills.SKILLS if s.id == "youtube-metadata")
    assert info.nombre in texto
    assert info.descripcion in texto


# --------------------------------------------------------------------------- #
# Render AGRUPADO: validadas vs experimentales (optgroup en el select)          #
# --------------------------------------------------------------------------- #


def test_grupos_skills_cubren_exactamente_la_lista_plana():
    """La vista plana SKILLS es la union (en orden) de los grupos, sin drift."""
    plana = tuple(s.id for s in feat_skills.SKILLS)
    de_grupos = tuple(s.id for g in feat_skills.GRUPOS_SKILLS for s in g.skills)
    assert plana == de_grupos
    # No hay ids repetidos entre grupos.
    assert len(plana) == len(set(plana))


def test_grupos_son_dos_validadas_y_experimentales():
    """Hay exactamente dos grupos: uno validado y otro experimental."""
    etiquetas = [g.etiqueta for g in feat_skills.GRUPOS_SKILLS]
    assert len(feat_skills.GRUPOS_SKILLS) == 2
    assert any("Validadas" in e for e in etiquetas)
    assert any("Experimentales" in e for e in etiquetas)
    experimentales = [g for g in feat_skills.GRUPOS_SKILLS if g.experimental]
    assert len(experimentales) == 1
    assert "Experimentales" in experimentales[0].etiqueta


def test_cada_skill_cae_en_su_grupo_correcto():
    """Las validadas y las experimentales estan en el grupo que les toca."""
    por_grupo = {g.etiqueta: {s.id for s in g.skills} for g in feat_skills.GRUPOS_SKILLS}
    validadas = next(ids for et, ids in por_grupo.items() if "Validadas" in et)
    experimentales = next(ids for et, ids in por_grupo.items() if "Experimentales" in et)

    assert validadas == {
        "copy-desde-nota",
        "clip-a-copy",
        "nota-a-formato",
        "resumen-tendencia",
        "youtube-metadata",
    }
    assert experimentales == {
        "nota-a-hilo",
        "calendario-editorial",
        "responde-comentarios",
    }
    # Disjuntos: ninguna skill esta en ambos grupos.
    assert validadas.isdisjoint(experimentales)


def test_get_skills_render_agrupado_con_optgroups(entorno):
    """El <select> trae un <optgroup> por grupo, con sus labels visibles."""
    c = _cliente()
    texto = c.get("/skills").text
    assert '<optgroup label="Validadas con el equipo">' in texto
    assert '<optgroup label="Experimentales (no validadas con el piloto)">' in texto
    # Las experimentales se etiquetan como tales en el propio label del grupo.
    assert "Experimentales" in texto
    assert "no validadas con el piloto" in texto


def test_get_skills_cada_skill_dentro_de_su_optgroup(entorno):
    """Cada <option> aparece DENTRO del <optgroup> de su grupo (no traspapelada)."""
    import re

    c = _cliente()
    texto = c.get("/skills").text
    # Trozos por optgroup: del label de cada grupo hasta su </optgroup>.
    grupos = re.findall(r'<optgroup label="([^"]+)">(.*?)</optgroup>', texto, re.DOTALL)
    bloques = dict(grupos)
    val = next(html for et, html in grupos if "Validadas" in et)
    exp = next(html for et, html in grupos if "Experimentales" in et)
    assert len(bloques) == 2

    for sid in ("copy-desde-nota", "clip-a-copy", "youtube-metadata"):
        assert f'value="{sid}"' in val
        assert f'value="{sid}"' not in exp
    for sid in ("nota-a-hilo", "calendario-editorial", "responde-comentarios"):
        assert f'value="{sid}"' in exp
        assert f'value="{sid}"' not in val


# --------------------------------------------------------------------------- #
# Drift: cada tipo de contenido listado DEBE existir como carpeta en disco     #
# --------------------------------------------------------------------------- #


def _dir_skills_curadas() -> Path:
    """Ruta a las skills curadas del repo: <repo>/skills-copy/.claude/skills/.

    El test vive en <repo>/mcp-metricas/tests/, asi que el repo esta tres niveles
    por encima. La fuente de las carpetas es la copia versionada en el repo."""
    repo = Path(__file__).resolve().parent.parent.parent
    return repo / "skills-copy" / ".claude" / "skills"


def test_skills_listadas_existen_como_carpeta_en_disco():
    """Anti-drift: si la consola lista un tipo de contenido cuyo `id` NO existe
    como carpeta en skills-copy/.claude/skills/, este test falla. Asi la lista
    curada nunca ofrece un tipo de contenido que el asistente no sabe ejecutar."""
    dir_skills = _dir_skills_curadas()
    assert dir_skills.is_dir(), (
        f"No se encontro el directorio de skills curadas: {dir_skills}"
    )
    carpetas = {p.name for p in dir_skills.iterdir() if p.is_dir()}
    faltantes = sorted(s.id for s in feat_skills.SKILLS if s.id not in carpetas)
    assert not faltantes, (
        "Tipos de contenido listados en la consola sin carpeta en "
        f"skills-copy/.claude/skills/: {faltantes}. Crea la carpeta o quita el tipo "
        "de la lista curada (SKILLS) para arreglar el drift."
    )


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
    assert "no permitido" in r.json()["error"].lower()
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
    with pytest.raises(feat_skills.SkillError, match="Tipo de contenido no permitido"):
        feat_skills.ejecutar_skill("inventada", "unotv", "x", runner=lambda *a, **k: "y")
    with pytest.raises(feat_skills.SkillError, match="Marca no permitida"):
        feat_skills.ejecutar_skill("copy-desde-nota", "ninguna", "x", runner=lambda *a, **k: "y")


# --------------------------------------------------------------------------- #
# Manejo de errores del motor: el runner falla -> mensaje en espanol, no traza #
# --------------------------------------------------------------------------- #


def test_runner_lanza_error_devuelve_mensaje_espanol_500(entorno, monkeypatch):
    def ejecutar_explota(skill, marca, texto, **kw):
        raise feat_skills.SkillError("El asistente terminó con error: detalle técnico.")

    monkeypatch.setattr(feat_skills, "ejecutar_skill", ejecutar_explota)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "hola"},
    )
    assert r.status_code == 500
    cuerpo = r.json()
    assert "error" in cuerpo
    assert "El asistente terminó con error" in cuerpo["error"]
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
    with pytest.raises(feat_skills.SkillError, match="tardó demasiado"):
        feat_skills.ejecutar_skill("copy-desde-nota", "unotv", "hola", timeout=1)


def test_claude_no_encontrado_da_mensaje_espanol(monkeypatch):
    """Si `claude` no esta en el PATH, mensaje claro en espanol (sin ejecutar)."""
    monkeypatch.setattr(feat_skills.shutil, "which", lambda _n: None)
    with pytest.raises(feat_skills.SkillError, match="No se encontró el asistente"):
        feat_skills.ejecutar_skill("copy-desde-nota", "unotv", "hola")


def test_runner_rc_distinto_de_cero_da_mensaje(monkeypatch):
    """rc != 0 => error en espanol con el stderr, sin shell, sin traceback."""

    class FakeProc:
        returncode = 2
        stdout = ""
        stderr = "algo fallo en la skill"

    monkeypatch.setattr(feat_skills.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(feat_skills.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(feat_skills.SkillError, match="El asistente terminó con error"):
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


# --------------------------------------------------------------------------- #
# SUBIR ARCHIVO (multipart): GET muestra el input; POST con runner MOCKEADO     #
# --------------------------------------------------------------------------- #


def test_get_skills_muestra_input_de_archivo(entorno):
    """La pagina ofrece subir un archivo como alternativa a pegar texto."""
    c = _cliente()
    texto = c.get("/skills").text
    assert 'type="file"' in texto
    assert 'name="archivo"' in texto
    assert 'id="skills-archivo"' in texto
    # UX: deja claro "pega texto O sube un archivo".
    bajo = texto.lower()
    assert "sube un archivo" in bajo
    # Sigue el aviso "nada se publica".
    assert "Nada se publica" in texto


def test_subir_archivo_texto_lee_contenido_y_llama_al_runner(entorno, monkeypatch):
    """Skill de texto: se LEE el contenido del archivo y se pasa como nota al runner."""
    capturado = {}

    def runner_mock(prompt, *, cwd, timeout):
        capturado["prompt"] = prompt
        return "BORRADOR (mock archivo)"

    monkeypatch.setattr(feat_skills, "_runner", runner_mock)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv"},
        files={"archivo": ("nota.txt", b"Contenido de mi nota subida.", "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["resultado"] == "BORRADOR (mock archivo)"
    # El prompt es el de TEXTO (nota), con el contenido del archivo incrustado.
    assert capturado["prompt"] == (
        "usa copy-desde-nota con la siguiente nota, marca unotv:\n\nContenido de mi nota subida."
    )


def test_subir_archivo_media_clip_a_copy_pasa_la_ruta_al_prompt(entorno, monkeypatch):
    """clip-a-copy es MEDIA: al runner le llega la RUTA temporal, no el contenido."""
    capturado = {}

    def runner_mock(prompt, *, cwd, timeout):
        capturado["prompt"] = prompt
        return "BORRADOR (mock media)"

    monkeypatch.setattr(feat_skills, "_runner", runner_mock)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "clip-a-copy", "marca": "claro-sports"},
        files={"archivo": ("entrevista.mp4", b"\x00\x01\x02 binario de video", "video/mp4")},
    )
    assert r.status_code == 200
    assert r.json()["resultado"] == "BORRADOR (mock media)"
    # El prompt referencia una RUTA (temporal, con la extension saneada .mp4).
    assert capturado["prompt"].startswith(
        "usa clip-a-copy con el archivo en esta ruta, marca claro-sports:\n\n"
    )
    ruta = capturado["prompt"].split("\n\n", 1)[1]
    assert ruta.endswith(".mp4")
    # NO se uso el nombre crudo del cliente como nombre de archivo.
    assert "entrevista.mp4" not in ruta


def test_subir_archivo_no_usa_el_nombre_crudo_del_cliente(entorno, monkeypatch):
    """Nombre saneado: un filename con path traversal NO aparece en la ruta temporal."""
    capturado = {}

    def runner_mock(prompt, *, cwd, timeout):
        capturado["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(feat_skills, "_runner", runner_mock)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "clip-a-copy", "marca": "unotv"},
        files={"archivo": ("../../etc/evil.mp4", b"datos", "video/mp4")},
    )
    assert r.status_code == 200
    ruta = capturado["prompt"].split("\n\n", 1)[1]
    assert ".." not in ruta
    assert "etc" not in ruta
    assert "evil" not in ruta
    assert ruta.endswith(".mp4")  # conserva solo la extension saneada


def test_subir_archivo_demasiado_grande_da_400_en_espanol(entorno, monkeypatch):
    """Excede el limite -> 400 con mensaje en espanol; el runner NO se llama."""
    llamado = {"runner": False}

    def runner_mock(prompt, *, cwd, timeout):
        llamado["runner"] = True
        return "no deberia"

    # Limite ridiculo para forzar el rechazo sin subir megas.
    monkeypatch.setattr(feat_skills, "_MAX_SUBIDA_TEXTO", 10)
    monkeypatch.setattr(feat_skills, "_runner", runner_mock)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv"},
        files={"archivo": ("nota.txt", b"x" * 1000, "text/plain")},
    )
    assert r.status_code == 400
    assert "demasiado grande" in r.json()["error"].lower()
    assert llamado["runner"] is False


def test_subir_archivo_vacio_da_400(entorno, monkeypatch):
    monkeypatch.setattr(feat_skills, "_runner", lambda *a, **k: "x")
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv"},
        files={"archivo": ("vacio.txt", b"", "text/plain")},
    )
    assert r.status_code == 400
    assert "vacío" in r.json()["error"].lower()


def test_sin_archivo_ni_texto_da_400(entorno):
    """Multipart sin la parte 'archivo' -> 400 en espanol (no 500, no traza)."""
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv"},
    )
    assert r.status_code == 400
    assert "archivo" in r.json()["error"].lower()


def test_subir_archivo_skill_fuera_de_allowlist_da_400(entorno, monkeypatch):
    llamado = {"runner": False}
    monkeypatch.setattr(
        feat_skills, "_runner", lambda *a, **k: llamado.__setitem__("runner", True) or "x"
    )
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "rm-rf-todo", "marca": "unotv"},
        files={"archivo": ("nota.txt", b"hola", "text/plain")},
    )
    assert r.status_code == 400
    assert "no permitido" in r.json()["error"].lower()
    assert llamado["runner"] is False


def test_subir_archivo_marca_fuera_de_allowlist_da_400(entorno):
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "marca-falsa"},
        files={"archivo": ("nota.txt", b"hola", "text/plain")},
    )
    assert r.status_code == 400
    assert "no permitida" in r.json()["error"].lower()


def test_subir_archivo_limpia_el_temporal(entorno, monkeypatch):
    """Tras procesar, el dir temporal de la subida se borra (no quedan residuos)."""
    capturado = {}

    def runner_mock(prompt, *, cwd, timeout):
        # En este momento la ruta TODAVIA existe (estamos procesando).
        ruta = Path(prompt.split("\n\n", 1)[1])
        capturado["ruta"] = ruta
        capturado["existia_durante"] = ruta.exists()
        capturado["dir"] = ruta.parent
        return "ok"

    monkeypatch.setattr(feat_skills, "_runner", runner_mock)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "clip-a-copy", "marca": "unotv"},
        files={"archivo": ("clip.mp4", b"datos", "video/mp4")},
    )
    assert r.status_code == 200
    assert capturado["existia_durante"] is True
    # Tras la respuesta, el temporal (y su dir) ya no existen.
    assert not capturado["ruta"].exists()
    assert not capturado["dir"].exists()


def test_subir_archivo_error_del_motor_limpia_y_da_500(entorno, monkeypatch):
    """Si el runner falla, el temporal se limpia igual y el error sale en espanol."""
    capturado = {}

    def runner_explota(prompt, *, cwd, timeout):
        capturado["dir"] = Path(prompt.split("\n\n", 1)[1]).parent
        raise feat_skills.SkillError("El asistente terminó con error: detalle.")

    monkeypatch.setattr(feat_skills, "_runner", runner_explota)
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "clip-a-copy", "marca": "unotv"},
        files={"archivo": ("clip.mp4", b"datos", "video/mp4")},
    )
    assert r.status_code == 500
    assert "El asistente terminó con error" in r.json()["error"]
    assert "Traceback" not in r.json()["error"]
    # Limpieza garantizada incluso ante fallo del motor.
    assert not capturado["dir"].exists()


def test_construir_prompt_ruta_referencia_la_ruta():
    prompt = feat_skills.construir_prompt_ruta("clip-a-copy", "unotv", "/tmp/x/abc.mp4")
    assert prompt == "usa clip-a-copy con el archivo en esta ruta, marca unotv:\n\n/tmp/x/abc.mp4"


def test_subir_archivo_argv_sin_shell_con_la_ruta(entorno, monkeypatch):
    """La ruta del media va como UN argumento argv, nunca por shell."""
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
    c = _cliente()
    r = c.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "clip-a-copy", "marca": "unotv"},
        files={"archivo": ("clip.mp4", b"datos", "video/mp4")},
    )
    assert r.status_code == 200
    assert isinstance(capturado["cmd"], list)
    assert capturado["cmd"][0] == "claude"
    assert capturado["cmd"][1] == "-p"
    assert capturado["shell"] is False

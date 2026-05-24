"""Tests de la feature Tareas de la Consola Keni. Todo OFFLINE.

No se lanza Claude Code real: el wrapper `abrir_tarea_en_claude_code` se mockea.
La config de proyectos (allowlist) vive en `tmp_path` via `KENI_CONSOLA_CONFIG` y
las tareas via `KENI_CONSOLA_TAREAS`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import proyectos
from keni_consola.features import tareas as feat_tareas


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Config + tareas aisladas en tmp; metricas offline (fuente de muestra)."""
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    return tmp_path


def _registrar_proyecto(tmp_path: Path, nombre: str = "Proyecto A", carpeta_nombre: str = "proyecto-a") -> Path:
    """Crea una carpeta permitida y la registra en consola.toml (allowlist)."""
    carpeta = tmp_path / carpeta_nombre
    carpeta.mkdir()
    cfg = tmp_path / "consola.toml"
    bloque = f'[[proyecto]]\nnombre = "{nombre}"\nruta = "{carpeta}"\n'
    texto = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    if texto and not texto.endswith("\n"):
        texto += "\n"
    cfg.write_text(texto + bloque, encoding="utf-8")
    return carpeta


def _cliente() -> TestClient:
    # `abrir` de proyectos: mock inofensivo (esta feature usa su propio wrapper).
    return TestClient(app_modulo.crear_app(abrir=lambda _r: "ok-mock"))


# --------------------------------------------------------------------------- #
# Pagina y nav                                                                 #
# --------------------------------------------------------------------------- #


def test_tareas_devuelve_html_200(entorno):
    c = _cliente()
    r = c.get("/tareas")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Tareas" in r.text


def test_tareas_aparece_en_la_nav(entorno):
    c = _cliente()
    html = c.get("/proyectos").text
    assert 'href="/tareas"' in html
    # orden=40 => Tareas va despues de Proyectos (10) y Metricas (20).
    assert html.index('href="/metricas"') < html.index('href="/tareas"')


def test_estado_vacio_sin_proyectos_invita_a_configurar(entorno):
    c = _cliente()
    texto = c.get("/tareas").text
    assert "Aún no tienes proyectos configurados" in texto


def test_estado_vacio_con_proyecto_pero_sin_tareas(entorno):
    _registrar_proyecto(entorno)
    c = _cliente()
    texto = c.get("/tareas").text
    assert "No hay tareas todavía" in texto
    # El proyecto aparece como opcion del desplegable.
    assert "Proyecto A" in texto


# --------------------------------------------------------------------------- #
# Crear / persistencia                                                         #
# --------------------------------------------------------------------------- #


def test_crear_tarea_la_persiste_y_se_lista(entorno):
    _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    c = _cliente()
    r = c.post(
        "/tareas/crear",
        data={"proyecto": pid, "titulo": "Escribir el guion", "detalle": "Prompt de arranque"},
        follow_redirects=False,
    )
    assert r.status_code == 303  # PRG
    assert r.headers["location"].startswith("/tareas")

    # Persistido en el JSON.
    guardadas = feat_tareas.cargar_tareas()
    assert len(guardadas) == 1
    assert guardadas[0]["titulo"] == "Escribir el guion"
    assert guardadas[0]["proyecto"] == pid
    assert guardadas[0]["estado"] == "pendiente"
    assert guardadas[0]["fecha"]  # fecha ISO no vacia

    # Visible en la lista, agrupada bajo el proyecto.
    texto = c.get("/tareas").text
    assert "Escribir el guion" in texto
    assert "Prompt de arranque" in texto


def test_crear_tarea_sin_titulo_es_rechazada(entorno):
    _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    c = _cliente()
    r = c.post("/tareas/crear", data={"proyecto": pid, "titulo": "  "}, follow_redirects=False)
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    assert feat_tareas.cargar_tareas() == []


def test_crear_tarea_proyecto_fuera_de_allowlist_rechazada(entorno):
    _registrar_proyecto(entorno)
    c = _cliente()
    r = c.post(
        "/tareas/crear",
        data={"proyecto": "idfalso00000", "titulo": "Intrusa"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    assert feat_tareas.cargar_tareas() == []


def test_guardado_es_atomico_no_deja_temporales(entorno):
    _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    feat_tareas.crear_tarea(pid, "Una tarea")
    # No deben quedar archivos .tmp-* en la carpeta de tareas.
    carpeta = feat_tareas.ruta_tareas().parent
    temporales = list(carpeta.glob("tareas.json.tmp-*"))
    assert temporales == []
    assert feat_tareas.ruta_tareas().is_file()


# --------------------------------------------------------------------------- #
# Marcar hecha / borrar                                                        #
# --------------------------------------------------------------------------- #


def test_marcar_hecha_actualiza_estado(entorno):
    _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    t = feat_tareas.crear_tarea(pid, "Tarea a completar")
    c = _cliente()
    r = c.post(f"/tareas/{t['id']}/hecha", follow_redirects=False)
    assert r.status_code == 303
    guardadas = feat_tareas.cargar_tareas()
    assert guardadas[0]["estado"] == "hecha"


def test_borrar_elimina_la_tarea(entorno):
    _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    t = feat_tareas.crear_tarea(pid, "Tarea a borrar")
    c = _cliente()
    r = c.post(f"/tareas/{t['id']}/borrar", follow_redirects=False)
    assert r.status_code == 303
    assert feat_tareas.cargar_tareas() == []


def test_marcar_hecha_tarea_inexistente_no_crashea(entorno):
    c = _cliente()
    r = c.post("/tareas/noexiste/hecha", follow_redirects=False)
    assert r.status_code == 303
    assert "error" in r.headers["location"]


# --------------------------------------------------------------------------- #
# Abrir en Claude Code (wrapper mockeado, sin lanzar nada)                      #
# --------------------------------------------------------------------------- #


def test_abrir_llama_al_lanzador_con_la_ruta_correcta_sin_lanzar_nada(entorno, monkeypatch):
    carpeta = _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    t = feat_tareas.crear_tarea(pid, "Trabajar aqui", detalle="haz esto")

    llamadas: list[tuple[Path, str]] = []

    def abrir_mock(ruta, detalle=""):
        llamadas.append((ruta, detalle))
        return "Claude Code abriendose (mock)."

    monkeypatch.setattr(feat_tareas, "abrir_tarea_en_claude_code", abrir_mock)

    c = _cliente()
    r = c.post(f"/tareas/{t['id']}/abrir", follow_redirects=False)
    assert r.status_code == 303
    assert llamadas == [(carpeta.resolve(), "haz esto")]
    # El mensaje del lanzador llega como aviso "ok" en el redirect (PRG).
    assert "mock" in r.headers["location"]


def test_abrir_tarea_huerfana_no_llama_al_lanzador(entorno, monkeypatch):
    """Tarea cuyo proyecto se quito de la allowlist: NO se intenta abrir nada."""
    carpeta = _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    t = feat_tareas.crear_tarea(pid, "Huerfana en potencia")

    # Quitamos el proyecto de la allowlist (vaciamos consola.toml).
    (entorno / "consola.toml").write_text("", encoding="utf-8")
    assert proyectos.proyecto_por_id(pid) is None
    assert carpeta.is_dir()  # la carpeta sigue, pero ya no esta permitida

    llamadas = []
    monkeypatch.setattr(
        feat_tareas, "abrir_tarea_en_claude_code", lambda *a, **k: llamadas.append(a)
    )

    c = _cliente()
    r = c.post(f"/tareas/{t['id']}/abrir", follow_redirects=False)
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    assert llamadas == []  # NO se intento lanzar nada


def test_abrir_default_pasa_el_detalle_como_prompt_al_lanzador(monkeypatch):
    """B8: el wrapper por defecto delega en consola.lanzador pasandole el detalle de
    la tarea como `prompt` (sin editar la firma del wrapper)."""
    from keni_consola import lanzador

    capt: list[tuple[Path, object]] = []

    def fake(ruta, prompt=None):  # noqa: ANN001 -- mock con la firma extendida
        capt.append((ruta, prompt))
        return "ok"

    monkeypatch.setattr(lanzador, "abrir_en_claude_code", fake)
    msg = feat_tareas.abrir_tarea_en_claude_code(Path("/tmp/x"), "haz el guion")
    assert capt == [(Path("/tmp/x"), "haz el guion")]
    assert msg == "ok"


def test_abrir_sin_detalle_no_pasa_prompt(monkeypatch):
    """Sin detalle, el lanzador recibe prompt=None (abre el asistente sin texto)."""
    from keni_consola import lanzador

    capt: list[tuple[Path, object]] = []
    monkeypatch.setattr(
        lanzador, "abrir_en_claude_code", lambda ruta, prompt=None: capt.append((ruta, prompt)) or "ok"
    )
    feat_tareas.abrir_tarea_en_claude_code(Path("/tmp/x"), "")
    assert capt == [(Path("/tmp/x"), None)]


def test_endpoint_abrir_pasa_el_detalle_de_la_tarea_como_prompt(entorno, monkeypatch):
    """B8 extremo a extremo: POST /tareas/{id}/abrir lleva el detalle de la tarea
    hasta el lanzador como `prompt` (mockeado, sin lanzar nada real)."""
    carpeta = _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    t = feat_tareas.crear_tarea(pid, "Escribir intro", detalle="Tono cercano, 3 parrafos")

    from keni_consola import lanzador

    capt: list[tuple[Path, object]] = []
    monkeypatch.setattr(
        lanzador, "abrir_en_claude_code", lambda ruta, prompt=None: capt.append((ruta, prompt)) or "ok"
    )

    c = _cliente()
    r = c.post(f"/tareas/{t['id']}/abrir", follow_redirects=False)
    assert r.status_code == 303
    assert capt == [(carpeta.resolve(), "Tono cercano, 3 parrafos")]


def test_boton_abrir_se_llama_abrir_asistente(entorno):
    """Des-jerga: el boton ya no dice 'Abrir en Claude Code' sino 'Abrir asistente'."""
    _registrar_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    feat_tareas.crear_tarea(pid, "Una tarea")
    texto = _cliente().get("/tareas").text
    assert "Abrir asistente" in texto
    assert "Abrir en Claude Code" not in texto


# --------------------------------------------------------------------------- #
# B8: el lanzador entrecomilla el prompt de forma segura (incl. apostrofo)     #
# --------------------------------------------------------------------------- #


def test_lanzador_con_prompt_escapa_bien_incluido_apostrofo(monkeypatch):
    """`abrir_en_claude_code(ruta, prompt=...)` arranca `claude '<prompt>'` con el
    prompt entrecomillado con shlex: un apostrofo dentro del texto NO rompe el
    comando ni permite inyeccion. Mockeamos osascript (no se lanza nada real)."""
    import shlex

    from keni_consola import lanzador

    monkeypatch.setattr(lanzador.sys, "platform", "darwin")

    capturado: dict[str, str] = {}

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        capturado["script"] = args[2]

        class _R:
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(lanzador.subprocess, "run", fake_run)

    # Prompt con apostrofo y comillas: el caso peligroso para un `cd && claude '...'`.
    prompt = "haz el guion de O'Brien sin \"comillas raras\""
    lanzador.abrir_en_claude_code(Path("/Users/o'brien/Proyecto"), prompt=prompt)

    script = capturado["script"]
    # Recuperamos el comando de shell deshaciendo el escape de AppleScript.
    inicio = script.index('do script "') + len('do script "')
    fin = script.index('"\n', inicio)
    comando_shell = script[inicio:fin].replace('\\"', '"').replace("\\\\", "\\")
    # Una vez parseado por /bin/sh, el comando es exactamente cd <ruta> && claude <prompt>.
    assert shlex.split(comando_shell) == [
        "cd",
        "/Users/o'brien/Proyecto",
        "&&",
        "claude",
        prompt,
    ]


def test_lanzador_sin_prompt_no_anade_argumento(monkeypatch):
    """Sin prompt (caso Proyectos) el comando sigue siendo `cd <ruta> && claude`."""
    import shlex

    from keni_consola import lanzador

    monkeypatch.setattr(lanzador.sys, "platform", "darwin")
    capturado: dict[str, str] = {}

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        capturado["script"] = args[2]

        class _R:
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(lanzador.subprocess, "run", fake_run)
    lanzador.abrir_en_claude_code(Path("/tmp/proj"))
    script = capturado["script"]
    inicio = script.index('do script "') + len('do script "')
    fin = script.index('"\n', inicio)
    comando_shell = script[inicio:fin].replace('\\"', '"').replace("\\\\", "\\")
    assert shlex.split(comando_shell) == ["cd", "/tmp/proj", "&&", "claude"]


# --------------------------------------------------------------------------- #
# Tarea huerfana visible en la lista                                           #
# --------------------------------------------------------------------------- #


def test_tarea_huerfana_se_muestra_pero_no_deja_abrir(entorno):
    pid = "manual0000aa"
    # Inyectamos directamente una tarea con un proyecto que no esta en la allowlist.
    feat_tareas.guardar_tareas(
        [
            {
                "id": "abc123",
                "proyecto": pid,
                "titulo": "Tarea sin proyecto",
                "detalle": "",
                "estado": "pendiente",
                "fecha": "2026-05-24",
            }
        ]
    )
    c = _cliente()
    texto = c.get("/tareas").text
    assert "Tarea sin proyecto" in texto
    assert "proyecto no configurado" in texto
    # No hay boton de abrir para una tarea huerfana.
    assert 'action="/tareas/abc123/abrir"' not in texto

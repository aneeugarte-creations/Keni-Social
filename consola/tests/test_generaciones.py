"""Tests del sistema de GENERACIONES (trabajos de IA en background, seguibles en vivo).

TODO OFFLINE: NUNCA se llama a `claude` ni a un proveedor de imagen real.

Cubre:
  - `AcumuladorStream` en modo PARCIAL (`--include-partial-messages`): texto token a
    token (`text_delta`), turnos por `message_start`, `thinking` ignorado.
  - Store de generaciones (crear/obtener/actualizar/listar) aislado en tmp.
  - Endpoints `GET /api/generaciones` y `GET /api/generaciones/{id}`.
  - El POST a `/api/skills/ejecutar` con el lanzador por defecto (noop) deja la
    generacion en `ejecutando` (no bloquea, sin resultado todavia) y es sondeable.
  - El lanzador de imagen completa la generacion con su `resultado`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import pytest

from keni_consola import generaciones, preferencias
from keni_consola.api import skills
from keni_consola.dominio import runner
from keni_consola.dominio import skills as dom_skills

from .conftest import _cliente

# Referencia GENUINA al lanzador de claude real (los tests de cancelacion/log lo usan).
# Otros tests crean la app con un lanzador FAKE inyectado (crear_app reasigna el atributo
# de modulo), que persistiria; aqui invocamos el REAL por esta referencia capturada.
_LANZAR_CLAUDE_REAL = generaciones.lanzar_job_claude

_MARCA = "unotv"

# Referencia GENUINA al lanzador de imagen real: otros tests crean la app con un lanzador
# FAKE inyectado (crear_app reasigna el atributo de modulo), que persistiria. Los tests que
# ejercitan el lanzador REAL lo invocan por esta referencia capturada al importar.
_LANZAR_IMAGEN_REAL = generaciones.lanzar_job_imagen


# --------------------------------------------------------------------------- #
# argv de claude: --effort segun preferencias                                 #
# --------------------------------------------------------------------------- #


def test_argv_sin_esfuerzo_no_pasa_effort(entorno):
    argv = generaciones._argv_claude("hola")
    assert "--effort" not in argv
    # Sigue siendo un comando de streaming valido.
    assert argv[:2] == ["claude", "-p"]
    assert "--include-partial-messages" in argv


def test_argv_con_esfuerzo_pasa_effort(entorno):
    preferencias.guardar_esfuerzo("high")
    argv = generaciones._argv_claude("hola")
    i = argv.index("--effort")
    assert argv[i + 1] == "high"


def test_argv_add_dir_para_dirs_permitidos(entorno):
    from pathlib import Path

    argv = generaciones._argv_claude("hola", [Path("/tmp/x")])
    # `--add-dir` y la ruta deben ir CONSECUTIVOS (par flag+valor).
    i = argv.index("--add-dir")
    assert argv[i + 1] == "/tmp/x"


def test_argv_sin_dirs_no_anade_add_dir(entorno):
    # Retrocompat: la firma de un solo argumento NO debe meter `--add-dir`.
    argv = generaciones._argv_claude("hola")
    assert "--add-dir" not in argv


def test_argv_incluye_skip_permissions_por_defecto(entorno, monkeypatch):
    # Headless (-p): sin --dangerously-skip-permissions `claude` no carga las skills del
    # proyecto ni usa WebFetch (no hay forma de aprobar el trust/permiso). Por defecto va.
    monkeypatch.delenv("KENI_CLAUDE_SKIP_PERMISSIONS", raising=False)
    assert "--dangerously-skip-permissions" in generaciones._argv_claude("hola")


def test_argv_skip_permissions_desactivable_por_env(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CLAUDE_SKIP_PERMISSIONS", "0")
    assert "--dangerously-skip-permissions" not in generaciones._argv_claude("hola")


# --------------------------------------------------------------------------- #
# argv de claude: --max-turns desde KENI_CLAUDE_MAX_TURNS (#103, F-T-01)        #
# --------------------------------------------------------------------------- #


def test_argv_sin_max_turns_no_pasa_la_bandera(entorno, monkeypatch):
    # Sin el env (caso por defecto del piloto), no se topa por turnos.
    monkeypatch.delenv("KENI_CLAUDE_MAX_TURNS", raising=False)
    argv = generaciones._argv_claude("hola")
    assert "--max-turns" not in argv


def test_argv_con_max_turns_pasa_la_bandera_al_subproceso(entorno, monkeypatch):
    # El env valido llega al COMANDO `claude -p` como `--max-turns <n>` (par flag+valor).
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "8")
    argv = generaciones._argv_claude("hola")
    i = argv.index("--max-turns")
    assert argv[i + 1] == "8"
    # Sigue siendo un comando de streaming valido.
    assert argv[:2] == ["claude", "-p"]


def test_argv_max_turns_invalido_o_cero_se_ignora(entorno, monkeypatch):
    # Tolerante: no numerico o <= 0 no debe meter la bandera (sin tope de turnos).
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "no-numero")
    assert "--max-turns" not in generaciones._argv_claude("hola")
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "0")
    assert "--max-turns" not in generaciones._argv_claude("hola")
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "-3")
    assert "--max-turns" not in generaciones._argv_claude("hola")


# --------------------------------------------------------------------------- #
# Entorno del subproceso: transporta la clave de imagen del ALMACEN (secretos) #
# --------------------------------------------------------------------------- #


def test_entorno_skill_inyecta_clave_de_imagen_del_almacen(entorno, monkeypatch):
    # secretos.toml es la unica fuente; la skill (plugin) la recibe por variable de entorno.
    from keni_consola import secretos

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secretos.guardar_clave_imagen("openai", "sk-almacen")
    env = generaciones._entorno_skill()
    assert env["OPENAI_API_KEY"] == "sk-almacen"


def test_entorno_skill_mapea_proveedor_a_su_variable(entorno, monkeypatch):
    from keni_consola import secretos

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secretos.guardar_clave_imagen("gemini", "g-almacen")
    env = generaciones._entorno_skill()
    assert env["GEMINI_API_KEY"] == "g-almacen"
    assert "OPENAI_API_KEY" not in env  # no inventa otras variables


def test_entorno_skill_mapea_openrouter(entorno, monkeypatch):
    from keni_consola import secretos

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    secretos.guardar_clave_imagen("openrouter", "sk-or-almacen")
    env = generaciones._entorno_skill()
    assert env["OPENROUTER_API_KEY"] == "sk-or-almacen"


def test_entorno_skill_no_pisa_una_variable_ya_puesta(entorno, monkeypatch):
    from keni_consola import secretos

    monkeypatch.setenv("OPENAI_API_KEY", "sk-del-entorno")
    secretos.guardar_clave_imagen("openai", "sk-almacen")
    env = generaciones._entorno_skill()
    assert env["OPENAI_API_KEY"] == "sk-del-entorno"  # prioridad de lo ya presente


def test_entorno_skill_sin_clave_no_anade_nada(entorno, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = generaciones._entorno_skill()  # almacen vacio (entorno aislado en tmp)
    assert "OPENAI_API_KEY" not in env
    assert "GEMINI_API_KEY" not in env


# --------------------------------------------------------------------------- #
# cwd de EJECUCION de skills: el dir que CONTIENE .claude/skills              #
# --------------------------------------------------------------------------- #


def test_cwd_ejecucion_skills_apunta_a_skills_copy(monkeypatch, tmp_path):
    # Estructura tipica del repo: las skills viven en `skills-copy/.claude/skills`.
    # El cwd vive en el dominio (`dominio.skills`); `api.skills` solo lo reexporta.
    (tmp_path / "skills-copy" / ".claude" / "skills").mkdir(parents=True)
    monkeypatch.setattr(dom_skills, "cwd_skills", lambda: tmp_path)
    assert dom_skills.cwd_ejecucion_skills() == tmp_path / "skills-copy"
    # La fachada reexpone el mismo resultado.
    assert skills._cwd_ejecucion_skills() == tmp_path / "skills-copy"


# --------------------------------------------------------------------------- #
# cwd_skills: fallback de descubrimiento de skills (#133)                      #
# --------------------------------------------------------------------------- #
#
# `cwd_skills()` debe resolver una RAIZ que contenga `.claude/skills` (directa o via
# `skills-copy/`). Preferencia: env KENI_SKILLS_CWD -> repo de dev -> cache del plugin
# (CLAUDE_PLUGIN_ROOT, luego ~/.claude/plugins/**/keni-social) -> cwd actual.


def _aislar_cwd_skills(monkeypatch, home: Path):
    """Aisla cwd_skills del entorno real: HOME -> tmp y limpia los envs implicados."""
    monkeypatch.setattr(dom_skills.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("KENI_SKILLS_CWD", raising=False)
    monkeypatch.delenv("KENI_SKILLS_EJECUCION_CWD", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)


def _crear_skills(raiz: Path) -> Path:
    """Crea la estructura de skills del plugin/repo (`skills-copy/.claude/skills`) bajo `raiz`."""
    (raiz / "skills-copy" / ".claude" / "skills").mkdir(parents=True)
    return raiz


def test_cwd_skills_repo_de_dev_presente(monkeypatch, tmp_path):
    # Con el repo de dev en disco (`~/projects/keni-social` con skills) se usa ese, intacto.
    home = tmp_path / "home"
    repo = _crear_skills(home / "projects" / "keni-social")
    _aislar_cwd_skills(monkeypatch, home)
    assert dom_skills.cwd_skills() == repo


def test_cwd_skills_fallback_a_claude_plugin_root(monkeypatch, tmp_path):
    # Sin repo de dev, pero con CLAUDE_PLUGIN_ROOT apuntando a un plugin con skills:
    # se usa la raiz del plugin (el caso del community manager que solo instalo el plugin).
    home = tmp_path / "home"
    (home / "projects").mkdir(parents=True)  # existe ~/projects pero SIN keni-social
    plugin = _crear_skills(tmp_path / "plugin_root")
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    assert dom_skills.cwd_skills() == plugin


def test_cwd_skills_fallback_a_cache_de_plugins(monkeypatch, tmp_path):
    # Sin repo de dev y sin CLAUDE_PLUGIN_ROOT: se descubre NUESTRO plugin en la cache
    # `~/.claude/plugins/**/keni-social` (clon de marketplace).
    home = tmp_path / "home"
    home.mkdir(parents=True)
    plugin = _crear_skills(
        home / ".claude" / "plugins" / "marketplaces" / "kenitech" / "plugins" / "keni-social"
    )
    _aislar_cwd_skills(monkeypatch, home)
    assert dom_skills.cwd_skills() == plugin


def test_cwd_skills_prioriza_plugin_root_sobre_cache(monkeypatch, tmp_path):
    # CLAUDE_PLUGIN_ROOT manda sobre el barrido de la cache: es la senal directa.
    home = tmp_path / "home"
    home.mkdir(parents=True)
    _crear_skills(home / ".claude" / "plugins" / "keni-social")  # tambien en cache
    plugin_env = _crear_skills(tmp_path / "plugin_env")
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_env))
    assert dom_skills.cwd_skills() == plugin_env


def test_cwd_skills_repo_de_dev_gana_al_plugin(monkeypatch, tmp_path):
    # El flujo de dev no se rompe: con repo Y plugin presentes, gana el repo de dev.
    home = tmp_path / "home"
    repo = _crear_skills(home / "projects" / "keni-social")
    _crear_skills(home / ".claude" / "plugins" / "keni-social")
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_crear_skills(tmp_path / "otro")))
    assert dom_skills.cwd_skills() == repo


def test_cwd_skills_sin_skills_cae_al_cwd_actual(monkeypatch, tmp_path):
    # Ni repo ni plugin con skills: ultimo recurso = cwd actual (compat con el viejo flujo).
    home = tmp_path / "home"
    home.mkdir(parents=True)
    cwd = tmp_path / "cwd_actual"
    cwd.mkdir()
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setattr(dom_skills.Path, "cwd", classmethod(lambda cls: cwd))
    assert dom_skills.cwd_skills() == cwd


def test_cwd_skills_env_explicito_se_respeta_aunque_sin_skills(monkeypatch, tmp_path):
    # KENI_SKILLS_CWD es override explicito: se respeta si es un dir existente, contenga
    # o no skills (lo usan operadores/tests). No debe caer al fallback del plugin.
    home = tmp_path / "home"
    _crear_skills(home / "projects" / "keni-social")  # habria repo, pero el env manda
    override = tmp_path / "override"
    override.mkdir()
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("KENI_SKILLS_CWD", str(override))
    assert dom_skills.cwd_skills() == override


# --------------------------------------------------------------------------- #
# CONTENEDOR (#130): descubrir y ejecutar desde un arbol BUNDLEADO, sin repo   #
# de dev ni cache del plugin de Claude Code.                                   #
# --------------------------------------------------------------------------- #
#
# En la imagen solo existe el arbol bundleado (KENI_SKILLS_CWD -> `<raiz>` con
# `skills-copy/.claude/skills` + `skills-copy/contexto-editorial/`). NO hay
# `~/projects/keni-social` ni `~/.claude/plugins`. Debe: (a) DESCUBRIR las skills,
# (b) que el cwd de EJECUCION sea el `skills-copy/` correcto (donde resuelve el corpus
# editorial relativo) y sea ESCRIBIBLE.


def _crear_bundle_contenedor(raiz: Path) -> Path:
    """Crea el arbol bundleado de la imagen: skills + contexto-editorial bajo `skills-copy/`."""
    base = _crear_skills(raiz)  # `<raiz>/skills-copy/.claude/skills`
    (base / "skills-copy" / "contexto-editorial" / "marcas").mkdir(parents=True)
    (base / "skills-copy" / "contexto-editorial" / "tropicalizacion.md").write_text(
        "tropicalizacion MX", encoding="utf-8"
    )
    return base


def test_contenedor_solo_skills_cwd_descubre_y_ejecuta(monkeypatch, tmp_path):
    # SOLO KENI_SKILLS_CWD definido (sin repo de dev ni cache del plugin):
    #   - cwd_skills() resuelve la raiz bundleada,
    #   - el cwd de EJECUCION es `skills-copy/` (donde resuelve `contexto-editorial/`),
    #   - ese cwd es ESCRIBIBLE.
    home = tmp_path / "home"
    home.mkdir(parents=True)  # NO hay ~/projects/keni-social ni ~/.claude/plugins
    bundle = _crear_bundle_contenedor(tmp_path / "app" / "keni-social")
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("KENI_SKILLS_CWD", str(bundle))

    assert dom_skills.cwd_skills() == bundle
    ejecucion = dom_skills.cwd_ejecucion_skills()
    assert ejecucion == bundle / "skills-copy"
    # El corpus editorial se resuelve RELATIVO al cwd de ejecucion.
    assert (ejecucion / "contexto-editorial" / "tropicalizacion.md").is_file()
    # El cwd de ejecucion es ESCRIBIBLE (claude escribe en su cwd).
    assert os.access(ejecucion, os.W_OK)
    (ejecucion / ".keni_escritura_ok").write_text("ok", encoding="utf-8")


def test_contenedor_catalogo_descubre_skills_via_skills_cwd(monkeypatch, tmp_path):
    # El CATALOGO descubre las skills end-to-end desde KENI_SKILLS_CWD (sin KENI_SKILLS_DIR,
    # sin repo de dev ni cache): `dir_skills()` resuelve `<raiz>/skills-copy/.claude/skills`
    # y `listar()` ve la skill bundleada.
    from keni_consola import skills_catalogo

    home = tmp_path / "home"
    home.mkdir(parents=True)
    bundle = _crear_bundle_contenedor(tmp_path / "app" / "keni-social")
    base_skills = bundle / "skills-copy" / ".claude" / "skills"
    (base_skills / "copy-demo").mkdir(parents=True)
    (base_skills / "copy-demo" / "keni.yaml").write_text("nombre: Copy Demo\n", encoding="utf-8")
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.delenv("KENI_SKILLS_DIR", raising=False)  # forzar la cadena via cwd_skills
    monkeypatch.setenv("KENI_SKILLS_CWD", str(bundle))

    assert skills_catalogo.dir_skills() == base_skills
    assert "copy-demo" in {s.id for s in skills_catalogo.listar()}


def test_contenedor_skills_cwd_apunta_directo_a_skills_copy(monkeypatch, tmp_path):
    # La imagen tambien puede bundlear apuntando KENI_SKILLS_CWD directo a `skills-copy/`
    # (raiz que contiene `.claude/skills` sin el nivel intermedio). El cwd de ejecucion es
    # esa misma raiz y el corpus editorial sigue resolviendo.
    home = tmp_path / "home"
    home.mkdir(parents=True)
    skills_copy = tmp_path / "app" / "skills-copy"
    (skills_copy / ".claude" / "skills").mkdir(parents=True)
    (skills_copy / "contexto-editorial").mkdir(parents=True)
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("KENI_SKILLS_CWD", str(skills_copy))

    assert dom_skills.cwd_skills() == skills_copy
    assert dom_skills.cwd_ejecucion_skills() == skills_copy
    assert (dom_skills.cwd_ejecucion_skills() / "contexto-editorial").is_dir()


def test_ejecucion_cwd_override_escribible(monkeypatch, tmp_path):
    # KENI_SKILLS_EJECUCION_CWD separa "donde corre claude" (copia ESCRIBIBLE) de la raiz
    # de descubrimiento (KENI_SKILLS_CWD), para el caso de bundle de SOLO LECTURA.
    home = tmp_path / "home"
    home.mkdir(parents=True)
    bundle = _crear_bundle_contenedor(tmp_path / "app" / "keni-social")  # descubrimiento
    escribible = _crear_bundle_contenedor(tmp_path / "rw" / "ejecucion")  # copia rw
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("KENI_SKILLS_CWD", str(bundle))
    monkeypatch.setenv("KENI_SKILLS_EJECUCION_CWD", str(escribible))

    # El descubrimiento sigue saliendo de KENI_SKILLS_CWD.
    assert dom_skills.cwd_skills() == bundle
    # El cwd de ejecucion sale del override y se normaliza a su `skills-copy/`.
    ejecucion = dom_skills.cwd_ejecucion_skills()
    assert ejecucion == escribible / "skills-copy"
    assert (ejecucion / "contexto-editorial" / "tropicalizacion.md").is_file()
    assert os.access(ejecucion, os.W_OK)


def test_ejecucion_cwd_override_inexistente_cae_a_skills_cwd(monkeypatch, tmp_path):
    # Si KENI_SKILLS_EJECUCION_CWD no existe, se ignora y el cwd de ejecucion se DERIVA de
    # cwd_skills() (no se rompe ni se devuelve una ruta inexistente).
    home = tmp_path / "home"
    home.mkdir(parents=True)
    bundle = _crear_bundle_contenedor(tmp_path / "app" / "keni-social")
    _aislar_cwd_skills(monkeypatch, home)
    monkeypatch.setenv("KENI_SKILLS_CWD", str(bundle))
    monkeypatch.setenv("KENI_SKILLS_EJECUCION_CWD", str(tmp_path / "no_existe"))

    assert dom_skills.cwd_ejecucion_skills() == bundle / "skills-copy"


# --------------------------------------------------------------------------- #
# AcumuladorStream: streaming token a token (eventos `stream_event`)          #
# --------------------------------------------------------------------------- #


def _se(event: dict) -> str:
    """Serializa un `stream_event` NDJSON (modo --include-partial-messages)."""
    return json.dumps({"type": "stream_event", "event": event})


def test_acumulador_streaming_texto_token_a_token():
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {"model": "claude-haiku-4-5"}}))
    # thinking NO debe acumularse en el texto del copy.
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "thinking_delta", "thinking": "pensando..."}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 1,
                            "delta": {"type": "text_delta", "text": "Hola "}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 1,
                            "delta": {"type": "text_delta", "text": "mundo"}}))
    acc.procesar_linea(_se({"type": "message_delta",
                            "usage": {"input_tokens": 10, "output_tokens": 5}}))

    assert acc.iniciado is True
    assert acc.texto == "Hola mundo"  # solo el texto, no el thinking
    assert "pensando" not in acc.texto
    assert acc.turnos == 1  # un solo message_start
    assert acc.modelo == "claude-haiku-4-5"
    parc = acc.metricas_parciales()
    assert parc is not None and parc.tokens_out == 5


def test_acumulador_parcial_no_recuenta_turnos_desde_assistant():
    """En modo parcial los turnos los cuenta `message_start`; un `assistant` posterior
    (que el CLI tambien emite) NO debe sumar otro turno."""
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": "ok"}}))
    acc.procesar_linea(json.dumps({"type": "assistant",
                                   "message": {"usage": {"input_tokens": 9, "output_tokens": 9}}}))
    assert acc.turnos == 1  # no 2


# --------------------------------------------------------------------------- #
# Store de generaciones                                                       #
# --------------------------------------------------------------------------- #


def test_store_crear_obtener_actualizar_listar(entorno):
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Copy desde nota"})
    gid = g["id"]
    assert g["estado"] == "ejecutando"
    assert g["fecha_inicio"]
    assert g["resultado"] is None

    leido = generaciones.obtener(gid)
    assert leido is not None and leido["etiqueta"] == "Copy desde nota"

    generaciones.actualizar(gid, {"estado": "completado", "salida": "hey",
                                  "resultado": {"piezas": [{"red": "x"}]}})
    g2 = generaciones.obtener(gid)
    assert g2["estado"] == "completado"
    assert g2["salida"] == "hey"
    assert g2["resultado"] == {"piezas": [{"red": "x"}]}

    assert any(x["id"] == gid for x in generaciones.listar())
    assert generaciones.obtener("noexiste") is None


def test_store_id_invalido_no_escapa(entorno):
    # Un id con separadores / .. no debe resolver (anti-traversal).
    assert generaciones.obtener("../secreto") is None
    assert generaciones.obtener("a/b") is None


# --------------------------------------------------------------------------- #
# Endpoints de sondeo                                                         #
# --------------------------------------------------------------------------- #


def test_get_generacion_404_si_no_existe(entorno):
    r = _cliente().get("/api/generaciones/noexiste")
    assert r.status_code == 404


def test_get_y_listar_generaciones(entorno):
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    cli = _cliente()
    r = cli.get(f"/api/generaciones/{g['id']}")
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == g["id"]
    lista = cli.get("/api/generaciones").json()["generaciones"]
    assert any(x["id"] == g["id"] for x in lista)


def test_ejecutar_lanza_en_background_y_queda_ejecutando(entorno):
    """Con el lanzador por defecto (noop) la generacion queda `ejecutando`, sondeable."""
    cli = _cliente()  # lanzador de generacion por defecto = noop (no claude)
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": _MARCA, "valores": {"fuente": "una nota"}},
    )
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["tipo"] == "copy"
    assert gen["estado"] == "ejecutando"
    assert gen["resultado"] is None
    # Sondeable por su id.
    r2 = cli.get(f"/api/generaciones/{gen['id']}")
    assert r2.status_code == 200
    assert r2.json()["generacion"]["estado"] == "ejecutando"


# --------------------------------------------------------------------------- #
# Lanzador de imagen (background, sin red)                                    #
# --------------------------------------------------------------------------- #


def test_lanzar_job_imagen_completa(entorno):
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Imagen"})["id"]
    _LANZAR_IMAGEN_REAL(
        gid, generar=lambda: {"id": "x.png", "url": "/api/media/x.png"}
    )
    # El handle se suelta DESPUES de fijar el estado terminal; si sigue, lo esperamos.
    with generaciones._HANDLES_LOCK:
        handle = generaciones._HANDLES.get(gid)
    if handle is not None:
        handle["hilo"].join(timeout=5)
    g = generaciones.obtener(gid)
    assert g["estado"] == "completado"
    assert g["resultado"] == {"id": "x.png", "url": "/api/media/x.png"}


def test_lanzar_job_imagen_error(entorno):
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Imagen"})["id"]

    def _falla() -> dict:
        raise RuntimeError("proveedor caído")

    _LANZAR_IMAGEN_REAL(gid, generar=_falla)
    with generaciones._HANDLES_LOCK:
        handle = generaciones._HANDLES.get(gid)
    if handle is not None:
        handle["hilo"].join(timeout=5)
    g = generaciones.obtener(gid)
    assert g["estado"] == "error"
    assert "proveedor" in g["error"].lower()


# --------------------------------------------------------------------------- #
# #137 INTERINO: tope de cola, cancelacion (mata el arbol), log sin tragar      #
# --------------------------------------------------------------------------- #


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _esperar_terminal(gid: str, timeout: float = 8.0) -> str:
    """Espera a que la generacion `gid` alcance un estado TERMINAL (no `ejecutando`).

    Mas robusto que mirar el handle: el handle se registra DENTRO del slot (puede tardar)
    y se suelta tras fijar el estado, asi que esperar el estado terminal evita carreras.
    """
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        g = generaciones.obtener(gid)
        if g is not None and g["estado"] != generaciones.ESTADO_EJECUTANDO:
            return g["estado"]
        time.sleep(0.05)
    return (generaciones.obtener(gid) or {}).get("estado", "")


@pytest.mark.timeout(20)
def test_lanzar_job_claude_rechaza_cuando_la_cola_esta_llena(entorno, monkeypatch):
    """Cola al tope -> `lanzar_job_claude` lanza ColaLlenaError SINCRONAMENTE (-> 429).

    La admision se decide ANTES de arrancar el hilo: con el cupo agotado, el llamante
    recibe la excepcion (que la API traduce a 429) en vez de apilar otro hilo daemon.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "0")
    # Saturamos la admision manualmente (1 slot, 0 cola -> tope 1).
    runner.admitir()
    try:
        gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})["id"]
        with pytest.raises(runner.ColaLlenaError):
            _LANZAR_CLAUDE_REAL(
                gid, prompt="hola", cwd=entorno, procesar=lambda s, m: {"ok": True}
            )
        # NO se creo ningun hilo de job extra para este gid (no se encolo).
        with generaciones._HANDLES_LOCK:
            assert gid not in generaciones._HANDLES
    finally:
        runner.liberar_admision()


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="grupos de procesos POSIX")
def test_cancelar_mata_el_arbol_y_marca_cancelado(entorno, monkeypatch):
    """`cancelar` mata el ARBOL del subproceso y deja el registro en `cancelado`.

    Sustituimos `runner.lanzar_proc` por uno que arranca un arbol REAL (padre python +
    hijo que duerme, en su propio grupo) que emite una linea NDJSON y se queda vivo.
    Cancelamos: el arbol debe morir (incluido el hijo) y el estado quedar terminal."""
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    pids: dict[str, int] = {}
    # El padre imprime el PID del hijo, emite una linea NDJSON valida y se queda vivo.
    guion = (
        "import subprocess, sys, time\n"
        "h = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "sys.stderr.write(str(h.pid) + '\\n'); sys.stderr.flush()\n"
        '''print('{"type": "stream_event", "event": {"type": "message_start", "message": {}}}', flush=True)\n'''
        "time.sleep(300)\n"
    )

    import subprocess as _sp

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        proc = _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd,
            stdout=_sp.PIPE,
            stderr=_sp.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        pids["hijo"] = int(proc.stderr.readline().strip())
        return proc

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)

    gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Cancelable"})["id"]
    _LANZAR_CLAUDE_REAL(gid, prompt="hola", cwd=entorno, procesar=lambda s, m: {"ok": True})

    # Esperamos a que el proceso este registrado en el handle.
    fin = time.monotonic() + 5
    while time.monotonic() < fin and "hijo" not in pids:
        time.sleep(0.05)
    assert "hijo" in pids and _vivo(pids["hijo"]), "el hijo deberia estar vivo antes de cancelar"

    assert generaciones.cancelar(gid) is True
    assert _esperar_terminal(gid) == generaciones.ESTADO_ERROR

    # El arbol (incluido el hijo) debe haber muerto.
    for _ in range(50):
        if not _vivo(pids["hijo"]):
            break
        time.sleep(0.1)
    assert not _vivo(pids["hijo"]), "cancelar debio matar el arbol entero (incluido el hijo)"

    g = generaciones.obtener(gid)
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert g["motivo"] == generaciones.MOTIVO_CANCELADO


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_excepcion_en_hilo_de_post_procesado_se_loggea_no_se_traga(entorno, monkeypatch, caplog):
    """Si `procesar` revienta, el fallo se LOGUEA con el job-id (#123) y NO se silencia.

    Antes era `except Exception: pass` opaco. Ahora deja traza correlacionable al job y
    el registro queda en `error` (mensaje claro, sin traceback al cliente).
    """
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    import subprocess as _sp

    # Subproceso que emite un stream COMPLETO (terminado) para que corra `procesar`.
    lineas = [
        '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}',
        '{"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, '
        '"delta": {"type": "text_delta", "text": "hola"}}}',
        '{"type": "result", "subtype": "success", "result": "hola", '
        '"usage": {"input_tokens": 1, "output_tokens": 1}}',
    ]
    guion = "import sys\n" + "".join(f"print({ln!r}, flush=True)\n" for ln in lineas)

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        return _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True, bufsize=1,
            start_new_session=True,
        )

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)

    def _procesar_revienta(_salida, _metricas):  # noqa: ANN001
        raise RuntimeError("el post-procesado fallo a proposito")

    gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Falla"})["id"]
    with caplog.at_level(logging.ERROR, logger="keni_consola.generaciones"):
        _LANZAR_CLAUDE_REAL(gid, prompt="hola", cwd=entorno, procesar=_procesar_revienta)
        assert _esperar_terminal(gid) == generaciones.ESTADO_ERROR

    g = generaciones.obtener(gid)
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert "no se pudo procesar" in g["error"].lower()
    # El fallo NO se trago: hay un log de ERROR correlacionado al job-id.
    correlacionados = [r for r in caplog.records if gid in r.getMessage()]
    assert correlacionados, "el fallo del post-procesado debe loguearse con el job-id"


def test_fallo_del_job_se_correlaciona_con_el_request_id(entorno, monkeypatch, caplog):
    """El log del fallo del job lleva el job-id Y el request-id de quien lo lanzo (#123+#137).

    `lanzar_job_claude` captura `request_id_actual()` al lanzarse (sincronicamente, dentro
    de la peticion); el hilo corre fuera de ese contexto, asi que el id viaja en el mensaje
    de log. Asi un fallo del trabajo se rastrea hasta la peticion HTTP que lo origino.
    """
    from keni_consola import observabilidad

    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    import subprocess as _sp

    lineas = [
        '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}',
        '{"type": "result", "subtype": "success", "result": "hola", '
        '"usage": {"input_tokens": 1, "output_tokens": 1}}',
    ]
    guion = "import sys\n" + "".join(f"print({ln!r}, flush=True)\n" for ln in lineas)

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        return _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True, bufsize=1,
            start_new_session=True,
        )

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)

    def _procesar_revienta(_salida, _metricas):  # noqa: ANN001
        raise RuntimeError("falla a proposito")

    gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Req"})["id"]
    # Simulamos el contexto de peticion: fijamos un request-id como lo haria el middleware.
    token = observabilidad.fijar_request_id("rid-job-123")
    try:
        with caplog.at_level(logging.ERROR, logger="keni_consola.generaciones"):
            _LANZAR_CLAUDE_REAL(gid, prompt="hola", cwd=entorno, procesar=_procesar_revienta)
            assert _esperar_terminal(gid) == generaciones.ESTADO_ERROR
    finally:
        observabilidad.restaurar_request_id(token)

    correlacionados = [r for r in caplog.records if gid in r.getMessage() and "rid-job-123" in r.getMessage()]
    assert correlacionados, "el log del job debe llevar el job-id Y el request-id"


# --------------------------------------------------------------------------- #
# #137 API: 429 cuando la cola esta llena + endpoint de cancelacion           #
# --------------------------------------------------------------------------- #


def test_endpoint_responde_429_si_la_cola_esta_llena(entorno):
    """Un endpoint que lanza claude responde 429 (no 500) cuando la cola esta al tope.

    Inyectamos un lanzador que SIEMPRE lanza ColaLlenaError; el manejador central de la
    app lo traduce a 429 + Retry-After (backpressure), en vez de un error generico.
    """
    def _lanzador_cola_llena(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        raise runner.ColaLlenaError("La cola de generaciones está llena.")

    cli = _cliente(lanzar_generacion=_lanzador_cola_llena)
    r = cli.post(
        "/api/hashtags/sugerir",
        json={"texto": "una nota larga para sugerir", "marca": _MARCA},
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert "error" in r.json()


def test_endpoint_cancelar_404_si_no_existe(entorno):
    r = _cliente().post("/api/generaciones/noexiste/cancelar")
    assert r.status_code == 404


def test_endpoint_cancelar_sin_job_en_vuelo_devuelve_el_registro(entorno):
    """Cancelar una generacion ya terminada es idempotente: devuelve el registro tal cual."""
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    generaciones.actualizar(g["id"], {"estado": generaciones.ESTADO_COMPLETADO})
    r = _cliente().post(f"/api/generaciones/{g['id']}/cancelar")
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == g["id"]

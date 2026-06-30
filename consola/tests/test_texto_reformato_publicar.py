"""Reformato (one-shot) + publicación de línea base ("first commit") de la Prompts.

  - `reformatear_prompts`: propaga al store el cuerpo reformateado de la inicial SOLO si el cuerpo
    actual casa EXACTO con el viejo conocido (respeta ediciones del equipo); idempotente por
    sentinela. PURO, sin BD.
  - `publicar_linea_base`: publica una versión inicial de cada doc activo sin puntero; idempotente y
    no toca los ya publicados ni los de cuerpo vacío. Necesita git + Postgres (fixture `pg`).
  - Guarda de integridad: el mapa REAL `_REFORMATO_PROMPTS_V1` apunta a prompts que existen en la
    inicial y cuyo hash registrado es el del cuerpo VIEJO (distinto del reformateado actual).
"""

from __future__ import annotations

import hashlib
import shutil

import pytest

from keni_consola import libprompts
from keni_consola.libprompts import _inicial


def _escribir(ruta, titulo, cuerpo):
    """Escribe un `.md` mínimo (frontmatter + cuerpo) directo a disco, sin pasar por la API."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        f'---\ntitulo: "{titulo}"\ntipo: prompt\ncarpeta: ""\n---\n\n{cuerpo}\n',
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# reformatear_prompts: gate por hash (respeta edits) + idempotencia            #
# --------------------------------------------------------------------------- #


def test_reformatear_pisa_solo_lo_no_editado_y_es_idempotente(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    store = tmp_path / "texto"
    inicial = tmp_path / "inicial"

    cuerpo_nuevo = "Cuerpo NUEVO reformateado.\n\nCon párrafos y aire."
    _escribir(inicial / "prompt" / "demo.md", "Demo", cuerpo_nuevo)
    _escribir(inicial / "prompt" / "otro.md", "Otro", "cuerpo nuevo de otro")

    cuerpo_viejo = "Cuerpo viejo en un bloque denso."
    _escribir(store / "prompt" / "demo.md", "Demo", cuerpo_viejo)
    _escribir(store / "prompt" / "otro.md", "Otro", "EDITADO por el equipo")

    sha_viejo_demo = hashlib.sha256(cuerpo_viejo.encode("utf-8")).hexdigest()
    # Para `otro`, el hash registrado NO casa con su cuerpo actual (editado) -> no se toca.
    sha_no_casa = hashlib.sha256(b"cuerpo nuevo de otro").hexdigest()
    monkeypatch.setattr(
        _inicial,
        "_REFORMATO_PROMPTS_V1",
        (("prompt/demo", sha_viejo_demo), ("prompt/otro", sha_no_casa)),
    )

    n = libprompts.reformatear_prompts(origen=inicial)
    assert n == 1  # solo demo (otro está editado: se respeta)
    assert libprompts.obtener("prompt/demo").cuerpo == cuerpo_nuevo
    assert libprompts.obtener("prompt/otro").cuerpo == "EDITADO por el equipo"

    # Idempotente: el sentinela impide una segunda pasada (no vuelve a pisar ediciones futuras).
    assert libprompts.reformatear_prompts(origen=inicial) == 0


def test_reformatear_no_crea_docs_que_no_existen_en_el_store(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    inicial = tmp_path / "inicial"
    _escribir(inicial / "prompt" / "demo.md", "Demo", "nuevo")
    monkeypatch.setattr(_inicial, "_REFORMATO_PROMPTS_V1", (("prompt/demo", "deadbeef"),))
    # El store no tiene `prompt/demo`: la migración solo PISA lo existente, no siembra.
    assert libprompts.reformatear_prompts(origen=inicial) == 0
    assert libprompts.obtener("prompt/demo") is None


def test_mapa_reformato_real_apunta_a_prompts_reales_con_hash_viejo():
    """Guarda: cada entrada del mapa REAL referencia un prompt de la inicial y su hash es el del
    cuerpo VIEJO — es decir, DISTINTO del cuerpo reformateado que hoy vive en la inicial. Si alguien
    pegara por error el hash NUEVO, el gate no dispararía nunca y este test lo caza."""
    for doc_id, sha_viejo in _inicial._REFORMATO_PROMPTS_V1:
        doc = libprompts.obtener_inicial(doc_id)
        assert doc is not None, f"{doc_id} no existe en la inicial"
        assert len(sha_viejo) == 64 and all(c in "0123456789abcdef" for c in sha_viejo)
        sha_actual = hashlib.sha256(doc.cuerpo.encode("utf-8")).hexdigest()
        assert sha_actual != sha_viejo, (
            f"{doc_id}: el hash registrado coincide con el cuerpo ACTUAL; debe ser el VIEJO"
        )


# --------------------------------------------------------------------------- #
# propagar_plataformas_claro_x: gate por hash (respeta edits) + idempotencia   #
# --------------------------------------------------------------------------- #

_CLARO_X_ID = "editorial/rrss/claro-sports/plataformas"
_CLARO_X_VIEJO = "- Convención: gancho + dato en un tuit; emojis 1-3; el hilo para el desglose."
_CLARO_X_NUEVO = (
    "- Convención: gancho + dato en un tuit; 1 emoji (no los 3-4 de Facebook/Instagram); "
    "sin hashtags; el hilo para el desglose."
)


def _escribir_editorial(ruta, cuerpo):
    """Escribe un editorial mínimo (frontmatter + cuerpo) directo a disco."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        f'---\ntitulo: "Formato"\ntipo: editorial\nclase: plataforma\nmarcas: [claro-sports]\n'
        f"---\n\n{cuerpo}\n",
        encoding="utf-8",
    )


def test_claro_x_pisa_solo_lo_no_editado_y_es_idempotente(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    store = tmp_path / "texto"
    inicial = tmp_path / "inicial"
    ruta_rel = f"{_CLARO_X_ID}.md".split("/")

    _escribir_editorial(inicial.joinpath(*ruta_rel), _CLARO_X_NUEVO)
    _escribir_editorial(store.joinpath(*ruta_rel), _CLARO_X_VIEJO)
    sha_viejo = hashlib.sha256(_CLARO_X_VIEJO.encode("utf-8")).hexdigest()
    monkeypatch.setattr(_inicial, "_PLATAFORMAS_CLARO_X_V1", ((_CLARO_X_ID, sha_viejo),))

    n = libprompts.propagar_plataformas_claro_x(origen=inicial)
    assert n == 1
    cuerpo = libprompts.obtener(_CLARO_X_ID).cuerpo
    assert "1 emoji" in cuerpo and "sin hashtags" in cuerpo

    # Idempotente: el sentinela impide una segunda pasada.
    assert libprompts.propagar_plataformas_claro_x(origen=inicial) == 0


def test_claro_x_respeta_ediciones_del_equipo(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    store = tmp_path / "texto"
    inicial = tmp_path / "inicial"
    ruta_rel = f"{_CLARO_X_ID}.md".split("/")

    _escribir_editorial(inicial.joinpath(*ruta_rel), _CLARO_X_NUEVO)
    _escribir_editorial(store.joinpath(*ruta_rel), "EDITADO por el equipo")
    # El sha registrado es el del VIEJO; el cuerpo actual (editado) no casa -> no se toca.
    monkeypatch.setattr(
        _inicial, "_PLATAFORMAS_CLARO_X_V1",
        ((_CLARO_X_ID, hashlib.sha256(_CLARO_X_VIEJO.encode("utf-8")).hexdigest()),),
    )

    assert libprompts.propagar_plataformas_claro_x(origen=inicial) == 0
    assert libprompts.obtener(_CLARO_X_ID).cuerpo == "EDITADO por el equipo"


def test_mapa_claro_x_real_apunta_a_editorial_real_con_hash_viejo():
    """Guarda: la entrada del mapa REAL referencia el editorial de la inicial y su hash es el del
    cuerpo VIEJO — distinto del que hoy vive en la inicial (con 1 emoji / sin hashtags)."""
    for doc_id, sha_viejo in _inicial._PLATAFORMAS_CLARO_X_V1:
        doc = libprompts.obtener_inicial(doc_id)
        assert doc is not None, f"{doc_id} no existe en la inicial"
        assert len(sha_viejo) == 64 and all(c in "0123456789abcdef" for c in sha_viejo)
        sha_actual = hashlib.sha256(doc.cuerpo.encode("utf-8")).hexdigest()
        assert sha_actual != sha_viejo, (
            f"{doc_id}: el hash registrado coincide con el cuerpo ACTUAL; debe ser el VIEJO"
        )


# --------------------------------------------------------------------------- #
# publicar_linea_base: publica los sin-puntero, idempotente, ignora vacíos     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def entorno_pub(monkeypatch, tmp_path, pg):
    """Texto aislada en tmp + git ON + Postgres de pruebas (skip sin git)."""
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_PROMPTS_GIT", "1")
    yield


def test_publicar_linea_base_publica_y_es_idempotente(entorno_pub):
    p = libprompts.crear("Prompt uno", cuerpo="contenido del prompt")
    e = libprompts.crear("Editorial uno", tipo="editorial", clase="marca", cuerpo="contenido editorial")
    vacio = libprompts.crear("Vacío", cuerpo="")  # sin cuerpo: NO debe publicarse

    n = libprompts.publicar_linea_base(nota="first commit")
    assert n == 2  # prompt + editorial; el vacío se ignora

    for d in (p, e):
        pub = libprompts.produccion_de(d.id)
        assert pub is not None and pub["nota"] == "first commit"
        assert libprompts.estado_publicacion(d.id)["sin_publicar"] is False
    assert libprompts.produccion_de(vacio.id) is None

    # Idempotente: una segunda pasada no re-publica nada.
    assert libprompts.publicar_linea_base() == 0

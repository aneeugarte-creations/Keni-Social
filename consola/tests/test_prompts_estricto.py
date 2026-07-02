"""Modo ESTRICTO de la biblioteca (`KENI_PROMPTS_ESTRICTO`): puntero ilegible = fallo LOUD.

Contrato (ver `libprompts/_publicacion.py`):
  - Flag OFF (defecto): un puntero de produccion cuyo sha no es legible en git cae en
    silencio a la working copy (migracion suave) — el comportamiento de siempre.
  - Flag ON: `cuerpo_publicado` y `aplicar_produccion` lanzan `ProduccionIlegibleError`
    con un mensaje claro (el job de generacion falla con el; no hay crash-loop: los
    daemons capturan por barrido y la cola marca el job en error).
  - El editor/preview no cambia en ningun modo: `estado_publicacion` y la lectura de la
    working copy siguen funcionando aunque el puntero este roto.

SIN Postgres: el puntero se inyecta monkeypatcheando la capa best-effort
(`_publicacion.produccion_de` / `producciones`), que es justo la frontera con la BD.
"""

from __future__ import annotations

import pytest

from keni_consola import libprompts
from keni_consola.libprompts import _publicacion


@pytest.fixture
def entorno_texto(monkeypatch, tmp_path):
    """Biblioteca aislada en tmp, sin BD y con git APAGADO (ningun sha es legible)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_PROMPTS_GIT", "0")
    monkeypatch.delenv("KENI_PROMPTS_ESTRICTO", raising=False)


def _doc_con_puntero_roto(monkeypatch) -> "libprompts.Documento":
    """Crea un doc en la working copy y le inyecta un puntero a un sha inexistente."""
    doc = libprompts.crear("Estricto", cuerpo="CUERPO WORKING COPY")
    puntero = {"sha": "cafe1234cafe", "autor": "", "nota": "", "creado": ""}
    monkeypatch.setattr(_publicacion, "produccion_de", lambda doc_id: puntero)
    monkeypatch.setattr(_publicacion, "producciones", lambda: {doc.id: puntero})
    return doc


def test_flag_off_cae_a_working_copy(entorno_texto, monkeypatch):
    """Defecto (OFF): puntero ilegible -> None/doc intacto; cuerpo_efectivo da la working copy."""
    doc = _doc_con_puntero_roto(monkeypatch)
    assert libprompts.cuerpo_publicado(doc.id) is None
    aplicados = libprompts.aplicar_produccion([doc])
    assert aplicados[0].cuerpo == "CUERPO WORKING COPY"
    assert "CUERPO WORKING COPY" in (libprompts.cuerpo_efectivo(doc.id) or "")


def test_flag_on_cuerpo_publicado_lanza(entorno_texto, monkeypatch):
    monkeypatch.setenv("KENI_PROMPTS_ESTRICTO", "1")
    doc = _doc_con_puntero_roto(monkeypatch)
    with pytest.raises(libprompts.ProduccionIlegibleError) as exc:
        libprompts.cuerpo_publicado(doc.id)
    assert doc.id in str(exc.value)
    assert "cafe1234cafe" in str(exc.value)
    assert "KENI_PROMPTS_ESTRICTO" in str(exc.value)


def test_flag_on_aplicar_produccion_lanza(entorno_texto, monkeypatch):
    monkeypatch.setenv("KENI_PROMPTS_ESTRICTO", "1")
    doc = _doc_con_puntero_roto(monkeypatch)
    with pytest.raises(libprompts.ProduccionIlegibleError):
        libprompts.aplicar_produccion([doc])


def test_flag_on_sin_puntero_no_cambia_nada(entorno_texto, monkeypatch):
    """Estricto solo muerde a los docs CON puntero: sin puntero, working copy como siempre."""
    monkeypatch.setenv("KENI_PROMPTS_ESTRICTO", "1")
    doc = libprompts.crear("Sin puntero", cuerpo="LIBRE")
    assert libprompts.cuerpo_publicado(doc.id) is None
    aplicados = libprompts.aplicar_produccion([doc])
    assert aplicados[0].cuerpo == "LIBRE"
    assert "LIBRE" in (libprompts.cuerpo_efectivo(doc.id) or "")


def test_flag_on_editor_sigue_leyendo_working_copy(entorno_texto, monkeypatch):
    """El flujo del editor no se rompe en estricto: obtener/estado_publicacion no lanzan."""
    monkeypatch.setenv("KENI_PROMPTS_ESTRICTO", "1")
    doc = _doc_con_puntero_roto(monkeypatch)
    leido = libprompts.obtener(doc.id)
    assert leido is not None and leido.cuerpo == "CUERPO WORKING COPY"
    estado = libprompts.estado_publicacion(doc.id)
    assert estado["produccion"]["sha"] == "cafe1234cafe"
    assert estado["sin_publicar"] is True

"""Tests del QA editorial como APROBADOR AUTOMATICO (items A-D). SIN Postgres.

Cubre el flujo PURO/lógico del veredicto de QA atado a una pieza, sin levantar la BD real:

  - `dominio.qa_editorial.hash_copy`: hash estable del copy revisado (item D).
  - `dominio.qa_editorial.construir_procesar_qa`: persiste el veredicto atado a la pieza
    cuando se le pasa `plataforma_id` (item A); no ata nada en una revisión suelta.
  - `repos.ultimo_veredicto_qa`: devuelve el último veredicto VIGENTE e INVALIDA el veredicto
    si el copy cambió después del QA (item B/D), monkeypatcheando `db` (sin Postgres).
"""

from __future__ import annotations

from keni_consola import repos
from keni_consola.dominio import qa_editorial as dom_qa


# --------------------------------------------------------------------------- #
# hash_copy (item D)                                                           #
# --------------------------------------------------------------------------- #


def test_hash_copy_estable_e_ignora_espacios_al_borde():
    assert dom_qa.hash_copy("hola mundo") == dom_qa.hash_copy("  hola mundo  ")
    assert dom_qa.hash_copy("") == ""
    assert dom_qa.hash_copy("   ") == ""


def test_hash_copy_cambia_si_el_texto_cambia():
    assert dom_qa.hash_copy("texto A") != dom_qa.hash_copy("texto B")


# --------------------------------------------------------------------------- #
# construir_procesar_qa: persistir veredicto atado a la pieza (item A)         #
# --------------------------------------------------------------------------- #

_SALIDA = """🟢 LISTO PARA APROBAR

```json
{"veredicto": "🟢", "resumen": "Todo en orden.", "hallazgos": []}
```
"""


def test_procesar_qa_ata_veredicto_a_la_pieza(monkeypatch):
    registros: list[dict] = []
    monkeypatch.setattr(repos, "registrar_historial_prompt", lambda *a, **k: "hist-1")
    monkeypatch.setattr(
        repos, "registrar_veredicto_qa", lambda **k: registros.append(k) or "ver-1"
    )

    procesar = dom_qa.construir_procesar_qa(
        "unotv", "Una pieza",
        plataforma_id="plat-7", contenido_id="cont-3", copy_hash="abc123",
    )
    res = procesar(_SALIDA, None)

    assert res["verdicto"] == "listo"
    assert len(registros) == 1
    r = registros[0]
    assert r["plataforma_id"] == "plat-7"
    assert r["contenido_id"] == "cont-3"
    assert r["verdicto"] == "listo"
    assert r["copy_hash"] == "abc123"
    assert r["historial_id"] == "hist-1"


def test_procesar_qa_revision_suelta_no_ata_nada(monkeypatch):
    registros: list[dict] = []
    monkeypatch.setattr(repos, "registrar_historial_prompt", lambda *a, **k: "hist-2")
    monkeypatch.setattr(
        repos, "registrar_veredicto_qa", lambda **k: registros.append(k) or "x"
    )

    procesar = dom_qa.construir_procesar_qa("unotv", "Suelta")  # sin plataforma_id
    procesar(_SALIDA, None)

    assert registros == []  # nada atado: revisión suelta (copy pegado a mano)


# --------------------------------------------------------------------------- #
# repos.ultimo_veredicto_qa: vigencia e invalidación por cambio de copy (B/D)  #
# --------------------------------------------------------------------------- #


def test_ultimo_veredicto_none_si_no_hay(monkeypatch):
    monkeypatch.setattr(repos.db, "ultimo_veredicto_qa", lambda pid: None)
    assert repos.ultimo_veredicto_qa("plat-1") is None


def test_ultimo_veredicto_none_si_plataforma_vacia():
    assert repos.ultimo_veredicto_qa("") is None


def test_ultimo_veredicto_vigente_si_copy_no_cambio(monkeypatch):
    copy = "El equipo ganó 3-0."
    monkeypatch.setattr(
        repos.db, "ultimo_veredicto_qa",
        lambda pid: {
            "verdicto": "listo", "resumen": "ok", "copy_hash": dom_qa.hash_copy(copy),
        },
    )
    monkeypatch.setattr(repos.db, "obtener_contenido_plataforma", lambda pid: {"copy": copy})

    ver = repos.ultimo_veredicto_qa("plat-1")
    assert ver == {"verdicto": "listo", "resumen": "ok"}


def test_ultimo_veredicto_se_invalida_si_copy_cambio(monkeypatch):
    monkeypatch.setattr(
        repos.db, "ultimo_veredicto_qa",
        lambda pid: {
            "verdicto": "listo", "resumen": "ok",
            "copy_hash": dom_qa.hash_copy("copy VIEJO revisado"),
        },
    )
    # La pieza tiene un copy DISTINTO al revisado: el veredicto ya no aplica.
    monkeypatch.setattr(
        repos.db, "obtener_contenido_plataforma", lambda pid: {"copy": "copy NUEVO sin revisar"}
    )
    assert repos.ultimo_veredicto_qa("plat-1") is None


def test_ultimo_veredicto_sin_hash_se_acepta(monkeypatch):
    # Registro viejo sin copy_hash: no se puede invalidar, se acepta tal cual.
    monkeypatch.setattr(
        repos.db, "ultimo_veredicto_qa",
        lambda pid: {"verdicto": "revisar", "resumen": "r", "copy_hash": ""},
    )
    ver = repos.ultimo_veredicto_qa("plat-1")
    assert ver == {"verdicto": "revisar", "resumen": "r"}


# --------------------------------------------------------------------------- #
# Sanidad: el parseo del informe sigue derivando el verdicto del semáforo      #
# --------------------------------------------------------------------------- #


def test_parsear_informe_verdicto_listo():
    informe = dom_qa.parsear_informe(_SALIDA)
    assert informe["verdicto"] == "listo"

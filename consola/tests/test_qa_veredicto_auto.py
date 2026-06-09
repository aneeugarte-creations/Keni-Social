"""Tests del aprobador-automático de QA en la cadena de aprobación. SIN Postgres.

Cubre el flujo PURO/lógico del veredicto de QA atado a una pieza, sin levantar la BD real. (La
PÁGINA de revisión de copy que PRODUCÍA estos veredictos se retiró; queda la ETAPA de validación
que los CONSUME, más su almacén.)

  - `dominio.qa_editorial.hash_copy`: hash estable del copy revisado.
  - `repos.ultimo_veredicto_qa`: devuelve el último veredicto VIGENTE e INVALIDA el veredicto
    si el copy cambió después del QA, monkeypatcheando `db` (sin Postgres).
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


# Salida de ejemplo de una criba 🟢 (reutilizada por el parseo del informe, abajo).
_SALIDA = """🟢 LISTO PARA APROBAR

```json
{"veredicto": "🟢", "resumen": "Todo en orden.", "hallazgos": []}
```
"""


# --------------------------------------------------------------------------- #
# repos.ultimo_veredicto_qa: vigencia e invalidación por cambio de copy        #
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

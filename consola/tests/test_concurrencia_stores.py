"""Concurrencia de stores JSON/JSONL: `bloqueo_archivo` evita perdidas en RMW (#115).

Sin el lock por-ruta, N hilos que leen-modifican-escriben el mismo fichero se pisan
(last-write-wins) y se pierden entradas. Estos tests lanzan escrituras concurrentes y
verifican que NO se pierde ninguna.

DISENO ANTI-CUELGUE: todo acotado en el tiempo -> `Barrier(timeout)`, `join(timeout)` y
asercion de que ningun hilo quedo vivo. `pytest-timeout` es el backstop final. Nada
puede esperar para siempre.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest

from keni_consola import autodesarrollo as ad
from keni_consola import sugerencias as sug


def _en_paralelo(trabajo: Callable[[int], None], n: int = 25) -> None:
    """Ejecuta `trabajo(i)` en n hilos que arrancan a la vez; acotado, sin cuelgues."""
    barrera = threading.Barrier(n, timeout=5)
    errores: list[BaseException] = []

    def correr(i: int) -> None:
        try:
            barrera.wait()
            trabajo(i)
        except BaseException as exc:  # noqa: BLE001 - se reporta al hilo principal
            errores.append(exc)

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)
        assert not h.is_alive(), "un hilo quedo colgado (posible deadlock)"
    assert not errores, f"errores en hilos: {errores!r}"


@pytest.mark.timeout(30)
def test_sugerencias_crear_concurrente_no_pierde(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_SUGERENCIAS", str(tmp_path / "sug.json"))
    _en_paralelo(lambda i: sug.crear(f"idea {i}"), n=25)
    titulos = {s["titulo"] for s in sug.listar()}
    faltan = [f"idea {i}" for i in range(25) if f"idea {i}" not in titulos]
    assert not faltan, f"se perdieron sugerencias: {faltan}"


@pytest.mark.timeout(30)
def test_auditoria_registrar_concurrente_no_pierde(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_AUTODESARROLLO_AUDITORIA", str(tmp_path / "aud.jsonl"))
    _en_paralelo(
        lambda i: ad.registrar_auditoria({"sugerencia_id": f"s{i}", "estado": "parked"}),
        n=25,
    )
    ids = {e.get("sugerencia_id") for e in ad.leer_auditoria(limite=1000)}
    faltan = [f"s{i}" for i in range(25) if f"s{i}" not in ids]
    assert not faltan, f"se perdieron entradas de auditoria: {faltan}"

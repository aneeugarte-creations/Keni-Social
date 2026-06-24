"""API del catálogo de etiquetas (/api/etiquetas): unicidad y resurrección de líneas. OFFLINE."""

from __future__ import annotations


def _crear(cliente, nombre, marca="unotv", clase="categoria"):
    return cliente.post(
        "/api/etiquetas", json={"nombre": nombre, "clase": clase, "marca": marca}
    )


def test_crear_etiqueta_duplicada_activa_choca(cliente):
    # Dos altas del mismo (nombre, clase, marca) con la primera AÚN visible: la segunda choca.
    assert _crear(cliente, "Cultura").status_code == 200
    r = _crear(cliente, "Cultura")
    assert r.status_code == 409
    assert "ya existe" in r.json()["error"].lower()


def test_reañadir_linea_quitada_la_resucita(cliente):
    # La × oculta la línea (activo=False), no la borra. Re-añadir el mismo nombre debe
    # resucitar ESA fila —no chocar con la copia oculta ni crear un duplicado—.
    alta = _crear(cliente, "Ciencia/Tech")
    assert alta.status_code == 200
    id_original = alta.json()["etiqueta"]["id"]

    # Quitar = lo que hace el botón × del plan: PATCH activo=False.
    assert cliente.patch(
        f"/api/etiquetas/{id_original}", json={"activo": False}
    ).status_code == 200
    # Ya no aparece entre las activas (por eso "no está" en la lista del plan).
    activas = cliente.get("/api/etiquetas?marca=unotv&clase=categoria&activas=1").json()
    assert all(e["id"] != id_original for e in activas["etiquetas"])

    # Re-añadir el mismo nombre: 200, MISMA fila, de nuevo activa (sin 409, sin duplicar).
    rea = _crear(cliente, "Ciencia/Tech")
    assert rea.status_code == 200
    assert rea.json()["etiqueta"]["id"] == id_original
    assert rea.json()["etiqueta"]["activo"] is True

    activas = cliente.get("/api/etiquetas?marca=unotv&clase=categoria&activas=1").json()
    coincidencias = [e for e in activas["etiquetas"] if e["nombre"] == "Ciencia/Tech"]
    assert len(coincidencias) == 1
    assert coincidencias[0]["id"] == id_original

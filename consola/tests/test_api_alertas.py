"""Tests del endpoint de alertas de rendimiento (GET /api/alertas).

OFFLINE, persistencia en tmp. Siembra eventos internos directamente en la bitacora
(`db.registrar_evento_interno`) y verifica que el endpoint devuelve SOLO los dos tipos de
alerta de rendimiento (bajo rendimiento), filtrando el resto de
eventos internos. Cubre tambien la forma de la respuesta y el `?limite=`.
"""

from __future__ import annotations

from keni_consola import db


def _inicializar(tipo, **campos):
    """Inserta un evento interno en la bitacora (clave_idempotencia unica por defecto)."""
    return db.registrar_evento_interno(tipo=tipo, **campos)


def test_respuesta_tiene_forma_esperada(cliente):
    r = cliente.get("/api/alertas")
    assert r.status_code == 200
    datos = r.json()
    assert isinstance(datos["alertas"], list)


def test_devuelve_alertas_de_rendimiento_filtradas(cliente):
    # Una alerta de rendimiento + un evento de OTRO tipo que NO debe salir.
    _inicializar(
        "pieza.bajo_rendimiento",
        contenido_id="c1",
        plataforma_id="p1",
        payload={"resumen": "Engagement bajo"},
    )
    _inicializar("pieza.publicada", contenido_id="c3")  # otro tipo: NO es alerta

    alertas = cliente.get("/api/alertas").json()["alertas"]
    tipos = {a["tipo"] for a in alertas}
    assert tipos == {"pieza.bajo_rendimiento"}
    # No se cuela ningun evento ajeno (la publicacion).
    assert all(a["tipo"] != "pieza.publicada" for a in alertas)
    # Cada alerta trae los campos del contrato.
    una = next(a for a in alertas if a["tipo"] == "pieza.bajo_rendimiento")
    assert una["contenido_id"] == "c1"
    assert una["plataforma_id"] == "p1"
    assert una["payload"]["resumen"] == "Engagement bajo"
    assert una["id"] and una["creado"]


def test_sin_alertas_devuelve_lista_vacia(cliente):
    # Solo hay eventos de otros tipos: el endpoint no devuelve ninguno.
    _inicializar("contenido.vencido", contenido_id="cx")
    assert cliente.get("/api/alertas").json()["alertas"] == []


def test_limite_acota_el_numero_de_alertas(cliente):
    for i in range(5):
        _inicializar("pieza.bajo_rendimiento", contenido_id=f"c{i}")
    alertas = cliente.get("/api/alertas?limite=2").json()["alertas"]
    assert len(alertas) == 2

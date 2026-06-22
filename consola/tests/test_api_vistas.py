"""Tests de la API de Vistas guardadas (HTTP, vía TestClient). Todo OFFLINE.

Una vista guardada es un preset nombrado del dashboard de Analíticas: congela la config de
vista (`config`), la marca (id canónico; '' = todas) y el periodo (token de `?periodo=`).
Son compartidas por el equipo: cualquiera con sesión las lista, crea, edita y borra. Aquí se
valida la FORMA de la respuesta y el CRUD completo.
"""

from __future__ import annotations

_CONFIG = {
    "red": "instagram",
    "secciones": {"Resumen del periodo": True},
    "columnas": {"piezas": {"orden": ["titulo", "vistas"], "ocultas": ["url"]}},
}


def _crear(cli, **campos):
    cuerpo = {
        "nombre": "Claro Sports IG dirección",
        "marca": "claro-sports",
        "periodo": "mes",
        "config": _CONFIG,
        **campos,
    }
    return cli.post("/api/metricas/vistas", json=cuerpo)


def test_crear_listar_y_forma(cliente):
    r = _crear(cliente)
    assert r.status_code == 201, r.text
    vista = r.json()["vista"]
    assert vista["nombre"] == "Claro Sports IG dirección"
    assert vista["marca"] == "claro-sports"
    assert vista["marca_nombre"] == "Claro Sports"
    assert vista["periodo"] == "mes"
    # `config` viaja como objeto (no string): es el `VistaConfig` que recupera el frontend.
    assert vista["config"] == _CONFIG

    lista = cliente.get("/api/metricas/vistas")
    assert lista.status_code == 200
    assert any(v["id"] == vista["id"] for v in lista.json()["vistas"])


def test_crear_marca_todas(cliente):
    # Sin marca (o '') = vista de "todas": marca vacía y nombre legible vacío.
    r = _crear(cliente, marca="")
    assert r.status_code == 201, r.text
    vista = r.json()["vista"]
    assert vista["marca"] == ""
    assert vista["marca_nombre"] == ""


def test_crear_sin_nombre_es_400(cliente):
    r = _crear(cliente, nombre="   ")
    assert r.status_code == 400
    assert "nombre" in r.json()["error"].lower()


def test_crear_sin_periodo_es_400(cliente):
    r = _crear(cliente, periodo="")
    assert r.status_code == 400


def test_crear_marca_invalida_es_400(cliente):
    r = _crear(cliente, marca="no-existe")
    assert r.status_code == 400


def test_crear_config_no_objeto_es_400(cliente):
    r = _crear(cliente, config=["no", "es", "objeto"])
    assert r.status_code == 400


def test_filtrar_por_marca(cliente):
    a = _crear(cliente, nombre="UnoTV", marca="unotv").json()["vista"]
    b = _crear(cliente, nombre="Claro", marca="claro-sports").json()["vista"]
    solo_unotv = cliente.get("/api/metricas/vistas?marca=unotv").json()["vistas"]
    ids = {v["id"] for v in solo_unotv}
    assert a["id"] in ids
    assert b["id"] not in ids


def test_actualizar_y_borrar(cliente):
    vista = _crear(cliente).json()["vista"]
    u = cliente.put(
        f"/api/metricas/vistas/{vista['id']}",
        json={"nombre": "Dirección semanal", "periodo": "semana", "marca": "unotv"},
    )
    assert u.status_code == 200, u.text
    actualizada = u.json()["vista"]
    assert actualizada["nombre"] == "Dirección semanal"
    assert actualizada["periodo"] == "semana"
    assert actualizada["marca"] == "unotv"
    # No tocamos config: se conserva.
    assert actualizada["config"] == _CONFIG

    b = cliente.delete(f"/api/metricas/vistas/{vista['id']}")
    assert b.status_code == 200
    assert cliente.delete(f"/api/metricas/vistas/{vista['id']}").status_code == 404


def test_actualizar_inexistente_es_404(cliente):
    r = cliente.put("/api/metricas/vistas/nope", json={"nombre": "x"})
    assert r.status_code == 404

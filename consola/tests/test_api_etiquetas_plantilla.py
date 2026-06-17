"""Tests de la API del catálogo de etiquetas de plantilla (/api/etiquetas-plantilla). OFFLINE."""

from __future__ import annotations

# Doc base de una plantilla (hueco de foto explícito): para los casos de «etiqueta en uso».
_DOC = {
    "formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
    "capas": [
        {"tipo": "imagen", "objeto": "", "x": 0, "y": 0, "w": 1080, "h": 1350, "z": 0, "es_foto": True},
    ],
}


def test_listar_vacio(cliente):
    r = cliente.get("/api/etiquetas-plantilla")
    assert r.status_code == 200
    assert r.json() == {"etiquetas": []}


def test_crear_renombrar_y_listar(cliente):
    # PUT crea el rótulo; el slug del path se normaliza (mayúsculas/guiones → slug canónico).
    r = cliente.put("/api/etiquetas-plantilla/unotv/Ultima-Hora", json={"etiqueta": "Lo último"})
    assert r.status_code == 200, r.text
    e = r.json()["etiqueta"]
    assert e == {"marca": "unotv", "slug": "ultima-hora", "etiqueta": "Lo último"}

    # GET lo lista, filtrable por marca.
    assert cliente.get("/api/etiquetas-plantilla?marca=unotv").json()["etiquetas"] == [
        {"marca": "unotv", "slug": "ultima-hora", "etiqueta": "Lo último"}
    ]

    # Renombrar (mismo slug) actualiza el rótulo en sitio, sin duplicar.
    cliente.put("/api/etiquetas-plantilla/unotv/ultima-hora", json={"etiqueta": "Última noticia"})
    etiquetas = cliente.get("/api/etiquetas-plantilla?marca=unotv").json()["etiquetas"]
    assert etiquetas == [{"marca": "unotv", "slug": "ultima-hora", "etiqueta": "Última noticia"}]


def test_override_es_por_marca(cliente):
    cliente.put("/api/etiquetas-plantilla/unotv/marcador", json={"etiqueta": "Resultado"})
    cliente.put("/api/etiquetas-plantilla/claro-sports/marcador", json={"etiqueta": "Marcador final"})
    assert cliente.get("/api/etiquetas-plantilla?marca=unotv").json()["etiquetas"] == [
        {"marca": "unotv", "slug": "marcador", "etiqueta": "Resultado"}
    ]
    assert cliente.get("/api/etiquetas-plantilla?marca=claro-sports").json()["etiquetas"] == [
        {"marca": "claro-sports", "slug": "marcador", "etiqueta": "Marcador final"}
    ]
    # Sin filtro: las dos marcas.
    assert len(cliente.get("/api/etiquetas-plantilla").json()["etiquetas"]) == 2


def test_marca_invalida_400(cliente):
    r = cliente.put("/api/etiquetas-plantilla/no-existe/marcador", json={"etiqueta": "X"})
    assert r.status_code == 400


def test_borrar_en_uso_409_no_toca_plantillas(cliente):
    # Una plantilla usa la categoría `efemerides`: su rótulo no se puede borrar mientras esté en uso.
    pid = cliente.post(
        "/api/plantillas-diseno",
        json={"marca": "unotv", "nombre": "Aniversario", "categoria": "Efemérides", "documento": _DOC},
    ).json()["plantilla"]["id"]
    cliente.put("/api/etiquetas-plantilla/unotv/efemerides", json={"etiqueta": "Aniversarios"})

    r = cliente.delete("/api/etiquetas-plantilla/unotv/efemerides")
    assert r.status_code == 409
    assert r.json()["en_uso"] == 1
    # El override y la plantilla siguen intactos.
    assert cliente.get("/api/etiquetas-plantilla?marca=unotv").json()["etiquetas"]
    assert cliente.get(f"/api/plantillas-diseno/{pid}").json()["plantilla"]["categoria"] == "efemerides"


def test_borrar_sin_uso_ok(cliente):
    cliente.put("/api/etiquetas-plantilla/unotv/fichaje", json={"etiqueta": "Altas y bajas"})
    r = cliente.delete("/api/etiquetas-plantilla/unotv/fichaje")
    assert r.status_code == 200
    assert cliente.get("/api/etiquetas-plantilla?marca=unotv").json()["etiquetas"] == []

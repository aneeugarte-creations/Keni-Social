"""Tests de la API Piezas (/api/piezas). OFFLINE, DB en tmp.

Cubre: opciones (catalogos), CRUD, lote, filtros, validaciones (marca/red/estado),
resolucion de nombres legibles y edicion parcial.
"""

from __future__ import annotations

from keni_consola import repos


def _crear(cliente, **campos):
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    return cliente.post("/api/piezas", json=base)


# --------------------------------------------------------------------------- #
# GET /api/piezas/opciones                                             #
# --------------------------------------------------------------------------- #


def test_opciones(cliente):
    datos = cliente.get("/api/piezas/opciones").json()
    assert {"redes", "estados", "marcas", "categorias"} <= set(datos)
    # `categorias`: mapa marca -> categorías con franja (pueblan el dropdown obligatorio de
    # «Crear post»). Sin franjas configuradas en el entorno de test el mapa puede ir vacío por
    # marca, pero la forma (dict de listas) es estable.
    assert isinstance(datos["categorias"], dict)
    assert all(isinstance(v, list) for v in datos["categorias"].values())
    # redes en orden fijo con limite
    ids = [r["id"] for r in datos["redes"]]
    assert ids == ["x", "instagram", "facebook", "tiktok", "youtube"]
    x = datos["redes"][0]
    assert x == {"id": "x", "nombre": "X", "limite": 25000}
    assert datos["redes"][2]["limite"] is None  # facebook
    # estados con nombre legible
    estados = {e["id"]: e["nombre"] for e in datos["estados"]}
    assert estados == {
        "borrador": "Borrador",
        "en_revision": "En revisión",
        "programado": "Programado",
        "publicado": "Publicado",
    }
    # marcas: las de Skills (con slug)
    assert any(m["id"] == "unotv" for m in datos["marcas"])


# --------------------------------------------------------------------------- #
# POST / GET listado                                                          #
# --------------------------------------------------------------------------- #


def test_crear_y_listar(cliente):
    r = _crear(cliente)
    assert r.status_code == 200
    pub = r.json()["pieza"]
    assert pub["id"]
    assert pub["estado"] == "borrador"
    assert pub["marca_nombre"] == "UnoTV"
    assert pub["red_nombre"] == "X"
    listado = cliente.get("/api/piezas").json()["piezas"]
    assert len(listado) == 1


def test_crear_estado_explicito(cliente):
    pub = _crear(cliente, estado="en_revision").json()["pieza"]
    assert pub["estado"] == "en_revision"


def test_crear_marca_invalida_400(cliente):
    r = _crear(cliente, marca="marca_falsa")
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()


def test_crear_marca_golf_rechazada_400(cliente):
    # El golf NO es marca de primer nivel (es un sub-vertical editorial de Claro
    # Sports): no se acepta como destino de copy.
    r = _crear(cliente, marca="claro-sports-golf")
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()


def test_crear_id_metricas_no_es_id_canonico_400(cliente):
    # La forma id_metricas (guion_bajo) NO es un id canonico => no vale como marca.
    assert _crear(cliente, marca="claro_sports_golf").status_code == 400


def test_crear_red_invalida_400(cliente):
    r = _crear(cliente, red="myspace")
    assert r.status_code == 400
    assert "red" in r.json()["error"].lower()


def test_crear_estado_invalido_400(cliente):
    r = _crear(cliente, estado="archivado")
    assert r.status_code == 400


def test_crear_titulo_no_texto_400(cliente):
    r = cliente.post("/api/piezas", json={"marca": "unotv", "red": "x", "titulo": 5})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Filtros                                                                     #
# --------------------------------------------------------------------------- #


def test_filtros(cliente):
    _crear(cliente, red="x", estado="borrador")
    _crear(cliente, red="instagram", estado="en_revision")
    _crear(cliente, marca="piso-15", red="x")
    assert len(cliente.get("/api/piezas?marca=unotv").json()["piezas"]) == 2
    assert len(cliente.get("/api/piezas?red=x").json()["piezas"]) == 2
    assert len(cliente.get("/api/piezas?estado=en_revision").json()["piezas"]) == 1
    assert (
        len(cliente.get("/api/piezas?marca=unotv&red=x").json()["piezas"]) == 1
    )


def test_filtro_categoria_tipo_y_fuente(cliente):
    """Filtros de limpieza sobre el contenido padre: categoría del plan, tipo y medio de origen."""
    pz = repos.crear_pieza("unotv", "x", titulo="Breaking", contenido="C", tipo_contenido="fuente")
    cid = repos.obtener_pieza_fila(pz["id"])["publicacion_id"]
    repos.actualizar_publicacion(cid, {"categoria": "breaking", "fuente_nombre": "Infobae"})
    repos.crear_pieza("unotv", "x", titulo="Normal", contenido="C", tipo_contenido="ia")
    assert len(cliente.get("/api/piezas?categoria=breaking").json()["piezas"]) == 1
    assert len(cliente.get("/api/piezas?tipo=fuente").json()["piezas"]) == 1
    assert len(cliente.get("/api/piezas?fuente=Infobae").json()["piezas"]) == 1
    assert len(cliente.get("/api/piezas?categoria=mx").json()["piezas"]) == 0


def test_filtro_fase(cliente):
    """`?fase=incompleto` = en producción (le falta copy/arte/revisión, en borrador); `programado`
    = ya en calendario. Permite barrer lo nunca terminado y conservar lo completado."""
    inc = repos.crear_pieza("unotv", "x", titulo="Incompleta", contenido="")
    repos.actualizar_pieza(
        inc["id"], {"falta_copy": 1, "falta_imagen": 1, "falta_revision": 1, "estado": "borrador"}
    )
    prog = repos.crear_pieza("unotv", "x", titulo="Programada", contenido="C")
    repos.actualizar_pieza(
        prog["id"], {"falta_copy": 0, "falta_imagen": 0, "falta_revision": 0, "estado": "programado"}
    )
    incompletos = cliente.get("/api/piezas?fase=incompleto").json()["piezas"]
    assert [p["titulo"] for p in incompletos] == ["Incompleta"]
    programados = cliente.get("/api/piezas?fase=programado").json()["piezas"]
    assert [p["titulo"] for p in programados] == ["Programada"]


def test_filtro_antiguedad(cliente):
    """`?antiguedad_h=24` deja solo lo creado hace MÁS de 24 h (sobre la creación del tema)."""
    repos.crear_pieza(
        "unotv", "x", titulo="Vieja", contenido="C", fecha_creacion="2020-01-01T00:00:00"
    )
    repos.crear_pieza("unotv", "x", titulo="Nueva", contenido="C")
    viejas = cliente.get("/api/piezas?antiguedad_h=24").json()["piezas"]
    assert [p["titulo"] for p in viejas] == ["Vieja"]


def test_filtro_pendiente_pseudo_estado(cliente):
    """`?estado=pendiente` = TODO lo que aún no salió (cualquier estado salvo `publicado`);
    su complementario EXACTO es `?estado=publicado`, de modo que pendiente + publicado = total.
    Es la partición binaria del feed/lista (Pendientes · Publicadas · Todas)."""
    for estado in ("borrador", "en_revision", "programado", "publicado"):
        _crear(cliente, red="x", estado=estado)
    total = cliente.get("/api/piezas?marca=unotv").json()["paginacion"]["total"]
    pend = cliente.get("/api/piezas?marca=unotv&estado=pendiente").json()
    pub = cliente.get("/api/piezas?marca=unotv&estado=publicado").json()
    assert total == 4
    # Pendientes = los 3 no publicados; Publicadas = solo el publicado.
    assert pend["paginacion"]["total"] == 3
    assert pub["paginacion"]["total"] == 1
    # Partición exacta: ninguna pieza publicada se cuela en pendientes y la suma cuadra.
    assert all(p["estado"] != "publicado" for p in pend["piezas"])
    assert pend["paginacion"]["total"] + pub["paginacion"]["total"] == total


def test_opciones_incluye_lineas(cliente):
    """`opciones.lineas` expone las etiquetas verticales (líneas editoriales) activas."""
    from keni_consola import repos

    repos.crear_etiqueta(nombre="Deportes", clase="vertical", marca="unotv")
    # Una etiqueta de OTRA clase no debe colarse como línea editorial.
    repos.crear_etiqueta(nombre="Mundial", clase="campania", marca="unotv")
    lineas = cliente.get("/api/piezas/opciones").json()["lineas"]
    nombres = {l["nombre"] for l in lineas}
    assert "Deportes" in nombres
    assert "Mundial" not in nombres


def test_filtro_linea(cliente):
    """`?linea=<id>` deja solo las piezas cuyo contenido padre tiene esa etiqueta vertical."""
    from keni_consola import repos

    etiqueta = repos.crear_etiqueta(nombre="Política", clase="vertical", marca="unotv")
    con_linea = _crear(cliente, titulo="Con línea").json()["pieza"]
    _crear(cliente, titulo="Sin línea")
    repos.asignar_etiqueta(con_linea["publicacion_id"], etiqueta["id"])

    filtrado = cliente.get(f"/api/piezas?linea={etiqueta['id']}").json()
    assert [p["titulo"] for p in filtrado["piezas"]] == ["Con línea"]
    assert filtrado["paginacion"]["total"] == 1


def test_payload_incluye_responsable(cliente):
    """Toda publicación expone `responsable_id`/`responsable_nombre` ("" = libre)."""
    pub = _crear(cliente).json()["pieza"]
    assert pub["responsable_id"] == ""
    assert pub["responsable_nombre"] == ""
    listado = cliente.get("/api/piezas").json()["piezas"]
    assert listado[0]["responsable_id"] == ""
    assert listado[0]["responsable_nombre"] == ""


def test_filtro_responsable(cliente):
    """`?responsable=<id>` = piezas cogidas por ese usuario; `?responsable=sin` = libres.

    El responsable vive en el `contenido` PADRE (el reparto es del tema): cogerlo via
    `repos.reclamar_publicacion` se refleja en TODAS sus piezas por red.
    """
    from keni_consola import repos

    cogida = _crear(cliente, titulo="Cogida").json()["pieza"]
    _crear(cliente, titulo="Libre")
    asignada = repos.reclamar_publicacion(
        cogida["publicacion_id"], responsable_id="u-elias", responsable_nombre="Elías"
    )
    assert asignada is not None

    mias = cliente.get("/api/piezas?responsable=u-elias").json()
    assert [p["titulo"] for p in mias["piezas"]] == ["Cogida"]
    assert mias["piezas"][0]["responsable_nombre"] == "Elías"
    assert mias["paginacion"]["total"] == 1

    libres = cliente.get("/api/piezas?responsable=sin").json()
    assert [p["titulo"] for p in libres["piezas"]] == ["Libre"]
    assert libres["paginacion"]["total"] == 1

    # Sin el filtro se ven TODAS (el reparto no oculta nada por defecto).
    assert len(cliente.get("/api/piezas").json()["piezas"]) == 2


def test_filtro_responsable_compone_con_marca(cliente):
    """El filtro de reparto compone con los demás (marca): la vista de ClaroSports."""
    from keni_consola import repos

    cs = _crear(cliente, marca="claro-sports", titulo="CS cogida").json()["pieza"]
    _crear(cliente, marca="claro-sports", titulo="CS libre")
    uno = _crear(cliente, marca="unotv", titulo="Uno cogida").json()["pieza"]
    repos.reclamar_publicacion(cs["publicacion_id"], responsable_id="u1", responsable_nombre="Ana")
    repos.reclamar_publicacion(uno["publicacion_id"], responsable_id="u1", responsable_nombre="Ana")

    r = cliente.get("/api/piezas?marca=claro-sports&responsable=u1").json()
    assert [p["titulo"] for p in r["piezas"]] == ["CS cogida"]
    r = cliente.get("/api/piezas?marca=claro-sports&responsable=sin").json()
    assert [p["titulo"] for p in r["piezas"]] == ["CS libre"]


def test_filtro_rango_fecha_programada(cliente):
    """`?desde=&hasta=` acota por `fecha_programada`; las piezas SIN fecha quedan FUERA.

    El CALENDARIO pide solo la ventana visible (mes ± margen) en vez del conjunto completo
    que el cap de 1000 truncaba en silencio.
    """
    _crear(cliente, titulo="Dentro", estado="programado", fecha_programada="2026-06-15T18:00")
    _crear(cliente, titulo="Antes", estado="programado", fecha_programada="2026-05-20T18:00")
    _crear(cliente, titulo="Despues", estado="programado", fecha_programada="2026-08-01T18:00")
    _crear(cliente, titulo="Sin fecha")  # borrador sin fecha_programada

    r = cliente.get("/api/piezas?desde=2026-06-01&hasta=2026-06-30").json()
    assert [p["titulo"] for p in r["piezas"]] == ["Dentro"]
    # El total respeta el rango (no es el global): la paginación no miente por omisión.
    assert r["paginacion"]["total"] == 1

    # Sin el rango se ven TODAS (retrocompatible), incluida la pieza sin fecha.
    todas = cliente.get("/api/piezas").json()
    assert {p["titulo"] for p in todas["piezas"]} == {
        "Dentro", "Antes", "Despues", "Sin fecha",
    }


def test_filtro_solo_hasta_excluye_sin_fecha(cliente):
    """Con solo `?hasta=` la pieza sin fecha (cadena vacía) NO debe colarse en el rango."""
    _crear(cliente, titulo="Programada", estado="programado", fecha_programada="2026-06-15T18:00")
    _crear(cliente, titulo="Sin fecha")
    r = cliente.get("/api/piezas?hasta=2026-12-31").json()
    assert [p["titulo"] for p in r["piezas"]] == ["Programada"]


# --------------------------------------------------------------------------- #
# Lote                                                                        #
# --------------------------------------------------------------------------- #


def test_crear_lote(cliente):
    r = cliente.post(
        "/api/piezas/lote",
        json={
            "piezas": [
                {"marca": "unotv", "red": "x", "contenido": "a"},
                {"marca": "unotv", "red": "instagram", "contenido": "b"},
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["piezas"]) == 2
    assert len(cliente.get("/api/piezas").json()["piezas"]) == 2


def test_lote_una_invalida_no_inserta_nada(cliente):
    r = cliente.post(
        "/api/piezas/lote",
        json={
            "piezas": [
                {"marca": "unotv", "red": "x"},
                {"marca": "unotv", "red": "myspace"},  # invalida
            ]
        },
    )
    assert r.status_code == 400
    # todo o nada: no se inserto la primera
    assert cliente.get("/api/piezas").json()["piezas"] == []


def test_lote_vacio_400(cliente):
    r = cliente.post("/api/piezas/lote", json={"piezas": []})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# GET / PUT / DELETE por id                                                   #
# --------------------------------------------------------------------------- #


def test_detalle(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.get(f"/api/piezas/{pid}")
    assert r.status_code == 200
    assert r.json()["pieza"]["id"] == pid


def test_detalle_404(cliente):
    assert cliente.get("/api/piezas/noexiste").status_code == 404


def test_actualizar_parcial(cliente):
    pid = _crear(cliente, titulo="Viejo").json()["pieza"]["id"]
    r = cliente.put(
        f"/api/piezas/{pid}", json={"titulo": "Nuevo", "estado": "en_revision"}
    )
    assert r.status_code == 200
    pub = r.json()["pieza"]
    assert pub["titulo"] == "Nuevo"
    assert pub["estado"] == "en_revision"


def test_crear_y_editar_copy_in(cliente):
    # El copy_in (texto EN imagen) se acepta al crear y se edita por PUT, independiente del
    # contenido. Nace "" si no se manda.
    pub = _crear(cliente).json()["pieza"]
    assert pub["copy_in"] == ""
    r = cliente.put(
        f"/api/piezas/{pub['id']}", json={"copy_in": "TITULAR EN LA IMAGEN"}
    )
    assert r.status_code == 200
    editada = r.json()["pieza"]
    assert editada["copy_in"] == "TITULAR EN LA IMAGEN"
    assert editada["contenido"] == "C"  # el contenido no se toca


def test_actualizar_copy_in_no_texto_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.put(f"/api/piezas/{pid}", json={"copy_in": 123})
    assert r.status_code == 400


def test_integrar_foto_marca_visual_recompone(cliente, monkeypatch):
    # Marca con plantilla (unotv): integrar-foto recompone la foto en el marco con el copy_in
    # como titular y devuelve la imagen compuesta (mockeamos el compositor, sin Pillow).
    from keni_consola.dominio import estudio_imagen

    llamadas = []

    def _fake_componer(imagen, *, marca, formato, titular, etiqueta=None, autor=None):
        llamadas.append({"imagen": imagen, "marca": marca, "titular": titular})
        return {"id": "compuesta.png", "url": "/api/media/compuesta.png"}

    monkeypatch.setattr(estudio_imagen, "componer", _fake_componer)

    pid = _crear(cliente, marca="unotv").json()["pieza"]["id"]
    cliente.put(f"/api/piezas/{pid}", json={"copy_in": "DATO CLAVE"})
    r = cliente.post(f"/api/piezas/{pid}/integrar-foto", json={"imagen": "foto-real.jpg"})
    assert r.status_code == 200
    body = r.json()
    assert body["imagen"] == "compuesta.png"
    assert body["imagen_url"] == "/api/media/compuesta.png"
    assert llamadas == [{"imagen": "foto-real.jpg", "marca": "unotv", "titular": "DATO CLAVE"}]


def test_integrar_foto_marca_sin_plantilla_devuelve_foto(cliente):
    # Marca sin identidad visual (piso-15): no recompone; devuelve la foto tal cual.
    pid = _crear(cliente, marca="piso-15").json()["pieza"]["id"]
    r = cliente.post(f"/api/piezas/{pid}/integrar-foto", json={"imagen": "foto-real.jpg"})
    assert r.status_code == 200
    assert r.json()["imagen"] == "foto-real.jpg"


def test_integrar_foto_sin_imagen_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.post(f"/api/piezas/{pid}/integrar-foto", json={})
    assert r.status_code == 400


def test_integrar_foto_404(cliente):
    r = cliente.post("/api/piezas/noexiste/integrar-foto", json={"imagen": "x.jpg"})
    assert r.status_code == 404


def test_aplicar_plantilla_persiste_receta_no_hornea(cliente, monkeypatch):
    """aplicar-plantilla guarda la RECETA (plantilla+foto+encuadre) y deja `imagen` vacío:
    la composición se renderiza on-demand (`imagen_url` -> /compuesta), no se hornea."""
    from keni_consola import repos
    from keni_consola.dominio import estudio_imagen

    # Render de validación a BYTES mockeado (no Node, no persiste).
    monkeypatch.setattr(
        estudio_imagen, "componer_desde_plantilla_bytes", lambda *a, **k: b"png",
    )
    plantilla = repos.crear_plantilla_diseno(
        marca="unotv", nombre="P", categoria="post", documento="{}", miniatura="",
    )
    pid = _crear(cliente, marca="unotv").json()["pieza"]["id"]
    r = cliente.post(
        f"/api/piezas/{pid}/aplicar-plantilla",
        json={"plantilla_id": plantilla["id"], "foto": "f.jpg", "copy_in": "Y"},
    )
    assert r.status_code == 200, r.text
    pub = r.json()["pieza"]
    assert pub["imagen"] == ""  # NO se hornea
    assert pub["plantilla_diseno_id"] == plantilla["id"]
    assert pub["foto"] == "f.jpg"
    # La URL puede llevar sufijo `?v=` (cache-bust por `actualizado`); comparamos solo la ruta.
    assert pub["imagen_url"].split("?")[0] == f"/api/piezas/{pid}/compuesta"


def test_componer_slide_hornea_y_devuelve_media(cliente, monkeypatch):
    """componer-slide compone la placa del slide y devuelve su media id en `artes/` SIN tocar la
    pieza (la procedencia la guarda el SPA dentro del JSON `carrusel`)."""
    from keni_consola import media, repos
    from keni_consola.dominio import estudio_imagen

    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla_bytes", lambda *a, **k: b"png")
    monkeypatch.setattr(
        media, "guardar_bytes_contenido", lambda datos, ext="png", categoria="render": "artes/x.png"
    )
    plantilla = repos.crear_plantilla_diseno(
        marca="unotv", nombre="P", categoria="post", documento="{}", miniatura="",
    )
    pid = _crear(cliente, marca="unotv").json()["pieza"]["id"]
    r = cliente.post(
        f"/api/piezas/{pid}/componer-slide",
        json={"plantilla_id": plantilla["id"], "foto": "f.jpg", "titular": "Clave 2"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "artes/x.png", "url": "/api/media/artes/x.png"}
    # NO toca la pieza: sigue sin imagen horneada propia.
    assert cliente.get(f"/api/piezas/{pid}").json()["pieza"]["imagen"] == ""


def test_componer_slide_marca_sin_plantilla_promueve_foto(cliente, monkeypatch):
    """Marca sin plantilla de estudio: el slide es la foto cruda, protegida en `artes/`."""
    from keni_consola import almacen_media
    from keni_consola.dominio import render_pieza

    monkeypatch.setattr(render_pieza, "_plantilla_efectiva", lambda pub: None)
    monkeypatch.setattr(almacen_media, "promover_objeto", lambda clave, cat: f"{cat}/{clave}")
    pid = _crear(cliente, marca="piso-15").json()["pieza"]["id"]
    r = cliente.post(f"/api/piezas/{pid}/componer-slide", json={"foto": "cruda.jpg"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "artes/cruda.jpg"


def test_componer_slide_sin_foto_ni_titular_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.post(f"/api/piezas/{pid}/componer-slide", json={})
    assert r.status_code == 400


def test_componer_slide_404(cliente):
    r = cliente.post("/api/piezas/noexiste/componer-slide", json={"titular": "x"})
    assert r.status_code == 404


def test_actualizar_estado_invalido_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.put(f"/api/piezas/{pid}", json={"estado": "archivado"})
    assert r.status_code == 400


def test_actualizar_sin_campos_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.put(f"/api/piezas/{pid}", json={})
    assert r.status_code == 400


def test_actualizar_404(cliente):
    r = cliente.put("/api/piezas/noexiste", json={"titulo": "x"})
    assert r.status_code == 404


def test_actualizar_no_toca_marca_ni_red(cliente):
    """La edicion parcial ignora marca/red aunque vengan en el body."""
    pid = _crear(cliente, marca="unotv", red="x").json()["pieza"]["id"]
    r = cliente.put(
        f"/api/piezas/{pid}", json={"titulo": "Z", "marca": "piso-15", "red": "youtube"}
    )
    pub = r.json()["pieza"]
    assert pub["marca"] == "unotv"
    assert pub["red"] == "x"


def test_borrar(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    assert cliente.delete(f"/api/piezas/{pid}").status_code == 200
    assert cliente.get(f"/api/piezas/{pid}").status_code == 404


def test_borrar_404(cliente):
    assert cliente.delete("/api/piezas/noexiste").status_code == 404


# --------------------------------------------------------------------------- #
# GET /api/piezas/{id}/compuesta (render on-demand)                     #
# --------------------------------------------------------------------------- #


def test_compuesta_404_si_no_existe(cliente):
    assert cliente.get("/api/piezas/noexiste/compuesta").status_code == 404


def test_compuesta_sirve_bytes_efimeros_con_etag(cliente, monkeypatch):
    """El endpoint renderiza ON-DEMAND, sirve los bytes con su mime y un ETag (sin persistir)."""
    from keni_consola.dominio import render_pieza

    pid = _crear(cliente).json()["pieza"]["id"]
    monkeypatch.setattr(render_pieza, "render_bytes", lambda pub: (b"PNG-BYTES", "image/png"))

    r = cliente.get(f"/api/piezas/{pid}/compuesta")
    assert r.status_code == 200
    assert r.content == b"PNG-BYTES"
    assert r.headers["content-type"].startswith("image/png")
    assert r.headers.get("etag")  # ETag presente para la caché HTTP


def test_compuesta_304_si_etag_coincide(cliente, monkeypatch):
    """Con If-None-Match igual al ETag (receta sin cambios) -> 304 SIN recomponer."""
    from keni_consola.dominio import render_pieza

    pid = _crear(cliente).json()["pieza"]["id"]
    llamadas = {"n": 0}

    def _render(pub):
        llamadas["n"] += 1
        return (b"PNG-BYTES", "image/png")

    monkeypatch.setattr(render_pieza, "render_bytes", _render)

    r1 = cliente.get(f"/api/piezas/{pid}/compuesta")
    etag = r1.headers["etag"]
    r2 = cliente.get(f"/api/piezas/{pid}/compuesta", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert llamadas["n"] == 1  # el 304 NO recompuso (render solo en la 1ª)


def test_compuesta_404_si_no_hay_imagen_derivable(cliente, monkeypatch):
    from keni_consola.dominio import render_pieza

    pid = _crear(cliente).json()["pieza"]["id"]
    monkeypatch.setattr(render_pieza, "render_bytes", lambda pub: None)
    assert cliente.get(f"/api/piezas/{pid}/compuesta").status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/piezas/borrar-lote (borrado batch)                          #
# --------------------------------------------------------------------------- #


def test_borrar_lote(cliente):
    ids = [_crear(cliente, titulo=f"T{i}").json()["pieza"]["id"] for i in range(3)]
    r = cliente.post("/api/piezas/borrar-lote", json={"ids": ids})
    assert r.status_code == 200
    assert r.json() == {"borradas": 3, "fallos": []}
    assert cliente.get("/api/piezas").json()["piezas"] == []


def test_borrar_lote_reporta_fallos_parciales(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.post("/api/piezas/borrar-lote", json={"ids": [pid, "no-existe"]})
    assert r.status_code == 200
    datos = r.json()
    assert datos["borradas"] == 1
    assert datos["fallos"] == ["no-existe"]


def test_borrar_lote_sin_ids_400(cliente):
    assert cliente.post("/api/piezas/borrar-lote", json={}).status_code == 400
    assert cliente.post("/api/piezas/borrar-lote", json={"ids": []}).status_code == 400
    assert cliente.post("/api/piezas/borrar-lote", json={"ids": "x"}).status_code == 400


def test_borrar_lote_dedup_ids(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.post("/api/piezas/borrar-lote", json={"ids": [pid, pid]})
    assert r.json() == {"borradas": 1, "fallos": []}


# --------------------------------------------------------------------------- #
# GET /api/piezas/cadenas (cadenas de aprobacion en batch, feed)        #
# --------------------------------------------------------------------------- #


def test_cadenas_lote_devuelve_entrada_por_id(cliente):
    a = _crear(cliente, titulo="A").json()["pieza"]["id"]
    b = _crear(cliente, titulo="B").json()["pieza"]["id"]
    r = cliente.get(f"/api/piezas/cadenas?ids={a},{b}")
    assert r.status_code == 200
    cadenas = r.json()["cadenas"]
    assert set(cadenas) == {a, b}
    # Piezas recien creadas: sin cadena montada -> estado global "sin_cadena".
    assert cadenas[a]["estado"] == "sin_cadena"
    assert cadenas[a]["niveles"] == []
    assert "comentarios_sin_resolver" in cadenas[a]


def test_cadenas_lote_coincide_con_endpoint_individual(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    # Monta una cadena real (la misma que veria el endpoint individual).
    assert cliente.post(f"/api/plataformas/{pid}/aprobacion", json={}).status_code == 201
    individual = cliente.get(f"/api/plataformas/{pid}/aprobacion").json()
    lote = cliente.get(f"/api/piezas/cadenas?ids={pid}").json()["cadenas"][pid]
    assert lote == individual


def test_cadenas_lote_id_inexistente_sale_vacia_no_404(cliente):
    # El batch NUNCA omite ids (el cliente no debe reiterar "faltantes"): inexistente -> vacia.
    r = cliente.get("/api/piezas/cadenas?ids=fantasma")
    assert r.status_code == 200
    assert r.json()["cadenas"]["fantasma"]["estado"] == "sin_cadena"


def test_cadenas_lote_sin_ids_400(cliente):
    assert cliente.get("/api/piezas/cadenas").status_code == 400
    assert cliente.get("/api/piezas/cadenas?ids=,,").status_code == 400


# --------------------------------------------------------------------------- #
# Maquina de estados del PUT generico (tabla de transiciones)                  #
# --------------------------------------------------------------------------- #


def test_put_publicado_es_terminal_400(cliente):
    """Una pieza `publicado` NO se mueve por el PUT generico (ni a borrador ni a otro)."""
    pid = _crear(cliente).json()["pieza"]["id"]
    assert cliente.put(f"/api/piezas/{pid}", json={"estado": "publicado"}).status_code == 200
    for destino in ("borrador", "en_revision", "programado"):
        r = cliente.put(f"/api/piezas/{pid}", json={"estado": destino})
        assert r.status_code == 400, destino
        assert "Transición" in r.json()["error"]


def test_put_retroceso_invalido_400(cliente):
    """Retroceder a revisión NO se permite por el PUT genérico: `programado -> en_revision`
    se rechaza (desprogramar va a `borrador`; volver a revisión lo hace el flujo de revisión)."""
    pid = _crear(cliente, estado="programado").json()["pieza"]["id"]
    r = cliente.put(f"/api/piezas/{pid}", json={"estado": "en_revision"})
    assert r.status_code == 400
    assert "Transición" in r.json()["error"]


def test_put_mismo_estado_es_noop_permitido(cliente):
    pid = _crear(cliente, estado="en_revision").json()["pieza"]["id"]
    r = cliente.put(f"/api/piezas/{pid}", json={"estado": "en_revision"})
    assert r.status_code == 200
    assert r.json()["pieza"]["estado"] == "en_revision"


def test_put_desprogramar_a_borrador_permitido(cliente):
    pid = _crear(cliente, estado="programado").json()["pieza"]["id"]
    r = cliente.put(f"/api/piezas/{pid}", json={"estado": "borrador"})
    assert r.status_code == 200
    assert r.json()["pieza"]["estado"] == "borrador"


# --------------------------------------------------------------------------- #
# PUBLICADO es TERMINAL: ni se re-encola ni se le mueve la fecha               #
# --------------------------------------------------------------------------- #


def test_encolar_publicado_es_terminal_409(cliente):
    """Una pieza ya publicada NO se re-encola: el endpoint la rechaza ANTES de tocar nada."""
    pub = _crear(
        cliente, estado="publicado", fecha_programada="2026-06-15T18:00"
    ).json()["pieza"]
    pid = pub["id"]
    r = cliente.post(f"/api/piezas/{pid}/encolar")
    assert r.status_code == 409
    assert "publicada" in r.json()["error"].lower()
    # Sigue publicado, con su fecha intacta.
    despues = cliente.get(f"/api/piezas/{pid}").json()["pieza"]
    assert despues["estado"] == "publicado"
    assert despues["fecha_programada"] == "2026-06-15T18:00"


def test_put_fecha_programada_publicado_es_terminal_409(cliente):
    """Mover la `fecha_programada` de una pieza publicada miente sobre cuándo salió: 409,
    sin cambio. El no-op (misma fecha, distinto formato) SÍ se permite (guardado inocuo)."""
    pub = _crear(
        cliente, estado="publicado", fecha_programada="2026-06-15T18:00"
    ).json()["pieza"]
    pid = pub["id"]
    r = cliente.put(
        f"/api/piezas/{pid}", json={"fecha_programada": "2026-06-20T12:00"}
    )
    assert r.status_code == 409
    assert "publicada" in r.json()["error"].lower()
    despues = cliente.get(f"/api/piezas/{pid}").json()["pieza"]
    assert despues["estado"] == "publicado"
    assert despues["fecha_programada"] == "2026-06-15T18:00"
    # No-op: misma fecha con segundos -> tras el canon es idéntica -> 200 (no rompe).
    ok = cliente.put(
        f"/api/piezas/{pid}", json={"fecha_programada": "2026-06-15T18:00:00"}
    )
    assert ok.status_code == 200
    assert ok.json()["pieza"]["fecha_programada"] == "2026-06-15T18:00"


def test_put_mover_fecha_resetea_preparado_en(cliente):
    """REPROGRAMAR por PUT (arrastre del calendario) limpia `preparado_en`: sin esto el barrido
    vería la pieza 'ya preparada' y NO la (re)publicaría en la nueva hora (post perdido con
    KENI_PUBLICAR_REAL on). Espejo de lo que hace `_encolar_en_hueco_libre`."""
    from keni_consola import repos

    pid = _crear(
        cliente, estado="programado", fecha_programada="2026-06-15T18:00"
    ).json()["pieza"]["id"]
    # Estampa el claim de preparación (como hace el barrido al preparar la pieza).
    assert repos.reclamar_preparacion(pid, "2026-06-15T17:50:00")
    assert repos.obtener_pieza(pid)["preparado_en"] == "2026-06-15T17:50:00"

    r = cliente.put(
        f"/api/piezas/{pid}", json={"fecha_programada": "2026-06-16T19:00"}
    )
    assert r.status_code == 200
    despues = repos.obtener_pieza(pid)
    assert despues["fecha_programada"] == "2026-06-16T19:00"
    assert despues["preparado_en"] == ""  # claim reseteado: el barrido la volverá a publicar


def test_put_misma_fecha_conserva_preparado_en(cliente):
    """El no-op de fecha (guardar la MISMA hora) NO resetea `preparado_en`: no es reprogramar,
    así que no se debe re-publicar una pieza ya preparada."""
    from keni_consola import repos

    pid = _crear(
        cliente, estado="programado", fecha_programada="2026-06-15T18:00"
    ).json()["pieza"]["id"]
    assert repos.reclamar_preparacion(pid, "2026-06-15T17:50:00")
    r = cliente.put(
        f"/api/piezas/{pid}", json={"fecha_programada": "2026-06-15T18:00"}
    )
    assert r.status_code == 200
    assert repos.obtener_pieza(pid)["preparado_en"] == "2026-06-15T17:50:00"


# --------------------------------------------------------------------------- #
# Canon de fecha_programada (minutos, UTC sin offset)                          #
# --------------------------------------------------------------------------- #


def test_fecha_programada_se_normaliza_a_minutos(cliente):
    """El UNIQUE de parrilla compara el TEXT crudo: 'T18:00:00' y 'T18:00' deben quedar
    iguales tras la normalizacion."""
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.put(
        f"/api/piezas/{pid}",
        json={"estado": "programado", "fecha_programada": "2026-06-10T18:00:00"},
    )
    assert r.status_code == 200
    assert r.json()["pieza"]["fecha_programada"] == "2026-06-10T18:00"


def test_fecha_programada_con_offset_se_convierte_a_utc(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.put(
        f"/api/piezas/{pid}",
        json={"estado": "programado", "fecha_programada": "2026-06-10T12:00:00-06:00"},
    )
    assert r.status_code == 200
    assert r.json()["pieza"]["fecha_programada"] == "2026-06-10T18:00"


def test_fecha_programada_invalida_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.put(
        f"/api/piezas/{pid}", json={"fecha_programada": "manana a las 6"}
    )
    assert r.status_code == 400
    assert "fecha" in r.json()["error"].lower()


def test_crear_normaliza_fecha_programada(cliente):
    pub = _crear(
        cliente, estado="programado", fecha_programada="2026-06-11T09:30:15"
    ).json()["pieza"]
    assert pub["fecha_programada"] == "2026-06-11T09:30"


def test_doble_reserva_mismo_slot_con_formatos_distintos_409(cliente):
    """Dos piezas al MISMO instante con formatos distintos ('T18:00' vs 'T18:00:00')
    chocan tras el canon: la segunda recibe 409."""
    a = _crear(cliente).json()["pieza"]["id"]
    b = _crear(cliente).json()["pieza"]["id"]
    r1 = cliente.put(
        f"/api/piezas/{a}",
        json={"estado": "programado", "fecha_programada": "2026-06-12T18:00"},
    )
    assert r1.status_code == 200
    r2 = cliente.put(
        f"/api/piezas/{b}",
        json={"estado": "programado", "fecha_programada": "2026-06-12T18:00:00"},
    )
    assert r2.status_code == 409


# --------------------------------------------------------------------------- #
# Topes del servidor: cap de listado y body JSON maximo                       #
# --------------------------------------------------------------------------- #


def test_listado_respeta_cap_de_servidor(cliente, monkeypatch):
    monkeypatch.setenv("KENI_LISTADO_MAX", "2")
    for i in range(4):
        _crear(cliente, titulo=f"Cap{i}")
    datos = cliente.get("/api/piezas").json()
    assert len(datos["piezas"]) == 2  # acotado por el cap
    assert datos["paginacion"]["total"] == 4  # el total sigue siendo exacto
    assert datos["paginacion"]["limite"] == 2  # cap reportado (hubo truncado)


def test_body_json_gigante_413(cliente, monkeypatch):
    monkeypatch.setenv("KENI_JSON_MAX_BYTES", "1024")
    r = cliente.post(
        "/api/piezas",
        json={"marca": "unotv", "red": "x", "titulo": "T", "contenido": "x" * 5000},
    )
    assert r.status_code == 413

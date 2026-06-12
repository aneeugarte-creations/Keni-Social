"""Tests de la API Publicaciones (/api/publicaciones). OFFLINE, DB en tmp.

Cubre: opciones (catalogos), CRUD, lote, filtros, validaciones (marca/red/estado),
resolucion de nombres legibles y edicion parcial.
"""

from __future__ import annotations


def _crear(cliente, **campos):
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    return cliente.post("/api/publicaciones", json=base)


# --------------------------------------------------------------------------- #
# GET /api/publicaciones/opciones                                             #
# --------------------------------------------------------------------------- #


def test_opciones(cliente):
    datos = cliente.get("/api/publicaciones/opciones").json()
    assert {"redes", "estados", "marcas"} <= set(datos)
    # redes en orden fijo con limite
    ids = [r["id"] for r in datos["redes"]]
    assert ids == ["x", "instagram", "facebook", "tiktok", "youtube"]
    x = datos["redes"][0]
    assert x == {"id": "x", "nombre": "X", "limite": 280}
    assert datos["redes"][2]["limite"] is None  # facebook
    # estados con nombre legible
    estados = {e["id"]: e["nombre"] for e in datos["estados"]}
    assert estados == {
        "borrador": "Borrador",
        "en_revision": "En revisión",
        "aprobado": "Aprobado",
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
    pub = r.json()["publicacion"]
    assert pub["id"]
    assert pub["estado"] == "borrador"
    assert pub["marca_nombre"] == "UnoTV"
    assert pub["red_nombre"] == "X"
    listado = cliente.get("/api/publicaciones").json()["publicaciones"]
    assert len(listado) == 1


def test_crear_estado_explicito(cliente):
    pub = _crear(cliente, estado="aprobado").json()["publicacion"]
    assert pub["estado"] == "aprobado"


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
    r = cliente.post("/api/publicaciones", json={"marca": "unotv", "red": "x", "titulo": 5})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Filtros                                                                     #
# --------------------------------------------------------------------------- #


def test_filtros(cliente):
    _crear(cliente, red="x", estado="borrador")
    _crear(cliente, red="instagram", estado="aprobado")
    _crear(cliente, marca="piso-15", red="x")
    assert len(cliente.get("/api/publicaciones?marca=unotv").json()["publicaciones"]) == 2
    assert len(cliente.get("/api/publicaciones?red=x").json()["publicaciones"]) == 2
    assert len(cliente.get("/api/publicaciones?estado=aprobado").json()["publicaciones"]) == 1
    assert (
        len(cliente.get("/api/publicaciones?marca=unotv&red=x").json()["publicaciones"]) == 1
    )


def test_opciones_incluye_lineas(cliente):
    """`opciones.lineas` expone las etiquetas verticales (líneas editoriales) activas."""
    from keni_consola import repos

    repos.crear_etiqueta(nombre="Deportes", clase="vertical", marca="unotv")
    # Una etiqueta de OTRA clase no debe colarse como línea editorial.
    repos.crear_etiqueta(nombre="Mundial", clase="campania", marca="unotv")
    lineas = cliente.get("/api/publicaciones/opciones").json()["lineas"]
    nombres = {l["nombre"] for l in lineas}
    assert "Deportes" in nombres
    assert "Mundial" not in nombres


def test_filtro_linea(cliente):
    """`?linea=<id>` deja solo las piezas cuyo contenido padre tiene esa etiqueta vertical."""
    from keni_consola import repos

    etiqueta = repos.crear_etiqueta(nombre="Política", clase="vertical", marca="unotv")
    con_linea = _crear(cliente, titulo="Con línea").json()["publicacion"]
    _crear(cliente, titulo="Sin línea")
    repos.asignar_etiqueta(con_linea["contenido_id"], etiqueta["id"])

    filtrado = cliente.get(f"/api/publicaciones?linea={etiqueta['id']}").json()
    assert [p["titulo"] for p in filtrado["publicaciones"]] == ["Con línea"]
    assert filtrado["paginacion"]["total"] == 1


def test_payload_incluye_responsable(cliente):
    """Toda publicación expone `responsable_id`/`responsable_nombre` ("" = libre)."""
    pub = _crear(cliente).json()["publicacion"]
    assert pub["responsable_id"] == ""
    assert pub["responsable_nombre"] == ""
    listado = cliente.get("/api/publicaciones").json()["publicaciones"]
    assert listado[0]["responsable_id"] == ""
    assert listado[0]["responsable_nombre"] == ""


def test_filtro_responsable(cliente):
    """`?responsable=<id>` = piezas cogidas por ese usuario; `?responsable=sin` = libres.

    El responsable vive en el `contenido` PADRE (el reparto es del tema): cogerlo via
    `repos.reclamar_contenido` se refleja en TODAS sus piezas por red.
    """
    from keni_consola import repos

    cogida = _crear(cliente, titulo="Cogida").json()["publicacion"]
    _crear(cliente, titulo="Libre")
    asignada = repos.reclamar_contenido(
        cogida["contenido_id"], responsable_id="u-elias", responsable_nombre="Elías"
    )
    assert asignada is not None

    mias = cliente.get("/api/publicaciones?responsable=u-elias").json()
    assert [p["titulo"] for p in mias["publicaciones"]] == ["Cogida"]
    assert mias["publicaciones"][0]["responsable_nombre"] == "Elías"
    assert mias["paginacion"]["total"] == 1

    libres = cliente.get("/api/publicaciones?responsable=sin").json()
    assert [p["titulo"] for p in libres["publicaciones"]] == ["Libre"]
    assert libres["paginacion"]["total"] == 1

    # Sin el filtro se ven TODAS (el reparto no oculta nada por defecto).
    assert len(cliente.get("/api/publicaciones").json()["publicaciones"]) == 2


def test_filtro_responsable_compone_con_marca(cliente):
    """El filtro de reparto compone con los demás (marca): la vista de ClaroSports."""
    from keni_consola import repos

    cs = _crear(cliente, marca="claro-sports", titulo="CS cogida").json()["publicacion"]
    _crear(cliente, marca="claro-sports", titulo="CS libre")
    uno = _crear(cliente, marca="unotv", titulo="Uno cogida").json()["publicacion"]
    repos.reclamar_contenido(cs["contenido_id"], responsable_id="u1", responsable_nombre="Ana")
    repos.reclamar_contenido(uno["contenido_id"], responsable_id="u1", responsable_nombre="Ana")

    r = cliente.get("/api/publicaciones?marca=claro-sports&responsable=u1").json()
    assert [p["titulo"] for p in r["publicaciones"]] == ["CS cogida"]
    r = cliente.get("/api/publicaciones?marca=claro-sports&responsable=sin").json()
    assert [p["titulo"] for p in r["publicaciones"]] == ["CS libre"]


def test_filtro_rango_fecha_programada(cliente):
    """`?desde=&hasta=` acota por `fecha_programada`; las piezas SIN fecha quedan FUERA.

    El CALENDARIO pide solo la ventana visible (mes ± margen) en vez del conjunto completo
    que el cap de 1000 truncaba en silencio.
    """
    _crear(cliente, titulo="Dentro", estado="programado", fecha_programada="2026-06-15T18:00")
    _crear(cliente, titulo="Antes", estado="programado", fecha_programada="2026-05-20T18:00")
    _crear(cliente, titulo="Despues", estado="programado", fecha_programada="2026-08-01T18:00")
    _crear(cliente, titulo="Sin fecha")  # borrador sin fecha_programada

    r = cliente.get("/api/publicaciones?desde=2026-06-01&hasta=2026-06-30").json()
    assert [p["titulo"] for p in r["publicaciones"]] == ["Dentro"]
    # El total respeta el rango (no es el global): la paginación no miente por omisión.
    assert r["paginacion"]["total"] == 1

    # Sin el rango se ven TODAS (retrocompatible), incluida la pieza sin fecha.
    todas = cliente.get("/api/publicaciones").json()
    assert {p["titulo"] for p in todas["publicaciones"]} == {
        "Dentro", "Antes", "Despues", "Sin fecha",
    }


def test_filtro_solo_hasta_excluye_sin_fecha(cliente):
    """Con solo `?hasta=` la pieza sin fecha (cadena vacía) NO debe colarse en el rango."""
    _crear(cliente, titulo="Programada", estado="programado", fecha_programada="2026-06-15T18:00")
    _crear(cliente, titulo="Sin fecha")
    r = cliente.get("/api/publicaciones?hasta=2026-12-31").json()
    assert [p["titulo"] for p in r["publicaciones"]] == ["Programada"]


# --------------------------------------------------------------------------- #
# Lote                                                                        #
# --------------------------------------------------------------------------- #


def test_crear_lote(cliente):
    r = cliente.post(
        "/api/publicaciones/lote",
        json={
            "publicaciones": [
                {"marca": "unotv", "red": "x", "contenido": "a"},
                {"marca": "unotv", "red": "instagram", "contenido": "b"},
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["publicaciones"]) == 2
    assert len(cliente.get("/api/publicaciones").json()["publicaciones"]) == 2


def test_lote_una_invalida_no_inserta_nada(cliente):
    r = cliente.post(
        "/api/publicaciones/lote",
        json={
            "publicaciones": [
                {"marca": "unotv", "red": "x"},
                {"marca": "unotv", "red": "myspace"},  # invalida
            ]
        },
    )
    assert r.status_code == 400
    # todo o nada: no se inserto la primera
    assert cliente.get("/api/publicaciones").json()["publicaciones"] == []


def test_lote_vacio_400(cliente):
    r = cliente.post("/api/publicaciones/lote", json={"publicaciones": []})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# GET / PUT / DELETE por id                                                   #
# --------------------------------------------------------------------------- #


def test_detalle(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.get(f"/api/publicaciones/{pid}")
    assert r.status_code == 200
    assert r.json()["publicacion"]["id"] == pid


def test_detalle_404(cliente):
    assert cliente.get("/api/publicaciones/noexiste").status_code == 404


def test_actualizar_parcial(cliente):
    pid = _crear(cliente, titulo="Viejo").json()["publicacion"]["id"]
    r = cliente.put(
        f"/api/publicaciones/{pid}", json={"titulo": "Nuevo", "estado": "aprobado"}
    )
    assert r.status_code == 200
    pub = r.json()["publicacion"]
    assert pub["titulo"] == "Nuevo"
    assert pub["estado"] == "aprobado"


def test_crear_y_editar_copy_in(cliente):
    # El copy_in (texto EN imagen) se acepta al crear y se edita por PUT, independiente del
    # contenido. Nace "" si no se manda.
    pub = _crear(cliente).json()["publicacion"]
    assert pub["copy_in"] == ""
    r = cliente.put(
        f"/api/publicaciones/{pub['id']}", json={"copy_in": "TITULAR EN LA IMAGEN"}
    )
    assert r.status_code == 200
    editada = r.json()["publicacion"]
    assert editada["copy_in"] == "TITULAR EN LA IMAGEN"
    assert editada["contenido"] == "C"  # el contenido no se toca


def test_actualizar_copy_in_no_texto_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"copy_in": 123})
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

    pid = _crear(cliente, marca="unotv").json()["publicacion"]["id"]
    cliente.put(f"/api/publicaciones/{pid}", json={"copy_in": "DATO CLAVE"})
    r = cliente.post(f"/api/publicaciones/{pid}/integrar-foto", json={"imagen": "foto-real.jpg"})
    assert r.status_code == 200
    body = r.json()
    assert body["imagen"] == "compuesta.png"
    assert body["imagen_url"] == "/api/media/compuesta.png"
    assert llamadas == [{"imagen": "foto-real.jpg", "marca": "unotv", "titular": "DATO CLAVE"}]


def test_integrar_foto_marca_sin_plantilla_devuelve_foto(cliente):
    # Marca sin identidad visual (piso-15): no recompone; devuelve la foto tal cual.
    pid = _crear(cliente, marca="piso-15").json()["publicacion"]["id"]
    r = cliente.post(f"/api/publicaciones/{pid}/integrar-foto", json={"imagen": "foto-real.jpg"})
    assert r.status_code == 200
    assert r.json()["imagen"] == "foto-real.jpg"


def test_integrar_foto_sin_imagen_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.post(f"/api/publicaciones/{pid}/integrar-foto", json={})
    assert r.status_code == 400


def test_integrar_foto_404(cliente):
    r = cliente.post("/api/publicaciones/noexiste/integrar-foto", json={"imagen": "x.jpg"})
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
    pid = _crear(cliente, marca="unotv").json()["publicacion"]["id"]
    r = cliente.post(
        f"/api/publicaciones/{pid}/aplicar-plantilla",
        json={"plantilla_id": plantilla["id"], "foto": "f.jpg", "copy_in": "Y"},
    )
    assert r.status_code == 200, r.text
    pub = r.json()["publicacion"]
    assert pub["imagen"] == ""  # NO se hornea
    assert pub["plantilla_diseno_id"] == plantilla["id"]
    assert pub["foto"] == "f.jpg"
    # La URL puede llevar sufijo `?v=` (cache-bust por `actualizado`); comparamos solo la ruta.
    assert pub["imagen_url"].split("?")[0] == f"/api/publicaciones/{pid}/compuesta"


def test_actualizar_estado_invalido_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"estado": "archivado"})
    assert r.status_code == 400


def test_actualizar_sin_campos_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={})
    assert r.status_code == 400


def test_actualizar_404(cliente):
    r = cliente.put("/api/publicaciones/noexiste", json={"titulo": "x"})
    assert r.status_code == 404


def test_actualizar_no_toca_marca_ni_red(cliente):
    """La edicion parcial ignora marca/red aunque vengan en el body."""
    pid = _crear(cliente, marca="unotv", red="x").json()["publicacion"]["id"]
    r = cliente.put(
        f"/api/publicaciones/{pid}", json={"titulo": "Z", "marca": "piso-15", "red": "youtube"}
    )
    pub = r.json()["publicacion"]
    assert pub["marca"] == "unotv"
    assert pub["red"] == "x"


def test_borrar(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.delete(f"/api/publicaciones/{pid}").status_code == 200
    assert cliente.get(f"/api/publicaciones/{pid}").status_code == 404


def test_borrar_404(cliente):
    assert cliente.delete("/api/publicaciones/noexiste").status_code == 404


# --------------------------------------------------------------------------- #
# GET /api/publicaciones/{id}/compuesta (render on-demand)                     #
# --------------------------------------------------------------------------- #


def test_compuesta_404_si_no_existe(cliente):
    assert cliente.get("/api/publicaciones/noexiste/compuesta").status_code == 404


def test_compuesta_sirve_bytes_efimeros_con_etag(cliente, monkeypatch):
    """El endpoint renderiza ON-DEMAND, sirve los bytes con su mime y un ETag (sin persistir)."""
    from keni_consola.dominio import render_pieza

    pid = _crear(cliente).json()["publicacion"]["id"]
    monkeypatch.setattr(render_pieza, "render_bytes", lambda pub: (b"PNG-BYTES", "image/png"))

    r = cliente.get(f"/api/publicaciones/{pid}/compuesta")
    assert r.status_code == 200
    assert r.content == b"PNG-BYTES"
    assert r.headers["content-type"].startswith("image/png")
    assert r.headers.get("etag")  # ETag presente para la caché HTTP


def test_compuesta_304_si_etag_coincide(cliente, monkeypatch):
    """Con If-None-Match igual al ETag (receta sin cambios) -> 304 SIN recomponer."""
    from keni_consola.dominio import render_pieza

    pid = _crear(cliente).json()["publicacion"]["id"]
    llamadas = {"n": 0}

    def _render(pub):
        llamadas["n"] += 1
        return (b"PNG-BYTES", "image/png")

    monkeypatch.setattr(render_pieza, "render_bytes", _render)

    r1 = cliente.get(f"/api/publicaciones/{pid}/compuesta")
    etag = r1.headers["etag"]
    r2 = cliente.get(f"/api/publicaciones/{pid}/compuesta", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert llamadas["n"] == 1  # el 304 NO recompuso (render solo en la 1ª)


def test_compuesta_404_si_no_hay_imagen_derivable(cliente, monkeypatch):
    from keni_consola.dominio import render_pieza

    pid = _crear(cliente).json()["publicacion"]["id"]
    monkeypatch.setattr(render_pieza, "render_bytes", lambda pub: None)
    assert cliente.get(f"/api/publicaciones/{pid}/compuesta").status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/publicaciones/borrar-lote (borrado batch)                          #
# --------------------------------------------------------------------------- #


def test_borrar_lote(cliente):
    ids = [_crear(cliente, titulo=f"T{i}").json()["publicacion"]["id"] for i in range(3)]
    r = cliente.post("/api/publicaciones/borrar-lote", json={"ids": ids})
    assert r.status_code == 200
    assert r.json() == {"borradas": 3, "fallos": []}
    assert cliente.get("/api/publicaciones").json()["publicaciones"] == []


def test_borrar_lote_reporta_fallos_parciales(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.post("/api/publicaciones/borrar-lote", json={"ids": [pid, "no-existe"]})
    assert r.status_code == 200
    datos = r.json()
    assert datos["borradas"] == 1
    assert datos["fallos"] == ["no-existe"]


def test_borrar_lote_sin_ids_400(cliente):
    assert cliente.post("/api/publicaciones/borrar-lote", json={}).status_code == 400
    assert cliente.post("/api/publicaciones/borrar-lote", json={"ids": []}).status_code == 400
    assert cliente.post("/api/publicaciones/borrar-lote", json={"ids": "x"}).status_code == 400


def test_borrar_lote_dedup_ids(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.post("/api/publicaciones/borrar-lote", json={"ids": [pid, pid]})
    assert r.json() == {"borradas": 1, "fallos": []}


# --------------------------------------------------------------------------- #
# GET /api/publicaciones/cadenas (cadenas de aprobacion en batch, feed)        #
# --------------------------------------------------------------------------- #


def test_cadenas_lote_devuelve_entrada_por_id(cliente):
    a = _crear(cliente, titulo="A").json()["publicacion"]["id"]
    b = _crear(cliente, titulo="B").json()["publicacion"]["id"]
    r = cliente.get(f"/api/publicaciones/cadenas?ids={a},{b}")
    assert r.status_code == 200
    cadenas = r.json()["cadenas"]
    assert set(cadenas) == {a, b}
    # Piezas recien creadas: sin cadena montada -> estado global "sin_cadena".
    assert cadenas[a]["estado"] == "sin_cadena"
    assert cadenas[a]["niveles"] == []
    assert "comentarios_sin_resolver" in cadenas[a]


def test_cadenas_lote_coincide_con_endpoint_individual(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    # Monta una cadena real (la misma que veria el endpoint individual).
    assert cliente.post(f"/api/plataformas/{pid}/aprobacion", json={}).status_code == 201
    individual = cliente.get(f"/api/plataformas/{pid}/aprobacion").json()
    lote = cliente.get(f"/api/publicaciones/cadenas?ids={pid}").json()["cadenas"][pid]
    assert lote == individual


def test_cadenas_lote_id_inexistente_sale_vacia_no_404(cliente):
    # El batch NUNCA omite ids (el cliente no debe reiterar "faltantes"): inexistente -> vacia.
    r = cliente.get("/api/publicaciones/cadenas?ids=fantasma")
    assert r.status_code == 200
    assert r.json()["cadenas"]["fantasma"]["estado"] == "sin_cadena"


def test_cadenas_lote_sin_ids_400(cliente):
    assert cliente.get("/api/publicaciones/cadenas").status_code == 400
    assert cliente.get("/api/publicaciones/cadenas?ids=,,").status_code == 400


# --------------------------------------------------------------------------- #
# Maquina de estados del PUT generico (tabla de transiciones)                  #
# --------------------------------------------------------------------------- #


def test_put_publicado_es_terminal_400(cliente):
    """Una pieza `publicado` NO se mueve por el PUT generico (ni a borrador ni a otro)."""
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.put(f"/api/publicaciones/{pid}", json={"estado": "publicado"}).status_code == 200
    for destino in ("borrador", "en_revision", "aprobado", "programado"):
        r = cliente.put(f"/api/publicaciones/{pid}", json={"estado": destino})
        assert r.status_code == 400, destino
        assert "Transición" in r.json()["error"]


def test_put_retroceso_invalido_400(cliente):
    """Retroceder solo se permite a `borrador` (o programado->aprobado): `aprobado ->
    en_revision` por el PUT generico se rechaza (eso lo hace el flujo de revision)."""
    pid = _crear(cliente, estado="aprobado").json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"estado": "en_revision"})
    assert r.status_code == 400
    assert "Transición" in r.json()["error"]


def test_put_mismo_estado_es_noop_permitido(cliente):
    pid = _crear(cliente, estado="aprobado").json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"estado": "aprobado"})
    assert r.status_code == 200
    assert r.json()["publicacion"]["estado"] == "aprobado"


def test_put_desprogramar_a_aprobado_permitido(cliente):
    pid = _crear(cliente, estado="programado").json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"estado": "aprobado"})
    assert r.status_code == 200
    assert r.json()["publicacion"]["estado"] == "aprobado"


# --------------------------------------------------------------------------- #
# Canon de fecha_programada (minutos, UTC sin offset)                          #
# --------------------------------------------------------------------------- #


def test_fecha_programada_se_normaliza_a_minutos(cliente):
    """El UNIQUE de parrilla compara el TEXT crudo: 'T18:00:00' y 'T18:00' deben quedar
    iguales tras la normalizacion (antes no chocaban y se doble-reservaba el slot)."""
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(
        f"/api/publicaciones/{pid}",
        json={"estado": "programado", "fecha_programada": "2026-06-10T18:00:00"},
    )
    assert r.status_code == 200
    assert r.json()["publicacion"]["fecha_programada"] == "2026-06-10T18:00"


def test_fecha_programada_con_offset_se_convierte_a_utc(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(
        f"/api/publicaciones/{pid}",
        json={"estado": "programado", "fecha_programada": "2026-06-10T12:00:00-06:00"},
    )
    assert r.status_code == 200
    assert r.json()["publicacion"]["fecha_programada"] == "2026-06-10T18:00"


def test_fecha_programada_invalida_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(
        f"/api/publicaciones/{pid}", json={"fecha_programada": "manana a las 6"}
    )
    assert r.status_code == 400
    assert "fecha" in r.json()["error"].lower()


def test_crear_normaliza_fecha_programada(cliente):
    pub = _crear(
        cliente, estado="programado", fecha_programada="2026-06-11T09:30:15"
    ).json()["publicacion"]
    assert pub["fecha_programada"] == "2026-06-11T09:30"


def test_doble_reserva_mismo_slot_con_formatos_distintos_409(cliente):
    """Dos piezas al MISMO instante con formatos distintos ('T18:00' vs 'T18:00:00')
    chocan tras el canon: la segunda recibe 409 (antes pasaban ambas)."""
    a = _crear(cliente).json()["publicacion"]["id"]
    b = _crear(cliente).json()["publicacion"]["id"]
    r1 = cliente.put(
        f"/api/publicaciones/{a}",
        json={"estado": "programado", "fecha_programada": "2026-06-12T18:00"},
    )
    assert r1.status_code == 200
    r2 = cliente.put(
        f"/api/publicaciones/{b}",
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
    datos = cliente.get("/api/publicaciones").json()
    assert len(datos["publicaciones"]) == 2  # acotado por el cap
    assert datos["paginacion"]["total"] == 4  # el total sigue siendo exacto
    assert datos["paginacion"]["limite"] == 2  # cap reportado (hubo truncado)


def test_body_json_gigante_413(cliente, monkeypatch):
    monkeypatch.setenv("KENI_JSON_MAX_BYTES", "1024")
    r = cliente.post(
        "/api/publicaciones",
        json={"marca": "unotv", "red": "x", "titulo": "T", "contenido": "x" * 5000},
    )
    assert r.status_code == 413

"""Tests de la PAGINACION KEYSET (scroll infinito del feed). OFFLINE, todo en tmp.

El feed social pide páginas por cursor `?cursor=<creado>|<id>` en el orden estable
`(creado DESC, id DESC)`. Verifica que:
  - las páginas no se solapan ni saltan filas (límites estables);
  - `paginacion.cursor_siguiente` apunta a la última fila vista mientras hay más, y se
    OMITE en la última página (señal de fin de scroll);
  - una inserción nueva al principio NO desplaza la página siguiente (inmunidad del keyset);
  - el modo offset/completo de siempre sigue intacto (retrocompat de otros callers).

Se inyecta `fecha_creacion` explícita y creciente para un orden determinista (el default
es `now()` a segundos, que colisionaría en inserciones rápidas; el desempate por `id` lo
cubriría igual, pero así el test es inequívoco).
"""

from __future__ import annotations

from urllib.parse import quote

from keni_consola import repos


def _crear(titulo: str, creado: str) -> dict:
    """Crea una publicación con `fecha_creacion` fija (orden determinista del keyset)."""
    return repos.crear_pieza(
        "unotv", "x", titulo=titulo, contenido="C", fecha_creacion=creado
    )


def test_keyset_recorre_todo_sin_solape_ni_huecos(cliente):
    # 5 piezas con creado creciente -> el feed las ve en orden DESC (la más nueva primero).
    for i in range(5):
        _crear(f"P{i}", f"2026-01-0{i + 1}T00:00:00")

    vistos: list[str] = []
    cursor: str | None = None
    paginas = 0
    while True:
        # `feed=1` activa el keyset desde la 1ª página (como hace el frontend); `cursor` encadena.
        ruta = "/api/piezas?feed=1&limite=2"
        if cursor:
            ruta += f"&cursor={quote(cursor)}"
        datos = cliente.get(ruta).json()
        vistos.extend(p["id"] for p in datos["piezas"])
        paginas += 1
        cursor = datos["paginacion"].get("cursor_siguiente")
        if not cursor:
            break
        assert paginas < 10  # cota de seguridad: nunca debería bucle infinito

    # Todas las piezas, exactamente una vez, sin solape ni huecos.
    assert len(vistos) == 5
    assert len(set(vistos)) == 5
    # Orden DESC por creado: la más nueva (P4) primero, la más vieja (P0) al final.
    titulos = [repos.obtener_pieza(i)["titulo"] for i in vistos]
    assert titulos == ["P4", "P3", "P2", "P1", "P0"]


def test_cursor_siguiente_presente_mientras_hay_mas_y_ausente_al_final(cliente):
    for i in range(3):
        _crear(f"P{i}", f"2026-01-0{i + 1}T00:00:00")

    # Página llena (feed, limite=2, hay 3): debe traer cursor de continuación.
    p1 = cliente.get("/api/piezas?feed=1&limite=2").json()
    assert len(p1["piezas"]) == 2
    assert p1["paginacion"].get("cursor_siguiente")

    # Última página (1 fila restante, menos que el límite): SIN cursor (fin del scroll).
    p2 = cliente.get(
        f"/api/piezas?feed=1&limite=2&cursor={quote(p1['paginacion']['cursor_siguiente'])}"
    ).json()
    assert len(p2["piezas"]) == 1
    assert "cursor_siguiente" not in p2["paginacion"]


def test_insercion_nueva_no_desplaza_la_pagina_siguiente(cliente):
    # Keyset inmune a inserciones: tras leer la 1ª página, una pieza MÁS NUEVA que se inserte
    # no aparece al pedir la siguiente página (el cursor ancla la posición por su clave).
    for i in range(4):
        _crear(f"P{i}", f"2026-01-0{i + 1}T00:00:00")

    p1 = cliente.get("/api/piezas?feed=1&limite=2").json()
    ids_p1 = [p["id"] for p in p1["piezas"]]
    cursor = p1["paginacion"]["cursor_siguiente"]

    # Inserta una pieza aún más nueva (iría al principio en orden DESC).
    _crear("NUEVA", "2026-02-01T00:00:00")

    p2 = cliente.get(f"/api/piezas?feed=1&limite=2&cursor={quote(cursor)}").json()
    ids_p2 = [p["id"] for p in p2["piezas"]]
    # La nueva NO se cuela en la página siguiente, y no hay solape con la primera.
    titulos_p2 = [repos.obtener_pieza(i)["titulo"] for i in ids_p2]
    assert "NUEVA" not in titulos_p2
    assert not (set(ids_p1) & set(ids_p2))


def test_modo_completo_sin_cursor_sigue_intacto(cliente):
    # Sin `?limite=` ni `?cursor=`: conjunto completo, con `total` exacto y SIN cursor_siguiente
    # (retrocompat de calendario/lista que esperan todas las filas).
    for i in range(3):
        _crear(f"P{i}", f"2026-01-0{i + 1}T00:00:00")
    datos = cliente.get("/api/piezas").json()
    assert len(datos["piezas"]) == 3
    assert datos["paginacion"]["total"] == 3
    assert "cursor_siguiente" not in datos["paginacion"]


def test_modo_offset_puro_no_emite_cursor(cliente):
    # OFFSET clásico (`?limite=` SIN `?feed=`): retrocompat de GestionPublicaciones, que pagina
    # por offset y lee `total`. NO debe emitir `cursor_siguiente` (no es modo feed).
    for i in range(3):
        _crear(f"P{i}", f"2026-01-0{i + 1}T00:00:00")
    datos = cliente.get("/api/piezas?limite=2&desplazamiento=0").json()
    assert len(datos["piezas"]) == 2
    assert datos["paginacion"] == {"total": 3, "limite": 2, "desplazamiento": 0}
    assert "cursor_siguiente" not in datos["paginacion"]

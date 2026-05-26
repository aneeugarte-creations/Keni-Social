"""Tests de la heuristica de reciclaje proactivo (`dominio.reciclaje`). PUROS.

No tocan persistencia ni red: alimentan dicts de publicaciones y fijan `hoy` para
hacer la heuristica deterministica. Cubren las tres senales (efemeride, perenne,
recurrente), la exclusion de copias ya recicladas, el orden y el tope.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from keni_consola.dominio import reciclaje


def _pub(**campos):
    """Publicacion minima con valores por defecto razonables."""
    base = {
        "id": "p1",
        "titulo": "Titulo",
        "marca": "unotv",
        "red": "x",
        "contenido": "",
        "estado": "publicado",
        "evergreen": False,
        "fecha_creacion": "2024-01-01T10:00:00",
        "fecha_actualizacion": "2024-01-01T10:00:00",
    }
    base.update(campos)
    return base


def _hace(dias: int, hoy: date) -> str:
    return (datetime(hoy.year, hoy.month, hoy.day) - timedelta(days=dias)).isoformat(
        timespec="seconds"
    )


# --------------------------------------------------------------------------- #
# Efemeride                                                                    #
# --------------------------------------------------------------------------- #


def test_efemeride_proxima_propone_con_motivo():
    hoy = date(2026, 5, 5)  # Dia de las Madres (10-may) cae en 5 dias
    pub = _pub(id="p1", titulo="Las mejores ideas para el Día de las Madres", estado="publicado")
    out = reciclaje.candidatas_reciclaje([pub], hoy=hoy)
    assert len(out) == 1
    assert out[0]["id"] == "p1"
    assert out[0]["motivo"] == reciclaje.MOTIVO_EFEMERIDE
    assert "Madres" in out[0]["motivo_detalle"]


def test_efemeride_lejana_no_propone():
    hoy = date(2026, 6, 1)  # nada dentro de la ventana de 21 dias
    pub = _pub(titulo="Día de Muertos: la ofrenda", estado="publicado")
    assert reciclaje.candidatas_reciclaje([pub], hoy=hoy) == []


def test_efemeride_solo_sobre_piezas_publicadas():
    hoy = date(2026, 5, 5)
    pub = _pub(titulo="Día de las Madres", estado="borrador")
    assert reciclaje.candidatas_reciclaje([pub], hoy=hoy) == []


# --------------------------------------------------------------------------- #
# Perenne madurada                                                             #
# --------------------------------------------------------------------------- #


def test_perenne_madurada_propone():
    hoy = date(2026, 5, 25)
    pub = _pub(
        id="ever",
        titulo="Guía atemporal de seguridad vial",
        evergreen=True,
        estado="publicado",
        fecha_actualizacion=_hace(45, hoy),
        fecha_creacion=_hace(60, hoy),
    )
    out = reciclaje.candidatas_reciclaje([pub], hoy=hoy)
    assert len(out) == 1
    assert out[0]["motivo"] == reciclaje.MOTIVO_PERENNE
    assert "perenne" in out[0]["motivo_detalle"].lower()


def test_perenne_reciente_no_propone():
    hoy = date(2026, 5, 25)
    pub = _pub(
        evergreen=True,
        estado="publicado",
        fecha_actualizacion=_hace(5, hoy),
        fecha_creacion=_hace(5, hoy),
    )
    assert reciclaje.candidatas_reciclaje([pub], hoy=hoy) == []


def test_no_perenne_no_propone_por_esa_senal():
    hoy = date(2026, 5, 25)
    pub = _pub(
        evergreen=False,
        estado="publicado",
        fecha_actualizacion=_hace(200, hoy),
        fecha_creacion=_hace(200, hoy),
        titulo="Algo cualquiera sin tema",
    )
    # Sin efemeride, sin perenne y sin tema recurrente (no hay piezas recientes).
    assert reciclaje.candidatas_reciclaje([pub], hoy=hoy) == []


# --------------------------------------------------------------------------- #
# Tema recurrente                                                              #
# --------------------------------------------------------------------------- #


def test_tema_recurrente_propone_pieza_antigua():
    hoy = date(2026, 5, 25)
    vieja = _pub(
        id="vieja",
        titulo="Sismo: protocolo de evacuación recomendado",
        contenido="qué hacer durante un sismo fuerte",
        estado="publicado",
        fecha_creacion=_hace(120, hoy),
        fecha_actualizacion=_hace(120, hoy),
    )
    reciente = _pub(
        id="reciente",
        titulo="Nuevo sismo sacude la zona; protocolo de evacuación activado",
        contenido="el sismo de hoy reactiva el protocolo",
        estado="publicado",
        fecha_creacion=_hace(2, hoy),
        fecha_actualizacion=_hace(2, hoy),
    )
    out = reciclaje.candidatas_reciclaje([vieja, reciente], hoy=hoy)
    ids = [c["id"] for c in out]
    assert "vieja" in ids
    cand = next(c for c in out if c["id"] == "vieja")
    assert cand["motivo"] == reciclaje.MOTIVO_RECURRENTE
    # La reciente no es candidata por antiguedad (es nueva, no archivo).
    assert "reciente" not in ids


def test_tema_recurrente_distinta_marca_no_cruza():
    hoy = date(2026, 5, 25)
    vieja = _pub(
        id="vieja",
        marca="unotv",
        titulo="Sismo protocolo evacuación edificio",
        estado="publicado",
        fecha_creacion=_hace(120, hoy),
    )
    reciente = _pub(
        id="reciente",
        marca="piso-15",
        titulo="Sismo protocolo evacuación edificio",
        estado="publicado",
        fecha_creacion=_hace(2, hoy),
    )
    out = reciclaje.candidatas_reciclaje([vieja, reciente], hoy=hoy)
    assert all(c["motivo"] != reciclaje.MOTIVO_RECURRENTE for c in out)


# --------------------------------------------------------------------------- #
# Exclusion de copias y orden                                                  #
# --------------------------------------------------------------------------- #


def test_excluye_pieza_ya_reciclada():
    hoy = date(2026, 5, 5)
    original = _pub(id="orig", titulo="Día de las Madres", estado="publicado")
    copia = _pub(id="copia", titulo="Día de las Madres", estado="borrador", evergreen=True)
    out = reciclaje.candidatas_reciclaje([original, copia], hoy=hoy)
    assert out == []  # ya hay una copia pendiente con mismo titulo/marca/red


def test_efemeride_gana_a_perenne_en_la_misma_pieza_y_orden_global():
    hoy = date(2026, 5, 5)
    # Pieza A: efemeride proxima (debe encabezar).
    a = _pub(id="a", titulo="Día de las Madres especial", estado="publicado")
    # Pieza B: solo perenne madurada.
    b = _pub(
        id="b",
        titulo="Guía perenne",
        evergreen=True,
        estado="publicado",
        fecha_actualizacion=_hace(90, hoy),
        fecha_creacion=_hace(90, hoy),
    )
    out = reciclaje.candidatas_reciclaje([a, b], hoy=hoy)
    assert [c["id"] for c in out] == ["a", "b"]
    assert out[0]["motivo"] == reciclaje.MOTIVO_EFEMERIDE


def test_respeta_el_limite():
    hoy = date(2026, 5, 5)
    pubs = [
        _pub(id=f"p{i}", titulo=f"Día de las Madres nota {i}", estado="publicado")
        for i in range(20)
    ]
    out = reciclaje.candidatas_reciclaje(pubs, hoy=hoy, limite=5)
    assert len(out) == 5

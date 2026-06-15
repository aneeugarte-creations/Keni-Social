from __future__ import annotations

import pytest

from keni_metricas.fuentes.base import CuentaNoEncontrada
from keni_metricas.fuentes.muestra import FuenteMuestra


@pytest.fixture
def fuente() -> FuenteMuestra:
    return FuenteMuestra()


def test_cuentas_listadas(fuente: FuenteMuestra):
    cuentas = fuente.cuentas()
    ids = {c.id for c in cuentas}
    assert {"claro_sports", "unotv", "nacion_gamer", "fundacion"} <= ids
    # cuentas hermanas de Claro Sports que el equipo promociona aparte
    assert {"claro_sports_tv", "csport_golf"} <= ids
    assert len(cuentas) == 7


# --- #102: identidad UNICA de marca (guard de no-divergencia) ---------------
def test_ids_marca_muestra_anclados_al_catalogo_canonico(fuente: FuenteMuestra):
    """Las cuentas de la muestra son exactamente las 5 marcas editoriales (en su
    `id_metricas` guion_bajo) MAS las 2 cuentas hermanas de Claro Sports.

    Ancla los ids al catalogo UNICO de marca, que vive AHORA en `keni_shared.marcas`
    (H3/E1): `IDS_METRICAS_MARCAS` se DERIVA de ese catalogo (no es ya un espejo),
    asi que si alguien renombra o anade una marca en el `_MARCAS` de la muestra sin
    actualizar la fuente, este test lo caza.
    """
    from keni_shared import cuentas as ks_cuentas
    from keni_shared import marcas as ks_marcas

    from keni_metricas.fuentes.muestra import (
        IDS_CUENTAS_HERMANAS,
        IDS_METRICAS_MARCAS,
    )

    # La fuente es UNICA: los conjuntos de la muestra se derivan de keni_shared.
    assert IDS_METRICAS_MARCAS == {m.id_metricas for m in ks_marcas.MARCAS}
    assert IDS_CUENTAS_HERMANAS == set(ks_cuentas.CUENTAS_DEPORTES_HERMANAS)

    ids_cuentas = {c.id for c in fuente.cuentas()}
    # Toda cuenta de la muestra es marca editorial o cuenta hermana; nada mas.
    assert ids_cuentas == IDS_METRICAS_MARCAS | IDS_CUENTAS_HERMANAS
    # Marcas y cuentas hermanas son conjuntos disjuntos (el golf NO es marca).
    assert not (IDS_METRICAS_MARCAS & IDS_CUENTAS_HERMANAS)
    # Esquema guion_bajo en TODAS las claves (nunca el id canonico slug-guion).
    assert all("-" not in cid for cid in ids_cuentas)
    assert "claro-sports" not in ids_cuentas


def test_resumen_determinista(fuente: FuenteMuestra):
    a = fuente.resumen("claro_sports", "semana")
    b = fuente.resumen("claro_sports", "semana")
    assert a == b  # mismo input -> mismo output


def test_resumen_cifras_creibles(fuente: FuenteMuestra):
    r = fuente.resumen("claro_sports", "mes")
    # Claro Sports ~80M/mes; tolerancia amplia por el jitter
    assert 50_000_000 < r.visualizaciones < 110_000_000
    assert 1.0 <= r.engagement_pct <= 12.0
    assert r.fuente == "muestra"
    # las plataformas del resumen son exactamente las de la cuenta
    cuenta = next(c for c in fuente.cuentas() if c.id == "claro_sports")
    assert {m.plataforma for m in r.por_plataforma} == set(cuenta.plataformas)


def test_semana_menor_que_mes(fuente: FuenteMuestra):
    assert fuente.resumen("claro_sports", "semana").visualizaciones < fuente.resumen(
        "claro_sports", "mes"
    ).visualizaciones


def test_mejores_piezas_ordenadas(fuente: FuenteMuestra):
    piezas = fuente.mejores_piezas("claro_sports", "semana", 5)
    assert len(piezas) == 5
    eng = [p.engagement_pct for p in piezas]
    assert eng == sorted(eng, reverse=True)
    # cada pieza se sella con su marca (para estratificar top/peores por marca).
    assert all(p.cuenta == "claro_sports" for p in piezas)


def test_cuenta_desconocida(fuente: FuenteMuestra):
    with pytest.raises(CuentaNoEncontrada):
        fuente.resumen("no_existe", "semana")


def test_rango_invalido(fuente: FuenteMuestra):
    with pytest.raises(ValueError):
        fuente.resumen("claro_sports", "trimestre")


# --- B7: n negativo no debe devolver de mas --------------------------------
@pytest.mark.parametrize("n", [-1, -5, -100])
def test_mejores_piezas_n_negativo_devuelve_vacio(fuente: FuenteMuestra, n: int):
    # antes, candidatas[:n] con n<0 devolvia casi todas las candidatas (p.ej. 11)
    assert fuente.mejores_piezas("claro_sports", "mes", n) == []


def test_mejores_piezas_n_cero(fuente: FuenteMuestra):
    assert fuente.mejores_piezas("claro_sports", "mes", 0) == []


# --- T9: determinismo ------------------------------------------------------
def test_rand_determinista():
    from keni_metricas.fuentes.muestra import _rand

    assert _rand("claro_sports", "mes", "v") == _rand("claro_sports", "mes", "v")
    # inputs distintos -> (casi seguro) valores distintos
    assert _rand("claro_sports", "mes", "v") != _rand("unotv", "mes", "v")


def test_mejores_piezas_deterministas(fuente: FuenteMuestra):
    a = fuente.mejores_piezas("unotv", "mes", 5)
    b = fuente.mejores_piezas("unotv", "mes", 5)
    assert a == b  # mismo input -> mismas piezas (id, cifras, orden)


def test_resumen_cifras_estables_entre_invocaciones(fuente: FuenteMuestra):
    a = fuente.resumen("nacion_gamer", "semana")
    b = fuente.resumen("nacion_gamer", "semana")
    assert a.visualizaciones == b.visualizaciones
    assert a.engagement_pct == b.engagement_pct
    assert a.seguidores_netos == b.seguidores_netos


# --- T9: las mejores piezas baten la media de engagement de su plataforma ---
def test_mejores_piezas_baten_media_de_su_plataforma(fuente: FuenteMuestra):
    from keni_metricas.fuentes.muestra import _ENG, _ENG_FACTOR

    cuenta_id = "claro_sports"
    factor = _ENG_FACTOR[cuenta_id]
    piezas = fuente.mejores_piezas(cuenta_id, "mes", 12)
    assert piezas
    for p in piezas:
        eng_min, eng_max = _ENG[p.plataforma]
        media_plataforma = (eng_min + eng_max) / 2 * factor
        # cada pieza destacada bate (o iguala, con redondeo a 1 decimal) la media
        assert p.engagement_pct >= round(media_plataforma, 1) - 0.05


# --- T9: el factor de engagement por marca cae donde toca ------------------
def test_engagement_claro_sports_en_rango_esperado(fuente: FuenteMuestra):
    # Cifra de la coordinadora operativa: Claro Sports combinado ~2-3%.
    r = fuente.resumen("claro_sports", "mes")
    assert 1.8 <= r.engagement_pct <= 3.5


def test_engagement_unotv_mas_bajo_que_claro_sports(fuente: FuenteMuestra):
    # UnoTV (noticias) prioriza alcance: engagement combinado mas bajo.
    cs = fuente.resumen("claro_sports", "mes").engagement_pct
    uno = fuente.resumen("unotv", "mes").engagement_pct
    assert uno < cs


def test_serie_diaria_muestra_determinista():
    """La serie diaria de muestra cubre todos los días del periodo y es estable."""
    from keni_metricas.fuentes.muestra import FuenteMuestra

    f = FuenteMuestra()
    cuenta = f.cuentas()[0].id
    s1 = f.serie_diaria(cuenta, "semana")
    s2 = f.serie_diaria(cuenta, "semana")
    assert len(s1) == 7
    # determinista: dos llamadas dan el mismo resultado.
    assert [(p.fecha, p.visualizaciones, p.interacciones) for p in s1] == [
        (p.fecha, p.visualizaciones, p.interacciones) for p in s2
    ]
    assert all(p.visualizaciones >= 0 for p in s1)

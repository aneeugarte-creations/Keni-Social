"""Tests del score de prioridad dinamico (PURO, sin DB)."""

from __future__ import annotations

from datetime import date

from keni_consola import priorizacion as pr

HOY = date(2026, 5, 31)


def _item(**kw):
    base = {"id": "c1", "prioridad": "media", "flujo": "", "fecha_objetivo": "", "creado": ""}
    base.update(kw)
    return base


def test_compromiso_domina_sobre_prioridad():
    con = pr.score_contenido(_item(prioridad="baja"), etiquetas=["compromiso"], hoy=HOY)
    sin = pr.score_contenido(_item(prioridad="alta"), etiquetas=[], hoy=HOY)
    assert con > sin


def test_evergreen_suma_bonus_pero_por_debajo_de_compromiso():
    base = pr.score_contenido(_item(), etiquetas=[], hoy=HOY)
    evergreen = pr.score_contenido(_item(), etiquetas=["evergreen"], hoy=HOY)
    compromiso = pr.score_contenido(_item(), etiquetas=["compromiso"], hoy=HOY)
    assert base < evergreen < compromiso


def test_evergreen_acumula_con_compromiso():
    ambos = pr.score_contenido(_item(), etiquetas=["evergreen", "compromiso"], hoy=HOY)
    solo = pr.score_contenido(_item(), etiquetas=["compromiso"], hoy=HOY)
    assert ambos == solo + pr.BONUS_EVERGREEN


def test_prioridad_ordena_cuando_resto_igual():
    alta = pr.score_contenido(_item(prioridad="alta"), hoy=HOY)
    media = pr.score_contenido(_item(prioridad="media"), hoy=HOY)
    baja = pr.score_contenido(_item(prioridad="baja"), hoy=HOY)
    assert alta > media > baja


def test_fecha_vencida_pesa_mas_que_hoy_y_que_futura():
    vencida = pr.peso_fecha("2026-05-30", HOY)
    hoy = pr.peso_fecha("2026-05-31", HOY)
    pronto = pr.peso_fecha("2026-06-02", HOY)
    lejana = pr.peso_fecha("2026-09-01", HOY)
    assert vencida > hoy > pronto > lejana


def test_fecha_invalida_o_vacia_no_suma():
    assert pr.peso_fecha("", HOY) == 0
    assert pr.peso_fecha("no-fecha", HOY) == 0


def test_fecha_con_hora_se_tolera():
    assert pr.peso_fecha("2026-05-31T09:00", HOY) == pr.peso_fecha("2026-05-31", HOY)


def test_frescura_decae_con_los_dias():
    hoy = pr.peso_frescura("2026-05-31", HOY)
    ayer = pr.peso_frescura("2026-05-30", HOY)
    viejo = pr.peso_frescura("2026-04-01", HOY)
    assert hoy > ayer > viejo == 0


def test_flujo_importante_suma_mas_que_evergreen():
    imp = pr.score_contenido(_item(flujo="importante"), hoy=HOY)
    ever = pr.score_contenido(_item(flujo="evergreen"), hoy=HOY)
    assert imp > ever


def test_ordenar_por_score_es_estable_en_empates():
    items = [_item(id="a"), _item(id="b"), _item(id="c")]  # mismo score
    ordenados = pr.ordenar_por_score(items, hoy=HOY)
    assert [i["id"] for i in ordenados] == ["a", "b", "c"]


def test_ordenar_pone_compromiso_con_fecha_arriba():
    items = [
        _item(id="evergreen", flujo="evergreen", prioridad="baja"),
        _item(id="compromiso_hoy", prioridad="media", fecha_objetivo="2026-05-31"),
        _item(id="alta_sin_fecha", prioridad="alta"),
    ]
    etiquetas = {"compromiso_hoy": ["compromiso"]}
    ordenados = pr.ordenar_por_score(items, etiquetas_por_item=etiquetas, hoy=HOY)
    assert ordenados[0]["id"] == "compromiso_hoy"
    assert ordenados[-1]["id"] == "evergreen"


def test_ordenar_no_muta_la_entrada():
    items = [_item(id="a", prioridad="baja"), _item(id="b", prioridad="alta")]
    pr.ordenar_por_score(items, hoy=HOY)
    assert [i["id"] for i in items] == ["a", "b"]


# --------------------------------------------------------------------------- #
# Fase 5: señal de VIRALIDAD del Radar (persistida en `senal_viralidad`)        #
# --------------------------------------------------------------------------- #


def test_sin_senal_de_viralidad_puntua_como_antes():
    """Una pieza sin señal (ausente o 0) NO cambia su score (degradacion elegante)."""
    sin_clave = pr.score_contenido(_item(), hoy=HOY)
    con_cero = pr.score_contenido(_item(senal_viralidad=0), hoy=HOY)
    base_esperada = (
        pr.PESO_PRIORIDAD["media"]  # prioridad media
    )
    assert sin_clave == con_cero == base_esperada


def test_viralidad_sube_el_score_por_intervalos():
    """Mayor señal -> mayor bonus, por intervalos acotados (no lineal)."""
    bajo = pr.score_contenido(_item(senal_viralidad=2_000), hoy=HOY)
    medio = pr.score_contenido(_item(senal_viralidad=60_000), hoy=HOY)
    alto = pr.score_contenido(_item(senal_viralidad=1_000_000), hoy=HOY)
    base = pr.score_contenido(_item(), hoy=HOY)
    assert base < bajo < medio < alto
    assert alto - base == pr.BONUS_VIRALIDAD_MAX


def test_viralidad_no_supera_al_compromiso():
    """Un trending fuerte sube, pero el must-do humano sigue por encima."""
    viral = pr.score_contenido(_item(senal_viralidad=10_000_000), hoy=HOY)
    compromiso = pr.score_contenido(_item(), etiquetas=["compromiso"], hoy=HOY)
    assert compromiso > viral


def test_peso_viralidad_invalido_o_negativo_es_cero():
    assert pr.peso_viralidad(None) == 0
    assert pr.peso_viralidad("no-numero") == 0
    assert pr.peso_viralidad(-5) == 0
    assert pr.peso_viralidad(0) == 0
    assert pr.peso_viralidad("50000") == pr.peso_viralidad(50_000)  # str numerico se tolera


# --------------------------------------------------------------------------- #
# peso_fecha: lo vencido DECAE (no se queda clavado arriba para siempre)        #
# --------------------------------------------------------------------------- #


def test_vencido_reciente_es_lo_mas_urgente():
    assert pr.peso_fecha("2026-05-30", HOY) == 150          # vencida ayer
    assert pr.peso_fecha("2026-05-24", HOY) == 150          # vencida hace 7 dias (pleno)


def test_vencido_viejo_decae_por_intervalos():
    pleno = pr.peso_fecha("2026-05-30", HOY)                 # atraso 1 dia
    dos_semanas = pr.peso_fecha("2026-05-20", HOY)           # atraso 11 dias
    un_mes = pr.peso_fecha("2026-05-05", HOY)                # atraso 26 dias
    viejisimo = pr.peso_fecha("2026-03-01", HOY)             # atraso ~3 meses
    assert pleno > dos_semanas > un_mes > viejisimo
    # Vencido hace mas de un mes pesa como lo lejano: ya no urge.
    assert viejisimo == pr.peso_fecha("2026-09-01", HOY)


def test_vencido_muy_viejo_no_supera_a_hoy():
    hoy_peso = pr.peso_fecha(HOY.isoformat(), HOY)
    assert pr.peso_fecha("2026-03-01", HOY) < hoy_peso

"""Tests de la lógica pura de frescura.

Cubre `estado_frescura` con todos los casos relevantes: evergreen, fechas vacías,
fechas malformadas, días dentro del TTL, días fuera del TTL (con y sin margen), y
el comportamiento de evergreen sobre TTL>0.

No requiere BD (módulo puro).
"""

from __future__ import annotations

from keni_consola.produccion.frescura import estado_frescura

# --------------------------------------------------------------------------- #
# Parámetros de la función bajo prueba                                         #
# --------------------------------------------------------------------------- #
# estado_frescura(fecha_item, ttl_dias, es_evergreen, *, hoy) -> "fresco" | "caduco"


class TestEverevergreenYSinTTL:
    """Líneas evergreen o sin TTL → siempre 'fresco'."""

    def test_es_evergreen_true_ignora_fecha_y_ttl(self):
        # Con es_evergreen=True, aunque ttl_dias=1 y el ítem sea de ayer, es fresco
        assert estado_frescura("2026-01-01", ttl_dias=1, es_evergreen=True, hoy="2026-06-05") == "fresco"

    def test_ttl_cero_siempre_fresco(self):
        # ttl_dias=0 = sin caducidad
        assert estado_frescura("2020-01-01", ttl_dias=0, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_ttl_negativo_siempre_fresco(self):
        # ttl_dias<0 también = evergreen (por robustez)
        assert estado_frescura("2020-01-01", ttl_dias=-5, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_es_evergreen_y_ttl_cero_fresco(self):
        assert estado_frescura("2000-01-01", ttl_dias=0, es_evergreen=True, hoy="2026-06-05") == "fresco"


class TestFechasInvalidas:
    """Fechas vacías o malformadas → 'fresco' (nunca ocultar por dato malo)."""

    def test_fecha_item_vacia_es_fresco(self):
        assert estado_frescura("", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_fecha_item_none_str_es_fresco(self):
        assert estado_frescura("None", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_fecha_item_garbage_es_fresco(self):
        assert estado_frescura("not-a-date", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_fecha_item_parcial_es_fresco(self):
        assert estado_frescura("2026-06", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_hoy_invalido_es_fresco(self):
        # hoy malformado → fresco por seguridad
        assert estado_frescura("2026-06-04", ttl_dias=1, es_evergreen=False, hoy="bad") == "fresco"

    def test_fecha_item_espacios_extra(self):
        # Trim debe funcionar
        assert estado_frescura("  2026-06-05  ", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"


class TestTTL1Dia:
    """TTL = 1 día: fresco hoy (mismo día), fresco ayer, caduco antes de ayer."""

    def test_item_de_hoy_es_fresco(self):
        assert estado_frescura("2026-06-05", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_item_de_ayer_es_fresco(self):
        # hoy - fecha = 1 día <= ttl_dias=1 → fresco
        assert estado_frescura("2026-06-04", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_item_de_anteayer_es_caduco(self):
        # hoy - fecha = 2 días > ttl_dias=1 → caduco
        assert estado_frescura("2026-06-03", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "caduco"

    def test_item_de_semana_pasada_es_caduco(self):
        assert estado_frescura("2026-05-29", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "caduco"


class TestTTL2Dias:
    """TTL = 2 días (Virales): fresco si la diferencia <= 2."""

    def test_hoy_mismo_dia_fresco(self):
        assert estado_frescura("2026-06-05", ttl_dias=2, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_un_dia_antes_fresco(self):
        assert estado_frescura("2026-06-04", ttl_dias=2, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_dos_dias_antes_fresco(self):
        # diferencia exacta = ttl_dias → fresco (<=)
        assert estado_frescura("2026-06-03", ttl_dias=2, es_evergreen=False, hoy="2026-06-05") == "fresco"

    def test_tres_dias_antes_caduco(self):
        assert estado_frescura("2026-06-02", ttl_dias=2, es_evergreen=False, hoy="2026-06-05") == "caduco"


class TestItemFuturo:
    """Ítem con fecha futura siempre es fresco (diferencia negativa)."""

    def test_item_del_futuro_es_fresco(self):
        assert estado_frescura("2026-12-31", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "fresco"


class TestEvergreenSobrewritesTTL:
    """es_evergreen=True siempre gana sobre ttl_dias > 0."""

    def test_evergreen_true_con_ttl_1_item_viejo_fresco(self):
        assert estado_frescura("2025-01-01", ttl_dias=1, es_evergreen=True, hoy="2026-06-05") == "fresco"

    def test_evergreen_false_con_ttl_1_item_viejo_caduco(self):
        assert estado_frescura("2025-01-01", ttl_dias=1, es_evergreen=False, hoy="2026-06-05") == "caduco"

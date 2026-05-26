"""Tests de las cuentas hermanas (`cuentas`) — H3/E1.

Las hermanas de Claro Sports NO son marcas del catalogo: este test ancla esa
invariante contra `keni_shared.marcas` (misma fuente, sin espejos).
"""

from __future__ import annotations

from keni_shared import cuentas, marcas


def test_cuenta_principal_coincide_con_el_catalogo():
    assert cuentas.CUENTA_DEPORTES_PRINCIPAL == marcas.id_metricas_de("claro-sports")


def test_hermanas_no_son_marcas_del_catalogo():
    canonicos = {m.id_metricas for m in marcas.MARCAS}
    assert not (set(cuentas.CUENTAS_DEPORTES_HERMANAS) & canonicos)


def test_hermanas_son_las_esperadas():
    assert cuentas.CUENTAS_DEPORTES_HERMANAS == ("claro_sports_tv", "csport_golf")

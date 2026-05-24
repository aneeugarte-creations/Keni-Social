from __future__ import annotations

from datetime import date

import pytest

from keni_metricas.fuentes.tiktok import AdaptadorTikTok
from keni_metricas.fuentes.x import AdaptadorX
from keni_metricas.fuentes.youtube import AdaptadorYouTube

DESDE = date(2026, 5, 16)
HASTA = date(2026, 5, 22)


@pytest.mark.parametrize(
    "adaptador",
    [AdaptadorYouTube({}), AdaptadorX({}), AdaptadorTikTok({})],
)
def test_sin_credenciales_degrada(adaptador):
    assert not adaptador.disponible()
    assert adaptador.metricas("h", DESDE, HASTA) is None
    assert adaptador.piezas("h", DESDE, HASTA, 3) == []


def test_disponible_con_credenciales():
    assert AdaptadorYouTube({"access_token": "x"}).disponible()
    assert AdaptadorX({"bearer_token": "x"}).disponible()
    assert AdaptadorTikTok({"access_token": "x"}).disponible()

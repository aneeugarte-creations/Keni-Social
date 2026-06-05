"""Tests de la lógica de migración a carpetas (`keni_consola.migrar_carpetas`).

OFFLINE y SIN Postgres: ejercitan los helpers de planificación (`_migrable`, `_Plan`,
`_migrar_fotos_array`) sobre el backend de DISCO. La migración completa (`migrar()`) recorre
`repos` (Postgres) y la valida el CI con la suite operacional.
"""

from __future__ import annotations

import json

import pytest

from keni_consola import almacen_media, migrar_carpetas


@pytest.fixture
def disco(monkeypatch, tmp_path):
    """Backend DISCO aislado en tmp (borra cualquier S3_*)."""
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    almacen_media._resetear_cliente_s3()
    return tmp_path


def _poner(clave: str, datos: bytes = b"x") -> None:
    almacen_media.guardar_objeto(clave, datos, content_type="image/png")


def test_migrable_solo_planos_existentes(disco):
    _poner("abc.png")
    assert migrar_carpetas._migrable("abc.png") is True
    assert migrar_carpetas._migrable("noexiste.png") is False     # no existe
    assert migrar_carpetas._migrable("fotos/abc.png") is False    # ya en carpeta
    assert migrar_carpetas._migrable("") is False
    assert migrar_carpetas._migrable(None) is False
    assert migrar_carpetas._migrable("https://x/y.png") is False  # URL externa


def test_migrar_ref_aplicar_copia_y_repunta(disco):
    _poner("deadbeef.png", b"pix")
    plan = migrar_carpetas._Plan(aplicar=True)
    nueva = plan.migrar_ref("deadbeef.png", "fotos")
    assert nueva == "fotos/deadbeef.png"
    assert almacen_media.leer_objeto("fotos/deadbeef.png") == b"pix"
    # COPIA: el plano original sigue ahí (se purga aparte).
    assert almacen_media.leer_objeto("deadbeef.png") == b"pix"
    assert plan.cuentas["fotos"] == 1


def test_migrar_ref_dry_run_no_muta(disco):
    _poner("cafe.png")
    plan = migrar_carpetas._Plan(aplicar=False)
    nueva = plan.migrar_ref("cafe.png", "logos")
    assert nueva == "logos/cafe.png"           # planifica el destino
    assert almacen_media.objeto_existe("logos/cafe.png") is False  # pero NO copia
    assert plan.cuentas["logos"] == 1


def test_migrar_ref_ya_en_carpeta_es_none(disco):
    _poner("logos/x.png")
    plan = migrar_carpetas._Plan(aplicar=True)
    assert plan.migrar_ref("logos/x.png", "logos") is None
    assert not plan.cuentas


def test_referencia_plana_viva_no_se_purga(disco):
    """Una key plana que NO se migra (p.ej. inexistente como objeto) se anota como viva."""
    plan = migrar_carpetas._Plan(aplicar=True)
    assert plan.migrar_ref("huerfana.png", "fotos") is None
    assert "huerfana.png" in plan.referenciados_planos


def test_migrar_fotos_array(disco):
    _poner("uno.png")
    _poner("dos.png")
    plan = migrar_carpetas._Plan(aplicar=True)
    entrada = json.dumps(
        [
            {"objeto": "uno.png", "foco": [0.5, 0.5], "zoom": 1},
            {"objeto": "dos.png"},
            {"objeto": "fotos/ya.png"},  # ya en carpeta: intacta
        ]
    )
    salida, cambio = migrar_carpetas._migrar_fotos_array(plan, entrada)
    assert cambio is True
    assert salida[0]["objeto"] == "fotos/uno.png"
    assert salida[0]["foco"] == [0.5, 0.5]  # conserva el resto del item
    assert salida[1]["objeto"] == "fotos/dos.png"
    assert salida[2]["objeto"] == "fotos/ya.png"


def test_purgar_planos_borra_no_referenciados(disco):
    _poner("migrada.png", b"a")        # se migrará y luego se podrá purgar
    _poner("viva-plana.png", b"b")     # algo sin migrar la sigue usando -> NO se purga
    plan = migrar_carpetas._Plan(aplicar=True)
    plan.migrar_ref("migrada.png", "fotos")  # copia a fotos/migrada.png
    # 'viva-plana.png' la mantiene viva una referencia que NO migramos (media embebido en un
    # documento de capas): el plan la habría anotado como viva. Lo simulamos directamente.
    plan.referenciados_planos.add("viva-plana.png")
    plan.purgar_planos()
    assert almacen_media.objeto_existe("migrada.png") is False       # plano migrado -> purgado
    assert almacen_media.objeto_existe("fotos/migrada.png") is True  # la copia en carpeta queda
    assert almacen_media.objeto_existe("viva-plana.png") is True     # protegida (referenciada)

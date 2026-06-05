"""Tests de la PODA de retencion de registros de generacion (`podar_generaciones`).

Las generaciones viven en ficheros YAML (no Postgres), así que estos tests aíslan el almacén
en `tmp_path` vía `KENI_CONSOLA_GENERACIONES` y NO necesitan base de datos. La poda juzga la
edad por el MTIME del fichero (barato, sin parsear el YAML), así que los tests fijan el mtime
con `os.utime` en vez de depender del reloj o del campo `fecha_inicio` del YAML.

Cubre:
  - conserva los registros recientes (dentro de la ventana de días);
  - conserva SIEMPRE los `maximo` más recientes aunque sean viejos (piso de los N);
  - borra los viejos que caen FUERA del piso;
  - es idempotente (un segundo barrido no borra nada nuevo);
  - tolera ficheros ajenos / temporales / corruptos sin romper ni borrarlos;
  - almacén vacío o por debajo del piso: no hace nada.
"""

from __future__ import annotations

import os
import time

import pytest

from keni_consola import generaciones


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    """Aísla el almacén de generaciones en `tmp_path` y devuelve su raíz (ya creada)."""
    raiz = tmp_path / "generaciones"
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(raiz))
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def _crear(raiz, *, edad_dias: float, sufijo: str = "") -> str:
    """Crea un registro de generación con MTIME `edad_dias` en el pasado. Devuelve su id."""
    gen = generaciones.crear({"tipo": "copy", "marca": "", "etiqueta": "x"})
    ruta = raiz / f"{gen['id']}.yaml"
    cuando = time.time() - edad_dias * 86400.0
    os.utime(ruta, (cuando, cuando))
    return gen["id"]


def test_conserva_recientes(almacen):
    """Registros dentro de la ventana de días no se tocan, aunque haya muchos."""
    ids = [_crear(almacen, edad_dias=1) for _ in range(5)]
    podados = generaciones.podar_generaciones(dias=30, maximo=2)
    assert podados == 0
    for gen_id in ids:
        assert generaciones.obtener(gen_id) is not None


def test_borra_viejos_fuera_del_piso(almacen):
    """Los viejos (fuera de días) que caen por debajo del piso de los N más recientes se borran."""
    viejos = [_crear(almacen, edad_dias=60) for _ in range(4)]
    nuevos = [_crear(almacen, edad_dias=1) for _ in range(2)]
    # piso=2 -> conserva los 2 más recientes (los nuevos); los 4 viejos están fuera del piso
    # y fuera de la ventana de días -> se borran.
    podados = generaciones.podar_generaciones(dias=30, maximo=2)
    assert podados == 4
    for gen_id in viejos:
        assert generaciones.obtener(gen_id) is None
    for gen_id in nuevos:
        assert generaciones.obtener(gen_id) is not None


def test_piso_protege_viejos(almacen):
    """El piso de los N más recientes NUNCA se borra, aunque todos sean viejos."""
    # 5 registros, todos viejos (90 d), mtime escalonado para un orden determinista.
    ids = []
    for i in range(5):
        gen_id = _crear(almacen, edad_dias=90 + i)  # más antiguo cuanto mayor i
        ids.append(gen_id)
    # piso=3 -> conserva los 3 más recientes (i=0,1,2) aunque viejos; borra los 2 más antiguos.
    podados = generaciones.podar_generaciones(dias=30, maximo=3)
    assert podados == 2
    vivos = [g for g in ids if generaciones.obtener(g) is not None]
    assert len(vivos) == 3
    # Los conservados son los de mtime más reciente (i=0,1,2).
    assert set(vivos) == set(ids[:3])


def test_idempotente(almacen):
    """Un segundo barrido inmediato no borra nada nuevo."""
    [_crear(almacen, edad_dias=60) for _ in range(4)]
    [_crear(almacen, edad_dias=1) for _ in range(2)]
    primero = generaciones.podar_generaciones(dias=30, maximo=2)
    assert primero == 4
    segundo = generaciones.podar_generaciones(dias=30, maximo=2)
    assert segundo == 0


def test_por_debajo_del_piso_no_poda(almacen):
    """Con menos registros que el piso no se borra nada, aunque sean viejos."""
    _crear(almacen, edad_dias=90)
    _crear(almacen, edad_dias=90)
    assert generaciones.podar_generaciones(dias=30, maximo=2000) == 0


def test_almacen_vacio_no_rompe(almacen):
    assert generaciones.podar_generaciones(dias=30, maximo=2000) == 0


def test_ignora_ficheros_ajenos_y_temporales(almacen):
    """Solo borra registros `<12hex>.yaml`; nada de temporales ni ficheros ajenos viejos."""
    # Registro de generación viejo (candidato a borrar).
    gen_id = _crear(almacen, edad_dias=90)
    # Ficheros que NO son registros de generación, también viejos: no deben tocarse.
    ajenos = [
        almacen / ".tmp-abc123.yaml",
        almacen / "no-es-un-id.yaml",
        almacen / "deadbeef.yaml",  # 8 hex, no 12: no es un id válido
        almacen / "notas.txt",
    ]
    viejo = time.time() - 90 * 86400.0
    for f in ajenos:
        f.write_text("x: 1\n", encoding="utf-8")
        os.utime(f, (viejo, viejo))
    podados = generaciones.podar_generaciones(dias=30, maximo=0)
    assert podados == 1  # solo el registro de generación real
    assert generaciones.obtener(gen_id) is None
    for f in ajenos:
        assert f.exists(), f"no debió tocar {f.name}"


def test_no_parsea_yaml_corrupto(almacen):
    """Un registro con id válido pero YAML corrupto se PODA por mtime sin intentar parsearlo."""
    ruta = almacen / ("a" * 12 + ".yaml")
    ruta.write_text(": : : no es yaml válido : :\n", encoding="utf-8")
    viejo = time.time() - 90 * 86400.0
    os.utime(ruta, (viejo, viejo))
    podados = generaciones.podar_generaciones(dias=30, maximo=0)
    assert podados == 1
    assert not ruta.exists()


def test_lee_knobs_del_entorno(almacen, monkeypatch):
    """Sin args explícitos, lee días/máximo de las env vars (defaults INLINE)."""
    [_crear(almacen, edad_dias=10) for _ in range(3)]  # 10 d de antigüedad
    # Ventana de 5 días -> los de 10 d están fuera; piso 1 -> conserva 1, borra 2.
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_DIAS", "5")
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_MAX", "1")
    assert generaciones.podar_generaciones() == 2


def test_env_invalido_cae_al_default(almacen, monkeypatch):
    """Una env var no numérica no rompe: cae al default (30 d / 2000)."""
    [_crear(almacen, edad_dias=1) for _ in range(3)]
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_DIAS", "no-numero")
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_MAX", "")
    # Con defaults (30 d / 2000) y registros de 1 d: no se borra nada.
    assert generaciones.podar_generaciones() == 0

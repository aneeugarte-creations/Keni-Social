"""Daemon de re-derivación de patrones: gate OFF por defecto (leído EN VIVO por
`bucle_gateado`), frescura sin estado extra y aplicación best-effort. PURO (extracción
de Metricool monkeypatcheada, sin red/DB)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from keni_shared import marcas as cat_marcas

from keni_consola import config, patrones_marca, patrones_refresco


def test_gate_apagado_por_defecto_y_en_vivo(monkeypatch):
    """El gate ya no se lee una vez al arrancar: `iniciar_refresco_patrones` monta un
    `bucle_gateado` con `config.patrones_auto_activo` como `activo_fn`, así que basta con
    cubrir el accesor: OFF por defecto, y el env aplica en caliente (cada ciclo lo relee)."""
    monkeypatch.delenv("KENI_PATRONES_AUTO", raising=False)
    assert config.patrones_auto_activo() is False
    monkeypatch.setenv("KENI_PATRONES_AUTO", "1")
    assert config.patrones_auto_activo() is True


def _runtime_fresco(tmp_path, monkeypatch, *, hace_dias: float) -> None:
    """Escribe un perfil runtime para TODAS las marcas del catálogo con esa edad."""
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path))
    generado = (datetime.now(timezone.utc) - timedelta(days=hace_dias)).isoformat(
        timespec="seconds"
    )
    for marca, _ in cat_marcas.opciones():
        (tmp_path / f"{marca}.json").write_text(
            json.dumps({"version": 1, "marca": marca, "generado": generado, "redes": {}}),
            encoding="utf-8",
        )


def test_refrescar_no_toca_si_los_perfiles_son_frescos(tmp_path, monkeypatch):
    _runtime_fresco(tmp_path, monkeypatch, hace_dias=2)

    def _no_debe_llamarse(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("con perfiles frescos NO se extrae de Metricool")

    from keni_consola import patrones_derivar

    monkeypatch.setattr(patrones_derivar, "extraer_piezas_metricool", _no_debe_llamarse)
    assert patrones_refresco.refrescar_patrones() == 0


def test_refrescar_deriva_si_el_perfil_esta_viejo(tmp_path, monkeypatch):
    _runtime_fresco(tmp_path, monkeypatch, hace_dias=45)  # > 30 días por defecto
    piezas = [
        {"red": "facebook", "texto": f"Pieza con texto suficiente {i}.",
         "engagement_pct": i / 10.0, "visualizaciones": 1000, "publicado": "2026-05-01"}
        for i in range(120)
    ]
    from keni_consola import patrones_derivar

    monkeypatch.setattr(
        patrones_derivar, "extraer_piezas_metricool",
        lambda ids, meses: {"unotv": piezas},
    )
    assert patrones_refresco.refrescar_patrones() == 1
    # El runtime quedó actualizado (generado reciente) y el doc del store existe.
    datos = json.loads((tmp_path / "unotv.json").read_text(encoding="utf-8"))
    assert datos["redes"]["facebook"]["muestras"] == 120
    from keni_consola import libtexto

    assert libtexto.obtener("editorial/rrss/unotv/patrones") is not None


def test_refrescar_sin_runtime_deriva(tmp_path, monkeypatch):
    # Primer arranque con el daemon activo: sin perfiles runtime, toca derivar.
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path))
    from keni_consola import patrones_derivar

    llamado = {}

    def _extraer(ids, meses):  # noqa: ANN001
        llamado["si"] = True
        return {}

    monkeypatch.setattr(patrones_derivar, "extraer_piezas_metricool", _extraer)
    assert patrones_refresco.refrescar_patrones() == 0  # sin piezas no aplica nada
    assert llamado.get("si") is True


def test_extraccion_vacia_conserva_el_perfil_anterior(tmp_path, monkeypatch):
    _runtime_fresco(tmp_path, monkeypatch, hace_dias=45)
    antes = (tmp_path / "unotv.json").read_text(encoding="utf-8")
    from keni_consola import patrones_derivar

    monkeypatch.setattr(
        patrones_derivar, "extraer_piezas_metricool", lambda ids, meses: {}
    )
    assert patrones_refresco.refrescar_patrones() == 0
    assert (tmp_path / "unotv.json").read_text(encoding="utf-8") == antes


def test_edad_dias_robusta():
    ahora = datetime.now(timezone.utc)
    assert patrones_refresco._edad_dias("", ahora) is None
    assert patrones_refresco._edad_dias("no-es-fecha", ahora) is None
    casi_cero = patrones_refresco._edad_dias(ahora.isoformat(), ahora)
    assert casi_cero is not None and casi_cero < 0.01
    # Naive ISO (sin tz): se asume UTC, no lanza.
    naive = (ahora - timedelta(days=3)).replace(tzinfo=None).isoformat()
    edad = patrones_refresco._edad_dias(naive, ahora)
    assert edad is not None and 2.9 < edad < 3.1


def test_cargar_perfil_ignora_version_desconocida(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path))
    (tmp_path / "fundacion.json").write_text(
        json.dumps({"version": 99, "marca": "fundacion", "redes": {}}), encoding="utf-8"
    )
    # Versión mayor a la conocida y sin inicial del paquete (fundación no tiene datos
    # en Metricool): None (no se inventa).
    assert patrones_marca.cargar_perfil("fundacion") is None

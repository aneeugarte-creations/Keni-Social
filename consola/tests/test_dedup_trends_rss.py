"""Tests del dedup Trends↔RSS a nivel pool (`repos.claves_existentes_directas`).

Google Trends vuelca noticias con `fuente_id="google-trends"` (fijo): la MISMA nota que ya
entró por el feed RSS de su medio tiene la misma `clave` (url canónica) pero distinto
`fuente_id`, así que burla el UNIQUE `(fuente_id, clave)` y se duplicaría. Este helper deja que
el daemon de Trends descarte lo que YA está en el pool desde un feed DIRECTO. Usa la fixture
`entorno` (Postgres de pruebas; se salta si no hay).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from keni_consola import repos

_VIEJO = "2020-01-01T00:00:00+00:00"


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def test_encuentra_solo_las_claves_de_feeds_directos(entorno):
    """Una clave ya presente por un feed DIRECTO se detecta; la que solo está por Trends, no
    (excluir_fuente); la que no está, tampoco."""
    repos.crear_noticias_items([
        {"fuente_id": "feed-excelsior", "fuente_nombre": "Excélsior", "categoria": "mx",
         "titulo": "Nota directa", "url": "https://excelsior.com.mx/n1",
         "url_canonica": "excelsior.com.mx/n1", "clave": "excelsior.com.mx/n1",
         "capturado_en": _ahora()},
        {"fuente_id": "google-trends", "fuente_nombre": "Milenio", "categoria": "tendencias",
         "titulo": "Solo en trends", "url": "https://milenio.com/n2",
         "url_canonica": "milenio.com/n2", "clave": "milenio.com/n2", "capturado_en": _ahora()},
    ])

    presentes = repos.claves_existentes_directas(
        ["excelsior.com.mx/n1", "milenio.com/n2", "nueva.com/n3"],
        excluir_fuente="google-trends",
    )
    # Solo la que está por un feed directo (no Trends, no inexistente).
    assert presentes == {"excelsior.com.mx/n1"}


def test_respeta_la_ventana_desde(entorno):
    """Fuera de la ventana `desde` no cuenta como 'ya presente' (una resurgencia tardía es nueva)."""
    repos.crear_noticias_items([
        {"fuente_id": "feed-x", "fuente_nombre": "X", "categoria": "mx", "titulo": "Viejo",
         "url": "https://x.com/viejo", "url_canonica": "x.com/viejo", "clave": "x.com/viejo",
         "capturado_en": _VIEJO},
    ])
    desde = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
    assert repos.claves_existentes_directas(["x.com/viejo"], desde=desde) == set()
    # Sin ventana sí la encuentra (la fila existe).
    assert repos.claves_existentes_directas(["x.com/viejo"]) == {"x.com/viejo"}


def test_sin_candidatas_devuelve_vacio(entorno):
    assert repos.claves_existentes_directas([]) == set()
    assert repos.claves_existentes_directas(["", "  "]) == set()

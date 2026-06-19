"""Tests de las indicaciones del equipo (cajón `contexto`) inyectadas en el copy.

El cajón `contexto` de los Insumos recibe los lineamientos de Coordinación Marketing /
Temas Editoriales. `dominio.indicaciones` los lee (VIGENTES: últimos 7 días, marca de la
pieza o sin marca, tipo "contexto") y `generar.componer_copy` (punto ÚNICO de composición
del copy) los inyecta como bloque OBLIGATORIO en el prompt de TODOS los copys de la marca.

- `bloque_indicaciones` es PURO (lista de ítems entra, bloque sale): sin BD.
- `indicaciones_vigentes` y la integración con `componer_copy` usan el Postgres de pruebas
  (fixture `entorno`, mismo patrón que test_api_insumos).
- Sin ítems vigentes (o sin BD) el prompt NO cambia ni un byte (best-effort).
"""

from __future__ import annotations

from datetime import date, timedelta

from keni_consola.dominio import generar, indicaciones
from keni_consola.tiempo import hoy_utc

# --------------------------------------------------------------------------- #
# bloque_indicaciones (PURO: lista de ítems entra, bloque de texto sale)       #
# --------------------------------------------------------------------------- #


def test_bloque_sin_items_es_cadena_vacia():
    assert indicaciones.bloque_indicaciones([]) == ""
    # Ítems sin título útil tampoco generan bloque (no hay nada que indicar).
    assert indicaciones.bloque_indicaciones([{"titulo": "  ", "resumen": "x"}]) == ""


def test_bloque_con_items_compone_encabezado_lineas_y_fechas():
    items = [
        {
            "titulo": "Hoy prioridad al Mundial",
            "resumen": "Coordinación Marketing",
            "fecha": "2026-06-11",
        },
        {"titulo": "No usar el término 'Tri'", "resumen": "", "fecha": "2026-06-09"},
    ]
    bloque = indicaciones.bloque_indicaciones(items)
    assert bloque.startswith(indicaciones.ENCABEZADO_INDICACIONES)
    assert "OBLIGATORIAS" in bloque
    # Una línea por ítem, fechada DD/MM, con el resumen cuando lo hay.
    assert "- Hoy prioridad al Mundial — Coordinación Marketing (11/06)" in bloque
    assert "- No usar el término 'Tri' (09/06)" in bloque
    # Respeta el orden de entrada (vigentes ya llegan más recientes primero).
    assert bloque.index("Mundial") < bloque.index("Tri")


def test_bloque_tolera_fecha_invalida_sin_romper():
    bloque = indicaciones.bloque_indicaciones([{"titulo": "Revisar marcador", "fecha": "???"}])
    assert "- Revisar marcador" in bloque
    assert "(" not in bloque.splitlines()[-1]  # sin sufijo de fecha si no parsea


# --------------------------------------------------------------------------- #
# indicaciones_vigentes (filtro: cajón contexto + marca + ventana de 7 días)   #
# --------------------------------------------------------------------------- #


def _inicializar_contexto(repos, items: list[dict]) -> None:
    """Siembra ítems en un lote del cajón `contexto` (defaults de indicación)."""
    lote = repos.crear_insumo_lote(fecha=items[0]["fecha"], cajon="contexto", estado="listo")
    repos.crear_insumo_items([
        {"lote_id": lote["id"], "cajon": "contexto", "tipo": "contexto", **it} for it in items
    ])


def test_vigentes_filtra_marca_ventana_y_tipo(entorno):
    from keni_consola import repos

    hoy = date(2026, 6, 11)
    _inicializar_contexto(repos, [
        {"fecha": "2026-06-11", "marca": "claro-sports", "titulo": "Prioridad al Mundial"},
        {"fecha": "2026-06-10", "marca": "", "titulo": "Sin marca aplica a todas"},
        {"fecha": "2026-06-04", "marca": "claro-sports", "titulo": "Justo en el borde (7 días)"},
        {"fecha": "2026-06-03", "marca": "claro-sports", "titulo": "Caducada (8 días)"},
        {"fecha": "2026-06-11", "marca": "unotv", "titulo": "De otra marca"},
        # Re-tipado a nota dentro del cajón: dejó de ser indicación.
        {"fecha": "2026-06-11", "marca": "claro-sports", "titulo": "Nota suelta", "tipo": "nota"},
        {"fecha": "", "marca": "claro-sports", "titulo": "Sin fecha no hay vigencia"},
    ])

    titulos = [i["titulo"] for i in indicaciones.indicaciones_vigentes("claro-sports", hoy=hoy)]
    assert titulos == [
        "Prioridad al Mundial",
        "Sin marca aplica a todas",
        "Justo en el borde (7 días)",
    ]  # más recientes primero; fuera: caducada, otra marca, re-tipada y sin fecha


def test_vigentes_respeta_el_tope_de_items(entorno):
    from keni_consola import repos

    hoy = date(2026, 6, 11)
    _inicializar_contexto(repos, [
        {"fecha": "2026-06-11", "marca": "claro-sports", "titulo": f"Indicación {i:02d}"}
        for i in range(indicaciones.TOPE_ITEMS + 5)
    ])
    vigentes = indicaciones.indicaciones_vigentes("claro-sports", hoy=hoy)
    assert len(vigentes) == indicaciones.TOPE_ITEMS


# --------------------------------------------------------------------------- #
# Integración: componer_copy inyecta las indicaciones de SU marca              #
# --------------------------------------------------------------------------- #


def test_componer_copy_inyecta_indicaciones_vigentes_de_la_marca(entorno):
    from keni_consola import repos

    hoy = hoy_utc()
    _inicializar_contexto(repos, [
        {
            "fecha": hoy.isoformat(),
            "marca": "claro-sports",
            "titulo": "Hoy prioridad al Mundial",
        },
        {
            "fecha": (hoy - timedelta(days=indicaciones.VENTANA_DIAS + 1)).isoformat(),
            "marca": "claro-sports",
            "titulo": "Indicación caducada",
        },
    ])

    prompt = generar.componer_copy(
        "HAZ EL COPY", marca="claro-sports", contexto="Nota: gol en el 90'", redes_ids=["x"]
    )
    assert indicaciones.ENCABEZADO_INDICACIONES in prompt
    assert "Hoy prioridad al Mundial" in prompt
    assert "Indicación caducada" not in prompt
    # ORDEN: las indicaciones van en la cola variable, ANTES del CONTEXTO (no confiable) y
    # FUERA del envoltorio anti-inyección (son instrucciones confiables del equipo).
    i_indicaciones = prompt.index(indicaciones.ENCABEZADO_INDICACIONES)
    i_contexto = prompt.index("CONTEXTO:")
    assert prompt.index("HAZ EL COPY") < i_indicaciones < i_contexto
    assert "contenido_usuario" not in prompt[:i_contexto]

    # Otra marca SIN indicaciones vigentes: el prompt no cambia ni un byte.
    sin_items = generar.componer_copy(
        "HAZ EL COPY", marca="unotv", contexto="Nota", redes_ids=["x"]
    )
    assert indicaciones.ENCABEZADO_INDICACIONES not in sin_items


def test_componer_copy_sin_bd_no_rompe_ni_inyecta(monkeypatch, tmp_path):
    """BEST-EFFORT: sin Postgres el copy sale igual que hoy (sin bloque, sin excepción)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))  # no tocar el store real

    prompt = generar.componer_copy(
        "HAZ EL COPY", marca="claro-sports", contexto="Nota", redes_ids=["x"]
    )
    assert "HAZ EL COPY" in prompt
    assert indicaciones.ENCABEZADO_INDICACIONES not in prompt


# --------------------------------------------------------------------------- #
# Fecha de redacción: dato del sistema para resolver relativos a absolutos     #
# --------------------------------------------------------------------------- #


def test_componer_copy_inyecta_fecha_de_redaccion(monkeypatch, tmp_path):
    """La fecha del día va en el bloque CONTEXTO (variable), fuera del envoltorio anti-inyección.

    Es dato del sistema (no contenido del usuario) y permite al modelo convertir referencias
    temporales relativas de la fuente en fechas absolutas. No depende de la BD.
    """
    from keni_consola.dominio.placeholders import fecha_es

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))

    prompt = generar.componer_copy(
        "HAZ EL COPY", marca="unotv", contexto="el pasado domingo hubo un evento", redes_ids=["x"]
    )

    etiqueta = f"Fecha de redacción: {fecha_es()}"
    assert etiqueta in prompt
    i_contexto = prompt.index("CONTEXTO:")
    i_fecha = prompt.index("Fecha de redacción:")
    # El envoltorio anti-inyección abre con `<contenido_usuario_<nonce>>` (la primera vez en su aviso).
    i_usuario = prompt.index("<contenido_usuario_")
    # DENTRO del bloque CONTEXTO (variable) y FUERA del envoltorio del contenido del usuario.
    assert i_contexto < i_fecha < i_usuario
    # La fecha NO contamina el prefijo estable (prompt caching por marca).
    assert "Fecha de redacción:" not in prompt[:i_contexto]

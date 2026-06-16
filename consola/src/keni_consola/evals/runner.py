"""Runner del harness: carga casos, corre dimensiones, agrega el reporte y lo renderiza.

Determinista y barato (cero `claude -p`): apto para CI. La validación del CATÁLOGO (marca/red
del caso conocidas) se hace aquí, antes de correr las dimensiones: un caso que apunta a una
marca/red inexistente es un error de configuración del set, no un caso que "pasa".
"""

from __future__ import annotations

from pathlib import Path

from .checks import correr_dimensiones
from .modelo import (
    ESTADO_FALLA,
    ESTADO_NA,
    ESTADO_OK,
    CasoEval,
    ReporteEvals,
    ResultadoCaso,
    ResultadoDimension,
    cargar_casos,
)


def _validar_catalogo(caso: CasoEval) -> list[str]:
    """Errores de catálogo del caso (marca/red desconocidas). Reusa los catálogos canónicos."""
    errores: list[str] = []
    try:
        from keni_consola import marcas, redes

        if not marcas.es_marca(caso.marca):
            errores.append(f"marca desconocida: {caso.marca!r}")
        if not redes.es_red(caso.red):
            errores.append(f"red desconocida: {caso.red!r}")
    except Exception:  # noqa: BLE001 -- sin catálogo cargable no validamos (no rompemos)
        return []
    return errores


def correr_caso(caso: CasoEval) -> ResultadoCaso:
    """Corre un caso: valida catálogo y ejecuta sus dimensiones aplicables."""
    errores = _validar_catalogo(caso)
    if errores:
        # Un caso mal dirigido FALLA de forma explícita en una pseudo-dimensión `catalogo`.
        return ResultadoCaso(
            caso=caso,
            dimensiones=[ResultadoDimension(nombre="catalogo", estado=ESTADO_FALLA, avisos=tuple(errores))],
        )
    return ResultadoCaso(caso=caso, dimensiones=correr_dimensiones(caso))


def correr_casos(casos: list[CasoEval]) -> ReporteEvals:
    """Corre una lista de casos ya cargados y devuelve el reporte agregado."""
    return ReporteEvals(resultados=[correr_caso(c) for c in casos])


def correr_directorio(directorio: Path | str | None = None) -> ReporteEvals:
    """Carga los casos de `directorio` (def `dir_casos_por_defecto`) y los corre."""
    return correr_casos(cargar_casos(directorio))


# --- Render del reporte (texto legible para humanos y logs de CI) -------------------------- #

_SIMBOLO = {ESTADO_OK: "✓", ESTADO_FALLA: "✗", ESTADO_NA: "·"}


def render_texto(reporte: ReporteEvals, *, verboso: bool = False) -> str:
    """Reporte legible: una línea por caso (dictamen vs esperado) + detalle de las dimensiones
    que fallan; con `verboso`, también las que pasan. Cierra con el score agregado."""
    lineas: list[str] = []
    lineas.append("HARNESS DE EVALS · calidad de la salida de IA (determinista, sin claude -p)")
    lineas.append("=" * 78)
    for r in reporte.resultados:
        marca_ok = "OK " if r.cuadra else "‼  "
        lineas.append(
            f"{marca_ok}[{r.caso.id}] {r.caso.marca}/{r.caso.red} "
            f"· espera={r.caso.espera} dictamen={r.dictamen}"
        )
        if r.caso.descripcion:
            lineas.append(f"      {r.caso.descripcion}")
        for d in r.dimensiones:
            if d.fallo or verboso:
                avisos = ("  " + " | ".join(d.avisos)) if d.avisos else ""
                lineas.append(f"      {_SIMBOLO.get(d.estado, '?')} {d.nombre}{avisos}")
        if not r.cuadra:
            lineas.append(
                f"      → DISCREPANCIA: el caso esperaba '{r.caso.espera}' y salió '{r.dictamen}'"
                + (
                    f" (se esperaba que fallara en '{r.caso.falla_esperada_en}'; "
                    f"falló en {r.dimensiones_fallidas or 'ninguna'})"
                    if r.caso.espera == "falla" and r.caso.falla_esperada_en
                    else ""
                )
            )
    lineas.append("-" * 78)
    lineas.append(
        f"TOTAL {reporte.total} · cuadran {reporte.cuadran} · "
        f"discrepancias {len(reporte.discrepancias)} · score {reporte.score:.0%}"
    )
    return "\n".join(lineas)

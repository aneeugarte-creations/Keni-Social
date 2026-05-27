"""Helpers de formato compartidos entre el reporte (Markdown) y el dashboard (HTML).

Centraliza los datos/strings comunes que estaban duplicados en `reporte.py` y
`dashboard.py` (DRY): el signo de un porcentaje, el mapa de motivos de omision y
la lista de partes `plataforma (motivo)` de una cobertura parcial. El render
final (Markdown vs. HTML) se queda en cada modulo; aqui solo viven los datos.
"""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import Cobertura

# Etiquetas legibles para los motivos de omision de cobertura.
_MOTIVO_TEXTO: dict[str, str] = {
    "sin_credenciales": "sin credenciales",
    "presupuesto_agotado": "presupuesto agotado",
    "error_api": "error de API",
}


# Nombre canonico de la fuente offline de datos sinteticos. UNICA fuente de
# verdad: `FuenteMuestra.nombre` usa este mismo valor y los renders comparan
# contra el (no contra el literal "muestra" disperso) para decidir si avisar.
FUENTE_MUESTRA = "muestra"

# Aviso DESTACADO de datos de muestra. Va al inicio de cada reporte/salida de
# texto (no solo en el campo `fuente`) para que sea IMPOSIBLE confundir cifras
# sinteticas con reales: el miedo #1 del cliente es publicar datos inventados
# (issue #131). Variantes Markdown y texto plano; el HTML tiene su propio banner.
AVISO_MUESTRA_MD = (
    "> ⚠️ **DATOS DE MUESTRA — NO SON CIFRAS REALES.** Generados de forma "
    "sintetica para demo/pruebas. **No tomar decisiones ni publicar con estos "
    "numeros.** Configura una fuente real para obtener datos de produccion."
)
AVISO_MUESTRA_TXT = (
    "⚠️ DATOS DE MUESTRA — NO SON CIFRAS REALES. Generados de forma sintetica "
    "para demo/pruebas. No tomar decisiones ni publicar con estos numeros."
)


def es_fuente_muestra(fuente: str | None) -> bool:
    """True si la fuente del reporte es la muestra sintetica (no datos reales)."""
    return (fuente or "").strip().lower() == FUENTE_MUESTRA


def aviso_muestra_md(fuente: str | None) -> str | None:
    """Banner Markdown de datos de muestra, o None si la fuente es real.

    Pensado para anteponerlo a cualquier reporte de texto consolidado: hace
    visible (no solo en el campo `fuente`) que las cifras son sinteticas.
    """
    return AVISO_MUESTRA_MD if es_fuente_muestra(fuente) else None


def signo(pct: float) -> str:
    """Devuelve el porcentaje con signo explicito (+/-)."""
    return f"+{pct}" if pct > 0 else f"{pct}"


def miles(n: int | float) -> str:
    """Formatea un entero con separador de miles estilo es-MX (punto: "1.234").

    UNICA fuente de verdad del separador de miles para TODA la salida (texto y
    HTML): antes el dashboard usaba punto (es-MX) y el reporte/picos/digest
    usaban la coma de Python (`f"{n:,}"`), asi que el mismo numero salia distinto
    segun el canal. Aqui se unifica al separador es-MX (punto). Si `n` no es un
    numero, cae a su texto (escapado por seguridad, ya que tambien alimenta HTML).
    """
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return escape(str(n))


def etiqueta_marca(cuenta_id: str, nombres: Mapping[str, str] | None = None) -> str:
    """Nombre legible de una marca a partir de su id interno.

    Es la MISMA regla que usa el dashboard (`nombres.get(cuenta_id, cuenta_id)`):
    se traduce el id crudo (`claro_sports`) al nombre legible (`Claro Sports`)
    usando el mapa `{id: nombre}` que las fuentes ya exponen via `cuentas()`. Si
    no hay nombre para ese id (o no se pasa mapa), se cae al id tal cual para no
    perder informacion. Centraliza el fallback id->titulo de las CLIs de texto
    (reporte, picos, digest) para que sean consistentes con el dashboard.
    """
    if not nombres:
        return cuenta_id
    return nombres.get(cuenta_id, cuenta_id)


# Nº de alertas (picos) que se muestran antes de colapsar el resto en un resumen.
# Mismo criterio que el dashboard (que muestra 6 + "ver todas (N)"); aqui, en
# texto, mostramos el top-N por magnitud y resumimos el resto en una linea.
PICOS_VISIBLES = 6


def particionar_picos(
    alertas: list, visibles: int = PICOS_VISIBLES
) -> tuple[list, int]:
    """Parte una lista de alertas (ya ordenada por magnitud) en (top-N, nº resto).

    Centraliza el criterio "top-N + resto colapsado" que comparten el reporte y
    el digest de notificaciones: en vez de volcar las ~24/~29 alertas planas,
    se muestran las `visibles` de mayor magnitud y se resume cuantas quedan. El
    render de la linea de resumen ("… y N alertas mas") se hace en cada modulo.
    """
    alertas = alertas or []
    if visibles < 0:
        visibles = 0
    return alertas[:visibles], max(len(alertas) - visibles, 0)


def linea_resto_picos(n_resto: int) -> str | None:
    """Linea de resumen para las alertas colapsadas; None si no hay resto."""
    if n_resto <= 0:
        return None
    plural = "alerta" if n_resto == 1 else "alertas"
    return f"… y {n_resto} {plural} mas (ordenadas por magnitud)"


def _cobertura_dict(cob: Cobertura | Mapping | None) -> dict | None:
    """Normaliza una `Cobertura` (modelo o dict) a un dict simple, o None."""
    if cob is None:
        return None
    if isinstance(cob, Mapping):
        return dict(cob)
    # Modelo Pydantic Cobertura -> dict JSON-serializable.
    return cob.model_dump(mode="json")


def partes_cobertura(
    cob: Cobertura | Mapping | None,
    etiqueta: Mapping[str, str] | None = None,
) -> list[str] | None:
    """Lista de partes `plataforma (motivo)` de una cobertura parcial.

    Devuelve None si respondio todo (o no aplica). `etiqueta` mapea opcionalmente
    el id de plataforma a un nombre legible (p. ej. el dashboard usa "Facebook"
    en vez de "facebook"); si se omite, se usa el id tal cual. El render final
    (Markdown vs. HTML) se construye en cada modulo a partir de estas partes.
    """
    d = _cobertura_dict(cob)
    if not d or not d.get("omitidas"):
        return None
    motivo = d.get("motivo") or {}
    etiqueta = etiqueta or {}
    partes = []
    for p in d["omitidas"]:
        nombre = etiqueta.get(p, p)
        texto = _MOTIVO_TEXTO.get(motivo.get(p, ""), motivo.get(p, "?"))
        partes.append(f"{nombre} ({texto})")
    return partes

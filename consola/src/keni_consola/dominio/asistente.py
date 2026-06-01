"""Dominio ASISTENTE de tablero: IA sobre un item de `contenido` (PURO orquestador).

El asistente del tablero (herramienta de community manager) toma un item de `contenido`
—su titulo, brief/descripcion y notas— y lanza una generacion de IA que REUTILIZA las
skills de copy ya existentes (`copy-desde-nota`, voz de marca + tropicalizacion MX +
auto-verificacion) para producir el copy por red. Tres modos:

  - `generar`    : copy nuevo, UNA pieza por red (las redes del propio contenido). El
                   frontend aplica cada pieza al `copy` de su fila `contenido_plataforma`.
  - `variantes`  : TRES opciones del copy para el contenido (en el `resultado` libre), para
                   que el community elija; sigue dando `piezas` por red como punto de
                   partida aplicable.
  - `resumir`    : condensa la nota/brief en un copy breve y directo por red.

NO es un transporte: arma el "texto base" (brief) y la instruccion ADITIVA por modo, y
delega el lanzamiento en `dominio.generar.lanzar_copy` (misma pipeline que copy/RSS: encola
un `claude -p` con el prompt de copy autocontenido + editorial, post-procesa a `{resultado,
piezas, verdicto, publicaciones}`, seguible token a token via `GET /api/generaciones/{id}`).
El handler HTTP (`api/contenido`) solo valida y llama aqui.
"""

from __future__ import annotations

from . import generar

# Etiqueta de origen del historial: el asistente REUTILIZA la pipeline de copy por red
# (piezas + veredicto + voz de marca). Solo cambia el TEXTO BASE (brief) y una instruccion
# ADITIVA por modo; el resto es la generacion de copy de siempre.
SKILL_COPY = "copy-desde-nota"

# Modos soportados por el asistente (allowlist; cualquier otro => 400 en el handler).
MODOS: tuple[str, ...] = ("generar", "variantes", "resumir")

# Instruccion ADITIVA por modo. Se ANEXA al prompt de la skill (la skill mantiene su voz
# de marca, tropicalizacion y auto-verificacion). `generar` no anade nada extra.
_INSTRUCCION_MODO: dict[str, str] = {
    "variantes": (
        "Además del copy por red, propón TRES variantes alternativas del copy "
        "(distinto enfoque o gancho) para este contenido, numeradas 1, 2 y 3, antes "
        "del bloque JSON, para que el community manager elija."
    ),
    "resumir": (
        "Haz el copy lo más BREVE y directo posible: condensa la nota a lo esencial, "
        "una idea por red, sin relleno."
    ),
}


def _brief(titulo: str, descripcion: str, notas: str) -> str:
    """Arma el TEXTO BASE (nota) que alimenta la skill de copy desde el item del tablero.

    Junta el titulo (como encabezado), el brief/descripcion y las notas internas en un
    solo bloque de texto. Es lo que la skill trata como "la nota" a convertir en copy.
    """
    partes: list[str] = []
    if titulo.strip():
        partes.append(titulo.strip())
    if descripcion.strip():
        partes.append(descripcion.strip())
    if notas.strip():
        partes.append(f"Notas del equipo: {notas.strip()}")
    return "\n\n".join(partes)


def construir_texto_base(
    *, modo: str, titulo: str, descripcion: str, notas: str
) -> str:
    """Texto base (brief + instruccion del modo) que se pasa a la skill de copy.

    El brief sale del item del tablero; la instruccion ADITIVA del modo se anexa al final
    para no tocar el cuerpo del prompt de la skill (que ya trae voz de marca, etc.).
    """
    base = _brief(titulo, descripcion, notas)
    extra = _INSTRUCCION_MODO.get(modo, "")
    return f"{base}\n\n{extra}".rstrip() if extra else base


def lanzar(
    *,
    modo: str,
    marca: str,
    titulo: str,
    descripcion: str,
    notas: str,
    redes_ids: list[str],
    autor: dict[str, str] | None = None,
) -> dict[str, object]:
    """Lanza (ENCOLA) la generacion del asistente para un item del tablero.

    Reutiliza el prompt de copy (`SKILL_COPY`) y la pipeline de `generar.lanzar_copy`:
    compone el prompt autocontenido (copy + editorial + brief) y lo encola. Devuelve el
    registro de `generacion` (estado "ejecutando"); el frontend lo sondea y, al completarse,
    lee `resultado.piezas` para rellenar el `copy` de cada fila.
    """
    texto_base = construir_texto_base(
        modo=modo, titulo=titulo, descripcion=descripcion, notas=notas
    )
    return generar.lanzar_copy(
        marca=marca,
        contexto=texto_base,
        redes_ids=redes_ids,
        titulo=titulo,
        titulo_dado=titulo,  # el asistente fija el título de la fila como título del historial
        texto_base=texto_base,
        origen_historial=SKILL_COPY,
        autor=autor,
    )

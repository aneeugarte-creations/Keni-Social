"""Relevancia por marca para la investigacion (Plan del dia / Radar).

La investigacion es POR MARCA: el Plan del dia de Claro Sports no es "lo viral en
general", sino "lo que Claro Sports deberia publicar hoy". Para eso, cada marca
tiene un conjunto de PALABRAS CLAVE de interes; los temas que las contienen suben
en la parrilla de esa marca.

v1 (semilla en codigo): un mapa `marca_id -> palabras` para las marcas de AMX,
editable aqui. Es el primer paso explicito y versionado; la intencion es externalizar
este vocabulario a configuracion por marca (gestionable desde la Consola) sin cambiar
el contrato de `palabras_de_marca`. Honestidad: si una marca no tiene vocabulario, la
relevancia de marca no aplica (la parrilla cae a su scoring general, sin inventar).

Las palabras son tokens o frases en minuscula; el matching (en `parrilla`) es por
token o por subcadena para las frases, ya normalizado (sin acentos).
"""

from __future__ import annotations

# Vocabulario semilla por marca (id canonico → palabras de interes). Sin acentos:
# el matching normaliza el texto antes de comparar.
_PALABRAS_POR_MARCA: dict[str, frozenset[str]] = {
    "claro-sports": frozenset({
        "futbol", "soccer", "liga mx", "champions", "mundial", "seleccion",
        "nfl", "nba", "mlb", "box", "boxeo", "ufc", "f1", "formula 1",
        "golf", "tenis", "gol", "fichaje", "playoffs", "final", "torneo",
        "olimpicos", "atletismo", "ciclismo", "deporte", "deportes",
    }),
    "unotv": frozenset({
        "mexico", "cdmx", "presidencia", "gobierno", "sheinbaum", "senado",
        "elecciones", "seguridad", "clima", "sismo", "huracan", "economia",
        "salud", "educacion", "trafico", "noticia", "nacional", "estados",
    }),
    "nacion-gamer": frozenset({
        "videojuego", "videojuegos", "gaming", "gamer", "esports", "twitch",
        "playstation", "xbox", "nintendo", "switch", "steam", "pc gaming",
        "anime", "manga", "comic", "marvel", "consola", "lanzamiento",
    }),
    "piso-15": frozenset({
        "entretenimiento", "espectaculos", "famosos", "celebridades", "musica",
        "concierto", "cine", "pelicula", "serie", "streaming", "premios",
        "tendencia", "viral", "redes", "lifestyle", "moda",
    }),
    "fundacion": frozenset({
        "fundacion", "donacion", "voluntariado", "comunidad", "social",
        "causa", "ayuda", "beneficencia", "salud", "educacion", "ambiente",
        "sostenibilidad", "inclusion",
    }),
}


def palabras_de_marca(marca_id: str | None) -> frozenset[str]:
    """Palabras clave de interes de una marca (vacio si no hay marca o vocabulario).

    `marca_id` es el id canonico (slug-guion, p. ej. `claro-sports`). Devuelve un
    conjunto vacio cuando no hay marca activa o la marca no tiene vocabulario: en ese
    caso la parrilla usa su scoring general (sin relevancia de marca).
    """
    if not marca_id:
        return frozenset()
    return _PALABRAS_POR_MARCA.get(marca_id, frozenset())

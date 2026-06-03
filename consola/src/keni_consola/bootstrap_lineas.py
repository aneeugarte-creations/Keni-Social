"""Semilla idempotente de LÍNEAS de contenido (etiquetas clase 'vertical') y ORÍGENES
(clase 'origen') por marca.

- Las LÍNEAS de UnoTV las dictó el equipo (Bernardo): virales, internacional, nacional,
  presidencia, comercial, reportero/corresponsales, ciencia/tech, geek/pop, eventos.
- El resto de marcas llevan un arranque razonable (editable desde la pestaña de líneas).
- Los ORÍGENES son GLOBALES (marca=''): "Interno" (fallback, sin keywords) y "Petición
  externa" (publicación impuesta: gobierno/comercial/marketing).

Cada keyword se casa sin acentos ni mayúsculas (ver `dominio/clasificador_lineas.py`).
Idempotente: solo crea lo que no exista ya (por nombre+clase+marca); NUNCA pisa keywords
editados por el equipo. Pensada para correr en el bootstrap del arranque.
"""

from __future__ import annotations

import logging

from . import repos

_log = logging.getLogger(__name__)

# Líneas (clase 'vertical') por marca: (nombre, keywords CSV).
LINEAS_POR_MARCA: dict[str, list[tuple[str, str]]] = {
    "unotv": [
        ("Virales", "viral,insolito,curioso,impactante,camaras,video captado,no vas a creer,sorprende,gracioso"),
        ("Internacional", "internacional,mundo,eeuu,estados unidos,europa,china,rusia,ucrania,gaza,trump,onu,extranjero"),
        ("Nacional", "nacional,mexico,cdmx,estado de mexico,guadalajara,monterrey,gobernador,congreso,seguridad,inundacion,accidente"),
        ("Presidencia", "presidencia,presidenta,sheinbaum,claudia sheinbaum,mananera,palacio nacional,gobierno federal"),
        ("Comercial", "patrocinado,publicidad,promocion,oferta,descuento,lanzamiento de producto,anuncio,marca"),
        ("Reportero/Corresponsales", "corresponsal,reportero,enviado,en vivo desde,cobertura especial,reporte"),
        ("Ciencia/Tech", "ciencia,tecnologia,nasa,espacio,inteligencia artificial,estudio,investigacion,cientificos,gadget,app"),
        ("Geek/Pop", "geek,marvel,star wars,anime,videojuego,serie,pelicula,comic,netflix,disney,gamer"),
        ("Eventos", "evento,festival,concierto,feria,desfile,premios,ceremonia,expo"),
    ],
    "claro-sports": [
        ("Fútbol", "futbol,gol,liga mx,seleccion,el tri,champions,partido,messi,cristiano,barcelona,real madrid,america,chivas"),
        ("Mundial", "mundial,copa del mundo,mundial 2026,fifa,eliminatorias"),
        ("Béisbol", "beisbol,home run,jonron,mlb,pitcher,bateador,serie mundial"),
        ("Fórmula 1", "formula 1,gran premio,checo perez,verstappen,ferrari,mclaren,parrilla"),
        ("Tenis", "tenis,grand slam,roland garros,wimbledon,us open,sabalenka,alcaraz,djokovic"),
        ("Básquetbol", "basquetbol,basquet,nba,lakers,playoffs,duela"),
        ("Ciclismo", "ciclismo,tour de francia,giro,vuelta,isaac del toro,etapa"),
        ("Juegos Olímpicos", "juegos olimpicos,olimpicos,medalla,clavados,atletismo"),
        ("Americano", "nfl,futbol americano,super bowl,touchdown,quarterback"),
    ],
    "nacion-gamer": [
        ("Lanzamientos", "lanzamiento,estreno,trailer,fecha de salida,preventa,demo,gameplay"),
        ("Esports", "esports,torneo,competitivo,valorant,league of legends,dota,cs2"),
        ("Hardware", "consola,playstation,xbox,nintendo,switch,gpu,tarjeta grafica,asus,rog"),
        ("Cine/Series", "pelicula,serie,marvel,dc,netflix,hbo,disney,trailer"),
        ("Anime", "anime,manga,crunchyroll,shonen,otaku,temporada"),
        ("Virales", "viral,meme,insolito,curioso,gracioso"),
    ],
    "piso-15": [
        ("Música", "musica,cancion,album,artista,gira,nodal,cazzu,banda,corridos"),
        ("Espectáculos", "espectaculos,celebridad,farandula,famoso,escandalo,boda,ruptura"),
        ("Eventos", "evento,festival,feria,premios,alfombra roja,expo"),
        ("Cultura", "cultura,museo,exposicion,arte,libro,teatro,patrimonio"),
    ],
    "fundacion": [
        ("Salud", "salud,medicina,premio en salud,doctor,doctora,hospital,prevencion"),
        ("Educación", "educacion,curso,aprende,capacitacion,beca,taller,aprende.org"),
        ("Impacto social", "impacto social,apoyo,comunidad,donacion,pobreza,bienestar"),
        ("Cultura/Soumaya", "museo soumaya,exposicion,arte,capsula,obra,coleccion"),
    ],
}

# Orígenes GLOBALES (marca=''): "Interno" sin keywords es el FALLBACK por defecto.
ORIGENES_GLOBALES: list[tuple[str, str]] = [
    ("Interno", ""),
    (
        "Petición externa",
        "presidencia,gobierno,comercial,patrocinado,promocion,marketing,"
        "difusion,instruccion,boletin,comunicado,promo",
    ),
]


def _crear_si_falta(*, nombre: str, clase: str, marca: str, keywords: str) -> bool:
    """Crea la etiqueta si no existe (nombre+clase+marca). True si la creó."""
    if repos.existe_etiqueta_nombre(nombre, clase, marca):
        return False
    repos.crear_etiqueta(nombre=nombre, clase=clase, marca=marca, keywords=keywords)
    return True


def sembrar_lineas() -> int:
    """Siembra líneas (vertical) por marca y orígenes (global). Devuelve cuántas creó.

    Idempotente: no duplica ni pisa lo existente. Tolerante a fallos por etiqueta (no
    aborta el resto). Pensada para el bootstrap del arranque.
    """
    creadas = 0
    for marca, lineas in LINEAS_POR_MARCA.items():
        for nombre, keywords in lineas:
            try:
                if _crear_si_falta(nombre=nombre, clase="vertical", marca=marca, keywords=keywords):
                    creadas += 1
            except Exception:  # noqa: BLE001 -- una etiqueta no debe romper el resto
                _log.warning("semilla líneas: no se pudo crear %s/%s", marca, nombre, exc_info=True)
    for nombre, keywords in ORIGENES_GLOBALES:
        try:
            if _crear_si_falta(nombre=nombre, clase="origen", marca="", keywords=keywords):
                creadas += 1
        except Exception:  # noqa: BLE001
            _log.warning("semilla orígenes: no se pudo crear %s", nombre, exc_info=True)
    if creadas:
        _log.info("semilla líneas/orígenes: %d etiquetas creadas", creadas)
    return creadas

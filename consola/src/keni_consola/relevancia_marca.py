"""Relevancia por marca para la investigacion (Plan del dia / Radar / listón de noticias).

La investigacion es POR MARCA: el Plan del dia de Claro Sports no es "lo viral en
general", sino "lo que Claro Sports deberia publicar hoy". Para eso, cada marca
tiene un conjunto de PALABRAS CLAVE de interes; los temas que las contienen suben
en la parrilla de esa marca y superan el listón de producción automática.

v1 (semilla en codigo): un mapa `marca_id -> palabras` para las marcas del cliente,
editable aqui. Es el primer paso explicito y versionado; la intencion es externalizar
este vocabulario a configuracion por marca (gestionable desde la Consola) sin cambiar
el contrato de `palabras_de_marca`. Honestidad: si una marca no tiene vocabulario, la
relevancia de marca no aplica (la parrilla cae a su scoring general, sin inventar).
Cuando la etapa Editorial (perfil Haiku) esta activa, ese perfil SUSTITUYE esta
semilla (ver `noticias_liston.palabras_relevancia`); la semilla es el suelo fiable.

Las palabras son tokens o frases en minuscula y SIN ACENTOS (el matching normaliza el
texto antes de comparar): tokens por igualdad exacta de token, frases por limite de
palabra. CRITERIO de la semilla: terminos que identifican la AGENDA de la marca con
poca ambiguedad. Los nombres de UNA palabra muy genericos ("leon", "santos") van en
FRASE ("club leon", "santos laguna") para no arrastrar historias de otra agenda; los
clusters SIN marca (Trends/agencias) se asignan por este vocabulario y un falso
positivo cambia de marca la historia, no solo su score.
"""

from __future__ import annotations

# Vocabulario semilla por marca (id canonico → palabras de interes). Sin acentos:
# el matching normaliza el texto antes de comparar.
_PALABRAS_POR_MARCA: dict[str, frozenset[str]] = {
    # ------------------------------------------------------------------ #
    # Claro Sports: deportes (MX + internacional).                         #
    # ------------------------------------------------------------------ #
    "claro-sports": frozenset({
        # Deporte / genérico
        "deporte", "deportes", "deportivo", "deportista", "atleta", "campeonato",
        "torneo", "final", "semifinal", "playoffs", "eliminatoria", "clasificacion",
        "medalla", "medallista", "record", "marcador", "estadio", "fichaje", "traspaso",
        "lesion", "debut", "retiro", "contrato", "entrenador", "tecnico", "arbitro",
        # Futbol
        "futbol", "soccer", "gol", "goleada", "penal", "var", "liga mx", "liguilla",
        "jornada", "clasico", "ascenso", "descenso", "femenil", "seleccion",
        "seleccion mexicana", "el tri", "mundial", "copa del mundo", "fifa", "concacaf",
        "conmebol", "champions", "champions league", "europa league", "premier league",
        "laliga", "serie a", "bundesliga", "mls", "copa oro", "copa america",
        "leagues cup", "america", "chivas", "guadalajara", "cruz azul", "pumas",
        "tigres", "rayados", "monterrey", "toluca", "atlas", "pachuca", "club leon",
        "santos laguna", "xolos", "necaxa", "puebla fc", "real madrid", "barcelona",
        "atletico", "manchester city", "manchester united", "liverpool", "arsenal",
        "chelsea", "bayern", "juventus", "inter", "milan", "psg", "messi", "cristiano",
        "ronaldo", "mbappe", "haaland", "neymar", "vinicius", "bellingham", "lewandowski",
        # NFL / NBA / MLB
        "nfl", "super bowl", "superbowl", "touchdown", "quarterback", "futbol americano",
        "nba", "basquetbol", "baloncesto", "lebron", "curry", "lakers", "celtics",
        "mlb", "beisbol", "grandes ligas", "serie mundial", "yankees", "dodgers",
        "ohtani", "jonron",
        # Combate
        "box", "boxeo", "boxeador", "pelea", "peleador", "canelo", "ufc", "mma",
        "lucha libre", "wwe", "cinturon", "nocaut", "knockout", "titulo mundial",
        # Motor
        "f1", "formula 1", "formula uno", "gran premio", "checo perez", "verstappen",
        "ferrari", "red bull", "mclaren", "nascar", "motogp", "rally",
        # Raqueta y más
        "tenis", "tenista", "wimbledon", "roland garros", "us open", "abierto de australia",
        "atp", "wta", "djokovic", "alcaraz", "sinner", "golf", "pga", "masters",
        "golfista", "padel",
        # Olimpismo y disciplinas
        "olimpicos", "olimpico", "juegos olimpicos", "paralimpicos", "atletismo",
        "maraton", "ciclismo", "natacion", "clavados", "gimnasia", "voleibol",
        "taekwondo", "halterofilia", "triatlon",
    }),
    # ------------------------------------------------------------------ #
    # UnoTV: noticias nacionales MX (politica, seguridad, clima, economia, #
    # estados, sociedad).                                                  #
    # ------------------------------------------------------------------ #
    "unotv": frozenset({
        # País / geografía
        "mexico", "mexicano", "mexicana", "mexicanos", "nacional", "republica",
        "cdmx", "ciudad de mexico", "edomex", "estado de mexico", "guadalajara",
        "jalisco", "monterrey", "nuevo leon", "puebla", "veracruz", "oaxaca",
        "chiapas", "guerrero", "michoacan", "sinaloa", "sonora", "tamaulipas",
        "chihuahua", "coahuila", "queretaro", "guanajuato", "hidalgo", "morelos",
        "tabasco", "yucatan", "quintana roo", "cancun", "tijuana", "acapulco",
        "toluca", "ecatepec", "naucalpan", "iztapalapa", "frontera",
        # Política / gobierno
        "gobierno", "presidencia", "presidenta", "presidente", "sheinbaum", "amlo",
        "morena", "oposicion", "senado", "senadores", "diputados", "congreso",
        "camara", "ine", "elecciones", "electoral", "campana", "candidato",
        "gobernador", "gobernadora", "alcalde", "alcaldesa", "alcaldia", "municipio",
        "reforma", "ley", "decreto", "iniciativa", "constitucion", "scjn",
        "suprema corte", "tribunal", "juez", "jueza", "fiscalia", "fgr", "juicio",
        "audiencia", "secretaria de", "segob", "sre", "mananera",
        # Seguridad / justicia
        "seguridad", "violencia", "homicidio", "feminicidio", "asesinato", "balacera",
        "ataque armado", "secuestro", "desaparecidos", "extorsion", "huachicol",
        "cartel", "narco", "narcotrafico", "crimen organizado", "detenido", "detencion",
        "operativo", "guardia nacional", "sedena", "ejercito", "marina", "policia",
        "extradicion", "rescate", "victimas",
        # Clima / desastres / proteccion civil
        "clima", "sismo", "temblor", "huracan", "tormenta", "ciclon", "lluvias",
        "inundacion", "inundaciones", "granizada", "frente frio", "ola de calor",
        "sequia", "incendio", "incendio forestal", "volcan", "popocatepetl",
        "proteccion civil", "conagua", "smn", "alerta", "evacuacion", "damnificados",
        "derrumbe", "deslave",
        # Economía / consumo
        "economia", "inflacion", "peso mexicano", "dolar", "tipo de cambio", "banxico",
        "hacienda", "sat", "impuestos", "aranceles", "gasolina", "canasta basica",
        "salario", "salario minimo", "empleo", "desempleo", "remesas", "pemex", "cfe",
        "inversion", "pib", "aguinaldo", "buen fin", "profeco", "infonavit", "pension",
        "bienestar",
        # Sociedad / servicios / movilidad
        "salud", "imss", "issste", "vacuna", "vacunacion", "dengue", "covid",
        "sarampion", "hospital", "educacion", "sep", "unam", "ipn", "maestros",
        "estudiantes", "migrantes", "migracion", "aduana", "metro", "metrobus",
        "aeropuerto", "aifa", "carretera", "autopista", "bloqueo", "marcha",
        "protesta", "paro", "tren maya", "agua", "desabasto",
    }),
    # ------------------------------------------------------------------ #
    # Nación Gamer: gaming, esports y cultura geek.                        #
    # ------------------------------------------------------------------ #
    "nacion-gamer": frozenset({
        # Gaming / industria
        "videojuego", "videojuegos", "gaming", "gamer", "gamers", "jugadores",
        "consola", "consolas", "lanzamiento", "trailer", "gameplay", "dlc",
        "expansion", "remake", "remaster", "beta", "early access", "parche",
        "actualizacion", "speedrun", "free to play", "battle royale", "indie",
        "mod", "crossover", "skin", "temporada",
        # Plataformas / hardware
        "playstation", "ps5", "ps4", "psn", "xbox", "game pass", "nintendo",
        "switch", "steam", "steam deck", "pc gaming", "epic games", "gpu", "nvidia",
        "geforce", "rtx", "radeon", "realidad virtual", "psvr", "emulador",
        # Empresas / estudios
        "sony", "activision", "blizzard", "ubisoft", "electronic arts", "ea sports",
        "rockstar", "bethesda", "capcom", "konami", "sega", "bandai namco",
        "square enix", "valve", "riot", "naughty dog", "fromsoftware", "kojima",
        "hoyoverse",
        # Franquicias
        "mario", "zelda", "pokemon", "kirby", "metroid", "smash bros", "mario kart",
        "animal crossing", "fortnite", "minecraft", "roblox", "gta", "grand theft auto",
        "call of duty", "warzone", "apex legends", "valorant", "league of legends",
        "dota", "counter strike", "cs2", "overwatch", "halo", "god of war",
        "the last of us", "horizon", "ghost of", "elden ring", "dark souls",
        "final fantasy", "kingdom hearts", "resident evil", "silent hill",
        "metal gear", "street fighter", "tekken", "mortal kombat", "hollow knight",
        "hades", "baldurs gate", "cyberpunk", "the witcher", "starfield", "fallout",
        "doom", "diablo", "world of warcraft", "warcraft", "hearthstone", "genshin",
        "honkai", "palworld", "among us", "ea sports fc", "efootball",
        # Esports / eventos / streaming
        "esports", "competitivo", "worlds", "major", "evo", "game awards",
        "summer game fest", "gamescom", "tokyo game show", "nintendo direct",
        "state of play", "twitch", "streamer", "streamers", "kick",
        # Cultura geek / anime / comics
        "anime", "manga", "otaku", "cosplay", "crunchyroll", "dragon ball", "naruto",
        "one piece", "demon slayer", "jujutsu kaisen", "ghibli", "comic", "comics",
        "marvel", "dc comics", "batman", "superman", "spider-man", "spiderman",
        "avengers", "x-men", "star wars",
    }),
    # ------------------------------------------------------------------ #
    # Piso 15: entretenimiento y espectaculos.                             #
    # ------------------------------------------------------------------ #
    "piso-15": frozenset({
        "entretenimiento", "espectaculos", "famosos", "celebridades", "celebridad",
        "musica", "cantante", "banda", "concierto", "conciertos", "gira", "festival",
        "album", "sencillo", "estreno", "cine", "pelicula", "peliculas", "taquilla",
        "serie", "series", "streaming", "netflix", "hbo", "disney", "premios",
        "premiacion", "oscar", "oscares", "grammy", "grammys", "alfombra roja",
        "actor", "actriz", "director", "reality", "television", "telenovela",
        "influencer", "tendencia", "viral", "redes sociales", "tiktok", "lifestyle",
        "moda", "boda", "romance", "escandalo", "polemica", "taylor swift",
        "bad bunny", "shakira", "peso pluma", "corridos",
    }),
    # ------------------------------------------------------------------ #
    # Fundación: causas sociales y comunidad.                              #
    # ------------------------------------------------------------------ #
    "fundacion": frozenset({
        "fundacion", "donacion", "donaciones", "donativo", "voluntariado",
        "voluntarios", "comunidad", "social", "causa", "causas", "ayuda",
        "beneficencia", "filantropia", "ong", "salud", "educacion", "becas",
        "ambiente", "medio ambiente", "sostenibilidad", "sustentable", "reciclaje",
        "reforestacion", "inclusion", "discapacidad", "equidad", "pobreza",
        "damnificados", "albergue", "rescate animal", "bienestar social",
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

"""Dominio RECICLAJE PROACTIVO: sugiere contenido de ARCHIVO que merece retomarse.

El reciclaje manual ya existe (`POST /api/publicaciones/{id}/reciclar`): duplica una
pieza ya publicada (o perenne) y la encola. Lo que FALTA, y resuelve este modulo, es
la capa PROACTIVA: en vez de esperar a que alguien recuerde una pieza vieja, la app
PROPONE candidatas del archivo con un MOTIVO explicable. El caso de uso real es "este
video/post se reviralizo / vuelve a ser relevante".

NO usa ML. La heuristica es simple, deterministica y AUDITABLE; cada candidata trae
su `motivo` (etiqueta), su `detalle` (frase para la UI) y una `puntuacion` para ordenar.
Solo LECTURA: no toca persistencia, recibe las publicaciones ya cargadas.

SENALES (de mas a menos fuerte):
  1. EFEMERIDE / estacional — el titulo/contenido casa con una efemeride MX que cae
     dentro de una ventana proxima (por defecto 21 dias). Es la senal mas fuerte:
     el contexto vuelve a hacer la pieza relevante AHORA.
  2. PERENNE MADURADA — la pieza esta marcada `evergreen` (el equipo ya la juzgo
     reutilizable: el mejor proxy de "rindio bien") y ha pasado suficiente tiempo
     desde su ultima actividad para volver a sacarla sin saturar.
  3. ANTIGUEDAD + TEMA RECURRENTE — pieza publicada hace tiempo cuyo tema reaparece
     en piezas mas recientes de la MISMA marca (palabras clave compartidas): senal
     de que el tema "vuelve a circular".

Solo se consideran piezas en estado `publicado` (archivo real). Se EXCLUYEN las que ya
tienen una copia reciente (mismo titulo/marca/red en estado borrador o programado):
si ya se reciclo, no se vuelve a proponer.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

from .. import marcas, redes

# --------------------------------------------------------------------------- #
# Parametros de la heuristica (constantes, faciles de auditar/ajustar)         #
# --------------------------------------------------------------------------- #

# Ventana (dias) para considerar una efemeride "proxima".
VENTANA_EFEMERIDE_DIAS = 21
# Edad minima (dias desde la ultima actividad) para proponer una perenne madurada.
EDAD_MINIMA_PERENNE_DIAS = 30
# Edad minima (dias) para que una pieza cuente como "archivo antiguo" reutilizable.
EDAD_MINIMA_ANTIGUEDAD_DIAS = 60
# Minimo de palabras clave compartidas para considerar un tema "recurrente".
MIN_PALABRAS_TEMA_RECURRENTE = 2
# Tope de candidatas devueltas (la UI muestra una lista discreta, no un volcado).
MAX_CANDIDATAS = 12

# Motivos (etiquetas estables que la UI pinta con su propio icono/color).
MOTIVO_EFEMERIDE = "efemeride"
MOTIVO_PERENNE = "perenne"
MOTIVO_RECURRENTE = "recurrente"

# Puntuacion base por motivo (la efemeride manda; desempata la edad).
_PESO_MOTIVO = {
    MOTIVO_EFEMERIDE: 1000,
    MOTIVO_PERENNE: 500,
    MOTIVO_RECURRENTE: 250,
}

# Palabras vacias (es-MX) que NO cuentan como "tema" al cruzar piezas.
_VACIAS: frozenset[str] = frozenset(
    """
    el la los las un una unos unas de del al a ante con en para por sobre tras
    y o u e ni que se su sus mi mis tu tus le les lo me te nos os es son fue ser
    como mas mas pero si no ya muy entre desde hasta este esta estos estas ese esa
    esos esas aqui alli hay ha han haber estar estan era eran sera seran cuando
    donde quien cual cuales porque sin segun cada todo toda todos todas otro otra
    """.split()
)

# Calendario MINIMO de efemerides MX (mes, dia, etiqueta, palabras clave). No es
# exhaustivo: es un punto de partida explicable que el equipo puede ampliar. Las
# palabras clave se comparan ya normalizadas (sin acentos, minusculas).
_EFEMERIDES: tuple[tuple[int, int, str, tuple[str, ...]], ...] = (
    (1, 1, "Ano Nuevo", ("ano nuevo", "propositos")),
    (2, 14, "Dia del Amor y la Amistad", ("amor", "amistad", "san valentin", "pareja")),
    (3, 8, "Dia de la Mujer", ("mujer", "mujeres", "8m", "feminismo")),
    (3, 21, "Natalicio de Benito Juarez", ("benito juarez", "juarez")),
    (4, 30, "Dia del Nino", ("nino", "ninos", "infancia")),
    (5, 1, "Dia del Trabajo", ("trabajo", "trabajador", "trabajadores")),
    (5, 5, "Batalla de Puebla", ("cinco de mayo", "puebla", "batalla")),
    (5, 10, "Dia de las Madres", ("madre", "madres", "mama")),
    (5, 15, "Dia del Maestro", ("maestro", "maestros", "docente")),
    (9, 16, "Independencia de Mexico", ("independencia", "grito", "viva mexico")),
    (10, 31, "Halloween", ("halloween", "disfraz", "disfraces")),
    (11, 2, "Dia de Muertos", ("dia de muertos", "muertos", "ofrenda", "catrina")),
    (11, 20, "Revolucion Mexicana", ("revolucion mexicana", "revolucion")),
    (12, 12, "Dia de la Virgen de Guadalupe", ("guadalupe", "virgen", "basilica")),
    (12, 25, "Navidad", ("navidad", "posada", "posadas", "nochebuena")),
)


# --------------------------------------------------------------------------- #
# Utilidades de texto y fechas                                                 #
# --------------------------------------------------------------------------- #


def _normalizar(texto: str) -> str:
    """Minusculas sin acentos (para comparar palabras clave de forma robusta)."""
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _palabras(texto: str) -> set[str]:
    """Conjunto de palabras 'utiles' (>=4 letras, sin acentos, sin vacias)."""
    crudas = re.findall(r"[a-z0-9]+", _normalizar(texto))
    return {p for p in crudas if len(p) >= 4 and p not in _VACIAS}


def _parsear_fecha(iso: str) -> datetime | None:
    """Parsea una fecha ISO de publicacion; None si esta vacia o no es valida."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _dias_hasta_efemeride(efemeride: tuple[int, int, str, tuple[str, ...]], hoy: date) -> int:
    """Dias desde hoy hasta la PROXIMA ocurrencia de la efemeride (0 = hoy)."""
    mes, dia, _, _ = efemeride
    año = hoy.year
    try:
        proxima = date(año, mes, dia)
    except ValueError:  # p. ej. 29-feb en año no bisiesto: empuja al 1-mar
        proxima = date(año, mes, 28)
    if proxima < hoy:
        try:
            proxima = date(año + 1, mes, dia)
        except ValueError:
            proxima = date(año + 1, mes, 28)
    return (proxima - hoy).days


# --------------------------------------------------------------------------- #
# Heuristica                                                                   #
# --------------------------------------------------------------------------- #


def _es_archivo(pub: dict[str, Any]) -> bool:
    """True si la pieza es archivo reutilizable: publicada (estado 'publicado')."""
    return pub.get("estado") == "publicado"


def _claves_copia(pub: dict[str, Any]) -> tuple[str, str, str]:
    """Clave de identidad (titulo normalizado, marca, red) para detectar copias."""
    return (_normalizar(pub.get("titulo", "")).strip(), pub.get("marca", ""), pub.get("red", ""))


def _ya_reciclada(pub: dict[str, Any], pendientes: set[tuple[str, str, str]]) -> bool:
    """True si ya existe una copia pendiente (borrador/programado) de esta pieza."""
    return _claves_copia(pub) in pendientes


def _detalle_pieza(pub: dict[str, Any]) -> dict[str, Any]:
    """Recorta los campos de la pieza relevantes para la UI de la candidata."""
    return {
        "id": pub["id"],
        "titulo": pub.get("titulo", ""),
        "marca": pub.get("marca", ""),
        "marca_nombre": marcas.etiqueta_de(pub.get("marca", "")),
        "red": pub.get("red", ""),
        "red_nombre": redes.nombre_por_id(pub.get("red", "")),
        "fecha_creacion": pub.get("fecha_creacion", ""),
        "fecha_actualizacion": pub.get("fecha_actualizacion", ""),
    }


def _candidata(
    pub: dict[str, Any], motivo: str, detalle: str, puntuacion: int
) -> dict[str, Any]:
    """Construye el dict de una candidata de reciclaje para la API/UI."""
    return {
        **_detalle_pieza(pub),
        "motivo": motivo,
        "motivo_detalle": detalle,
        "puntuacion": puntuacion,
    }


def _por_efemeride(
    pub: dict[str, Any], hoy: date
) -> tuple[str, int] | None:
    """Detalle+bonus si la pieza casa con una efemeride proxima; None si no."""
    texto = _normalizar(f"{pub.get('titulo', '')} {pub.get('contenido', '')}")
    mejor: tuple[str, int] | None = None
    for efemeride in _EFEMERIDES:
        _, _, etiqueta, claves = efemeride
        if not any(clave in texto for clave in claves):
            continue
        dias = _dias_hasta_efemeride(efemeride, hoy)
        if dias > VENTANA_EFEMERIDE_DIAS:
            continue
        cuando = "hoy" if dias == 0 else f"en {dias} día{'s' if dias != 1 else ''}"
        detalle = f"{etiqueta} es {cuando}: este contenido vuelve a ser relevante."
        # Cuanto mas cerca la efemeride, mayor bonus (manda la mas inminente).
        bonus = VENTANA_EFEMERIDE_DIAS - dias
        if mejor is None or bonus > mejor[1]:
            mejor = (detalle, bonus)
    return mejor


def _por_perenne(pub: dict[str, Any], hoy: date) -> tuple[str, int] | None:
    """Detalle+bonus si es perenne madurada (evergreen + antiguedad); None si no."""
    if not pub.get("evergreen"):
        return None
    ref = _parsear_fecha(pub.get("fecha_actualizacion", "")) or _parsear_fecha(
        pub.get("fecha_creacion", "")
    )
    if ref is None:
        return None
    dias = (hoy - ref.date()).days
    if dias < EDAD_MINIMA_PERENNE_DIAS:
        return None
    detalle = (
        f"Contenido perenne sin volver a publicarse en {dias} días: "
        "buen momento para retomarlo."
    )
    return (detalle, dias)


def _temas_recientes(publicadas: list[dict[str, Any]], hoy: date) -> dict[str, set[str]]:
    """Palabras-tema por marca de las piezas publicadas RECIENTES (< antiguedad min).

    Se usa para detectar que el tema de una pieza vieja "vuelve a circular": si una
    pieza antigua comparte palabras clave con piezas recientes de su misma marca.
    """
    por_marca: dict[str, set[str]] = {}
    for pub in publicadas:
        fecha = _parsear_fecha(pub.get("fecha_creacion", ""))
        if fecha is None:
            continue
        if (hoy - fecha.date()).days >= EDAD_MINIMA_ANTIGUEDAD_DIAS:
            continue  # solo piezas recientes alimentan el "tema actual"
        marca = pub.get("marca", "")
        por_marca.setdefault(marca, set()).update(
            _palabras(f"{pub.get('titulo', '')} {pub.get('contenido', '')}")
        )
    return por_marca


def _por_recurrente(
    pub: dict[str, Any], hoy: date, temas: dict[str, set[str]]
) -> tuple[str, int] | None:
    """Detalle+bonus si es archivo antiguo cuyo tema reaparece reciente; None si no."""
    fecha = _parsear_fecha(pub.get("fecha_creacion", ""))
    if fecha is None:
        return None
    dias = (hoy - fecha.date()).days
    if dias < EDAD_MINIMA_ANTIGUEDAD_DIAS:
        return None
    recientes = temas.get(pub.get("marca", ""), set())
    if not recientes:
        return None
    propias = _palabras(f"{pub.get('titulo', '')} {pub.get('contenido', '')}")
    comunes = propias & recientes
    if len(comunes) < MIN_PALABRAS_TEMA_RECURRENTE:
        return None
    muestra = ", ".join(sorted(comunes)[:3])
    detalle = (
        f"Tema recurrente ({muestra}): vuelve a circular y tu archivo "
        f"ya lo cubrió hace {dias} días."
    )
    return (detalle, len(comunes))


def candidatas_reciclaje(
    publicaciones: list[dict[str, Any]],
    *,
    hoy: date | None = None,
    limite: int = MAX_CANDIDATAS,
) -> list[dict[str, Any]]:
    """Propone piezas de archivo a reciclar, cada una con su motivo explicable.

    `publicaciones` son TODAS las piezas (de cualquier estado): las pendientes
    (borrador/programado) se usan para no reproponer lo ya reciclado, y las
    publicadas recientes para detectar temas recurrentes. Solo las piezas en estado
    `publicado` son candidatas. Devuelve como mucho `limite`, ordenadas por
    puntuacion (efemeride > perenne > recurrente; desempata la senal interna),
    UNA candidata por pieza (gana su motivo mas fuerte).
    """
    if hoy is None:
        hoy = date.today()

    publicadas = [p for p in publicaciones if _es_archivo(p)]
    pendientes = {
        _claves_copia(p)
        for p in publicaciones
        if p.get("estado") in ("borrador", "programado")
    }
    temas = _temas_recientes(publicadas, hoy)

    candidatas: list[dict[str, Any]] = []
    for pub in publicadas:
        if _ya_reciclada(pub, pendientes):
            continue
        # Para cada pieza elegimos su MOTIVO mas fuerte (no duplicamos la pieza).
        opciones: list[tuple[str, str, int]] = []
        if (ef := _por_efemeride(pub, hoy)) is not None:
            opciones.append((MOTIVO_EFEMERIDE, ef[0], _PESO_MOTIVO[MOTIVO_EFEMERIDE] + ef[1]))
        if (pe := _por_perenne(pub, hoy)) is not None:
            opciones.append((MOTIVO_PERENNE, pe[0], _PESO_MOTIVO[MOTIVO_PERENNE] + pe[1]))
        if (re_ := _por_recurrente(pub, hoy, temas)) is not None:
            opciones.append(
                (MOTIVO_RECURRENTE, re_[0], _PESO_MOTIVO[MOTIVO_RECURRENTE] + re_[1])
            )
        if not opciones:
            continue
        motivo, detalle, puntuacion = max(opciones, key=lambda o: o[2])
        candidatas.append(_candidata(pub, motivo, detalle, puntuacion))

    candidatas.sort(key=lambda c: (-c["puntuacion"], c["titulo"]))
    return candidatas[: max(0, limite)]

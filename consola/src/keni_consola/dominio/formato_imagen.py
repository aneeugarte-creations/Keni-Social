"""¿La imagen de una pieza tiene un FORMATO (aspecto) de social válido? — lógica PURA.

La validación editorial exige que la pieza tenga "imagen con formato correcto" antes de
abrir los OK del equipo. "Formato correcto" = la imagen es uno de los LIENZOS CANÓNICOS de
social (`formatos_red.ASPECTOS`): vertical 9:16, feed 4:5, cuadrado 1:1, horizontal 16:9. Es
decir: una placa bien formateada, no un recorte raro (un thumbnail apaisado de la fuente, un
banner). Aquí, sin I/O ni Pillow, decidimos si unas dimensiones `(ancho, alto)` encajan en
ALGUNO de esos aspectos, con tolerancia (las exportaciones reales rara vez dan el ratio exacto
al píxel). El llamante lee las dimensiones de la imagen y nos las pasa.

NO se exige el formato POR RED: el equipo cruza formatos (postea 1:1 y 4:5 indistintamente en
IG/FB/X), así que atar cada red a un único lienzo bloqueaba imágenes perfectamente válidas. La
matriz `red -> lienzos` de `formatos_red` describe qué GENERA el flujo de ilustración desde una foto,
no qué es aceptable al validar; por eso aquí miramos el set canónico completo. `red` se conserva
en la firma por compatibilidad (y por si en el futuro se quiere afinar por red).
"""

from __future__ import annotations

from ..formatos_red import ASPECTOS


def _ratio(aspecto: str) -> float | None:
    """`"9:16"` -> 0.5625; None si la cadena no es un aspecto `a:b` válido."""
    try:
        a_txt, b_txt = aspecto.split(":")
        a, b = float(a_txt), float(b_txt)
    except (ValueError, AttributeError):
        return None
    return a / b if b else None


def formato_correcto(red: str, ancho: int, alto: int, *, tolerancia: float = 0.06) -> bool:
    """True si `(ancho, alto)` coincide con un lienzo CANÓNICO de social (con `tolerancia`).

    Acepta cualquiera de los aspectos canónicos (9:16, 4:5, 1:1, 16:9), independientemente de
    la `red`: el equipo cruza formatos. `tolerancia` es la desviación relativa máxima del ratio
    (def 6%): cubre los pocos píxeles que sobran/faltan en una exportación real sin colar
    aspectos raros (un 3:1 o un thumbnail apaisado no pasan). Dimensiones no positivas -> False.
    """
    if ancho <= 0 or alto <= 0:
        return False
    real = ancho / alto
    for aspecto in ASPECTOS.values():
        esperado = _ratio(aspecto)
        if esperado is not None and abs(real - esperado) <= tolerancia * esperado:
            return True
    return False

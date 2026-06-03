"""¿La imagen de una pieza tiene el FORMATO (aspecto) que pide su red? — lógica PURA.

El auto-avance "dale el OK" exige que la pieza tenga "imagen con formato correcto" antes de
abrir los OK del equipo. La matriz canónica `red -> lienzos` vive en `formatos_red` (feed 4:5,
vertical 9:16, cuadrado 1:1, horizontal 16:9). Aquí, sin I/O ni Pillow, decidimos si unas
dimensiones `(ancho, alto)` encajan en ALGUNO de los lienzos que la red admite, con tolerancia
(las exportaciones reales rara vez dan el ratio exacto al píxel). El llamante (auto_avance) lee
las dimensiones de la imagen y nos las pasa; así esta capa es trivial de testear.

Una red SIN formatos en la matriz (p.ej. `web`) no impone aspecto: cualquier imagen vale.
"""

from __future__ import annotations

from ..formatos_red import ASPECTOS, lienzos_de


def _ratio(aspecto: str) -> float | None:
    """`"9:16"` -> 0.5625; None si la cadena no es un aspecto `a:b` válido."""
    try:
        a_txt, b_txt = aspecto.split(":")
        a, b = float(a_txt), float(b_txt)
    except (ValueError, AttributeError):
        return None
    return a / b if b else None


def formato_correcto(red: str, ancho: int, alto: int, *, tolerancia: float = 0.06) -> bool:
    """True si `(ancho, alto)` encaja en algún lienzo que admite `red` (con `tolerancia`).

    `tolerancia` es la desviación relativa máxima del ratio (def 6%): cubre los pocos píxeles
    que sobran/faltan en una exportación real sin colar formatos equivocados (un 9:16 jamás
    pasa por 4:5). Dimensiones no positivas -> False (no se puede verificar). Red sin lienzos
    en la matriz -> True (esa red no impone formato).
    """
    if ancho <= 0 or alto <= 0:
        return False
    lienzos = lienzos_de(red)
    if not lienzos:
        return True  # red sin matriz de formatos (p.ej. web): no se exige aspecto
    real = ancho / alto
    for lienzo in lienzos:
        esperado = _ratio(ASPECTOS.get(lienzo, ""))
        if esperado is not None and abs(real - esperado) <= tolerancia * esperado:
            return True
    return False

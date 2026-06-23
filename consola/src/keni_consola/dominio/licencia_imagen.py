"""Bloqueo infranqueable: una imagen de STOCK no autorizada NUNCA se publica.

Las fotos de stock (RSS original o APIs gratuitas) entran al sistema SOLO como AYUDA VISUAL:
se muestran atenuadas y con watermark "SIN LICENCIA", `falta_imagen` sigue activo, y NINGÚN
camino a `programado`/`publicado` las deja pasar hasta que un humano REVISE los derechos y las
autorice (`imagen_autorizada=1`). Internamente se pueden descargar/ver como referencia; lo que
queda prohibido es publicarlas sin licencia.

Una pieza es "stock sin autorizar" cuando `imagen_origen == 'stock'` y `imagen_autorizada` es
falso. El disparador es `imagen_origen` (no el default de `imagen_autorizada`), así la seguridad
no depende de un default: las piezas no-stock (todas las históricas) publican como siempre.

Este helper es la FUENTE ÚNICA del criterio; lo invocan los cinco caminos que llevan a publicar
(aprobación manual, auto-programación, PATCH de plataforma / MCP tablero, PUT de pieza, y el
programador que hace el posteo real), para que el bloqueo cubra TODAS las rutas.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Valor de `imagen_origen` que marca una foto externa (RSS/API gratuita) usada como ayuda visual.
ORIGEN_STOCK = "stock"

# Valor de `imagen_origen` de una foto con LICENCIA editorial (p. ej. AFP): SÍ es publicable sin
# autorización manual de derechos (la licencia ya los cubre), con CRÉDITO/BYLINE obligatorio. A
# diferencia del stock gratuito, NO dispara el bloqueo: solo `'stock'` sin autorizar bloquea.
ORIGEN_LICENCIADA = "licenciada"

# Estados de publicación cuya entrada exige una imagen publicable (con licencia o autorizada).
ESTADOS_PUBLICABLES = frozenset({"programado", "publicado"})

# Mensaje único de rechazo (lo reusan API y MCP para responder igual en todos los caminos).
MOTIVO_BLOQUEO = (
    "La imagen es de stock SIN LICENCIA (solo ayuda visual): no se puede programar ni publicar "
    "hasta sustituirla por una propia/licenciada o autorizarla expresamente."
)


def es_stock_sin_autorizar(pieza: Mapping[str, Any] | None) -> bool:
    """True si la imagen adjunta es de stock y aún no la autorizó un humano.

    Acepta tanto el dict público de pieza (`db_piezas`) como la fila por plataforma
    (`db_publicacion`): ambos exponen `imagen_origen` e `imagen_autorizada`.
    """
    if not pieza:
        return False
    if (pieza.get("imagen_origen") or "") != ORIGEN_STOCK:
        return False
    return not bool(pieza.get("imagen_autorizada"))


def bloquea_estado(pieza: Mapping[str, Any] | None, estado_destino: str | None) -> bool:
    """True si mover la pieza a `estado_destino` debe bloquearse por imagen de stock sin autorizar."""
    if (estado_destino or "") not in ESTADOS_PUBLICABLES:
        return False
    return es_stock_sin_autorizar(pieza)

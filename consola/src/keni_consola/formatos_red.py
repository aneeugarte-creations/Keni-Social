"""Matriz `red -> formatos de imagen` — fuente UNICA de los lienzos por red (Fase 3).

Hoy `limites_plataforma` solo cubre el TEXTO (topes de caracteres por red). Lo que
NO existia hasta ahora es la matriz visual: que LIENZOS de imagen necesita cada red
para sus distintos tipos de pieza (post de feed, reel/story, short...). Este modulo
la define como DATOS, propiedad del flujo de Arte multi-formato.

DECISION DE DIRECCION (plan §5): los formatos los dicta la RED, no el usuario. El
equipo postea posts y reels en IG, posts en X, video en TikTok, etc.; eso se reduce a
una matriz de POCOS recortes canonicos. En la practica son **3 lienzos** que cubren
todo:

  - `vertical`   (9:16, 1080x1920) — reels / stories / TikTok / shorts.
  - `feed`       (4:5,  1080x1350) — post de feed de IG (sirve tambien a FB).
  - `cuadrado`   (1:1,  1080x1080) — post 1:1 (FB).
  - `horizontal` (16:9, 1600x900)  — post de X / web.

Las CLAVES de lienzo (`vertical|feed|cuadrado|horizontal`) son EXACTAMENTE las del
motor determinista (`motores/estudio_imagen/editar.py:FORMATOS` y `dominio/
estudio_imagen.ASPECTOS`): esta matriz NO redefine medidas, solo mapea `red -> que
lienzos` para que el flujo de arte genere el set de una sola foto aportada.

Sin estado ni I/O: solo datos y funciones puras (como `redes.py`). La matriz por
DEFECTO es la del plan; es ajustable cambiando `MATRIZ` (o, mas adelante, cargandola
de configuracion como hace `keni_shared.cliente` con las marcas).
"""

from __future__ import annotations

from dataclasses import dataclass

# Lienzos canonicos. Las claves COINCIDEN con `motores/estudio_imagen/editar.py:FORMATOS`
# y con `dominio/estudio_imagen.ASPECTOS` (misma identidad de formato en todo el Estudio).
# `(ancho, alto)` SOLO con fines de presentacion/diagnostico aqui: la medida REAL la
# aplica el motor (no se duplica la verdad; debe coincidir con `FORMATOS`).
LIENZOS: dict[str, tuple[int, int]] = {
    "vertical": (1080, 1920),   # 9:16
    "feed": (1080, 1350),       # 4:5
    "cuadrado": (1080, 1080),   # 1:1
    "horizontal": (1600, 900),  # 16:9
}

# Relacion de aspecto humana por lienzo (espejo de `ASPECTOS` del dominio).
ASPECTOS: dict[str, str] = {
    "vertical": "9:16",
    "feed": "4:5",
    "cuadrado": "1:1",
    "horizontal": "16:9",
}


@dataclass(frozen=True)
class FormatoSalida:
    """Un lienzo de salida para una red, con su tipo editorial (post/reel/short...).

    - `tipo`    rol editorial de la pieza en esa red (`post`, `reel`, `story`,
                `short`, `video`). Es lo que el equipo "postea" en lenguaje de red.
    - `lienzo`  clave de lienzo canonico (`vertical|feed|cuadrado|horizontal`).
    """

    tipo: str
    lienzo: str

    @property
    def aspecto(self) -> str:
        """Relacion de aspecto humana del lienzo (p.ej. `9:16`)."""
        return ASPECTOS.get(self.lienzo, "")

    @property
    def tamano(self) -> tuple[int, int]:
        """`(ancho, alto)` nominal del lienzo (referencia; la medida la aplica el motor)."""
        return LIENZOS.get(self.lienzo, (1080, 1350))


# Matriz POR DEFECTO `red -> formatos de salida` (plan §5). Ajustable: el flujo de arte
# la consume por las funciones puras de abajo, asi que cambiar esta tabla cambia el set.
# El ORDEN dentro de cada red es estable (define el orden del set generado).
MATRIZ: dict[str, tuple[FormatoSalida, ...]] = {
    "instagram": (
        FormatoSalida("post", "feed"),       # 4:5
        FormatoSalida("reel", "vertical"),   # 9:16 (sirve tambien a story)
    ),
    "facebook": (
        FormatoSalida("post", "cuadrado"),   # 1:1
        FormatoSalida("reel", "vertical"),   # 9:16
    ),
    "x": (
        FormatoSalida("post", "horizontal"),  # 16:9
    ),
    "tiktok": (
        FormatoSalida("video", "vertical"),  # 9:16
    ),
    "youtube": (
        FormatoSalida("short", "vertical"),  # 9:16
    ),
}


def formatos_de(red: str) -> tuple[FormatoSalida, ...]:
    """Formatos de salida para una red; `()` si la red no esta en la matriz."""
    return MATRIZ.get(red, ())


def lienzos_de(red: str) -> list[str]:
    """Lienzos canonicos (sin duplicados, en orden) que necesita una red.

    Si una red repite lienzo entre tipos (p.ej. reel y story ambos 9:16), se genera
    una sola vez: el set por foto se indexa por lienzo, no por tipo.
    """
    vistos: list[str] = []
    for f in formatos_de(red):
        if f.lienzo not in vistos:
            vistos.append(f.lienzo)
    return vistos


def lienzos_canonicos() -> list[str]:
    """Todos los lienzos distintos que aparecen en la matriz, en orden de `LIENZOS`.

    Es el set MAXIMO: si no se filtra por red, el flujo de arte genera estos lienzos
    (en la practica los 3-4 que cubren todas las redes).
    """
    usados = {f.lienzo for fmts in MATRIZ.values() for f in fmts}
    return [k for k in LIENZOS if k in usados]


def redes_que_usan(lienzo: str) -> list[str]:
    """Redes (en orden de la matriz) que necesitan un lienzo dado. Util para el feed."""
    return [red for red, fmts in MATRIZ.items() if any(f.lienzo == lienzo for f in fmts)]


def es_lienzo(lienzo: str) -> bool:
    """True si `lienzo` es una clave de lienzo canonico conocida."""
    return lienzo in LIENZOS


def como_lista() -> list[dict[str, object]]:
    """Serializa la matriz para la UI / diagnostico: `[{red, formatos:[...]}]`.

    Cada formato lleva `tipo`, `lienzo`, `aspecto` y `tamano` ("AxB") para que el
    frontend pinte que sale por red sin redefinir nada.
    """
    salida: list[dict[str, object]] = []
    for red, fmts in MATRIZ.items():
        salida.append(
            {
                "red": red,
                "formatos": [
                    {
                        "tipo": f.tipo,
                        "lienzo": f.lienzo,
                        "aspecto": f.aspecto,
                        "tamano": f"{f.tamano[0]}x{f.tamano[1]}",
                    }
                    for f in fmts
                ],
            }
        )
    return salida

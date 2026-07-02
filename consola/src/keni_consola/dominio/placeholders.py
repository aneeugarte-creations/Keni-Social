"""Dominio PLACEHOLDERS: variables `{...}` en el copy del tablero (PURO, sin HTTP).

El community manager escribe el copy de una fila `pieza` con VARIABLES
entre llaves que se autocompletan con el contexto del contenido y su marca:

  - `{marca}`     nombre humano de la marca del contenido (vacio si no tiene).
  - `{fecha}`     fecha de hoy, formateada en es-MX (p.ej. "29 de mayo de 2026").
  - `{titulo}`    titulo del item del tablero.
  - `{programa}`  programa/campana del contenido (evergreen), si lo tiene.
  - `{hashtags}`  los hashtags del PRIMER grupo de hashtags de esa marca, unidos por
                  espacio (vacio si la marca no tiene ningun grupo). Reutiliza el
                  catalogo de grupos de hashtags ya existente (no inventa nada).

Logica PURA: dado un `mapa` `var -> valor` ya resuelto, sustituye las variables del
texto. La RESOLUCION del mapa (que toca marcas/repos para `{hashtags}`) vive en
`resolver_variables`, que es la unica funcion con dependencias de catalogo. El handler
HTTP (`api/publicaciones.py`) solo orquesta: pide el mapa y expande.

Robustez:
  - Una variable DESCONOCIDA se deja TAL CUAL (`{loquesea}` no se toca): nunca rompe.
  - Las llaves dobles `{{` / `}}` se respetan como literales `{` / `}` (escape), igual
    que Python str.format, para poder escribir una llave literal en el copy.
"""

from __future__ import annotations

import re
from datetime import date

from keni_shared import marcas

from ..tiempo import hoy_utc

# Variables soportadas y su explicacion humana (para el catalogo del frontend). El ORDEN
# es el de presentacion en la UI. La RESOLUCION de cada una vive en `resolver_variables`.
VARIABLES: tuple[tuple[str, str], ...] = (
    ("marca", "Nombre de la marca del contenido"),
    ("fecha", "Fecha de hoy (es-MX)"),
    ("titulo", "Título del contenido"),
    ("programa", "Programa o campaña, si lo tiene"),
    ("hashtags", "Hashtags del primer grupo de esa marca"),
)

_NOMBRES = {nombre for nombre, _ in VARIABLES}

# Una variable: `{` + nombre (sin llaves) + `}`. NO casa `{{`/`}}` (escapes): exigimos
# que el caracter previo/siguiente no sea otra llave usando lookarounds.
_RE_VAR = re.compile(r"(?<!\{)\{([a-z_]+)\}(?!\})")

# Meses en espanol para formatear `{fecha}` sin depender del locale del SO.
_MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def fecha_es(hoy: date | None = None) -> str:
    """Fecha en es-MX larga ("29 de mayo de 2026"), sin depender del locale del SO."""
    hoy = hoy or hoy_utc()
    return f"{hoy.day} de {_MESES_ES[hoy.month - 1]} de {hoy.year}"


def _hashtags_de_marca(_marca: str) -> str:
    """Variable `{hashtags}` de plantilla: hoy SIEMPRE vacía (la biblioteca de grupos se retiró).

    Los hashtags ya no se expanden desde un catálogo de grupos: la etapa `sugerir_hashtags` los
    propone en el feed para que un humano los acepte. Se conserva la variable por compatibilidad
    con las plantillas existentes, resolviéndola a "".
    """
    return ""


def resolver_variables(contenido: dict, *, hoy: date | None = None) -> dict[str, str]:
    """Mapa `variable -> valor` para un item del tablero (toca marcas/repos).

    `contenido` es un dict del tablero (`repos.obtener_publicacion`). Devuelve SIEMPRE
    todas las variables soportadas (valores vacios si el contenido no aporta el dato),
    para que el frontend pueda mostrar la previa completa.
    """
    marca_id = contenido.get("marca", "") or ""
    return {
        "marca": marcas.etiqueta_de(marca_id) if marca_id and marcas.es_marca(marca_id) else "",
        "fecha": fecha_es(hoy),
        "titulo": contenido.get("titulo", "") or "",
        "programa": contenido.get("programa", "") or "",
        "hashtags": _hashtags_de_marca(marca_id),
    }


def expandir(texto: str, mapa: dict[str, str]) -> str:
    """Sustituye las variables `{...}` de `texto` por su valor segun `mapa` (PURO).

    - Una variable conocida pero AUSENTE del mapa se trata como vacia.
    - Una variable DESCONOCIDA (no en `VARIABLES`) se deja literal (`{loquesea}`).
    - `{{`/`}}` se colapsan a `{`/`}` literales (escape), como en str.format.
    """
    if not texto:
        return texto

    def _sub(m: re.Match[str]) -> str:
        nombre = m.group(1)
        if nombre not in _NOMBRES:
            return m.group(0)  # desconocida: literal
        return mapa.get(nombre, "")

    expandido = _RE_VAR.sub(_sub, texto)
    # Escapes: `{{`/`}}` -> `{`/`}`. Se hace DESPUES para no interferir con `_RE_VAR`.
    return expandido.replace("{{", "{").replace("}}", "}")


def catalogo() -> list[dict[str, str]]:
    """Catalogo `[{clave, etiqueta, ejemplo}]` de variables para la UI del tablero.

    `ejemplo` es la sintaxis lista para insertar (`{marca}`), `etiqueta` la explicacion.
    No resuelve valores (eso depende del contenido concreto): es estatico.
    """
    return [
        {"clave": nombre, "ejemplo": "{" + nombre + "}", "etiqueta": etiqueta}
        for nombre, etiqueta in VARIABLES
    ]

"""Extracción TOLERANTE de JSON de la salida de un modelo (`claude -p`) + truncado avisado.

FUENTE ÚNICA del patrón "saca el JSON de lo que dijo el modelo", antes duplicado en
`insumos_parse`, `fusion_semantica`, `traduccion`, `parrilla_import`, `perfil_editorial`
e `importador_calendario`. Cadena de intentos:

  1. `json.loads` directo (la salida ES el JSON).
  2. Bloques cercados ```json ... ``` del ÚLTIMO al primero (el modelo a veces razona antes
     y el bloque final es el bueno).
  3. Desde el último '{'/'[' balanceado del texto (prosa antes/después del JSON), extendiendo
     hacia fuera si el bloque hallado es un fragmento interno de un envoltorio mayor.

Si nada produce el tipo esperado, devuelve None. PURO: sin I/O, nunca lanza.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any

_log = logging.getLogger("keni_consola.dominio.json_llm")

_RE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# Tope de posiciones '{'/'[' que se intentan en el rescate por brackets (salidas malformadas
# enormes: cada intento fallido puede costar O(n); acotamos para no degenerar en O(n²)).
_MAX_INTENTOS_BRACKET = 50


def _desde_brackets(s: str) -> Any | None:
    """Último bloque JSON balanceado del texto (dict/list), tolerando prosa alrededor.

    Recorre los '{'/'[' del ÚLTIMO al primero con `raw_decode` (ignora lo que siga al valor).
    El bloque hallado puede ser un FRAGMENTO interno (p.ej. el último objeto de la lista
    envolvente cuando el envoltorio lleva prefijo): se prueba desde brackets ANTERIORES y se
    prefiere el que lo CONTENGA.
    """
    dec = json.JSONDecoder()
    posiciones = [i for i, c in enumerate(s) if c in "[{"]
    base: tuple[int, int, Any] | None = None
    for i in reversed(posiciones[-_MAX_INTENTOS_BRACKET:]):
        try:
            valor, fin = dec.raw_decode(s, i)
        except ValueError:
            continue
        if isinstance(valor, (dict, list)):
            base = (i, fin, valor)
            break
    if base is None:
        return None
    inicio, fin, valor = base
    for j in posiciones[:_MAX_INTENTOS_BRACKET]:
        if j >= inicio:
            break
        try:
            envoltorio, fin_env = dec.raw_decode(s, j)
        except ValueError:
            continue
        if fin_env >= fin and isinstance(envoltorio, (dict, list)):
            return envoltorio
    return valor


def _candidatos(texto: str) -> Iterator[Any]:
    """Valores JSON candidatos de la salida, en orden de preferencia (puede no rendir ninguno)."""
    if not isinstance(texto, str) or not texto.strip():
        return
    s = texto.strip()
    try:
        yield json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass
    cercados = [c.strip() for c in _RE_FENCE.findall(s) if c.strip()]
    for crudo in reversed(cercados):
        try:
            yield json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            continue
    valor = _desde_brackets(s)
    if valor is not None:
        yield valor


def extraer_json(
    texto: str, esperado: type | tuple[type, ...] = (dict, list)
) -> Any | None:
    """Primer JSON de la salida del modelo cuyo tipo case con `esperado`. None si no hay."""
    for data in _candidatos(texto):
        if isinstance(data, esperado):
            return data
    return None


def extraer_lista(texto: str, claves: tuple[str, ...] = ()) -> list[Any] | None:
    """Lista JSON de la salida del modelo: cruda o bajo una de `claves` de un dict envoltorio.

    Recorre los candidatos (directo → último fence → brackets) hasta dar con una lista; un
    candidato dict sin ninguna de las `claves` (con valor lista) se descarta y se sigue con el
    siguiente. None si nada produce una lista.
    """
    for data in _candidatos(texto):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for clave in claves:
                if isinstance(data.get(clave), list):
                    return data[clave]
    return None


def truncar(valor: str, limite: int) -> tuple[str, bool]:
    """Recorta `valor` a `limite` caracteres. Devuelve `(valor, fue_truncado)`."""
    s = valor or ""
    if len(s) > limite:
        return s[:limite], True
    return s, False


def truncar_avisando(
    valor: str, limite: int, *, campo: str, log: logging.Logger | None = None
) -> tuple[str, bool]:
    """`truncar` que además deja un WARN con el campo y las longitudes si recortó."""
    recortado, fue = truncar(valor, limite)
    if fue:
        (log or _log).warning(
            "Campo «%s» truncado (%d→%d caracteres).", campo, len(valor or ""), limite
        )
    return recortado, fue

"""(De)serialización tolerante de columnas JSON (TEXT) de la capa de datos.

Varias columnas guardan estructuras (listas, dicts) como JSON en una columna TEXT.
La (de)serialización es *tolerante*: nunca lanza por datos ausentes o malformados;
ante un valor que no encaja devuelve el neutro vacío (`""` al serializar, `[]`/`{}`
al deserializar). Un `str` ya serializado pasa **tal cual** (passthrough), de modo que
un valor que ya viene en su forma de columna no se re-serializa.

Estos cuatro helpers consolidan ~una docena de implementaciones byte-a-byte idénticas
repartidas por la capa `db_*` (noticias, comercial, hashtags/franjas, parrilla, métricas).
Semántica común y deliberada:

- Serializar: `json.dumps(..., ensure_ascii=False)` (no escapa el no-ASCII); `""` si el
  valor no es del tipo esperado o no es serializable.
- Deserializar: `json.loads(crudo or "<neutro>")`; el neutro vacío si está vacío, es
  malformado, o el JSON no decodifica al tipo esperado.

`de_json_lista` NO filtra elementos: devuelve la lista cruda y deja al llamante imponer
la forma de sus elementos (lista de dicts vs lista de strings), preservando así las dos
variantes que existían sin duplicar el parseo tolerante. NO usar en migraciones de
esquema (su forma serializada es sensible y se versiona aparte).
"""
from __future__ import annotations

import json
from typing import Any


def a_json_lista(valor: Any) -> str:
    """Serializa un valor-lista para una columna JSON (tolerante).

    - `list` -> JSON (`ensure_ascii=False`); `""` si no es serializable.
    - `str`  -> passthrough (se asume ya serializado).
    - resto  -> `""`.
    """
    if isinstance(valor, list):
        try:
            return json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return valor if isinstance(valor, str) else ""


def a_json_dict(valor: Any) -> str:
    """Serializa un valor-dict para una columna JSON (tolerante).

    - `dict` -> JSON (`ensure_ascii=False`); `""` si no es serializable.
    - `str`  -> passthrough (se asume ya serializado).
    - resto  -> `""`.
    """
    if isinstance(valor, dict):
        try:
            return json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return valor if isinstance(valor, str) else ""


def de_json_lista(crudo: Any) -> list[Any]:
    """Deserializa una columna JSON a lista; `[]` si vacía, malformada o no-lista.

    No filtra los elementos: el llamante decide la forma. Para una lista de dicts:
    `[d for d in de_json_lista(x) if isinstance(d, dict)]`; para una de strings:
    `[str(x) for x in de_json_lista(x)]`.
    """
    try:
        datos = json.loads(crudo or "[]")
    except (ValueError, TypeError):
        return []
    return datos if isinstance(datos, list) else []


def de_json_dict(crudo: Any) -> dict[str, Any]:
    """Deserializa una columna JSON a dict; `{}` si vacía, malformada o no-dict."""
    try:
        datos = json.loads(crudo or "{}")
    except (ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}

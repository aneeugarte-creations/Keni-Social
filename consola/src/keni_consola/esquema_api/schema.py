"""Emisor de JSON Schema (Draft 2020-12) desde los `TypedDict` del subconjunto.

Sin dependencias externas: introspecta los tipos con `typing.get_type_hints` y los
traduce a JSON Schema. Cubre EXACTAMENTE las formas usadas en `modelos.py`
(str/int/float/bool, `X | None`, `list[...]`, `dict[str, ...]`, `Literal[...]`,
y `TypedDict` anidados, opcionales con `NotRequired`). Si se introduce una forma
no soportada, falla en voz alta (`TypeError`) en vez de emitir algo incorrecto.

El esquema raiz usa `$defs` con un `$ref` por modelo (titulo = nombre del
TypedDict). `json-schema-to-typescript` consume esa forma y emite una `interface`
por cada `$def`, conservando los nombres tal cual.

`additionalProperties: false` se omite a proposito: las respuestas reales del
backend pueden ganar campos nuevos (p. ej. `fuente` se anadio despues); el
contrato describe lo que el frontend CONSUME, no prohibe extras. El guard compara
el TS GENERADO contra el comiteado, asi que cualquier cambio de forma se detecta.
"""

from __future__ import annotations

import types
import typing
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from .modelos import MODELOS

# Origen de `Literal` (es un objeto especial; se compara por identidad).
_LITERAL_ORIGIN = get_origin(Literal["x"])

# Tipos primitivos Python -> JSON Schema.
_PRIMITIVOS: dict[type, dict[str, str]] = {
    str: {"type": "string"},
    bool: {"type": "boolean"},
    int: {"type": "integer"},
    float: {"type": "number"},
}


def _es_typeddict(tp: Any) -> bool:
    """True si `tp` es una clase `TypedDict` (tiene `__annotations__` y marca)."""
    return isinstance(tp, type) and hasattr(tp, "__annotations__") and hasattr(tp, "__required_keys__")


def _desenvolver_no_requerido(tp: Any) -> tuple[Any, bool]:
    """Quita `NotRequired[X]`/`Required[X]`; devuelve `(X, es_opcional)`."""
    origen = get_origin(tp)
    if origen is typing.NotRequired:
        return get_args(tp)[0], True
    if origen is typing.Required:
        return get_args(tp)[0], False
    return tp, False


def _esquema_de_tipo(tp: Any) -> dict[str, Any]:
    """Traduce una anotacion de tipo a un fragmento de JSON Schema."""
    # Primitivos directos.
    if tp in _PRIMITIVOS:
        return dict(_PRIMITIVOS[tp])

    if tp is type(None):
        return {"type": "null"}

    origen = get_origin(tp)

    # Literal[...] -> enum de sus valores.
    if origen is _LITERAL_ORIGIN:
        return {"enum": list(get_args(tp))}

    # Uniones: `X | None` (PEP 604) y `Union[...]`. Se modela como anyOf; un
    # `None` entre los miembros se traduce a `{"type": "null"}`.
    if origen in (Union, types.UnionType):
        miembros = [_esquema_de_tipo(a) for a in get_args(tp)]
        return {"anyOf": miembros}

    # list[...] -> array; sin args -> items libres.
    if origen in (list, typing.List):  # noqa: UP006
        args = get_args(tp)
        items = _esquema_de_tipo(args[0]) if args else {}
        return {"type": "array", "items": items}

    # dict[str, V] -> object con additionalProperties = esquema de V.
    if origen in (dict, typing.Dict):  # noqa: UP006
        args = get_args(tp)
        valor = _esquema_de_tipo(args[1]) if len(args) == 2 else {}
        return {"type": "object", "additionalProperties": valor}

    # TypedDict anidado -> referencia a su $def.
    if _es_typeddict(tp):
        return {"$ref": f"#/$defs/{tp.__name__}"}

    raise TypeError(
        f"Tipo no soportado por el emisor de esquema: {tp!r}. "
        "Anade su traduccion en esquema_api/schema.py si lo necesitas."
    )


def _esquema_de_typeddict(modelo: type) -> dict[str, Any]:
    """JSON Schema (objeto) de un `TypedDict`: propiedades + requeridos."""
    pistas = get_type_hints(modelo, include_extras=True)
    propiedades: dict[str, Any] = {}
    requeridos: list[str] = []
    # `__required_keys__` ya refleja `total=`; combinamos con `NotRequired`.
    opcionales_marca = set(getattr(modelo, "__optional_keys__", set()))

    for nombre, anotacion in pistas.items():
        tipo, no_requerido = _desenvolver_no_requerido(anotacion)
        propiedades[nombre] = _esquema_de_tipo(tipo)
        if not no_requerido and nombre not in opcionales_marca:
            requeridos.append(nombre)

    esquema: dict[str, Any] = {
        "type": "object",
        "title": modelo.__name__,
        "properties": propiedades,
    }
    if modelo.__doc__:
        esquema["description"] = modelo.__doc__.strip()
    if requeridos:
        esquema["required"] = requeridos
    return esquema


def esquema_json() -> dict[str, Any]:
    """JSON Schema raiz del subconjunto: un `$def` por modelo en `MODELOS`.

    La raiz referencia todos los modelos via `oneOf` para que el generador de TS
    visite cada `$def` y emita su `interface`. El orden de `$defs` sigue `MODELOS`.
    """
    defs: dict[str, Any] = {}
    for modelo in MODELOS:
        defs[modelo.__name__] = _esquema_de_typeddict(modelo)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ContratoApiKeni",
        "$comment": (
            "Generado desde keni_consola.esquema_api. NO editar a mano. "
            "Subconjunto estable del contrato /api/* (#101)."
        ),
        "$defs": defs,
        # Referencia a todos los modelos para que el generador emita cada interface.
        "anyOf": [{"$ref": f"#/$defs/{m.__name__}"} for m in MODELOS],
    }

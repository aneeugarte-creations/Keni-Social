"""Helpers compartidos por los modulos del paquete `_db_core` (sin estado de entidad).

Funciones puras de inspeccion de esquema (`information_schema`) y parsing de horas/franjas
que usan tanto las migraciones de columnas como las de modelo, y el logger del paquete. Hoja
del grafo de imports del paquete (solo stdlib). Extraido de `_db_core.py` al trocearlo por
areas (refactor de pura reubicacion; sin cambio de comportamiento).
"""
from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger("keni_consola.db")


def _columnas_existentes(con: Any, tabla: str) -> set[str]:
    """Nombres de columnas que YA tiene `tabla` (Postgres, via `information_schema`).

    `tabla` es SIEMPRE un nombre interno de una allowlist (constantes del modulo, nunca
    entrada de usuario). El placeholder `?` lo traduce `motor_db` a `%s`.
    """
    filas = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        (tabla,),
    ).fetchall()
    return {fila["column_name"] for fila in filas}


def _tabla_existe(con: Any, tabla: str) -> bool:
    """True si `tabla` existe en el esquema actual (Postgres, `information_schema.tables`)."""
    fila = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1",
        (tabla,),
    ).fetchone()
    return fila is not None


def _parsear_lista_franjas(crudo: Any) -> list[dict[str, str]]:
    """Parsea el JSON de `rota_config_franjas.franjas` a `[{nombre,inicio,fin}, ...]`.

    Tolerante: devuelve `[]` si el valor esta vacio, no es una lista o trae basura (filas sin
    nombre/inicio/fin se descartan). No lanza: lo usan tanto las migraciones como la lectura.
    """
    if not crudo:
        return []
    try:
        datos = json.loads(crudo)
    except (TypeError, ValueError):
        return []
    if not isinstance(datos, list):
        return []
    salida: list[dict[str, str]] = []
    for item in datos:
        if not isinstance(item, dict):
            continue
        nombre = str(item.get("nombre", "")).strip()
        inicio = str(item.get("inicio", "")).strip()
        fin = str(item.get("fin", "")).strip()
        if nombre and inicio and fin:
            salida.append({"nombre": nombre, "inicio": inicio, "fin": fin})
    return salida


def resolver_franjas_plantilla(
    franjas_json: Any,
    matutino_inicio: str,
    matutino_fin: str,
    vespertino_inicio: str,
    vespertino_fin: str,
    *,
    nombre_manana: str,
    nombre_tarde: str,
) -> list[dict[str, str]]:
    """Lista de franjas-plantilla `[{nombre,inicio,fin}, ...]` para sembrar una semana nueva.

    Fuente de verdad: la columna JSON `franjas`. Si esta vacia (fila previa a la columna, o
    marca que nunca edito su plantilla con el editor de lista) se DERIVA de las columnas
    legadas matutino/vespertino, asi una marca con rangos personalizados los conserva. La
    franja "Descanso" NO va aqui: la anade SIEMPRE la siembra de la semana.
    """
    lista = _parsear_lista_franjas(franjas_json)
    if lista:
        return lista
    return [
        {"nombre": nombre_manana, "inicio": matutino_inicio, "fin": matutino_fin},
        {"nombre": nombre_tarde, "inicio": vespertino_inicio, "fin": vespertino_fin},
    ]


def _parsear_hora_a_minutos(crudo: str) -> int | None:
    """Convierte `HH:MM` (o un rango `HH:MM-HH:MM` del Excel) a minutos. None si malformado.

    Acepta sufijos del Excel real ("16:00-18:00", "16:00–18:00"): se queda con la hora de
    inicio. No lanza: la migracion debe ser tolerante con datos viejos sucios.
    """
    if not isinstance(crudo, str) or not crudo.strip():
        return None
    parte = crudo.strip().replace("–", "-").split("-", 1)[0].strip()
    partes = parte.split(":")
    if len(partes) < 2:
        return None
    try:
        h = int(partes[0])
        m = int(partes[1])
    except ValueError:
        return None
    if not (0 <= h <= 24 and 0 <= m <= 59):
        return None
    if h == 24 and m != 0:
        return None
    return h * 60 + m


def _franja_para_hora_migracion(
    hora: str, *, mat_ini: int, mat_fin: int, ves_ini: int, ves_fin: int
) -> str:
    """Mapea una hora a su franja usando rangos en MINUTOS. `descanso` si no encaja o malformado.

    Replica `rota.mapear_franja` sin tirar de el (para no introducir dep ciclica desde db.py).
    """
    minutos = _parsear_hora_a_minutos(hora)
    if minutos is None:
        return "descanso"
    if mat_ini <= minutos < mat_fin:
        return "matutino"
    if ves_ini <= minutos < ves_fin:
        return "vespertino"
    return "descanso"

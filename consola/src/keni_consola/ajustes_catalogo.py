"""Catalogo DECLARATIVO de ajustes editables (la fuente de verdad para la API admin).

Cada ajuste enlaza una env var `KENI_*` (su `clave`) con su tipo, etiqueta/ayuda para la UI,
grupo, si es peligroso, su valor por defecto y, segun el tipo, sus opciones (select) o sus
cotas (int/float). La API admin (`api/ajustes.py`) usa este catalogo para:
  - PINTAR el formulario (un dict por ajuste con su valor EFECTIVO + de donde viene).
  - VALIDAR lo que escribe el admin (`validar_valor`) antes de persistirlo en el store.
  - ACOTAR las claves escribibles: SOLO se guardan claves del catalogo; el resto del codigo
    sigue cayendo a env como hasta hoy (precedencia STORE > ENV > DEFECTO en `config._crudo`).

El VALOR efectivo y su FUENTE se calculan con la misma precedencia que `config._crudo`:
store (UI) > env > defecto del catalogo. NO importamos `config` aqui (los accesores numericos
de `config` ya aplican sus propios minimos/defaults); leemos el store via `ajustes.obtener` y
el entorno via `os.environ` directamente para reportar la fuente con fidelidad.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from . import ajustes, config, marcas

# Conjuntos de verdad/falsedad para flags (mismos que `config`, fuente del parseo de bool).
_VERDADEROS = frozenset({"1", "true", "yes", "si", "sí", "on"})
_FALSOS = frozenset({"0", "false", "no", "off", ""})

# Titulos humanos de cada grupo (orden estable del contrato GET /api/ajustes).
GRUPOS: tuple[tuple[str, str], ...] = (
    ("automatizacion", "Automatización"),
    ("tuning", "Ajustes finos"),
    ("publicacion", "Publicación"),
)


@dataclass(frozen=True)
class Ajuste:
    """Un ajuste editable del catalogo (declarativo)."""

    clave: str
    tipo: str  # 'bool' | 'int' | 'float' | 'select'
    etiqueta: str
    ayuda: str
    grupo: str  # 'automatizacion' | 'tuning' | 'publicacion'
    defecto: Any
    peligroso: bool = False
    opciones: tuple[dict[str, str], ...] = ()  # solo 'select': [{id, etiqueta}, ...]
    minimo: float | None = None  # solo int/float
    maximo: float | None = None  # solo int/float


def _opciones_radar_marca() -> tuple[dict[str, str], ...]:
    """Opciones del select de marca del Radar: `(ninguna)` + las marcas del catalogo."""
    items = [{"id": "", "etiqueta": "(ninguna)"}]
    items.extend({"id": mid, "etiqueta": etiqueta} for mid, etiqueta in marcas.opciones())
    return tuple(items)


_GEO_OPCIONES: tuple[dict[str, str], ...] = (
    {"id": "MX", "etiqueta": "México"},
    {"id": "US", "etiqueta": "Estados Unidos"},
    {"id": "ES", "etiqueta": "España"},
    {"id": "AR", "etiqueta": "Argentina"},
    {"id": "CO", "etiqueta": "Colombia"},
    {"id": "CL", "etiqueta": "Chile"},
)


def _construir_catalogo() -> list[Ajuste]:
    """Construye la lista de ajustes editables. Se llama en cada `catalogo()` (las opciones
    de marca dependen del catalogo de marcas, que es estable pero se resuelve en caliente)."""
    return [
        # --- Automatizacion (flags) ------------------------------------------------ #
        Ajuste(
            clave=config.ENV_AUTOGEN,
            tipo="bool",
            etiqueta="Auto-generar copy",
            ayuda="Genera copy automáticamente para los temas del tablero alimentados por "
            "fuentes que aún no tienen copy.",
            grupo="automatizacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_ARTE,
            tipo="bool",
            etiqueta="Auto-generar arte",
            ayuda="Genera imagen por IA para los temas con copy pero sin imagen y la adjunta. "
            "Requiere proveedor de imagen configurado.",
            grupo="automatizacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_RADAR_AUTO,
            tipo="bool",
            etiqueta="Radar automático",
            ayuda="Promueve periódicamente los temas del Radar que superan el umbral de señal "
            "a 'lo importante del día'.",
            grupo="automatizacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_ALERTAS_ACTIVAS,
            tipo="bool",
            etiqueta="Alertas de rendimiento",
            ayuda="Barrido que emite alertas cuando una pieza publicada rinde por debajo del umbral de engagement.",
            grupo="automatizacion",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_EVENTOS_VENCIMIENTOS,
            tipo="bool",
            etiqueta="Eventos de vencimientos",
            ayuda="Barrido que detecta contenido vencido en el tablero y dispara los eventos "
            "internos correspondientes.",
            grupo="automatizacion",
            defecto=True,
        ),
        Ajuste(
            clave=config.ENV_AUTO_PREAPROBACION,
            tipo="bool",
            etiqueta="Pre-aprobación de bajo riesgo",
            ayuda="Auto-aprueba los niveles inferiores de la cadena de aprobación para piezas "
            "de bajo riesgo (el último nivel siempre queda a un humano).",
            grupo="automatizacion",
            defecto=False,
        ),
        Ajuste(
            clave=config.ENV_MEDIA_GC,
            tipo="bool",
            etiqueta="Limpieza de media huérfana",
            ayuda="Borra periódicamente los objetos de imagen del Estudio que ninguna "
            "publicación usa y son más viejos que el umbral de antigüedad.",
            grupo="automatizacion",
            defecto=False,
        ),
        # --- Publicacion (peligroso) ----------------------------------------------- #
        Ajuste(
            clave=config.ENV_PUBLICAR_REAL,
            tipo="bool",
            etiqueta="Publicación real",
            ayuda="¡Cuidado! Si se activa, el sistema envía las piezas programadas al scheduler "
            "real de Metricool. Sin esto opera en dry-run.",
            grupo="publicacion",
            defecto=False,
            peligroso=True,
        ),
        # --- Tuning (int/float/select) --------------------------------------------- #
        Ajuste(
            clave=config.ENV_AUTOGEN_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Auto-copy: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de auto-generación de copy.",
            grupo="tuning",
            defecto=config.AUTOGEN_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_MAX,
            tipo="int",
            etiqueta="Auto-copy: máximo por barrido",
            ayuda="Máximo de temas a auto-generar por barrido (cada uno lanza una generación).",
            grupo="tuning",
            defecto=config.AUTOGEN_MAX_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_ARTE_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Auto-arte: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de auto-generación de arte.",
            grupo="tuning",
            defecto=config.AUTOGEN_ARTE_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_AUTOGEN_ARTE_MAX,
            tipo="int",
            etiqueta="Auto-arte: máximo por barrido",
            ayuda="Máximo de temas a auto-ilustrar por barrido (cada uno llama al proveedor de imagen).",
            grupo="tuning",
            defecto=config.AUTOGEN_ARTE_MAX_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_RADAR_AUTO_UMBRAL,
            tipo="int",
            etiqueta="Radar: umbral de señal",
            ayuda="Señal mínima de un tema para que el Radar lo auto-promueva. Alto = solo lo muy viral entra solo.",
            grupo="tuning",
            defecto=config.RADAR_AUTO_UMBRAL_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_RADAR_AUTO_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Radar: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de auto-promoción del Radar.",
            grupo="tuning",
            defecto=config.RADAR_AUTO_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_RADAR_AUTO_MAX,
            tipo="int",
            etiqueta="Radar: máximo por barrido",
            ayuda="Máximo de temas a auto-promover por barrido (los de mayor señal).",
            grupo="tuning",
            defecto=config.RADAR_AUTO_MAX_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_RADAR_AUTO_GEO,
            tipo="select",
            etiqueta="Radar: geografía",
            ayuda="País del Radar de tendencias para la auto-promoción.",
            grupo="tuning",
            defecto=config.RADAR_AUTO_GEO_DEF,
            opciones=_GEO_OPCIONES,
        ),
        Ajuste(
            clave=config.ENV_RADAR_AUTO_MARCA,
            tipo="select",
            etiqueta="Radar: marca por defecto",
            ayuda="Marca a asignar a las piezas auto-promovidas por el Radar. '(ninguna)' deja "
            "que el equipo la asigne luego.",
            grupo="tuning",
            defecto="",
            opciones=_opciones_radar_marca(),
        ),
        Ajuste(
            clave=config.ENV_ALERTAS_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Alertas: intervalo (horas)",
            ayuda="Cada cuántas horas corre el barrido de alertas de rendimiento.",
            grupo="tuning",
            defecto=config.ALERTAS_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_ALERTAS_UMBRAL_ENGAGEMENT,
            tipo="float",
            etiqueta="Alertas: umbral de engagement (%)",
            ayuda="Engagement (%) por debajo del cual una pieza publicada dispara una alerta de bajo rendimiento.",
            grupo="tuning",
            defecto=config.ALERTAS_UMBRAL_ENGAGEMENT_DEF,
            minimo=0,
        ),
        Ajuste(
            clave=config.ENV_MAX_JOBS,
            tipo="int",
            etiqueta="Jobs simultáneos",
            ayuda="Máximo de generaciones `claude` ejecutándose a la vez.",
            grupo="tuning",
            defecto=config.MAX_JOBS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_MEDIA_GC_INTERVALO_HORAS,
            tipo="int",
            etiqueta="Limpieza media: intervalo (horas)",
            ayuda="Cada cuántas horas barre el daemon de limpieza de media huérfana.",
            grupo="tuning",
            defecto=config.MEDIA_GC_INTERVALO_HORAS_DEF,
            minimo=1,
        ),
        Ajuste(
            clave=config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
            tipo="int",
            etiqueta="Limpieza media: antigüedad mínima (horas)",
            ayuda="Un objeto de media más nuevo que esto nunca se borra, aunque parezca "
            "huérfano (protege las variantes del Estudio que aún se revisan).",
            grupo="tuning",
            defecto=config.MEDIA_GC_ANTIGUEDAD_HORAS_DEF,
            minimo=1,
        ),
    ]


def catalogo() -> list[Ajuste]:
    """Lista completa de ajustes editables (la fuente de verdad)."""
    return _construir_catalogo()


def por_clave(clave: str) -> Ajuste | None:
    """Ajuste del catalogo con esa `clave` (= nombre ENV), o None si no es editable."""
    for ajuste in catalogo():
        if ajuste.clave == clave:
            return ajuste
    return None


# --------------------------------------------------------------------------- #
# Casteo / validacion por tipo                                                #
# --------------------------------------------------------------------------- #


def _castea(ajuste: Ajuste, crudo: str) -> Any:
    """Castea un valor CRUDO (str) al tipo del ajuste. Tolerante: ante un crudo invalido
    cae al `defecto` del ajuste (mismo espiritu que los accesores de `config`)."""
    if ajuste.tipo == "bool":
        return crudo.strip().lower() in _VERDADEROS
    if ajuste.tipo == "int":
        try:
            valor = int(crudo)
        except (TypeError, ValueError):
            return ajuste.defecto
        if ajuste.minimo is not None and valor < ajuste.minimo:
            return int(ajuste.minimo)
        if ajuste.maximo is not None and valor > ajuste.maximo:
            return int(ajuste.maximo)
        return valor
    if ajuste.tipo == "float":
        try:
            valor = float(crudo)
        except (TypeError, ValueError):
            return ajuste.defecto
        if ajuste.minimo is not None and valor < ajuste.minimo:
            return float(ajuste.minimo)
        if ajuste.maximo is not None and valor > ajuste.maximo:
            return float(ajuste.maximo)
        return valor
    # select: el id se reporta tal cual (mayusculas para geo, igual que `config.radar_auto_geo`)
    valor = crudo.strip()
    if ajuste.clave == config.ENV_RADAR_AUTO_GEO:
        valor = valor.upper()
    ids = {o["id"] for o in ajuste.opciones}
    return valor if valor in ids else ajuste.defecto


def valor_y_fuente(ajuste: Ajuste) -> tuple[Any, str]:
    """Valor EFECTIVO (tipado) + su FUENTE ('store' | 'env' | 'defecto').

    Misma precedencia que `config._crudo`: store (UI) > env > defecto del catalogo.
    """
    desde_store = ajustes.obtener(ajuste.clave)
    if desde_store is not None:
        return _castea(ajuste, desde_store), "store"
    desde_env = os.environ.get(ajuste.clave)
    if desde_env is not None and desde_env.strip() != "":
        return _castea(ajuste, desde_env), "env"
    return ajuste.defecto, "defecto"


def a_dict(ajuste: Ajuste) -> dict[str, Any]:
    """Serializa un ajuste a su dict de API (con valor efectivo + fuente).

    Forma EXACTA del contrato con el frontend: `clave, tipo, etiqueta, ayuda, grupo,
    peligroso, valor (tipado), fuente, defecto (tipado)`, y solo cuando aplica `opciones`
    (select) y `min`/`max` (int/float).
    """
    valor, fuente = valor_y_fuente(ajuste)
    salida: dict[str, Any] = {
        "clave": ajuste.clave,
        "tipo": ajuste.tipo,
        "etiqueta": ajuste.etiqueta,
        "ayuda": ajuste.ayuda,
        "grupo": ajuste.grupo,
        "peligroso": ajuste.peligroso,
        "valor": valor,
        "fuente": fuente,
        "defecto": ajuste.defecto,
    }
    if ajuste.tipo == "select":
        salida["opciones"] = [dict(o) for o in ajuste.opciones]
    if ajuste.minimo is not None:
        salida["min"] = ajuste.minimo
    if ajuste.maximo is not None:
        salida["max"] = ajuste.maximo
    return salida


def validar_valor(ajuste: Ajuste, valor: Any) -> tuple[str | None, str | None]:
    """Valida/castea `valor` (del body de la API) y devuelve `(str_a_guardar, error)`.

    Exactamente uno de los dos es None: en exito `(str, None)`, en error `(None, mensaje)`.
    El string devuelto es lo que se persiste en el store (formato env-like).

    Reglas por tipo:
      - bool: acepta true/false (json) o "1"/"0"/"true"/"false"/... (texto). Guarda "1"/"0".
      - int: entero (o str numerico); respeta min/max -> error si fuera de rango.
      - float: numero (o str numerico); respeta min/max -> error si fuera de rango.
      - select: el id debe estar en `opciones` (geo se normaliza a mayusculas). Guarda el id.
    """
    if ajuste.tipo == "bool":
        if isinstance(valor, bool):
            return ("1" if valor else "0"), None
        if isinstance(valor, (int, float)) and valor in (0, 1):
            return ("1" if valor else "0"), None
        if isinstance(valor, str):
            v = valor.strip().lower()
            if v in _VERDADEROS:
                return "1", None
            if v in _FALSOS:
                return "0", None
        return None, f"'{ajuste.clave}' espera un valor booleano (true/false)."

    if ajuste.tipo == "int":
        if isinstance(valor, bool):  # bool es subtipo de int: rechazar explicito
            return None, f"'{ajuste.clave}' espera un número entero."
        try:
            n = int(valor) if not isinstance(valor, str) else int(valor.strip())
        except (TypeError, ValueError):
            return None, f"'{ajuste.clave}' espera un número entero."
        if ajuste.minimo is not None and n < ajuste.minimo:
            return None, f"'{ajuste.clave}' debe ser ≥ {int(ajuste.minimo)}."
        if ajuste.maximo is not None and n > ajuste.maximo:
            return None, f"'{ajuste.clave}' debe ser ≤ {int(ajuste.maximo)}."
        return str(n), None

    if ajuste.tipo == "float":
        if isinstance(valor, bool):
            return None, f"'{ajuste.clave}' espera un número."
        try:
            n = float(valor) if not isinstance(valor, str) else float(valor.strip())
        except (TypeError, ValueError):
            return None, f"'{ajuste.clave}' espera un número."
        if ajuste.minimo is not None and n < ajuste.minimo:
            return None, f"'{ajuste.clave}' debe ser ≥ {ajuste.minimo}."
        if ajuste.maximo is not None and n > ajuste.maximo:
            return None, f"'{ajuste.clave}' debe ser ≤ {ajuste.maximo}."
        return repr(n), None

    # select
    if not isinstance(valor, str):
        return None, f"'{ajuste.clave}' espera uno de los valores permitidos."
    v = valor.strip()
    if ajuste.clave == config.ENV_RADAR_AUTO_GEO:
        v = v.upper()
    ids = {o["id"] for o in ajuste.opciones}
    if v not in ids:
        permitidos = ", ".join(repr(o["id"]) for o in ajuste.opciones)
        return None, f"'{ajuste.clave}' debe ser uno de: {permitidos}."
    return v, None

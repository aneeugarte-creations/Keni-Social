"""Configuracion LOCAL del Termometro mundial (no secreta).

El Termometro mundial es el posteo de GALERIA diario con las 5-8 noticias
internacionales mas importantes (una por region). Esta config guarda las
PREFERENCIAS que comparten la pagina de la consola y el cron de las 7:00:

  - `numero`   cuantos slides de noticia (entre 5 y 8; def. 8).
  - `regiones` regiones a cubrir (texto libre, CSV; vacio = reparto por defecto).
  - `hora`     hora de la generacion programada ("HH:MM", 24h; def. "07:00").
  - `marca`    marca para la que se arma (id canonico de `marcas`; "" = sin fijar).

El archivo vive en `~/.config/keni-social/termometro.json` (o la ruta de
`KENI_CONSOLA_TERMOMETRO`, util en tests). Escritura ATOMICA (temp + os.replace),
mismo patron defensivo que `preferencias.py`/`sugerencias.py`. NO contiene secretos.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from . import marcas

# Limites del numero de slides de noticia (mas la portada). Coinciden con la skill.
NUMERO_MIN = 5
NUMERO_MAX = 8
NUMERO_DEFECTO = 8

# Hora por defecto de la generacion programada (24h, "HH:MM").
HORA_DEFECTO = "07:00"

# Tope de longitud del texto de regiones (defensa frente a entradas gigantes).
_MAX_REGIONES = 2000

# "HH:MM" en formato 24h (00:00 - 23:59).
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def ruta() -> Path:
    """Ruta del archivo de config. `KENI_CONSOLA_TERMOMETRO` la sobreescribe (tests)."""
    if (p := os.environ.get("KENI_CONSOLA_TERMOMETRO")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "termometro.json"


def defectos() -> dict[str, Any]:
    """Config por defecto (todo a sus valores base; sin marca fijada)."""
    return {"numero": NUMERO_DEFECTO, "regiones": "", "hora": HORA_DEFECTO, "marca": ""}


def _leer() -> dict[str, Any]:
    """Lee el JSON de config (o {} si no existe / esta corrupto). Solo lectura."""
    archivo = ruta()
    if not archivo.exists():
        return {}
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _escribir(datos: dict[str, Any]) -> None:
    """Escribe la config como JSON de forma atomica (temp + os.replace)."""
    archivo = ruta()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, tmp_nombre = tempfile.mkstemp(dir=str(archivo.parent), prefix=".termometro-", suffix=".json.tmp")
    tmp = Path(tmp_nombre)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(contenido)
        os.replace(tmp, archivo)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class TermometroConfigError(ValueError):
    """Valor de config invalido, con mensaje ya en espanol para mostrar al usuario."""


def _numero_valido(valor: Any) -> int:
    """Normaliza `numero` a un entero acotado a [NUMERO_MIN, NUMERO_MAX]."""
    if isinstance(valor, bool):
        raise TermometroConfigError("El número de slides debe ser un número entre 5 y 8.")
    if isinstance(valor, str):
        valor = valor.strip()
        if not valor:
            return NUMERO_DEFECTO
        try:
            valor = int(valor)
        except ValueError as e:
            raise TermometroConfigError("El número de slides debe ser un número entre 5 y 8.") from e
    if not isinstance(valor, int):
        raise TermometroConfigError("El número de slides debe ser un número entre 5 y 8.")
    if valor < NUMERO_MIN or valor > NUMERO_MAX:
        raise TermometroConfigError(f"El número de slides debe estar entre {NUMERO_MIN} y {NUMERO_MAX}.")
    return valor


def _hora_valida(valor: Any) -> str:
    """Normaliza/valida `hora` a "HH:MM" (24h)."""
    if not isinstance(valor, str) or not _RE_HORA.match(valor.strip()):
        raise TermometroConfigError("La hora debe tener el formato HH:MM (24 horas), por ejemplo 07:00.")
    return valor.strip()


def _marca_valida(valor: Any) -> str:
    """Normaliza/valida `marca` (id canonico o "" para sin fijar)."""
    if valor in (None, ""):
        return ""
    if not isinstance(valor, str) or not marcas.es_marca(valor):
        raise TermometroConfigError("Marca no permitida.")
    return valor


def _regiones_validas(valor: Any) -> str:
    """Normaliza `regiones` a texto recortado (CSV libre)."""
    if valor in (None, ""):
        return ""
    if not isinstance(valor, str):
        raise TermometroConfigError("Las regiones deben ser texto separado por comas.")
    texto = valor.strip()
    if len(texto) > _MAX_REGIONES:
        raise TermometroConfigError("El texto de regiones es demasiado largo.")
    return texto


def obtener() -> dict[str, Any]:
    """Config actual con los defectos aplicados y normalizada (tolerante a valores raros)."""
    crudo = _leer()
    base = defectos()
    try:
        base["numero"] = _numero_valido(crudo.get("numero", base["numero"]))
    except TermometroConfigError:
        pass
    try:
        base["hora"] = _hora_valida(crudo.get("hora", base["hora"]))
    except TermometroConfigError:
        pass
    try:
        base["regiones"] = _regiones_validas(crudo.get("regiones", base["regiones"]))
    except TermometroConfigError:
        pass
    try:
        base["marca"] = _marca_valida(crudo.get("marca", base["marca"]))
    except TermometroConfigError:
        pass
    return base


def guardar(cambios: dict[str, Any]) -> dict[str, Any]:
    """Valida y mezcla `cambios` sobre la config actual (escritura atomica). Devuelve la config.

    Solo se tocan las claves presentes en `cambios`. Lanza `TermometroConfigError`
    (=> 400 en la API) si algun valor presente no es valido.
    """
    if not isinstance(cambios, dict):
        raise TermometroConfigError("La configuración del termómetro no es válida.")
    config = obtener()
    if "numero" in cambios:
        config["numero"] = _numero_valido(cambios["numero"])
    if "hora" in cambios:
        config["hora"] = _hora_valida(cambios["hora"])
    if "regiones" in cambios:
        config["regiones"] = _regiones_validas(cambios["regiones"])
    if "marca" in cambios:
        config["marca"] = _marca_valida(cambios["marca"])
    _escribir(config)
    return config

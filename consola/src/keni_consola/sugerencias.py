"""Buzón de sugerencias LOCAL de la Consola Keni.

Almacén sencillo y autónomo para que el equipo deje ideas y mejoras del producto
sin salir de la consola. NO usa la capa `repos`/`db` (no necesita el doble backend
ni migraciones): vive en su propio JSON, igual de local y privado que
`preferencias.py` y `secretos.py`.

El archivo vive en `~/.config/keni-social/sugerencias.json` (o la ruta de
`KENI_CONSOLA_SUGERENCIAS`, útil en tests). Escritura ATÓMICA (temp + os.replace).
NO contiene secretos.

La PRIMERA vez que se lee (archivo inexistente) se SIEMBRA con una idea de partida
(moderación de lives de YouTube como herramienta aparte). Borrar todas las
sugerencias deja el archivo con lista vacía y NO vuelve a sembrar.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config, rutas
from .io_atomico import bloqueo_archivo, escribir_atomico

# Categorías y estados válidos (la UI los pinta con etiquetas legibles).
CATEGORIAS: tuple[str, ...] = ("idea", "producto", "mejora", "bug")
ESTADOS: tuple[str, ...] = ("nueva", "en-estudio", "hecha", "descartada")

CATEGORIA_DEFECTO = "idea"
ESTADO_DEFECTO = "nueva"

# Topes defensivos de longitud (evitan archivos enormes; el front también limita).
_MAX_TITULO = 200
_MAX_DETALLE = 8000
_MAX_AUTOR = 120

# Idea de partida: la moderación de lives de YouTube, planteada como producto
# APARTE de keni-social (que es gestión de redes con LLM, menos específica).
_SEMILLA: list[dict[str, Any]] = [
    {
        "id": "semilla-moderacion-youtube",
        "titulo": "Moderador de lives de YouTube (herramienta aparte)",
        "detalle": (
            "Idea surgida en la demo de AMX (Fundación, evento **México Siglo XXI**): "
            "un **moderador en vivo** del chat de YouTube que detecte groserías, spam/bots "
            "y separe las **preguntas legítimas** (becas, sillas de ruedas, inscripciones) "
            "para responderlas.\n\n"
            "**Decisión:** NO encaja dentro de keni-social, que es una suite de **gestión de "
            "redes con LLM** (menos específica). La moderación de directos debería ser una "
            "herramienta **estándar, independiente y diseñada para lives de YouTube**: API "
            "real (`liveChatMessages`, bans), OAuth del canal y ampliación de cuota, en su "
            "propio repo.\n\n"
            "Pendiente: validar alcance, fecha del evento y volumen pico para dimensionar cuota."
        ),
        "categoria": "producto",
        "estado": "nueva",
        "autor": "Demo AMX · Fundación",
        "creada": "2026-05-25T00:00:00",
    }
]


def ruta_sugerencias() -> Path:
    """Ruta del archivo de sugerencias.

    `KENI_CONSOLA_SUGERENCIAS` la sobreescribe (override de maxima prioridad; tests). Si
    no, cuelga de la raiz de estado unica (`rutas.dir_config()`): local
    `${XDG_CONFIG_HOME:-~/.config}/keni-social/sugerencias.json`, o bajo `KENI_DATA_DIR`.
    """
    if (p := config.override_ruta(config.ENV_SUGERENCIAS)) is not None:
        return p
    return rutas.dir_config() / "sugerencias.json"


# --------------------------------------------------------------------------- #
# Lectura / escritura del almacén                                             #
# --------------------------------------------------------------------------- #


def _normalizar(item: Any) -> dict[str, Any] | None:
    """Sanea un registro leído de disco; None si no es utilizable (sin id/título)."""
    if not isinstance(item, dict):
        return None
    sid = item.get("id")
    titulo = item.get("titulo")
    if not isinstance(sid, str) or not sid or not isinstance(titulo, str) or not titulo.strip():
        return None
    categoria = item.get("categoria")
    estado = item.get("estado")
    return {
        "id": sid,
        "titulo": titulo,
        "detalle": item.get("detalle") if isinstance(item.get("detalle"), str) else "",
        "categoria": categoria if categoria in CATEGORIAS else CATEGORIA_DEFECTO,
        "estado": estado if estado in ESTADOS else ESTADO_DEFECTO,
        "autor": item.get("autor") if isinstance(item.get("autor"), str) else "",
        "creada": item.get("creada") if isinstance(item.get("creada"), str) else "",
    }


def _leer() -> list[dict[str, Any]]:
    """Lee la lista del JSON (o `[]` si no existe / está corrupto). Solo lectura."""
    ruta = ruta_sugerencias()
    if not ruta.exists():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    crudas = datos.get("sugerencias") if isinstance(datos, dict) else datos
    if not isinstance(crudas, list):
        return []
    return [n for item in crudas if (n := _normalizar(item)) is not None]


def _escribir(lista: list[dict[str, Any]]) -> None:
    """Escribe la lista como JSON de forma atómica (temp + os.replace)."""
    contenido = json.dumps({"sugerencias": lista}, ensure_ascii=False, indent=2)
    escribir_atomico(
        ruta_sugerencias(), contenido, prefijo=".sugerencias-", sufijo=".json.tmp"
    )


# --------------------------------------------------------------------------- #
# API pública                                                                  #
# --------------------------------------------------------------------------- #


def listar() -> list[dict[str, Any]]:
    """Lista de sugerencias. La PRIMERA vez (sin archivo) siembra la idea de partida."""
    if not ruta_sugerencias().exists():
        semilla = [dict(s) for s in _SEMILLA]
        _escribir(semilla)
        return semilla
    return _leer()


def crear(
    titulo: str,
    detalle: str = "",
    categoria: str = CATEGORIA_DEFECTO,
    autor: str = "",
) -> dict[str, Any]:
    """Crea una sugerencia (al principio de la lista) y la persiste.

    Lanza `ValueError` si el título está vacío. Categoría inválida -> defecto.
    """
    titulo = (titulo or "").strip()[:_MAX_TITULO]
    if not titulo:
        raise ValueError("titulo")
    sugerencia = {
        "id": uuid.uuid4().hex[:12],
        "titulo": titulo,
        "detalle": (detalle or "").strip()[:_MAX_DETALLE],
        "categoria": categoria if categoria in CATEGORIAS else CATEGORIA_DEFECTO,
        "estado": ESTADO_DEFECTO,
        "autor": (autor or "").strip()[:_MAX_AUTOR],
        "creada": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with bloqueo_archivo(ruta_sugerencias()):
        lista = listar()
        lista.insert(0, sugerencia)
        _escribir(lista)
    return sugerencia


def actualizar_estado(sugerencia_id: str, estado: str) -> dict[str, Any] | None:
    """Cambia el estado de una sugerencia. None si no existe; `ValueError` si estado inválido."""
    if estado not in ESTADOS:
        raise ValueError("estado")
    with bloqueo_archivo(ruta_sugerencias()):
        lista = listar()
        for s in lista:
            if s["id"] == sugerencia_id:
                s["estado"] = estado
                _escribir(lista)
                return s
    return None


def borrar(sugerencia_id: str) -> bool:
    """Borra una sugerencia por id. True si existía. NO vuelve a sembrar al vaciarse."""
    with bloqueo_archivo(ruta_sugerencias()):
        lista = listar()
        restantes = [s for s in lista if s["id"] != sugerencia_id]
        if len(restantes) == len(lista):
            return False
        _escribir(restantes)
    return True

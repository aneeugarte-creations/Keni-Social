"""API del TABLERO de contenido unificado (herramienta de community manager).

Un item de `contenido` es el padre del tablero: lo IMPORTANTE del dia, contenido EVERGREEN,
cobertura de un EVENTO previsto, o una TAREA libre del equipo (relevo/recado). Cada contenido
publicable lleva N filas `contenido_plataforma` (una por red) con su propio estado y checklist
"falta copy / imagen / revision / publicar".

El tablero es UNICO y compartido (como Tareas): todo usuario autenticado lo ve y lo edita.

SEGURIDAD:
  - Multiusuario via middleware (sesion o token); `autor`/`responsable` se atribuyen al usuario.
  - `marca` debe ser del catalogo (`consola.marcas`); `red` una red canonica (`consola.redes`)
    o el canal extra "web". `evento_id`, si llega, debe existir en la rota. El RESPONSABLE
    solo puede ser un usuario REAL. Nada se confia del cliente.
  - SQL parametrizado en `repos`/`db` (nunca f-strings con datos).

================================================================================
ESTRUCTURA DEL PAQUETE (refactor sin cambio de comportamiento)

Este módulo era un único `contenido.py` (~1226 líneas); se partió en submódulos por
área funcional. El descubridor de `api/__init__.py` (`pkgutil.iter_modules`) NO
desciende dentro de subpaquetes, así que la ÚNICA superficie pública sigue siendo la
variable `RUTAS` que este `__init__` exporta (mismo orden/paths/métodos que antes).

  - `_comun.py`     : imports + helpers compartidos (red, serialización, validación
                      de marca/responsable, foco por marca, constantes, logger).
  - `tablero.py`    : listar, crear, actualizar, borrar (el padre del tablero).
  - `plataformas.py`: agregar/actualizar/borrar fila por red + adaptar_imagen.
  - `etiquetas.py`  : asignar/quitar etiqueta de un contenido.
  - `radar.py`      : desde_radar (promoción de un tema del Radar).
  - `metricas.py`   : metricas (rendimiento real por pieza).
  - `asistente.py`  : previsualizar (placeholders) + asistente_ia (copy IA).
  - `importar.py`   : importar (calendario tabular o IA al worker).
  - `aportar.py`    : aportar (puerta creativa del equipo).
================================================================================
"""

from __future__ import annotations

from starlette.routing import Route

from .aportar import aportar
from .asistente import asistente_ia, previsualizar
from .etiquetas import asignar_etiqueta, quitar_etiqueta
from .importar import importar
from .metricas import metricas
from .plataformas import (
    actualizar_plataforma,
    adaptar_imagen,
    agregar_plataforma,
    borrar_plataforma,
)
from .radar import desde_radar
from .tablero import actualizar, borrar, crear, listar

__all__ = [
    "RUTAS",
    "listar",
    "crear",
    "actualizar",
    "borrar",
    "metricas",
    "desde_radar",
    "aportar",
    "importar",
    "previsualizar",
    "asistente_ia",
    "adaptar_imagen",
    "agregar_plataforma",
    "actualizar_plataforma",
    "borrar_plataforma",
    "asignar_etiqueta",
    "quitar_etiqueta",
]


RUTAS = [
    Route("/api/contenido", listar, methods=["GET"]),
    Route("/api/contenido", crear, methods=["POST"]),
    Route("/api/contenido/metricas", metricas, methods=["GET"]),
    Route("/api/contenido/desde-radar", desde_radar, methods=["POST"]),
    Route("/api/contenido/aportar", aportar, methods=["POST"]),
    Route("/api/contenido/importar", importar, methods=["POST"]),
    Route("/api/contenido/{contenido_id}/preview", previsualizar, methods=["POST"]),
    Route("/api/contenido/{contenido_id}/asistente", asistente_ia, methods=["POST"]),
    Route("/api/contenido/{contenido_id}/adaptar-imagen", adaptar_imagen, methods=["POST"]),
    Route("/api/contenido/{contenido_id}", actualizar, methods=["PATCH"]),
    Route("/api/contenido/{contenido_id}", borrar, methods=["DELETE"]),
    Route("/api/contenido/{contenido_id}/plataformas", agregar_plataforma, methods=["POST"]),
    Route(
        "/api/contenido/{contenido_id}/plataformas/{plataforma_id}",
        actualizar_plataforma,
        methods=["PATCH"],
    ),
    Route(
        "/api/contenido/{contenido_id}/plataformas/{plataforma_id}",
        borrar_plataforma,
        methods=["DELETE"],
    ),
    Route("/api/contenido/{contenido_id}/etiquetas", asignar_etiqueta, methods=["POST"]),
    Route(
        "/api/contenido/{contenido_id}/etiquetas/{etiqueta_id}",
        quitar_etiqueta,
        methods=["DELETE"],
    ),
]

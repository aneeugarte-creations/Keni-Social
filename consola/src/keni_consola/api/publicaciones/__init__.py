"""API del TABLERO de contenido unificado (herramienta de community manager).

Un item de `contenido` es el padre del tablero: lo IMPORTANTE del dia, contenido EVERGREEN,
cobertura de un EVENTO previsto, o una TAREA libre del equipo (relevo/recado). Cada contenido
publicable lleva N filas `pieza` (una por red) con su propio estado y checklist
"falta copy / imagen / revision / publicar".

El tablero es UNICO y compartido (como Tareas): todo usuario autenticado lo ve y lo edita.

SEGURIDAD:
  - Multiusuario via middleware (sesion o token); `autor`/`responsable` se atribuyen al usuario.
  - `marca` debe ser del catalogo (`consola.marcas`); `red` una red canonica (`consola.redes`)
    o el canal extra "web". `evento_id`, si llega, debe existir en la rota. El RESPONSABLE
    solo puede ser un usuario REAL. Nada se confia del cliente.
  - SQL parametrizado en `repos`/`db` (nunca f-strings con datos).
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
from .post_directo import crear_post_directo
from .radar import desde_radar
from .tablero import (
    aceptar,
    actualizar,
    asignar,
    borrar,
    coger,
    crear,
    cubrir_evento,
    listar,
    soltar,
)

__all__ = [
    "RUTAS",
    "listar",
    "crear",
    "actualizar",
    "borrar",
    "coger",
    "soltar",
    "asignar",
    "aceptar",
    "cubrir_evento",
    "metricas",
    "desde_radar",
    "aportar",
    "crear_post_directo",
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
    Route("/api/publicaciones", listar, methods=["GET"]),
    Route("/api/publicaciones", crear, methods=["POST"]),
    Route("/api/publicaciones/metricas", metricas, methods=["GET"]),
    Route("/api/publicaciones/desde-radar", desde_radar, methods=["POST"]),
    Route("/api/publicaciones/aportar", aportar, methods=["POST"]),
    Route("/api/publicaciones/cubrir-evento", cubrir_evento, methods=["POST"]),
    Route("/api/publicaciones/post-directo", crear_post_directo, methods=["POST"]),
    Route("/api/publicaciones/importar", importar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/preview", previsualizar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/asistente", asistente_ia, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/adaptar-imagen", adaptar_imagen, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}", actualizar, methods=["PATCH"]),
    Route("/api/publicaciones/{publicacion_id}", borrar, methods=["DELETE"]),
    Route("/api/publicaciones/{publicacion_id}/coger", coger, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/soltar", soltar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/asignar", asignar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/aceptar", aceptar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/plataformas", agregar_plataforma, methods=["POST"]),
    Route(
        "/api/publicaciones/{publicacion_id}/plataformas/{pieza_id}",
        actualizar_plataforma,
        methods=["PATCH"],
    ),
    Route(
        "/api/publicaciones/{publicacion_id}/plataformas/{pieza_id}",
        borrar_plataforma,
        methods=["DELETE"],
    ),
    Route("/api/publicaciones/{publicacion_id}/etiquetas", asignar_etiqueta, methods=["POST"]),
    Route(
        "/api/publicaciones/{publicacion_id}/etiquetas/{etiqueta_id}",
        quitar_etiqueta,
        methods=["DELETE"],
    ),
]

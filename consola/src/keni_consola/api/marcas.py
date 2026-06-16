"""API Dashboard "Marcas" (`GET /api/marcas`, SOLO ADMIN): una vista única por marca.

Marcas es de POSTPROXY (las métricas de Metricool viven en Analíticas, no aquí). Una
sola lista: por cada marca, una fila de sumatorio y, debajo, una fila por red con sus
números (seguidores / posts / posts-día) y su estado de conexión, para conectarla o
desconectarla. Los números salen de los snapshots de Postproxy de cada cuenta CONECTADA;
las redes sin conectar aparecen con números a null y un botón de conectar.

PRINCIPIO RECTOR: el endpoint NUNCA debe cascar. Si Postproxy falla (config incompleta,
red caída), esa parte DEGRADA a null/desconectado y NUNCA inventa ceros (ADR 0005). Los
secretos NUNCA salen (solo estado/pista, ya filtrados por los helpers de `api.conexiones`).

Las redes son las del catálogo Postproxy; se EXCLUYE `google_business` por no ser una red
de publicación de contenido editorial en el alcance del piloto (añadirla = a `_REDES_DASHBOARD`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from keni_metricas.fuentes import postproxy as _pp_cliente

from .. import permisos
from . import conexiones as _conexiones

# Mensaje de rechazo (mismo que conexiones: vista de estado de conexiones globales).
_MSG_SOLO_ADMIN = "Solo un administrador puede ver el panel de marcas (estado de conexiones)."

# Redes que pinta el dashboard: catálogo Postproxy SIN google_business (ver módulo).
_REDES_DASHBOARD: tuple[str, ...] = tuple(
    p for p in _pp_cliente.PLATAFORMAS if p != "google_business"
)


def _stats_perfil(api_key: str, perfil_id: str) -> dict:
    """Números de un perfil desde Postproxy ({seguidores, posts_totales, posts_dia}); defensivo."""
    try:
        _ok, _m, st = _pp_cliente.stats_perfil(api_key, perfil_id)
    except Exception:  # noqa: BLE001 -- el endpoint nunca debe cascar
        return {"seguidores": None, "posts_totales": None, "posts_dia": None}
    return st


def _fila_marca(mid: str, etiqueta: str, api_key: str, pp_marca: dict) -> dict:
    """Una marca: sus redes (estado + números) y el sumatorio. Todo desde Postproxy."""
    grupo = pp_marca.get("profile_group_id")
    canal = pp_marca.get("canal") or "metricool"

    # Perfiles conectados, indexados por plataforma (primer perfil gana).
    perfiles: dict[str, dict] = {}
    if api_key and grupo:
        try:
            ok, _msg, lista = _pp_cliente.listar_perfiles(api_key, grupo)
        except Exception:  # noqa: BLE001 -- defensivo
            ok, lista = False, []
        if ok:
            for p in lista:
                plat = p.get("platform")
                if isinstance(plat, str) and plat not in perfiles:
                    perfiles[plat] = p

    redes: list[dict] = []
    tot_seg = tot_posts = 0
    suma_dia = 0.0
    hay_seg = hay_posts = hay_dia = False

    for plataforma in _REDES_DASHBOARD:
        perfil = perfiles.get(plataforma)
        if perfil is None:
            redes.append(
                {
                    "plataforma": plataforma,
                    "conectado": False,
                    "estado": None,
                    "perfil_id": None,
                    "nombre_cuenta": None,
                    "seguidores": None,
                    "posts_totales": None,
                    "posts_dia": None,
                }
            )
            continue

        pid = perfil.get("id")
        st = _stats_perfil(api_key, pid) if isinstance(pid, str) else {}
        seg = st.get("seguidores")
        posts = st.get("posts_totales")
        if posts is None:
            posts = perfil.get("post_count")  # respaldo: posts gestionados por Postproxy
        dia = st.get("posts_dia")

        if isinstance(seg, int):
            tot_seg += seg
            hay_seg = True
        if isinstance(posts, int):
            tot_posts += posts
            hay_posts = True
        if isinstance(dia, (int, float)):
            suma_dia += dia
            hay_dia = True

        redes.append(
            {
                "plataforma": plataforma,
                "conectado": True,
                "estado": perfil.get("status"),
                "perfil_id": pid,
                "nombre_cuenta": perfil.get("name"),
                "seguidores": seg if isinstance(seg, int) else None,
                "posts_totales": posts if isinstance(posts, int) else None,
                "posts_dia": dia if isinstance(dia, (int, float)) else None,
            }
        )

    return {
        "marca": mid,
        "etiqueta": etiqueta,
        "canal_publicacion": canal,
        "postproxy": {"conectado": bool(grupo), "profile_group_id": grupo},
        "redes": redes,
        "total": {
            "seguidores": tot_seg if hay_seg else None,
            "posts_totales": tot_posts if hay_posts else None,
            "posts_dia": (round(suma_dia, 1) if hay_dia else None),
        },
    }


def _construir_dashboard() -> dict:
    """Arma la vista de Marcas: por marca, sus redes (estado + números) y el sumatorio.

    Una llamada a Postproxy por cuenta conectada (el handler lo corre en threadpool). Cada
    proveedor degrada por separado a null/desconectado si falla; nunca casca."""
    from keni_shared import marcas as _marcas_catalogo

    estado_pp = _conexiones.estado_postproxy()
    pp_por_marca = {m["marca"]: m for m in estado_pp.get("marcas", [])}
    api_key = _conexiones._postproxy_api_key(_conexiones._config_existente())

    filas: list[dict] = []
    tot_seg = tot_posts = 0
    suma_dia = 0.0
    hay_seg = hay_posts = hay_dia = False

    for mid, etiqueta in _marcas_catalogo.opciones_metricas():
        fila = _fila_marca(mid, etiqueta, api_key, pp_por_marca.get(mid, {}))
        filas.append(fila)
        t = fila["total"]
        if isinstance(t["seguidores"], int):
            tot_seg += t["seguidores"]
            hay_seg = True
        if isinstance(t["posts_totales"], int):
            tot_posts += t["posts_totales"]
            hay_posts = True
        if isinstance(t["posts_dia"], (int, float)):
            suma_dia += t["posts_dia"]
            hay_dia = True

    return {
        "generado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "totales": {
            "seguidores": tot_seg if hay_seg else None,
            "posts_totales": tot_posts if hay_posts else None,
            "posts_dia": (round(suma_dia, 1) if hay_dia else None),
        },
        "marcas": filas,
    }


async def dashboard(request: Request) -> Response:
    """GET /api/marcas: vista única de marcas × redes (estado + números). SOLO ADMIN (#153).

    Nunca casca: lo que falte va a null/desconectado. En threadpool: las llamadas a
    Postproxy son síncronas y no deben bloquear el event loop.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    try:
        cuerpo = await run_in_threadpool(_construir_dashboard)
    except Exception:  # noqa: BLE001 -- última red de seguridad: nunca un 500 crudo
        return JSONResponse(
            {"error": "No se pudo construir el panel de marcas."}, status_code=500
        )
    return JSONResponse(cuerpo)


RUTAS = [
    Route("/api/marcas", dashboard, methods=["GET"]),
]

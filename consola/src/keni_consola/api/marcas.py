"""API Dashboard "Marcas": una vista consolidada por marca (redes + métricas).

`GET /api/marcas` (SOLO ADMIN) devuelve, por cada marca del catálogo de métricas:
  - si está conectada a Metricool (lectura de métricas) y a Postproxy (publicación),
  - el estado de cada red del catálogo Postproxy (conectada o no, estado, post_count…),
  - métricas agregadas (seguidores, posts totales, posts/día) cuando se puedan leer.

PRINCIPIO RECTOR: el endpoint NUNCA debe cascar. Si un proveedor falla (config
incompleta, red caída, datos no disponibles), esa parte DEGRADA a `null`/desconectado
y NUNCA inventa ceros (ADR 0005: ausencia de dato ≠ 0). Los secretos NUNCA salen.

SOLO ADMIN (#153): mismo gate que `/api/conexiones` (es una vista de configuración y
estado de conexiones globales). Un editor recibe 403.

Las redes listadas son las del catálogo Postproxy; se EXCLUYE `google_business` por no
ser una red social de publicación de contenido editorial en el alcance del piloto (se
documenta aquí; reincorporarla es añadirla a `_REDES_DASHBOARD`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from keni_metricas import servicio as _metricas_servicio
from keni_metricas.fuentes import postproxy as _pp_cliente

from .. import permisos
from . import conexiones as _conexiones

# Mensaje de rechazo (mismo que conexiones: vista de estado de conexiones globales).
_MSG_SOLO_ADMIN = (
    "Solo un administrador puede ver el panel de marcas (estado de conexiones)."
)

# Redes que pinta el dashboard: catálogo Postproxy SIN google_business (ver módulo).
_REDES_DASHBOARD: tuple[str, ...] = tuple(
    p for p in _pp_cliente.PLATAFORMAS if p != "google_business"
)

# Rango por defecto para las métricas agregadas del dashboard.
_RANGO_DEF = "mes"


def _red_vacia(plataforma: str) -> dict:
    """Entrada de red DESCONECTADA (forma completa, todo a null salvo la bandera)."""
    return {
        "plataforma": plataforma,
        "conectado": False,
        "estado": None,
        "perfil_id": None,
        "nombre_cuenta": None,
        "post_count": None,
        "seguidores": None,
    }


def _perfiles_postproxy(api_key: str, grupo: str | None) -> dict[str, dict]:
    """Perfiles de Postproxy de una marca, indexados por plataforma. {} si no se pueden leer.

    Degrada a {} ante cualquier fallo (sin api_key, sin grupo, red caída): el dashboard
    pinta esas redes como desconectadas, nunca casca.
    """
    if not api_key or not grupo:
        return {}
    try:
        ok, _msg, perfiles = _pp_cliente.listar_perfiles(api_key, grupo)
    except Exception:  # noqa: BLE001 -- defensivo: el endpoint nunca debe cascar
        return {}
    if not ok:
        return {}
    por_plataforma: dict[str, dict] = {}
    for p in perfiles:
        plat = p.get("platform")
        # Primer perfil gana por plataforma (suficiente para el estado del dashboard).
        if isinstance(plat, str) and plat not in por_plataforma:
            por_plataforma[plat] = p
    return por_plataforma


def _metricas_marca(marca: str, rango: str) -> dict:
    """Métricas agregadas de una marca: {seguidores, posts_totales, posts_dia}.

    Cablea lo que keni_metricas ofrece y DEGRADA a null donde no haya dato o falle:
      - `seguidores`: ÚLTIMO total de la serie de seguidores (stock), vía
        `servicio.construir_serie_seguidores`. None si la fuente no expone followers.
      - `posts_totales`: `total.publicaciones` de `servicio.construir_reporte`.
      - `posts_dia`: posts_totales / nº de días del periodo del reporte. None si no se
        puede calcular (sin periodo o sin posts).
    NUNCA inventa ceros: ausencia de dato => null.
    """
    seguidores: int | None = None
    posts_totales: int | None = None
    posts_dia: float | None = None

    # Seguidores (stock): último punto de la serie. Degrada a null si vacía o falla.
    try:
        serie = _metricas_servicio.construir_serie_seguidores(rango, marca)
        puntos = serie.get("puntos") if isinstance(serie, dict) else None
        if isinstance(puntos, list) and puntos:
            total = puntos[-1].get("total")
            if isinstance(total, (int, float)):
                seguidores = int(total)
    except Exception:  # noqa: BLE001 -- defensivo: degrada a null, nunca casca
        seguidores = None

    # Posts totales y posts/día desde el reporte consolidado de la marca.
    try:
        rep = _metricas_servicio.construir_reporte(rango, marca)
        total = rep.get("total") if isinstance(rep, dict) else None
        if isinstance(total, dict):
            pub = total.get("publicaciones")
            if isinstance(pub, int):
                posts_totales = pub
        posts_dia = _posts_por_dia(posts_totales, rep)
    except Exception:  # noqa: BLE001 -- defensivo: degrada a null, nunca casca
        posts_totales = None
        posts_dia = None

    return {
        "seguidores": seguidores,
        "posts_totales": posts_totales,
        "posts_dia": posts_dia,
    }


def _posts_por_dia(posts_totales: int | None, rep: dict) -> float | None:
    """posts/día = posts_totales / nº días del periodo del reporte. None si no se puede.

    Lee el periodo de la PRIMERA cuenta del reporte (todas comparten rango). Sin posts o
    sin periodo válido => None (no se inventa una media sobre 0 días ni sobre 0 posts).
    """
    if not posts_totales:
        return None
    cuentas = rep.get("cuentas") if isinstance(rep, dict) else None
    if not isinstance(cuentas, list) or not cuentas:
        return None
    resumen = cuentas[0].get("resumen") if isinstance(cuentas[0], dict) else None
    periodo = resumen.get("periodo") if isinstance(resumen, dict) else None
    if not isinstance(periodo, dict):
        return None
    desde, hasta = periodo.get("desde"), periodo.get("hasta")
    if not isinstance(desde, str) or not isinstance(hasta, str):
        return None
    try:
        d0 = datetime.fromisoformat(desde).date()
        d1 = datetime.fromisoformat(hasta).date()
    except ValueError:
        return None
    dias = (d1 - d0).days + 1
    if dias <= 0:
        return None
    return round(posts_totales / dias, 2)


def _construir_dashboard(rango: str = _RANGO_DEF) -> dict:
    """Arma la respuesta del dashboard. Cada proveedor degrada por separado a null."""
    # Estado de conexiones (sin secretos). Reutiliza los helpers de `api.conexiones`.
    estado_pp = _conexiones.estado_postproxy()
    pp_por_marca = {m["marca"]: m for m in estado_pp.get("marcas", [])}
    pp_api_key = _conexiones._postproxy_api_key(_conexiones._config_existente())

    mc_por_marca = {m["marca"]: m for m in _conexiones.estado_marcas_metricool()}

    from keni_shared import marcas as _marcas_catalogo

    filas: list[dict] = []
    tot_redes = tot_cuentas = tot_posts = 0
    suma_seguidores: int | None = None
    suma_posts_dia: float | None = None

    for mid, etiqueta in _marcas_catalogo.opciones_metricas():
        pp_marca = pp_por_marca.get(mid, {})
        grupo = pp_marca.get("profile_group_id")
        # Canal de publicación de la marca (default "metricool"): el selector que decide a
        # qué adaptador entrega el programador. Lo expone `estado_postproxy()`.
        canal = pp_marca.get("canal") or "metricool"
        mc_conectado = bool(mc_por_marca.get(mid, {}).get("conectado"))

        perfiles = _perfiles_postproxy(pp_api_key, grupo)
        redes: list[dict] = []
        for plataforma in _REDES_DASHBOARD:
            perfil = perfiles.get(plataforma)
            if perfil is None:
                redes.append(_red_vacia(plataforma))
                continue
            tot_redes += 1
            tot_cuentas += 1
            redes.append(
                {
                    "plataforma": plataforma,
                    "conectado": True,
                    "estado": perfil.get("status"),
                    "perfil_id": perfil.get("id"),
                    "nombre_cuenta": perfil.get("name"),
                    "post_count": perfil.get("post_count"),
                    # Postproxy no expone seguidores por perfil: null honesto.
                    "seguidores": None,
                }
            )

        metricas = _metricas_marca(mid, rango)
        if isinstance(metricas.get("seguidores"), int):
            suma_seguidores = (suma_seguidores or 0) + metricas["seguidores"]
        if isinstance(metricas.get("posts_totales"), int):
            tot_posts += metricas["posts_totales"]
        if isinstance(metricas.get("posts_dia"), (int, float)):
            suma_posts_dia = (suma_posts_dia or 0.0) + metricas["posts_dia"]

        filas.append(
            {
                "marca": mid,
                "etiqueta": etiqueta,
                "canal_publicacion": canal,
                "metricool": {"conectado": mc_conectado},
                "postproxy": {"conectado": bool(grupo), "profile_group_id": grupo},
                "redes": redes,
                "metricas": metricas,
            }
        )

    return {
        "generado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "totales": {
            "marcas": len(filas),
            "redes_conectadas": tot_redes,
            "cuentas": tot_cuentas,
            "seguidores": suma_seguidores,
            "posts_totales": tot_posts,
            "posts_dia": (round(suma_posts_dia, 2) if suma_posts_dia is not None else None),
        },
        "marcas": filas,
    }


async def dashboard(request: Request) -> Response:
    """GET /api/marcas: panel consolidado por marca. SOLO ADMIN (#153).

    Nunca casca: cada proveedor degrada a null/desconectado si falla. Secretos jamás
    salen (solo estado/pista, ya filtrados por los helpers de `api.conexiones`).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    rango = request.query_params.get("rango") or _RANGO_DEF
    try:
        cuerpo = _construir_dashboard(rango)
    except Exception:  # noqa: BLE001 -- última red de seguridad: nunca un 500 crudo
        return JSONResponse(
            {"error": "No se pudo construir el panel de marcas."}, status_code=500
        )
    return JSONResponse(cuerpo)


RUTAS = [
    Route("/api/marcas", dashboard, methods=["GET"]),
]

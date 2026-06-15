"""API Dashboard "Marcas": estado de conexiones por marca × red.

`GET /api/marcas` (SOLO ADMIN) devuelve, por cada marca del catálogo de métricas:
  - si está conectada a Metricool (lectura de métricas) y a Postproxy (publicación),
  - el estado de cada red del catálogo Postproxy (conectada o no, estado, post_count…),
  - su canal de publicación activo (metricool | postproxy).

Es CONTROL DE CONEXIONES, no de analítica: carga al instante (solo estado, sin lecturas
lentas). Las MÉTRICAS de audiencia (seguidores, posts, engagement…) NO se calculan aquí
—tienen su propia página en Analíticas (Metricool)—; el panel solo enlaza allí.

PRINCIPIO RECTOR: el endpoint NUNCA debe cascar. Si un proveedor falla (config
incompleta, red caída), esa parte DEGRADA a `null`/desconectado y NUNCA inventa ceros
(ADR 0005: ausencia de dato ≠ 0). Los secretos NUNCA salen.

SOLO ADMIN (#153): mismo gate que `/api/conexiones` (es una vista de configuración y
estado de conexiones globales). Un editor recibe 403.

Las redes listadas son las del catálogo Postproxy; se EXCLUYE `google_business` por no
ser una red social de publicación de contenido editorial en el alcance del piloto (se
documenta aquí; reincorporarla es añadirla a `_REDES_DASHBOARD`).
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
_MSG_SOLO_ADMIN = (
    "Solo un administrador puede ver el panel de marcas (estado de conexiones)."
)

# Redes que pinta el dashboard: catálogo Postproxy SIN google_business (ver módulo).
_REDES_DASHBOARD: tuple[str, ...] = tuple(
    p for p in _pp_cliente.PLATAFORMAS if p != "google_business"
)


def _red_vacia(plataforma: str) -> dict:
    """Entrada de red DESCONECTADA (forma completa, todo a null salvo la bandera)."""
    return {
        "plataforma": plataforma,
        "conectado": False,
        "estado": None,
        "perfil_id": None,
        "nombre_cuenta": None,
        "post_count": None,
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


def _construir_dashboard() -> dict:
    """Arma la respuesta del dashboard: SOLO estado de conexiones (rápido, sin métricas).

    Las métricas de audiencia viven en Analíticas (Metricool); aquí no se leen. Cada
    proveedor degrada por separado a null/desconectado si falla; nunca casca."""
    # Estado de conexiones (sin secretos). Reutiliza los helpers de `api.conexiones`.
    estado_pp = _conexiones.estado_postproxy()
    pp_por_marca = {m["marca"]: m for m in estado_pp.get("marcas", [])}
    pp_api_key = _conexiones._postproxy_api_key(_conexiones._config_existente())

    mc_por_marca = {m["marca"]: m for m in _conexiones.estado_marcas_metricool()}

    from keni_shared import marcas as _marcas_catalogo

    filas: list[dict] = []
    tot_redes = tot_cuentas = 0

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
                }
            )

        filas.append(
            {
                "marca": mid,
                "etiqueta": etiqueta,
                "canal_publicacion": canal,
                "metricool": {"conectado": mc_conectado},
                "postproxy": {"conectado": bool(grupo), "profile_group_id": grupo},
                "redes": redes,
            }
        )

    return {
        "generado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "totales": {
            "marcas": len(filas),
            "redes_conectadas": tot_redes,
            "cuentas": tot_cuentas,
        },
        "marcas": filas,
    }


async def dashboard(request: Request) -> Response:
    """GET /api/marcas: panel de conexiones por marca. SOLO ADMIN (#153).

    Nunca casca: cada proveedor degrada a null/desconectado si falla. Secretos jamás
    salen (solo estado/pista, ya filtrados por los helpers de `api.conexiones`).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    try:
        # En threadpool: el armado hace llamadas síncronas (Postproxy) y no debe
        # bloquear el event loop del resto de peticiones.
        cuerpo = await run_in_threadpool(_construir_dashboard)
    except Exception:  # noqa: BLE001 -- última red de seguridad: nunca un 500 crudo
        return JSONResponse(
            {"error": "No se pudo construir el panel de marcas."}, status_code=500
        )
    return JSONResponse(cuerpo)


RUTAS = [
    Route("/api/marcas", dashboard, methods=["GET"]),
]

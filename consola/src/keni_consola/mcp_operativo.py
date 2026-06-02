"""Servidor MCP OPERATIVO de keni-social, montado en `/mcp` de la propia Consola.

Por qué existe
==============
La Consola ya expone una API JSON completa (`/api/...`) que el SPA consume para
crear/gestionar/aprobar contenido y leer métricas. Este módulo expone ESA MISMA
capacidad a un cliente MCP (p. ej. Claude Code) sin que el cliente conozca la API:
publica un puñado de *tools* de alto nivel ("crea un contenido", "envía a revisión",
"dame el reporte de métricas") y, por dentro, cada tool llama a la API de la Consola.

Cómo encaja (arquitectura)
==========================
- El servidor MCP se MONTA dentro de la app Starlette de la Consola, en `/mcp`
  (transporte streamable-HTTP del SDK `mcp`). Reusa el ingress de Traefik del back
  (basta extender el router a `PathPrefix(/api) || PathPrefix(/mcp)`), sin imagen ni
  servicio nuevos. Ver `app.crear_app` y `deploy/docker-compose.yml`.
- BARRERA EXTERNA: el endpoint `/mcp` exige `Authorization: Bearer <KENI_MCP_BEARER>`
  (middleware `GuardBearerMcp`, comparación en tiempo constante). Si no hay bearer
  configurado, el MCP NO se monta (apagado por defecto: el despliegue no cambia).
- IDENTIDAD INTERNA: las tools no entran por el token de mantenimiento (que no tiene
  usuario y dejaría las acciones "sin autor"), sino con una SESIÓN del usuario
  `config.mcp_usuario()` (por defecto el admin/dueño). Así el historial atribuye lo
  que hace el MCP al dueño, y la regla de aprobación ("otro par de ojos") se evalúa
  con su rol admin. La llamada a la API es IN-PROCESO vía `httpx.ASGITransport` (sin
  socket ni puerto): el back corre con 1 worker uvicorn y un bucle asyncio reentrante
  sirve la petición anidada sin bloquear.

Techo de capacidad (seguridad)
==============================
Las tools llegan HASTA APROBACIÓN: crear/editar/gestionar contenido, generar copy,
enviar a revisión, aprobar/rechazar y LEER métricas. NO se expone programar/publicar
real (eso sigue gated por `KENI_PUBLICAR_REAL` y se opera desde la UI).
"""

from __future__ import annotations

import contextlib
import logging
import secrets
from collections.abc import AsyncIterator
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.types import ASGIApp, Receive, Scope, Send

from . import auth, config
from .observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Base URL interna (solo da el `Host`; ASGITransport no abre socket). No tiene que
# resolver: el transporte llama a la app en proceso. Sin esquema/host válidos httpx
# se queja, así que damos uno sintético y estable.
_BASE_URL = "http://mcp.interno"

# Mensajes (forma `{"error": ...}` del proyecto, en español).
_MSG_NO_INIT = "El servidor MCP aún no está inicializado (lifespan no ejecutado)."
_MSG_SIN_USUARIO = (
    "No hay un usuario al que atribuir las acciones del MCP. Configura "
    "KENI_MCP_USUARIO (o KENI_CONSOLA_ADMIN_USER) con un usuario existente."
)


# --------------------------------------------------------------------------- #
# Cliente: llama a la API de la Consola en proceso, con sesión del dueño.      #
# --------------------------------------------------------------------------- #


def _resolver_usuario_id(nombre: str | None) -> str | None:
    """Id del usuario `nombre` (o, si no existe/None, el primer admin). None si no hay.

    No necesita contraseña: el MCP mintea la sesión por id (`auth.crear_sesion`), lo que
    además evita el gate de `debe_cambiar_password` del bootstrap (el dueño real ya no lo
    tiene). La resolución es tolerante: si el usuario configurado no existe, cae a un admin
    para no dejar el MCP inoperante por un typo en la env.
    """
    usuarios = auth.listar_usuarios()
    if nombre:
        for u in usuarios:
            if u.get("usuario") == nombre:
                return u.get("id")
    for u in usuarios:
        if u.get("rol") == "admin":
            return u.get("id")
    return None


class ClienteConsola:
    """Cliente HTTP IN-PROCESO de la API de la Consola, autenticado como el dueño.

    Mantiene una cookie de sesión (minteada por id, perezosa) y la renueva al primer
    401 (sesión caducada). Cada método devuelve el JSON de la API tal cual (ya viene en
    español y con `{"error": ...}` en los fallos), garantizando una clave `error` en 4xx/5xx.
    """

    def __init__(self, app: ASGIApp, usuario: str | None) -> None:
        self._http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE_URL, timeout=120.0
        )
        self._usuario = usuario
        self._cookie: str | None = None

    def _mintar_sesion(self) -> str | None:
        """Crea (o recrea) una sesión para el usuario del MCP y devuelve su token."""
        uid = _resolver_usuario_id(self._usuario)
        if not uid:
            return None
        return auth.crear_sesion(uid)

    async def _request(self, metodo: str, ruta: str, *, params=None, json=None) -> dict:
        if self._cookie is None:
            self._cookie = self._mintar_sesion()
            if self._cookie is None:
                return {"error": _MSG_SIN_USUARIO}
        # Limpia params/json de valores vacíos (la API distingue "no enviado" de "vacío").
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        cuerpo = None if json is None else {k: v for k, v in json.items() if v not in (None, "")}
        cookies = {auth.COOKIE_SESION: self._cookie}
        try:
            r = await self._http.request(metodo, ruta, params=params, json=cuerpo, cookies=cookies)
            if r.status_code == 401:
                # Sesión caducada/invalidada: re-mintea una vez y reintenta.
                self._cookie = self._mintar_sesion()
                if self._cookie is None:
                    return {"error": _MSG_SIN_USUARIO}
                r = await self._http.request(
                    metodo, ruta, params=params, json=cuerpo,
                    cookies={auth.COOKIE_SESION: self._cookie},
                )
        except httpx.HTTPError as e:  # red en proceso: no debería, pero degradamos limpio
            return {"error": f"Fallo llamando a la API interna: {e}"}
        try:
            datos = r.json()
        except ValueError:
            datos = {"error": f"Respuesta no-JSON de la API ({r.status_code})."}
        if r.status_code >= 400 and "error" not in datos:
            datos = {"error": f"La API respondió {r.status_code}."}
        return datos

    async def get(self, ruta: str, **params: Any) -> dict:
        return await self._request("GET", ruta, params=params)

    async def post(self, ruta: str, cuerpo: dict | None = None) -> dict:
        return await self._request("POST", ruta, json=cuerpo or {})

    async def patch(self, ruta: str, cuerpo: dict | None = None) -> dict:
        return await self._request("PATCH", ruta, json=cuerpo or {})

    async def aclose(self) -> None:
        await self._http.aclose()


class _Holder:
    """Contenedor mutable del cliente: lo puebla el lifespan; lo leen las tools."""

    cliente: ClienteConsola | None = None


# --------------------------------------------------------------------------- #
# Guard del endpoint: Bearer obligatorio en /mcp.                             #
# --------------------------------------------------------------------------- #


class GuardBearerMcp:
    """Middleware ASGI: exige `Authorization: Bearer <bearer>` en las rutas `/mcp`.

    Todo lo que NO empieza por `/mcp` pasa intacto (el resto de la app la protege
    `SeguridadConsola`). La comparación es en tiempo constante. Es la única barrera del
    MCP frente al exterior; por dentro las tools operan con la sesión del dueño.
    """

    def __init__(self, app: ASGIApp, bearer: str) -> None:
        self.app = app
        self._bearer = bearer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return
        if not self._autorizado(scope):
            from starlette.responses import JSONResponse

            resp = JSONResponse(
                {"error": "No autorizado: falta el bearer del MCP o es incorrecto."},
                status_code=401,
            )
            await resp(scope, receive, send)
            return
        # NORMALIZA el path desnudo: el sub-app del MCP se monta en `/mcp` y su ruta interna
        # es `/`, así que `Mount` espera `/mcp/` (con `/mcp` a secas el prefijo se consume y
        # la ruta interna no casa -> caería al SPA). Reescribimos `/mcp` -> `/mcp/` para que el
        # cliente pueda apuntar a la URL limpia `…/mcp` sin depender de redirecciones (que el
        # cliente HTTP del MCP no sigue por defecto).
        if scope.get("path") == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)

    def _autorizado(self, scope: Scope) -> bool:
        for k, v in scope.get("headers", []):
            if k.decode("latin-1").lower() == "authorization":
                valor = v.decode("latin-1")
                if valor.lower().startswith("bearer "):
                    presentado = valor[len("bearer "):].strip()
                    return bool(presentado) and secrets.compare_digest(presentado, self._bearer)
        return False


# --------------------------------------------------------------------------- #
# Servidor MCP: construcción + registro de tools.                             #
# --------------------------------------------------------------------------- #


class ServidorMcp:
    """Empaqueta el FastMCP montable: la sub-app ASGI, su lifespan y el holder del cliente."""

    def __init__(self, usuario: str | None) -> None:
        # Import perezoso del SDK: solo cuando el MCP está encendido (bearer configurado).
        from mcp.server.fastmcp import FastMCP
        from mcp.server.transport_security import TransportSecuritySettings

        self._usuario = usuario
        self.holder = _Holder()
        # streamable_http_path="/" porque el prefijo `/mcp` lo pone el Mount del padre
        # (si no, el endpoint quedaría en /mcp/mcp). stateless_http=True: cada petición es
        # autónoma (no exigimos continuidad de sesión SSE entre llamadas), más simple tras
        # un proxy. El SDK crea el session manager perezosamente en streamable_http_app().
        self._mcp = FastMCP(
            "keni-social",
            streamable_http_path="/",
            stateless_http=True,
            json_response=True,
            # DNS-rebinding protection DESACTIVADA a propósito: por defecto el SDK exige que
            # el Host esté en una allowlist (localhost), y tras Traefik el Host es el público
            # (`social.kenitech.io`) -> daría 421 "Invalid Host header". Esa protección cubre
            # navegadores atacando un server local; aquí NO es el modelo de amenaza: el back
            # solo es alcanzable por Traefik y el endpoint exige el bearer del MCP.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
            instructions=(
                "Operación de redes sociales de keni-social (piloto AMX: UnoTV / Claro "
                "Sports). Con estas tools puedes consultar el catálogo de marcas y redes, "
                "crear y gestionar contenido, generar copy, mover piezas por el flujo de "
                "aprobación (hasta aprobar/rechazar) y leer métricas. Empieza por "
                "`keni_contexto` para conocer marcas, redes y estados válidos."
            ),
        )
        _registrar_tools(self._mcp, self.holder)
        # Crea la sub-app ASGI AHORA (esto instancia el session_manager, requisito para
        # poder engancharlo en el lifespan del padre).
        self._app_asgi = self._mcp.streamable_http_app()

    def app_asgi(self) -> Starlette:
        """La sub-app ASGI a montar con `Mount("/mcp", app=...)`."""
        return self._app_asgi

    @contextlib.asynccontextmanager
    async def lifespan(self, app: Starlette) -> AsyncIterator[None]:
        """Lifespan del PADRE: arranca el session manager y abre el cliente in-proceso.

        Starlette NO ejecuta el lifespan de una sub-app montada, así que enganchamos aquí
        `session_manager.run()` (si no, el endpoint /mcp respondería 500). El cliente se
        crea con el `app` ya construido (para el ASGITransport en proceso).
        """
        self.holder.cliente = ClienteConsola(app, self._usuario)
        try:
            async with self._mcp.session_manager.run():
                yield
        finally:
            with contextlib.suppress(Exception):
                await self.holder.cliente.aclose()
            self.holder.cliente = None


def crear_servidor(usuario: str | None) -> ServidorMcp:
    """Construye el servidor MCP operativo atribuido al usuario `usuario` (o el admin)."""
    return ServidorMcp(usuario)


# --------------------------------------------------------------------------- #
# Tools: capa fina sobre la API de la Consola.                                #
# --------------------------------------------------------------------------- #


def _registrar_tools(mcp, holder: _Holder) -> None:  # noqa: C901 -- registro plano de tools
    """Registra las tools del MCP. Cada una llama a la API con la sesión del dueño."""

    def _cli() -> ClienteConsola | None:
        return holder.cliente

    # ---- Descubrimiento / contexto -------------------------------------- #

    @mcp.tool()
    async def keni_contexto() -> dict:
        """Catálogo operativo: marcas, redes sociales, etiquetas, eventos y los estados
        válidos del flujo. Úsala PRIMERO para saber qué marca/red/estado usar en el resto
        de tools (los demás aceptan esos ids)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        datos = await cli.get("/api/contenido")
        # /api/contenido trae contenidos + catalogos; para contexto basta el catálogo.
        return {"catalogos": datos.get("catalogos", datos)} if "error" not in datos else datos

    @mcp.tool()
    async def keni_metricas_opciones() -> dict:
        """Marcas y rangos disponibles para las tools de métricas (ids exactos a pasar
        como `marca` y `rango`)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/opciones")

    # ---- Contenido (creación / gestión) --------------------------------- #

    @mcp.tool()
    async def keni_listar_contenido(
        marca: str = "", estado: str = "", flujo: str = "",
        responsable_id: str = "", desde: str = "", hasta: str = "", etiqueta: str = "",
    ) -> dict:
        """Lista las piezas de contenido del tablero, con filtros opcionales. `estado` ∈
        {pendiente,en_curso,hecha}; `flujo` ∈ {importante,evergreen,evento}; `desde`/`hasta`
        son fechas YYYY-MM-DD sobre la fecha objetivo. Devuelve cada pieza con sus
        plataformas (copy, estado por red, etc.)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        datos = await cli.get(
            "/api/contenido", marca=marca, estado=estado, flujo=flujo,
            responsable_id=responsable_id, desde=desde, hasta=hasta, etiqueta=etiqueta,
        )
        # Recorta el catálogo (ya lo da `keni_contexto`): la lista de piezas es lo útil aquí.
        if isinstance(datos, dict):
            datos.pop("catalogos", None)
        return datos

    @mcp.tool()
    async def keni_crear_contenido(
        titulo: str, marca: str = "", flujo: str = "", descripcion: str = "",
        prioridad: str = "media", redes: list[str] | None = None,
        fecha_objetivo: str = "", notas: str = "", tipo_contenido: str = "ia",
    ) -> dict:
        """Crea una pieza de contenido en el tablero. `titulo` es obligatorio. `marca` y
        `redes` (ids del catálogo, ver keni_contexto) son necesarias para luego generar
        copy. `flujo` ∈ {importante,evergreen,evento}; `prioridad` ∈ {alta,media,baja}.
        Devuelve la pieza creada (con su id)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            "/api/contenido",
            {
                "titulo": titulo, "marca": marca, "flujo": flujo, "descripcion": descripcion,
                "prioridad": prioridad, "redes": redes or [], "fecha_objetivo": fecha_objetivo,
                "notas": notas, "tipo_contenido": tipo_contenido,
            },
        )

    @mcp.tool()
    async def keni_actualizar_contenido(
        contenido_id: str, estado: str = "", titulo: str = "", descripcion: str = "",
        prioridad: str = "", flujo: str = "", marca: str = "", fecha_objetivo: str = "",
        notas: str = "",
    ) -> dict:
        """Actualiza campos de una pieza (solo los que pases). `estado` ∈
        {pendiente,en_curso,hecha}. Devuelve la pieza actualizada."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo = {
            "estado": estado, "titulo": titulo, "descripcion": descripcion,
            "prioridad": prioridad, "flujo": flujo, "marca": marca,
            "fecha_objetivo": fecha_objetivo, "notas": notas,
        }
        cuerpo = {k: v for k, v in cuerpo.items() if v != ""}
        if not cuerpo:
            return {"error": "Indica algún campo a actualizar."}
        return await cli.patch(f"/api/contenido/{contenido_id}", cuerpo)

    @mcp.tool()
    async def keni_generar_copy(
        contenido_id: str, modo: str = "generar", redes: list[str] | None = None
    ) -> dict:
        """Lanza la generación de copy por IA para una pieza (asistente editorial). `modo` ∈
        {generar,variantes,resumir}. Requiere que la pieza tenga marca y al menos una red.
        Devuelve la generación con su id; sigue su avance con `keni_estado_generacion`."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            f"/api/contenido/{contenido_id}/asistente", {"modo": modo, "redes": redes or []}
        )

    @mcp.tool()
    async def keni_estado_generacion(generacion_id: str) -> dict:
        """Estado y resultado de un trabajo de IA (copy/imagen) por su id: `estado`
        (ejecutando|completado|error), porcentaje y, si terminó, el `resultado` (piezas/copy)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/generaciones/{generacion_id}")

    @mcp.tool()
    async def keni_listar_generaciones(limite: int = 20) -> dict:
        """Últimos trabajos de IA (copy/imagen) lanzados, con su estado. Útil para ver qué
        está corriendo o terminó hace poco."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/generaciones", limite=limite)

    # ---- Publicaciones (posts por plataforma) --------------------------- #

    @mcp.tool()
    async def keni_listar_publicaciones(
        marca: str = "", red: str = "", estado: str = "", limite: int = 50
    ) -> dict:
        """Lista publicaciones (un post por plataforma). `estado` ∈
        {borrador,en_revision,aprobado,programado,publicado}. Devuelve cada post con su
        copy, imagen y estado."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/publicaciones", marca=marca, red=red, estado=estado, limite=limite
        )

    @mcp.tool()
    async def keni_detalle_publicacion(publicacion_id: str) -> dict:
        """Detalle completo de una publicación por su id (copy, imagen, estado, autor,
        revisor, fechas)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/publicaciones/{publicacion_id}")

    # ---- Aprobación (hasta aprobar/rechazar; NO publica) ---------------- #

    @mcp.tool()
    async def keni_cola_aprobacion() -> dict:
        """Cola de publicaciones EN REVISIÓN, pendientes de aprobar o rechazar (con autor y
        fecha de envío)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/aprobacion/cola")

    @mcp.tool()
    async def keni_enviar_a_revision(publicacion_id: str) -> dict:
        """Envía una publicación en borrador a revisión (entra en la cola de aprobación)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/aprobacion/{publicacion_id}/enviar-a-revision")

    @mcp.tool()
    async def keni_aprobar(publicacion_id: str) -> dict:
        """Aprueba una publicación que está en revisión (decide el nivel actual de la
        cadena). NO publica: la deja aprobada, lista para programar desde la UI."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/aprobacion/{publicacion_id}/aprobar")

    @mcp.tool()
    async def keni_rechazar(publicacion_id: str) -> dict:
        """Rechaza una publicación en revisión: vuelve a borrador para corregirla."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/aprobacion/{publicacion_id}/rechazar")

    # ---- Panel y métricas (análisis, solo lectura) --------------------- #

    @mcp.tool()
    async def keni_panel(rango: str = "semana", marca: str = "") -> dict:
        """Panel operativo: total de métricas del rango, picos por marca, cola de
        aprobación y próximas publicaciones. `rango` ∈ {semana,mes,7d,30d}."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/panel", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_tuberia(marca: str = "") -> dict:
        """Tubería de producción: cuántas piezas hay en cada etapa (priorizada, generando
        copy, generando arte, lista para revisar, ...)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/panel/tuberia", marca=marca)

    @mcp.tool()
    async def keni_resumen_dia(marca: str = "") -> dict:
        """Lo que toca HOY: piezas priorizadas del día con su score, por fuente y estado."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/panel/dia", marca=marca)

    @mcp.tool()
    async def keni_metricas_reporte(rango: str = "mes", marca: str = "") -> dict:
        """Reporte de métricas: total + desglose por marca/cuenta del rango. `rango` ∈
        {semana,mes,7d,30d} o un token de mes/rango (ver keni_metricas_opciones)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/reporte", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_metricas_analisis(rango: str = "semana", marca: str = "") -> dict:
        """Análisis accionable del periodo: qué subió/bajó, la pieza que lo explica y el
        siguiente paso recomendado. `rango` ∈ {semana,mes,7d,30d}."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/analisis", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_metricas_piezas(rango: str = "mes", marca: str = "") -> dict:
        """Mejores y peores piezas del rango por engagement, con su plataforma y enlace."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/piezas", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_metricas_seguidores(rango: str = "mes", marca: str = "") -> dict:
        """Evolución de seguidores del rango: serie diaria (total + por red) y el neto
        ganado/perdido del periodo. `rango` ∈ {semana,mes,7d,30d} o un token de mes/rango
        (ver keni_metricas_opciones); `marca` acota a una marca, vacío = todas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/seguidores", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_metricas_desglose(rango: str = "mes", marca: str = "") -> dict:
        """Desglose de interacciones por marca×red: likes, comentarios, compartidos,
        guardados, video_views y agregados (con totales). `rango` ∈ {semana,mes,7d,30d};
        `marca` acota a una marca, vacío = todas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/desglose", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_metricas_crosstab(rango: str = "mes", marca: str = "") -> dict:
        """Rendimiento cruzado marca×red×formato: nº de piezas, visualizaciones,
        interacciones, engagement y rendimiento relativo medio por celda. `rango` ∈
        {semana,mes,7d,30d}; `marca` acota a una marca, vacío = todas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/crosstab", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_metricas_correlacion(rango: str = "mes", marca: str = "") -> dict:
        """Correlación seguidores ganados ↔ piezas publicadas (no causalidad): por
        marca×red×fecha, seguidores ganados, nº de posts, ratio por post y el post estrella
        del día. `rango` ∈ {semana,mes,7d,30d}; `marca` acota a una marca, vacío = todas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/correlacion", rango=rango, marca=marca)

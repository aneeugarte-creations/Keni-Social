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
from contextvars import ContextVar
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.types import ASGIApp, Receive, Scope, Send

from . import auth, config
from .observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Identidad a IMPERSONAR en la petición MCP en curso (id de usuario). La fija el guard del
# endpoint y la lee `ClienteConsola` para mintear la sesión de ESE usuario (así un Ralph
# operativo actúa como quien lo lanzó, acotado a sus permisos). El guard la resuelve por dos vías
# (ver `GuardBearerMcp`): si el bearer presentado es un TOKEN MCP por identidad, el usuario es su
# dueño (no se mira ninguna cabecera); si es el bearer COMPARTIDO legacy (`KENI_MCP_BEARER`), cae
# a la cabecera `X-Keni-Usuario-Id`. None => usuario fijo (`config.mcp_usuario()`), el del MCP de
# sesión (claude.ai/desktop).
_HEADER_USUARIO = "x-keni-usuario-id"
_USUARIO_PETICION: ContextVar[str | None] = ContextVar("_USUARIO_PETICION", default=None)

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
        # Cookie de sesión CACHEADA POR id de usuario: cada identidad (la del Ralph que llama o
        # el usuario fijo) tiene la suya, sin pisarse entre peticiones concurrentes de distintos
        # usuarios.
        self._cookies: dict[str, str] = {}

    def _uid_efectivo(self) -> str | None:
        """Id del usuario a impersonar: el de la petición (cabecera) o, si no, el fijo del MCP."""
        uid = _USUARIO_PETICION.get()
        if uid:
            return uid
        return _resolver_usuario_id(self._usuario)

    async def _request(self, metodo: str, ruta: str, *, params=None, json=None) -> dict:
        uid = self._uid_efectivo()
        if not uid:
            return {"error": _MSG_SIN_USUARIO}
        cookie = self._cookies.get(uid)
        if cookie is None:
            cookie = auth.crear_sesion(uid)
            self._cookies[uid] = cookie
        # Limpia params/json de valores vacíos (la API distingue "no enviado" de "vacío").
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        cuerpo = None if json is None else {k: v for k, v in json.items() if v not in (None, "")}
        cookies = {auth.COOKIE_SESION: cookie}
        try:
            r = await self._http.request(metodo, ruta, params=params, json=cuerpo, cookies=cookies)
            if r.status_code == 401:
                # Sesión caducada/invalidada: re-mintea la de ESTE usuario una vez y reintenta.
                cookie = auth.crear_sesion(uid)
                self._cookies[uid] = cookie
                r = await self._http.request(
                    metodo, ruta, params=params, json=cuerpo,
                    cookies={auth.COOKIE_SESION: cookie},
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

    async def put(self, ruta: str, cuerpo: dict | None = None) -> dict:
        return await self._request("PUT", ruta, json=cuerpo or {})

    async def delete(self, ruta: str) -> dict:
        return await self._request("DELETE", ruta)

    async def aclose(self) -> None:
        await self._http.aclose()


class _Holder:
    """Contenedor mutable del cliente: lo puebla el lifespan; lo leen las tools."""

    cliente: ClienteConsola | None = None


# --------------------------------------------------------------------------- #
# Guard del endpoint: Bearer obligatorio en /mcp.                             #
# --------------------------------------------------------------------------- #


class GuardBearerMcp:
    """Middleware ASGI: autentica `Authorization: Bearer <token>` en las rutas `/mcp`.

    Todo lo que NO empieza por `/mcp` pasa intacto (el resto de la app la protege
    `SeguridadConsola`). Es la única barrera del MCP frente al exterior; por dentro las tools
    operan con la sesión del usuario resuelto.

    DOS VENTANAS de autenticación, en orden:
      1) TOKEN MCP POR IDENTIDAD: si el bearer presentado valida contra `tokens_mcp`
         (`auth.token_mcp_valido`), la identidad de la petición es su DUEÑO. No se mira ninguna
         cabecera: el token YA identifica al usuario.
      2) BEARER COMPARTIDO legacy (`KENI_MCP_BEARER`): si el token no es de identidad y el bearer
         compartido sigue configurado, se compara en tiempo constante; al pasar, la identidad se
         toma de la cabecera `X-Keni-Usuario-Id` (o el usuario fijo si no viene). Vía de
         transición mientras queden emisores con el bearer compartido.
    """

    def __init__(self, app: ASGIApp, bearer: str | None) -> None:
        self.app = app
        self._bearer = bearer or ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return
        presentado = self._bearer_presentado(scope)
        usuario = auth.token_mcp_valido(presentado) if presentado else None
        if usuario is not None:
            # Vía 1: el token identifica al usuario; la cabecera se ignora.
            uid: str | None = usuario["id"]
        elif self._autorizado(presentado):
            # Vía 2 (legacy): bearer compartido válido -> identidad por cabecera (o fijo).
            uid = self._usuario_cabecera(scope)
        else:
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
        # Impersona al usuario resuelto durante TODA la petición: el cliente in-proceso mintea su
        # sesión.
        token = _USUARIO_PETICION.set(uid)
        try:
            await self.app(scope, receive, send)
        finally:
            _USUARIO_PETICION.reset(token)

    def _bearer_presentado(self, scope: Scope) -> str | None:
        """Token del `Authorization: Bearer …` presentado (o None si no viene)."""
        for k, v in scope.get("headers", []):
            if k.decode("latin-1").lower() == "authorization":
                valor = v.decode("latin-1")
                if valor.lower().startswith("bearer "):
                    return valor[len("bearer "):].strip() or None
        return None

    def _autorizado(self, presentado: str | None) -> bool:
        """True si `presentado` casa con el bearer COMPARTIDO legacy (tiempo constante).

        False si no hay bearer compartido configurado (ventana legacy cerrada).
        """
        if not self._bearer or not presentado:
            return False
        return secrets.compare_digest(presentado, self._bearer)

    def _usuario_cabecera(self, scope: Scope) -> str | None:
        """Id de usuario a impersonar de la cabecera `X-Keni-Usuario-Id` (o None)."""
        for k, v in scope.get("headers", []):
            if k.decode("latin-1").lower() == _HEADER_USUARIO:
                uid = v.decode("latin-1").strip()
                return uid or None
        return None


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
                "Sports). Cubre la gestión del día a día de un usuario normal: catálogo de "
                "marcas y redes; crear/editar/gestionar contenido (asignar, coger/soltar, "
                "etiquetar, comentar, clonar, editar copy con historial); trabajar el pool de "
                "noticias e historias (mesa de redacción, usar/descartar) y breaking; generar "
                "copy con la biblioteca de prompts y verificar la voz contra los patrones "
                "medidos; ideas evergreen, sugerencias e insumos; campañas, etiquetas y "
                "notificaciones; mover piezas por el flujo de aprobación (hasta aprobar/"
                "rechazar/deshacer); leer métricas (incl. líneas, comparativas y Ads); y la "
                "rota del equipo (turnos y canjes). NO cubre, a propósito: administración de "
                "usuarios, publicar/programar real (eso es de la UI) y la edición de media "
                "(audio, vídeo, imagen). Empieza por `keni_contexto` para conocer marcas, "
                "redes y estados válidos."
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
        datos = await cli.get("/api/publicaciones")
        # /api/publicaciones trae contenidos + catalogos; para contexto basta el catálogo.
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
    async def keni_listar_publicaciones(
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
            "/api/publicaciones", marca=marca, estado=estado, flujo=flujo,
            responsable_id=responsable_id, desde=desde, hasta=hasta, etiqueta=etiqueta,
        )
        # Recorta el catálogo (ya lo da `keni_contexto`): la lista de piezas es lo útil aquí.
        if isinstance(datos, dict):
            datos.pop("catalogos", None)
        return datos

    @mcp.tool()
    async def keni_crear_publicacion(
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
            "/api/publicaciones",
            {
                "titulo": titulo, "marca": marca, "flujo": flujo, "descripcion": descripcion,
                "prioridad": prioridad, "redes": redes or [], "fecha_objetivo": fecha_objetivo,
                "notas": notas, "tipo_contenido": tipo_contenido,
            },
        )

    @mcp.tool()
    async def keni_actualizar_publicacion(
        publicacion_id: str, estado: str = "", titulo: str = "", descripcion: str = "",
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
        return await cli.patch(f"/api/publicaciones/{publicacion_id}", cuerpo)

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

    # ---- Piezas (posts por plataforma) --------------------------- #

    @mcp.tool()
    async def keni_listar_piezas(
        marca: str = "", red: str = "", estado: str = "", limite: int = 50
    ) -> dict:
        """Lista piezas (un post por plataforma). `estado` ∈
        {borrador,en_revision,programado,publicado}. Devuelve cada post con su
        copy, imagen y estado."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/piezas", marca=marca, red=red, estado=estado, limite=limite
        )

    @mcp.tool()
    async def keni_detalle_pieza(pieza_id: str) -> dict:
        """Detalle completo de una publicación por su id (copy, imagen, estado, autor,
        revisor, fechas)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/piezas/{pieza_id}")

    # ---- Aprobación (hasta aprobar/rechazar; NO publica) ---------------- #

    @mcp.tool()
    async def keni_cola_aprobacion() -> dict:
        """Cola de piezas EN REVISIÓN, pendientes de aprobar o rechazar (con autor y
        fecha de envío)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/aprobacion/cola")

    @mcp.tool()
    async def keni_enviar_a_revision(pieza_id: str) -> dict:
        """Envía una publicación en borrador a revisión (entra en la cola de aprobación)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/aprobacion/{pieza_id}/enviar-a-revision")

    @mcp.tool()
    async def keni_aprobar(pieza_id: str) -> dict:
        """Da un OK (like) a una publicación en revisión (decide el nivel actual de la cadena).
        Con los 2 OK de personas distintas la pieza se auto-programa al próximo hueco. NO publica."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/aprobacion/{pieza_id}/aprobar")

    @mcp.tool()
    async def keni_rechazar(pieza_id: str) -> dict:
        """Rechaza una publicación en revisión: vuelve a borrador para corregirla."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/aprobacion/{pieza_id}/rechazar")

    # ---- Métricas (análisis, solo lectura) ----------------------------- #

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

    @mcp.tool()
    async def keni_metricas_pieza_historico(id: str) -> dict:
        """Histórico de UNA pieza por su id (de Metricool): la serie de snapshots
        acumulados (visualizaciones, interacciones, engagement, granulares) y un resumen
        de velocidad (% en las primeras 24 h, delta medio por día). `puntos` vacío = la
        pieza aún no se está siguiendo (sin histórico todavía); `velocidad` nula con menos
        de 2 snapshots."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/pieza-historico", id=id)

    @mcp.tool()
    async def keni_metricas_comparar(
        rango_a: str = "semana", rango_b: str = "mes", marca: str = ""
    ) -> dict:
        """Comparativa de DOS periodos (A vs B): totales, desglose de interacciones y
        seguidores de ambos, para ver qué cambió. `rango_a`/`rango_b` ∈ {semana,mes,7d,30d}
        o un token de mes/rango (ver keni_metricas_opciones)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/metricas/comparar", rango_a=rango_a, rango_b=rango_b, marca=marca
        )

    @mcp.tool()
    async def keni_metricas_lineas(rango: str = "mes", marca: str = "") -> dict:
        """Rendimiento del periodo por LÍNEA editorial (etiqueta de clase `vertical`) y por
        ORIGEN: nº de piezas, visualizaciones, interacciones y engagement medio por cubo.
        Responde "qué línea funciona" (p. ej. Liga MX vs NFL en Claro Sports)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/lineas", rango=rango, marca=marca)

    @mcp.tool()
    async def keni_metricas_ads(rango: str = "mes", marca: str = "") -> dict:
        """Campañas de publicidad PAGADA del periodo (Meta/TikTok Ads): impresiones, gasto
        y clics por campaña + totales. Lista vacía = sin Ads conectado o sin entrega en el
        periodo."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/metricas/ads", rango=rango, marca=marca)

    # ---- Patrones editoriales y verificación de voz (ADR 0009) ---------- #

    @mcp.tool()
    async def keni_patrones_marca(marca: str = "") -> dict:
        """Perfil de PATRONES medidos de una marca (derivado de su rendimiento real en
        Metricool): por red, bandas del cuartil TOP vs FONDO (longitud, emojis, hashtags,
        gancho en MAYÚSCULAS, pregunta, formatos) y las reglas del lint de voz. Sin
        `marca`, devuelve qué marcas tienen perfil. Úsalo para escribir copy dentro del
        patrón real de la marca."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/patrones", marca=marca)

    @mcp.tool()
    async def keni_verificar_voz(
        marca: str, texto: str, redes: list[str] | None = None, copy_unico: bool = True
    ) -> dict:
        """Verifica un TEXTO contra los patrones medidos de su marca (la misma verificación
        determinista que corre tras generar copy): emojis, longitud, hashtags, gancho y
        pregunta fuera del patrón real. `redes` acota la verificación (sin ella, todas);
        `copy_unico` aplica además el contrato del copy unificado (sin hashtags). Devuelve
        `{avisos, dentro_de_patron}` — un texto con avisos merece revisión, no es un
        bloqueo."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {"marca": marca, "texto": texto, "copy_unico": copy_unico}
        if redes:
            cuerpo["redes"] = redes
        return await cli.post("/api/patrones/verificar-voz", cuerpo)

    # ---- Noticias (pool de ingesta -> tablero) -------------------------- #

    @mcp.tool()
    async def keni_listar_noticias(
        marca: str = "", estado: str = "", q: str = "", desde: str = "", limite: int = 20
    ) -> dict:
        """Pool de noticias ingeridas (RSS/tendencias), más nuevas primero. `estado` ∈
        {nuevo,usado,descartado}; `q` busca en título+resumen; `desde` es fecha ISO sobre
        la captura. Cada item trae título, resumen, url, marca sugerida y relevancia. Para
        convertir una en contenido usa `keni_usar_noticia`."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/noticias", marca=marca, estado=estado, q=q, desde=desde, limit=limite
        )

    @mcp.tool()
    async def keni_usar_noticia(
        item_id: str, redes: list[str] | None = None, generar: bool = True
    ) -> dict:
        """Lleva una noticia del pool al tablero: crea el contenido (origen=noticia) y, si
        `generar` (def True) y la noticia tiene marca, encola el copy en segundo plano.
        Idempotente: si ya estaba usada devuelve el contenido enlazado sin duplicar."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {"generar": generar}
        if redes:
            cuerpo["redes"] = redes
        return await cli.post(f"/api/noticias/{item_id}/usar", cuerpo)

    @mcp.tool()
    async def keni_descartar_noticia(item_id: str) -> dict:
        """Descarta una noticia del pool (estado=descartado): no aparecerá como candidata."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/noticias/{item_id}/descartar")

    @mcp.tool()
    async def keni_noticias_cobertura() -> dict:
        """Salud del motor de ingesta de noticias: cuántos items hay por marca/estado y
        qué tan fresca es la captura (para detectar marcas sin pool que alimentar)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/noticias/cobertura")

    # ---- Apoyos editoriales: franjas, evergreen, algoritmos --- #

    @mcp.tool()
    async def keni_franjas() -> dict:
        """Franjas horarias de publicación configuradas (día de semana + hora, por marca y
        red): las ventanas en las que el equipo programa."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/franjas")

    @mcp.tool()
    async def keni_evergreen_ideas(marca: str = "", estado: str = "") -> dict:
        """Catálogo de ideas EVERGREEN (contenido reutilizable sin caducidad) con su estado.
        Útil para llenar huecos de parrilla cuando no hay actualidad."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/evergreen/ideas", marca=marca, estado=estado)

    @mcp.tool()
    async def keni_algoritmos(plataforma: str = "", nivel: str = "", limite: int = 20) -> dict:
        """Inteligencia de PLATAFORMA: cambios de algoritmo y tendencias por red
        (Instagram/TikTok/Facebook/YouTube/X), ordenadas por importancia. `nivel` filtra
        por importancia; `solo cambios` los confirmados. Para saber a qué jugarle hoy."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/algoritmos", plataforma=plataforma, nivel=nivel, limite=limite
        )

    # ---- Observabilidad de la generación --------------------------------- #

    @mcp.tool()
    async def keni_cola_estado(marca: str = "") -> dict:
        """Snapshot EN VIVO de la cola de generación de IA: jobs en curso/esperando (con su
        marca y tipo), capacidad de workers, daemons y presupuesto/gasto del día. Para
        saber por qué algo tarda o si la máquina está saturada."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/actividad/cola", marca=marca)

    @mcp.tool()
    async def keni_produccion_dia(marca: str = "") -> dict:
        """Producción del DÍA de una marca, de un vistazo: el flujo de las últimas 24 h
        (temas creados → generando → en borrador → en revisión → programado →
        publicado), desglosado por vertical y por origen, contra el objetivo diario
        (`KENI_CUPO_DIA`); más la cola de generación y la de programación (programadas con
        su hora y próximos huecos de franja por red). Para monitorizar el objetivo de N
        contenidos diarios sin sumar a mano."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/produccion/dia", marca=marca)

    # ---- Verificación de video (datar un viral) -------------------------- #

    @mcp.tool()
    async def keni_verificar_video(enlace: str, contexto: str = "") -> dict:
        """Lanza la verificación de un VIDEO viral (datarlo: nuevo vs reciclado): descarga
        metadatos, OCR de fechas en pantalla y enlaces de búsqueda inversa. Corre en
        segundo plano: devuelve una generación; sigue su avance con
        `keni_estado_generacion` (el resultado junta la evidencia, el dictamen lo pone el
        humano)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post("/api/verificar", {"enlace": enlace, "contexto": contexto})

    @mcp.tool()
    async def keni_verificar_estado() -> dict:
        """Salud de los motores de verificación de vídeo (binarios disponibles, si puede
        verificar, qué falta). Consúltalo antes de lanzar `keni_verificar_video`."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/verificar/estado")

    # ---- Generación de copy (biblioteca de prompts) --------------------- #

    @mcp.tool()
    async def keni_lanzar_copy(
        marca: str, target_tipo: str = "contenido", target_valor: str = "",
        prompt_id: str = "", texto: str = "", titulo: str = "",
        redes: list[str] | None = None, adjuntos: list[str] | None = None,
    ) -> dict:
        """Genera copy con la máquina de prompts. `marca` obligatoria. Indica QUÉ ejecutar con
        `prompt_id` (un prompt de la biblioteca, ver `keni_listar_prompts`) o `texto` (prompt
        ad-hoc). `target_tipo` ∈ {contenido,area,url,ninguno} y `target_valor` su id/URL (p.
        ej. tipo=contenido + valor=<publicacion_id> para escribir sobre una pieza existente).
        `redes` acota plataformas. Corre en segundo plano: devuelve una generación; sigue su
        avance con `keni_estado_generacion`."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        target: dict[str, Any] = {"tipo": target_tipo}
        if target_valor:
            target["valor"] = target_valor
        cuerpo: dict[str, Any] = {
            "marca": marca, "target": target, "prompt_id": prompt_id, "texto": texto,
            "titulo": titulo, "redes": redes or [], "adjuntos": adjuntos or [],
        }
        return await cli.post("/api/prompts/lanzar", cuerpo)

    @mcp.tool()
    async def keni_listar_prompts(
        tipo: str = "", carpeta: str = "", q: str = "", marca: str = "", pipeline: str = ""
    ) -> dict:
        """Biblioteca de prompts disponibles (con sus carpetas y facetas). `q` busca por texto;
        `marca`/`tipo`/`pipeline` filtran. Devuelve cada documento con su id (úsalo como
        `prompt_id` en `keni_lanzar_copy`)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/prompts", tipo=tipo, carpeta=carpeta, q=q, marca=marca, pipeline=pipeline
        )

    @mcp.tool()
    async def keni_leer_prompt(doc_id: str) -> dict:
        """Contenido de UN prompt de la biblioteca por su id (ver `keni_listar_prompts`)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/prompts/{doc_id}")

    @mcp.tool()
    async def keni_prompts_editoriales(marca: str, pipeline: str = "") -> dict:
        """Documentos editoriales de una marca que se auto-adjuntan al generar copy (contexto
        de voz/estrategia). `pipeline` los acota a un pipeline."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/prompts/editoriales", marca=marca, pipeline=pipeline)

    @mcp.tool()
    async def keni_estrategia_marca(marca: str = "") -> dict:
        """Pilares editoriales de una marca (marca, voz, tropicalización, plataforma, reglas) y
        su completitud: qué contexto hay definido para escribir bien y qué falta."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/prompts/estrategia", marca=marca)

    @mcp.tool()
    async def keni_prompt_variables() -> dict:
        """Catálogo de variables `{{VAR}}` que la Consola sustituye al inyectar un prompt
        (nombre, descripción, ejemplo y origen de cada una)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/prompts/variables")

    # ---- Piezas (gestión del copy y del post por plataforma) ------------ #

    @mcp.tool()
    async def keni_guardar_copy(pieza_id: str, copy: str, nota: str = "") -> dict:
        """Guarda el copy de una pieza (un post por plataforma), versionando el anterior en su
        historial. `nota` documenta el cambio. No hace nada si el copy no cambia."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/plataformas/{pieza_id}/copy", {"copy": copy, "nota": nota})

    @mcp.tool()
    async def keni_copy_versiones(pieza_id: str) -> dict:
        """Historial de copy de una pieza (versiones, más reciente primero) y el copy actual."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/plataformas/{pieza_id}/copy/versiones")

    @mcp.tool()
    async def keni_revertir_copy(pieza_id: str, version_id: str) -> dict:
        """Revierte el copy de una pieza a una versión de su historial (`version_id`, ver
        `keni_copy_versiones`), versionando antes el copy actual."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            f"/api/plataformas/{pieza_id}/copy/revertir", {"version_id": version_id}
        )

    @mcp.tool()
    async def keni_clonar_pieza(pieza_id: str, red: str) -> dict:
        """Clona el contenido de una pieza a otra red (`red`, id del catálogo): crea la pieza
        hermana o sobrescribe la existente (no si ya está publicada)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/piezas/{pieza_id}/clonar", {"red": red})

    @mcp.tool()
    async def keni_borrar_pieza(pieza_id: str) -> dict:
        """Borra una pieza (un post por plataforma) por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.delete(f"/api/piezas/{pieza_id}")

    @mcp.tool()
    async def keni_piezas_opciones() -> dict:
        """Catálogos para gestionar piezas: redes, estados, marcas, líneas editoriales y
        categorías válidas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/piezas/opciones")

    # ---- Tablero (gestión de la pieza de contenido) --------------------- #

    @mcp.tool()
    async def keni_borrar_publicacion(publicacion_id: str) -> dict:
        """Borra una pieza de contenido del tablero por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.delete(f"/api/publicaciones/{publicacion_id}")

    @mcp.tool()
    async def keni_asignar_publicacion(publicacion_id: str, responsable_id: str) -> dict:
        """Asigna una pieza de contenido a una persona (`responsable_id`, ver `keni_contexto`).
        Requiere rol admin."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            f"/api/publicaciones/{publicacion_id}/asignar", {"responsable_id": responsable_id}
        )

    @mcp.tool()
    async def keni_coger_publicacion(publicacion_id: str) -> dict:
        """Reclama una pieza de contenido libre para ti (claim atómico: falla si ya la tiene
        alguien)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/publicaciones/{publicacion_id}/coger")

    @mcp.tool()
    async def keni_soltar_publicacion(publicacion_id: str) -> dict:
        """Libera una pieza de contenido que tenías cogida (vuelve a quedar disponible)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/publicaciones/{publicacion_id}/soltar")

    @mcp.tool()
    async def keni_aceptar_publicacion(publicacion_id: str) -> dict:
        """Acepta una tarea-propuesta y la promueve al calendario de contenido."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/publicaciones/{publicacion_id}/aceptar")

    @mcp.tool()
    async def keni_etiquetar_publicacion(publicacion_id: str, etiqueta_id: str) -> dict:
        """Asigna una etiqueta (`etiqueta_id`, ver `keni_listar_etiquetas`) a una pieza de
        contenido."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            f"/api/publicaciones/{publicacion_id}/etiquetas", {"etiqueta_id": etiqueta_id}
        )

    @mcp.tool()
    async def keni_agregar_red(publicacion_id: str, red: str) -> dict:
        """Añade una plataforma/red (`red`, id del catálogo) a una pieza de contenido: crea su
        post para esa red."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/publicaciones/{publicacion_id}/plataformas", {"red": red})

    @mcp.tool()
    async def keni_comentar(
        publicacion_id: str, texto: str, pieza_id: str = "", menciones: list[str] | None = None
    ) -> dict:
        """Añade un comentario al hilo de una pieza de contenido. `pieza_id` lo acota a una
        plataforma; `menciones` son ids de usuario a notificar."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {"texto": texto}
        if pieza_id:
            cuerpo["pieza_id"] = pieza_id
        if menciones:
            cuerpo["menciones"] = menciones
        return await cli.post(f"/api/publicaciones/{publicacion_id}/comentarios", cuerpo)

    @mcp.tool()
    async def keni_comentarios(publicacion_id: str, pieza_id: str = "") -> dict:
        """Lista los comentarios del hilo de una pieza de contenido (filtrable por `pieza_id`
        de plataforma)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/publicaciones/{publicacion_id}/comentarios", pieza_id=pieza_id)

    # ---- Aprobación: deshacer la propia decisión ------------------------ #

    @mcp.tool()
    async def keni_deshacer_aprobacion(pieza_id: str) -> dict:
        """Retira TU decisión (OK o rechazo) sobre una pieza en revisión: su nivel vuelve a
        pendiente. No publica nada."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/aprobacion/{pieza_id}/deshacer")

    # ---- Noticias: mesa de redacción, historias y breaking -------------- #

    @mcp.tool()
    async def keni_mesa_noticias(marca: str, por_linea: int = 5) -> dict:
        """Mesa de redacción de una marca: el pool de historias segmentado por las LÍNEAS de su
        plan editorial, con cupos, generados/publicados y candidatas por línea (`por_linea`,
        máx 20). Para decidir qué cubrir hoy y dónde hay hueco."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/noticias/mesa", marca=marca, por_linea=por_linea)

    @mcp.tool()
    async def keni_listar_historias(
        marca: str = "", estado: str = "", desde: str = "", limite: int = 50, offset: int = 0
    ) -> dict:
        """Historias (clusters de noticias) rankeadas por score, con su umbral de
        promovibilidad. `estado` ∈ {nuevo,usado,descartado}; `desde` fecha ISO. Convierte una
        en contenido con `keni_usar_historia`."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/noticias/historias", marca=marca, estado=estado, desde=desde,
            limit=limite, offset=offset,
        )

    @mcp.tool()
    async def keni_detalle_historia(cluster_id: str) -> dict:
        """Detalle de una historia por su id: la historia y todos sus items de archivo."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/noticias/historias/{cluster_id}")

    @mcp.tool()
    async def keni_usar_historia(
        cluster_id: str, redes: list[str] | None = None, generar: bool = True
    ) -> dict:
        """Lleva una historia al tablero: crea el borrador (origen=historia) y, si `generar`
        (def True) y hay marca, encola el copy. Idempotente si ya estaba usada."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {"generar": generar}
        if redes:
            cuerpo["redes"] = redes
        return await cli.post(f"/api/noticias/historias/{cluster_id}/usar", cuerpo)

    @mcp.tool()
    async def keni_descartar_historia(cluster_id: str) -> dict:
        """Descarta una historia (irreversible): no volverá a aparecer como candidata."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/noticias/historias/{cluster_id}/descartar")

    @mcp.tool()
    async def keni_breaking(marca: str, geo: str = "MX") -> dict:
        """Temas de BREAKING de una marca (señales calientes del momento), ordenados por
        señal, con el estado de su borrador si ya se preparó."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/breaking", marca=marca, geo=geo)

    @mcp.tool()
    async def keni_preparar_breaking(
        titulo: str, marca: str, redes: list[str] | None = None
    ) -> dict:
        """Prepara un breaking: crea el borrador de alta prioridad y encola su copy (dedup por
        título+marca). NUNCA publica."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {"titulo": titulo, "marca": marca}
        if redes:
            cuerpo["redes"] = redes
        return await cli.post("/api/breaking/preparar", cuerpo)

    # ---- Evergreen (ideas reutilizables) -------------------------------- #

    @mcp.tool()
    async def keni_crear_evergreen(
        marca: str, titulo: str, descripcion: str = "", origen: str = "manual"
    ) -> dict:
        """Crea una idea evergreen (contenido reutilizable sin caducidad) para una marca."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            "/api/evergreen/ideas",
            {"marca": marca, "titulo": titulo, "descripcion": descripcion, "origen": origen},
        )

    @mcp.tool()
    async def keni_actualizar_evergreen(
        idea_id: str, estado: str = "", titulo: str = "", descripcion: str = ""
    ) -> dict:
        """Actualiza una idea evergreen (solo los campos que pases).

        Aprobarla (estado='aprobada') LANZA su investigación con IA; al completar nace un tema del
        pipeline que producción recoge igual que una historia verificada.
        """
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo = {"estado": estado, "titulo": titulo, "descripcion": descripcion}
        cuerpo = {k: v for k, v in cuerpo.items() if v != ""}
        if not cuerpo:
            return {"error": "Indica algún campo a actualizar."}
        return await cli.patch(f"/api/evergreen/ideas/{idea_id}", cuerpo)

    @mcp.tool()
    async def keni_borrar_evergreen(idea_id: str) -> dict:
        """Borra una idea evergreen por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.delete(f"/api/evergreen/ideas/{idea_id}")

    # ---- Sugerencias de producto/contenido ------------------------------ #

    @mcp.tool()
    async def keni_listar_sugerencias() -> dict:
        """Lista las sugerencias (con sus categorías y estados válidos)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/sugerencias")

    @mcp.tool()
    async def keni_crear_sugerencia(titulo: str, detalle: str = "", categoria: str = "") -> dict:
        """Crea una sugerencia con título y, opcionalmente, detalle y categoría."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            "/api/sugerencias", {"titulo": titulo, "detalle": detalle, "categoria": categoria}
        )

    @mcp.tool()
    async def keni_detalle_sugerencia(sugerencia_id: str) -> dict:
        """Detalle de una sugerencia por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/sugerencias/{sugerencia_id}")

    @mcp.tool()
    async def keni_actualizar_sugerencia(
        sugerencia_id: str, estado: str = "", titulo: str = "", detalle: str = "",
        categoria: str = "",
    ) -> dict:
        """Actualiza una sugerencia (solo los campos que pases). Cambiar `estado` puede requerir
        rol superadmin."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo = {
            "estado": estado, "titulo": titulo, "detalle": detalle, "categoria": categoria,
        }
        cuerpo = {k: v for k, v in cuerpo.items() if v != ""}
        if not cuerpo:
            return {"error": "Indica algún campo a actualizar."}
        return await cli.patch(f"/api/sugerencias/{sugerencia_id}", cuerpo)

    @mcp.tool()
    async def keni_construir_sugerencia(sugerencia_id: str, complejidad: str = "") -> dict:
        """Lanza la construcción (generación) de una sugerencia. Devuelve la generación; sigue
        su avance con `keni_estado_generacion`."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            f"/api/sugerencias/{sugerencia_id}/construir", {"complejidad": complejidad}
        )

    # ---- Insumos (materia prima del día) -------------------------------- #

    @mcp.tool()
    async def keni_listar_insumos(
        fecha: str = "", cajon: str = "", marca: str = "", solo_frescos: bool = False
    ) -> dict:
        """Insumos (materia prima volcada por el equipo) agrupados por cajón. `fecha`
        YYYY-MM-DD (def hoy); `solo_frescos` deja solo los sin usar."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/insumos", fecha=fecha, cajon=cajon, marca=marca,
            solo_frescos=("1" if solo_frescos else ""),
        )

    @mcp.tool()
    async def keni_insumos_dias() -> dict:
        """Días con insumos y cuántos hay por cajón (para navegar el histórico)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/insumos/dias")

    @mcp.tool()
    async def keni_aportar_insumo(
        cajon: str, texto: str, fecha: str = "", marca: str = ""
    ) -> dict:
        """Aporta un insumo de TEXTO a un cajón (crea el lote y lo procesa). `fecha`
        YYYY-MM-DD (def hoy); `marca` lo etiqueta."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            "/api/insumos/aportar",
            {"cajon": cajon, "texto": texto, "fecha": fecha, "marca": marca},
        )

    @mcp.tool()
    async def keni_usar_insumo(
        item_id: str, redes: list[str] | None = None, generar: bool = True
    ) -> dict:
        """Lleva un insumo al tablero: crea el contenido y, si `generar` (def True), encola el
        copy. `redes` acota plataformas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {"generar": generar}
        if redes:
            cuerpo["redes"] = redes
        return await cli.post(f"/api/insumos/item/{item_id}/usar", cuerpo)

    @mcp.tool()
    async def keni_actualizar_insumo(
        item_id: str, titulo: str = "", resumen: str = "", marca: str = "", linea: str = "",
        hora: str = "", lugar: str = "", estado_material: str = "", tipo: str = "",
    ) -> dict:
        """Actualiza un item de insumo (solo los campos que pases)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo = {
            "titulo": titulo, "resumen": resumen, "marca": marca, "linea": linea,
            "hora": hora, "lugar": lugar, "estado_material": estado_material, "tipo": tipo,
        }
        cuerpo = {k: v for k, v in cuerpo.items() if v != ""}
        if not cuerpo:
            return {"error": "Indica algún campo a actualizar."}
        return await cli.patch(f"/api/insumos/item/{item_id}", cuerpo)

    @mcp.tool()
    async def keni_borrar_insumo(item_id: str) -> dict:
        """Descarta/borra un item de insumo por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.delete(f"/api/insumos/item/{item_id}")

    # ---- Campañas ------------------------------------------------------- #

    @mcp.tool()
    async def keni_listar_campanias(marca: str = "") -> dict:
        """Lista las campañas (agrupaciones de hashtags por marca). `marca` filtra."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/campanias", marca=marca)

    @mcp.tool()
    async def keni_crear_campania(
        nombre: str, hashtags: list[str] | None = None,
        marcas: list[str] | None = None, marca: str = "",
    ) -> dict:
        """Crea una campaña con `nombre` y sus `hashtags`. Indica su alcance con `marcas`
        (varias) o `marca` (una)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {"nombre": nombre, "hashtags": hashtags or []}
        if marcas:
            cuerpo["marcas"] = marcas
        elif marca:
            cuerpo["marca"] = marca
        return await cli.post("/api/campanias", cuerpo)

    @mcp.tool()
    async def keni_detalle_campania(campania_id: str) -> dict:
        """Detalle de una campaña por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(f"/api/campanias/{campania_id}")

    @mcp.tool()
    async def keni_actualizar_campania(
        campania_id: str, nombre: str = "", hashtags: list[str] | None = None,
        marcas: list[str] | None = None, activa: bool | None = None,
    ) -> dict:
        """Actualiza una campaña (solo los campos que pases): `nombre`, `hashtags`, `marcas` o
        `activa`."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {}
        if nombre:
            cuerpo["nombre"] = nombre
        if hashtags is not None:
            cuerpo["hashtags"] = hashtags
        if marcas is not None:
            cuerpo["marcas"] = marcas
        if activa is not None:
            cuerpo["activa"] = activa
        if not cuerpo:
            return {"error": "Indica algún campo a actualizar."}
        return await cli.put(f"/api/campanias/{campania_id}", cuerpo)

    @mcp.tool()
    async def keni_borrar_campania(campania_id: str) -> dict:
        """Borra una campaña por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.delete(f"/api/campanias/{campania_id}")

    # ---- Etiquetas ------------------------------------------------------ #

    @mcp.tool()
    async def keni_listar_etiquetas(
        marca: str = "", clase: str = "", solo_activas: bool = False
    ) -> dict:
        """Catálogo de etiquetas (con sus clases). `marca`/`clase` filtran; `solo_activas` deja
        las vigentes."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/etiquetas", marca=marca, clase=clase,
            activas=("1" if solo_activas else ""),
        )

    @mcp.tool()
    async def keni_crear_etiqueta(
        nombre: str, clase: str = "", marca: str = "", color: str = "",
        keywords: str = "", hashtags: str = "", grupo: str = "",
    ) -> dict:
        """Crea una etiqueta. `nombre` obligatorio; `clase` (p. ej. vertical), `marca`,
        `color`, `keywords`, `hashtags` y `grupo` opcionales."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo = {
            "nombre": nombre, "clase": clase, "marca": marca, "color": color,
            "keywords": keywords, "hashtags": hashtags, "grupo": grupo,
        }
        cuerpo = {k: v for k, v in cuerpo.items() if v != ""}
        return await cli.post("/api/etiquetas", cuerpo)

    @mcp.tool()
    async def keni_actualizar_etiqueta(
        etiqueta_id: str, nombre: str = "", clase: str = "", marca: str = "", color: str = "",
        keywords: str = "", hashtags: str = "", grupo: str = "", activo: bool | None = None,
    ) -> dict:
        """Actualiza una etiqueta (solo los campos que pases). `activo` la activa/desactiva."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        cuerpo: dict[str, Any] = {
            "nombre": nombre, "clase": clase, "marca": marca, "color": color,
            "keywords": keywords, "hashtags": hashtags, "grupo": grupo,
        }
        cuerpo = {k: v for k, v in cuerpo.items() if v != ""}
        if activo is not None:
            cuerpo["activo"] = activo
        if not cuerpo:
            return {"error": "Indica algún campo a actualizar."}
        return await cli.patch(f"/api/etiquetas/{etiqueta_id}", cuerpo)

    @mcp.tool()
    async def keni_borrar_etiqueta(etiqueta_id: str) -> dict:
        """Borra una etiqueta por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.delete(f"/api/etiquetas/{etiqueta_id}")

    # ---- Notificaciones ------------------------------------------------- #

    @mcp.tool()
    async def keni_notificaciones(marca_id: str = "") -> dict:
        """Buzón de notificaciones del usuario (acotado a `marca_id` si se pasa), con el conteo
        de no leídas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/notificaciones", marca_id=marca_id)

    @mcp.tool()
    async def keni_notificaciones_contador(marca_id: str = "") -> dict:
        """Solo el número de notificaciones no leídas (para un vistazo rápido)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/notificaciones/contador", marca_id=marca_id)

    @mcp.tool()
    async def keni_marcar_notificacion(notificacion_id: str) -> dict:
        """Marca UNA notificación como leída por su id."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/notificaciones/{notificacion_id}/leer")

    @mcp.tool()
    async def keni_marcar_todas_leidas(marca_id: str = "") -> dict:
        """Marca TODAS las notificaciones como leídas (acotado a `marca_id` si se pasa)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post("/api/notificaciones/leer-todas", {"marca_id": marca_id})

    # ---- Rota del equipo (turnos y canjes) ------------------------------ #

    @mcp.tool()
    async def keni_rota_semana(lunes: str = "", marca: str = "") -> dict:
        """Horario del equipo de una semana (con sus franjas). `lunes` YYYY-MM-DD del lunes de
        la semana (def la actual)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/rota/turnos", lunes=lunes, marca=marca)

    @mcp.tool()
    async def keni_mis_turnos(lunes: str = "", marca: str = "") -> dict:
        """Solo TUS turnos de una semana. `lunes` YYYY-MM-DD (def la actual)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/rota/mis-turnos", lunes=lunes, marca=marca)

    @mcp.tool()
    async def keni_rota_mes(mes: str = "", marca: str = "") -> dict:
        """Calendario mensual de turnos de TODO el equipo. `mes` YYYY-MM (def el actual)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/rota/turnos/mes", mes=mes, marca=marca)

    @mcp.tool()
    async def keni_rota_cobertura(lunes: str = "", marca: str = "") -> dict:
        """Cobertura de los eventos de la semana (qué eventos quedan cubiertos por la rota y
        cuáles no). `lunes` YYYY-MM-DD (def la actual)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get("/api/rota/cobertura", lunes=lunes, marca=marca)

    @mcp.tool()
    async def keni_listar_swaps(estado: str = "", mio: bool = False, marca: str = "") -> dict:
        """Solicitudes de canje de turno. `estado` ∈ {propuesto,aceptado,rechazado,
        rechazado_admin,cancelado,aplicado}; `mio` deja solo las tuyas."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.get(
            "/api/rota/swaps", estado=estado, marca=marca, mio=("true" if mio else "")
        )

    @mcp.tool()
    async def keni_crear_swap(
        destinatario_id: str, fecha_a: str, franja_a: str, fecha_b: str, franja_b: str,
        motivo: str = "",
    ) -> dict:
        """Solicita un canje de turno con otra persona: ofreces tu turno (`fecha_a`/`franja_a`)
        a cambio del suyo (`fecha_b`/`franja_b`). Fechas YYYY-MM-DD."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(
            "/api/rota/swaps",
            {
                "destinatario_id": destinatario_id, "fecha_a": fecha_a, "franja_a": franja_a,
                "fecha_b": fecha_b, "franja_b": franja_b, "motivo": motivo,
            },
        )

    @mcp.tool()
    async def keni_aceptar_swap(swap_id: str, respuesta: str = "") -> dict:
        """Acepta un canje de turno del que eres destinatario (queda pendiente de visto bueno
        del admin)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/rota/swaps/{swap_id}/aceptar", {"respuesta": respuesta})

    @mcp.tool()
    async def keni_rechazar_swap(swap_id: str, respuesta: str = "") -> dict:
        """Rechaza un canje de turno del que eres destinatario."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/rota/swaps/{swap_id}/rechazar", {"respuesta": respuesta})

    @mcp.tool()
    async def keni_cancelar_swap(swap_id: str) -> dict:
        """Cancela un canje de turno que TÚ solicitaste (mientras no esté aplicado)."""
        cli = _cli()
        if cli is None:
            return {"error": _MSG_NO_INIT}
        return await cli.post(f"/api/rota/swaps/{swap_id}/cancelar")

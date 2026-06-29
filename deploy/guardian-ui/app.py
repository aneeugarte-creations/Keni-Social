#!/usr/bin/env python3
"""guardian-ui: UI INDEPENDIENTE de observación del incident-keeper.

NO depende del back, db ni front de la consola: importa SÓLO starlette + stdlib (+ el helper local
`cuenta.py`, también stdlib), y lee el rastro que el keeper deja en /data/keeper (volumen
compartido, montado read-only). Así, cuando la app está caída y el keeper la está arreglando, esta
UI SIGUE sirviendo (Traefik la enruta directa).

Sirve:
  GET /                 -> index.html (página autocontenida que sondea la API)
  GET /api/sesiones     -> {vigilancia, sesiones:[meta...]}  (lista de detecciones)
  GET /api/sesiones/{id}-> {meta, transcript:[...]}          (razonamiento + acciones, streaming)
  GET /api/cuenta       -> {auth, uso}                       (cuenta de Claude del guardián)
  POST /api/cuenta/login/{iniciar,codigo,cancelar}, /api/cuenta/logout  (cambiar de cuenta)

La gestión de cuenta corre el CLI `claude` (vive en `cuenta.py`, autocontenido). Va tras el
basicauth propio del panel (Traefik `KENI_GUARDIAN_HTPASSWD`), así que no añade su propio gate.
"""
import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

import cuenta

DATA = Path(os.environ.get("KENI_KEEPER_DATA", "/data/keeper"))
AQUI = Path(__file__).resolve().parent
# Fichero del PAT de Woodpecker que usa el keeper (KENI_WOODPECKER_API_TOKEN_FILE). Volumen
# compartido `keeper-secrets`: el guardian-ui lo escribe (rw), el keeper lo lee (ro) en cada ciclo.
# Asi el token se pone/ROTA desde este panel (tras el basicauth de Traefik), sin tocar el .env.
TOKEN = Path(os.environ.get("KENI_WOODPECKER_TOKEN_FILE", "/secrets/woodpecker_token"))

# Tipos de bloque del stream-json de claude -> etiqueta para la UI.
_TIPO = {"text": "texto", "thinking": "razonamiento", "tool_use": "accion"}

# Herramienta -> clave de su input con el dato legible (el comando de Bash, la ruta de Read…). Así
# la acción se ve como "🔧 Bash: git rebase…" en vez de un "🔧 Bash" pelado e inútil.
_TOOL_ARG = {
    "Bash": "command", "Read": "file_path", "Edit": "file_path", "Write": "file_path",
    "NotebookEdit": "notebook_path", "Grep": "pattern", "Glob": "pattern",
    "WebFetch": "url", "WebSearch": "query", "Task": "description",
}


def _resumen_tool(nombre: str, datos: dict) -> str:
    """Resumen legible del input de una herramienta (comando/ruta/patrón…), compacto a una línea."""
    if not isinstance(datos, dict):
        return ""
    valor = datos.get(_TOOL_ARG.get(nombre, ""))
    if not isinstance(valor, str) or not valor.strip():
        valor = next((v for v in datos.values() if isinstance(v, str) and v.strip()), "")
    return " ".join(valor.split())[:300]


def _cerrar_bloque(actual: dict | None) -> dict | None:
    """Finaliza el bloque en curso: si es una herramienta con input acumulado, le pega el resumen
    (el comando) y limpia las claves internas. Para text/razonamiento lo devuelve tal cual."""
    if actual and actual.get("_tool"):
        try:
            datos = json.loads(actual["_json"]) if actual.get("_json", "").strip() else {}
        except ValueError:
            datos = {}
        resumen = _resumen_tool(actual["_tool"], datos)
        if resumen:
            actual["texto"] = "🔧 " + actual["_tool"] + ": " + resumen
        actual.pop("_tool", None)
        actual.pop("_json", None)
    return actual


def _leer_json(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _metas() -> list[dict]:
    if not DATA.is_dir():
        return []
    metas = []
    for f in DATA.glob("*.meta.json"):
        m = _leer_json(f)
        if isinstance(m, dict):
            metas.append(m)
    # más reciente primero (por `inicio` ISO; fallback al nombre)
    metas.sort(key=lambda m: m.get("inicio") or m.get("id") or "", reverse=True)
    return metas


def _texto_evento(ev: dict) -> str | None:
    """Texto legible de un evento NO-stream (`assistant` o `result`): el motivo de una sesión que
    no llegó a razonar (p.ej. el mensaje sintético de un límite de uso). None si no lo trae."""
    tipo = ev.get("type")
    if tipo == "assistant":
        for bloque in (ev.get("message") or {}).get("content") or []:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                t = (bloque.get("text") or "").strip()
                if t:
                    return t
    elif tipo == "result":
        t = (ev.get("result") or "").strip()
        if t:
            return t
    return None


def _transcript(jsonl: Path) -> list[dict]:
    """Reconstruye el transcript (razonamiento + texto + acciones) de los deltas del stream-json.

    Acumula text_delta/thinking_delta por bloque y cierra en content_block_stop; el bloque en vuelo
    (sesión corriendo) se emite con `vivo=true` para que la UI lo muestre creciendo.
    """
    items: list[dict] = []
    actual: dict | None = None
    respaldo: str | None = None  # texto de cierre por si NO hay ningún stream_event (p.ej. un 429)
    try:
        with jsonl.open(encoding="utf-8", errors="replace") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    ev = json.loads(linea)
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                if ev.get("type") != "stream_event":
                    # Sesiones que mueren sin razonar (límite de uso, error de arranque) traen el
                    # motivo solo en un mensaje `assistant`/`result`. Lo guardamos como respaldo.
                    respaldo = _texto_evento(ev) or respaldo
                    continue
                e = ev.get("event") or {}
                tipo_ev = e.get("type")
                if tipo_ev == "content_block_start":
                    bloque = e.get("content_block") or {}
                    btipo = bloque.get("type", "text")
                    actual = {"tipo": _TIPO.get(btipo, "texto"), "texto": ""}
                    if btipo == "tool_use":
                        nombre = bloque.get("name") or "herramienta"
                        actual["texto"] = "🔧 " + nombre
                        actual["_tool"] = nombre  # el input llega luego en input_json_delta
                        actual["_json"] = ""
                elif tipo_ev == "content_block_delta":
                    if actual is None:
                        actual = {"tipo": "texto", "texto": ""}
                    d = e.get("delta") or {}
                    dt = d.get("type")
                    if dt == "text_delta":
                        actual["texto"] += d.get("text") or ""
                    elif dt == "thinking_delta":
                        actual["texto"] += d.get("thinking") or ""
                    elif dt == "input_json_delta" and "_json" in actual:
                        actual["_json"] += d.get("partial_json") or ""
                elif tipo_ev == "content_block_stop":
                    actual = _cerrar_bloque(actual)
                    if actual and actual["texto"].strip():
                        items.append(actual)
                    actual = None
    except OSError:
        return items
    actual = _cerrar_bloque(actual)
    if actual and actual["texto"].strip():
        actual["vivo"] = True
        items.append(actual)
    if not items and respaldo:
        items.append({"tipo": "texto", "texto": respaldo})
    return items


async def sesiones(_request: Request) -> JSONResponse:
    return JSONResponse(
        {"vigilancia": _leer_json(DATA / "estado.json"), "sesiones": _metas()}
    )


async def sesion(request: Request) -> JSONResponse:
    sid = request.path_params["id"]
    if not sid.isdigit():  # los id son epochs; evita traversal
        return JSONResponse({"error": "id inválido"}, status_code=400)
    meta = _leer_json(DATA / f"{sid}.meta.json")
    if meta is None:
        return JSONResponse({"error": "sesión no encontrada"}, status_code=404)
    return JSONResponse({"meta": meta, "transcript": _transcript(DATA / f"{sid}.jsonl")})


def _borrar_sesion(sid: str) -> bool:
    """Borra los ficheros (meta + jsonl) de una sesión. True si borró algo."""
    ok = False
    for f in (DATA / f"{sid}.meta.json", DATA / f"{sid}.jsonl"):
        try:
            f.unlink()
            ok = True
        except OSError:
            pass
    return ok


async def historial_borrar(_request: Request) -> JSONResponse:
    """Borra TODO el historial de detecciones, salvo una sesión `corriendo` (activa)."""
    borradas = 0
    if DATA.is_dir():
        for meta in list(DATA.glob("*.meta.json")):
            m = _leer_json(meta)
            if isinstance(m, dict) and m.get("estado") == "corriendo":
                continue  # no borrar una sesión en marcha
            if _borrar_sesion(meta.name[: -len(".meta.json")]):
                borradas += 1
    return JSONResponse({"borradas": borradas})


async def sesion_borrar(request: Request) -> JSONResponse:
    """Borra UNA detección por id (no si está `corriendo`)."""
    sid = request.path_params["id"]
    if not sid.isdigit():  # los id son epochs; evita traversal
        return JSONResponse({"error": "id inválido"}, status_code=400)
    m = _leer_json(DATA / f"{sid}.meta.json")
    if isinstance(m, dict) and m.get("estado") == "corriendo":
        return JSONResponse({"error": "la sesión está en marcha"}, status_code=409)
    return JSONResponse({"borrada": _borrar_sesion(sid)})


def _token_puesto() -> bool:
    try:
        return bool(TOKEN.read_text(encoding="utf-8").strip())
    except OSError:
        return False


async def token(request: Request) -> JSONResponse:
    """GET: ¿hay token? (nunca devuelve el valor). POST {token}: lo guarda/ROTA."""
    if request.method == "POST":
        try:
            cuerpo = await request.json()
        except (ValueError, TypeError):
            return JSONResponse({"error": "json inválido"}, status_code=400)
        tok = (cuerpo.get("token") or "").strip() if isinstance(cuerpo, dict) else ""
        if not tok or len(tok) > 4096:
            return JSONResponse({"error": "token vacío o demasiado largo"}, status_code=400)
        try:
            TOKEN.parent.mkdir(parents=True, exist_ok=True)
            tmp = TOKEN.with_name(TOKEN.name + ".tmp")
            tmp.write_text(tok, encoding="utf-8")
            os.chmod(tmp, 0o644)  # volumen aislado; el keeper (otro uid) debe poder leerlo
            os.replace(tmp, TOKEN)
        except OSError as e:
            return JSONResponse({"error": f"no se pudo guardar: {e}"}, status_code=500)
    return JSONResponse({"set": _token_puesto()})


async def _cuerpo(request: Request) -> dict:
    """Body JSON de un POST -> dict (vacío si no es un objeto o no parsea)."""
    try:
        datos = await request.json()
    except (ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}


async def cuenta_estado(_request: Request) -> JSONResponse:
    """Estado de auth + medidor de uso de la cuenta de Claude del GUARDIÁN.

    Las dos lecturas corren `claude` (bloqueante) en el threadpool; el `/usage` es lento, así que
    la página lo pide en su propio ciclo, no en el sondeo rápido de la lista.
    """
    auth = await run_in_threadpool(cuenta.estado)
    uso = await run_in_threadpool(cuenta.uso)
    return JSONResponse({"auth": auth, "uso": uso})


async def cuenta_login_iniciar(request: Request) -> JSONResponse:
    c = await _cuerpo(request)
    res = await run_in_threadpool(
        cuenta.iniciar_login,
        console=bool(c.get("console")),
        email=(c.get("email") or None),
        sso=bool(c.get("sso")),
    )
    return JSONResponse(res, status_code=200 if res.get("sesion") else 502)


async def cuenta_login_codigo(request: Request) -> JSONResponse:
    c = await _cuerpo(request)
    sid, codigo = (c.get("sesion") or ""), (c.get("codigo") or "")
    if not sid or not codigo:
        return JSONResponse({"ok": False, "error": "faltan sesion/codigo"}, status_code=400)
    res = await run_in_threadpool(cuenta.enviar_codigo, sid, codigo)
    return JSONResponse(res, status_code=200 if res.get("ok") else 502)


async def cuenta_login_cancelar(request: Request) -> JSONResponse:
    c = await _cuerpo(request)
    res = await run_in_threadpool(cuenta.cancelar_login, c.get("sesion") or "")
    return JSONResponse(res)


async def cuenta_logout(_request: Request) -> JSONResponse:
    res = await run_in_threadpool(cuenta.logout)
    return JSONResponse(res, status_code=200 if res.get("ok") else 502)


async def indice(_request: Request) -> FileResponse:
    return FileResponse(AQUI / "index.html")


async def favicon(_request: Request) -> FileResponse:
    return FileResponse(AQUI / "favicon.png", media_type="image/png")


# Servido en RAÍZ de su propio subdominio (guardian.kenitech.io): no comparte host con el back, así
# que las rutas `/api/...` de la página no chocan con el `/api` del back. Traefik enruta
# Host(guardian.kenitech.io) aquí (ver labels en docker-compose).
app = Starlette(
    routes=[
        Route("/", indice),
        Route("/favicon.png", favicon),
        Route("/api/sesiones", sesiones),
        Route("/api/historial/borrar", historial_borrar, methods=["POST"]),
        Route("/api/sesiones/{id}/borrar", sesion_borrar, methods=["POST"]),
        Route("/api/sesiones/{id}", sesion),
        Route("/api/token", token, methods=["GET", "POST"]),
        # Cuenta de Claude del guardián (rutas específicas antes que la genérica del login).
        Route("/api/cuenta", cuenta_estado),
        Route("/api/cuenta/login/iniciar", cuenta_login_iniciar, methods=["POST"]),
        Route("/api/cuenta/login/codigo", cuenta_login_codigo, methods=["POST"]),
        Route("/api/cuenta/login/cancelar", cuenta_login_cancelar, methods=["POST"]),
        Route("/api/cuenta/logout", cuenta_logout, methods=["POST"]),
    ]
)

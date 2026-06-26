#!/usr/bin/env python3
"""guardian-ui: UI INDEPENDIENTE de observación del incident-keeper.

NO depende del back, db ni front de la consola: importa SÓLO starlette + stdlib, y lee el rastro
que el keeper deja en /data/keeper (volumen compartido, montado read-only). Así, cuando la app
está caída y el keeper la está arreglando, esta UI SIGUE sirviendo (Traefik la enruta directa).

Sirve:
  GET /                 -> index.html (página autocontenida que sondea la API)
  GET /api/sesiones     -> {vigilancia, sesiones:[meta...]}  (lista de detecciones)
  GET /api/sesiones/{id}-> {meta, transcript:[...]}          (razonamiento + acciones, streaming)
"""
import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

DATA = Path(os.environ.get("KENI_KEEPER_DATA", "/data/keeper"))
AQUI = Path(__file__).resolve().parent
# Fichero del PAT de Woodpecker que usa el keeper (KENI_WOODPECKER_API_TOKEN_FILE). Volumen
# compartido `keeper-secrets`: el guardian-ui lo escribe (rw), el keeper lo lee (ro) en cada ciclo.
# Asi el token se pone/ROTA desde este panel (tras el basicauth de Traefik), sin tocar el .env.
TOKEN = Path(os.environ.get("KENI_WOODPECKER_TOKEN_FILE", "/secrets/woodpecker_token"))

# Tipos de bloque del stream-json de claude -> etiqueta para la UI.
_TIPO = {"text": "texto", "thinking": "razonamiento", "tool_use": "accion"}


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


def _transcript(jsonl: Path) -> list[dict]:
    """Reconstruye el transcript (razonamiento + texto + acciones) de los deltas del stream-json.

    Acumula text_delta/thinking_delta por bloque y cierra en content_block_stop; el bloque en vuelo
    (sesión corriendo) se emite con `vivo=true` para que la UI lo muestre creciendo.
    """
    items: list[dict] = []
    actual: dict | None = None
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
                if not isinstance(ev, dict) or ev.get("type") != "stream_event":
                    continue
                e = ev.get("event") or {}
                tipo_ev = e.get("type")
                if tipo_ev == "content_block_start":
                    bloque = e.get("content_block") or {}
                    btipo = bloque.get("type", "text")
                    actual = {"tipo": _TIPO.get(btipo, "texto"), "texto": ""}
                    if btipo == "tool_use":
                        actual["texto"] = "🔧 " + (bloque.get("name") or "herramienta")
                elif tipo_ev == "content_block_delta":
                    if actual is None:
                        actual = {"tipo": "texto", "texto": ""}
                    d = e.get("delta") or {}
                    if d.get("type") == "text_delta":
                        actual["texto"] += d.get("text") or ""
                    elif d.get("type") == "thinking_delta":
                        actual["texto"] += d.get("thinking") or ""
                elif tipo_ev == "content_block_stop":
                    if actual and actual["texto"].strip():
                        items.append(actual)
                    actual = None
    except OSError:
        return items
    if actual and actual["texto"].strip():
        actual["vivo"] = True
        items.append(actual)
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


async def indice(_request: Request) -> FileResponse:
    return FileResponse(AQUI / "index.html")


# Servido bajo /guardian SIN stripprefix: así las rutas absolutas de la página (/guardian/api/...)
# enrutan de vuelta a este servicio y NO al back (/api). Traefik enruta PathPrefix(/guardian) aquí.
app = Starlette(
    routes=[
        Route("/guardian", indice),
        Route("/guardian/", indice),
        Route("/guardian/api/sesiones", sesiones),
        Route("/guardian/api/sesiones/{id}", sesion),
        Route("/guardian/api/token", token, methods=["GET", "POST"]),
    ]
)

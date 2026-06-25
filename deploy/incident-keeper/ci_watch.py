#!/usr/bin/env python3
"""Watcher de CI para el incident-keeper: replica el disparo del "green keeper".

Mira el estado del ÚLTIMO pipeline de `main` en Woodpecker y, si está ROJO (estado terminal
failure/error), imprime un bloque con el número del pipeline, el mensaje del commit y los fallos
REALES de los steps en rojo (FAILED/ERROR/error TS/violaciones de frontera). El keeper usa esa
salida como evidencia para lanzar un claude -p que lo arregle.

Dos fuentes, seleccionadas por entorno:
- API REST de Woodpecker (`KENI_WOODPECKER_API` definido): la vía desacoplada. No depende del
  esquema interno ni del backend (sqlite/postgres) del server.
- SQLite del datastore (`KENI_WOODPECKER_DB`, montado read-only): fallback histórico.

No imprime nada si el último pipeline está verde, corriendo/pendiente, o no hay datos: en esos
casos no hay nada que arreglar. Solo lectura e idempotente (no toca Woodpecker).
"""
import datetime
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

DB = os.environ.get("KENI_WOODPECKER_DB", "/woodpecker/woodpecker.sqlite")
REPO = int(os.environ.get("KENI_KEEPER_REPO_ID", "1"))
API = os.environ.get("KENI_WOODPECKER_API", "").rstrip("/")
TIMEOUT = float(os.environ.get("KENI_WOODPECKER_API_TIMEOUT", "8"))
TERMINAL_FALLO = {"failure", "error"}
# exit_code 126 = el step lo CANCELÓ un push posterior (no es un fallo real). Un pipeline cuyos
# steps en rojo son TODOS 126 está cancelado, no roto: NO se arregla. Con ~7 agentes empujando en
# paralelo las cancelaciones son constantes; sin este filtro el keeper "arreglaría" nada en bucle.
EXIT_CANCELADO = 126
MAX_FALLOS = 80


def _es_fallo_real(linea: str) -> bool:
    return (
        linea.startswith("FAILED ")
        or linea.startswith("ERROR ")
        or "error TS" in linea
        or "AssertionError" in linea
        or "SyntaxError" in linea
        or "contrato-fronteras" in linea
        or "router sin app declarada" in linea
    )


def _token() -> str:
    fichero = os.environ.get("KENI_WOODPECKER_API_TOKEN_FILE", "")
    if fichero and os.path.exists(fichero):
        try:
            with open(fichero, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""
    return os.environ.get("KENI_WOODPECKER_API_TOKEN", "").strip()


def _api_get(path: str):
    """GET a la API de Woodpecker; devuelve JSON parseado (o texto), o None si falla."""
    req = urllib.request.Request(f"{API}{path}")
    tok = _token()
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            cuerpo = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        return json.loads(cuerpo)
    except json.JSONDecodeError:
        return cuerpo


def _ultimo_pipeline_api():
    """Último pipeline vía API: (number, status, message, id) o None."""
    datos = _api_get(f"/api/repos/{REPO}/pipelines?page=1&perPage=1")
    if not isinstance(datos, list) or not datos:
        return None
    p = datos[0]
    return (p.get("number"), p.get("status"), p.get("message") or "", p.get("id"))


def _steps_rojos_api(number):
    """Steps en rojo vía API: lista de (step_id, name, exit_code). El detalle del pipeline trae
    los workflows con sus children (steps)."""
    det = _api_get(f"/api/repos/{REPO}/pipelines/{number}")
    if not isinstance(det, dict):
        return []
    rojos = []
    for wf in det.get("workflows") or []:
        for st in wf.get("children") or []:
            if st.get("state") in TERMINAL_FALLO:
                rojos.append((st.get("id"), st.get("name") or "?", st.get("exit_code")))
    return rojos


def _logs_step_api(number, step_id):
    """Líneas de log de un step vía API. La respuesta es una lista de entradas {data}."""
    datos = _api_get(f"/api/repos/{REPO}/logs/{number}/{step_id}")
    if isinstance(datos, list):
        return [e.get("data", "") for e in datos if isinstance(e, dict)]
    if isinstance(datos, str):
        return datos.splitlines()
    return []


def _con_sqlite():
    if not os.path.exists(DB):
        return None
    try:
        return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None


def _ultimo_pipeline_sqlite():
    """Último pipeline vía sqlite: (number, status, message, id) o None."""
    con = _con_sqlite()
    if con is None:
        return None
    try:
        fila = con.execute(
            "SELECT number, status, message, id FROM pipelines WHERE repo_id=? "
            "ORDER BY number DESC LIMIT 1",
            (REPO,),
        ).fetchone()
        return fila
    except sqlite3.Error:
        return None
    finally:
        con.close()


def ultimo_pipeline():
    """Último pipeline de `main`: (number, status, message, id) o None, según fuente activa."""
    return _ultimo_pipeline_api() if API else _ultimo_pipeline_sqlite()


def fallos_pipeline(number, pid):
    """(steps_en_rojo, lineas_fallo) para un pipeline. `number` para la API, `pid` para sqlite."""
    lineas = []
    fallo_real = False
    if API:
        pasos = _steps_rojos_api(number)
        for sid, sname, exit_code in pasos:
            if exit_code != EXIT_CANCELADO:
                fallo_real = True
            for data in _logs_step_api(number, sid):
                for ln in (data or "").splitlines():
                    if _es_fallo_real(ln):
                        lineas.append(f"[{sname}] {ln.strip()}")
                        fallo_real = True
        return pasos, lineas, fallo_real

    con = _con_sqlite()
    if con is None:
        return [], [], False
    try:
        pasos = con.execute(
            "SELECT id, name, exit_code FROM steps WHERE pipeline_id=? AND state IN ('failure','error')",
            (pid,),
        ).fetchall()
        for sid, sname, exit_code in pasos:
            if exit_code != EXIT_CANCELADO:
                fallo_real = True
            for (data,) in con.execute(
                "SELECT CAST(data AS TEXT) FROM log_entries WHERE step_id=? ORDER BY line",
                (sid,),
            ):
                for ln in (data or "").splitlines():
                    if _es_fallo_real(ln):
                        lineas.append(f"[{sname}] {ln.strip()}")
                        fallo_real = True
        return pasos, lineas, fallo_real
    except sqlite3.Error:
        return [], [], False
    finally:
        con.close()


def heartbeat(destino: str, ci_on: str) -> None:
    """Escribe el estado de vigilancia para guardian-ui: si el keeper vigila el CI y qué ve."""
    ult = ultimo_pipeline() if ci_on == "1" else None
    estado = {
        "ci_on": ci_on == "1",
        "ultimo_chequeo": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ultimo_pipeline": (
            {"number": ult[0], "status": ult[1], "message": ult[2]} if ult else None
        ),
    }
    try:
        tmp = destino + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(estado, fh, ensure_ascii=False)
        os.replace(tmp, destino)
    except OSError:
        pass


def main() -> None:
    # Modo heartbeat: `ci_watch.py --heartbeat <estado.json> <ci_on>` y sale.
    if len(sys.argv) >= 4 and sys.argv[1] == "--heartbeat":
        heartbeat(sys.argv[2], sys.argv[3])
        return

    ult = ultimo_pipeline()
    if not ult:
        return
    number, status, message, pid = ult
    if status not in TERMINAL_FALLO:
        return  # verde, corriendo o pendiente: nada que arreglar

    _pasos, lineas, fallo_real = fallos_pipeline(number, pid)

    # Cancelación pura (todos los steps en rojo son exit 126 y ninguna línea de fallo real): NO es
    # un rojo que arreglar; otro push lo canceló. El keeper no debe tocarlo.
    if not fallo_real:
        return

    vistos, fallos = set(), []
    for l in lineas:
        if l not in vistos:
            vistos.add(l)
            fallos.append(l)

    print(f"PIPELINE_ROJO={number}")
    print(f"COMMIT={message}")
    print("FALLOS:")
    print(
        "\n".join(fallos[:MAX_FALLOS])
        if fallos
        else "(steps en rojo con exit!=126 pero sin líneas FAILED/error reconocibles; "
        "consulta los logs del pipeline con el snippet python del rol)"
    )


if __name__ == "__main__":
    main()

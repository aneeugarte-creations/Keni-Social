#!/usr/bin/env python3
"""Watcher de CI para el incident-keeper: decide QUÉ rojo de `main` arreglar, de forma inteligente.

NO mira solo el último pipeline (casi siempre `running` con ~7 agentes empujando: inútil). Mira el
ÚLTIMO que CORRIÓ COMPLETO (con veredicto real: success/failure/error; salta los running/pendientes
y los cancelados) y solo dispara si ESE falló. Así:
- Si el último completo está VERDE, no hay nada que arreglar aunque haya rojos más viejos.
- Si el último completo está ROJO, imprime el bloque (nº de pipeline + commit + fallos REALES de los
  steps en rojo) que el keeper usa como evidencia para lanzar un claude -p.

Además expone `--verde-despues <N>`: sale 0 si existe un pipeline MÁS NUEVO que `N` ya en verde
(success). El keeper lo usa como watchdog para ABORTAR un fix en curso cuando otro commit ya dejó
`main` verde (no arreglar algo ya arreglado).

Dos fuentes, seleccionadas por entorno:
- API REST de Woodpecker (`KENI_WOODPECKER_API` definido): la vía desacoplada. No depende del
  esquema interno ni del backend (sqlite/postgres) del server.
- SQLite del datastore (`KENI_WOODPECKER_DB`, montado read-only): fallback histórico.

Solo lectura e idempotente (no toca Woodpecker).
"""
import datetime
import hashlib
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
# Estados que significan "el pipeline corrió hasta un VEREDICTO real" (no en curso, no cancelado).
# `killed`/`declined`/`blocked`/`skipped` son cancelaciones/saltos: no son un veredicto, se ignoran
# al buscar el último completo (queremos el último que de verdad pasó o falló).
COMPLETADO = {"success", "failure", "error"}
# Cuántos pipelines recientes traer para decidir (cubre de sobra la racha de pushes en paralelo).
PERPAGE = int(os.environ.get("KENI_KEEPER_CI_PERPAGE", "20"))
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


def _pipelines_api(n: int):
    """Últimos `n` pipelines vía API: lista de (number, status, message, id), más nuevo primero."""
    datos = _api_get(f"/api/repos/{REPO}/pipelines?page=1&perPage={n}")
    if not isinstance(datos, list):
        return []
    return [(p.get("number"), p.get("status"), p.get("message") or "", p.get("id")) for p in datos]


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


def _pipelines_sqlite(n: int):
    """Últimos `n` pipelines vía sqlite: lista de (number, status, message, id), más nuevo primero."""
    con = _con_sqlite()
    if con is None:
        return []
    try:
        filas = con.execute(
            "SELECT number, status, message, id FROM pipelines WHERE repo_id=? "
            "ORDER BY number DESC LIMIT ?",
            (REPO, n),
        ).fetchall()
        return [tuple(f) for f in filas]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def pipelines_recientes(n: int = PERPAGE):
    """Últimos `n` pipelines de `main` (más nuevo primero), según la fuente activa."""
    return _pipelines_api(n) if API else _pipelines_sqlite(n)


def ultimo_pipeline():
    """El pipeline MÁS NUEVO (sea cual sea su estado): para el heartbeat de la UI."""
    pls = pipelines_recientes(1)
    return pls[0] if pls else None


def objetivo_rojo(pipelines):
    """El rojo a arreglar = el ÚLTIMO pipeline que CORRIÓ COMPLETO, si falló.

    Recorre del más nuevo al más viejo y se queda con el primero que tenga veredicto real
    (`COMPLETADO`): si es failure/error -> ese es el objetivo; si es success -> None (el último
    completo está verde: nada que arreglar, aunque haya rojos más viejos). Si ninguno corrió
    completo todavía (todos en curso/cancelados) -> None.
    """
    for fila in pipelines:
        status = fila[1]
        if status in COMPLETADO:
            return fila if status in TERMINAL_FALLO else None
    return None


def hay_verde_despues(pipelines, number: int) -> bool:
    """¿Existe un pipeline MÁS NUEVO que `number` ya en verde (success)? (watchdog de aborto)."""
    return any(num is not None and num > number and status == "success"
               for num, status, *_ in pipelines)


def huella_fallos(fallos) -> str:
    """Firma ESTABLE del conjunto de fallos (independiente del nº de pipeline): mismos fallos ->
    misma huella. Sirve para que el keeper sepa si un rojo nuevo es 'lo mismo' que ya está
    arreglando (lag de propagación) o algo distinto."""
    norm = sorted({(l or "").strip() for l in fallos if (l or "").strip()})
    return hashlib.sha1("\n".join(norm).encode("utf-8")).hexdigest()[:16] if norm else ""


def verdicto_fix(sha: str) -> str:
    """Veredicto de un fix PUSHEADO por el keeper (commit `sha`), por ETAPAS VERDES (no por push):
      - resuelto:    el pipeline de ESE commit está VERDE -> el fix del keeper funcionó.
      - abortado:    el de ese commit NO está verde pero hay uno MÁS NUEVO verde -> main quedó sano
                     por OTRO commit (de otro agente), no por el fix del keeper.
      - fallido:     el de ese commit está ROJO y no hay verde más nuevo -> el fix no bastó.
      - verificando: el de ese commit aún corre (y main no está verde por otro) -> esperar.
    """
    if not API or not sha:
        return "verificando"
    raw = _api_get(f"/api/repos/{REPO}/pipelines?page=1&perPage={PERPAGE}")
    if not isinstance(raw, list):
        return "verificando"
    mio_num, mio_status = None, None
    for p in raw:
        c = p.get("commit") or ""
        if c and (c.startswith(sha) or sha.startswith(c)):
            mio_num, mio_status = p.get("number"), p.get("status")
            break
    verde_nuevo = any(
        p.get("status") == "success" and mio_num is not None and (p.get("number") or 0) > mio_num
        for p in raw
    )
    if mio_status == "success":
        return "resuelto"
    if mio_status in TERMINAL_FALLO:
        return "abortado" if verde_nuevo else "fallido"
    if mio_num is None:
        # El pipeline del commit del keeper no está entre los recientes (aún no creado / desplazado):
        # si el último COMPLETO no es rojo y hay algún verde, main está sano por otro -> abortado.
        objetivo = objetivo_rojo(
            [(p.get("number"), p.get("status"), p.get("message") or "", p.get("id")) for p in raw]
        )
        if objetivo is None and any(p.get("status") == "success" for p in raw):
            return "abortado"
    return "verificando"


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


def imprimir_logs(number, cola: int = 200) -> None:
    """Vuelca los steps en ROJO del pipeline `number` y la COLA de sus logs (donde suele estar el
    traceback/resumen), vía la API de Woodpecker. Es lo que usa el keeper-agent para profundizar:
    su contenedor NO tiene montado el datastore sqlite, pero SÍ habla con la API."""
    if not API:
        print("(sin KENI_WOODPECKER_API: no puedo consultar Woodpecker; revisa el entorno del keeper)")
        return
    pasos = _steps_rojos_api(number)
    if not pasos:
        print(f"(pipeline #{number}: la API no devuelve steps en rojo; ¿nº correcto / token válido?)")
        return
    for sid, sname, exit_code in pasos:
        print(f"===== step «{sname}» (exit {exit_code}) =====")
        lineas = []
        for data in _logs_step_api(number, sid):
            lineas.extend((data or "").splitlines())
        for ln in lineas[-cola:]:
            print(ln)
        print()


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

    # Modo watchdog: `ci_watch.py --verde-despues <N>` -> sale 0 si hay un pipeline > N en verde.
    if len(sys.argv) >= 3 and sys.argv[1] == "--verde-despues":
        try:
            n = int(sys.argv[2])
        except ValueError:
            sys.exit(1)
        sys.exit(0 if hay_verde_despues(pipelines_recientes(), n) else 1)

    # Modo logs: `ci_watch.py --logs <N>` -> vuelca los steps en rojo + cola de logs (para el agente).
    if len(sys.argv) >= 3 and sys.argv[1] == "--logs":
        try:
            n = int(sys.argv[2])
        except ValueError:
            sys.exit(1)
        imprimir_logs(n)
        return

    # Modo veredicto: `ci_watch.py --verdicto-fix <sha>` -> resuelto/fallido/abortado/verificando.
    if len(sys.argv) >= 3 and sys.argv[1] == "--verdicto-fix":
        print(verdicto_fix(sys.argv[2]))
        return

    obj = objetivo_rojo(pipelines_recientes())
    if not obj:
        return  # el último pipeline COMPLETO está verde (o ninguno corrió completo): nada que arreglar
    number, status, message, pid = obj

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
    print(f"HUELLA={huella_fallos(fallos)}")
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

#!/usr/bin/env python3
"""Watcher de CI para el incident-keeper: replica el disparo del "green keeper".

Lee el datastore de Woodpecker (SQLite, montado read-only) y, si el ÚLTIMO pipeline de `main`
está ROJO (estado terminal failure/error), imprime un bloque con el número del pipeline, el
mensaje del commit y los fallos REALES de los steps en rojo (FAILED/ERROR/error TS/violaciones de
frontera). El keeper usa esa salida como evidencia para lanzar un claude -p que lo arregle.

No imprime nada si el último pipeline está verde, corriendo/pendiente, o no hay datos: en esos
casos no hay nada que arreglar. La conexión es read-only e idempotente (no toca Woodpecker).
"""
import os
import sqlite3
import sys

DB = os.environ.get("KENI_WOODPECKER_DB", "/woodpecker/woodpecker.sqlite")
REPO = int(os.environ.get("KENI_KEEPER_REPO_ID", "1"))
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


def main() -> None:
    if not os.path.exists(DB):
        return
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return
    cur = con.cursor()
    fila = cur.execute(
        "SELECT id, number, status, message FROM pipelines "
        "WHERE repo_id=? ORDER BY number DESC LIMIT 1",
        (REPO,),
    ).fetchone()
    if not fila:
        return
    pid, number, status, message = fila
    if status not in TERMINAL_FALLO:
        return  # verde, corriendo o pendiente: nada que arreglar

    pasos = cur.execute(
        "SELECT id, name, exit_code FROM steps WHERE pipeline_id=? AND state IN ('failure','error')",
        (pid,),
    ).fetchall()

    lineas = []
    fallo_real = False
    for sid, sname, exit_code in pasos:
        # Un step con exit != 126 es un fallo de verdad (1 = test/frontera, 2 = build/tsc, ...).
        if exit_code != EXIT_CANCELADO:
            fallo_real = True
        for (data,) in cur.execute(
            "SELECT CAST(data AS TEXT) FROM log_entries WHERE step_id=? ORDER BY line",
            (sid,),
        ):
            for ln in (data or "").splitlines():
                if _es_fallo_real(ln):
                    lineas.append(f"[{sname}] {ln.strip()}")
                    fallo_real = True

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

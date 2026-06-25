#!/usr/bin/env python3
"""Escribe/actualiza el meta de una sesión del incident-keeper (para guardian-ui).

Uso:  python3 sesion.py <meta.json> <jsonl|-> clave=valor clave=valor ...

- Parte del meta existente (si lo hay) y le aplica los `clave=valor` del argv (valores arbitrarios,
  pasados como argv => sin re-parseo del shell, seguros con comillas/saltos).
- Si <jsonl> existe y no es "-", parsea su ÚLTIMA línea `type=="result"` (el evento final de
  `claude -p --output-format stream-json`) y añade coste/tokens/turnos/is_error. Así el coste lo
  calcula el keeper (que produjo los datos) y guardian-ui sólo lo muestra, sin acoplarse a nada.
- Escritura atómica (tmp + replace).
"""
import json
import os
import sys


def _coste_del_jsonl(ruta: str) -> dict:
    resultado = None
    try:
        with open(ruta, encoding="utf-8", errors="replace") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    obj = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("type") == "result":
                    resultado = obj  # nos quedamos con el ÚLTIMO result
    except OSError:
        return {}
    if not resultado:
        return {}
    uso = resultado.get("usage") or {}
    return {
        "coste_usd": resultado.get("total_cost_usd"),
        "num_turns": resultado.get("num_turns"),
        "is_error": resultado.get("is_error"),
        "tokens_in": uso.get("input_tokens"),
        "tokens_out": uso.get("output_tokens"),
        "duracion_ms": resultado.get("duration_ms"),
    }


def main() -> None:
    if len(sys.argv) < 3:
        return
    meta_path, jsonl = sys.argv[1], sys.argv[2]

    data: dict = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}

    for arg in sys.argv[3:]:
        if "=" in arg:
            clave, valor = arg.split("=", 1)
            # cadenas vacías => no piso un valor previo con "" (p.ej. commit_sha sin commit)
            if valor != "" or clave not in data:
                data[clave] = valor

    if jsonl and jsonl != "-" and os.path.exists(jsonl):
        coste = _coste_del_jsonl(jsonl)
        data.update({k: v for k, v in coste.items() if v is not None})

    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, meta_path)


if __name__ == "__main__":
    main()

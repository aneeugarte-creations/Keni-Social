#!/usr/bin/env python3
"""Escribe/actualiza el meta de una sesión del incident-keeper (para guardian-ui).

Uso:  python3 sesion.py <meta.json> <jsonl|-> clave=valor clave=valor ...

- Parte del meta existente (si lo hay) y le aplica los `clave=valor` del argv (valores arbitrarios,
  pasados como argv => sin re-parseo del shell, seguros con comillas/saltos).
- Si <jsonl> existe y no es "-", parsea su ÚLTIMA línea `type=="result"` (el evento final de
  `claude -p --output-format stream-json`) y añade coste/tokens/turnos/is_error. Así el coste lo
  calcula el keeper (que produjo los datos) y guardian-ui sólo lo muestra, sin acoplarse a nada.
- Si la sesión murió contra el LÍMITE de uso de la cuenta (un 429/`rate_limit_event`: la cuenta
  agotó su cuota y `claude -p` ni arrancó), marca `estado=bloqueado-limite` con el motivo y el
  instante de reset, para que la UI no lo confunda con un `escalado` que pide diagnóstico humano.
- Escritura atómica (tmp + replace).
"""
import datetime
import json
import os
import sys


def _epoch_a_iso(epoch) -> str | None:
    """Epoch (segundos UTC) -> ISO "2026-07-01T07:00:00Z", o None si no es un entero válido."""
    try:
        return datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _resumen_del_jsonl(ruta: str) -> dict:
    """Recorre el stream-json una vez: saca coste/tokens del último `result` y detecta si la
    sesión chocó con el límite de uso de la cuenta (rate limit / 429)."""
    resultado = None
    rate_info = None
    texto_limite = None
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
                if not isinstance(obj, dict):
                    continue
                tipo = obj.get("type")
                if tipo == "result":
                    resultado = obj  # nos quedamos con el ÚLTIMO result
                elif tipo == "rate_limit_event":
                    info = obj.get("rate_limit_info")
                    if isinstance(info, dict) and info.get("status") == "rejected":
                        rate_info = info
                elif tipo == "assistant":
                    # El mensaje sintético del límite ("You've hit your weekly limit…") es texto.
                    msg = obj.get("message") or {}
                    for bloque in msg.get("content") or []:
                        if isinstance(bloque, dict) and bloque.get("type") == "text":
                            t = (bloque.get("text") or "").strip()
                            if t:
                                texto_limite = t
    except OSError:
        return {}

    datos: dict = {}
    if resultado:
        uso = resultado.get("usage") or {}
        datos.update(
            {
                "coste_usd": resultado.get("total_cost_usd"),
                "num_turns": resultado.get("num_turns"),
                "is_error": resultado.get("is_error"),
                "tokens_in": uso.get("input_tokens"),
                "tokens_out": uso.get("output_tokens"),
                "duracion_ms": resultado.get("duration_ms"),
            }
        )

    es_limite = rate_info is not None or (
        isinstance(resultado, dict) and resultado.get("api_error_status") == 429
    )
    if es_limite:
        mensaje = None
        if isinstance(resultado, dict):
            mensaje = (resultado.get("result") or "").strip() or None
        mensaje = mensaje or texto_limite
        datos["estado"] = "bloqueado-limite"  # pisa el `escalado` que pasa keeper.sh
        datos["bloqueo_motivo"] = "limite-uso"
        if rate_info and rate_info.get("rateLimitType"):
            datos["bloqueo_tipo"] = rate_info.get("rateLimitType")
        reset_iso = _epoch_a_iso(rate_info.get("resetsAt")) if rate_info else None
        if reset_iso:
            datos["bloqueo_reset_iso"] = reset_iso
        if mensaje:
            datos["bloqueo_mensaje"] = mensaje

    return datos


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
        resumen = _resumen_del_jsonl(jsonl)
        data.update({k: v for k, v in resumen.items() if v is not None})

    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, meta_path)


if __name__ == "__main__":
    main()

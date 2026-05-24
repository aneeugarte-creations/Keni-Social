"""Notificador PROACTIVO: empuja un digest de picos (+ resumen) a un webhook.

╔══════════════════════════════════════════════════════════════════════════╗
║  SEGURIDAD — ESTO ENVIA A LA RED. LEER ANTES DE TOCAR.                     ║
║                                                                            ║
║  SAFE BY DEFAULT: por defecto NO se hace NINGUNA peticion de red.          ║
║   - Sin `KENI_WEBHOOK_URL` configurada O sin la bandera `--enviar`, la     ║
║     CLI SOLO PREVISUALIZA el payload (lo imprime) — CERO red.              ║
║   - Un POST REAL ocurre SOLO si hay URL configurada Y se pasa `--enviar`.  ║
║     Si se pide `--enviar` sin URL, se aborta ANTES de tocar la red.        ║
║   - Ningun camino por defecto (ni los tests) alcanza un endpoint en vivo.  ║
║                                                                            ║
║  Misma disciplina dry-run que `publicacion/meta.py`: el humano decide;     ║
║  nada sale solo. La fuente por defecto es `muestra` (offline).             ║
╚══════════════════════════════════════════════════════════════════════════╝

El detector de picos (`picos.detectar_picos`) ya marca anomalias, pero solo se
ven si alguien corre la tool. Esto cierra el lazo: arma el digest y lo empuja a
un webhook (Slack o un endpoint JSON generico), pensado para cron/launchd.

    python -m keni_metricas.notificaciones                 # preview (cero red)
    python -m keni_metricas.notificaciones --enviar        # POST real (si hay URL)

Config por entorno:
- `KENI_WEBHOOK_URL`      destino del POST. Sin ella => solo preview.
- `KENI_WEBHOOK_FORMATO`  `slack` (payload `{"text": ...}`) | `generico` (def).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import TYPE_CHECKING

from .formato import miles

# NO se modifican estos modulos: se importan de SOLO LECTURA.
from .fuentes._http import cliente_http, log, post_json

if TYPE_CHECKING:
    from .fuentes.base import FuenteMetricas
    from .historico import Historico

FORMATOS = ("generico", "slack")


def construir_digest(
    fuente: FuenteMetricas,
    rango: str = "semana",
    umbral_pct: int = 50,
    historico: Historico | None = None,
    incluir_resumen: bool = False,
) -> dict:
    """Arma el digest (picos + opcionalmente un resumen corto). Funcion PURA: SIN red.

    Reutiliza `picos.detectar_picos`/`render_markdown`. Si `incluir_resumen`,
    agrega los totales del reporte consolidado (sin desglose, para mantenerlo
    breve para un webhook).
    """
    from . import picos as picos_mod

    picos_rep = picos_mod.detectar_picos(fuente, rango, umbral_pct, historico)
    digest: dict = {
        "fuente": fuente.nombre,
        "rango": rango,
        "generado": picos_rep["generado"],
        "picos": picos_rep,
        "picos_markdown": picos_mod.render_markdown(picos_rep),
        "n_alertas": len(picos_rep["alertas"]),
    }

    if incluir_resumen:
        from .reporte import construir_reporte

        rep = construir_reporte(fuente, rango, top=0, historico=historico)
        digest["resumen"] = {
            "total": rep["total"],
            "cobertura": rep.get("cobertura"),
        }

    return digest


def _texto_digest(digest: dict) -> str:
    """Texto plano legible del digest (encabezado + markdown de picos)."""
    out: list[str] = [f"Keni · alertas de redes ({digest['rango']}) — fuente: {digest['fuente']}"]
    if (resumen := digest.get("resumen")) is not None:
        t = resumen["total"]
        out.append(
            f"Total: {miles(t['visualizaciones'])} vis · {miles(t['alcance'])} alcance · "
            f"{t['engagement_pct']}% eng · {t['cuentas']} cuentas"
        )
    out.append("")
    out.append(digest["picos_markdown"])
    return "\n".join(out)


def formatear_payload(digest: dict, formato: str = "generico") -> dict:
    """Convierte el digest en el body JSON a postear. Funcion PURA: SIN red.

    - `slack`:    `{"text": <texto plano del digest>}` (compatible con incoming
                  webhooks de Slack y muchos clones que aceptan ese shape).
    - `generico`: el digest entero como JSON, mas un `text` de cortesia para
                  consumidores que solo miran ese campo.
    """
    if formato not in FORMATOS:
        raise ValueError(f"Formato no soportado: {formato!r}. Usa uno de: {', '.join(FORMATOS)}")

    texto = _texto_digest(digest)
    if formato == "slack":
        return {"text": texto}
    # generico: payload rico + texto de cortesia.
    return {
        "text": texto,
        "fuente": digest["fuente"],
        "rango": digest["rango"],
        "generado": digest["generado"],
        "n_alertas": digest["n_alertas"],
        "picos": digest["picos"],
        **({"resumen": digest["resumen"]} if "resumen" in digest else {}),
    }


def enviar(payload: dict, url: str, cliente=None) -> dict:
    """POST REAL del payload al webhook. Reutiliza `_http.post_json`/`cliente_http`.

    NO se llama nunca por defecto: solo desde el camino `--enviar` con URL. Aqui
    SI se toca la red. Devuelve la respuesta JSON del webhook.
    """
    cli = cliente or cliente_http()
    log.info("Notificaciones: POST a webhook (%s alertas)", payload.get("n_alertas", "?"))
    return post_json(cli, url, json=payload)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m keni_metricas.notificaciones",
        description="Empuja un digest de picos (+ resumen) a un webhook. SAFE BY DEFAULT: "
        "sin --enviar (o sin KENI_WEBHOOK_URL) SOLO previsualiza, sin tocar la red.",
    )
    ap.add_argument("--rango", default="semana", help="semana | mes | 7d | 30d (def: semana)")
    ap.add_argument("--umbral", type=int, default=50, help="umbral %% para marcar picos (def: 50)")
    ap.add_argument(
        "--resumen", action="store_true", help="incluye los totales del reporte consolidado"
    )
    ap.add_argument(
        "--formato",
        choices=list(FORMATOS),
        help="formato del payload; def: $KENI_WEBHOOK_FORMATO o 'generico'",
    )
    ap.add_argument(
        "--enviar",
        action="store_true",
        help="HACE el POST real (requiere KENI_WEBHOOK_URL). Sin esta bandera: solo preview.",
    )
    args = ap.parse_args(argv)

    formato = args.formato or os.environ.get("KENI_WEBHOOK_FORMATO") or "generico"
    if formato not in FORMATOS:
        print(
            f"Error: KENI_WEBHOOK_FORMATO={formato!r} invalido. Usa: {', '.join(FORMATOS)}.",
            file=sys.stderr,
        )
        return 2

    url = os.environ.get("KENI_WEBHOOK_URL") or ""

    from .config import cargar_config, construir_fuente
    from .historico import Historico, historico_activo

    fuente = construir_fuente(cargar_config())
    historico = Historico() if historico_activo() else None
    try:
        digest = construir_digest(
            fuente, args.rango, args.umbral, historico, incluir_resumen=args.resumen
        )
        payload = formatear_payload(digest, formato)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # --- decision de seguridad: enviar de verdad SOLO con --enviar Y URL --------
    if args.enviar and not url:
        # Se pidio enviar pero no hay destino: abortar ANTES de tocar la red.
        print(
            "Error: --enviar requiere KENI_WEBHOOK_URL configurada. No se hizo ninguna "
            "peticion de red.",
            file=sys.stderr,
        )
        return 2

    if not args.enviar or not url:
        # CAMINO POR DEFECTO: preview puro. CERO red.
        motivo = "sin --enviar" if not args.enviar else "sin KENI_WEBHOOK_URL"
        print(f"# PREVIEW notificacion ({motivo}) — formato {formato}")
        print(f"# Destino: {url or '(no configurado)'}")
        print("# NADA se ha enviado. Esto es lo que se postearia:\n")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(
            "\n# Para enviar de verdad: configura KENI_WEBHOOK_URL y pasa --enviar.",
            file=sys.stderr,
        )
        return 0

    # --- CAMINO REAL: solo aqui se toca la red (URL + --enviar) ------------------
    try:
        resp = enviar(payload, url)
    except Exception as e:  # noqa: BLE001 — degradar limpio sin volcar stacktrace al cron
        print(f"Error al enviar al webhook: {e}", file=sys.stderr)
        return 1
    print(f"Notificacion enviada a {url} ({digest['n_alertas']} alertas). Respuesta: {resp!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

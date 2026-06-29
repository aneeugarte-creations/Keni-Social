"""Tests de sesion.py: el meta que guardian-ui lee. Stdlib puro (sin Postgres)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sesion  # noqa: E402

# Recorte real del stream-json de una sesión que murió contra el límite semanal (429).
JSONL_LIMITE = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init", "session_id": "x"}),
        json.dumps(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {
                    "status": "rejected",
                    "resetsAt": 1782889200,
                    "rateLimitType": "seven_day",
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "You've hit your weekly limit · resets Jul 1, 7am (UTC)"}
                    ],
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "api_error_status": 429,
                "result": "You've hit your weekly limit · resets Jul 1, 7am (UTC)",
                "num_turns": 1,
                "duration_ms": 323,
                "total_cost_usd": 0,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        ),
    ]
)

# Sesión normal resuelta: un result con coste y tokens, sin rate limit.
JSONL_OK = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps(
            {
                "type": "result",
                "is_error": False,
                "num_turns": 7,
                "duration_ms": 42000,
                "total_cost_usd": 0.1234,
                "usage": {"input_tokens": 1500, "output_tokens": 800},
            }
        ),
    ]
)


def _escribir(tmp_path, contenido):
    ruta = tmp_path / "s.jsonl"
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)


def test_epoch_a_iso():
    assert sesion._epoch_a_iso(1782889200) == "2026-07-01T07:00:00Z"
    assert sesion._epoch_a_iso(None) is None
    assert sesion._epoch_a_iso("no") is None


def test_resumen_detecta_limite(tmp_path):
    r = sesion._resumen_del_jsonl(_escribir(tmp_path, JSONL_LIMITE))
    assert r["estado"] == "bloqueado-limite"
    assert r["bloqueo_motivo"] == "limite-uso"
    assert r["bloqueo_tipo"] == "seven_day"
    assert r["bloqueo_reset_iso"] == "2026-07-01T07:00:00Z"
    assert "weekly limit" in r["bloqueo_mensaje"]
    assert r["is_error"] is True
    assert r["tokens_in"] == 0 and r["tokens_out"] == 0


def test_resumen_sesion_normal_no_marca_limite(tmp_path):
    r = sesion._resumen_del_jsonl(_escribir(tmp_path, JSONL_OK))
    assert "estado" not in r  # no pisa el estado que pasa keeper.sh
    assert "bloqueo_motivo" not in r
    assert r["coste_usd"] == 0.1234
    assert r["num_turns"] == 7
    assert r["tokens_in"] == 1500 and r["tokens_out"] == 800


def test_main_escribe_meta_con_bloqueo(tmp_path):
    jsonl = _escribir(tmp_path, JSONL_LIMITE)
    meta = tmp_path / "m.meta.json"
    argv = ["sesion.py", str(meta), jsonl, "estado=escalado", "trigger=CI #16", "commit_sha="]
    old = sys.argv
    sys.argv = argv
    try:
        sesion.main()
    finally:
        sys.argv = old
    data = json.loads(meta.read_text(encoding="utf-8"))
    # El límite PISA el escalado que pasa keeper.sh, y conserva el resto del meta.
    assert data["estado"] == "bloqueado-limite"
    assert data["trigger"] == "CI #16"
    assert data["bloqueo_reset_iso"] == "2026-07-01T07:00:00Z"

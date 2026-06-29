"""Tests de guardian-ui app.py: el respaldo de transcript cuando no hay stream_event."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def _jsonl(tmp_path, lineas):
    ruta = tmp_path / "s.jsonl"
    ruta.write_text("\n".join(json.dumps(o) for o in lineas), encoding="utf-8")
    return ruta


def test_transcript_respaldo_cuando_no_hay_stream(tmp_path):
    # Una sesión que muere en un 429 NO emite stream_event: el motivo vive en assistant/result.
    ruta = _jsonl(
        tmp_path,
        [
            {"type": "system", "subtype": "init"},
            {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}},
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "You've hit your weekly limit"}]},
            },
            {"type": "result", "is_error": True, "result": "You've hit your weekly limit"},
        ],
    )
    items = app._transcript(ruta)
    assert len(items) == 1
    assert items[0]["tipo"] == "texto"
    assert "weekly limit" in items[0]["texto"]


def test_transcript_prefiere_stream_event(tmp_path):
    # Con stream_event real, el respaldo NO se usa.
    ruta = _jsonl(
        tmp_path,
        [
            {
                "type": "stream_event",
                "event": {"type": "content_block_start", "content_block": {"type": "thinking"}},
            },
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "thinking_delta", "thinking": "déjame mirar el CI"},
                },
            },
            {"type": "stream_event", "event": {"type": "content_block_stop"}},
            {"type": "result", "result": "no debería aparecer"},
        ],
    )
    items = app._transcript(ruta)
    assert len(items) == 1
    assert items[0]["tipo"] == "razonamiento"
    assert "déjame mirar el CI" in items[0]["texto"]


def test_transcript_muestra_comando_de_la_herramienta(tmp_path):
    # Una acción Bash debe mostrar el COMANDO (input_json_delta), no un "🔧 Bash" pelado.
    ruta = _jsonl(
        tmp_path,
        [
            {"type": "stream_event", "event": {"type": "content_block_start",
             "content_block": {"type": "tool_use", "name": "Bash"}}},
            {"type": "stream_event", "event": {"type": "content_block_delta",
             "delta": {"type": "input_json_delta", "partial_json": '{"command": "git '}}},
            {"type": "stream_event", "event": {"type": "content_block_delta",
             "delta": {"type": "input_json_delta", "partial_json": 'fetch origin"}'}}},
            {"type": "stream_event", "event": {"type": "content_block_stop"}},
        ],
    )
    items = app._transcript(ruta)
    assert len(items) == 1
    assert items[0]["tipo"] == "accion"
    assert items[0]["texto"] == "🔧 Bash: git fetch origin"
    assert "_tool" not in items[0] and "_json" not in items[0]  # claves internas limpiadas


def test_resumen_tool():
    assert app._resumen_tool("Bash", {"command": "ls -la\n  /tmp"}) == "ls -la /tmp"
    assert app._resumen_tool("Read", {"file_path": "/repo/x.py"}) == "/repo/x.py"
    assert app._resumen_tool("Grep", {"pattern": "FAILED"}) == "FAILED"
    assert app._resumen_tool("Bash", {}) == ""


def test_texto_evento():
    assert app._texto_evento({"type": "result", "result": "hola"}) == "hola"
    assert (
        app._texto_evento(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "ey"}]}}
        )
        == "ey"
    )
    assert app._texto_evento({"type": "system"}) is None
    assert app._texto_evento({"type": "result", "result": ""}) is None

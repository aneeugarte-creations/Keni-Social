"""Pruebas PURAS del reparto de notificaciones (`dominio/notificaciones`).

Sin red ni Postgres: solo validan que el módulo carga y que los resúmenes legibles que
verá el "cajón" salen bien por tipo. El reparto real (a quién se notifica) se ejercita
con el resto de la suite de colaboración (que sí monta Postgres).
"""

from __future__ import annotations

from keni_consola.dominio import notificaciones as n


def test_tipos_canonicos():
    assert n.TIPOS == (
        "mencion",
        "comentario",
        "aprobacion",
        "rechazo",
        "pieza",
        "asignacion",
        "revision",
        "sistema",
    )


def test_resumen_por_tipo():
    assert "te mencionó" in n._resumen("mencion", "Diana", "Gol de último minuto")
    assert "comentó" in n._resumen("comentario", "Elías", "Gol de último minuto")
    assert "dio su OK" in n._resumen("aprobacion", "Mariana", "Gol de último minuto")
    assert "rechazó" in n._resumen("rechazo", "Lalo", "Gol de último minuto")
    # La publicación no tiene actor humano; la red entra en el resumen si se pasa.
    resumen_pub = n._resumen("pieza", "", "Gol de último minuto", "Instagram")
    assert "Se publicó" in resumen_pub and "Instagram" in resumen_pub
    # Asignación: el manager te empuja una pieza (la señal que retira el "te paso esto").
    assert "te asignó" in n._resumen("asignacion", "Elías", "Gol de último minuto")


def test_resumen_incluye_titulo_entre_comillas():
    assert "«Gol»" in n._resumen("comentario", "Diana", "Gol")


def test_resumen_titulo_vacio_cae_en_generico():
    # Sin actor conocido, el resumen usa "Alguien" como sujeto.
    assert n._resumen("comentario", "", "Algo").startswith("Alguien")


def _capturar_reparto(monkeypatch, coordinadores: set[str]):
    """Parchea coordinadores + persistencia y devuelve la lista de notis creadas."""
    creadas: list[dict] = []
    monkeypatch.setattr(n, "_coordinadores_de_marca", lambda _m: coordinadores)
    monkeypatch.setattr(
        n.repos, "crear_notificacion", lambda **kw: creadas.append(kw) or kw
    )
    return creadas


def test_avance_lote_notifica_agregado_a_coordinadores(monkeypatch):
    """UN aviso por coordinador con el CONTEO del barrido (nunca uno por pieza)."""
    creadas = _capturar_reparto(monkeypatch, {"coord-1", "coord-2"})
    n.tras_avance_lote("unotv", 3)
    assert len(creadas) == 2  # una por coordinador, no por pieza
    assert all(c["tipo"] == "revision" for c in creadas)
    assert all(c["marca_id"] == "unotv" for c in creadas)
    assert all("3 piezas nuevas" in c["resumen"] for c in creadas)


def test_avance_lote_singular_y_ceros(monkeypatch):
    creadas = _capturar_reparto(monkeypatch, {"coord-1"})
    n.tras_avance_lote("unotv", 1)
    assert len(creadas) == 1 and "1 pieza nueva" in creadas[0]["resumen"]
    creadas.clear()
    # Sin piezas o sin marca no hay nada que avisar.
    n.tras_avance_lote("unotv", 0)
    n.tras_avance_lote("", 5)
    assert creadas == []


def test_revision_estancada_notifica_con_umbral(monkeypatch):
    creadas = _capturar_reparto(monkeypatch, {"coord-1"})
    n.tras_revision_estancada("claro-sports", 4, 24)
    assert len(creadas) == 1
    assert creadas[0]["tipo"] == "revision"
    assert creadas[0]["marca_id"] == "claro-sports"
    assert "4 piezas llevan más de 24 h" in creadas[0]["resumen"]


def test_credencial_por_caducar_avisa_a_los_admin(monkeypatch):
    """El aviso de credencial va a los ADMIN y sin marca: es maquinaria, no contenido."""
    creadas = _capturar_reparto(monkeypatch, set())
    monkeypatch.setattr(n, "_admins", lambda: {"admin-1"})

    n.tras_credencial_por_caducar("a", "Claro Sports", caducada=False, horas=1.6)
    assert len(creadas) == 1
    assert creadas[0]["tipo"] == "sistema"
    assert creadas[0]["marca_id"] == ""
    assert "caduca en 2 h" in creadas[0]["resumen"]
    assert "cuenta A (Claro Sports)" in creadas[0]["resumen"]

    creadas.clear()
    n.tras_credencial_por_caducar("a", "", caducada=True, horas=-3)
    assert "caducó" in creadas[0]["resumen"]

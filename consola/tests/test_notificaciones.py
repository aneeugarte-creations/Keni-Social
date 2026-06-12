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
        "publicacion",
        "asignacion",
    )


def test_resumen_por_tipo():
    assert "te mencionó" in n._resumen("mencion", "Diana", "Gol de último minuto")
    assert "comentó" in n._resumen("comentario", "Elías", "Gol de último minuto")
    assert "dio su OK" in n._resumen("aprobacion", "Mariana", "Gol de último minuto")
    assert "rechazó" in n._resumen("rechazo", "Lalo", "Gol de último minuto")
    # La publicación no tiene actor humano; la red entra en el resumen si se pasa.
    resumen_pub = n._resumen("publicacion", "", "Gol de último minuto", "Instagram")
    assert "Se publicó" in resumen_pub and "Instagram" in resumen_pub
    # Asignación: el manager te empuja una pieza (la señal que retira el "te paso esto").
    assert "te asignó" in n._resumen("asignacion", "Elías", "Gol de último minuto")


def test_resumen_incluye_titulo_entre_comillas():
    assert "«Gol»" in n._resumen("comentario", "Diana", "Gol")


def test_resumen_titulo_vacio_cae_en_generico():
    # Sin actor conocido, el resumen usa "Alguien" como sujeto.
    assert n._resumen("comentario", "", "Algo").startswith("Alguien")

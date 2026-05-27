from __future__ import annotations

import pytest

from keni_metricas.dashboard import (
    _ENG_UMBRAL_ALTO,
    _ENG_UMBRAL_BAJO,
    _fecha_legible,
    _sparkline,
    construir_html,
    generar_dashboard,
    main,
)
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.historico import Historico
from keni_metricas.picos import detectar_picos
from keni_metricas.reporte import construir_reporte


def test_dashboard_es_html_autocontenido():
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    # documento HTML valido-ish
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "<html" in html and "</html>" in html
    assert "<style>" in html and "</style>" in html
    # autocontenido: ningun recurso externo / red / JS externo
    assert "<script" not in html.lower()
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()


def test_dashboard_contiene_nombres_de_marca():
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    # nombres legibles de las 5 marcas de la muestra
    for nombre in ["Claro Sports", "UnoTV", "Nacion Gamer", "Piso 15", "Fundacion"]:
        assert nombre in html


def test_dashboard_contiene_totales_y_rango():
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres)

    assert "Dashboard de metricas — mes" in html
    # el total de visualizaciones aparece formateado con separador de miles (punto)
    total_vis = f"{rep['total']['visualizaciones']:,}".replace(",", ".")
    assert total_vis in html
    # engagement global no es comparable entre plataformas heterogeneas (#138):
    # el total lo reporta None y el dashboard lo muestra como "n/d", no un numero.
    assert rep["total"]["engagement_pct"] is None
    assert "n/d" in html


def test_dashboard_incluye_nota_de_cobertura():
    # la muestra siempre tiene cobertura completa -> la nota obligatoria debe aparecer
    html = generar_dashboard(FuenteMuestra(), "semana", top=2)
    assert "Cobertura completa" in html
    assert "NO son datos reales" in html or "respondieron" in html


def test_cobertura_global_usa_nombre_legible_no_slug():
    """C3: el aviso de cobertura parcial a nivel reporte debe mostrar el NOMBRE
    legible de la marca, no el id crudo (regresion: imprimia el slug)."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=2)
    # fuerza cobertura parcial en una marca cuyo nombre difiere del id
    rep["cobertura"] = {"completa": False, "cuentas_parciales": ["claro_sports"]}
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres, "mes")

    aviso = html.split("Cobertura parcial", 1)[1].split("</p>", 1)[0]
    assert "Claro Sports" in aviso  # nombre legible
    assert "claro_sports" not in aviso  # no el slug crudo


def test_dashboard_seccion_de_picos():
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "Alertas (picos)" in html


def test_picos_usan_nombres_legibles_no_slugs():
    """Las alertas (picos) deben mostrar el nombre legible de la marca, no el id
    crudo (regresion: _render_alerta imprimia el slug `piso_15`/`nacion_gamer`)."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres)
    # la seccion de alertas debe usar el nombre legible dentro de <strong>
    for slug, nombre in nombres.items():
        if nombre != slug:  # marcas cuyo nombre difiere del id
            assert f"<strong>{slug}</strong>" not in html


def test_dashboard_escapa_html_de_titulos():
    """Los titulos de contenido se escapan (sin inyeccion de HTML)."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=2)
    # inyecta un titulo malicioso en una pieza
    rep["cuentas"][0]["mejores_piezas"][0]["titulo"] = "<script>alert(1)</script>"
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_dashboard_rango_invalido_propaga():
    with pytest.raises(ValueError):
        generar_dashboard(FuenteMuestra(), "trimestre")


# --- Engagement: metrica north-star ---


def test_dashboard_seccion_engagement_north_star():
    """La seccion north-star aparece con el engagement global y los umbrales."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres, "mes")

    assert "Engagement (north-star)" in html
    assert "Engagement global" in html
    # el engagement global no es comparable entre plataformas heterogeneas (#138):
    # el hero north-star muestra "n/d", no un numero engañoso.
    assert rep["total"]["engagement_pct"] is None
    assert "n/d" in html
    # los umbrales documentados se muestran al lector
    assert str(_ENG_UMBRAL_ALTO) in html
    assert str(_ENG_UMBRAL_BAJO) in html


def test_dashboard_engagement_ranking_color_coded():
    """El ranking por marca clasifica con clases de color y etiquetas de nivel."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert 'class="ranking"' in html
    # al menos una clase de color de engagement aparece
    assert "eng-alto" in html or "eng-medio" in html or "eng-bajo" in html
    # las etiquetas de nivel legibles
    assert ">alto<" in html or ">ok<" in html or ">bajo<" in html


def test_dashboard_engagement_ranking_ordenado_desc():
    """Las marcas se listan de mayor a menor engagement en el ranking."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres, "mes")

    # engagement de cada marca por su nombre legible
    ranking_html = html.split('class="ranking"', 1)[1].split("</ul>", 1)[0]
    eng_por_nombre = {
        nombres[f["resumen"]["cuenta"]]: f["resumen"]["engagement_pct"] for f in rep["cuentas"]
    }
    assert all(ranking_html.find(f">{nombre}<") != -1 for nombre in eng_por_nombre)
    # ordena los nombres por la posicion en que aparecen en el ranking HTML y
    # verifica que su engagement no crece (el dashboard ordena por engagement
    # desc; ante empates respeta el orden de entrada, sin desempate por nombre).
    por_posicion = sorted(eng_por_nombre, key=lambda nom: ranking_html.find(f">{nom}<"))
    engs_en_orden = [eng_por_nombre[nom] for nom in por_posicion]
    assert engs_en_orden == sorted(engs_en_orden, reverse=True)


def test_dashboard_sin_historico_omite_tendencia():
    """Sin historico, no se renderiza la tendencia (y no falla)."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3, historico=None)
    assert "Engagement (north-star)" in html  # la seccion sigue
    assert "Tendencia de engagement" not in html  # pero sin trend


def test_dashboard_con_historico_muestra_tendencia(tmp_path):
    """Con >= 2 snapshots historicos, aparece la tendencia de engagement por marca."""
    from datetime import date

    fuente = FuenteMuestra()
    hist = Historico(tmp_path / "h.db")
    # siembra un periodo previo (fecha fija, distinta de la actual) para cada marca
    for c in fuente.cuentas():
        r = fuente.resumen(c.id, "semana")
        r.periodo.hasta = date(2020, 1, 6)  # periodo claramente anterior y distinto
        hist.guardar(r)

    # genera con historico activo: construir_reporte guarda el snapshot actual,
    # de modo que la serie tendra >= 2 lecturas (la sembrada + la actual).
    html = generar_dashboard(fuente, "semana", top=3, historico=hist)
    assert "Engagement (north-star)" in html
    assert "Tendencia de engagement" in html
    # la tabla de tendencia rinde filas de Periodo y Engagement
    assert "Engagement</td>" in html


def test_dashboard_tendencia_historico_roto_no_explota():
    """Si Historico.serie lanza, la tendencia se omite sin romper el dashboard."""

    class HistoricoRoto:
        def serie(self, *a, **k):
            raise RuntimeError("boom")

    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres, "mes", HistoricoRoto())
    assert "Engagement (north-star)" in html
    assert "Tendencia de engagement" not in html


def test_dashboard_engagement_escapa_nombres():
    """Los nombres de marca en el ranking north-star se escapan."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    cid = rep["cuentas"][0]["resumen"]["cuenta"]
    nombres[cid] = "<b>x</b>"
    html = construir_html(rep, picos, nombres, "mes")
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


# --- T5: CLI (main) y robustez de helpers (pulido demo) ---


def test_main_escribe_html_y_rc_cero(tmp_path):
    """main(['--salida', <tmp>]) escribe el HTML y retorna rc=0."""
    salida = tmp_path / "dash.html"
    rc = main(["--salida", str(salida)])
    assert rc == 0
    assert salida.exists()
    html = salida.read_text(encoding="utf-8")
    assert html.lstrip().startswith("<!DOCTYPE html>")
    # sigue autocontenido tras pasar por el CLI
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html


def test_main_rango_invalido_rc_dos(tmp_path, capsys):
    """--rango invalido -> rc=2 + mensaje en stderr (no escribe el archivo)."""
    salida = tmp_path / "dash.html"
    rc = main(["--salida", str(salida), "--rango", "trimestre"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Error" in err
    assert not salida.exists()


def test_main_argparse_arg_invalido_rc_dos(tmp_path):
    """Un valor no entero para --top hace que argparse aborte con SystemExit(2)."""
    with pytest.raises(SystemExit) as exc:
        main(["--salida", str(tmp_path / "d.html"), "--top", "no-numero"])
    assert exc.value.code == 2


def test_main_presentacion_no_rompe(tmp_path):
    """El flag --presentacion no rompe y marca el body en modo presentacion."""
    salida = tmp_path / "dash.html"
    rc = main(["--salida", str(salida), "--presentacion"])
    assert rc == 0
    html = salida.read_text(encoding="utf-8")
    assert "presentacion" in html  # clase de body activada
    # por defecto (sin el flag) no debe activarse
    salida2 = tmp_path / "dash2.html"
    main(["--salida", str(salida2)])
    assert 'class="raiz presentacion"' not in salida2.read_text(encoding="utf-8")


def test_sparkline_serie_constante_no_divide_por_cero():
    """_sparkline con valores identicos (span 0) no lanza ZeroDivisionError."""
    out = _sparkline([5, 5, 5])
    assert out  # rinde algo
    assert out.count('class="pip"') == 3  # un pip por valor
    # sin entradas tampoco explota
    assert _sparkline([]) == ""


def test_fecha_legible_es_mx():
    """La marca ISO se muestra como fecha es-MX legible ('24 may 2026')."""
    assert _fecha_legible("2026-05-24T17:05:32+00:00") == "24 may 2026"
    assert _fecha_legible("2026-01-01T00:00:00+00:00") == "1 ene 2026"
    # entradas degeneradas: devuelve el original sin lanzar
    assert _fecha_legible("") == ""
    assert _fecha_legible("no-es-fecha") == "no-es-fecha"


def test_dashboard_branding_y_footer_privacidad():
    """UX-2/UX-6/UX-11: eyebrow Keni, fecha legible y footer de privacidad."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "KENI AI" in html and "AMX Contenido" in html  # eyebrow (UX-2)
    assert "Generado en tu máquina" in html  # footer privacidad (UX-11)
    assert "sin red" in html


def test_dashboard_callout_pieza_estrella():
    """UX-7: callout con la pieza de mayor engagement global."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres, "mes")
    assert "Lo que más rompió" in html
    # la pieza del callout es la de mayor engagement entre todas las marcas
    mejor = max(
        (p for f in rep["cuentas"] for p in (f.get("mejores_piezas") or [])),
        key=lambda p: p["engagement_pct"],
    )
    assert f'{mejor["engagement_pct"]}%' in html


def test_dashboard_picos_colapsa_el_resto():
    """UX-1: solo se muestran las primeras alertas; el resto va en un <details>."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    total = len(picos["alertas"])
    html = construir_html(rep, picos, nombres, "mes")
    if total > 6:
        assert "alertas-resto" in html
        assert f"Ver todas las alertas ({total})" in html
    # todas las alertas siguen presentes (visibles + plegadas)
    seccion = html.split("Alertas (picos)", 1)[1].split("<footer", 1)[0]
    assert seccion.count("<li>") == total


def test_dashboard_ranking_barra_con_porcentaje_visible():
    """UX-10: cada barra del ranking muestra el % visible."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert 'class="barra-pct"' in html
    assert 'class="relleno' in html


# --- UX-9: impresion / "Guardar como PDF" (@media print) ---


def test_dashboard_incluye_bloque_media_print():
    """El CSS lleva un bloque @media print para que el PDF del navegador salga limpio."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "@media print" in html
    # los <details> plegados se fuerzan abiertos al imprimir (no esconder info)
    assert "details" in html and "revert" in html
    # se fuerza la impresion de fondos/colores y se evitan cortes feos
    assert "print-color-adjust" in html
    assert "break-inside" in html


def test_dashboard_media_print_sigue_autocontenido():
    """El bloque @media print no introduce recursos externos: sigue autocontenido."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    low = html.lower()
    assert "<script" not in low
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in low
    # ni @import ni url() que carguen recursos remotos en el CSS
    assert "@import" not in low
    assert "url(" not in low


# --- tier-2: pie con leyenda de niveles + criterio del callout estrella ---


def test_dashboard_footer_leyenda_de_niveles():
    """UX-12: el pie incluye una leyenda imprimible de los niveles de engagement."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    seccion = html.split("<footer", 1)[1]
    assert "Niveles de engagement" in seccion
    # los tres niveles con sus umbrales y el icono de la pieza estrella
    assert "eng-alto" in seccion and "eng-medio" in seccion and "eng-bajo" in seccion
    assert str(_ENG_UMBRAL_ALTO) in seccion and str(_ENG_UMBRAL_BAJO) in seccion
    assert "🔥" in seccion


def test_dashboard_callout_estrella_aclara_criterio():
    """UX-10: el callout aclara que se elige por mayor engagement %."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "Lo que más rompió" in html
    assert "mayor engagement %" in html


# --- Accesibilidad (a11y) + responsive (issue #58) ---


def test_dashboard_lang_es_y_meta_viewport():
    """El documento declara idioma espanol y viewport responsive."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert '<html lang="es">' in html
    # viewport para que escale en pantallas angostas / proyeccion vertical
    assert '<meta name="viewport"' in html
    assert "width=device-width" in html


def test_dashboard_title_descriptivo():
    """El <title> describe el contenido e incluye el rango."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "<title>Dashboard de metricas — mes</title>" in html


def test_dashboard_landmarks_semanticos():
    """Estructura semantica: header, main, footer y secciones con encabezado."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    # landmarks
    assert "<main>" in html and "</main>" in html
    assert "<header" in html and "</header>" in html
    assert "<footer" in html and "</footer>" in html
    # secciones etiquetadas por su encabezado (aria-labelledby -> id del <h2>)
    assert "<section aria-labelledby=" in html
    for tid in ("titulo-total", "titulo-engagement", "titulo-marca", "titulo-picos"):
        assert f'id="{tid}"' in html


def test_dashboard_aria_label_en_hero_y_barras():
    """El hero north-star y las barras del ranking exponen su valor a lectores
    de pantalla via role=img + aria-label (comunican valor visualmente)."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres, "mes")

    # hero: figura con etiqueta legible del engagement global
    assert 'class="ns-hero" role="img" aria-label="Engagement global' in html
    # barras del ranking: cada una es una figura con su valor en la etiqueta
    assert 'class="barra" role="img" aria-label=' in html
    # el % superpuesto a la barra es decorativo (no duplica para el lector)
    assert 'class="barra-pct" aria-hidden="true"' in html


def test_dashboard_aria_label_barra_escapa_nombre():
    """El nombre de marca dentro del aria-label de la barra tambien se escapa."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    cid = rep["cuentas"][0]["resumen"]["cuenta"]
    nombres[cid] = '<b>x</b>'
    html = construir_html(rep, picos, nombres, "mes")
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_dashboard_usa_color_de_texto_marca_con_contraste():
    """El acento de marca para TEXTO usa una variante oscura (--marca-texto) que
    cumple contraste AA; el naranja vivo queda para bordes/decoracion."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "--marca-texto:" in html
    # los textos de acento (eyebrow, titulos de callout) usan la variante oscura
    assert "color: var(--marca-texto)" in html


def test_dashboard_incluye_media_query_responsive():
    """Hay un @media (max-width: 640px) para apilar tarjetas/KPIs/ranking."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "@media screen and (max-width: 640px)" in html
    # convive con el bloque de impresion sin pisarlo
    assert "@media print" in html


def test_dashboard_responsive_sigue_autocontenido():
    """Los bloques a11y/responsive no introducen recursos externos."""
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    low = html.lower()
    assert "<script" not in low
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in low
    assert "@import" not in low
    assert "url(" not in low


def test_dashboard_cta_siguiente_paso():
    """Tier-2 (roadmap #11): cierra con un CTA que devuelve a la accion,
    nombrando la marca de mayor engagement del periodo."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres, "mes")

    assert 'class="cta"' in html
    assert "Siguiente paso" in html
    # nombra la marca top por engagement
    mejor = max(rep["cuentas"], key=lambda f: f["resumen"]["engagement_pct"])
    assert nombres[mejor["resumen"]["cuenta"]] in html.split('class="cta"', 1)[1]

"""Tests UNITARIOS de la logica de parrilla (`keni_consola.parrilla`). OFFLINE, sin red.

Cubre:
  - puntuar_tema: pura y deterministica; senales individuales; comparaciones relativas.
  - _clasificar_tipo: posteo vs editorial; subtipo clip/galeria/infografia/normal.
  - armar_parrilla: cuotas 13+6, orden global, sobrantes, parrilla vacia.
"""

from __future__ import annotations

from keni_consola import parrilla, relevancia_marca
from keni_consola.radar import Enlace, Tema

# --------------------------------------------------------------------------- #
# Helpers de construccion de Temas de prueba                                   #
# --------------------------------------------------------------------------- #

def _tema(titulo: str, senal: int = 0, por_que: str = "", fuentes=None, redes=None, n_enlaces: int = 0) -> Tema:
    """Construye un Tema minimal para las pruebas."""
    enlaces = [
        Enlace(titulo=f"Nota {i}", url=f"https://example.com/{i}", fuente="Fuente")
        for i in range(n_enlaces)
    ]
    return Tema(
        titulo=titulo,
        redes=set(redes or {"busquedas-mx"}),
        fuentes=set(fuentes or {"Google Trends"}),
        por_que=por_que,
        senal=senal,
        senal_texto=str(senal) if senal else "",
        enlaces=enlaces,
        _claves_enlace=set(),
    )


# --------------------------------------------------------------------------- #
# puntuar_tema: funcion pura                                                    #
# --------------------------------------------------------------------------- #

class TestPuntuarTema:
    def test_devuelve_score_y_razon(self):
        tema = _tema("Nota de prueba")
        score, razon = parrilla.puntuar_tema(tema)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert isinstance(razon, str) and razon

    def test_determinismo(self):
        tema = _tema("Junior H", senal=2000, por_que="concierto en Mexico")
        r1 = parrilla.puntuar_tema(tema, contexto="MX")
        r2 = parrilla.puntuar_tema(tema, contexto="MX")
        assert r1 == r2

    def test_mas_viral_mas_score(self):
        bajo = _tema("A", senal=100)
        alto = _tema("A", senal=500_000)
        s_bajo, _ = parrilla.puntuar_tema(bajo)
        s_alto, _ = parrilla.puntuar_tema(alto)
        assert s_alto > s_bajo

    def test_relevancia_mx_sube_score(self):
        sin_mx = _tema("Noticia generica internacional")
        con_mx = _tema("Sismo en Ciudad de Mexico CDMX")
        s_sin, _ = parrilla.puntuar_tema(sin_mx)
        s_con, _ = parrilla.puntuar_tema(con_mx)
        assert s_con > s_sin

    def test_mas_fuentes_sube_score(self):
        una = _tema("Evento", redes={"busquedas-mx"}, fuentes={"Fuente1"})
        varias = _tema("Evento", redes={"busquedas-mx", "rss"}, fuentes={"Fuente1", "Fuente2", "Fuente3"})
        s_una, _ = parrilla.puntuar_tema(una)
        s_varias, _ = parrilla.puntuar_tema(varias)
        assert s_varias > s_una

    def test_mas_enlaces_sube_impacto(self):
        sin = _tema("Tema", n_enlaces=0)
        con = _tema("Tema", n_enlaces=3)
        s_sin, _ = parrilla.puntuar_tema(sin)
        s_con, _ = parrilla.puntuar_tema(con)
        assert s_con > s_sin

    def test_razon_menciona_senal_cuando_hay_viralidad(self):
        tema = _tema("Liga MX", senal=50_000, por_que="record de audiencia")
        _, razon = parrilla.puntuar_tema(tema)
        assert "viralidad" in razon.lower() or "50000" in razon

    def test_razon_menciona_mexico_cuando_aplica(self):
        tema = _tema("Sheinbaum anuncia plan en México")
        _, razon = parrilla.puntuar_tema(tema)
        assert "México" in razon or "mexico" in razon.lower()

    def test_score_cero_senal_sin_fuentes(self):
        # Tema completamente vacio: score bajo pero valido (no lanza)
        tema = _tema("Algo", senal=0, redes={"r"}, fuentes={"f"})
        score, _ = parrilla.puntuar_tema(tema)
        assert 0.0 <= score <= 1.0

    def test_contexto_es_parametro_no_afecta_mx_por_defecto(self):
        # El contexto por defecto es MX; si se pasa "US" el comportamiento es distinto
        tema = _tema("Mexico aprueba ley")
        s_mx, _ = parrilla.puntuar_tema(tema, contexto="MX")
        # Con US sigue siendo la misma logica de palabras; solo cambia el contexto string
        s_us, _ = parrilla.puntuar_tema(tema, contexto="US")
        # Ambos deben ser floats validos (no crash)
        assert 0.0 <= s_mx <= 1.0
        assert 0.0 <= s_us <= 1.0


# --------------------------------------------------------------------------- #
# _clasificar_tipo: palabras clave                                              #
# --------------------------------------------------------------------------- #

class TestClasificarTipo:
    def test_clip_por_video(self):
        t = _tema("Video del accidente en carretera")
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "posteo"
        assert subtipo == parrilla.SUBTIPO_CLIP

    def test_clip_por_declaracion(self):
        t = _tema("Declaraciones del presidente en conferencia de prensa")
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "posteo"
        assert subtipo == parrilla.SUBTIPO_CLIP

    def test_galeria_por_fotos(self):
        t = _tema("Fotos de la boda de la estrella")
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "posteo"
        assert subtipo == parrilla.SUBTIPO_GALERIA

    def test_infografia_por_datos(self):
        t = _tema("Top 10 ciudades con mas inflacion en Mexico: datos y cifras")
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "posteo"
        assert subtipo == parrilla.SUBTIPO_INFOGRAFIA

    def test_normal_sin_indicadores(self):
        t = _tema("Nuevo hospital en Monterrey")
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "posteo"
        assert subtipo == parrilla.SUBTIPO_NORMAL

    def test_editorial_por_analisis(self):
        t = _tema("Analisis: por que sube la inflacion en Mexico")
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "editorial"
        assert subtipo == ""

    def test_editorial_por_investigacion(self):
        t = _tema("Investigacion sobre corrupcion en la SEP")
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "editorial"
        assert subtipo == ""

    def test_editorial_por_muchos_enlaces(self):
        # 4+ enlaces sin palabras clave editoriales -> editorial por profundidad
        t = _tema("Crisis politica sin resolver", n_enlaces=4)
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "editorial"
        assert subtipo == ""

    def test_posteo_normal_con_pocos_enlaces(self):
        t = _tema("Nota breve sin indicadores especiales", n_enlaces=2)
        tipo, subtipo = parrilla._clasificar_tipo(t)
        assert tipo == "posteo"

    def test_editorial_por_escandalo(self):
        t = _tema("Escandalo de fraude en empresa pública")
        tipo, _ = parrilla._clasificar_tipo(t)
        assert tipo == "editorial"

    def test_editorial_por_por_que_en_por_que(self):
        t = _tema("Corrupcion en Pemex", por_que="Claves para entender el escandalo")
        tipo, _ = parrilla._clasificar_tipo(t)
        assert tipo == "editorial"


# --------------------------------------------------------------------------- #
# armar_parrilla: integracion de clasificacion + scoring                        #
# --------------------------------------------------------------------------- #

class TestArmarParrilla:
    def test_parrilla_vacia_con_lista_vacia(self):
        p = parrilla.armar_parrilla([])
        assert p.posteos == []
        assert p.editorial == []
        assert p.sobrantes == []
        assert p.total_entrada == 0

    def test_cuota_posteos_respetada(self):
        # 20 temas normales (todos posteos): no mas de 13 en posteos
        temas = [_tema(f"Noticia {i}", senal=100 - i) for i in range(20)]
        p = parrilla.armar_parrilla(temas)
        assert len(p.posteos) <= parrilla.CUOTA_POSTEOS

    def test_cuota_editorial_respetada(self):
        # 10 temas editoriales: no mas de 6 en editorial
        temas = [_tema(f"Analisis del tema {i}", senal=1000 - i) for i in range(10)]
        p = parrilla.armar_parrilla(temas)
        assert len(p.editorial) <= parrilla.CUOTA_EDITORIAL

    def test_sobrantes_cuando_hay_mas_de_cuota(self):
        temas = [_tema(f"Noticia {i}", senal=i) for i in range(20)]
        p = parrilla.armar_parrilla(temas)
        total = len(p.posteos) + len(p.editorial) + len(p.sobrantes)
        assert total == 20  # ningun tema se pierde

    def test_ordenes_asignados_consecutivos(self):
        temas = [_tema(f"Nota {i}", senal=i * 10) for i in range(5)]
        p = parrilla.armar_parrilla(temas)
        todos = sorted(p.posteos + p.editorial + p.sobrantes, key=lambda t: t.orden)
        ordenes = [t.orden for t in todos]
        assert ordenes == list(range(1, len(ordenes) + 1))

    def test_orden_mayor_score_primero(self):
        # El tema mas viral debe tener orden mas bajo (mas prioritario)
        viral = _tema("Tendra el mayor score", senal=1_000_000, por_que="Mexico")
        bajo = _tema("Score bajo", senal=1)
        p = parrilla.armar_parrilla([viral, bajo])
        viral_tc = next(t for t in p.posteos + p.editorial if "mayor score" in t.tema.titulo)
        bajo_tc = next(t for t in p.posteos + p.editorial + p.sobrantes if "Score bajo" in t.tema.titulo)
        assert viral_tc.orden < bajo_tc.orden

    def test_tipo_se_asigna_correctamente(self):
        post = _tema("Video del evento deportivo en Mexico", senal=5000)
        edit = _tema("Analisis del escandalo de corrupcion en gobierno", senal=3000)
        p = parrilla.armar_parrilla([post, edit])
        tipos = {t.tema.titulo: t.tipo for t in p.posteos + p.editorial + p.sobrantes}
        assert tipos.get("Video del evento deportivo en Mexico") == "posteo"
        assert tipos.get("Analisis del escandalo de corrupcion en gobierno") == "editorial"

    def test_total_entrada_correcto(self):
        temas = [_tema(f"T {i}") for i in range(7)]
        p = parrilla.armar_parrilla(temas)
        assert p.total_entrada == 7

    def test_a_dict_incluye_campos_esperados(self):
        temas = [_tema("Noticia de prueba", senal=100)]
        p = parrilla.armar_parrilla(temas)
        d = p.a_dict()
        assert "posteos" in d
        assert "editorial" in d
        assert "sobrantes" in d
        assert d["total_entrada"] == 1
        assert d["cuota_posteos"] == parrilla.CUOTA_POSTEOS
        assert d["cuota_editorial"] == parrilla.CUOTA_EDITORIAL

    def test_tema_clasificado_a_dict_incluye_campos(self):
        temas = [_tema("Nota con datos estadisticos y ranking", senal=200)]
        p = parrilla.armar_parrilla(temas)
        todos = p.posteos + p.editorial
        assert todos
        d = todos[0].a_dict()
        for campo in ("titulo", "tipo", "subtipo", "score", "orden", "razon"):
            assert campo in d, f"Campo '{campo}' ausente en TemaClasificado.a_dict()"

    def test_sin_duplicacion_de_temas(self):
        # Cada tema aparece EXACTAMENTE una vez
        temas = [_tema(f"T{i}", senal=i) for i in range(10)]
        p = parrilla.armar_parrilla(temas)
        todos_titulos = [t.tema.titulo for t in p.posteos + p.editorial + p.sobrantes]
        assert len(todos_titulos) == len(set(todos_titulos))

    def test_contexto_pasa_a_resultado(self):
        temas = [_tema("Noticia")]
        p = parrilla.armar_parrilla(temas, contexto="US")
        assert p.contexto == "US"
        assert p.a_dict()["contexto"] == "US"


# --------------------------------------------------------------------------- #
# Relevancia POR MARCA: la investigacion es por marca, no global                #
# --------------------------------------------------------------------------- #

class TestRelevanciaMarca:
    def test_palabras_de_marca_conocida_y_desconocida(self):
        assert relevancia_marca.palabras_de_marca("claro-sports")  # no vacio
        assert relevancia_marca.palabras_de_marca("inexistente") == frozenset()
        assert relevancia_marca.palabras_de_marca(None) == frozenset()
        assert relevancia_marca.palabras_de_marca("") == frozenset()

    def test_sin_palabras_score_es_el_general(self):
        # Sin palabras de marca, el score debe ser EXACTO al scoring general (base).
        tema = _tema("Final de futbol", senal=5000, por_que="gol en Mexico")
        base, _ = parrilla.puntuar_tema(tema, contexto="MX")
        con_vacio, _ = parrilla.puntuar_tema(tema, contexto="MX", palabras_marca=frozenset())
        assert base == con_vacio

    def test_tema_en_foco_supera_a_fuera_de_foco(self):
        # Con la marca Claro Sports, un tema deportivo gana a uno NO deportivo, aunque
        # el no deportivo sea mas viral: la investigacion es POR MARCA.
        palabras = relevancia_marca.palabras_de_marca("claro-sports")
        deportivo = _tema("Gran final de futbol", senal=1000)
        viral_no_marca = _tema("Receta de pastel viral", senal=900000)
        s_dep, razon_dep = parrilla.puntuar_tema(deportivo, palabras_marca=palabras)
        s_otro, _ = parrilla.puntuar_tema(viral_no_marca, palabras_marca=palabras)
        assert s_dep > s_otro
        assert "marca" in razon_dep

    def test_armar_parrilla_filtra_fuera_de_foco(self):
        # Con marca, el plan SOLO incluye los temas de la marca; el resto NO entra
        # (se reporta como fuera_foco). El Plan del dia muestra LO SUYO.
        palabras = relevancia_marca.palabras_de_marca("claro-sports")
        temas = [
            _tema("Receta viral de la semana", senal=900000),
            _tema("Boxeo: pelea estelar", senal=1500),
            _tema("Chismes de la farandula", senal=50000),
        ]
        p = parrilla.armar_parrilla(temas, palabras_marca=palabras)
        titulos = [t.tema.titulo for t in p.posteos + p.editorial + p.sobrantes]
        assert titulos == ["Boxeo: pelea estelar"]
        assert p.total_entrada == 1
        assert p.fuera_foco == 2
        assert p.a_dict()["total_fuera_foco"] == 2

    def test_tema_en_foco(self):
        palabras = relevancia_marca.palabras_de_marca("claro-sports")
        assert parrilla.tema_en_foco(_tema("Final de futbol"), palabras) is True
        # Acentos: 'fútbol' (como llega del Radar) debe matchear la keyword 'futbol'.
        assert parrilla.tema_en_foco(_tema("Gran final de fútbol"), palabras) is True
        assert parrilla.tema_en_foco(_tema("Receta de pastel"), palabras) is False
        # Sin palabras no hay foco que aplicar.
        assert parrilla.tema_en_foco(_tema("Final de futbol"), frozenset()) is False

    def test_sin_marca_no_filtra(self):
        # Sin marca, NO se filtra nada (fuera_foco 0; entran todos).
        temas = [_tema("A", senal=100), _tema("B", senal=200)]
        p = parrilla.armar_parrilla(temas)
        assert p.total_entrada == 2
        assert p.fuera_foco == 0

    def test_tema_curado_entra_aunque_no_matchee_keyword(self):
        # Un tema CURADO (de una fuente propia de la marca) entra al foco SIEMPRE,
        # aunque su titulo no contenga ninguna palabra clave de la marca.
        palabras = relevancia_marca.palabras_de_marca("claro-sports")
        curado = _tema("Resumen de la jornada", senal=0)  # sin keyword deportiva en el titulo
        curado.curado = True
        normal = _tema("Receta de pastel", senal=0)
        assert parrilla.tema_en_foco(curado, palabras) is True
        assert parrilla.tema_en_foco(normal, palabras) is False
        p = parrilla.armar_parrilla([curado, normal], palabras_marca=palabras)
        titulos = [t.tema.titulo for t in p.posteos + p.editorial + p.sobrantes]
        assert titulos == ["Resumen de la jornada"]
        assert p.fuera_foco == 1

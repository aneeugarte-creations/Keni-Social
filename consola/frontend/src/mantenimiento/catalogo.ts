/**
 * Snapshot del catálogo de navegación (`GET /api/catalogo` → `navegacion`) para la página de
 * MANTENIMIENTO. La página la sirve un contenedor aparte (no el back), así que no puede pedir
 * el catálogo en vivo: se hornea esta foto y se inyecta en la caché de react-query para que el
 * `Sidebar` REAL pinte la barra idéntica a la app.
 *
 * FUENTE DE VERDAD: lo genera `registro.entradas_nav_activas({})` del backend (apps/registro.py,
 * todas las apps activas, como prod por defecto). Para regenerarlo tras tocar un manifest TOML:
 *   cd consola && python3 -c "import importlib.util,json,sys; \
 *     s=importlib.util.spec_from_file_location('r','src/keni_consola/apps/registro.py'); \
 *     m=importlib.util.module_from_spec(s); sys.modules['r']=m; s.loader.exec_module(m); \
 *     print(json.dumps({'apps':[],'navegacion':m.entradas_nav_activas({})},ensure_ascii=False,indent=2))"
 */

export interface ItemCatalogo {
  ruta: string;
  etiqueta: string;
  icono: string;
  descripcion: string;
}

export interface BloqueCatalogo {
  etiqueta: string;
  items: ItemCatalogo[];
}

export interface Catalogo {
  apps: unknown[];
  navegacion: BloqueCatalogo[];
}

export const CATALOGO: Catalogo = {
  apps: [],
  navegacion: [
    {
      etiqueta: "Operación",
      items: [
        {
          ruta: "/operacion/investigacion",
          etiqueta: "Investigación",
          icono: "Search",
          descripcion:
            "El pool de noticias que alimenta la máquina: Noticias, Fuentes, Algoritmos y Contenidos. El pipeline (descubrir/verificar) se controla en Contexto.",
        },
        {
          ruta: "/operacion/feed",
          etiqueta: "Feed",
          icono: "LayoutGrid",
          descripcion:
            "El feed de ideación del equipo (piezas como posts, aprobación en línea) y la lista de contenido.",
        },
        {
          ruta: "/operacion/programa",
          etiqueta: "Programa",
          icono: "CalendarDays",
          descripcion:
            "Calendario de publicaciones y el plan de líneas (hashtag y keywords), por marca.",
        },
      ],
    },
    {
      etiqueta: "Equipo",
      items: [
        {
          ruta: "/equipo/trabajo",
          etiqueta: "Trabajo",
          icono: "ClipboardList",
          descripcion:
            "Eventos y tareas del equipo con su cobertura: qué hay que cubrir y quién lo coge, por marca.",
        },
        {
          ruta: "/equipo/calendario",
          etiqueta: "Calendario",
          icono: "CalendarClock",
          descripcion:
            "El horario de turnos del equipo: tu calendario y el del equipo, semana o mes, por marca.",
        },
      ],
    },
    {
      etiqueta: "Contenido",
      items: [
        {
          ruta: "/contenido/imagen",
          etiqueta: "Imagen",
          icono: "Image",
          descripcion:
            "Estudio de imagen por capas: texto, logos, marcos, plantillas y bloques por marca; genera/expande/retoca con IA y exporta el arte de la pieza.",
        },
        {
          ruta: "/contenido/video",
          etiqueta: "Video",
          icono: "Clapperboard",
          descripcion:
            "Estudio de video: el toque RRSS sobre un clip ya editado — formato, overlay, PiP y subtítulos; el render fiel lo produce el servidor.",
        },
        {
          ruta: "/contenido/audio",
          etiqueta: "Audio",
          icono: "AudioLines",
          descripcion:
            "Gestor de audio→texto: sube cualquier audio o vídeo, extrae la voz y genera la transcripción con timestamps; límpiala, resúmela o corrígela con agentes de Claude.",
        },
        {
          ruta: "/contenido/galeria",
          etiqueta: "Galería",
          icono: "Camera",
          descripcion:
            "Descarga la herramienta local y procesa las fotos de un partido en tu equipo.",
        },
      ],
    },
    {
      etiqueta: "Máquina",
      items: [
        {
          ruta: "/maquina/contexto",
          etiqueta: "Contexto",
          icono: "Layers",
          descripcion:
            "La máquina en una página: el pipeline de Investigación y Producción como estructura — cada fase con su prompt, el contexto editorial que inyecta, sus logs y su interruptor on/off.",
        },
        {
          ruta: "/maquina/agentes",
          etiqueta: "Agentes",
          icono: "Bot",
          descripcion:
            "La «sala de máquinas» (observabilidad y control de los agentes): Cómputo (la cola en vivo) y, en pestañas hermanas, la Economía (presupuesto + coste) y la Actividad (la traza completa).",
        },
      ],
    },
    {
      etiqueta: "Datos",
      items: [
        {
          ruta: "/datos/analiticas",
          etiqueta: "Analíticas",
          icono: "BarChart3",
          descripcion:
            "Rendimiento de las cuentas y seguimiento de campañas. Pestañas Métricas / Campañas.",
        },
      ],
    },
  ],
};

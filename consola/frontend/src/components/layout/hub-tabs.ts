import {
  Activity,
  BarChart3,
  BookText,
  CalendarClock,
  CalendarDays,
  GitBranch,
  LayoutGrid,
  ListTodo,
  Megaphone,
  Newspaper,
  Rss,
  ScanSearch,
  ScanText,
  Sparkles,
  Target,
  Zap,
  type LucideIcon,
} from "lucide-react";

/** Una sub-pestaña de un hub (consumida por el sidebar con scope). */
export interface ItemTabHub {
  /** Ruta absoluta del tab (NavLink la consume tal cual). */
  ruta: string;
  etiqueta: string;
  icono: LucideIcon;
  /**
   * Si es `true`, el tab solo se marca activo cuando la URL coincide
   * exactamente; útil para el tab "raíz" de un hub que comparte prefijo con
   * los demás (p.ej. `/activos` vs `/activos/plantillas`).
   */
  end?: boolean;
}

/**
 * Registro COMPARTIDO de las sub-pestañas de cada hub de la consola.
 *
 * Cada hub (Investigación, Revisión, Analíticas, Feed, Calendario, Biblioteca) declara
 * aquí sus pestañas, una sola vez, para que las consuman tanto la página del hub
 * como la barra de pestañas in-page (`SubnavHub`). El mapa de abajo las indexa por
 * la ruta PADRE del hub (con su prefijo de bloque: `/operacion`, `/contenido`,
 * `/datos`).
 */
// Investigación = la máquina de contenido de la marca, colapsada a TRES PIEZAS,
// todo por marca:
//   - NOTICIAS (índice del hub): items informativos/temporales a publicar
//     (agencias, RSS ajenos, reporteros, corresponsales). Caducan. Su núcleo es el
//     pool persistente de cobertura + el descubrimiento/plan del Investigador.
//   - CONTENIDOS: piezas educativas/curiosas/atemporales (reportajes internos,
//     producciones propias). Evergreen (banco GREEN).
//   - FUENTES: ajustes de TODOS los canales que alimentan Noticias y Contenidos
//     (RSS, buzones, agentes de investigación, eventos/programas, cajón green,
//     agencias, Trends). Cada fuente declara si alimenta Noticias o Contenidos.
// (Termómetro, Cajones, Eventos, Agentes y Cobertura siguen vivos como rutas
// durante la transición, pero ya NO son pestañas de la subnav; se fusionarán y
// redirigirán en fases posteriores. Algoritmos pasó a la Biblioteca.)
export const TABS_INVESTIGACION: ItemTabHub[] = [
  // `end: true`: comparte prefijo con `/contenidos` y `/fuentes`, así que el tab
  // raíz (Noticias) solo se marca activo en la coincidencia exacta del índice.
  { ruta: "/datos/investigacion", etiqueta: "Noticias", icono: Newspaper, end: true },
  { ruta: "/datos/investigacion/contenidos", etiqueta: "Contenidos", icono: Sparkles },
  { ruta: "/datos/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
];

export const TABS_REVISION: ItemTabHub[] = [
  { ruta: "/operacion/revision/editorial", etiqueta: "Editorial", icono: ScanText },
  { ruta: "/operacion/revision/verificacion", etiqueta: "Verificación", icono: ScanSearch },
  // Carril Rápido: solo Claro Sports (y vista "Todas"). El gating se aplica en
  // `gating-marca.ts` (oculta del nav para otras marcas) y en el GuardTurnos equivalente.
  { ruta: "/operacion/revision/breaking", etiqueta: "Breaking", icono: Zap },
];

export const TABS_ANALITICAS: ItemTabHub[] = [
  { ruta: "/datos/analiticas/metricas", etiqueta: "Métricas", icono: BarChart3 },
  { ruta: "/datos/analiticas/comercial", etiqueta: "Comercial", icono: Megaphone },
];

// El antiguo hub "Parrilla" se separó en DOS hubs (#cal-feed): "Feed" agrupa el feed de
// ideación (formato red social) y la Lista de contenido; "Calendario" agrupa los Turnos de
// cobertura y el Calendario de publicaciones. La marca la fija el switch global de la topbar.
export const TABS_FEED: ItemTabHub[] = [
  { ruta: "/operacion/feed/feed", etiqueta: "Feed", icono: LayoutGrid },
  { ruta: "/operacion/feed/lista", etiqueta: "Lista", icono: ListTodo },
];

export const TABS_CALENDARIO: ItemTabHub[] = [
  { ruta: "/operacion/calendario/calendario", etiqueta: "Programación", icono: CalendarDays },
  { ruta: "/operacion/calendario/turnos", etiqueta: "Turnos", icono: CalendarClock },
];

// El bloque CONTENIDO ya no agrupa un hub "Estudio" con pestañas: Imagen, Video y Texto
// son TRES entradas planas del sidebar (sin sub-navegación por pestañas). Imagen
// (`/contenido/imagen`) y Video (`/contenido/video`) son páginas sueltas; Texto sigue
// siendo el hub de la Biblioteca (abajo).

// La página TEXTO (antes "Biblioteca") es un hub: documentos (prompts + línea editorial),
// estrategia de marcas e inteligencia de plataforma (algoritmos).
export const TABS_TEXTO: ItemTabHub[] = [
  // Documentos: prompts + línea editorial + plantillas, con filtros.
  { ruta: "/contenido/texto/documentos", etiqueta: "Documentos", icono: BookText },
  { ruta: "/contenido/texto/estrategia", etiqueta: "Estrategia de marcas", icono: Target },
  // Algoritmos: inteligencia de plataforma (cambios de algoritmo por red). Vive en
  // Texto porque su salida son las fichas editoriales de cada plataforma.
  { ruta: "/contenido/texto/algoritmos", etiqueta: "Algoritmos", icono: Newspaper },
];

// Actividad IA es un hub: el feed de actividad (índice del hub) y los Pipelines (vista
// CI/CD del pipeline de contenido, etapa a etapa). Pipelines deja de ser una entrada suelta
// del sidebar para vivir como pestaña aquí.
export const TABS_ACTIVIDAD: ItemTabHub[] = [
  // `end: true`: comparte prefijo con `/pipelines`, así que el tab raíz (el feed) solo se
  // marca activo en la coincidencia exacta del índice.
  { ruta: "/datos/actividad", etiqueta: "Actividad", icono: Activity, end: true },
  { ruta: "/datos/actividad/pipelines", etiqueta: "Pipelines", icono: GitBranch },
];

/**
 * Mapa `rutaPadre -> sub-pestañas`. La clave es la ruta del hub (la misma que
 * entrega el catálogo para esa entrada de nav). El sidebar la usa para saber que
 * una entrada es un hub; la barra in-page pinta las pestañas.
 */
export const HUB_TABS: Record<string, ItemTabHub[]> = {
  "/datos/investigacion": TABS_INVESTIGACION,
  "/operacion/revision": TABS_REVISION,
  "/datos/analiticas": TABS_ANALITICAS,
  "/operacion/feed": TABS_FEED,
  "/operacion/calendario": TABS_CALENDARIO,
  // Bajo /contenido solo Texto es un hub con pestañas; Imagen y Video son páginas planas
  // (sin entrada aquí), por eso /contenido ya no figura en el mapa.
  "/contenido/texto": TABS_TEXTO,
  "/datos/actividad": TABS_ACTIVIDAD,
};

/**
 * Sub-pestañas de la sección cuya ruta es `ruta`, o `undefined` si esa ruta no
 * corresponde a un hub. Lo usa el sidebar para decidir si expandir una entrada.
 */
export function subPestanasDe(ruta: string): ItemTabHub[] | undefined {
  return HUB_TABS[ruta];
}

/**
 * Sub-pestañas del hub al que pertenece `pathname` (la sección de cabecera
 * `/investigacion`, `/revision`, …), o `undefined` si la ruta no cae en un hub.
 * A diferencia de `subPestanasDe` (que exige la ruta-padre EXACTA), esto matchea
 * también las hojas del hub (`/investigacion/radar` → pestañas de Investigación),
 * para que la barra de pestañas in-page se pinte estando en cualquier sub-ruta.
 * Lo consume el `SubnavHub` del AppShell: los hubs son UNA entrada en el sidebar
 * (calma la barra) y su sub-navegación vive aquí, como pestañas sobre el contenido.
 */
export function pestanasDeRuta(pathname: string): ItemTabHub[] | undefined {
  for (const [ruta, pestanas] of Object.entries(HUB_TABS)) {
    if (pathname === ruta || pathname.startsWith(`${ruta}/`)) return pestanas;
  }
  return undefined;
}

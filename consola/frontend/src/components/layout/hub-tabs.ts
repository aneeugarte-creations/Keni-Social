import {
  BarChart3,
  BookText,
  LayoutGrid,
  ListTodo,
  Megaphone,
  Newspaper,
  Rss,
  Sparkles,
  Target,
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
 * Cada hub (Investigación, Revisión, Analíticas, Feed, Calendario, Texto) declara
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
//     producciones propias). Everevergreen (banco EVERGREEN).
//   - FUENTES: ajustes de TODOS los canales que alimentan Noticias y Contenidos
//     (RSS, buzones, agentes de investigación, eventos/programas, cajón evergreen,
//     agencias, Trends). Cada fuente declara si alimenta Noticias o Contenidos.
// (Termómetro, Cajones, Eventos, Agentes y Cobertura siguen vivos como rutas
// durante la transición, pero ya NO son pestañas de la subnav; se fusionarán y
// redirigirán en fases posteriores. Algoritmos pasó a la Texto.)
export const TABS_INVESTIGACION: ItemTabHub[] = [
  // `end: true`: comparte prefijo con `/contenidos` y `/fuentes`, así que el tab
  // raíz (Noticias) solo se marca activo en la coincidencia exacta del índice.
  { ruta: "/datos/investigacion", etiqueta: "Noticias", icono: Newspaper, end: true },
  { ruta: "/datos/investigacion/contenidos", etiqueta: "Contenidos", icono: Sparkles },
  { ruta: "/datos/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
];

export const TABS_ANALITICAS: ItemTabHub[] = [
  { ruta: "/datos/analiticas/metricas", etiqueta: "Métricas", icono: BarChart3 },
  { ruta: "/datos/analiticas/comercial", etiqueta: "Campañas", icono: Megaphone },
];

// El antiguo hub "Parrilla" se separó en "Feed" (feed de ideación + Lista de contenido).
// El hub "Calendario" se separó a su vez en DOS páginas planas del sidebar —Programación
// y Turnos— sin sub-pestañas (no figuran aquí). La marca la fija el switch global de la topbar.
export const TABS_FEED: ItemTabHub[] = [
  { ruta: "/operacion/feed/feed", etiqueta: "Feed", icono: LayoutGrid },
  { ruta: "/operacion/feed/lista", etiqueta: "Lista", icono: ListTodo },
];

// El bloque CONTENIDO ya no agrupa un hub "Estudio" con pestañas: Imagen, Video y Texto
// son TRES entradas planas del sidebar (sin sub-navegación por pestañas). Imagen
// (`/contenido/imagen`) y Video (`/contenido/video`) son páginas sueltas; Texto sigue
// siendo el hub de la Texto (abajo).

// La página TEXTO (antes "Texto") es un hub: documentos (prompts + línea editorial) y
// estrategia de marcas. Algoritmos (inteligencia de plataforma) se MUDÓ al cockpit de
// Investigación: es un INPUT del motor de descubrimiento, no una herramienta de la Biblioteca.
export const TABS_TEXTO: ItemTabHub[] = [
  // Documentos: prompts + línea editorial + plantillas, con filtros.
  { ruta: "/contenido/texto/documentos", etiqueta: "Documentos", icono: BookText },
  { ruta: "/contenido/texto/estrategia", etiqueta: "Estrategia de marcas", icono: Target },
];

// Producción (antes «Actividad IA») es ya una PÁGINA PLANA (el feed unificado: runs del
// pipeline + actividad suelta, con conteos y métricas). Su antigua pestaña «Monitor» se
// RELOCALIZÓ a la sección «Máquina» (fase 2A): la vista global del worker/cola es
// `/maquina/cola`. Por eso /datos/produccion ya no es un hub (no figura en HUB_TABS).

/**
 * Mapa `rutaPadre -> sub-pestañas`. La clave es la ruta del hub (la misma que
 * entrega el catálogo para esa entrada de nav). El sidebar la usa para saber que
 * una entrada es un hub; la barra in-page pinta las pestañas.
 */
export const HUB_TABS: Record<string, ItemTabHub[]> = {
  "/datos/investigacion": TABS_INVESTIGACION,
  "/datos/analiticas": TABS_ANALITICAS,
  "/operacion/feed": TABS_FEED,
  // Bajo /operacion, Programación y Turnos son páginas planas (sin pestañas), no hubs;
  // por eso no figuran aquí. Igual que Imagen/Video bajo /contenido y la sección «Máquina»
  // (Investigación/Producción/Cola son tres páginas planas del bloque, no un hub).
  "/contenido/texto": TABS_TEXTO,
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
 * `/datos/investigacion`, `/datos/analiticas`, …), o `undefined` si la ruta no cae en un hub.
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

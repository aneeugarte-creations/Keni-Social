import {
  BarChart3,
  BookText,
  CalendarCheck,
  CalendarClock,
  FileText,
  LayoutGrid,
  ListTodo,
  Megaphone,
  Newspaper,
  Presentation,
  Radar,
  Rss,
  ScanSearch,
  ScanText,
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
 * Cada hub (Investigación, Revisión, Analíticas, Parrilla, Biblioteca) declara
 * aquí sus pestañas, una sola vez, para que las consuman tanto la página del hub
 * como la barra de pestañas in-page (`SubnavHub`). El mapa de abajo las indexa por
 * la ruta PADRE del hub (con su prefijo de bloque: `/operacion`, `/contenido`,
 * `/datos`).
 */
// Investigación = el loop diario de la marca: el Plan del día (lo más importante:
// la lista definitiva de contenidos de hoy) se alimenta del Descubrimiento
// (tendencias y señales) y de las Fuentes que cada marca gestiona. Todo por marca.
// (Termómetro alimenta el Plan del día y se entra desde ahí; Algoritmos pasó a la
// Biblioteca, porque su salida son las fichas de plataforma.)
export const TABS_INVESTIGACION: ItemTabHub[] = [
  { ruta: "/datos/investigacion/plan", etiqueta: "Plan del día", icono: CalendarCheck },
  { ruta: "/datos/investigacion/descubrimiento", etiqueta: "Descubrimiento", icono: Radar },
  { ruta: "/datos/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
];

export const TABS_REVISION: ItemTabHub[] = [
  { ruta: "/operacion/revision/editorial", etiqueta: "Editorial", icono: ScanText },
  { ruta: "/operacion/revision/verificacion", etiqueta: "Verificación", icono: ScanSearch },
];

export const TABS_ANALITICAS: ItemTabHub[] = [
  { ruta: "/datos/analiticas/metricas", etiqueta: "Métricas", icono: BarChart3 },
  { ruta: "/datos/analiticas/comercial", etiqueta: "Comercial", icono: Megaphone },
  { ruta: "/datos/analiticas/reporte-deportes", etiqueta: "Reporte deportes", icono: Presentation },
];

export const TABS_PARRILLA: ItemTabHub[] = [
  { ruta: "/operacion/parrilla/pendientes", etiqueta: "Pendientes", icono: ListTodo },
  { ruta: "/operacion/parrilla/feed", etiqueta: "Feed", icono: LayoutGrid },
  { ruta: "/operacion/parrilla/turnos", etiqueta: "Turnos", icono: CalendarClock },
];

// Biblioteca es ahora un hub: sus documentos (prompts + línea editorial) y las
// plantillas de contenido (antes la página "Activos", absorbida como pestaña).
export const TABS_BIBLIOTECA: ItemTabHub[] = [
  { ruta: "/contenido/biblioteca/documentos", etiqueta: "Documentos", icono: BookText },
  { ruta: "/contenido/biblioteca/plantillas", etiqueta: "Plantillas", icono: FileText },
  { ruta: "/contenido/biblioteca/estrategia", etiqueta: "Estrategia de marcas", icono: Target },
  // Algoritmos: inteligencia de plataforma (cambios de algoritmo por red). Vive en
  // la Biblioteca porque su salida son las fichas editoriales de cada plataforma.
  { ruta: "/contenido/biblioteca/algoritmos", etiqueta: "Algoritmos", icono: Newspaper },
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
  "/operacion/parrilla": TABS_PARRILLA,
  "/contenido/biblioteca": TABS_BIBLIOTECA,
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

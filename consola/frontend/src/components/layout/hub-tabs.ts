import {
  BarChart3,
  Bot,
  BookText,
  CalendarClock,
  CalendarDays,
  CalendarPlus,
  Inbox,
  LayoutGrid,
  ListTodo,
  Megaphone,
  Newspaper,
  Rss,
  ScanSearch,
  ScanText,
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
// Investigación = el loop diario de la marca, colapsado a DOS páginas: el
// Investigador (plan del día + descubrimiento en una sola superficie; es el índice
// del hub) y las Fuentes que cada marca gestiona. Todo por marca. (Termómetro
// alimenta el Investigador y se entra desde un botón dentro de él; Algoritmos pasó
// a la Biblioteca, porque su salida son las fichas de plataforma.)
export const TABS_INVESTIGACION: ItemTabHub[] = [
  // `end: true`: comparte prefijo con `/fuentes`, así que el tab raíz solo se marca
  // activo en la coincidencia exacta del índice.
  { ruta: "/datos/investigacion", etiqueta: "Investigador", icono: ScanSearch, end: true },
  { ruta: "/datos/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
  { ruta: "/datos/investigacion/cajones", etiqueta: "Cajones del día", icono: Inbox },
  // Eventos a cubrir: se mudó del Calendario al hub de Fuentes (ola "Calendario =
  // turnos / Fuentes = eventos"). La asignación de cobertura sigue en Turnos.
  { ruta: "/datos/investigacion/eventos", etiqueta: "Eventos", icono: CalendarPlus },
  // Agentes de investigación (Ola 6): briefs reutilizables + candidatos fechados.
  { ruta: "/datos/investigacion/agentes", etiqueta: "Agentes", icono: Bot },
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

// Biblioteca es ahora un hub: sus documentos (prompts + línea editorial) y las
// plantillas de contenido (antes la página "Activos", absorbida como pestaña).
export const TABS_BIBLIOTECA: ItemTabHub[] = [
  // Una sola Biblioteca: prompts + línea editorial + plantillas, con filtros (sin sub-pestañas).
  { ruta: "/contenido/biblioteca/documentos", etiqueta: "Biblioteca", icono: BookText },
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
  "/operacion/feed": TABS_FEED,
  "/operacion/calendario": TABS_CALENDARIO,
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

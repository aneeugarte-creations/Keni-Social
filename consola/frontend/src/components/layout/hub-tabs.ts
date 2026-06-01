import {
  Activity,
  BarChart3,
  Bot,
  CalendarClock,
  FileText,
  Globe,
  Images,
  ListTodo,
  Megaphone,
  Presentation,
  Radar,
  Rss,
  ScanSearch,
  ScanText,
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
   * los demás (p.ej. `/agentes` vs `/agentes/actividad`).
   */
  end?: boolean;
}

/**
 * Registro COMPARTIDO de las sub-pestañas de cada hub de la consola.
 *
 * Antes cada hub (Investigación, Revisión, Analíticas, Parrilla, Agentes)
 * declaraba sus `TABS` como `const` local. Ahora viven aquí, una sola vez, para
 * que las consuman TANTO la página del hub (que no cambia de comportamiento)
 * COMO el sidebar con scope (que las expande indentadas bajo la sección del
 * hub). Así no se hardcodean en el sidebar: este mapea cada entrada de nav de
 * la app a sus sub-pestañas vía `subPestanasDe(ruta)`; si la entrada no es un
 * hub, no expande nada.
 *
 * Cada bloque es la fuente de verdad de un hub; el mapa de abajo los indexa por
 * la ruta PADRE (la del item de nav de la app que abre el hub).
 */
export const TABS_INVESTIGACION: ItemTabHub[] = [
  { ruta: "/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
  { ruta: "/investigacion/termometro", etiqueta: "Termómetro", icono: Globe },
  { ruta: "/investigacion/radar", etiqueta: "Radar", icono: Radar },
];

export const TABS_REVISION: ItemTabHub[] = [
  { ruta: "/revision/editorial", etiqueta: "Editorial", icono: ScanText },
  { ruta: "/revision/verificacion", etiqueta: "Verificación", icono: ScanSearch },
];

export const TABS_ANALITICAS: ItemTabHub[] = [
  { ruta: "/analiticas/metricas", etiqueta: "Métricas", icono: BarChart3 },
  { ruta: "/analiticas/comercial", etiqueta: "Comercial", icono: Megaphone },
  { ruta: "/analiticas/reporte-deportes", etiqueta: "Reporte deportes", icono: Presentation },
];

export const TABS_PARRILLA: ItemTabHub[] = [
  { ruta: "/parrilla/calendario", etiqueta: "Turnos", icono: CalendarClock },
  { ruta: "/parrilla/pendientes", etiqueta: "Pendientes", icono: ListTodo },
];

export const TABS_AGENTES: ItemTabHub[] = [
  // `end` para que el catálogo no quede activo cuando estás en /agentes/actividad.
  { ruta: "/agentes", etiqueta: "Agentes", icono: Bot, end: true },
  { ruta: "/agentes/actividad", etiqueta: "Actividad IA", icono: Activity },
];

export const TABS_ACTIVOS: ItemTabHub[] = [
  { ruta: "/activos/plantillas", etiqueta: "Plantillas", icono: FileText },
  { ruta: "/activos/biblioteca", etiqueta: "Biblioteca", icono: Images },
];

/**
 * Mapa `rutaPadre -> sub-pestañas`. La clave es la ruta del item de nav de la
 * app que abre el hub (la misma que entrega el catálogo). El sidebar lo usa para
 * expandir; cada página de hub toma su array directo (export con nombre).
 */
export const HUB_TABS: Record<string, ItemTabHub[]> = {
  "/investigacion": TABS_INVESTIGACION,
  "/revision": TABS_REVISION,
  "/analiticas": TABS_ANALITICAS,
  "/parrilla": TABS_PARRILLA,
  "/agentes": TABS_AGENTES,
  "/activos": TABS_ACTIVOS,
};

/**
 * Sub-pestañas de la sección cuya ruta es `ruta`, o `undefined` si esa ruta no
 * corresponde a un hub. Lo usa el sidebar para decidir si expandir una entrada.
 */
export function subPestanasDe(ruta: string): ItemTabHub[] | undefined {
  return HUB_TABS[ruta];
}

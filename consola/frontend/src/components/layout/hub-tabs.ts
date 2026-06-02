import {
  BarChart3,
  CalendarClock,
  FileText,
  Globe,
  LayoutGrid,
  ListTodo,
  Megaphone,
  Newspaper,
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
   * los demás (p.ej. `/activos` vs `/activos/plantillas`).
   */
  end?: boolean;
}

/**
 * Registro COMPARTIDO de las sub-pestañas de cada hub de la consola.
 *
 * Antes cada hub (Investigación, Revisión, Analíticas, Parrilla, Activos)
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
  { ruta: "/investigacion/algoritmos", etiqueta: "Algoritmos", icono: Newspaper },
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
  { ruta: "/parrilla/pendientes", etiqueta: "Pendientes", icono: ListTodo },
  { ruta: "/parrilla/feed", etiqueta: "Feed", icono: LayoutGrid },
  { ruta: "/parrilla/calendario", etiqueta: "Turnos", icono: CalendarClock },
];

export const TABS_ACTIVOS: ItemTabHub[] = [
  { ruta: "/activos/plantillas", etiqueta: "Plantillas", icono: FileText },
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
  "/activos": TABS_ACTIVOS,
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

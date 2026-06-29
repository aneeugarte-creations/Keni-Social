import {
  Activity,
  BarChart3,
  CalendarDays,
  Coins,
  Cpu,
  Inbox,
  LayoutGrid,
  ListTodo,
  Megaphone,
  Newspaper,
  Rss,
  Sparkles,
  Tags,
  TrendingUp,
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
 * Cada hub (Investigación, Analíticas, Feed, Programa, Agentes) declara aquí sus
 * pestañas, una sola vez, para que las consuman tanto la página del hub como la barra
 * de pestañas in-page (`SubnavHub`). El mapa de abajo las indexa por la ruta PADRE del
 * hub (con su prefijo de bloque: `/operacion`, `/maquina`, `/datos`).
 */
// Investigación (`/operacion/investigacion`) = el pool de noticias que el equipo revisa a diario:
//   - NOTICIAS (aterrizaje): items informativos/temporales a publicar (agencias, RSS ajenos,
//     reporteros, corresponsales). Caducan. El pool persistente de cobertura.
//   - FUENTES: ajustes de TODOS los canales que alimentan el pool (RSS, buzones, eventos, agencias).
//   - ALGORITMOS: inteligencia de plataforma + trends.
//   - PUBLICACIONES: piezas atemporales (reportajes internos, producciones propias). Banco EVERGREEN.
export const TABS_INVESTIGACION: ItemTabHub[] = [
  { ruta: "/operacion/investigacion/noticias", etiqueta: "Noticias", icono: Newspaper },
  { ruta: "/operacion/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
  { ruta: "/operacion/investigacion/algoritmos", etiqueta: "Algoritmos", icono: TrendingUp },
  { ruta: "/operacion/investigacion/publicaciones", etiqueta: "Publicaciones", icono: Sparkles },
];

export const TABS_ANALITICAS: ItemTabHub[] = [
  { ruta: "/datos/analiticas/metricas", etiqueta: "Métricas", icono: BarChart3 },
  { ruta: "/datos/analiticas/campanias", etiqueta: "Campañas", icono: Megaphone },
  // Inbox: buzón de SOLO lectura (DMs + comentarios de FB/IG), misma frontera Metricool.
  { ruta: "/datos/analiticas/inbox", etiqueta: "Buzón", icono: Inbox },
];

// Programa: el «qué/cuándo» de publicación de una marca. Programación (la rejilla mensual) es la
// pestaña de aterrizaje; Plan es la taxonomía de líneas (su hashtag derivado + los keywords del
// clasificador, además del cupo/día y los horarios).
export const TABS_PROGRAMA: ItemTabHub[] = [
  { ruta: "/operacion/programa/programacion", etiqueta: "Programación", icono: CalendarDays },
  { ruta: "/operacion/programa/plan", etiqueta: "Plan", icono: Tags },
];

export const TABS_FEED: ItemTabHub[] = [
  { ruta: "/operacion/feed/feed", etiqueta: "Feed", icono: LayoutGrid },
  // Portal: clon del Feed acotado al canal `origen="portal"` (auto-producidos de fuente propia).
  { ruta: "/operacion/feed/portal", etiqueta: "Portal", icono: Newspaper },
  { ruta: "/operacion/feed/lista", etiqueta: "Lista", icono: ListTodo },
];

// Hub «Agentes» (`/maquina/agentes`): la observabilidad y el control de la máquina. Cómputo (la
// cola) es la pestaña de aterrizaje y vive en la PROPIA ruta-padre (`end: true` para no marcarse
// activa en el detalle de un daemon, que cuelga de ella); Economía (coste) y Actividad (la traza)
// son sus hermanas. Economía y Actividad NO comparten el prefijo de la ruta-padre, así que
// `pestanasDeRuta` casa por pertenencia (abajo).
export const TABS_MAQUINA: ItemTabHub[] = [
  { ruta: "/maquina/agentes", etiqueta: "Cómputo", icono: Cpu, end: true },
  { ruta: "/maquina/economia", etiqueta: "Economía", icono: Coins },
  { ruta: "/maquina/actividad", etiqueta: "Actividad", icono: Activity },
];

/**
 * Mapa `rutaPadre -> sub-pestañas`. La clave es la ruta del hub (la misma que
 * entrega el catálogo para esa entrada de nav). El sidebar la usa para saber que
 * una entrada es un hub; la barra in-page pinta las pestañas.
 */
export const HUB_TABS: Record<string, ItemTabHub[]> = {
  "/operacion/investigacion": TABS_INVESTIGACION,
  "/operacion/feed": TABS_FEED,
  "/operacion/programa": TABS_PROGRAMA,
  "/datos/analiticas": TABS_ANALITICAS,
  // Bajo /equipo, Trabajo y Calendario son páginas planas (sin pestañas), no hubs; por eso no
  // figuran aquí. Igual que Imagen/Video/Audio/Galería bajo /contenido.
  // Hub «Agentes»: la clave es la pestaña de aterrizaje (Cómputo, `/maquina/agentes`), la MISMA
  // ruta que el catálogo entrega para esa entrada de nav.
  "/maquina/agentes": TABS_MAQUINA,
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
 * `/operacion/investigacion`, `/datos/analiticas`, …), o `undefined` si la ruta no cae en un hub.
 * A diferencia de `subPestanasDe` (que exige la ruta-padre EXACTA), esto matchea
 * también las hojas del hub (`/operacion/investigacion/historia/:id` → pestañas de Investigación),
 * para que la barra de pestañas in-page se pinte estando en cualquier sub-ruta.
 * Lo consume el `SubnavHub` del AppShell: los hubs son UNA entrada en el sidebar
 * (calma la barra) y su sub-navegación vive aquí, como pestañas sobre el contenido.
 */
export function pestanasDeRuta(pathname: string): ItemTabHub[] | undefined {
  for (const [ruta, pestanas] of Object.entries(HUB_TABS)) {
    if (pathname === ruta || pathname.startsWith(`${ruta}/`)) return pestanas;
    // Hubs cuyas pestañas NO comparten el prefijo de la ruta-padre (p. ej. el hub Agentes:
    // /maquina/agentes · /maquina/economia · /maquina/actividad): se casa por PERTENENCIA a una
    // pestaña (la propia ruta o una sub-ruta suya, como un detalle).
    if (pestanas.some((p) => pathname === p.ruta || pathname.startsWith(`${p.ruta}/`)))
      return pestanas;
  }
  return undefined;
}

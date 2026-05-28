import {
  BarChart3,
  Bot,
  CalendarClock,
  Globe,
  LayoutDashboard,
  Lightbulb,
  ListTodo,
  Megaphone,
  Presentation,
  Radar,
  Rss,
  ScanSearch,
  ScanText,
  Send,
  Settings2,
  Sparkles,
  UserCog,
  Users,
  Wand2,
  type LucideIcon,
} from "lucide-react";

export interface ItemNav {
  ruta: string;
  etiqueta: string;
  icono: LucideIcon;
  /** Descripcion corta para tooltip/accesibilidad. */
  descripcion: string;
  /** `true` si el ítem solo debe verse con rol admin (lo filtra el Sidebar). */
  soloAdmin?: boolean;
}

export interface GrupoNav {
  /**
   * Etiqueta del grupo en el sidebar. Si es cadena vacía, el grupo se renderiza
   * sin encabezado (útil para el bloque inicial con Panel suelto).
   */
  etiqueta: string;
  items: ItemNav[];
}

/**
 * Estructura del sidebar. Agrupada por flujo de trabajo (no por dependencia
 * técnica) para reducir carga cognitiva: el panel encabeza sin grupo, después
 * los pasos del día (generar → investigar → revisar → analizar → organizar) y
 * al final los ajustes.
 *
 * Páginas absorbidas como subnavegación:
 * - `Generación` reemplaza `Generar copy` + `Imágenes` (pestañas internas).
 * - `Agentes` absorbe `Actividad IA` (Monitor) como segunda pestaña.
 */
export const NAVEGACION: GrupoNav[] = [
  {
    etiqueta: "",
    items: [
      {
        ruta: "/panel",
        etiqueta: "Panel",
        icono: LayoutDashboard,
        descripcion:
          "Un vistazo: rendimiento del periodo, cola de aprobación y próximas publicaciones programadas.",
      },
    ],
  },
  {
    etiqueta: "Generación",
    items: [
      {
        ruta: "/generacion",
        etiqueta: "Generación",
        icono: Sparkles,
        descripcion:
          "Crea copy o imágenes con las skills editoriales. Cambia de modo con la pestaña superior.",
      },
    ],
  },
  {
    etiqueta: "Investigación",
    items: [
      {
        ruta: "/fuentes",
        etiqueta: "Fuentes",
        icono: Rss,
        descripcion: "Feeds RSS para alimentar la generación.",
      },
      {
        ruta: "/termometro",
        etiqueta: "Termómetro mundial",
        icono: Globe,
        descripcion: "Galería diaria con las 5–8 noticias internacionales más importantes.",
      },
      {
        ruta: "/radar",
        etiqueta: "Radar de tendencias",
        icono: Radar,
        descripcion: "Lo más viral del momento multi-red, agrupado por tema; tú marcas lo relevante.",
      },
    ],
  },
  {
    etiqueta: "Revisión",
    items: [
      {
        ruta: "/revision-editorial",
        etiqueta: "Revisión editorial",
        icono: ScanText,
        descripcion:
          "Revisa el copy que escribió el equipo: veredicto de typos, datos, legal y voz. Señala, no reescribe.",
      },
      {
        ruta: "/verificacion",
        etiqueta: "Verificación",
        icono: ScanSearch,
        descripcion: "Pega el enlace de un video y comprueba si es nuevo o ya circulaba.",
      },
    ],
  },
  {
    etiqueta: "Analíticas",
    items: [
      {
        ruta: "/metricas",
        etiqueta: "Métricas",
        icono: BarChart3,
        descripcion: "Reportes y comparativas de tus cuentas.",
      },
      {
        ruta: "/comercial",
        etiqueta: "Comercial",
        icono: Megaphone,
        descripcion:
          "Monitorea publicaciones comerciales por su enlace y entrega su reporte al llegar el KPI.",
      },
      {
        ruta: "/reporte-deportes",
        etiqueta: "Reporte deportes",
        icono: Presentation,
        descripcion: "Deck semanal de Claro Sports: mejores piezas, cuentas hermanas y agenda.",
      },
    ],
  },
  {
    etiqueta: "Organización",
    items: [
      {
        ruta: "/publicaciones",
        etiqueta: "Publicaciones",
        icono: Send,
        descripcion: "Gestiona borradores, aprueba, programa y publica.",
      },
      {
        ruta: "/tareas",
        etiqueta: "Pendientes",
        icono: ListTodo,
        descripcion: "Tareas por proyecto, con su estado; ábrelas en el asistente.",
      },
      {
        ruta: "/rota",
        etiqueta: "Parrilla y rota",
        icono: CalendarClock,
        descripcion:
          "Calendario de eventos (transmisión, solo imágenes o no cubrir) con reprogramaciones marcadas, rota de cobertura y horarios del equipo.",
      },
      {
        ruta: "/skills",
        etiqueta: "Skills",
        icono: Wand2,
        descripcion: "Gestiona las skills editoriales: campos, plantilla y SKILL.md.",
      },
      {
        ruta: "/agentes",
        etiqueta: "Agentes",
        icono: Bot,
        descripcion:
          "Cada marca: su contexto (CLAUDE.md) y sus ejecuciones. La actividad IA es la segunda pestaña.",
      },
    ],
  },
  {
    etiqueta: "Ajustes",
    items: [
      {
        ruta: "/mi-cuenta",
        etiqueta: "Mi cuenta",
        icono: UserCog,
        descripcion: "Tus datos y el cambio de tu contraseña.",
      },
      {
        ruta: "/configuracion",
        etiqueta: "Configuración",
        icono: Settings2,
        descripcion: "Fuente de datos, marcas, redes y clave de imagen IA.",
      },
      {
        ruta: "/sugerencias",
        etiqueta: "Sugerencias",
        icono: Lightbulb,
        descripcion: "Buzón de ideas y mejoras del producto.",
      },
      {
        ruta: "/usuarios",
        etiqueta: "Usuarios",
        icono: Users,
        descripcion: "Gestiona las cuentas que acceden a la consola (solo admin).",
        soloAdmin: true,
      },
    ],
  },
];

/**
 * Filtra la navegación según el rol: oculta los ítems `soloAdmin` cuando el
 * usuario no es admin, y descarta los grupos que quedan vacíos. La fuente de
 * verdad de visibilidad por rol vive aquí; las rutas en sí también se protegen.
 */
export function navegacionParaRol(esAdmin: boolean): GrupoNav[] {
  return NAVEGACION.map((grupo) => ({
    ...grupo,
    items: grupo.items.filter((item) => !item.soloAdmin || esAdmin),
  })).filter((grupo) => grupo.items.length > 0);
}

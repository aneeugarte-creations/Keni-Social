import {
  BarChart3,
  Bot,
  CalendarClock,
  LayoutDashboard,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
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
   * sin encabezado. Hoy todos los grupos del sidebar van sin encabezado y un
   * separador discreto los divide visualmente.
   */
  etiqueta: string;
  items: ItemNav[];
}

/**
 * Sidebar principal: solo 9 entradas, agrupadas en bloques sin encabezado
 * (separadores visuales).
 *
 * - Vistazo: Panel.
 * - Producción del día: Generación, Investigación, Revisión, Analíticas.
 * - Operación: Publicaciones, Parrilla, Skills, Agentes.
 *
 * Investigación, Revisión, Analíticas, Parrilla y Agentes son hubs con tabs
 * internos (sub-rutas); el sidebar no los expande, así se mantiene corto y
 * descubrible. Los ajustes (Mi cuenta, Configuración, Sugerencias, Usuarios)
 * NO viven en el sidebar: cuelgan del dropdown del avatar.
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
    etiqueta: "",
    items: [
      {
        ruta: "/generacion",
        etiqueta: "Generación",
        icono: Sparkles,
        descripcion:
          "Crea copy o imágenes con las skills editoriales. Pestañas Copy / Imágenes.",
      },
      {
        ruta: "/investigacion",
        etiqueta: "Investigación",
        icono: Search,
        descripcion:
          "Fuentes RSS, panorama mundial y tendencias virales. Pestañas Fuentes / Termómetro / Radar.",
      },
      {
        ruta: "/revision",
        etiqueta: "Revisión",
        icono: ShieldCheck,
        descripcion:
          "QA editorial y verificación de imágenes/videos antes de publicar. Pestañas Editorial / Verificación.",
      },
      {
        ruta: "/analiticas",
        etiqueta: "Analíticas",
        icono: BarChart3,
        descripcion:
          "Rendimiento de las cuentas, seguimiento de comercial y deck deportivo. Pestañas Métricas / Comercial / Reporte deportes.",
      },
    ],
  },
  {
    etiqueta: "",
    items: [
      {
        ruta: "/publicaciones",
        etiqueta: "Publicaciones",
        icono: Send,
        descripcion: "Gestiona borradores, aprueba, programa y publica.",
      },
      {
        ruta: "/parrilla",
        etiqueta: "Parrilla",
        icono: CalendarClock,
        descripcion:
          "Pendientes del equipo y calendario semanal con la rota de cobertura. Pestañas Pendientes / Calendario.",
      },
      {
        ruta: "/skills",
        etiqueta: "Skills",
        icono: Wand2,
        descripcion: "Catálogo de skills editoriales: campos, plantilla y SKILL.md.",
      },
      {
        ruta: "/agentes",
        etiqueta: "Agentes",
        icono: Bot,
        descripcion:
          "Cada marca: su contexto (CLAUDE.md) y sus ejecuciones. Pestañas Agentes / Actividad IA.",
      },
    ],
  },
];

/**
 * Filtra la navegación según el rol. Los ítems admin del sidebar se ocultan
 * para no-admin (hoy ya no hay ninguno: Usuarios bajó al dropdown del avatar
 * y se filtra allí). Se descartan los grupos que quedan vacíos.
 */
export function navegacionParaRol(esAdmin: boolean): GrupoNav[] {
  return NAVEGACION.map((grupo) => ({
    ...grupo,
    items: grupo.items.filter((item) => !item.soloAdmin || esAdmin),
  })).filter((grupo) => grupo.items.length > 0);
}

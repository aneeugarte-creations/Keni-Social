import {
  Activity,
  BarChart3,
  Bot,
  CalendarClock,
  Globe,
  ImagePlus,
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
  etiqueta: string;
  items: ItemNav[];
}

/**
 * Estructura del sidebar, agrupada en Trabajo (uso diario) y Ajustes
 * (configuracion). El orden y los grupos siguen el contrato del proyecto.
 */
export const NAVEGACION: GrupoNav[] = [
  {
    etiqueta: "Trabajo",
    items: [
      {
        ruta: "/panel",
        etiqueta: "Panel",
        icono: LayoutDashboard,
        descripcion:
          "Un vistazo: rendimiento del periodo, cola de aprobación y próximas publicaciones programadas.",
      },
      {
        ruta: "/generar-copy",
        etiqueta: "Generar copy",
        icono: Sparkles,
        descripcion: "Crea publicaciones con las skills editoriales.",
      },
      {
        ruta: "/imagenes",
        etiqueta: "Imágenes",
        icono: ImagePlus,
        descripcion:
          "Estudio de imagen: recorta, pon el breaking en marca o genera ilustraciones.",
      },
      {
        ruta: "/revision-editorial",
        etiqueta: "Revisión editorial",
        icono: ScanText,
        descripcion:
          "Revisa el copy que escribió el equipo: veredicto de typos, datos, legal y voz. Señala, no reescribe.",
      },
      {
        ruta: "/skills",
        etiqueta: "Skills",
        icono: Wand2,
        descripcion: "Gestiona las skills editoriales: campos, plantilla y SKILL.md.",
      },
      {
        ruta: "/publicaciones",
        etiqueta: "Publicaciones",
        icono: Send,
        descripcion: "Gestiona borradores, aprueba, programa y publica.",
      },
      {
        ruta: "/fuentes",
        etiqueta: "Fuentes",
        icono: Rss,
        descripcion: "Feeds RSS para alimentar Generar copy.",
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
      {
        ruta: "/verificacion",
        etiqueta: "Verificación",
        icono: ScanSearch,
        descripcion: "Pega el enlace de un video y comprueba si es nuevo o ya circulaba.",
      },
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
      {
        ruta: "/agentes",
        etiqueta: "Agentes",
        icono: Bot,
        descripcion: "Cada marca: su contexto (CLAUDE.md) y sus ejecuciones.",
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
          "Eventos + rota de cobertura y horarios/turnos del equipo (mañana/tarde/descanso, vacaciones): Keni propone (rota los sábados), tú apruebas y publicas.",
      },
      {
        ruta: "/monitor",
        etiqueta: "Actividad IA",
        icono: Activity,
        descripcion: "Monitoriza tokens, coste y duración de los runs de IA.",
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

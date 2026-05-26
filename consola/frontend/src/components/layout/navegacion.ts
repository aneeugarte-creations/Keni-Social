import {
  Activity,
  BarChart3,
  Bot,
  Globe,
  ImagePlus,
  Lightbulb,
  Presentation,
  Rss,
  ScanSearch,
  Send,
  Settings2,
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
    ],
  },
];

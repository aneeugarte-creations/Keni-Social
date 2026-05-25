import {
  Activity,
  BarChart3,
  Bot,
  Rss,
  Send,
  Settings2,
  Sparkles,
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
        ruta: "/metricas",
        etiqueta: "Métricas",
        icono: BarChart3,
        descripcion: "Reportes y comparativas de tus cuentas.",
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
    ],
  },
];

import {
  Activity,
  BarChart3,
  FolderPlus,
  FolderTree,
  ListTodo,
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
        ruta: "/metricas",
        etiqueta: "Métricas",
        icono: BarChart3,
        descripcion: "Reportes y comparativas de tus cuentas.",
      },
      {
        ruta: "/tareas",
        etiqueta: "Tareas",
        icono: ListTodo,
        descripcion: "Pendientes por proyecto.",
      },
    ],
  },
  {
    etiqueta: "Ajustes",
    items: [
      {
        ruta: "/proyectos",
        etiqueta: "Proyectos",
        icono: FolderTree,
        descripcion: "Carpetas conectadas y su CLAUDE.md.",
      },
      {
        ruta: "/carpetas",
        etiqueta: "Nueva carpeta",
        icono: FolderPlus,
        descripcion: "Crea una carpeta a partir de una plantilla.",
      },
      {
        ruta: "/estado",
        etiqueta: "Estado",
        icono: Activity,
        descripcion: "Revisa que tu equipo esté listo para trabajar.",
      },
      {
        ruta: "/configuracion",
        etiqueta: "Configuración",
        icono: Settings2,
        descripcion: "Fuente de datos, marcas y credenciales.",
      },
    ],
  },
];

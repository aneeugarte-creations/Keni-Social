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

import type { GrupoNavCatalogo } from "@/types";

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
 * Mapa nombre-de-icono (string) -> componente LucideIcon. El catálogo
 * (`GET /api/catalogo`, ADR 0005) entrega el icono como STRING (el nombre del
 * icono lucide declarado en el manifest TOML de la app); aquí lo resolvemos al
 * componente. Si un manifest usa un icono que no está en este mapa, caemos a
 * `Sparkles` (visible, no rompe el render) — añade el icono a este mapa.
 */
export const ICONOS: Record<string, LucideIcon> = {
  BarChart3,
  Bot,
  CalendarClock,
  LayoutDashboard,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Wand2,
};

/** Resuelve un nombre de icono del catálogo a su componente (fallback Sparkles). */
export function iconoDe(nombre: string): LucideIcon {
  return ICONOS[nombre] ?? Sparkles;
}

/**
 * Navegación POR DEFECTO (fallback): espejo EXACTO del sidebar generado por el
 * catálogo, para el primer pintado (antes de hidratar desde `/api/catalogo`) y por
 * si la petición del catálogo falla. La fuente de verdad es el backend
 * (manifests TOML); esto solo evita un sidebar vacío mientras carga.
 *
 * - Vistazo: Panel.
 * - Producción del día: Generación, Investigación, Revisión, Analíticas.
 * - Operación: Publicaciones, Parrilla, Skills, Agentes.
 */
export const NAVEGACION_DEFECTO: GrupoNav[] = [
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
 * Convierte la navegación del catálogo (`GET /api/catalogo`) en los grupos que
 * consume el sidebar, resolviendo cada icono-string a su componente. Esta es la
 * vía DATA-DRIVEN: añadir/activar una app NO obliga a editar este fichero, basta
 * con su manifest TOML en el backend.
 */
export function catalogoAGrupos(grupos: GrupoNavCatalogo[]): GrupoNav[] {
  return grupos.map((grupo) => ({
    etiqueta: grupo.etiqueta,
    items: grupo.items.map((item) => ({
      ruta: item.ruta,
      etiqueta: item.etiqueta,
      icono: iconoDe(item.icono),
      descripcion: item.descripcion,
    })),
  }));
}

/**
 * Filtra la navegación según el rol. Los ítems admin del sidebar se ocultan
 * para no-admin (hoy ya no hay ninguno: Usuarios bajó al dropdown del avatar
 * y se filtra allí). Se descartan los grupos que quedan vacíos.
 *
 * `grupos` permite inyectar la navegación hidratada del catálogo; si se omite, usa
 * `NAVEGACION_DEFECTO` (el espejo baked-in), de modo que el sidebar se renderiza
 * igual aunque el catálogo aún no haya cargado.
 */
export function navegacionParaRol(
  esAdmin: boolean,
  grupos: GrupoNav[] = NAVEGACION_DEFECTO,
): GrupoNav[] {
  return grupos
    .map((grupo) => ({
      ...grupo,
      items: grupo.items.filter((item) => !item.soloAdmin || esAdmin),
    }))
    .filter((grupo) => grupo.items.length > 0);
}

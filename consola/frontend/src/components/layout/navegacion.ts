import {
  Activity,
  BarChart3,
  Bot,
  CalendarClock,
  CalendarDays,
  Clapperboard,
  GitBranch,
  Image,
  ImagePlus,
  Layers,
  LayoutDashboard,
  LayoutGrid,
  Library,
  ListChecks,
  Palette,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Type,
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
 * Mapa nombre-de-icono (string) -> componente LucideIcon. El catálogo
 * (`GET /api/catalogo`, ADR 0005) entrega el icono como STRING (el nombre del
 * icono lucide declarado en el manifest TOML de la app); aquí lo resolvemos al
 * componente. Si un manifest usa un icono que no está en este mapa, caemos a
 * `Sparkles` (visible, no rompe el render) — añade el icono a este mapa.
 */
export const ICONOS: Record<string, LucideIcon> = {
  Activity,
  BarChart3,
  Bot,
  CalendarClock,
  CalendarDays,
  Clapperboard,
  GitBranch,
  Image,
  ImagePlus,
  Layers,
  LayoutDashboard,
  LayoutGrid,
  Library,
  ListChecks,
  Palette,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Type,
};

/** Resuelve un nombre de icono del catálogo a su componente (fallback Sparkles). */
export function iconoDe(nombre: string): LucideIcon {
  return ICONOS[nombre] ?? Sparkles;
}

/**
 * Filtra la navegación según el rol. Los ítems admin del sidebar se ocultan
 * para no-admin (hoy ya no hay ninguno: Usuarios bajó al dropdown del avatar
 * y se filtra allí). Se descartan los grupos que quedan vacíos.
 *
 * `grupos` es la navegación ya hidratada del catálogo (la de la app actual; vacía
 * en el launcher o en rutas de shell). La fuente de verdad es el backend
 * (manifests TOML); este módulo solo resuelve iconos y filtra por rol.
 */
export function navegacionParaRol(
  esAdmin: boolean,
  grupos: GrupoNav[],
): GrupoNav[] {
  return grupos
    .map((grupo) => ({
      ...grupo,
      items: grupo.items.filter((item) => !item.soloAdmin || esAdmin),
    }))
    .filter((grupo) => grupo.items.length > 0);
}

// Constantes y helpers compartidos por los paneles del editor (lista de capas e inspector).

import { Group as GroupIcon, Image as ImageIcon, PanelBottom, Square, Type } from "lucide-react";

import type { Capa, CapaTexto } from "../documento";

// Color totalmente transparente (#RRGGBBAA con alfa 00). Válido en render y validación.
export const COLOR_TRANSPARENTE = "#00000000";

// Alfa (0..1) de un color hex #RRGGBB (opaco) o #RRGGBBAA. Sirve para detectar "transparente".
export function alfaHex(color: string | undefined): number {
  if (!color || color.length < 9) return 1;
  const v = parseInt(color.slice(7, 9), 16);
  return Number.isNaN(v) ? 1 : v / 255;
}

export const ETIQUETA_TIPO: Record<Capa["tipo"], string> = {
  imagen: "Imagen",
  texto: "Texto",
  logo: "Logo",
  marco: "Marco",
  overlay: "Degradado",
  grupo: "Grupo",
};

export const ICONO_TIPO: Record<Capa["tipo"], typeof Type> = {
  imagen: ImageIcon,
  texto: Type,
  logo: ImageIcon,
  marco: Square,
  overlay: PanelBottom,
  grupo: GroupIcon,
};

// Nombre a mostrar: el `nombre` editable, o una etiqueta derivada del tipo/contenido.
export function nombreCapa(c: Capa): string {
  if (c.nombre) return c.nombre;
  if (c.tipo === "texto") return (c as CapaTexto).texto?.slice(0, 22) || "Texto";
  return ETIQUETA_TIPO[c.tipo];
}

/**
 * Distintivo de FORMATO + PLATAFORMA: los logos PELADOS (sin píldora ni fondo) — el icono
 * de formato (cámara = foto, vídeo = video, capas = carrusel) DELANTE del logo de la red
 * (X, Instagram, Facebook, TikTok, YouTube). Sin el NOMBRE de la red (solo iconos) y sin
 * partirse en dos burbujas. Orden del rediseño aprobado: FORMATO → RED → creador (IA/autor).
 *
 * Va en la CABECERA de la pieza, delante del logo de IA/autor — NO sobre la imagen, para no
 * taparla. Reusado por el feed de escritorio (`PostFeed`) y el móvil (`MobileFeed`).
 */
import { Camera, Layers, Video } from "lucide-react";

import { cn } from "@/lib/utils";
import { etiquetaFormato, normalizarFormato } from "@/pages/feed/formato";
import { iconoRed, nombreRed } from "@/pages/piezas/meta";

const ICONO_FORMATO = { foto: Camera, video: Video, carrusel: Layers } as const;

export function DistintivoRed({
  red,
  formato,
  className,
}: {
  red: string;
  formato?: string | null;
  className?: string;
}) {
  const Icono = iconoRed(red);
  const tieneFormato = formato != null && formato !== "";
  const fmt = normalizarFormato(formato);
  const IconoFormato = ICONO_FORMATO[fmt];
  const etiqueta = etiquetaFormato(formato);
  return (
    <span
      className={cn("inline-flex items-center gap-1 text-muted-foreground", className)}
      title={`${nombreRed(red)}${tieneFormato ? ` · ${etiqueta}` : ""}`}
    >
      {/* Mismo tamaño que el logo de red; la jerarquía formato<red la da la opacidad, no el tamaño. */}
      {tieneFormato && <IconoFormato className="h-3.5 w-3.5 opacity-70" aria-hidden="true" />}
      <Icono className="h-3.5 w-3.5" aria-hidden="true" />
      {/* Nombre accesible: el `title` no existe en táctil ni lo anuncian fiable los lectores. */}
      <span className="sr-only">
        {nombreRed(red)}
        {tieneFormato ? ` · ${etiqueta}` : ""}
      </span>
    </span>
  );
}

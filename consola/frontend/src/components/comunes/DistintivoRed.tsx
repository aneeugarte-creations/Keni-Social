/**
 * Distintivo de FORMATO + PLATAFORMA: los logos PELADOS (sin píldora ni fondo) — el icono
 * de formato (cámara = foto, vídeo = video) DELANTE del logo de la red (X, Instagram,
 * Facebook, TikTok, YouTube). Sin el NOMBRE de la red (solo iconos) y sin partirse en dos
 * burbujas. Orden del rediseño aprobado de la tarjeta: FORMATO → RED → creador (IA/autor).
 *
 * Va en la CABECERA de la pieza, delante del logo de IA/autor — NO sobre la imagen, para no
 * taparla. Reusado por el feed de escritorio (`PostFeed`) y el móvil (`MobileFeed`).
 */
import { Camera, Video } from "lucide-react";

import { cn } from "@/lib/utils";
import { iconoRed, nombreRed } from "@/pages/publicaciones/meta";

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
  const esVideo = (formato ?? "").trim().toLowerCase() === "video";
  const IconoFormato = esVideo ? Video : Camera;
  return (
    <span
      className={cn("inline-flex items-center gap-1 text-muted-foreground", className)}
      title={`${nombreRed(red)}${tieneFormato ? ` · ${esVideo ? "Video" : "Foto"}` : ""}`}
    >
      {tieneFormato && <IconoFormato className="h-3 w-3" aria-hidden="true" />}
      <Icono className="h-3.5 w-3.5" aria-hidden="true" />
    </span>
  );
}

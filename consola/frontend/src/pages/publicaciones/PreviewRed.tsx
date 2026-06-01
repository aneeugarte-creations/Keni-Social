/**
 * Vista previa de un post POR RED SOCIAL: un mockup que se parece a cómo se verá la
 * pieza en esa plataforma (no una tarjeta editorial). Cada red impone su relación de
 * aspecto de imagen, su tope de caracteres (recorta el copy como lo haría la red) y un
 * chrome aproximado (avatar + handle + acciones). Es la unidad del modo "Feed" del
 * tablero: una preview por (pieza × red), no una por pieza.
 */
import {
  Bookmark,
  Heart,
  ImageIcon,
  MessageCircle,
  Repeat2,
  Send,
  Share2,
  ThumbsUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import { aspectoRed, iconoRed, limiteRed, nombreRed } from "./meta";

/** Acciones (iconos estáticos) que se dibujan bajo el post, aproximadas por red. */
const ACCIONES_RED: Record<string, LucideIcon[]> = {
  instagram: [Heart, MessageCircle, Send, Bookmark],
  facebook: [ThumbsUp, MessageCircle, Share2],
  x: [MessageCircle, Repeat2, Heart, Share2],
  tiktok: [Heart, MessageCircle, Bookmark, Share2],
  youtube: [ThumbsUp, MessageCircle, Share2],
};

function accionesRed(red: string): LucideIcon[] {
  return ACCIONES_RED[red] ?? [Heart, MessageCircle, Share2];
}

/** Handle aproximado de la marca en la red: `@marcasinespacios`. */
function handleDe(marca: string): string {
  const limpio = marca.trim().replace(/\s+/g, "").toLowerCase();
  return limpio ? `@${limpio}` : "@marca";
}

export interface PreviewRedProps {
  red: string;
  marcaNombre: string;
  copy: string;
  imagenUrl?: string;
  /** Texto alternativo de la imagen (título de la pieza). */
  titulo?: string;
}

export function PreviewRed({ red, marcaNombre, copy, imagenUrl, titulo }: PreviewRedProps) {
  const Icono = iconoRed(red);
  const limite = limiteRed(red);
  const marca = marcaNombre || "Sin marca";
  // Recorta el copy al tope de la red (como lo haría la plataforma), con elipsis.
  const recortado =
    limite != null && copy.length > limite ? `${copy.slice(0, limite - 1).trimEnd()}…` : copy;
  const acciones = accionesRed(red);

  return (
    <Card className="overflow-hidden">
      <CardContent className="space-y-0 p-0">
        {/* Cabecera del "perfil" en esa red. */}
        <div className="flex items-center gap-2 px-3 pt-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
            {marca.slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium leading-tight">{marca}</p>
            <p className="truncate text-xs text-muted-foreground">{handleDe(marca)}</p>
          </div>
          <Icono className="h-4 w-4 shrink-0 text-muted-foreground" aria-label={nombreRed(red)} />
        </div>

        {/* Texto del post arriba (estilo X/Facebook) o abajo (estilo IG): lo mantenemos
            arriba para todas las redes salvo Instagram/TikTok, donde el copy va bajo la
            imagen. Para simplificar y ser consistentes, copy SIEMPRE bajo la imagen. */}

        {/* Lienzo de imagen con la relación de aspecto de la red. */}
        <div className={cn("mt-3 w-full bg-muted/50", aspectoRed(red))}>
          {imagenUrl ? (
            <img src={imagenUrl} alt={titulo || marca} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-muted-foreground/40">
              <ImageIcon className="h-10 w-10" />
            </div>
          )}
        </div>

        {/* Acciones aproximadas de la red. */}
        <div className="flex items-center gap-4 px-3 pt-2 text-muted-foreground">
          {acciones.map((A, i) => (
            <A key={i} className="h-4 w-4" />
          ))}
        </div>

        {/* Copy recortado al tope de la red. */}
        <div className="space-y-1 px-3 pb-3 pt-2">
          {recortado ? (
            <p className="line-clamp-4 whitespace-pre-wrap text-sm">
              <span className="font-medium">{handleDe(marca)} </span>
              {recortado}
            </p>
          ) : (
            <p className="text-sm italic text-muted-foreground/60">Sin copy para {nombreRed(red)}.</p>
          )}
          {limite != null && (
            <p
              className={cn(
                "text-[11px] tabular-nums",
                copy.length > limite ? "font-medium text-destructive" : "text-muted-foreground/70",
              )}
            >
              {copy.length} / {limite}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

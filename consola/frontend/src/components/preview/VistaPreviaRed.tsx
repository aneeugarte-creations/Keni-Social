/**
 * Vista previa estilizada de un post por red social.
 *
 * Dado `{red, marca, contenido, imagen_url?}` renderiza un mockup reconocible
 * (no pixel-perfect) de cómo se vería la pieza en esa red: X, Instagram,
 * Facebook, TikTok y YouTube. Reutilizado por "Generar copy" (ResultadoRedes) y
 * por el diálogo de edición de Publicaciones. Modo claro/oscuro; texto es-MX.
 */
import {
  Bookmark,
  Heart,
  ImageIcon,
  MessageCircle,
  MoreHorizontal,
  Music2,
  Play,
  Repeat2,
  Send,
  Share2,
  ThumbsUp,
} from "lucide-react";
import * as React from "react";

import { urlMedia } from "@/lib/api";
import { cn } from "@/lib/utils";

import { iconoRed, nombreRed } from "../../pages/publicaciones/meta";

export interface VistaPreviaRedProps {
  red: string;
  marca: string;
  contenido: string;
  /** Nombre del archivo o URL de la imagen; vacío = sin imagen. */
  imagen_url?: string;
}

/** Deriva un @handle a partir del nombre de la marca. */
function handleDe(marca: string): string {
  const limpio = marca.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
  return limpio ? `@${limpio}` : "@marca";
}

/** Iniciales de la marca para el avatar. */
function inicialesDe(marca: string): string {
  const palabras = marca.trim().split(/\s+/).filter(Boolean);
  if (palabras.length === 0) return "M";
  if (palabras.length === 1) return palabras[0].slice(0, 2).toUpperCase();
  return (palabras[0][0] + palabras[1][0]).toUpperCase();
}

/** Avatar circular con iniciales y el color de marca. */
function Avatar({ marca, className }: { marca: string; className?: string }) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground",
        className,
      )}
      aria-hidden="true"
    >
      {inicialesDe(marca)}
    </div>
  );
}

/** Placeholder de imagen (cuando no hay imagen adjunta). */
function PlaceholderImagen({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-1 bg-muted text-muted-foreground",
        className,
      )}
    >
      <ImageIcon className="h-6 w-6" />
      <span className="text-[10px]">Sin imagen</span>
    </div>
  );
}

/** Texto del post conservando saltos de línea; vacío muestra un guía. */
function Texto({ contenido, className }: { contenido: string; className?: string }) {
  if (!contenido.trim()) {
    return <p className={cn("italic text-muted-foreground", className)}>Sin texto…</p>;
  }
  return <p className={cn("whitespace-pre-wrap break-words", className)}>{contenido}</p>;
}

/** Mockup de X (antes Twitter). */
function PreviaX({ marca, contenido, imagen }: { marca: string; contenido: string; imagen: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 text-sm">
      <div className="flex gap-3">
        <Avatar marca={marca} className="h-10 w-10 text-sm" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold">{marca}</span>
            <span className="text-muted-foreground">{handleDe(marca)} · ahora</span>
            <MoreHorizontal className="ml-auto h-4 w-4 text-muted-foreground" />
          </div>
          <Texto contenido={contenido} className="mt-1 leading-relaxed" />
          {imagen && (
            <img
              src={imagen}
              alt=""
              className="mt-2.5 max-h-72 w-full rounded-2xl border border-border object-cover"
            />
          )}
          <div className="mt-3 flex max-w-xs items-center justify-between text-muted-foreground">
            <MessageCircle className="h-4 w-4" />
            <Repeat2 className="h-4 w-4" />
            <Heart className="h-4 w-4" />
            <Share2 className="h-4 w-4" />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Mockup de Instagram (imagen cuadrada + caption). */
function PreviaInstagram({
  marca,
  contenido,
  imagen,
}: {
  marca: string;
  contenido: string;
  imagen: string;
}) {
  return (
    <div className="mx-auto max-w-sm overflow-hidden rounded-xl border border-border bg-card text-sm">
      <div className="flex items-center gap-2.5 p-3">
        <Avatar marca={marca} className="h-8 w-8 text-[11px]" />
        <span className="font-semibold">{handleDe(marca).slice(1)}</span>
        <MoreHorizontal className="ml-auto h-4 w-4 text-muted-foreground" />
      </div>
      {imagen ? (
        <img src={imagen} alt="" className="aspect-square w-full object-cover" />
      ) : (
        <PlaceholderImagen className="aspect-square w-full" />
      )}
      <div className="space-y-2 p-3">
        <div className="flex items-center gap-4 text-foreground">
          <Heart className="h-5 w-5" />
          <MessageCircle className="h-5 w-5" />
          <Send className="h-5 w-5" />
          <Bookmark className="ml-auto h-5 w-5" />
        </div>
        <p className="leading-relaxed">
          <span className="font-semibold">{handleDe(marca).slice(1)} </span>
          <Texto contenido={contenido} className="inline" />
        </p>
      </div>
    </div>
  );
}

/** Mockup de Facebook. */
function PreviaFacebook({
  marca,
  contenido,
  imagen,
}: {
  marca: string;
  contenido: string;
  imagen: string;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card text-sm">
      <div className="flex items-center gap-2.5 p-3">
        <Avatar marca={marca} className="h-10 w-10 text-sm" />
        <div className="min-w-0">
          <p className="font-semibold leading-tight">{marca}</p>
          <p className="text-xs text-muted-foreground">Ahora · Público</p>
        </div>
        <MoreHorizontal className="ml-auto h-4 w-4 text-muted-foreground" />
      </div>
      <div className="px-3 pb-2">
        <Texto contenido={contenido} className="leading-relaxed" />
      </div>
      {imagen && <img src={imagen} alt="" className="max-h-80 w-full object-cover" />}
      <div className="flex items-center justify-around border-t border-border px-3 py-2 text-muted-foreground">
        <span className="flex items-center gap-1.5 text-xs font-medium">
          <ThumbsUp className="h-4 w-4" /> Me gusta
        </span>
        <span className="flex items-center gap-1.5 text-xs font-medium">
          <MessageCircle className="h-4 w-4" /> Comentar
        </span>
        <span className="flex items-center gap-1.5 text-xs font-medium">
          <Share2 className="h-4 w-4" /> Compartir
        </span>
      </div>
    </div>
  );
}

/** Mockup de TikTok (vertical 9:16 + caption sobreimpreso). */
function PreviaTikTok({
  marca,
  contenido,
  imagen,
}: {
  marca: string;
  contenido: string;
  imagen: string;
}) {
  return (
    <div className="mx-auto w-full max-w-[16rem]">
      <div className="relative aspect-[9/16] overflow-hidden rounded-xl border border-border bg-black">
        {imagen ? (
          <img src={imagen} alt="" className="h-full w-full object-cover opacity-90" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-neutral-900 text-neutral-500">
            <Play className="h-10 w-10" />
          </div>
        )}
        {/* Acciones laterales */}
        <div className="absolute bottom-16 right-2 flex flex-col items-center gap-3 text-white">
          <Heart className="h-6 w-6 drop-shadow" />
          <MessageCircle className="h-6 w-6 drop-shadow" />
          <Share2 className="h-6 w-6 drop-shadow" />
        </div>
        {/* Pie con marca + caption */}
        <div className="absolute inset-x-0 bottom-0 space-y-1 bg-gradient-to-t from-black/80 to-transparent p-3 text-white">
          <p className="text-sm font-semibold">{handleDe(marca)}</p>
          <Texto contenido={contenido} className="line-clamp-3 text-xs leading-snug" />
          <p className="flex items-center gap-1 text-[11px] text-white/80">
            <Music2 className="h-3 w-3" /> Sonido original
          </p>
        </div>
      </div>
    </div>
  );
}

/** Mockup de YouTube (thumbnail 16:9 + título + canal). */
function PreviaYouTube({
  marca,
  contenido,
  imagen,
}: {
  marca: string;
  contenido: string;
  imagen: string;
}) {
  // En YouTube el "contenido" hace de título: tomamos la primera línea.
  const titulo = contenido.trim().split("\n")[0] || "Título del video";
  return (
    <div className="mx-auto max-w-md text-sm">
      <div className="relative aspect-video overflow-hidden rounded-xl border border-border bg-muted">
        {imagen ? (
          <img src={imagen} alt="" className="h-full w-full object-cover" />
        ) : (
          <PlaceholderImagen className="h-full w-full" />
        )}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-600/90 text-white">
            <Play className="h-6 w-6 fill-current" />
          </div>
        </div>
      </div>
      <div className="mt-2.5 flex gap-2.5">
        <Avatar marca={marca} className="h-9 w-9 text-xs" />
        <div className="min-w-0">
          <p className="line-clamp-2 font-medium leading-snug">{titulo}</p>
          <p className="text-xs text-muted-foreground">{marca} · Hace un momento</p>
        </div>
      </div>
    </div>
  );
}

/** Mapa red -> componente de mockup. */
const PREVIAS: Record<
  string,
  React.ComponentType<{ marca: string; contenido: string; imagen: string }>
> = {
  x: PreviaX,
  instagram: PreviaInstagram,
  facebook: PreviaFacebook,
  tiktok: PreviaTikTok,
  youtube: PreviaYouTube,
};

/**
 * Renderiza la vista previa del post en la red indicada. Para redes sin mockup
 * específico cae a un layout tipo tarjeta genérica (estilo Facebook).
 */
export function VistaPreviaRed({ red, marca, contenido, imagen_url }: VistaPreviaRedProps) {
  const imagen = urlMedia(imagen_url);
  const nombreMarca = marca.trim() || "Marca";
  const Mockup = PREVIAS[red] ?? PreviaFacebook;
  const Icono = iconoRed(red);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icono className="h-4 w-4" aria-hidden="true" />
        <span>
          Vista previa en <span className="font-medium text-foreground">{nombreRed(red)}</span>
        </span>
      </div>
      <Mockup marca={nombreMarca} contenido={contenido} imagen={imagen} />
      <p className="text-[11px] text-muted-foreground">
        Mockup aproximado. El render real puede variar según la red.
      </p>
    </div>
  );
}

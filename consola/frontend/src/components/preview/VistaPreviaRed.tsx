/**
 * Vista previa estilizada de un post por red social.
 *
 * Dado `{red, marca, contenido, imagen_url?}` renderiza un mockup reconocible de
 * cómo se vería la pieza en esa red: X, Instagram, Facebook, TikTok y YouTube.
 * Reutilizado por "Generar copy" (ResultadoRedes) y por el diálogo de edición de
 * Publicaciones. Modo claro/oscuro; texto es-MX.
 *
 * Importante sobre el texto: las redes NO renderizan Markdown. Por eso aquí el
 * cuerpo se muestra TAL CUAL —respetando saltos de línea y enlazando URLs—, sin
 * convertir `**negrita**` ni listas a formato. (El render Markdown se reserva
 * para la lectura interna; ver `Markdown`.)
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
        "flex shrink-0 items-center justify-center rounded-full bg-primary font-semibold text-primary-foreground",
        className,
      )}
      aria-hidden="true"
    >
      {inicialesDe(marca)}
    </div>
  );
}

/** Placeholder de imagen elegante (cuando no hay imagen adjunta). */
function PlaceholderImagen({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-1.5 bg-gradient-to-br from-muted to-muted/60 text-muted-foreground",
        className,
      )}
    >
      <ImageIcon className="h-7 w-7 opacity-70" />
      <span className="text-[11px] font-medium">Sin imagen</span>
    </div>
  );
}

// Regex para detectar URLs sueltas y enlazarlas en la vista previa.
const RE_URL = /(https?:\/\/[^\s]+)/g;

/**
 * Texto del post tal y como lo vería la red: conserva saltos de línea y enlaza
 * URLs, pero NO interpreta Markdown (las redes no lo hacen). Vacío => guía.
 */
function TextoRed({ contenido, className }: { contenido: string; className?: string }) {
  if (!contenido.trim()) {
    return <p className={cn("italic text-muted-foreground", className)}>Sin texto…</p>;
  }
  const partes = contenido.split(RE_URL);
  return (
    <p className={cn("whitespace-pre-wrap break-words", className)}>
      {partes.map((parte, i) =>
        RE_URL.test(parte) ? (
          <a
            key={i}
            href={parte}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky-600 hover:underline dark:text-sky-400"
            onClick={(e) => e.stopPropagation()}
          >
            {parte}
          </a>
        ) : (
          <React.Fragment key={i}>{parte}</React.Fragment>
        ),
      )}
    </p>
  );
}

interface MockupProps {
  marca: string;
  contenido: string;
  imagen: string;
}

/** Mockup de X (antes Twitter). */
function PreviaX({ marca, contenido, imagen }: MockupProps) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 text-[15px]">
      <div className="flex gap-3">
        <Avatar marca={marca} className="h-11 w-11 text-sm" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1 text-[15px]">
            <span className="truncate font-bold leading-tight">{marca}</span>
            <span className="truncate text-muted-foreground">{handleDe(marca)}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground">ahora</span>
            <MoreHorizontal className="ml-auto h-4 w-4 shrink-0 text-muted-foreground" />
          </div>
          <TextoRed contenido={contenido} className="mt-0.5 leading-normal" />
          {imagen && (
            <img
              src={imagen}
              alt=""
              className="mt-3 aspect-video w-full rounded-2xl border border-border object-cover"
            />
          )}
          <div className="mt-3 flex max-w-md items-center justify-between text-muted-foreground">
            <span className="flex items-center gap-1.5 text-xs">
              <MessageCircle className="h-[18px] w-[18px]" />
            </span>
            <span className="flex items-center gap-1.5 text-xs">
              <Repeat2 className="h-[18px] w-[18px]" />
            </span>
            <span className="flex items-center gap-1.5 text-xs">
              <Heart className="h-[18px] w-[18px]" />
            </span>
            <span className="flex items-center gap-1.5 text-xs">
              <Share2 className="h-[18px] w-[18px]" />
            </span>
            <span aria-hidden="true" />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Mockup de Instagram (imagen cuadrada 1:1 + caption). */
function PreviaInstagram({ marca, contenido, imagen }: MockupProps) {
  return (
    <div className="mx-auto max-w-sm overflow-hidden rounded-xl border border-border bg-card text-sm">
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <Avatar
          marca={marca}
          className="h-8 w-8 text-[11px] ring-2 ring-pink-500/60 ring-offset-2 ring-offset-card"
        />
        <span className="text-[13px] font-semibold">{handleDe(marca).slice(1)}</span>
        <MoreHorizontal className="ml-auto h-4 w-4 text-muted-foreground" />
      </div>
      {imagen ? (
        <img src={imagen} alt="" className="aspect-square w-full object-cover" />
      ) : (
        <PlaceholderImagen className="aspect-square w-full" />
      )}
      <div className="space-y-2 px-3 py-2.5">
        <div className="flex items-center gap-4 text-foreground">
          <Heart className="h-6 w-6" />
          <MessageCircle className="h-6 w-6 -scale-x-100" />
          <Send className="h-6 w-6" />
          <Bookmark className="ml-auto h-6 w-6" />
        </div>
        <p className="text-[13px] font-semibold">128 Me gusta</p>
        <p className="text-[13px] leading-snug">
          <span className="font-semibold">{handleDe(marca).slice(1)} </span>
          <TextoRed contenido={contenido} className="inline" />
        </p>
      </div>
    </div>
  );
}

/** Mockup de Facebook. */
function PreviaFacebook({ marca, contenido, imagen }: MockupProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card text-[15px]">
      <div className="flex items-center gap-2.5 px-3 pt-3">
        <Avatar marca={marca} className="h-10 w-10 text-sm" />
        <div className="min-w-0">
          <p className="text-[15px] font-semibold leading-tight">{marca}</p>
          <p className="text-xs text-muted-foreground">Ahora · Público</p>
        </div>
        <MoreHorizontal className="ml-auto h-5 w-5 text-muted-foreground" />
      </div>
      <div className="px-3 py-2.5">
        <TextoRed contenido={contenido} className="leading-normal" />
      </div>
      {imagen ? (
        <img src={imagen} alt="" className="max-h-96 w-full object-cover" />
      ) : null}
      <div className="mt-1 flex items-center justify-around border-t border-border py-1.5 text-muted-foreground">
        <span className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium">
          <ThumbsUp className="h-[18px] w-[18px]" /> Me gusta
        </span>
        <span className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium">
          <MessageCircle className="h-[18px] w-[18px]" /> Comentar
        </span>
        <span className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium">
          <Share2 className="h-[18px] w-[18px]" /> Compartir
        </span>
      </div>
    </div>
  );
}

/** Mockup de TikTok (vertical 9:16 + caption sobreimpreso). */
function PreviaTikTok({ marca, contenido, imagen }: MockupProps) {
  return (
    <div className="mx-auto w-full max-w-[17rem]">
      <div className="relative aspect-[9/16] overflow-hidden rounded-2xl border border-border bg-black">
        {imagen ? (
          <img src={imagen} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-neutral-800 to-black text-neutral-500">
            <Play className="h-12 w-12" />
          </div>
        )}
        {/* Acciones laterales */}
        <div className="absolute bottom-20 right-2.5 flex flex-col items-center gap-4 text-white">
          <Avatar marca={marca} className="h-9 w-9 border-2 border-white text-[11px]" />
          <div className="flex flex-col items-center gap-1">
            <Heart className="h-7 w-7 fill-white drop-shadow" />
            <span className="text-[11px] font-semibold drop-shadow">12.4k</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <MessageCircle className="h-7 w-7 fill-white drop-shadow" />
            <span className="text-[11px] font-semibold drop-shadow">312</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <Share2 className="h-7 w-7 fill-white drop-shadow" />
            <span className="text-[11px] font-semibold drop-shadow">Compartir</span>
          </div>
        </div>
        {/* Pie con marca + caption */}
        <div className="absolute inset-x-0 bottom-0 space-y-1.5 bg-gradient-to-t from-black/85 via-black/40 to-transparent p-3 pr-16 text-white">
          <p className="text-sm font-semibold drop-shadow">{handleDe(marca)}</p>
          <TextoRed contenido={contenido} className="line-clamp-3 text-[13px] leading-snug drop-shadow" />
          <p className="flex items-center gap-1.5 text-xs text-white/90">
            <Music2 className="h-3.5 w-3.5" /> Sonido original — {marca}
          </p>
        </div>
      </div>
    </div>
  );
}

/** Mockup de YouTube (thumbnail 16:9 + título 2 líneas + canal). */
function PreviaYouTube({ marca, contenido, imagen }: MockupProps) {
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
          <div className="flex h-12 w-16 items-center justify-center rounded-xl bg-red-600 text-white shadow-lg">
            <Play className="h-6 w-6 fill-current" />
          </div>
        </div>
        <span className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-medium text-white">
          10:24
        </span>
      </div>
      <div className="mt-3 flex gap-3">
        <Avatar marca={marca} className="h-9 w-9 text-xs" />
        <div className="min-w-0">
          <p className="line-clamp-2 text-[15px] font-medium leading-snug">{titulo}</p>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{marca}</p>
          <p className="text-[13px] text-muted-foreground">1.2 mil vistas · Hace un momento</p>
        </div>
      </div>
    </div>
  );
}

/** Mapa red -> componente de mockup. */
const PREVIAS: Record<string, React.ComponentType<MockupProps>> = {
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
        Mockup aproximado. El render real puede variar según la red. Las redes no aplican formato
        Markdown.
      </p>
    </div>
  );
}

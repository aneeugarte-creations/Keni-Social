/**
 * Vista previa estilizada de un post por red social.
 *
 * Dado `{red, marca, contenido, imagen_url?}` renderiza un mockup reconocible de
 * cómo se vería la pieza en esa red: X, Instagram, Facebook, TikTok y YouTube.
 * Reutilizado por "Generar copy" (ResultadoRedes) y por el diálogo de edición de
 * Piezas. Modo claro/oscuro; texto es-MX.
 *
 * Importante sobre el texto: las redes NO renderizan Markdown. Por eso aquí el
 * cuerpo se muestra TAL CUAL —respetando saltos de línea y enlazando URLs—, sin
 * convertir `**negrita**` ni listas a formato. (El render Markdown se reserva
 * para la lectura interna; ver `Markdown`.)
 */
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
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
import { parsearCarrusel, type SlideCarrusel } from "@/lib/carrusel";
import { cn } from "@/lib/utils";

import { iconoRed, nombreRed, tamanoRed } from "../../pages/piezas/meta";

export interface VistaPreviaRedProps {
  red: string;
  marca: string;
  contenido: string;
  /** Texto que va DENTRO de la imagen (copy-in); vacío = sin texto sobre la imagen. */
  copy_in?: string;
  /** Nombre del archivo o URL de la imagen; vacío = sin imagen. */
  imagen_url?: string;
  /**
   * Slides EXTRA de una pieza `formato='carrusel'` (JSON `[{tipo,objeto}, …]`, campo
   * `Pieza.carrusel`). Con slides, la variante LIMPIA pinta un carrusel DESLIZABLE
   * (scroll lateral con snap, como en las redes de verdad): portada + slides en orden.
   * Vacío/ausente = imagen única de siempre.
   */
  carrusel?: string;
  /**
   * Título de la pieza (el tema). En la variante limpia da nombre accesible al área
   * interactiva ("Abrir: …") y `alt` a la imagen.
   */
  titulo?: string;
  /**
   * Variante `"limpia"`: callback al abrir la pieza. Lo dispara la IMAGEN (clic o teclado:
   * role=button + Enter/Espacio). Sin valor, la imagen no es interactiva.
   */
  onAbrir?: () => void;
  /**
   * Variante `"limpia"`: plegado CONTROLADO del caption ("leer más"). El feed lo eleva para que el
   * área de acciones expanda el MISMO caption que su texto. Sin `onAlternarCaption`, el caption
   * gestiona su propio plegado.
   */
  captionExpandido?: boolean;
  onAlternarCaption?: () => void;
  /**
   * `"completa"` (default): mockup fiel con su chrome social (como en "Generar copy" y el
   * diálogo de edición). `"limpia"`: feed de trabajo — conserva el logo/marca, el copy real
   * y la imagen, pero quita el chrome simulado (meta falsa, ⋯, barras de engagement) y el
   * pie "Mockup aproximado".
   */
  variante?: "completa" | "limpia";
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
      {/* text-xs (no text-[11px]): en escala con el "No generado" del PlaceholderRed contiguo. */}
      <span className="text-xs font-medium">Sin imagen</span>
    </div>
  );
}

// Regex para detectar URLs sueltas y enlazarlas en la vista previa.
const RE_URL = /(https?:\/\/[^\s]+)/g;

/**
 * Texto del post tal y como lo vería la red: conserva saltos de línea y enlaza
 * URLs, pero NO interpreta Markdown (las redes no lo hacen). Vacío => guía.
 *
 * Enlaces: subrayado PERMANENTE (WCAG 1.4.1: el color no puede ser la única señal; en táctil
 * no hay hover) y sky-700 (~4.6:1 sobre la tarjeta clara, AA). Con `enlacesTabulables: false`
 * los <a> salen del orden de tabulación: lo usa el copy PLEGADO (`CopyConLeerMas`), donde el
 * line-clamp los oculta y el focus ring caería en un punto invisible.
 */
const TextoRed = React.forwardRef<
  HTMLParagraphElement,
  { contenido: string; className?: string; enlacesTabulables?: boolean }
>(function TextoRed({ contenido, className, enlacesTabulables = true }, ref) {
  if (!contenido.trim()) {
    return (
      <p ref={ref} className={cn("italic text-muted-foreground", className)}>
        Sin texto
      </p>
    );
  }
  const partes = contenido.split(RE_URL);
  return (
    <p ref={ref} className={cn("whitespace-pre-wrap break-words", className)}>
      {partes.map((parte, i) =>
        RE_URL.test(parte) ? (
          <a
            key={i}
            href={parte}
            target="_blank"
            rel="noopener noreferrer"
            tabIndex={enlacesTabulables ? undefined : -1}
            className="text-sky-700 underline underline-offset-2 hover:text-sky-800 dark:text-sky-400 dark:hover:text-sky-300"
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
});

/**
 * Copy del feed estilo red social real: recortado a 2 líneas con un enlace "más" cuando el texto
 * desborda (y "menos" para volver a plegarlo). El bloque RESERVA siempre el alto de 2 líneas + la
 * fila del enlace, así TODAS las tarjetas miden lo mismo plegadas (rejilla uniforme), tengan o no
 * "más". Re-mide al cambiar el ancho (cambio de columnas) vía `ResizeObserver`.
 */
function CopyConLeerMas({
  contenido,
  expandido: expandidoProp,
  onAlternar,
}: {
  contenido: string;
  /** Plegado CONTROLADO: cuando el feed pasa `onAlternar`, el estado lo lleva el padre (para que
   *  el área de acciones expanda el mismo caption). Sin `onAlternar`, se gestiona aquí. */
  expandido?: boolean;
  onAlternar?: () => void;
}) {
  const controlado = onAlternar !== undefined;
  const [expandidoLocal, setExpandidoLocal] = React.useState(false);
  const expandido = controlado ? !!expandidoProp : expandidoLocal;
  const [hayMas, setHayMas] = React.useState(false);
  const ref = React.useRef<HTMLParagraphElement>(null);
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Mide el desbordamiento SOLO plegado (con el clamp puesto): si el texto real es más alto que
    // las 2 líneas visibles, hay "más". Expandido no se mide (se conserva el botón para "menos").
    const medir = () => {
      if (expandido) return;
      setHayMas(el.scrollHeight - el.clientHeight > 1);
    };
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, [contenido, expandido]);
  const alternar = onAlternar ?? (() => setExpandidoLocal((v) => !v));
  return (
    // TODA el área de texto alterna leer más/menos (conveniencia de puntero, estilo red social);
    // para su propio clic para no abrir la publicación. El control accesible es el BOTÓN
    // "más/menos" de abajo. Los enlaces del copy paran su propio clic (tocar una URL la abre).
    <div
      onClick={
        hayMas
          ? (e) => {
              e.stopPropagation();
              alternar();
            }
          : undefined
      }
      className={cn(hayMas && "cursor-pointer")}
    >
      <TextoRed
        ref={ref}
        contenido={contenido}
        // Plegado con desborde: los enlaces ocultos por el clamp salen del tab-order (el
        // usuario de teclado expande con el botón "más", que sí es tabulable, y entonces los
        // enlaces entran al foco ya visibles).
        enlacesTabulables={expandido || !hayMas}
        className={cn("text-sm leading-normal", !expandido && "line-clamp-2 min-h-[2.625rem]")}
      />
      {/* Fila del enlace SIEMPRE reservada (alto fijo) para que las tarjetas midan igual aunque
          unas tengan "más" y otras no. El margen negativo amplía el target táctil a ~32px sin
          alterar la fila h-5 reservada (WCAG 2.5.8). */}
      <div className="h-5">
        {hayMas && (
          <button
            type="button"
            aria-expanded={expandido}
            onClick={(e) => {
              e.stopPropagation();
              alternar();
            }}
            className="-m-1.5 p-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:underline"
          >
            {expandido ? "menos" : "más"}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Carrusel DESLIZABLE de la variante limpia (piezas `formato='carrusel'`): la PORTADA
 * (imagen compuesta) + los slides en crudo, en un strip horizontal con scroll-snap —se
 * desliza con el dedo/trackpad como en las redes de verdad— más flechas (escritorio),
 * contador "n/N" y puntos de posición. La PORTADA y los slides de IMAGEN abren el editor
 * al hacer clic; los slides de VIDEO no (el clic controla su reproducción).
 */
function CarruselLimpio({
  portada,
  copyIn,
  titulo,
  onAbrir,
  slides,
}: {
  portada: string;
  copyIn?: string;
  titulo?: string;
  onAbrir?: () => void;
  slides: SlideCarrusel[];
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [indice, setIndice] = React.useState(0);
  const total = slides.length + 1;
  const etiquetaAbrir = titulo ? `Abrir: ${titulo}` : "Abrir";

  // Índice visible derivado del scroll real (también cuando se desliza con el dedo).
  const onScroll = () => {
    const el = ref.current;
    if (!el || el.clientWidth === 0) return;
    setIndice(Math.min(total - 1, Math.max(0, Math.round(el.scrollLeft / el.clientWidth))));
  };
  const ir = (delta: -1 | 1) => {
    const el = ref.current;
    if (!el) return;
    el.scrollBy({ left: delta * el.clientWidth, behavior: "smooth" });
  };

  return (
    <div className="group/carrusel relative">
      <div
        ref={ref}
        onScroll={onScroll}
        className="flex aspect-[4/5] w-full snap-x snap-mandatory overflow-x-auto overflow-y-hidden bg-muted [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        role="group"
        aria-roledescription="carrusel"
        aria-label={`Carrusel de ${total} slides${titulo ? `: ${titulo}` : ""}`}
      >
        {/* Slide 1: la PORTADA (placa compuesta). Es el área que abre el editor. */}
        <div
          className={cn(
            "relative h-full w-full shrink-0 snap-center",
            onAbrir &&
              "group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
          )}
          role={onAbrir ? "button" : undefined}
          tabIndex={onAbrir ? 0 : undefined}
          title={onAbrir ? etiquetaAbrir : undefined}
          aria-label={onAbrir ? etiquetaAbrir : `Portada${titulo ? `: ${titulo}` : ""}`}
          onClick={onAbrir}
          onKeyDown={
            onAbrir
              ? (e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onAbrir();
                  }
                }
              : undefined
          }
        >
          {portada ? (
            <img
              src={portada}
              alt={titulo ?? ""}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover"
            />
          ) : (
            <PlaceholderImagen className="h-full w-full" />
          )}
          <CapaCopyIn texto={portada ? "" : copyIn} />
        </div>
        {/* Slides EN CRUDO, en su orden de publicación. Las IMÁGENES abren el editor al
            hacer clic (igual que la portada); los VIDEOS no: ahí el clic controla la
            reproducción (llevan sus propios controles). */}
        {slides.map((s, i) => {
          const clicable = !!onAbrir && s.tipo !== "video";
          return (
            <div
              key={`${s.objeto}-${i}`}
              className={cn(
                "relative h-full w-full shrink-0 snap-center bg-black",
                clicable &&
                  "group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              )}
              role={clicable ? "button" : undefined}
              tabIndex={clicable ? 0 : undefined}
              title={clicable ? etiquetaAbrir : undefined}
              aria-label={
                clicable ? `${etiquetaAbrir} (slide ${i + 2} de ${total})` : `Slide ${i + 2} de ${total}`
              }
              onClick={clicable ? onAbrir : undefined}
              onKeyDown={
                clicable
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onAbrir!();
                      }
                    }
                  : undefined
              }
            >
              {s.tipo === "video" ? (
                <video
                  src={urlMedia(s.objeto)}
                  controls
                  playsInline
                  preload="metadata"
                  className="h-full w-full object-contain"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <img
                  src={urlMedia(s.objeto)}
                  alt={`Slide ${i + 2}`}
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover"
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Contador "n/N" (arriba a la derecha, como IG). */}
      <span className="pointer-events-none absolute right-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-[11px] font-medium tabular-nums text-white">
        {indice + 1}/{total}
      </span>

      {/* Flechas (escritorio): aparecen al hover/focus; en táctil se desliza con el dedo. */}
      {indice > 0 && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            ir(-1);
          }}
          className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-background/85 p-1.5 text-foreground opacity-0 shadow-sm transition-opacity hover:bg-background focus-visible:opacity-100 group-hover/carrusel:opacity-100"
          aria-label="Slide anterior"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      )}
      {indice < total - 1 && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            ir(1);
          }}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-background/85 p-1.5 text-foreground opacity-0 shadow-sm transition-opacity hover:bg-background focus-visible:opacity-100 group-hover/carrusel:opacity-100"
          aria-label="Slide siguiente"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      )}

      {/* Puntos de posición (abajo, centrados). Decorativos: el contador ya da la posición. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-1.5 flex justify-center gap-1"
        aria-hidden="true"
      >
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 w-1.5 rounded-full bg-white/60 shadow-sm transition-colors",
              i === indice && "bg-white",
            )}
          />
        ))}
      </div>
    </div>
  );
}

interface MockupProps {
  marca: string;
  contenido: string;
  copyIn?: string;
  imagen: string;
  /**
   * Variante LIMPIA (feed de trabajo): oculta el "chrome" social simulado (meta falsa,
   * menú ⋯ y barras de Me gusta/Comentar/Compartir, contadores de engagement) para dejar
   * solo lo REAL de la pieza —marca + copy + imagen—. Default `false` = mockup completo,
   * como lo usan "Generar copy" y el diálogo de edición.
   */
  limpia?: boolean;
}

/**
 * Capa con el TEXTO EN IMAGEN (copy-in) sobre el área de imagen. Es una simulación del
 * texto sobre la placa (NO el estampado real, que es trabajo del compositor): se superpone
 * centrado, en blanco con sombra, para previsualizar cómo conviviría con la imagen. Se
 * inserta dentro de un contenedor `relative`. Vacío => no renderiza nada.
 */
function CapaCopyIn({ texto }: { texto?: string }) {
  if (!texto?.trim()) return null;
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-3">
      <p className="whitespace-pre-wrap break-words text-center text-base font-extrabold uppercase leading-tight text-white [text-shadow:_0_1px_6px_rgb(0_0_0_/_95%)]">
        {texto}
      </p>
    </div>
  );
}

/** Mockup de X (antes Twitter). */
function PreviaX({ marca, contenido, copyIn, imagen, limpia }: MockupProps) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 text-[15px]">
      <div className="flex gap-3">
        <Avatar marca={marca} className="h-11 w-11 text-sm" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1 text-[15px]">
            <span className="truncate font-bold leading-tight">{marca}</span>
            <span className="truncate text-muted-foreground">{handleDe(marca)}</span>
            {!limpia && (
              <>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground">ahora</span>
                <MoreHorizontal className="ml-auto h-4 w-4 shrink-0 text-muted-foreground" />
              </>
            )}
          </div>
          <TextoRed contenido={contenido} className="mt-0.5 leading-normal" />
          {(imagen || copyIn?.trim()) && (
            <div className="relative mt-3 aspect-[4/5] w-full overflow-hidden rounded-2xl border border-border">
              {imagen ? (
                <img src={imagen} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
              ) : (
                <PlaceholderImagen className="h-full w-full" />
              )}
              <CapaCopyIn texto={copyIn} />
            </div>
          )}
          {!limpia && (
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
          )}
        </div>
      </div>
    </div>
  );
}

/** Mockup de Instagram (imagen 4:5 vertical + caption). */
function PreviaInstagram({ marca, contenido, copyIn, imagen, limpia }: MockupProps) {
  return (
    <div className="mx-auto max-w-sm overflow-hidden rounded-xl border border-border bg-card text-sm">
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <Avatar
          marca={marca}
          className="h-8 w-8 text-[11px] ring-2 ring-pink-500/60 ring-offset-2 ring-offset-card"
        />
        <span className="text-[13px] font-semibold">{handleDe(marca).slice(1)}</span>
        {!limpia && <MoreHorizontal className="ml-auto h-4 w-4 text-muted-foreground" />}
      </div>
      <div className="relative aspect-[4/5] w-full overflow-hidden">
        {imagen ? (
          <img src={imagen} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
        ) : (
          <PlaceholderImagen className="h-full w-full" />
        )}
        <CapaCopyIn texto={copyIn} />
      </div>
      <div className="space-y-2 px-3 py-2.5">
        {!limpia && (
          <>
            <div className="flex items-center gap-4 text-foreground">
              <Heart className="h-6 w-6" />
              <MessageCircle className="h-6 w-6 -scale-x-100" />
              <Send className="h-6 w-6" />
              <Bookmark className="ml-auto h-6 w-6" />
            </div>
          </>
        )}
        <p className="text-[13px] leading-snug">
          <span className="font-semibold">{handleDe(marca).slice(1)} </span>
          <TextoRed contenido={contenido} className="inline" />
        </p>
      </div>
    </div>
  );
}

/** Mockup de Facebook. */
function PreviaFacebook({ marca, contenido, copyIn, imagen, limpia }: MockupProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card text-[15px]">
      <div className="flex items-center gap-2.5 px-3 pt-3">
        <Avatar marca={marca} className="h-10 w-10 text-sm" />
        <div className="min-w-0">
          <p className="text-[15px] font-semibold leading-tight">{marca}</p>
          {!limpia && <p className="text-xs text-muted-foreground">Ahora · Público</p>}
        </div>
        {!limpia && <MoreHorizontal className="ml-auto h-5 w-5 text-muted-foreground" />}
      </div>
      <div className="px-3 py-2.5">
        <TextoRed contenido={contenido} className="leading-normal" />
      </div>
      {imagen ? (
        <div className="relative aspect-[4/5] w-full overflow-hidden">
          <img src={imagen} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
          <CapaCopyIn texto={copyIn} />
        </div>
      ) : null}
      {!limpia && (
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
      )}
    </div>
  );
}

/** Mockup de TikTok (imagen 4:5 + caption sobreimpreso). */
function PreviaTikTok({ marca, contenido, copyIn, imagen, limpia }: MockupProps) {
  return (
    <div className="mx-auto w-full max-w-sm">
      <div className="relative aspect-[4/5] overflow-hidden rounded-2xl border border-border bg-black">
        {imagen ? (
          <img src={imagen} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-neutral-800 to-black text-neutral-500">
            <Play className="h-12 w-12" />
          </div>
        )}
        <CapaCopyIn texto={copyIn} />
        {/* Acciones laterales (engagement simulado): se ocultan en variante limpia. */}
        {!limpia && (
          <div className="absolute bottom-20 right-2.5 flex flex-col items-center gap-4 text-white">
            <Avatar marca={marca} className="h-9 w-9 border-2 border-white text-[11px]" />
            <div className="flex flex-col items-center gap-1">
              <Heart className="h-7 w-7 fill-white drop-shadow" />
            </div>
            <div className="flex flex-col items-center gap-1">
              <MessageCircle className="h-7 w-7 fill-white drop-shadow" />
            </div>
            <div className="flex flex-col items-center gap-1">
              <Share2 className="h-7 w-7 fill-white drop-shadow" />
              <span className="text-[11px] font-semibold drop-shadow">Compartir</span>
            </div>
          </div>
        )}
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

/** Mockup de YouTube (thumbnail 4:5 + título 2 líneas + canal). */
function PreviaYouTube({ marca, contenido, copyIn, imagen }: MockupProps) {
  // En YouTube el "contenido" hace de título: tomamos la primera línea.
  const titulo = contenido.trim().split("\n")[0] || "Título del video";
  return (
    <div className="mx-auto max-w-md text-sm">
      <div className="relative aspect-[4/5] overflow-hidden rounded-xl border border-border bg-muted">
        {imagen ? (
          <img src={imagen} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
        ) : (
          <PlaceholderImagen className="h-full w-full" />
        )}
        <CapaCopyIn texto={copyIn} />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex h-12 w-16 items-center justify-center rounded-xl bg-red-600 text-white shadow-lg">
            <Play className="h-6 w-6 fill-current" />
          </div>
        </div>
      </div>
      <div className="mt-3 flex gap-3">
        <Avatar marca={marca} className="h-9 w-9 text-xs" />
        <div className="min-w-0">
          <p className="line-clamp-2 text-[15px] font-medium leading-snug">{titulo}</p>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{marca}</p>
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
export function VistaPreviaRed({
  red,
  marca,
  contenido,
  copy_in,
  imagen_url,
  carrusel,
  titulo,
  onAbrir,
  captionExpandido,
  onAlternarCaption,
  variante = "completa",
}: VistaPreviaRedProps) {
  const imagen = urlMedia(imagen_url);
  const Icono = iconoRed(red);

  // FEED (variante limpia): tarjeta UNIFORME para TODAS las redes — misma caja, imagen a
  // 4:5 a ancho completo, SIN nada superpuesto que tape la imagen. El distintivo de
  // plataforma + formato va en la CABECERA (junto al logo de IA/autor), no aquí.
  if (variante === "limpia") {
    const etiquetaAbrir = titulo ? `Abrir: ${titulo}` : "Abrir";
    // CARRUSEL deslizable (piezas con slides): portada + media en crudo, scroll lateral
    // con snap (como en las redes de verdad). Sin slides, la imagen única de siempre.
    const slides = parsearCarrusel(carrusel);
    if (slides.length > 0) {
      return (
        <div>
          <CarruselLimpio
            portada={imagen}
            copyIn={copy_in}
            titulo={titulo}
            onAbrir={onAbrir}
            slides={slides}
          />
          <div className="px-4 pb-1 pt-3">
            <CopyConLeerMas
              contenido={contenido}
              expandido={captionExpandido}
              onAlternar={onAlternarCaption}
            />
          </div>
        </div>
      );
    }
    return (
      <div>
        {/* La imagen abre la publicación (`onAbrir`) y da el acceso por TECLADO (role=button +
            Enter/Espacio); sin foco visible no habría entrada accesible al detalle. El copy de
            abajo abre lo mismo al hacer clic, burbujeando a la tarjeta. */}
        <div
          className={cn(
            "relative aspect-[4/5] w-full overflow-hidden bg-muted",
            onAbrir &&
              "cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
          )}
          role={onAbrir ? "button" : undefined}
          tabIndex={onAbrir ? 0 : undefined}
          title={onAbrir ? etiquetaAbrir : undefined}
          aria-label={onAbrir ? etiquetaAbrir : undefined}
          onClick={onAbrir}
          onKeyDown={
            onAbrir
              ? (e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onAbrir();
                  }
                }
              : undefined
          }
        >
          {imagen ? (
            <img src={imagen} alt={titulo ?? ""} loading="lazy" decoding="async" className="h-full w-full object-cover" />
          ) : (
            <PlaceholderImagen className="h-full w-full" />
          )}
          {/* El copy-in solo cuando NO hay imagen: si hay placa compuesta, el texto va horneado. */}
          <CapaCopyIn texto={imagen ? "" : copy_in} />
        </div>
        {/* Copy (caption) bajo la imagen, idéntico para toda red: recortado a 2 líneas con "leer
            más" estilo red social, y alto reservado para que todas las tarjetas midan igual. */}
        <div className="px-4 pb-1 pt-3">
          <CopyConLeerMas
            contenido={contenido}
            expandido={captionExpandido}
            onAlternar={onAlternarCaption}
          />
        </div>
      </div>
    );
  }

  // PREVIA COMPLETA: mockup FIEL por red con su chrome (p. ej. "Generar copy" o el editor).
  const nombreMarca = marca.trim() || "Marca";
  const Mockup = PREVIAS[red] ?? PreviaFacebook;
  const tam = tamanoRed(red);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icono className="h-4 w-4" aria-hidden="true" />
        <span>
          Vista previa en <span className="font-medium text-foreground">{nombreRed(red)}</span>
        </span>
        {tam && (
          <span
            className="ml-auto rounded-full border border-border px-2 py-0.5 tabular-nums"
            title={`Recomendado: ${tam.ratio}, ${tam.px} px`}
          >
            {tam.ratio} · {tam.px} px
          </span>
        )}
      </div>
      {/* El overlay de simulación del copy-in solo cuando NO hay imagen: si ya hay una placa
          compuesta, el texto va horneado en la imagen y duplicarlo se vería doble. */}
      <Mockup
        marca={nombreMarca}
        contenido={contenido}
        copyIn={imagen ? "" : copy_in}
        imagen={imagen}
        limpia={false}
      />
    </div>
  );
}

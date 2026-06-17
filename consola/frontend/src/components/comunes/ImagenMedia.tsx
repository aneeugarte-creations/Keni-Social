/**
 * Imagen del almacén de medios servida a la RESOLUCIÓN de render, no a tamaño completo.
 *
 * Pide al back una DERIVADA WebP redimensionada (`/api/media/{n}?w=…`) en vez del original (que
 * puede pesar hasta 15 MB): así el feed/listas/preview cargan rápido y sin el "telón" (revelado
 * progresivo de arriba a abajo) de descargar una foto enorme dentro de un contenedor pequeño.
 *
 * - Responsive (`anchos` + `sizes`): emite `srcset`+`sizes` para que el navegador elija el ancho
 *   según el viewport y el DPR (retina pide ~2×). `src` cae al mayor de `anchos`.
 * - Fijo (`ancho`): un solo ancho (miniaturas de tamaño conocido).
 * - Reserva el HUECO: el contenedor padre debe fijar el aspecto (p. ej. `aspect-[4/5]`) y un
 *   fondo (`bg-muted`); aquí la imagen entra con un fundido al cargar (`onLoad`), de modo que el
 *   skeleton del fondo se ve hasta que la imagen está lista (nada salta ni se revela en telón).
 *
 * Para máxima calidad (descargas, vista a tamaño completo) NO se usa esto: ahí se sirve el
 * original sin `?w`.
 */
import * as React from "react";

import { srcsetMedia, urlMediaAncho } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface ImagenMediaProps {
  /** Nombre del objeto (`fotos/…png`) o URL ya formada (`/api/media/…`). */
  nombreOUrl: string;
  alt: string;
  className?: string;
  /** Anchos servibles para `srcset` (responsive). El `src` usa el mayor. */
  anchos?: number[];
  /** `sizes` que acompaña a `srcset` (ancho CSS estimado del hueco). */
  sizes?: string;
  /** Ancho FIJO cuando el hueco es de tamaño conocido (miniaturas). Default 640. */
  ancho?: number;
  loading?: "lazy" | "eager";
}

export function ImagenMedia({
  nombreOUrl,
  alt,
  className,
  anchos,
  sizes,
  ancho,
  loading = "lazy",
}: ImagenMediaProps) {
  const [cargada, setCargada] = React.useState(false);
  const ref = React.useRef<HTMLImageElement>(null);

  // Una imagen ya en caché puede completar ANTES de que React enganche `onLoad`: si al montar
  // ya está completa, márcala cargada para no quedarnos en opacidad 0 para siempre.
  React.useEffect(() => {
    if (ref.current?.complete) setCargada(true);
  }, [nombreOUrl]);

  const responsive = anchos && anchos.length > 0;
  const src = urlMediaAncho(nombreOUrl, responsive ? Math.max(...anchos) : (ancho ?? 640));
  const srcSet = responsive ? srcsetMedia(nombreOUrl, anchos) : undefined;

  return (
    <img
      ref={ref}
      src={src}
      srcSet={srcSet}
      sizes={srcSet ? sizes : undefined}
      alt={alt}
      loading={loading}
      decoding="async"
      onLoad={() => setCargada(true)}
      className={cn(
        "transition-opacity duration-300",
        cargada ? "opacity-100" : "opacity-0",
        className,
      )}
    />
  );
}

/**
 * Infraestructura COMPARTIDA del scroll infinito del feed (escritorio `FeedIdeacion` y móvil
 * `MobileFeed`): el sentinel que pide la siguiente página, el pie de estado del feed y el
 * skeleton con la anatomía real de una tarjeta. Un solo sitio para que ambas superficies se
 * comporten y se vean IGUAL (antes eran copias divergentes).
 */
import { Loader2 } from "lucide-react";
import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";

/**
 * Sentinel de scroll infinito: devuelve el ref a colgar de un nodo invisible al fondo del feed;
 * cuando entra en viewport, pide la siguiente página (con guardas de `hasNextPage` /
 * `isFetchingNextPage` para no encadenar peticiones). `habilitado: false` lo apaga sin
 * desmontar el nodo (lo usa el tope de búsqueda de las vistas filtradas).
 */
export function useSentinelInfinito({
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  habilitado = true,
}: {
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => Promise<unknown>;
  habilitado?: boolean;
}) {
  const sentinelRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const nodo = sentinelRef.current;
    if (!nodo || !hasNextPage || !habilitado) return;
    const obs = new IntersectionObserver(
      (entradas) => {
        if (entradas[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      // `rootMargin` adelanta la carga ~600px antes del fondo: el feed se siente continuo, sin
      // que el usuario llegue a ver el final antes de que aparezca lo siguiente.
      { rootMargin: "600px 0px" },
    );
    obs.observe(nodo);
    return () => obs.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, habilitado]);
  return sentinelRef;
}

/**
 * Pie del feed, con UN solo estilo para los tres estados: "buscando" (vista filtrada vacía
 * rastreando páginas), "cargando" (scroll infinito trayendo más) y "fin" (feed agotado).
 */
export function PieFeed({ estado }: { estado: "buscando" | "cargando" | "fin" }) {
  if (estado === "fin") {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Has llegado al final del feed.
      </p>
    );
  }
  return (
    <div
      className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-4 w-4 animate-spin" />
      {estado === "buscando" ? "Buscando piezas…" : "Cargando más…"}
    </div>
  );
}

/**
 * Skeleton con la ANATOMÍA real de una tarjeta del feed (cabecera + imagen 4:5 + copy + fila de
 * acciones): una tarjeta real mide ~700-900px de alto, así que un bloque plano de 320px
 * provocaba un salto de layout brutal al aterrizar el contenido.
 */
export function SkeletonPost() {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="px-4 py-3">
        <Skeleton className="h-4 w-1/3" />
      </div>
      <Skeleton className="aspect-[4/5] w-full rounded-none" />
      <div className="space-y-2 px-4 py-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      {/* Pie con la anatomía real de la fila de acciones: badge de etapa (izq) + iconos (der). */}
      <div className="flex items-center justify-between px-4 pb-3">
        <Skeleton className="h-5 w-24 rounded-md" />
        <div className="flex gap-1">
          <Skeleton className="h-8 w-8 rounded-md" />
          <Skeleton className="h-8 w-8 rounded-md" />
        </div>
      </div>
    </div>
  );
}

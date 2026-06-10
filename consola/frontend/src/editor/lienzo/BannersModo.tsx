// Banners flotantes de los modos de edición de imagen (reencuadre / recorte). Presentacional:
// cada uno se muestra cuando su modo está activo y llama a `onListo` al cerrar.
//
// Accesibilidad: cada banner es una región `role="status"` (aria-live cortés implícito), así el
// lector de pantalla ANUNCIA la entrada al modo al montarse; el nombre del modo va en un span
// `sr-only` (visualmente ya lo dice el contexto) y los iconos decorativos quedan `aria-hidden`.

import { Check, Crop as CropIcon, Move, X } from "lucide-react";

export function BannerReencuadre({ onListo }: { onListo?: () => void }) {
  return (
    <div
      role="status"
      className="absolute left-1/2 top-2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs shadow-md"
    >
      <Move aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="sr-only">Modo reencuadre activo.</span>
      <span>Arrastra la foto · rueda para zoom</span>
      <button
        onClick={() => onListo?.()}
        className="ml-1 flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-primary-foreground"
      >
        <Check aria-hidden="true" className="h-3.5 w-3.5" /> Listo
      </button>
    </div>
  );
}

// Banner del modo RECORTE estilo Canva: "Hecho" CONFIRMA (Enter) y "Cancelar" RESTAURA el recorte
// de entrada (Esc). Las instrucciones reflejan la interacción del CropOverlay (arrastrar la foto
// para reencuadrar; esquinas o rueda para escalarla dentro del marco).
export function BannerRecorte({ onListo, onCancelar }: { onListo?: () => void; onCancelar?: () => void }) {
  return (
    <div
      role="status"
      className="absolute left-1/2 top-2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs shadow-md"
    >
      <CropIcon aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="sr-only">Modo recorte activo.</span>
      <span>Arrastra la foto · esquinas o rueda para escalar</span>
      <button
        onClick={() => onCancelar?.()}
        className="ml-1 flex items-center gap-1 rounded-full border border-border px-2 py-0.5 hover:bg-muted"
      >
        <X aria-hidden="true" className="h-3.5 w-3.5" /> Cancelar
      </button>
      <button
        onClick={() => onListo?.()}
        className="flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-primary-foreground"
      >
        <Check aria-hidden="true" className="h-3.5 w-3.5" /> Hecho
      </button>
    </div>
  );
}

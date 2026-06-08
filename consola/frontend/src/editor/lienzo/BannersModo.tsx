// Banners flotantes de los modos de edición de imagen (reencuadre / recorte). Presentacional:
// cada uno se muestra cuando su modo está activo y llama a `onListo` al cerrar.

import { Check, Crop as CropIcon, Move } from "lucide-react";

export function BannerReencuadre({ onListo }: { onListo?: () => void }) {
  return (
    <div className="absolute left-1/2 top-2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs shadow-md">
      <Move className="h-3.5 w-3.5 text-muted-foreground" />
      <span>Arrastra la foto · rueda para zoom</span>
      <button
        onClick={() => onListo?.()}
        className="ml-1 flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-primary-foreground"
      >
        <Check className="h-3.5 w-3.5" /> Listo
      </button>
    </div>
  );
}

export function BannerRecorte({ onListo }: { onListo?: () => void }) {
  return (
    <div className="absolute left-1/2 top-2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs shadow-md">
      <CropIcon className="h-3.5 w-3.5 text-muted-foreground" />
      <span>Arrastra los tiradores para recortar</span>
      <button
        onClick={() => onListo?.()}
        className="ml-1 flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-primary-foreground"
      >
        <Check className="h-3.5 w-3.5" /> Listo
      </button>
    </div>
  );
}

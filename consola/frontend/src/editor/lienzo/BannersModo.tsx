// Banners flotantes de los modos de edición de imagen (reencuadre / recorte). Presentacional:
// cada uno se muestra cuando su modo está activo y llama a `onListo` al cerrar.
//
// Accesibilidad: cada banner es una región `role="status"` (aria-live cortés implícito), así el
// lector de pantalla ANUNCIA la entrada al modo al montarse; el nombre del modo va en un span
// `sr-only` (visualmente ya lo dice el contexto) y los iconos decorativos quedan `aria-hidden`.

import { Check, Crop as CropIcon, Move, X } from "lucide-react";

import { OPCIONES_ASPECTO, useAspectoRecorte } from "./aspectoRecorte";

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

// Banner del modo RECORTE: "Hecho" CONFIRMA (Enter) y "Cancelar" RESTAURA el recorte de entrada
// (Esc). La ayuda DIFERENCIA foto de forma (leído del estado compartido del recorte): la foto se
// reencuadra dentro del marco; la forma encoge el recuadro. Los CHIPS de relación de aspecto fijan
// la proporción del recorte (Libre / 1:1 / 4:5 / 9:16 / 16:9 / Original).
export function BannerRecorte({ onListo, onCancelar }: { onListo?: () => void; onCancelar?: () => void }) {
  const esImagen = useAspectoRecorte((s) => s.esImagen);
  const claveActiva = useAspectoRecorte((s) => s.clave);
  const fijar = useAspectoRecorte((s) => s.fijar);
  // Foto = reencuadra el crop; forma = encoge el recuadro. Mientras el tipo no se conoce (null,
  // primer render) se usa la ayuda de foto (caso mayoritario).
  const ayuda =
    esImagen === false
      ? "Arrastra los tiradores para recortar el recuadro"
      : "Arrastra los bordes para recortar · la foto o rueda para encuadrar";
  return (
    <div
      role="status"
      className="absolute left-1/2 top-2 z-30 flex -translate-x-1/2 flex-wrap items-center justify-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs shadow-md"
    >
      <CropIcon aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="sr-only">Modo recorte activo.</span>
      <span>{ayuda}</span>
      {/* Relación de aspecto FIJA del recorte. Grupo de radio: solo uno activo a la vez. */}
      <div role="radiogroup" aria-label="Relación de aspecto" className="flex items-center gap-1">
        {OPCIONES_ASPECTO.map((o) => {
          const activo = o.clave === claveActiva;
          return (
            <button
              key={o.clave}
              type="button"
              role="radio"
              aria-checked={activo}
              onClick={() => fijar(o.clave, o.ratio)}
              className={`rounded-full px-2 py-0.5 text-[11px] transition-colors ${
                activo
                  ? "bg-primary text-primary-foreground"
                  : "border border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              {o.etiqueta}
            </button>
          );
        })}
      </div>
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

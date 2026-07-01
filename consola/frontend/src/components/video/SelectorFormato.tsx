/**
 * Selector de FORMATO/aspecto del Estudio de Video (9:16 / 1:1 / 16:9).
 *
 * Fija el lienzo de la composición. Cada opción muestra un icono SVG con la FORMA
 * proporcional del aspecto (rectángulo vertical, cuadrado, rectángulo horizontal)
 * para reconocimiento visual inmediato, seguido del texto de la relación.
 */
import { ASPECTOS_VIDEO, type AspectoVideo } from "@/lib/video";

// Dimensiones del viewBox de cada aspecto. Todos comparten la misma base (16 unidades
// como máximo) para que el grosor de trazo sea coherente entre los tres iconos.
const DIMS: Record<AspectoVideo, { vw: number; vh: number }> = {
  "9:16": { vw: 9, vh: 16 },
  "1:1":  { vw: 16, vh: 16 },
  "16:9": { vw: 16, vh: 9 },
};

const PX_BASE = 13; // dimensión máxima en píxeles para los iconos

function IconoAspecto({ aspecto, activo }: { aspecto: AspectoVideo; activo: boolean }) {
  const { vw, vh } = DIMS[aspecto];
  const escala = PX_BASE / Math.max(vw, vh);
  const pw = Math.round(vw * escala);
  const ph = Math.round(vh * escala);
  return (
    <svg
      width={pw}
      height={ph}
      viewBox={`0 0 ${vw} ${vh}`}
      aria-hidden="true"
      className={activo ? "text-primary-foreground" : "text-muted-foreground"}
    >
      <rect
        x="0.5"
        y="0.5"
        width={vw - 1}
        height={vh - 1}
        rx="0.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
      />
    </svg>
  );
}

export interface SelectorFormatoProps {
  aspecto: AspectoVideo;
  onCambio: (aspecto: AspectoVideo) => void;
  disabled?: boolean;
  /** Muestra el párrafo de ayuda sobre márgenes punteados. Por defecto `true`. */
  mostrarAyuda?: boolean;
}

export function SelectorFormato({
  aspecto,
  onCambio,
  disabled,
  mostrarAyuda = true,
}: SelectorFormatoProps) {
  return (
    <div className={mostrarAyuda ? "space-y-1.5" : undefined}>
      <div
        className="inline-flex gap-0.5 rounded-md border border-border p-0.5"
        role="radiogroup"
        aria-label="Formato de video"
      >
        {ASPECTOS_VIDEO.map((a) => {
          const activo = a === aspecto;
          return (
            <button
              key={a}
              type="button"
              role="radio"
              aria-checked={activo}
              disabled={disabled}
              onClick={() => onCambio(a)}
              className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                activo
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
              }`}
            >
              <IconoAspecto aspecto={a} activo={activo} />
              {a}
            </button>
          );
        })}
      </div>
      {mostrarAyuda && (
        <p className="text-[11px] text-muted-foreground/70">
          Mantén contenido en los márgenes punteados
        </p>
      )}
    </div>
  );
}

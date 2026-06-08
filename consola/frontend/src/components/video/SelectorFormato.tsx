/**
 * Selector de FORMATO/aspecto del Estudio de Video (9:16 / 1:1 / 16:9).
 *
 * Fija el lienzo de la composición. Selector compacto de solo los números (segmentado),
 * sin rectángulos de muestra: la relación de aspecto se entiende del propio texto.
 */
import { ASPECTOS_VIDEO, type AspectoVideo } from "@/lib/video";

export interface SelectorFormatoProps {
  aspecto: AspectoVideo;
  onCambio: (aspecto: AspectoVideo) => void;
  disabled?: boolean;
}

export function SelectorFormato({ aspecto, onCambio, disabled }: SelectorFormatoProps) {
  return (
    <div className="space-y-2">
      <div
        className="inline-flex gap-1 rounded-md border border-border p-0.5"
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
              className={`rounded px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                activo
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
              }`}
            >
              {a}
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-muted-foreground/70">
        Zona segura: deja texto y logos dentro de los márgenes punteados del preview (el chrome
        de cada red tapa los bordes superior e inferior).
      </p>
    </div>
  );
}

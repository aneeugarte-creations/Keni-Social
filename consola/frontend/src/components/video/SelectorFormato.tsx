/**
 * Selector de FORMATO/aspecto del Estudio de Video (9:16 / 1:1 / 16:9).
 *
 * Fija el lienzo de la composición y muestra el preset elegido (resolución + zonas seguras
 * por plataforma). Los presets vienen de `GET /api/video/formatos` con fallback local a
 * `PRESETS_FORMATO_VIDEO` si la API aún no responde.
 */
import { Check, RectangleHorizontal, RectangleVertical, Square } from "lucide-react";

import {
  ASPECTOS_VIDEO,
  ETIQUETA_ASPECTO,
  presetParaAspecto,
  type AspectoVideo,
  type PresetFormatoVideo,
} from "@/lib/video";

const ICONO: Record<AspectoVideo, typeof Square> = {
  "9:16": RectangleVertical,
  "1:1": Square,
  "16:9": RectangleHorizontal,
};

export interface SelectorFormatoProps {
  aspecto: AspectoVideo;
  onCambio: (aspecto: AspectoVideo) => void;
  /** Presets servidos por la API (opcional; cae al fallback local). */
  presets?: PresetFormatoVideo[];
  disabled?: boolean;
}

export function SelectorFormato({ aspecto, onCambio, presets, disabled }: SelectorFormatoProps) {
  const buscar = (a: AspectoVideo): PresetFormatoVideo =>
    presets?.find((p) => p.aspecto === a) ?? presetParaAspecto(a);

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Formato de video">
        {ASPECTOS_VIDEO.map((a) => {
          const Icono = ICONO[a];
          const activo = a === aspecto;
          return (
            <button
              key={a}
              type="button"
              role="radio"
              aria-checked={activo}
              disabled={disabled}
              onClick={() => onCambio(a)}
              className={`relative flex flex-col items-center gap-1 rounded-lg border p-3 text-center transition-colors disabled:opacity-50 ${
                activo
                  ? "border-primary bg-primary/5 text-foreground"
                  : "border-border text-muted-foreground hover:bg-accent/50"
              }`}
            >
              {activo && <Check className="absolute right-1.5 top-1.5 h-3.5 w-3.5 text-primary" />}
              <Icono className="h-6 w-6" aria-hidden />
              <span className="text-sm font-semibold">{a}</span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        {ETIQUETA_ASPECTO[aspecto]} · {buscar(aspecto).w}×{buscar(aspecto).h}px ·{" "}
        {buscar(aspecto).fps} fps
      </p>
      <p className="text-[11px] text-muted-foreground/70">
        Zona segura: deja texto y logos dentro de los márgenes punteados del preview (el chrome
        de cada red tapa los bordes superior e inferior).
      </p>
    </div>
  );
}

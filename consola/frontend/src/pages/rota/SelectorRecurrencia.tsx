import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  DIAS_SEMANA,
  ETIQUETA_PRESET,
  type PresetRecurrencia,
  diasDePreset,
  finDeMesISO,
} from "@/lib/recurrencia";

/** Lo que el selector emite cuando hay recurrencia (null = evento suelto). */
export interface ValorRecurrencia {
  /** Días de la semana 0=lunes … 6=domingo. */
  dias_semana: number[];
  /** Fin de la recurrencia (ISO, inclusive). */
  repetir_hasta: string;
}

const PRESETS: PresetRecurrencia[] = [
  "no",
  "laborables",
  "fin_de_semana",
  "diario",
  "semanal",
  "personalizado",
];

/**
 * Control «Repetir» del formulario de evento. Ofrece patrones predefinidos (laborables, fin de
 * semana, diario, semanal) y un modo «personalizado» con chips de día de la semana, más un «hasta».
 * Es auto-contenido: gestiona su propio estado y avisa por `onChange` con `{dias_semana, repetir_hasta}`
 * (o `null` si no se repite). El padre solo guarda lo emitido para enviarlo al crear.
 */
export function SelectorRecurrencia({
  fechaBase,
  onChange,
  disabled = false,
}: {
  /** Fecha del evento (ISO): ancla «semanal» y el default de «hasta» (fin de su mes). */
  fechaBase: string;
  onChange: (valor: ValorRecurrencia | null) => void;
  disabled?: boolean;
}) {
  const [preset, setPreset] = React.useState<PresetRecurrencia>("no");
  const [diasCustom, setDiasCustom] = React.useState<number[]>([]);
  const [hasta, setHasta] = React.useState("");

  const dias = preset === "personalizado" ? diasCustom : diasDePreset(preset, fechaBase);

  // Emite el valor actual cada vez que cambian preset/días/hasta/fechaBase. Es idempotente para
  // el padre (solo guarda lo último), y ninguno de esos estados lo fija `onChange`: sin bucle.
  React.useEffect(() => {
    if (preset === "no") {
      onChange(null);
      return;
    }
    onChange({ dias_semana: dias, repetir_hasta: hasta });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset, diasCustom, hasta, fechaBase]);

  function alElegirPreset(nuevo: PresetRecurrencia) {
    setPreset(nuevo);
    // Al activar la recurrencia por primera vez, sugiere fin de mes como «hasta».
    if (nuevo !== "no" && !hasta) setHasta(finDeMesISO(fechaBase));
  }

  function alternarDia(valor: number) {
    setDiasCustom((prev) =>
      prev.includes(valor) ? prev.filter((d) => d !== valor) : [...prev, valor].sort((a, b) => a - b),
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="evento-repetir">Repetir</Label>
        <Select value={preset} onValueChange={(v) => alElegirPreset(v as PresetRecurrencia)} disabled={disabled}>
          <SelectTrigger id="evento-repetir">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRESETS.map((p) => (
              <SelectItem key={p} value={p}>
                {ETIQUETA_PRESET[p]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {preset === "personalizado" && (
        <div className="space-y-1.5">
          <Label>Días</Label>
          <div className="flex flex-wrap gap-1.5">
            {DIAS_SEMANA.map((d) => {
              const activo = diasCustom.includes(d.valor);
              return (
                <Tooltip key={d.valor} label={d.nombre}>
                  <button
                    type="button"
                    aria-pressed={activo}
                    aria-label={d.nombre}
                    disabled={disabled}
                    onClick={() => alternarDia(d.valor)}
                    className={cn(
                      "h-9 w-9 rounded-md border text-sm font-medium transition-colors",
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
                      activo
                        ? "border-foreground bg-foreground text-background"
                        : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    {d.corto}
                  </button>
                </Tooltip>
              );
            })}
          </div>
        </div>
      )}

      {preset !== "no" && (
        <div className="space-y-1.5">
          <Label htmlFor="evento-repetir-hasta">Repetir hasta</Label>
          <Input
            id="evento-repetir-hasta"
            type="date"
            value={hasta}
            min={fechaBase || undefined}
            disabled={disabled}
            onChange={(e) => setHasta(e.target.value)}
          />
          {preset === "personalizado" && diasCustom.length === 0 && (
            <p className="text-sm text-muted-foreground">Elige al menos un día de la semana.</p>
          )}
        </div>
      )}
    </div>
  );
}

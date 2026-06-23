/**
 * Editor de la LISTA de horas de publicación de una línea (en hora CDMX). En reposo muestra solo
 * las horas elegidas como chips con × y un botón «+ hora»; al pulsarlo despliega dos selectores
 * HH : MM (Radix, no el reloj nativo) para añadir, y se pliega de nuevo con «Listo». El valor es
 * la misma cadena CSV que consume `GestionPlan` (`parsearHoras` + franjas): no cambia el contrato.
 *
 * El añadir trabaja en pasos de 5 minutos; las horas ya guardadas con minutos sueltos se siguen
 * mostrando como chips y se conservan al guardar (solo el alta nueva usa la rejilla de 5 min).
 */
import { Check, Plus, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Lee el CSV de horas a "HH:MM" únicas y ordenadas (CDMX); descarta trozos vacíos o inválidos. */
function leerHoras(texto: string): string[] {
  const horas = new Set<string>();
  for (const trozo of (texto || "").split(",")) {
    const t = trozo.trim();
    if (!t) continue;
    const norm = t.length === 4 ? `0${t}` : t; // "8:45" -> "08:45"
    if (RE_HORA.test(norm)) horas.add(norm);
  }
  return [...horas].sort();
}

const HORAS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0"));
const MINUTOS = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, "0"));

export function SelectorHoras({
  value,
  onChange,
  ariaLabel,
}: {
  value: string;
  onChange: (csv: string) => void;
  ariaLabel: string;
}) {
  const horas = React.useMemo(() => leerHoras(value), [value]);
  const [hh, setHh] = React.useState("08");
  const [mm, setMm] = React.useState("45");
  const [abierto, setAbierto] = React.useState(false);

  const anadirHora = () => {
    const nueva = `${hh}:${mm}`;
    if (horas.includes(nueva)) return;
    onChange([...horas, nueva].sort().join(", "));
  };
  const quitarHora = (hora: string) => onChange(horas.filter((h) => h !== hora).join(", "));

  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={ariaLabel}>
      {horas.map((hora) => (
        <span
          key={hora}
          className="inline-flex items-center gap-1 rounded-md border border-input bg-muted/40 py-0.5 pl-2 pr-1 font-mono text-xs tabular-nums"
        >
          {hora}
          <button
            type="button"
            onClick={() => quitarHora(hora)}
            aria-label={`Quitar ${hora}`}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      {abierto ? (
        <div className="flex items-center gap-1">
          <Select value={hh} onValueChange={setHh}>
            <SelectTrigger
              className="h-7 w-14 px-2 font-mono text-xs tabular-nums"
              aria-label="Hora"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {HORAS.map((h) => (
                <SelectItem key={h} value={h} className="font-mono text-xs tabular-nums">
                  {h}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground">:</span>
          <Select value={mm} onValueChange={setMm}>
            <SelectTrigger
              className="h-7 w-14 px-2 font-mono text-xs tabular-nums"
              aria-label="Minuto"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MINUTOS.map((m) => (
                <SelectItem key={m} value={m} className="font-mono text-xs tabular-nums">
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={anadirHora}
            aria-label="Añadir hora"
            className="h-7 w-7"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => setAbierto(false)}
            aria-label="Listo"
            className="h-7 w-7 text-muted-foreground"
          >
            <Check className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAbierto(true)}
          aria-label="Añadir hora"
          className="inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Plus className="h-3.5 w-3.5" /> hora
        </button>
      )}
    </div>
  );
}

/**
 * Menú "⋮" de COLUMNAS de una tabla, en la cabecera de la propia tabla.
 *
 * Sustituye al antiguo panel macro "Configurar vista": el operador edita las columnas
 * DONDE están (mostrar/ocultar + reordenar con flechas), viéndolas, en vez de cotejar de
 * memoria una lista de checkboxes. Escribe en `vistaConfig.columnas[tablaId]` (orden +
 * ocultas), que persiste en localStorage y serializan las vistas guardadas. Dropdown propio
 * (sin dependencia nueva): cierra al clicar fuera, con Escape o al perder el foco.
 */
import { ChevronDown, ChevronUp, Columns3 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

import { TABLAS_CONFIG } from "./columnasMeta";
import { type ConfigColumnas, useVistaConfig } from "./vistaConfig";

/** Orden COMPLETO de columnas (incluidas las ocultas): `orden` válido + base al final. */
function ordenCompleto(todas: string[], cfg: ConfigColumnas): string[] {
  return [
    ...cfg.orden.filter((id) => todas.includes(id)),
    ...todas.filter((id) => !cfg.orden.includes(id)),
  ];
}

export function MenuColumnas({ tablaId }: { tablaId: string }) {
  const meta = TABLAS_CONFIG.find((t) => t.id === tablaId);
  const cfgGuardada = useVistaConfig((s) => s.columnas[tablaId]);
  const setColumnas = useVistaConfig((s) => s.setColumnas);

  const [abierto, setAbierto] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!abierto) return;
    const alClicFuera = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    };
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alClicFuera);
    document.addEventListener("keydown", alEscape);
    return () => {
      document.removeEventListener("mousedown", alClicFuera);
      document.removeEventListener("keydown", alEscape);
    };
  }, [abierto]);

  if (!meta) return null;

  const base = meta.columnas.map((c) => c.id);
  const cfg = cfgGuardada ?? { orden: base, ocultas: [] };
  const orden = ordenCompleto(base, cfg);
  const etiquetaDe = (id: string) => meta.columnas.find((c) => c.id === id)?.etiqueta ?? id;

  const toggle = (id: string, visible: boolean) => {
    const ocultas = visible ? cfg.ocultas.filter((x) => x !== id) : [...cfg.ocultas, id];
    setColumnas(tablaId, { orden, ocultas });
  };

  const mover = (idx: number, delta: number) => {
    const destino = idx + delta;
    if (destino < 0 || destino >= orden.length) return;
    const nuevo = [...orden];
    [nuevo[idx], nuevo[destino]] = [nuevo[destino], nuevo[idx]];
    setColumnas(tablaId, { orden: nuevo, ocultas: cfg.ocultas });
  };

  return (
    <div ref={ref} className="relative">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-7 w-7 text-muted-foreground hover:text-foreground"
        aria-label="Columnas"
        title="Columnas"
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <Columns3 className="h-4 w-4" />
      </Button>
      {abierto && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-64 rounded-md border border-border bg-popover p-2 text-popover-foreground shadow-md"
        >
          <p className="px-1 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Columnas
          </p>
          <ul className="space-y-0.5">
            {orden.map((id, idx) => {
              const visible = !cfg.ocultas.includes(id);
              const checkId = `colmenu-${tablaId}-${id}`;
              return (
                <li key={id} className="flex items-center gap-2 rounded-sm px-1 py-1 hover:bg-accent">
                  <Checkbox
                    id={checkId}
                    checked={visible}
                    onCheckedChange={(v) => toggle(id, Boolean(v))}
                    aria-label={etiquetaDe(id)}
                  />
                  <Label htmlFor={checkId} className="flex-1 cursor-pointer text-sm font-normal">
                    {etiquetaDe(id)}
                  </Label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => mover(idx, -1)}
                    disabled={idx === 0}
                    aria-label={`Subir ${etiquetaDe(id)}`}
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => mover(idx, 1)}
                    disabled={idx === orden.length - 1}
                    aria-label={`Bajar ${etiquetaDe(id)}`}
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

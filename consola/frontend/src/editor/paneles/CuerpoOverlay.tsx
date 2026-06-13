// Inspector · capa OVERLAY (degradado de fondo): color, altura fraccional y opacidad.

import { ColorControl } from "../ColorControl";

import type { Capa, CapaOverlay } from "../documento";

import { Campo, Num } from "./Campos";
import type { PropsCuerpoCapa } from "./tipos";

export function CuerpoOverlay({ capa, set }: PropsCuerpoCapa<CapaOverlay>) {
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3">
      {/* Borde al que se pega la banda: abajo (def) o arriba. Espejo exacto en editor y export. */}
      <Campo etiqueta="Lado">
        <select
          value={capa.lado === "arriba" ? "arriba" : "abajo"}
          onChange={(e) => set({ lado: e.target.value === "arriba" ? "arriba" : "abajo" } as Partial<Capa>)}
          className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
        >
          <option value="abajo">Abajo</option>
          <option value="arriba">Arriba</option>
        </select>
      </Campo>
      <Campo etiqueta="Color">
        <ColorControl valor={capa.color} onChange={(c) => set({ color: c } as Partial<Capa>)} />
      </Campo>
      {/* Clamps en cliente (mismo patrón que las paradas de degradado en Campos.tsx): un
          alto_frac > 1 pinta la banda por ENCIMA de su caja (también en el export) y un alpha
          fuera de 0-255 lo rechaza el servidor con 400 al guardar. */}
      <Campo etiqueta="Altura (frac)">
        <Num valor={capa.alto_frac} paso={0.05} onChange={(v) => set({ alto_frac: Math.min(1, Math.max(0.01, v)) } as Partial<Capa>)} />
      </Campo>
      <Campo etiqueta="Opacidad (0-255)">
        <Num valor={capa.alpha} onChange={(v) => set({ alpha: Math.min(255, Math.max(0, Math.round(v))) } as Partial<Capa>)} />
      </Campo>
    </div>
  );
}

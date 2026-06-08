// Inspector · capa OVERLAY (degradado de fondo): color, altura fraccional y opacidad.

import { ColorControl } from "../ColorControl";

import type { Capa, CapaOverlay } from "../documento";

import { Campo, Num } from "./Campos";
import type { PropsCuerpoCapa } from "./tipos";

export function CuerpoOverlay({ capa, set }: PropsCuerpoCapa<CapaOverlay>) {
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3">
      <Campo etiqueta="Color">
        <ColorControl valor={capa.color} onChange={(c) => set({ color: c } as Partial<Capa>)} />
      </Campo>
      <Campo etiqueta="Altura (frac)">
        <Num valor={capa.alto_frac} paso={0.05} onChange={(v) => set({ alto_frac: v } as Partial<Capa>)} />
      </Campo>
      <Campo etiqueta="Opacidad (0-255)">
        <Num valor={capa.alpha} onChange={(v) => set({ alpha: v } as Partial<Capa>)} />
      </Campo>
    </div>
  );
}

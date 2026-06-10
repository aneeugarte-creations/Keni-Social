// Inspector · capa LOGO: imagen (media_id) o wordmark (texto + tipografía y colores).

import { FlipHorizontal2, FlipVertical2 } from "lucide-react";

import { ColorControl } from "../ColorControl";

import type { Capa, CapaLogo } from "../documento";

import { Campo, Num } from "./Campos";
import type { PropsCuerpoCapa } from "./tipos";

export function CuerpoLogo({ capa, set, familias }: PropsCuerpoCapa<CapaLogo>) {
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3">
      <Campo etiqueta="Tipo">
        <select
          value={capa.tipo_logo}
          onChange={(e) => set({ tipo_logo: e.target.value as CapaLogo["tipo_logo"] } as Partial<Capa>)}
          className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
        >
          <option value="imagen">Imagen</option>
          <option value="wordmark">Wordmark</option>
        </select>
      </Campo>
      {/* VOLTEO (flip): espejo horizontal/vertical alrededor del centro de la caja. */}
      <Campo etiqueta="Voltear">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Voltear horizontal"
            aria-pressed={!!capa.flip_h}
            onClick={() => set({ flip_h: !capa.flip_h } as Partial<Capa>)}
            className={`rounded border border-input p-1 hover:bg-accent ${capa.flip_h ? "bg-accent" : "bg-background"}`}
          >
            <FlipHorizontal2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Voltear vertical"
            aria-pressed={!!capa.flip_v}
            onClick={() => set({ flip_v: !capa.flip_v } as Partial<Capa>)}
            className={`rounded border border-input p-1 hover:bg-accent ${capa.flip_v ? "bg-accent" : "bg-background"}`}
          >
            <FlipVertical2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </Campo>
      {capa.tipo_logo === "imagen" && (
        <Campo etiqueta="Media ID">
          <input
            type="text"
            value={capa.media_id}
            placeholder="id de media"
            onChange={(e) => set({ media_id: e.target.value.trim() } as Partial<Capa>)}
            className="w-40 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs"
          />
        </Campo>
      )}
      {capa.tipo_logo === "wordmark" && (
        <>
          <textarea
            value={capa.wordmark.texto}
            onChange={(e) => set({ wordmark: { ...capa.wordmark, texto: e.target.value } } as Partial<Capa>)}
            placeholder="Texto del wordmark…"
            className="min-h-[44px] rounded border border-input bg-background p-1.5 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <Campo etiqueta="Color">
              <ColorControl valor={capa.wordmark.color} onChange={(c) => set({ wordmark: { ...capa.wordmark, color: c } } as Partial<Capa>)} />
            </Campo>
            <Campo etiqueta="Fondo">
              <ColorControl valor={capa.wordmark.fondo} onChange={(c) => set({ wordmark: { ...capa.wordmark, fondo: c } } as Partial<Capa>)} />
            </Campo>
          </div>
          <Campo etiqueta="Fuente">
            <select
              value={capa.wordmark.familia}
              onChange={(e) => set({ wordmark: { ...capa.wordmark, familia: e.target.value } } as Partial<Capa>)}
              className="max-w-[140px] rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              {familias.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
              {!familias.includes(capa.wordmark.familia) && (
                <option value={capa.wordmark.familia}>{capa.wordmark.familia}</option>
              )}
            </select>
          </Campo>
          <Campo etiqueta="Peso">
            <Num valor={capa.wordmark.peso} paso={100} onChange={(v) => set({ wordmark: { ...capa.wordmark, peso: v } } as Partial<Capa>)} />
          </Campo>
        </>
      )}
    </div>
  );
}

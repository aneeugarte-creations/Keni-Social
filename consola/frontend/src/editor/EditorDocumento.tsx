// Ensambla el editor: barra + lienzo (centro) + paneles. RESPONSIVE: en escritorio los paneles son
// columnas laterales; en móvil el lienzo ocupa todo y los paneles se abren como cajones desde una
// barra inferior. Recibe el store del documento (uno por pestaña del workspace).

import { Image as ImageIcon, Layers, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { Lienzo } from "./Lienzo";
import { PanelBiblioteca } from "./PanelBiblioteca";
import { PanelIA } from "./PanelIA";
import { BarraHerramientas, Inspector, PanelCapas } from "./Paneles";
import { ProveedorEditor } from "./contexto";
import type { StoreEditor } from "./store";
import { useFuentesMarca } from "./useFuentesMarca";

type PanelMovil = null | "biblioteca" | "ia" | "inspector" | "capas";

export function EditorDocumento({
  store,
  marca,
  formato,
  onExportar,
}: {
  store: StoreEditor;
  marca: string;
  formato: string;
  onExportar?: () => void;
}) {
  const fuentesExtra = useFuentesMarca(marca);
  const [panel, setPanel] = useState<PanelMovil>(null);

  const biblioteca = <PanelBiblioteca marca={marca} />;
  const ia = <PanelIA marca={marca} formato={formato} />;
  const inspector = <Inspector fuentesExtra={fuentesExtra} />;
  const capasPanel = <PanelCapas />;

  const tituloPanel: Record<NonNullable<PanelMovil>, string> = {
    biblioteca: "Biblioteca",
    ia: "IA",
    inspector: "Propiedades",
    capas: "Capas",
  };

  return (
    <ProveedorEditor store={store}>
      <div className="flex h-full min-h-0 flex-col">
        <BarraHerramientas onExportar={onExportar} />
        <div className="relative flex min-h-0 flex-1 overflow-hidden">
          {/* Columna izquierda (escritorio): biblioteca + IA. */}
          <div className="hidden w-56 shrink-0 flex-col border-r border-border md:flex">
            <div className="min-h-0 flex-1 overflow-auto">{biblioteca}</div>
            <div className="max-h-[55%] shrink-0 overflow-auto border-t border-border">{ia}</div>
          </div>

          {/* Lienzo (siempre). */}
          <div className="flex min-w-0 flex-1 items-center justify-center overflow-hidden bg-muted/30 p-2 md:p-4">
            <Lienzo />
          </div>

          {/* Columna derecha (escritorio): inspector + capas. */}
          <div className="hidden w-72 shrink-0 flex-col border-l border-border md:flex">
            <div className="max-h-[55%] overflow-auto">{inspector}</div>
            <div className="min-h-0 flex-1 overflow-auto border-t border-border">{capasPanel}</div>
          </div>

          {/* Cajón móvil (overlay). */}
          {panel && (
            <div className="absolute inset-0 z-30 flex bg-black/30 md:hidden" onClick={() => setPanel(null)}>
              <div
                className="ml-auto flex h-full w-[86%] max-w-sm flex-col border-l border-border bg-background shadow-xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between border-b border-border px-3 py-2">
                  <span className="text-sm font-semibold">{tituloPanel[panel]}</span>
                  <button onClick={() => setPanel(null)} className="text-muted-foreground hover:text-foreground">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-auto">
                  {panel === "biblioteca" && biblioteca}
                  {panel === "ia" && ia}
                  {panel === "inspector" && inspector}
                  {panel === "capas" && capasPanel}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Barra inferior (móvil): abre cada panel como cajón. */}
        <div className="grid shrink-0 grid-cols-4 border-t border-border bg-background md:hidden">
          {(
            [
              ["biblioteca", "Biblioteca", ImageIcon],
              ["ia", "IA", Sparkles],
              ["inspector", "Propiedades", SlidersHorizontal],
              ["capas", "Capas", Layers],
            ] as const
          ).map(([clave, etiqueta, Icono]) => (
            <button
              key={clave}
              onClick={() => setPanel(clave)}
              className="flex flex-col items-center gap-0.5 py-2 text-[10px] text-muted-foreground active:bg-accent"
            >
              <Icono className="h-5 w-5" />
              {etiqueta}
            </button>
          ))}
        </div>
      </div>
    </ProveedorEditor>
  );
}

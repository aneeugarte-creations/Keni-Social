// Ensambla el editor de un documento: barra + lienzo (centro) + inspector y capas (derecha).
// Recibe el store del documento (uno por pestaña en el workspace multi-marca).

import { Lienzo } from "./Lienzo";
import { PanelBiblioteca } from "./PanelBiblioteca";
import { BarraHerramientas, Inspector, PanelCapas } from "./Paneles";
import { ProveedorEditor } from "./contexto";
import type { StoreEditor } from "./store";

export function EditorDocumento({
  store,
  marca,
  onExportar,
}: {
  store: StoreEditor;
  marca: string;
  onExportar?: () => void;
}) {
  return (
    <ProveedorEditor store={store}>
      <div className="flex h-full min-h-0 flex-col">
        <BarraHerramientas onExportar={onExportar} />
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div className="w-56 shrink-0 border-r border-border">
            <PanelBiblioteca marca={marca} />
          </div>
          <div className="flex flex-1 items-center justify-center overflow-auto bg-muted/30 p-4">
            <Lienzo maxAncho={620} maxAlto={760} />
          </div>
          <div className="flex w-72 shrink-0 flex-col border-l border-border">
            <div className="max-h-[55%] overflow-auto">
              <Inspector />
            </div>
            <div className="min-h-0 flex-1 overflow-auto border-t border-border">
              <PanelCapas />
            </div>
          </div>
        </div>
      </div>
    </ProveedorEditor>
  );
}

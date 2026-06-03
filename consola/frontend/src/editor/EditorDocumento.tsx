// Ensambla el editor de un documento: barra + lienzo (centro) + biblioteca/IA (izquierda) +
// inspector y capas (derecha). Recibe el store del documento (uno por pestaña del workspace).

import { Lienzo } from "./Lienzo";
import { PanelBiblioteca } from "./PanelBiblioteca";
import { PanelIA } from "./PanelIA";
import { BarraHerramientas, Inspector, PanelCapas } from "./Paneles";
import { ProveedorEditor } from "./contexto";
import type { StoreEditor } from "./store";
import { useFuentesMarca } from "./useFuentesMarca";

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
  // Tipografías propias de la marca: cargadas como FontFace (lienzo) + disponibles en el inspector.
  const fuentesExtra = useFuentesMarca(marca);
  return (
    <ProveedorEditor store={store}>
      <div className="flex h-full min-h-0 flex-col">
        <BarraHerramientas onExportar={onExportar} />
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div className="flex w-56 shrink-0 flex-col border-r border-border">
            <div className="min-h-0 flex-1 overflow-auto">
              <PanelBiblioteca marca={marca} />
            </div>
            <div className="max-h-[55%] shrink-0 overflow-auto border-t border-border">
              <PanelIA marca={marca} formato={formato} />
            </div>
          </div>
          <div className="flex flex-1 items-center justify-center overflow-auto bg-muted/30 p-4">
            <Lienzo maxAncho={620} maxAlto={760} />
          </div>
          <div className="flex w-72 shrink-0 flex-col border-l border-border">
            <div className="max-h-[55%] overflow-auto">
              <Inspector fuentesExtra={fuentesExtra} />
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

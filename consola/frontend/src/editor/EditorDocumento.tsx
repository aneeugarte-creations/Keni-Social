// Shell del editor (patrón Canva/Polotno, mobile-first):
//
//   [rail] [flyout?] [ barra contextual + acciones ]   [inspector?]
//                    [          LIENZO            ]
//
// - RAIL de herramientas: tira vertical de iconos (izquierda en escritorio, barra inferior en
//   móvil). Cada icono abre/cierra un FLYOUT con su panel (Elementos, Biblioteca, IA, Capas).
// - BARRA CONTEXTUAL: controles rápidos de la capa seleccionada; a su derecha, deshacer/rehacer y
//   exportar (siempre visibles).
// - INSPECTOR: panel de ajustes profundos, se abre desde «Ajustes» (columna derecha en escritorio,
//   hoja inferior en móvil).
// - Flyout e inspector son UN solo elemento responsive: columna acoplada en `md+`, hoja inferior
//   en móvil (clases `max-md:`), con backdrop solo en móvil.

import {
  DollarSign,
  LayoutTemplate,
  Layers,
  Image as ImageIcon,
  Redo2,
  Shapes,
  Sparkles,
  Undo2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

import { BarraContextual } from "./BarraContextual";
import { Lienzo } from "./Lienzo";
import { PanelBiblioteca } from "./PanelBiblioteca";
import { PanelElementos } from "./PanelElementos";
import { PanelIA } from "./PanelIA";
import { Inspector, PanelCapas } from "./Paneles";
import { ProveedorEditor } from "./contexto";
import type { StoreEditor } from "./store";
import { useFuentesMarca } from "./useFuentesMarca";

type Herramienta = "elementos" | "biblioteca" | "ia" | "capas";

const HERRAMIENTAS: { clave: Herramienta; etiqueta: string; Icono: typeof Shapes; costo?: boolean }[] = [
  { clave: "elementos", etiqueta: "Elementos", Icono: Shapes },
  { clave: "biblioteca", etiqueta: "Biblioteca", Icono: ImageIcon },
  { clave: "ia", etiqueta: "IA", Icono: Sparkles, costo: true },
  { clave: "capas", etiqueta: "Capas", Icono: Layers },
];

export function EditorDocumento({
  store,
  marca,
  formato,
  onExportar,
  onPlantillas,
}: {
  store: StoreEditor;
  marca: string;
  formato: string;
  onExportar?: () => void;
  onPlantillas?: () => void;
}) {
  const fuentesExtra = useFuentesMarca(marca);
  const [tool, setTool] = useState<Herramienta | null>("elementos");
  const [ajustes, setAjustes] = useState(false);
  // Capa de imagen a REENCUADRAR (B5) y a REEMPLAZAR (clic en activo de la biblioteca).
  const [reencuadreId, setReencuadreId] = useState<string | null>(null);
  const [reemplazarId, setReemplazarId] = useState<string | null>(null);

  const puedeDeshacer = store.getState().pasado.length > 0; // se refresca abajo con suscripción
  const [, force] = useState(0);
  useEffect(() => store.subscribe(() => force((n) => n + 1)), [store]);

  const seleccion = store.getState().seleccion;

  const abrirTool = (t: Herramienta) => setTool((prev) => (prev === t ? null : t));

  const abrirReencuadre = () => {
    const sel = store.getState().seleccion;
    if (sel) {
      setReencuadreId(sel);
      setAjustes(false);
      setTool(null);
    }
  };
  const abrirReemplazo = () => {
    const sel = store.getState().seleccion;
    if (sel) {
      setReemplazarId(sel);
      setTool("biblioteca");
    }
  };

  const panel = (() => {
    switch (tool) {
      case "elementos": return <PanelElementos />;
      case "biblioteca": return <PanelBiblioteca marca={marca} reemplazarId={reemplazarId} onReemplazado={() => setReemplazarId(null)} />;
      case "ia": return <PanelIA marca={marca} formato={formato} />;
      case "capas": return <PanelCapas />;
      default: return null;
    }
  })();
  const tituloTool = HERRAMIENTAS.find((h) => h.clave === tool)?.etiqueta ?? "";

  return (
    <ProveedorEditor store={store}>
      <div className="flex h-full min-h-0 w-full">
        {/* RAIL (escritorio: vertical izquierda). */}
        <nav className="hidden w-16 shrink-0 flex-col items-center gap-1 border-r border-border bg-muted/30 py-2 md:flex">
          {onPlantillas && (
            <RailBtn etiqueta="Plantillas" Icono={LayoutTemplate} onClick={onPlantillas} />
          )}
          {HERRAMIENTAS.map((h) => (
            <RailBtn key={h.clave} etiqueta={h.etiqueta} Icono={h.Icono} costo={h.costo} activo={tool === h.clave} onClick={() => abrirTool(h.clave)} />
          ))}
        </nav>

        {/* FLYOUT del rail (columna en md+, hoja inferior en móvil). */}
        {tool && (
          <>
            <div className="fixed inset-0 z-20 bg-black/30 md:hidden" onClick={() => setTool(null)} />
            <aside className="z-30 flex flex-col overflow-hidden border-border bg-background max-md:fixed max-md:inset-x-0 max-md:bottom-16 max-md:top-auto max-md:h-[58vh] max-md:rounded-t-xl max-md:border-t max-md:shadow-2xl md:relative md:w-72 md:border-r">
              <div className="flex shrink-0 items-center justify-between border-b border-border px-3 py-2">
                <span className="text-sm font-semibold">{tituloTool}</span>
                <button onClick={() => setTool(null)} className="text-muted-foreground hover:text-foreground" title="Cerrar">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-auto">{panel}</div>
            </aside>
          </>
        )}

        {/* COLUMNA CENTRAL: barra contextual + acciones + lienzo. En móvil deja hueco inferior
            para que el rail fijo (h-16) no tape el lienzo. */}
        <div className="flex min-w-0 flex-1 flex-col max-md:pb-16">
          <div className="flex items-stretch border-b border-border">
            <div className="min-w-0 flex-1">
              <BarraContextual
                fuentesExtra={fuentesExtra}
                onAbrirAjustes={() => setAjustes(true)}
                onReencuadrar={abrirReencuadre}
                onReemplazar={abrirReemplazo}
              />
            </div>
            <div className="flex shrink-0 items-center gap-1 border-l border-border bg-background px-2">
              <button
                title="Deshacer (⌘Z)"
                disabled={!puedeDeshacer}
                onClick={() => store.getState().deshacer()}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-40"
              >
                <Undo2 className="h-4 w-4" />
              </button>
              <button
                title="Rehacer (⇧⌘Z)"
                disabled={store.getState().futuro.length === 0}
                onClick={() => store.getState().rehacer()}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-40"
              >
                <Redo2 className="h-4 w-4" />
              </button>
              {onExportar && (
                <Button size="sm" className="ml-1" onClick={onExportar}>
                  Exportar
                </Button>
              )}
            </div>
          </div>

          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-muted/30 p-2 md:p-4">
            <Lienzo reencuadreId={reencuadreId} onSalirReencuadre={() => setReencuadreId(null)} />
          </div>
        </div>

        {/* INSPECTOR (ajustes profundos): columna derecha en md+, hoja inferior en móvil. */}
        {ajustes && (
          <>
            <div className="fixed inset-0 z-20 bg-black/30 md:hidden" onClick={() => setAjustes(false)} />
            <aside className="z-30 flex flex-col overflow-hidden border-border bg-background max-md:fixed max-md:inset-x-0 max-md:bottom-16 max-md:top-auto max-md:h-[58vh] max-md:rounded-t-xl max-md:border-t max-md:shadow-2xl md:relative md:w-72 md:border-l">
              <div className="flex shrink-0 items-center justify-between border-b border-border px-3 py-2">
                <span className="text-sm font-semibold">{seleccion ? "Ajustes de la capa" : "Lienzo y fondo"}</span>
                <button onClick={() => setAjustes(false)} className="text-muted-foreground hover:text-foreground" title="Cerrar">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-auto">
                <Inspector fuentesExtra={fuentesExtra} />
              </div>
            </aside>
          </>
        )}

        {/* RAIL móvil (barra inferior fija). */}
        <nav className="fixed inset-x-0 bottom-0 z-30 grid h-16 grid-cols-5 border-t border-border bg-background md:hidden">
          {onPlantillas && <RailBtnMovil etiqueta="Plantillas" Icono={LayoutTemplate} onClick={onPlantillas} />}
          {HERRAMIENTAS.map((h) => (
            <RailBtnMovil key={h.clave} etiqueta={h.etiqueta} Icono={h.Icono} costo={h.costo} activo={tool === h.clave} onClick={() => abrirTool(h.clave)} />
          ))}
        </nav>
      </div>
    </ProveedorEditor>
  );
}

function RailBtn({ etiqueta, Icono, activo, costo, onClick }: { etiqueta: string; Icono: typeof Shapes; activo?: boolean; costo?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={costo ? `${etiqueta} · usa IA con coste` : etiqueta}
      className={`flex w-full flex-col items-center gap-0.5 rounded-md py-2 text-[10px] transition-colors ${
        activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      }`}
    >
      <span className="relative">
        <Icono className="h-5 w-5" />
        {costo && <DollarSign className="absolute -right-2 -top-1 h-3 w-3 rounded-full bg-background" />}
      </span>
      {etiqueta}
    </button>
  );
}

function RailBtnMovil({ etiqueta, Icono, activo, costo, onClick }: { etiqueta: string; Icono: typeof Shapes; activo?: boolean; costo?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center justify-center gap-0.5 text-[10px] ${activo ? "text-primary" : "text-muted-foreground"}`}
    >
      <span className="relative">
        <Icono className="h-5 w-5" />
        {costo && <DollarSign className="absolute -right-2 -top-1 h-3 w-3 rounded-full bg-background" />}
      </span>
      {etiqueta}
    </button>
  );
}

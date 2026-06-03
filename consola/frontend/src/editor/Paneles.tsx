// Paneles del editor: barra de herramientas, lista de capas (z-order) e inspector de propiedades.
// Todos operan sobre el store del documento via contexto.

import {
  ArrowDown,
  ArrowUp,
  Copy,
  Eye,
  EyeOff,
  Image as ImageIcon,
  Lock,
  Redo2,
  Square,
  Trash2,
  Type,
  Unlock,
  Undo2,
} from "lucide-react";

import { Button } from "@/components/ui/button";

import type { Capa, CapaMarco, CapaOverlay, CapaTexto } from "./documento";
import { CATALOGO_FUENTES, nuevaCapaImagen, nuevaCapaMarco, nuevaCapaTexto, zTope } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

const ETIQUETA_TIPO: Record<Capa["tipo"], string> = {
  imagen: "Imagen",
  texto: "Texto",
  logo: "Logo",
  marco: "Marco",
  overlay: "Degradado",
  grupo: "Grupo",
};

export function BarraHerramientas({ onExportar }: { onExportar?: () => void }) {
  const store = useStoreEditor();
  const seleccion = useEditor((s) => s.seleccion);
  const puedeDeshacer = useEditor((s) => s.pasado.length > 0);
  const puedeRehacer = useEditor((s) => s.futuro.length > 0);

  const agregar = (capa: Capa) => {
    const st = store.getState();
    const z = zTope(st.documento);
    st.agregar({ ...capa, z } as Capa);
    st.seleccionar(capa.id);
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-border p-2">
      <Button variant="outline" size="sm" onClick={() => agregar(nuevaCapaTexto())}>
        <Type className="mr-1 h-4 w-4" /> Texto
      </Button>
      <Button variant="outline" size="sm" onClick={() => agregar(nuevaCapaMarco())}>
        <Square className="mr-1 h-4 w-4" /> Marco
      </Button>
      <Button variant="outline" size="sm" onClick={() => agregar(nuevaCapaImagen(""))}>
        <ImageIcon className="mr-1 h-4 w-4" /> Imagen
      </Button>
      <div className="mx-1 h-5 w-px bg-border" />
      <Button variant="ghost" size="sm" disabled={!puedeDeshacer} onClick={() => store.getState().deshacer()}>
        <Undo2 className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="sm" disabled={!puedeRehacer} onClick={() => store.getState().rehacer()}>
        <Redo2 className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="sm" disabled={!seleccion} onClick={() => seleccion && store.getState().duplicar(seleccion)}>
        <Copy className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="sm" disabled={!seleccion} onClick={() => seleccion && store.getState().quitar(seleccion)}>
        <Trash2 className="h-4 w-4" />
      </Button>
      <div className="ml-auto" />
      {onExportar && (
        <Button size="sm" onClick={onExportar}>
          Exportar PNG
        </Button>
      )}
    </div>
  );
}

export function PanelCapas() {
  const store = useStoreEditor();
  const capas = useEditor((s) => s.documento.capas);
  const seleccion = useEditor((s) => s.seleccion);
  // Más alta (z mayor) arriba en la lista.
  const ordenadas = [...capas].sort((a, b) => b.z - a.z);

  return (
    <div className="flex flex-col">
      <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Capas
      </div>
      <div className="flex-1 overflow-auto">
        {ordenadas.length === 0 && (
          <p className="p-3 text-sm text-muted-foreground">Sin capas. Añade texto, marco o imagen.</p>
        )}
        {ordenadas.map((capa) => (
          <div
            key={capa.id}
            onClick={() => store.getState().seleccionar(capa.id)}
            className={`flex items-center gap-1 border-b border-border/50 px-2 py-1.5 text-sm ${
              capa.id === seleccion ? "bg-accent" : "hover:bg-accent/50"
            }`}
          >
            <button
              className="text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                store.getState().actualizar(capa.id, { visible: !capa.visible } as Partial<Capa>);
              }}
              title={capa.visible ? "Ocultar" : "Mostrar"}
            >
              {capa.visible ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            </button>
            <button
              className="text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                store.getState().actualizar(capa.id, { bloqueada: !capa.bloqueada } as Partial<Capa>);
              }}
              title={capa.bloqueada ? "Desbloquear" : "Bloquear"}
            >
              {capa.bloqueada ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
            </button>
            <span className="flex-1 truncate">
              {ETIQUETA_TIPO[capa.tipo]}
              {capa.tipo === "texto" && (capa as CapaTexto).texto ? ` · ${(capa as CapaTexto).texto.slice(0, 18)}` : ""}
            </span>
            <button
              className="text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                store.getState().reordenar(capa.id, 1);
              }}
              title="Subir"
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </button>
            <button
              className="text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                store.getState().reordenar(capa.id, -1);
              }}
              title="Bajar"
            >
              <ArrowDown className="h-3.5 w-3.5" />
            </button>
            <button
              className="text-muted-foreground hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                store.getState().quitar(capa.id);
              }}
              title="Borrar capa"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{etiqueta}</span>
      {children}
    </label>
  );
}

function Num({
  valor,
  onChange,
  paso = 1,
}: {
  valor: number;
  onChange: (v: number) => void;
  paso?: number;
}) {
  return (
    <input
      type="number"
      step={paso}
      value={Math.round(valor * 100) / 100}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-20 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs"
    />
  );
}

export function Inspector({ fuentesExtra = [] }: { fuentesExtra?: string[] }) {
  const store = useStoreEditor();
  const capa = useEditor((s) => s.documento.capas.find((c) => c.id === s.seleccion) ?? null);
  // Familias disponibles: catálogo embebido + tipografías propias de la marca (sin duplicar).
  const familias = [...CATALOGO_FUENTES, ...fuentesExtra.filter((f) => !CATALOGO_FUENTES.includes(f as never))];

  if (!capa) {
    return (
      <div className="p-3 text-sm text-muted-foreground">
        Selecciona una capa para editar sus propiedades.
      </div>
    );
  }

  const set = (cambios: Partial<Capa>) => store.getState().actualizar(capa.id, cambios);

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {ETIQUETA_TIPO[capa.tipo]}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="X"><Num valor={capa.x} onChange={(v) => set({ x: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Y"><Num valor={capa.y} onChange={(v) => set({ y: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Ancho"><Num valor={capa.w} onChange={(v) => set({ w: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Alto"><Num valor={capa.h} onChange={(v) => set({ h: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Rotación"><Num valor={capa.rotacion} onChange={(v) => set({ rotacion: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Opacidad">
          <Num valor={capa.opacidad} paso={0.1} onChange={(v) => set({ opacidad: Math.min(1, Math.max(0, v)) } as Partial<Capa>)} />
        </Campo>
      </div>

      {capa.tipo === "texto" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <textarea
            value={(capa as CapaTexto).texto}
            onChange={(e) => set({ texto: e.target.value } as Partial<Capa>)}
            placeholder="Texto…"
            className="min-h-[60px] rounded border border-input bg-background p-1.5 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <Campo etiqueta="Tamaño"><Num valor={(capa as CapaTexto).tamano} onChange={(v) => set({ tamano: v } as Partial<Capa>)} /></Campo>
            <Campo etiqueta="Peso"><Num valor={(capa as CapaTexto).peso} paso={100} onChange={(v) => set({ peso: v } as Partial<Capa>)} /></Campo>
            <Campo etiqueta="Color">
              <input type="color" value={(capa as CapaTexto).color} onChange={(e) => set({ color: e.target.value } as Partial<Capa>)} className="h-6 w-10" />
            </Campo>
            <Campo etiqueta="Mayúsculas">
              <input type="checkbox" checked={(capa as CapaTexto).mayusculas} onChange={(e) => set({ mayusculas: e.target.checked } as Partial<Capa>)} />
            </Campo>
          </div>
          <Campo etiqueta="Fuente">
            <select
              value={(capa as CapaTexto).familia}
              onChange={(e) => set({ familia: e.target.value } as Partial<Capa>)}
              className="max-w-[140px] rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              {familias.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
              {/* Si la capa usa una familia que ya no está en la lista, la mostramos igual. */}
              {!familias.includes((capa as CapaTexto).familia) && (
                <option value={(capa as CapaTexto).familia}>{(capa as CapaTexto).familia}</option>
              )}
            </select>
          </Campo>
          <Campo etiqueta="Alineación">
            <select
              value={(capa as CapaTexto).alineacion}
              onChange={(e) => set({ alineacion: e.target.value as CapaTexto["alineacion"] } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="izquierda">Izquierda</option>
              <option value="centro">Centro</option>
              <option value="derecha">Derecha</option>
              <option value="justificado">Justificado</option>
            </select>
          </Campo>
        </div>
      )}

      {capa.tipo === "marco" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <Campo etiqueta="Forma">
            <select
              value={(capa as CapaMarco).forma}
              onChange={(e) => set({ forma: e.target.value as CapaMarco["forma"] } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="rect">Rectángulo</option>
              <option value="elipse">Elipse</option>
              <option value="linea">Línea</option>
            </select>
          </Campo>
          <Campo etiqueta="Relleno">
            <input
              type="color"
              value={(capa as CapaMarco).relleno ?? "#000000"}
              onChange={(e) => set({ relleno: e.target.value } as Partial<Capa>)}
              className="h-6 w-10"
            />
          </Campo>
          <Campo etiqueta="Borde">
            <input
              type="color"
              value={(capa as CapaMarco).borde?.color ?? "#FFFFFF"}
              onChange={(e) =>
                set({ borde: { color: e.target.value, grosor: (capa as CapaMarco).borde?.grosor ?? 6 } } as Partial<Capa>)
              }
              className="h-6 w-10"
            />
          </Campo>
          <Campo etiqueta="Grosor">
            <Num
              valor={(capa as CapaMarco).borde?.grosor ?? 0}
              onChange={(v) => set({ borde: { color: (capa as CapaMarco).borde?.color ?? "#FFFFFF", grosor: v } } as Partial<Capa>)}
            />
          </Campo>
          <Campo etiqueta="Radio"><Num valor={(capa as CapaMarco).radio} onChange={(v) => set({ radio: v } as Partial<Capa>)} /></Campo>
        </div>
      )}

      {capa.tipo === "overlay" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <Campo etiqueta="Color">
            <input type="color" value={(capa as CapaOverlay).color} onChange={(e) => set({ color: e.target.value } as Partial<Capa>)} className="h-6 w-10" />
          </Campo>
          <Campo etiqueta="Altura (frac)">
            <Num valor={(capa as CapaOverlay).alto_frac} paso={0.05} onChange={(v) => set({ alto_frac: v } as Partial<Capa>)} />
          </Campo>
          <Campo etiqueta="Opacidad (0-255)">
            <Num valor={(capa as CapaOverlay).alpha} onChange={(v) => set({ alpha: v } as Partial<Capa>)} />
          </Campo>
        </div>
      )}
    </div>
  );
}

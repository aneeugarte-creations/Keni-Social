// Barra CONTEXTUAL superior (patrón Canva/Polotno): muestra los controles MÁS usados de la capa
// seleccionada, en una fila compacta que en móvil se desplaza en horizontal. Lo profundo (todos
// los ajustes) vive en el Inspector, que se abre desde el botón «Ajustes». Sin selección, ofrece
// el tamaño del lienzo y el fondo. Opera sobre el store del documento vía contexto.

import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Crop,
  Maximize2,
  Replace,
  Settings2,
  Sparkles,
} from "lucide-react";

import type { Capa, CapaImagen, CapaMarco, CapaTexto } from "./documento";
import { CATALOGO_FUENTES } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

const ALIN_ICONO = { izquierda: AlignLeft, centro: AlignCenter, derecha: AlignRight, justificado: AlignRight } as const;
const ALIN_CICLO = ["izquierda", "centro", "derecha", "justificado"] as const;

function Sep() {
  return <div className="mx-0.5 h-5 w-px shrink-0 bg-border" />;
}

// Botón con icono, compacto.
function BotonIcono({
  onClick,
  activo,
  titulo,
  children,
}: {
  onClick: () => void;
  activo?: boolean;
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={titulo}
      className={`flex h-8 shrink-0 items-center gap-1 rounded-md px-2 text-sm transition-colors ${
        activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

// Pequeño stepper numérico (−/valor/+) intuitivo para tamaños.
function Stepper({ valor, onChange, min = 1, max = 9999, paso = 1, ancho = "w-12" }: {
  valor: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  paso?: number;
  ancho?: string;
}) {
  const fija = (v: number) => onChange(Math.max(min, Math.min(max, v)));
  return (
    <div className="flex h-8 shrink-0 items-center overflow-hidden rounded-md border border-input">
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor - paso)} title="Menos">−</button>
      <input
        type="number"
        value={Math.round(valor)}
        onChange={(e) => fija(Number(e.target.value))}
        className={`${ancho} bg-background px-1 text-center text-sm outline-none`}
      />
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor + paso)} title="Más">+</button>
    </div>
  );
}

function Swatch({ color, onChange, titulo }: { color: string; onChange: (c: string) => void; titulo: string }) {
  return (
    <label title={titulo} className="relative flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-input">
      <span className="h-4 w-4 rounded-sm border border-border" style={{ background: color }} />
      <input type="color" value={color} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" />
    </label>
  );
}

export function BarraContextual({
  fuentesExtra = [],
  onAbrirAjustes,
  onAbrirIA,
  onReencuadrar,
  onReemplazar,
}: {
  fuentesExtra?: string[];
  onAbrirAjustes: () => void;
  onAbrirIA: () => void;
  onReencuadrar: () => void;
  onReemplazar: () => void;
}) {
  const store = useStoreEditor();
  const capa = useEditor((s) => s.documento.capas.find((c) => c.id === s.seleccion) ?? null);
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  const set = (cambios: Partial<Capa>) => capa && store.getState().actualizar(capa.id, cambios);
  const familias = [...CATALOGO_FUENTES, ...fuentesExtra.filter((f) => !CATALOGO_FUENTES.includes(f as never))];

  // Varias capas: la barra contextual se mantiene minimalista (las acciones de alineación viven en
  // la barra flotante sobre la selección).
  if (seleccionMulti.length > 1) {
    return (
      <div className="flex h-11 items-center gap-1 overflow-x-auto bg-background px-2">
        <span className="text-sm text-muted-foreground">{seleccionMulti.length} capas seleccionadas</span>
        <Sep />
        <BotonIcono titulo="Ajustes" onClick={onAbrirAjustes}><Settings2 className="h-4 w-4" /> Ajustes</BotonIcono>
      </div>
    );
  }

  if (!capa) {
    // Sin selección: pista + acceso a IA (la edición de lienzo/fondo está en Ajustes).
    return (
      <div className="flex h-11 items-center gap-1 overflow-x-auto bg-background px-2">
        <span className="truncate text-sm text-muted-foreground">Selecciona una capa, o añade elementos desde el panel.</span>
        <div className="ml-auto flex items-center gap-1">
          <BotonIcono titulo="Generar con IA" onClick={onAbrirIA}><Sparkles className="h-4 w-4" /> IA</BotonIcono>
          <BotonIcono titulo="Lienzo y fondo" onClick={onAbrirAjustes}><Maximize2 className="h-4 w-4" /> Lienzo</BotonIcono>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-11 items-center gap-1 overflow-x-auto bg-background px-2">
      {capa.tipo === "texto" && (
        <>
          <select
            value={(capa as CapaTexto).familia}
            onChange={(e) => set({ familia: e.target.value } as Partial<Capa>)}
            className="h-8 shrink-0 rounded-md border border-input bg-background px-2 text-sm"
            title="Fuente"
          >
            {familias.map((f) => <option key={f} value={f}>{f}</option>)}
            {!familias.includes((capa as CapaTexto).familia) && <option value={(capa as CapaTexto).familia}>{(capa as CapaTexto).familia}</option>}
          </select>
          <Stepper valor={(capa as CapaTexto).tamano} min={8} max={400} onChange={(v) => set({ tamano: v } as Partial<Capa>)} />
          <BotonIcono
            titulo="Negrita"
            activo={(capa as CapaTexto).peso >= 600}
            onClick={() => set({ peso: (capa as CapaTexto).peso >= 600 ? 400 : 700 } as Partial<Capa>)}
          >
            <Bold className="h-4 w-4" />
          </BotonIcono>
          <Swatch color={(capa as CapaTexto).color} onChange={(c) => set({ color: c } as Partial<Capa>)} titulo="Color del texto" />
          {(() => {
            const al = (capa as CapaTexto).alineacion;
            const Icono = ALIN_ICONO[al];
            return (
              <BotonIcono
                titulo={`Alineación: ${al}`}
                onClick={() => set({ alineacion: ALIN_CICLO[(ALIN_CICLO.indexOf(al) + 1) % ALIN_CICLO.length] } as Partial<Capa>)}
              >
                <Icono className="h-4 w-4" />
              </BotonIcono>
            );
          })()}
        </>
      )}

      {capa.tipo === "imagen" && (
        <>
          <BotonIcono
            titulo={`Ajuste: ${(capa as CapaImagen).ajuste === "cover" ? "cubrir" : "contener"} (clic para alternar)`}
            onClick={() => set({ ajuste: (capa as CapaImagen).ajuste === "cover" ? "contain" : "cover" } as Partial<Capa>)}
          >
            {(capa as CapaImagen).ajuste === "cover" ? "Cubrir" : "Contener"}
          </BotonIcono>
          <BotonIcono titulo="Reencuadrar (arrastra la foto dentro del marco)" onClick={onReencuadrar}><Crop className="h-4 w-4" /> Reencuadrar</BotonIcono>
          <BotonIcono titulo="Reemplazar imagen" onClick={onReemplazar}><Replace className="h-4 w-4" /> Reemplazar</BotonIcono>
        </>
      )}

      {capa.tipo === "marco" && (
        <>
          <select
            value={(capa as CapaMarco).forma}
            onChange={(e) => set({ forma: e.target.value as CapaMarco["forma"] } as Partial<Capa>)}
            className="h-8 shrink-0 rounded-md border border-input bg-background px-2 text-sm"
            title="Forma"
          >
            <option value="rect">Rectángulo</option>
            <option value="elipse">Elipse</option>
            <option value="linea">Línea</option>
          </select>
          {(capa as CapaMarco).forma !== "linea" && (
            <Swatch
              color={(capa as CapaMarco).relleno ?? "#000000"}
              onChange={(c) => set({ relleno: c } as Partial<Capa>)}
              titulo="Relleno"
            />
          )}
          <Swatch
            color={(capa as CapaMarco).borde?.color ?? "#FFFFFF"}
            onChange={(c) => set({ borde: { color: c, grosor: (capa as CapaMarco).borde?.grosor ?? 6 } } as Partial<Capa>)}
            titulo="Color del borde"
          />
        </>
      )}

      {capa.tipo === "logo" && <span className="px-1 text-sm text-muted-foreground">Logo</span>}

      <div className="ml-auto flex items-center gap-1">
        <Sep />
        <BotonIcono titulo="Todos los ajustes" onClick={onAbrirAjustes}><Settings2 className="h-4 w-4" /> Ajustes</BotonIcono>
      </div>
    </div>
  );
}

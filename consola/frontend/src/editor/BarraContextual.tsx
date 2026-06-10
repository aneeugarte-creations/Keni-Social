// Barra CONTEXTUAL superior (patrón Canva/Polotno): muestra los controles MÁS usados de la capa
// seleccionada, en una fila compacta que en móvil se desplaza en horizontal. Lo profundo (todos
// los ajustes) vive en el Inspector, que se abre desde el botón «Ajustes». Sin selección, ofrece
// el tamaño del lienzo y el fondo. Opera sobre el store del documento vía contexto.

import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  Crop,
  Maximize2,
  Replace,
  Settings2,
} from "lucide-react";

import { useState } from "react";

import type { Capa, CapaTexto } from "./documento";
import { CATALOGO_FUENTES } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

const ALIN_ICONO = { izquierda: AlignLeft, centro: AlignCenter, derecha: AlignRight, justificado: AlignJustify } as const;
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
  ariaLabel,
}: {
  onClick: () => void;
  activo?: boolean;
  titulo: string;
  children: React.ReactNode;
  ariaLabel?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={titulo}
      aria-label={ariaLabel}
      aria-pressed={activo}
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
  const [edicion, setEdicion] = useState<string>(String(Math.round(valor)));

  // Sincroniza el estado local cuando `valor` cambia desde fuera.
  const val = Math.round(valor);
  if (edicion !== String(val) && edicion === String(Math.round(Number(edicion) || 0))) {
    setEdicion(String(val));
  }

  const fija = (v: number) => onChange(Math.max(min, Math.min(max, v)));
  const commitear = () => {
    const v = Number(edicion);
    if (!isNaN(v)) fija(v);
    setEdicion(String(Math.round(valor)));
  };

  return (
    <div className="flex h-8 shrink-0 items-center overflow-hidden rounded-md border border-input">
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor - paso)} title="Menos">−</button>
      <input
        type="number"
        value={edicion}
        onChange={(e) => setEdicion(e.target.value)}
        onBlur={commitear}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitear();
          if (e.key === "Escape") setEdicion(String(Math.round(valor)));
        }}
        aria-label="Tamaño de letra"
        className={`${ancho} bg-background px-1 text-center text-sm outline-none`}
      />
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor + paso)} title="Más">+</button>
    </div>
  );
}

function Swatch({ color, onChange, titulo }: { color: string; onChange: (c: string) => void; titulo: string }) {
  // Extrae #rrggbb del color (puede ser #rrggbb o #rrggbbaa).
  const hexRgb = color.slice(0, 7);
  // Preserva el alfa si estaba presente (últimos 2 chars).
  const alfa = color.length === 9 ? color.slice(7, 9) : "";

  const handleColorChange = (nuevoHex: string) => {
    // Si había alfa, preservarlo; si no, solo RGB.
    onChange(alfa ? nuevoHex + alfa : nuevoHex);
  };

  return (
    <label title={titulo} className="relative flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-input">
      <span className="h-4 w-4 rounded-sm border border-border" style={{ background: color }} />
      <input type="color" value={hexRgb} onChange={(e) => handleColorChange(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" />
    </label>
  );
}

export function BarraContextual({
  fuentesExtra = [],
  onAbrirAjustes,
  onReencuadrar,
  onReemplazar,
}: {
  fuentesExtra?: string[];
  onAbrirAjustes: () => void;
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
    // Sin selección: pista + acceso al lienzo/fondo (IA vive en el rail; no se duplica).
    return (
      <div className="flex h-11 items-center gap-1 overflow-x-auto bg-background px-2">
        <span className="truncate text-sm text-muted-foreground">Selecciona una capa, o añade elementos desde el panel.</span>
        <div className="ml-auto flex items-center gap-1">
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
            ariaLabel="Negrita"
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
                ariaLabel={`Alineación: ${al} (clic para cambiar)`}
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
          <BotonIcono titulo="Reemplazar imagen" onClick={onReemplazar}><Replace className="h-4 w-4" /> Reemplazar</BotonIcono>
          <BotonIcono titulo="Reencuadrar (arrastra la foto dentro del marco)" onClick={onReencuadrar}><Crop className="h-4 w-4" /> Reencuadrar</BotonIcono>
        </>
      )}

      {/* Marco: Forma, Relleno y Borde viven en el Inspector; la barra solo expone «Ajustes» (abajo). */}

      {capa.tipo === "logo" && (
        <BotonIcono titulo="Reemplazar logo" onClick={onReemplazar}><Replace className="h-4 w-4" /> Reemplazar</BotonIcono>
      )}

      <div className="ml-auto flex items-center gap-1">
        <Sep />
        <BotonIcono titulo="Todos los ajustes" onClick={onAbrirAjustes}><Settings2 className="h-4 w-4" /> Ajustes</BotonIcono>
      </div>
    </div>
  );
}

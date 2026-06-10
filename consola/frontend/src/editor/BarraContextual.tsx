// Barra CONTEXTUAL de la capa seleccionada (patrón Canva): píldora FLOTANTE sobre el lienzo (la
// aloja la franja reservada del Lienzo, junto a alinear/orden/duplicar/borrar) con los controles
// MÁS usados. SOLO aparece con selección; sin capa seleccionada no pinta nada (los ajustes del
// lienzo/fondo viven en el Inspector, vía «Ajustes» del rail). Lo profundo (todos los ajustes)
// vive en el Inspector, que se abre desde el botón «Ajustes». Opera sobre el store vía contexto.

import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  ChevronsLeftRight,
  ChevronsUpDown,
  Crop,
  Italic,
  Replace,
  Settings2,
  Underline,
} from "lucide-react";

import { useState } from "react";

import { tieneCursiva } from "../lib/placa/dibujar.mjs";

import { familiaReal } from "./capas/tipografia";
import type { Capa, CapaTexto } from "./documento";
import { CATALOGO_FUENTES } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

const ALIN_ICONO = { izquierda: AlignLeft, centro: AlignCenter, derecha: AlignRight, justificado: AlignJustify } as const;
const ALIN_CICLO = ["izquierda", "centro", "derecha", "justificado"] as const;

// Presets de INTERLINEADO (line-height relativo, patrón Canva). El valor actual del documento se
// añade como opción extra si no coincide con ninguno (p. ej. el 1.14 por defecto de las plantillas).
const INTERLINEADOS = [1.0, 1.15, 1.3, 1.5, 2.0] as const;
// "1" -> "1.0", "1.15" -> "1.15" (siempre con al menos un decimal, legible como factor).
const fmtInterlineado = (n: number) => (Number.isInteger(n) ? n.toFixed(1) : String(n));

function Sep() {
  return <div className="mx-0.5 h-5 w-px shrink-0 bg-border" />;
}

// Botón con icono, compacto. `deshabilitado` lo apaga (patrón Canva: el tooltip explica por qué).
function BotonIcono({
  onClick,
  activo,
  titulo,
  children,
  ariaLabel,
  deshabilitado,
}: {
  onClick: () => void;
  activo?: boolean;
  titulo: string;
  children: React.ReactNode;
  ariaLabel?: string;
  deshabilitado?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={titulo}
      aria-label={ariaLabel}
      aria-pressed={activo}
      disabled={deshabilitado}
      className={`flex h-8 shrink-0 items-center gap-1 rounded-md px-2 text-sm transition-colors ${
        deshabilitado
          ? "cursor-not-allowed text-muted-foreground/40"
          : activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

// Pequeño stepper numérico (−/valor/+) intuitivo para tamaños y espaciados.
function Stepper({ valor, onChange, min = 1, max = 9999, paso = 1, ancho = "w-12", etiqueta = "Tamaño de letra", icono }: {
  valor: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  paso?: number;
  ancho?: string;
  // Etiqueta accesible y tooltip del control (qué magnitud edita este stepper).
  etiqueta?: string;
  // Icono opcional delante del «−» para distinguir steppers vecinos de un vistazo.
  icono?: React.ReactNode;
}) {
  const [edicion, setEdicion] = useState<string>(String(Math.round(valor)));

  // Sincroniza el estado local SOLO cuando `valor` cambia desde fuera (undo, −/+, otra capa…),
  // nunca mientras se teclea. (El patrón anterior comparaba contra `edicion` y machacaba lo
  // tecleado en cuanto era un número "limpio": teclear en el stepper no funcionaba.)
  const [valorPrevio, setValorPrevio] = useState(valor);
  if (valor !== valorPrevio) {
    setValorPrevio(valor);
    setEdicion(String(Math.round(valor)));
  }

  const fija = (v: number) => onChange(Math.max(min, Math.min(max, v)));
  const commitear = () => {
    const v = Number(edicion);
    if (!isNaN(v)) fija(v);
    setEdicion(String(Math.round(valor)));
  };

  return (
    <div title={etiqueta} className="flex h-8 shrink-0 items-center overflow-hidden rounded-md border border-input">
      {icono && <span className="pl-1.5 text-muted-foreground">{icono}</span>}
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor - paso)} title={`${etiqueta}: menos`}>−</button>
      <input
        type="number"
        value={edicion}
        onChange={(e) => setEdicion(e.target.value)}
        onBlur={commitear}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitear();
          if (e.key === "Escape") setEdicion(String(Math.round(valor)));
        }}
        aria-label={etiqueta}
        className={`${ancho} bg-background px-1 text-center text-sm outline-none`}
      />
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor + paso)} title={`${etiqueta}: más`}>+</button>
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

  // Estilo de PÍLDORA flotante (mismo lenguaje que la barra de alinear/orden del Lienzo).
  const PILDORA =
    "flex min-w-0 max-w-full shrink items-center gap-1 overflow-x-auto rounded-md border border-border bg-popover p-1 shadow-md";

  // Varias capas: la barra contextual se mantiene minimalista (las acciones de alineación viven en
  // la píldora de al lado).
  if (seleccionMulti.length > 1) {
    return (
      <div className={PILDORA}>
        <span className="whitespace-nowrap px-1 text-xs text-muted-foreground">{seleccionMulti.length} capas</span>
        <Sep />
        <BotonIcono titulo="Ajustes" onClick={onAbrirAjustes}><Settings2 className="h-4 w-4" /> Ajustes</BotonIcono>
      </div>
    );
  }

  // Sin selección: nada (la barra solo existe para la capa seleccionada).
  if (!capa) return null;

  return (
    <div className={PILDORA}>
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
          {/* NEGRITA: toggle grueso 400<->700 (caras reales en todo el catálogo; nada se
              sintetiza). Los pesos finos (Ligera 300, Extranegrita 800, Black 900…) se eligen en
              Ajustes -> Peso y la B los NORMALIZA al usarla (Black+B => 400, Light+B => 700):
              mapeo honesto y predecible, igual que Canva/Docs. `activo` con peso >= 600. */}
          <BotonIcono
            titulo="Negrita (pesos finos en Ajustes → Peso)"
            ariaLabel="Negrita"
            activo={(capa as CapaTexto).peso >= 600}
            onClick={() => set({ peso: (capa as CapaTexto).peso >= 600 ? 400 : 700 } as Partial<Capa>)}
          >
            <Bold className="h-4 w-4" />
          </BotonIcono>
          {(() => {
            const c = capa as CapaTexto;
            // CURSIVA solo para familias con itálica REAL (la misma regla que `dibujar.mjs` y el
            // servidor): fuera de la lista el botón se apaga (patrón Canva) y nada se sintetiza.
            // `familiaReal` resuelve las familias lógicas legadas ("sans"/"condensada").
            const hayCursiva = tieneCursiva(familiaReal(c.familia));
            return (
              <BotonIcono
                titulo={hayCursiva ? "Cursiva" : "Esta fuente no tiene cursiva"}
                ariaLabel="Cursiva"
                activo={hayCursiva && !!c.cursiva}
                deshabilitado={!hayCursiva}
                onClick={() => set({ cursiva: !c.cursiva } as Partial<Capa>)}
              >
                <Italic className="h-4 w-4" />
              </BotonIcono>
            );
          })()}
          {(() => {
            const c = capa as CapaTexto;
            // El texto en ARCO (curva) no se subraya en ningún lado (ni Konva TextPath ni el
            // export): el botón se apaga para no prometer nada que la pieza final no tenga.
            const enArco = !!c.curva?.radio;
            return (
              <BotonIcono
                titulo={enArco ? "El texto en arco no admite subrayado" : "Subrayado"}
                ariaLabel="Subrayado"
                activo={!enArco && !!c.subrayado}
                deshabilitado={enArco}
                onClick={() => set({ subrayado: !c.subrayado } as Partial<Capa>)}
              >
                <Underline className="h-4 w-4" />
              </BotonIcono>
            );
          })()}
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
          {/* INTERLINEADO (line-height relativo): presets estilo Canva. Soportado end-to-end:
              `interlineado` viaja en el documento y lo pinta igual el editor (Konva `lineHeight`)
              y el export del servidor (`dibujar.mjs`). */}
          {(() => {
            const v = (capa as CapaTexto).interlineado;
            const opciones: number[] = INTERLINEADOS.includes(v as (typeof INTERLINEADOS)[number])
              ? [...INTERLINEADOS]
              : [...INTERLINEADOS, v].sort((a, b) => a - b);
            return (
              <label title="Interlineado" className="flex h-8 shrink-0 items-center gap-0.5 rounded-md border border-input bg-background pl-1.5 pr-1">
                <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                <select
                  aria-label="Interlineado"
                  value={String(v)}
                  onChange={(e) => set({ interlineado: Number(e.target.value) } as Partial<Capa>)}
                  className="h-full bg-background text-sm outline-none"
                >
                  {opciones.map((o) => (
                    <option key={o} value={String(o)}>{fmtInterlineado(o)}</option>
                  ))}
                </select>
              </label>
            );
          })()}
          {/* ESPACIADO ENTRE LETRAS (tracking, px): también end-to-end (`interletra` en el
              documento; Konva `letterSpacing` y `ctx.letterSpacing` en el render del servidor). */}
          <Stepper
            valor={(capa as CapaTexto).interletra || 0}
            min={-20}
            max={200}
            ancho="w-10"
            etiqueta="Espaciado entre letras"
            icono={<ChevronsLeftRight className="h-3.5 w-3.5" />}
            onChange={(v) => set({ interletra: v } as Partial<Capa>)}
          />
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

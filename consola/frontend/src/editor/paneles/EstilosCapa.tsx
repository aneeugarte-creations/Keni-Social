// Copiar/pegar ESTILO + estilos guardados con nombre (por marca). Reutiliza el portapapeles de
// estilo en memoria (compartido con los atajos ⌘⌥C/⌘⌥V del lienzo) y localStorage para los
// guardados. Aplica al pegar solo los campos compatibles con el tipo de la capa destino.

import { ClipboardPaste, Copy as CopyIcon, Save, Trash2 } from "lucide-react";
import { useState } from "react";

import type { Capa } from "../documento";
import { aplicarEstilo, estiloDe } from "../estilo";
import {
  cargarEstilosGuardados,
  copiarEstiloPortapapeles,
  estiloPortapapeles,
  guardarEstilo,
  quitarEstiloGuardado,
} from "../estilos-guardados";
import { useEditor, useStoreEditor } from "../usarEditor";

export function EstilosCapa({ capa, marca }: { capa: Capa; marca: string }) {
  const store = useStoreEditor();
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  // `tick` fuerza re-render tras copiar/guardar (las funciones son módulo, no estado de React).
  const [tick, setTick] = useState(0);
  const [guardando, setGuardando] = useState(false);
  const [nombre, setNombre] = useState("");

  const copiado = estiloPortapapeles();
  const guardados = cargarEstilosGuardados(marca).filter((e) => e.tipo === capa.tipo);

  // Aplica un estilo a TODA la selección (o a la capa actual), un solo paso de historial.
  const aplicarATodo = (estilo: ReturnType<typeof estiloDe>) => {
    const ids = seleccionMulti.length ? seleccionMulti : [capa.id];
    const st = store.getState();
    const objetivos = st.documento.capas.filter((c) => ids.includes(c.id));
    if (!objetivos.length) return;
    st.comenzarGesto();
    for (const c of objetivos) {
      const cambios = aplicarEstilo(c, estilo);
      if (Object.keys(cambios).length) st.actualizar(c.id, cambios, false);
    }
  };

  return (
    <div className="flex flex-col gap-1.5 border-t border-border pt-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Estilo</div>
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          onClick={() => { copiarEstiloPortapapeles(capa); setTick((n) => n + 1); }}
          className="flex items-center gap-1 rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
          title="Copiar estilo (⌘⌥C)"
        >
          <CopyIcon className="h-3.5 w-3.5" /> Copiar estilo
        </button>
        <button
          type="button"
          disabled={!copiado}
          onClick={() => { if (copiado) aplicarATodo(copiado); }}
          className="flex items-center gap-1 rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent disabled:opacity-40"
          title="Pegar estilo en la selección (⌘⌥V)"
        >
          <ClipboardPaste className="h-3.5 w-3.5" /> Pegar estilo
        </button>
        <button
          type="button"
          onClick={() => { setGuardando((v) => !v); setNombre(""); }}
          className="flex items-center gap-1 rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
          title="Guardar este estilo con un nombre (por marca)"
        >
          <Save className="h-3.5 w-3.5" /> Guardar estilo
        </button>
      </div>
      {/* Guardar estilo con nombre (input inline). */}
      {guardando && (
        <div className="flex items-center gap-1">
          <input
            autoFocus
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { guardarEstilo(marca, nombre, capa); setGuardando(false); setTick((n) => n + 1); }
              if (e.key === "Escape") setGuardando(false);
            }}
            placeholder="Nombre del estilo…"
            className="min-w-0 flex-1 rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          />
          <button
            type="button"
            onClick={() => { guardarEstilo(marca, nombre, capa); setGuardando(false); setTick((n) => n + 1); }}
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
          >
            OK
          </button>
        </div>
      )}
      {/* Estilos guardados del tipo de esta capa: aplicar (clic) o quitar (papelera). */}
      {guardados.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">Aplicar estilo guardado</span>
          {guardados.map((g) => (
            <div key={g.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => aplicarATodo(g.estilo)}
                className="min-w-0 flex-1 truncate rounded border border-input bg-background px-1.5 py-0.5 text-left text-xs hover:bg-accent"
                title={`Aplicar «${g.nombre}»`}
              >
                {g.nombre}
              </button>
              <button
                type="button"
                onClick={() => { quitarEstiloGuardado(marca, g.id); setTick((n) => n + 1); }}
                className="shrink-0 text-muted-foreground hover:text-destructive"
                title="Quitar estilo guardado"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
      <span className="hidden">{tick}</span>
    </div>
  );
}

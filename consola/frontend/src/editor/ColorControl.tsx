// Control de color reutilizable: muestra el color actual y, al abrirlo, ofrece el selector nativo
// más MUESTRAS de los colores ya usados en el diseño («paleta del documento») y los recientes.
// Pensado para reutilizar color de marca con un clic, sin tener que recordar el hex.

import { useEffect, useState } from "react";

import type { CapaMarco, CapaOverlay, CapaTexto } from "./documento";
import { useEditor } from "./usarEditor";

// Colores recientes a nivel de módulo (persisten entre selecciones y pestañas durante la sesión).
const recientes: string[] = [];
function recordar(color: string) {
  const c = color.toUpperCase();
  const i = recientes.indexOf(c);
  if (i >= 0) recientes.splice(i, 1);
  recientes.unshift(c);
  if (recientes.length > 10) recientes.length = 10;
}

// Recolecta los colores DISTINTOS presentes en el documento (texto, marcos, chips, overlays, fondo).
function coloresDelDocumento(capas: unknown[], fondo: { color?: string; degradado?: { desde: string; hasta: string } }): string[] {
  const set = new Set<string>();
  const add = (c?: string | null) => { if (c && /^#[0-9a-fA-F]{6}$/.test(c)) set.add(c.toUpperCase()); };
  for (const capa of capas as { tipo: string }[]) {
    if (capa.tipo === "texto") { add((capa as CapaTexto).color); add((capa as CapaTexto).chip?.color); add((capa as CapaTexto).contorno?.color); }
    if (capa.tipo === "marco") { add((capa as CapaMarco).relleno); add((capa as CapaMarco).borde?.color); }
    if (capa.tipo === "overlay") add((capa as CapaOverlay).color);
  }
  add(fondo.color);
  add(fondo.degradado?.desde);
  add(fondo.degradado?.hasta);
  return [...set];
}

function Muestras({ colores, valor, onPick }: { colores: string[]; valor: string; onPick: (c: string) => void }) {
  if (colores.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {colores.map((c) => (
        <button
          key={c}
          onClick={() => onPick(c)}
          title={c}
          className={`h-5 w-5 rounded border ${c.toUpperCase() === valor.toUpperCase() ? "border-primary ring-1 ring-primary" : "border-border"}`}
          style={{ background: c }}
        />
      ))}
    </div>
  );
}

export function ColorControl({ valor, onChange }: { valor: string; onChange: (c: string) => void }) {
  const [abierto, setAbierto] = useState(false);
  const capas = useEditor((s) => s.documento.capas);
  const fondo = useEditor((s) => s.documento.fondo);
  const delDoc = coloresDelDocumento(capas, fondo);

  useEffect(() => {
    if (!abierto) return;
    const cerrar = () => setAbierto(false);
    window.addEventListener("click", cerrar);
    return () => window.removeEventListener("click", cerrar);
  }, [abierto]);

  const elegir = (c: string) => { recordar(c); onChange(c); };

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setAbierto((v) => !v)}
        className="h-6 w-10 rounded border border-input"
        style={{ background: valor }}
        title="Color"
      />
      {abierto && (
        <div className="absolute right-0 z-50 mt-1 w-48 rounded-md border border-border bg-popover p-2 shadow-lg">
          <input
            type="color"
            value={valor}
            onChange={(e) => elegir(e.target.value)}
            className="mb-2 h-7 w-full cursor-pointer"
          />
          {delDoc.length > 0 && (
            <>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">En el diseño</div>
              <Muestras colores={delDoc} valor={valor} onPick={elegir} />
            </>
          )}
          {recientes.length > 0 && (
            <>
              <div className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Recientes</div>
              <Muestras colores={recientes} valor={valor} onPick={elegir} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

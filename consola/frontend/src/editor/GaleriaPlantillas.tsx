// Galería visual de plantillas de diseño: rejilla de miniaturas para elegir una de un vistazo
// (mucho mejor que un desplegable). Filtra por la marca de la pestaña activa (el llamante).

import { Copy, Trash2, X } from "lucide-react";
import { useState } from "react";

import { urlMedia, type PlantillaDiseno } from "@/lib/api";

export function GaleriaPlantillas({
  plantillas,
  onCargar,
  onBorrar,
  onDuplicar,
  onRenombrar,
  onCerrar,
}: {
  plantillas: PlantillaDiseno[];
  onCargar: (p: PlantillaDiseno) => void;
  /** Si se omite, no se ofrece borrar (modo SELECTOR, p. ej. elegir plantilla para una pieza). */
  onBorrar?: (p: PlantillaDiseno) => void;
  /** Si se omite, no se ofrece duplicar (modo SELECTOR). */
  onDuplicar?: (p: PlantillaDiseno) => void;
  /** Si se omite, no se ofrece renombrar (modo SELECTOR). */
  onRenombrar?: (p: PlantillaDiseno, nombre: string) => void;
  onCerrar: () => void;
}) {
  const [editId, setEditId] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const commit = (p: PlantillaDiseno) => {
    const n = editVal.trim();
    if (n && n !== p.nombre) onRenombrar?.(p, n);
    setEditId(null);
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onCerrar}>
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Plantillas</h2>
          <button onClick={onCerrar} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          {plantillas.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Aún no hay plantillas para esta marca. Diseña una y pulsa «Guardar plantilla».
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {plantillas.map((p) => (
                <div key={p.id} className="group relative">
                  <button
                    onClick={() => onCargar(p)}
                    title={`Cargar «${p.nombre}»`}
                    className="block w-full overflow-hidden rounded border border-border bg-muted/40 hover:ring-2 hover:ring-primary"
                  >
                    <div className="aspect-[4/5] w-full">
                      {/* Miniatura guardada (la genera el estudio al guardar) o, si falta —p. ej.
                          plantillas creadas por API/agente—, el render on-demand del documento. */}
                      <img
                        src={p.miniatura ? urlMedia(p.miniatura) : `/api/plantillas-diseno/${p.id}/preview`}
                        alt={p.nombre}
                        loading="lazy"
                        className="h-full w-full object-contain"
                      />
                    </div>
                  </button>
                  {/* Título: clic para renombrar inline (la miniatura de arriba abre la plantilla). */}
                  {onRenombrar && editId === p.id ? (
                    <input
                      autoFocus
                      value={editVal}
                      onChange={(e) => setEditVal(e.target.value)}
                      onBlur={() => commit(p)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commit(p);
                        else if (e.key === "Escape") setEditId(null);
                      }}
                      className="block w-full rounded border border-primary bg-background px-1.5 py-1 text-xs"
                    />
                  ) : onRenombrar ? (
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditId(p.id); setEditVal(p.nombre || ""); }}
                      title="Clic para renombrar"
                      className="block w-full truncate px-1.5 py-1 text-left text-xs text-muted-foreground hover:text-foreground"
                    >
                      {p.nombre || "(sin nombre)"}
                    </button>
                  ) : (
                    <div className="truncate px-1.5 py-1 text-left text-xs">{p.nombre || "(sin nombre)"}</div>
                  )}
                  {onDuplicar && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onDuplicar(p); }}
                      title="Duplicar plantilla"
                      className="absolute right-8 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 hover:text-foreground group-hover:opacity-100"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {onBorrar && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onBorrar(p); }}
                      title="Borrar plantilla"
                      className="absolute right-1 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

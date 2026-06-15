/**
 * Pestaña "Ficha" del editor de documentos: metadata editable con autosave.
 *
 * Cada campo dispara `onEditar` (el contenedor debouncea y guarda); las etiquetas
 * se confirman onBlur tras parsear por comas. Los campos exclusivos de documentos
 * editoriales (clase, marcas, prioridad) solo se muestran cuando `tipo !== "prompt"`.
 */
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import type { DocumentoTexto } from "@/types";

const CLASES_EDITORIAL = ["marca", "voz", "plataforma", "tropicalizacion", "reglas"] as const;

function Campo({
  htmlFor,
  etiqueta,
  ayuda,
  children,
}: {
  htmlFor?: string;
  etiqueta: string;
  ayuda?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor} className="text-xs font-medium">
        {etiqueta}
      </Label>
      {children}
      {ayuda ? <p className="text-[11px] leading-snug text-muted-foreground">{ayuda}</p> : null}
    </div>
  );
}

export function PanelFicha({
  borrador,
  marcas,
  onEditar,
}: {
  borrador: DocumentoTexto;
  marcas: { id: string; nombre: string }[];
  onEditar: (parcial: Partial<DocumentoTexto>) => void;
}) {
  const esEditorial = borrador.tipo !== "prompt";

  return (
    <div className="space-y-5 text-sm">
      {/* ── Identidad ── */}
      <div className="space-y-4">
        <Campo htmlFor="ficha-descripcion" etiqueta="Descripción" ayuda="Qué es y para qué sirve (solo para el equipo; no se inyecta).">
          <Input
            id="ficha-descripcion"
            value={borrador.descripcion ?? ""}
            onChange={(e) => onEditar({ descripcion: e.target.value })}
            placeholder="Qué es y para qué"
          />
        </Campo>

        <Campo htmlFor="ficha-carpeta" etiqueta="Carpeta" ayuda="Dónde se organiza en la biblioteca.">
          <Input
            id="ficha-carpeta"
            value={borrador.carpeta}
            onChange={(e) => onEditar({ carpeta: e.target.value })}
            placeholder="sin carpeta"
          />
        </Campo>

        <Campo
          htmlFor="ficha-etiquetas"
          etiqueta="Etiquetas"
          ayuda="Separadas por comas. Se guardan al salir del campo."
        >
          <Input
            id="ficha-etiquetas"
            defaultValue={(borrador.etiquetas ?? []).join(", ")}
            onBlur={(e) =>
              onEditar({
                etiquetas: e.target.value
                  .split(",")
                  .map((t) => t.trim())
                  .filter(Boolean),
              })
            }
            placeholder="ej. breaking, deportes"
          />
        </Campo>
      </div>

      {/* ── Ensamblaje editorial (solo documentos editoriales) ── */}
      {esEditorial ? (
        <div className="space-y-4 border-t border-border pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Ensamblaje editorial
          </p>

          <Campo htmlFor="ficha-clase" etiqueta="Clase" ayuda="Cómo se clasifica al auto-adjuntarse.">
            <select
              id="ficha-clase"
              value={borrador.clase || ""}
              onChange={(e) => onEditar({ clase: e.target.value })}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="">(sin clase)</option>
              {CLASES_EDITORIAL.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Campo>

          {marcas.length > 0 ? (
            <fieldset className="space-y-2">
              <legend className="text-xs font-medium">Marcas a las que aplica</legend>
              <div className="space-y-2 rounded-md border border-border p-3">
                {marcas.map((m) => {
                  const activa = (borrador.marcas ?? []).includes(m.id);
                  return (
                    <label
                      key={m.id}
                      htmlFor={`ficha-marca-${m.id}`}
                      className="flex cursor-pointer items-center gap-2.5 text-sm"
                    >
                      <Checkbox
                        id={`ficha-marca-${m.id}`}
                        checked={activa}
                        onCheckedChange={(checked) => {
                          const set = new Set(borrador.marcas ?? []);
                          if (checked) set.add(m.id);
                          else set.delete(m.id);
                          onEditar({ marcas: [...set] });
                        }}
                      />
                      {m.nombre}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ) : null}

          <Campo
            htmlFor="ficha-prioridad"
            etiqueta="Prioridad de ensamblaje"
            ayuda="Menor número = se adjunta antes."
          >
            <Input
              id="ficha-prioridad"
              type="number"
              value={borrador.prioridad ?? 0}
              onChange={(e) => onEditar({ prioridad: Number(e.target.value) })}
              className="w-28"
            />
          </Campo>
        </div>
      ) : null}
    </div>
  );
}

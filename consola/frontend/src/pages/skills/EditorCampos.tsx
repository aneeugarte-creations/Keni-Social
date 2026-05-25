/**
 * Editor de los `campos` de una skill: filas que se añaden, borran y reordenan.
 *
 * Cada fila edita un `Campo` completo: id, etiqueta, tipo, requerido, placeholder,
 * ayuda y —según el tipo— opciones (select) o tipos de medios (archivo). El estado
 * vive en el componente padre (el editor de la skill); aquí solo se renderiza y se
 * emite el array actualizado.
 */
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { Campo, TipoCampo } from "@/types";

import { TIPOS_CAMPO } from "./claves";

/** Un campo nuevo vacío con un id sugerido único dentro de la lista. */
function campoVacio(existentes: Campo[]): Campo {
  let n = existentes.length + 1;
  let id = `campo_${n}`;
  const ids = new Set(existentes.map((c) => c.id));
  while (ids.has(id)) {
    n += 1;
    id = `campo_${n}`;
  }
  return { id, etiqueta: "", tipo: "texto", requerido: false };
}

/** Convierte un texto multilínea/coma en un array de opciones (sin vacíos). */
function parsearOpciones(texto: string): string[] {
  return texto
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function EditorCampos({
  campos,
  onCambio,
}: {
  campos: Campo[];
  onCambio: (campos: Campo[]) => void;
}) {
  function actualizar(indice: number, parcial: Partial<Campo>) {
    onCambio(campos.map((c, i) => (i === indice ? { ...c, ...parcial } : c)));
  }

  function borrar(indice: number) {
    onCambio(campos.filter((_, i) => i !== indice));
  }

  function mover(indice: number, delta: number) {
    const destino = indice + delta;
    if (destino < 0 || destino >= campos.length) return;
    const copia = [...campos];
    const [fila] = copia.splice(indice, 1);
    copia.splice(destino, 0, fila);
    onCambio(copia);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Campos del formulario</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onCambio([...campos, campoVacio(campos)])}
        >
          <Plus className="h-4 w-4" />
          Añadir campo
        </Button>
      </div>

      {campos.length === 0 ? (
        <p className="rounded-md border border-dashed border-border bg-muted/20 px-3 py-4 text-center text-sm text-muted-foreground">
          Esta skill no tiene campos. Añade al menos uno para que el formulario
          pida datos al usuario.
        </p>
      ) : (
        <div className="space-y-3">
          {campos.map((campo, i) => (
            <div key={i} className="space-y-3 rounded-md border border-border p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-muted-foreground">Campo {i + 1}</span>
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => mover(i, -1)}
                    disabled={i === 0}
                    aria-label="Subir campo"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => mover(i, 1)}
                    disabled={i === campos.length - 1}
                    aria-label="Bajar campo"
                  >
                    <ArrowDown className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    onClick={() => borrar(i)}
                    aria-label="Borrar campo"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor={`campo-id-${i}`}>Identificador</Label>
                  <Input
                    id={`campo-id-${i}`}
                    value={campo.id}
                    onChange={(e) => actualizar(i, { id: e.target.value })}
                    placeholder="Ej. nota_base"
                    className="font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`campo-etiqueta-${i}`}>Etiqueta</Label>
                  <Input
                    id={`campo-etiqueta-${i}`}
                    value={campo.etiqueta}
                    onChange={(e) => actualizar(i, { etiqueta: e.target.value })}
                    placeholder="Ej. Nota base"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`campo-tipo-${i}`}>Tipo</Label>
                  <Select
                    value={campo.tipo}
                    onValueChange={(v) => actualizar(i, { tipo: v as TipoCampo })}
                  >
                    <SelectTrigger id={`campo-tipo-${i}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TIPOS_CAMPO.map((t) => (
                        <SelectItem key={t.id} value={t.id}>
                          {t.nombre}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-end pb-1">
                  <Label
                    htmlFor={`campo-req-${i}`}
                    className="flex cursor-pointer items-center gap-2 font-normal"
                  >
                    <Checkbox
                      id={`campo-req-${i}`}
                      checked={campo.requerido}
                      onCheckedChange={(v) => actualizar(i, { requerido: v })}
                    />
                    Requerido
                  </Label>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor={`campo-ph-${i}`}>Placeholder</Label>
                  <Input
                    id={`campo-ph-${i}`}
                    value={campo.placeholder ?? ""}
                    onChange={(e) => actualizar(i, { placeholder: e.target.value })}
                    placeholder="Texto de ejemplo dentro del campo"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`campo-ayuda-${i}`}>Ayuda</Label>
                  <Input
                    id={`campo-ayuda-${i}`}
                    value={campo.ayuda ?? ""}
                    onChange={(e) => actualizar(i, { ayuda: e.target.value })}
                    placeholder="Texto de ayuda bajo el campo"
                  />
                </div>
              </div>

              {campo.tipo === "select" && (
                <div className="space-y-1.5">
                  <Label htmlFor={`campo-op-${i}`}>Opciones (una por línea)</Label>
                  <Textarea
                    id={`campo-op-${i}`}
                    value={(campo.opciones ?? []).join("\n")}
                    onChange={(e) => actualizar(i, { opciones: parsearOpciones(e.target.value) })}
                    placeholder={"Opción A\nOpción B\nOpción C"}
                    className="min-h-[5rem]"
                  />
                </div>
              )}

              {campo.tipo === "archivo" && (
                <div className="space-y-1.5">
                  <Label htmlFor={`campo-media-${i}`}>Tipos de archivo aceptados (accept)</Label>
                  <Input
                    id={`campo-media-${i}`}
                    value={campo.media_tipos ?? ""}
                    onChange={(e) => actualizar(i, { media_tipos: e.target.value })}
                    placeholder="Ej. video/*,audio/* o .pdf,.docx"
                    className="font-mono"
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

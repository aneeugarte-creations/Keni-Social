/**
 * Renderiza el formulario DINÁMICO de una skill a partir de sus `campos`.
 *
 * Cada `Campo` se mapea a un control: textarea/texto/select/fecha → valor de
 * texto en el mapa `valores`; archivo → un `File` que vive aparte (el padre lo
 * gestiona). Muestra etiqueta, marcador de requerido, ayuda y placeholder.
 */
import { FileAudio, FileText, Upload, X } from "lucide-react";
import * as React from "react";

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
import type { Campo } from "@/types";

/** Asterisco rojo para campos requeridos (o "(opcional)" si no lo es). */
function MarcaRequerido({ requerido }: { requerido: boolean }) {
  if (requerido) return <span className="text-destructive"> *</span>;
  return <span className="font-normal text-muted-foreground"> (opcional)</span>;
}

/** Texto de ayuda bajo un campo, si lo hay. */
function Ayuda({ texto }: { texto?: string }) {
  if (!texto) return null;
  return <p className="text-xs text-muted-foreground">{texto}</p>;
}

/** Zona de subida de archivo para un campo de tipo `archivo`. */
function CampoArchivo({
  campo,
  archivo,
  onArchivo,
  onLimpiar,
}: {
  campo: Campo;
  archivo: File | null;
  onArchivo: (file: File | null) => void;
  onLimpiar: () => void;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const media = (campo.media_tipos ?? "").includes("video") || (campo.media_tipos ?? "").includes("audio");
  const Icono = media ? FileAudio : FileText;
  const acepta = campo.media_tipos || undefined;

  return (
    <div className="space-y-2">
      <Label htmlFor={`campo-${campo.id}`}>
        {campo.etiqueta}
        <MarcaRequerido requerido={campo.requerido} />
      </Label>
      <input
        ref={inputRef}
        id={`campo-${campo.id}`}
        type="file"
        accept={acepta}
        onChange={(e) => onArchivo(e.target.files?.[0] ?? null)}
        className="hidden"
      />
      {archivo ? (
        <div className="flex items-center gap-3 rounded-md border border-border bg-muted/40 px-3 py-2.5">
          <Icono className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-sm">{archivo.name}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {(archivo.size / 1024 / 1024).toFixed(1)} MB
          </span>
          <button
            type="button"
            onClick={onLimpiar}
            aria-label="Quitar archivo"
            className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/20 px-4 py-8 text-center transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <Upload className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm font-medium">Haz clic para elegir un archivo</span>
          {campo.placeholder && (
            <span className="text-xs text-muted-foreground">{campo.placeholder}</span>
          )}
        </button>
      )}
      <Ayuda texto={campo.ayuda} />
    </div>
  );
}

/**
 * Lista de campos de una skill. Para los de texto delega en `valores`/`onValor`;
 * para el (único) campo de archivo delega en `archivo`/`onArchivo`.
 */
export function CamposSkill({
  campos,
  valores,
  onValor,
  archivo,
  onArchivo,
}: {
  campos: Campo[];
  valores: Record<string, string>;
  onValor: (id: string, valor: string) => void;
  archivo: File | null;
  onArchivo: (file: File | null) => void;
}) {
  return (
    <div className="space-y-4">
      {campos.map((campo) => {
        if (campo.tipo === "archivo") {
          return (
            <CampoArchivo
              key={campo.id}
              campo={campo}
              archivo={archivo}
              onArchivo={onArchivo}
              onLimpiar={() => onArchivo(null)}
            />
          );
        }

        const valor = valores[campo.id] ?? "";
        const idControl = `campo-${campo.id}`;
        const etiqueta = (
          <Label htmlFor={idControl}>
            {campo.etiqueta}
            <MarcaRequerido requerido={campo.requerido} />
          </Label>
        );

        if (campo.tipo === "textarea") {
          return (
            <div key={campo.id} className="space-y-1.5">
              {etiqueta}
              <Textarea
                id={idControl}
                value={valor}
                onChange={(e) => onValor(campo.id, e.target.value)}
                placeholder={campo.placeholder}
                className="min-h-[10rem]"
              />
              <Ayuda texto={campo.ayuda} />
            </div>
          );
        }

        if (campo.tipo === "select") {
          return (
            <div key={campo.id} className="space-y-1.5">
              {etiqueta}
              <Select value={valor} onValueChange={(v) => onValor(campo.id, v)}>
                <SelectTrigger id={idControl}>
                  <SelectValue placeholder={campo.placeholder ?? "Elige una opción"} />
                </SelectTrigger>
                <SelectContent>
                  {(campo.opciones ?? []).map((op) => (
                    <SelectItem key={op} value={op}>
                      {op}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Ayuda texto={campo.ayuda} />
            </div>
          );
        }

        if (campo.tipo === "fecha") {
          return (
            <div key={campo.id} className="space-y-1.5">
              {etiqueta}
              <Input
                id={idControl}
                type="date"
                value={valor}
                onChange={(e) => onValor(campo.id, e.target.value)}
              />
              <Ayuda texto={campo.ayuda} />
            </div>
          );
        }

        // tipo === "texto"
        return (
          <div key={campo.id} className="space-y-1.5">
            {etiqueta}
            <Input
              id={idControl}
              value={valor}
              onChange={(e) => onValor(campo.id, e.target.value)}
              placeholder={campo.placeholder}
            />
            <Ayuda texto={campo.ayuda} />
          </div>
        );
      })}
    </div>
  );
}

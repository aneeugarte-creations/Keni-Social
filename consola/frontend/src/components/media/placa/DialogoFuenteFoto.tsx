/**
 * Diálogo de ORIGEN de la foto del hueco activo: usar imagen original · Galería · Subir ·
 * generar con IA. Se abre al TOCAR un hueco (no es un bloque fijo del panel). Escribe en el HUECO
 * ACTIVO (lo gobierna el componente padre vía callbacks).
 */
import { ImagePlus, Library, Loader2, Upload } from "lucide-react";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export interface DialogoFuenteFotoProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** ¿El collage tiene varios huecos? (cambia el título del diálogo). */
  esCollage: boolean;
  /** Índice (0-based) del hueco activo. */
  slotActivo: number;
  /** Nº total de huecos del diseño. */
  nHuecos: number;
  /** URL de la imagen original (RSS de marca propia), si la pieza la trae. */
  imagenFuente?: string;
  /** ¿Hay alguna acción de origen en curso? (deshabilita los controles). */
  ocupado: boolean;
  /** ¿Está subiendo un archivo? */
  subiendo: boolean;
  /** ¿Está cargando la imagen original? */
  usandoOriginal: boolean;
  /** ¿Está generando con IA? */
  generandoIA: boolean;
  /** Prompt de IA (controlado por el padre). */
  prompt: string;
  onPromptCambio: (valor: string) => void;
  /** Aviso (p. ej. error 400 de generación). */
  avisoGenerar: string;
  /** "Usar imagen original". */
  onUsarOriginal: () => void;
  /** Abre la galería de artes. */
  onAbrirGaleria: () => void;
  /** Abre el selector de archivo ("Subir"). */
  onSubir: () => void;
  /** Lanza la generación con IA. */
  onGenerar: () => void;
}

export function DialogoFuenteFoto({
  open,
  onOpenChange,
  esCollage,
  slotActivo,
  nHuecos,
  imagenFuente,
  ocupado,
  subiendo,
  usandoOriginal,
  generandoIA,
  prompt,
  onPromptCambio,
  avisoGenerar,
  onUsarOriginal,
  onAbrirGaleria,
  onSubir,
  onGenerar,
}: DialogoFuenteFotoProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {esCollage ? `Foto del hueco ${slotActivo + 1} de ${nHuecos}` : "Imagen de la pieza"}
          </DialogTitle>
          <DialogDescription>Elígela de la galería, súbela o genérala con IA.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {imagenFuente && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onUsarOriginal}
                disabled={ocupado}
              >
                {usandoOriginal ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ImagePlus className="h-4 w-4" />
                )}
                Usar imagen original
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onAbrirGaleria}
              disabled={ocupado}
            >
              <Library className="h-4 w-4" />
              Galería
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onSubir}
              disabled={ocupado}
            >
              {subiendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              Subir
            </Button>
          </div>
          <div className="space-y-1.5">
            <span className="text-xs text-muted-foreground">
              o genera con IA (sugerencia: el copy del post):
            </span>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                value={prompt}
                onChange={(e) => onPromptCambio(e.target.value)}
                placeholder="Describe la imagen: p. ej. estadio iluminado al atardecer…"
                disabled={ocupado}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && prompt.trim() && !ocupado) {
                    e.preventDefault();
                    onGenerar();
                  }
                }}
              />
              <Button
                type="button"
                size="sm"
                onClick={onGenerar}
                disabled={ocupado || prompt.trim().length === 0}
                className="shrink-0"
              >
                {generandoIA ? <Loader2 className="h-4 w-4 animate-spin" /> : <MarcaIA costo />}
                {generandoIA ? "Generando…" : "Generar con IA"}
              </Button>
            </div>
          </div>
          {avisoGenerar && (
            <p className="rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-300">
              {avisoGenerar}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

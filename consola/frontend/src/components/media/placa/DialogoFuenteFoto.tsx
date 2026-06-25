/**
 * Diálogo de ORIGEN de la foto del hueco activo: Galería · Subir · generar con IA. Se abre al
 * TOCAR un hueco (no es un bloque fijo del panel). Escribe en el HUECO ACTIVO (lo gobierna el
 * componente padre vía callbacks).
 */
import { Camera, Library, Newspaper, ScanSearch, Upload } from "lucide-react";

import { Aviso } from "@/components/comunes/Aviso";
import { MarcaIA } from "@/components/comunes/MarcaIA";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

export interface DialogoFuenteFotoProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** ¿El collage tiene varios huecos? (cambia el título del diálogo). */
  esCollage: boolean;
  /** Índice (0-based) del hueco activo. */
  slotActivo: number;
  /** Nº total de huecos del diseño. */
  nHuecos: number;
  /** ¿Hay alguna acción de origen en curso? (deshabilita los controles). */
  ocupado: boolean;
  /** ¿Está subiendo un archivo? */
  subiendo: boolean;
  /** ¿Está generando con IA? */
  generandoIA: boolean;
  /** Prompt de IA (controlado por el padre). */
  prompt: string;
  onPromptCambio: (valor: string) => void;
  /** Aviso (p. ej. error 400 de generación). */
  avisoGenerar: string;
  /** Abre la galería de artes. */
  onAbrirGaleria: () => void;
  /** Abre el selector de archivo ("Subir"). */
  onSubir: () => void;
  /** Abre el buscador de fotos de stock ("Buscar foto"); ausente si no hay pieza donde adjuntarla. */
  onBuscarStock?: () => void;
  /** Abre el buscador de fotos LICENCIADAS de agencia (AFP); ausente si no hay pieza. */
  onBuscarAgencias?: () => void;
  /** Abre el buscador de fotos PROPIAS (galería local del equipo); solo en piezas de Claro Sports. */
  onBuscarPropio?: () => void;
  /** Lanza la generación con IA. */
  onGenerar: () => void;
}

export function DialogoFuenteFoto({
  open,
  onOpenChange,
  esCollage,
  slotActivo,
  nHuecos,
  ocupado,
  subiendo,
  generandoIA,
  prompt,
  onPromptCambio,
  avisoGenerar,
  onAbrirGaleria,
  onSubir,
  onBuscarStock,
  onBuscarAgencias,
  onBuscarPropio,
  onGenerar,
}: DialogoFuenteFotoProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {esCollage ? `Foto del hueco ${slotActivo + 1} de ${nHuecos}` : "Imagen de la pieza"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
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
              {subiendo ? <Spinner className="h-4 w-4" /> : <Upload className="h-4 w-4" />}
              Subir
            </Button>
            {onBuscarStock && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onBuscarStock}
                disabled={ocupado}
              >
                <ScanSearch className="h-4 w-4" />
                Buscar foto
              </Button>
            )}
            {onBuscarAgencias && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onBuscarAgencias}
                disabled={ocupado}
              >
                <Newspaper className="h-4 w-4" />
                Foto de agencia (AFP)
              </Button>
            )}
            {onBuscarPropio && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onBuscarPropio}
                disabled={ocupado}
              >
                <Camera className="h-4 w-4" />
                Foto propia
              </Button>
            )}
          </div>
          <div className="space-y-1.5">
            <span className="text-xs text-muted-foreground">
              O genera con IA:
            </span>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                value={prompt}
                onChange={(e) => onPromptCambio(e.target.value)}
                placeholder="Ej: estadio iluminado al atardecer"
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
                {generandoIA ? <Spinner className="h-4 w-4" /> : <MarcaIA costo />}
                {generandoIA ? "Generando…" : "Generar"}
              </Button>
            </div>
          </div>
          {avisoGenerar && <Aviso icono={false}>{avisoGenerar}</Aviso>}
        </div>
      </DialogContent>
    </Dialog>
  );
}

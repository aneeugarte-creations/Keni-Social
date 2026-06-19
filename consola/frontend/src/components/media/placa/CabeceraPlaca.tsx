/**
 * Cabecera del editor de placa inline: título "Imagen" + selector nativo de plantilla (quitar
 * plantilla / publicar solo la foto · elegir plantilla del estudio).
 */
import { Download, ImagePlus, LayoutTemplate, Slash } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface CabeceraPlacaProps {
  /** "Sin plantilla": publicar solo la foto cruda (sin la plantilla encima). */
  sinPlantilla: boolean;
  /** Alterna "sin plantilla" (icono de plantilla tachada). */
  onAlternarSinPlantilla: () => void;
  /** Abre la galería de plantillas del estudio (selector nativo en la cabecera). */
  onAbrirGaleria?: () => void;
  /** Descarga el render completo (foto + plantilla + texto) tal cual se ve, para postear a mano. */
  onDescargar?: () => void;
}

export function CabeceraPlaca({
  sinPlantilla,
  onAlternarSinPlantilla,
  onAbrirGaleria,
  onDescargar,
}: CabeceraPlacaProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-1.5 text-sm font-medium">
        <ImagePlus className="h-4 w-4 text-muted-foreground" />
        Imagen
        {sinPlantilla && <span className="font-normal text-muted-foreground">· solo foto</span>}
      </span>
      {/* Selector nativo de plantilla: quitar plantilla (publicar solo la foto) · elegir plantilla
          del estudio (galería por marca). Todo es 4:5, así que la plantilla la dicta la MARCA. */}
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant={sinPlantilla ? "secondary" : "outline"}
          size="icon"
          className="h-7 w-7"
          onClick={onAlternarSinPlantilla}
          title={
            sinPlantilla
              ? "Solo foto. Toca para restaurar"
              : "Quitar la plantilla"
          }
          aria-pressed={sinPlantilla}
        >
          <span className="relative inline-flex">
            <LayoutTemplate className="h-3.5 w-3.5" />
            <Slash className="absolute inset-0 h-3.5 w-3.5 text-destructive" />
          </span>
        </Button>
        {onAbrirGaleria && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={onAbrirGaleria}
            title="Elegir plantilla"
          >
            <LayoutTemplate className="h-3.5 w-3.5" />
          </Button>
        )}
        {/* Descarga el render completo (foto + plantilla + texto) tal cual se ve, para postear a
            mano donde Metricool no llega (p. ej. X). */}
        {onDescargar && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={onDescargar}
            title="Descargar imagen para postear"
          >
            <Download className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

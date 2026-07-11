/**
 * Cabecera del editor de placa inline: título "Imagen" + controles de plantilla (con plantilla ↔
 * solo foto · elegir plantilla del estudio) y descarga del render.
 *
 * Estilo minimal: iconos ghost sin caja, sutiles. El glifo del MODO refleja el estado actual
 * (plantilla puesta ↔ solo foto), sin tachado; el sufijo "· solo foto" del título lo reafirma.
 * La descarga (exportar) queda como acción tranquila a la derecha.
 */
import { Download, Image as ImageIcon, ImagePlus, LayoutGrid, LayoutTemplate } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

export interface CabeceraPlacaProps {
  /** "Sin plantilla": publicar solo la foto cruda (sin la plantilla encima). */
  sinPlantilla: boolean;
  /** Alterna entre "con plantilla" y "solo foto". */
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
      {/* Controles ghost sutiles: modo (el glifo refleja el estado) · elegir plantilla · descargar. */}
      <div className="flex items-center gap-0.5 text-muted-foreground">
        <Tooltip
          label={
            sinPlantilla
              ? "Solo foto. Toca para poner la plantilla"
              : "Con plantilla. Toca para publicar solo la foto"
          }
        >
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-foreground"
            onClick={onAlternarSinPlantilla}
            aria-pressed={sinPlantilla}
          >
            {sinPlantilla ? (
              <ImageIcon className="h-4 w-4" />
            ) : (
              <LayoutTemplate className="h-4 w-4" />
            )}
          </Button>
        </Tooltip>
        {onAbrirGaleria && (
          <Tooltip label="Elegir plantilla">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-muted-foreground hover:text-foreground"
              onClick={onAbrirGaleria}
            >
              <LayoutGrid className="h-4 w-4" />
            </Button>
          </Tooltip>
        )}
        {/* Descarga el render completo (foto + plantilla + texto) tal cual se ve, para postear a
            mano donde Metricool no llega (p. ej. X). */}
        {onDescargar && (
          <Tooltip label="Descargar imagen para postear">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-muted-foreground hover:text-foreground"
              onClick={onDescargar}
            >
              <Download className="h-4 w-4" />
            </Button>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

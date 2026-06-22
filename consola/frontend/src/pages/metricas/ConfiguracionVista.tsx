/**
 * Panel "Configurar vista" del dashboard de Métricas.
 *
 * Diálogo que controla la capa de PRESENTACIÓN (no los datos): qué secciones se
 * muestran. Todo se persiste en `vistaConfig` (localStorage), así que sobrevive a
 * recargas y lo serializan las vistas guardadas. "Restablecer" vuelve al estado por
 * defecto (todo visible, todas las redes, orden base de columnas).
 */
import { RotateCcw, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

import { GRUPOS_SECCIONES } from "./seccionesMeta";
import { useVistaConfig } from "./vistaConfig";

/** Bloque de visibilidad de secciones (checkbox por sección, agrupadas). */
function SeccionesConfig() {
  const secciones = useVistaConfig((s) => s.secciones);
  const setSeccionVisible = useVistaConfig((s) => s.setSeccionVisible);

  return (
    <div className="space-y-5">
      {GRUPOS_SECCIONES.map((grupo) => (
        <fieldset key={grupo.titulo} className="space-y-2">
          <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {grupo.titulo}
          </legend>
          <div className="space-y-2">
            {grupo.secciones.map((s) => {
              const visible = secciones[s.id] !== false;
              const id = `sec-${s.id}`;
              return (
                <div key={s.id} className="flex items-center gap-2">
                  <Checkbox
                    id={id}
                    checked={visible}
                    onCheckedChange={(v) => setSeccionVisible(s.id, v)}
                    aria-label={s.etiqueta}
                  />
                  <Label htmlFor={id} className="cursor-pointer font-normal">
                    {s.etiqueta}
                  </Label>
                </div>
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

/** Botón "Configurar vista" + diálogo. Se monta en la cabecera de Analíticas. */
export function ConfiguracionVista() {
  const reset = useVistaConfig((s) => s.reset);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
          <SlidersHorizontal className="h-4 w-4" />
          Configurar vista
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Configurar vista</DialogTitle>
          <DialogDescription>
            Elige qué secciones se muestran. Los cambios se guardan en este navegador.
          </DialogDescription>
        </DialogHeader>

        <SeccionesConfig />

        <div className="flex justify-end border-t pt-4">
          <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => reset()}>
            <RotateCcw className="h-4 w-4" />
            Restablecer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

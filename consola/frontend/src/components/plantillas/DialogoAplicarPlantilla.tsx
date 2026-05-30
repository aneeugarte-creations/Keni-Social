/**
 * Diálogo "Aplicar plantilla": rellena las variables (modo estructura) y compone el copy en
 * el servidor; en modo plano el copy ES el contenido tal cual. Reutilizado por el catálogo
 * (`/activos/plantillas`) y por el selector "Usar plantilla" del compositor de copy.
 *
 * Si recibe `onUsar`, ofrece "Usar en el copy" (inserta el resultado en el editor); siempre
 * permite "Copiar al portapapeles". React Query + toasts; texto es-MX.
 */
import { useMutation } from "@tanstack/react-query";
import { ClipboardCheck, Copy, Loader2, Sparkles, Wand2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import type { PlantillaContenido } from "@/types";

import { variablesAplicables } from "./util";

export function DialogoAplicarPlantilla({
  plantilla,
  abierto,
  onCerrar,
  onUsar,
}: {
  plantilla: PlantillaContenido;
  abierto: boolean;
  onCerrar: () => void;
  /** Si se pasa, ofrece insertar el copy en el editor (además de copiar). */
  onUsar?: (copy: string) => void;
}) {
  const [valores, setValores] = React.useState<Record<string, string>>({});
  const [copy, setCopy] = React.useState("");
  const [faltan, setFaltan] = React.useState<string[]>([]);
  const [copiado, setCopiado] = React.useState(false);

  const esPlano = plantilla.modo === "plano";
  const claves = esPlano ? [] : variablesAplicables(plantilla);

  React.useEffect(() => {
    if (abierto) {
      setValores({});
      // Modo plano: no hay nada que rellenar; el copy es el contenido directo.
      setCopy(esPlano ? plantilla.contenido : "");
      setFaltan([]);
      setCopiado(false);
    }
  }, [abierto, esPlano, plantilla.contenido]);

  const aplicar = useMutation({
    mutationFn: () => api.aplicarPlantillaContenido(plantilla.id, { valores }),
    onSuccess: (r) => {
      setCopy(r.copy);
      setFaltan(r.faltan);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo aplicar."),
  });

  async function copiar() {
    try {
      await navigator.clipboard.writeText(copy);
      setCopiado(true);
      toast.success("Copy copiado al portapapeles.");
    } catch {
      toast.error("No se pudo copiar al portapapeles.");
    }
  }

  function usar() {
    onUsar?.(copy);
    toast.success(`Plantilla aplicada: ${plantilla.nombre}`);
    onCerrar();
  }

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Aplicar: {plantilla.nombre}</DialogTitle>
          <DialogDescription>
            {esPlano
              ? "Plantilla de texto fijo: el copy es su contenido tal cual."
              : "Rellena las variables y genera el copy base. Las que dejes vacías quedarán como marcador para completar a mano."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {!esPlano &&
            claves.map((v) => (
              <div key={v.clave} className="space-y-1.5">
                <Label htmlFor={`ap-${v.clave}`}>{v.etiqueta || v.clave}</Label>
                <Input
                  id={`ap-${v.clave}`}
                  value={valores[v.clave] ?? ""}
                  onChange={(e) => setValores((prev) => ({ ...prev, [v.clave]: e.target.value }))}
                  placeholder={v.ejemplo || `{{${v.clave}}}`}
                />
              </div>
            ))}
          {!esPlano && claves.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Esta plantilla no tiene variables; el copy es su estructura tal cual.
            </p>
          )}

          {copy && (
            <div className="space-y-1.5">
              <Label>Copy</Label>
              <pre className="whitespace-pre-wrap rounded border bg-muted p-2 text-sm">{copy}</pre>
              {faltan.length > 0 && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Sin rellenar: {faltan.join(", ")}.
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="flex-wrap">
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
          {/* Modo estructura: hay que generar el copy antes de usarlo/copiarlo. */}
          {!esPlano && !copy ? (
            <Button onClick={() => aplicar.mutate()} disabled={aplicar.isPending}>
              {aplicar.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-1.5 h-4 w-4" />
              )}
              Generar copy
            </Button>
          ) : (
            <>
              <Button variant="secondary" onClick={copiar} disabled={!copy}>
                {copiado ? (
                  <ClipboardCheck className="mr-1.5 h-4 w-4" />
                ) : (
                  <Copy className="mr-1.5 h-4 w-4" />
                )}
                Copiar
              </Button>
              {onUsar && (
                <Button onClick={usar} disabled={!copy}>
                  <Wand2 className="mr-1.5 h-4 w-4" />
                  Usar en el copy
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

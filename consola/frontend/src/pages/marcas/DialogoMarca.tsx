import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, mensajeError } from "@/lib/api";

/** Una marca tal como la edita el formulario (catálogo). */
export interface MarcaEditable {
  id: string;
  etiqueta: string;
  /** id_metricas (en el dashboard es el campo `marca`). */
  id_metricas: string;
}

function invalidarMarcas(qc: ReturnType<typeof useQueryClient>) {
  // El dashboard de Marcas y el catálogo canónico que alimenta los selectores globales.
  void qc.invalidateQueries({ queryKey: ["marcas", "dashboard"] });
  void qc.invalidateQueries({ queryKey: ["marcas-catalogo"] });
}

/**
 * Diálogo de CREAR o EDITAR una marca del catálogo (la fuente única editable). Al crear,
 * `id` e `id_metricas` se derivan del nombre si se dejan vacíos. Al editar, el `id`
 * canónico es inmutable (referencia el contenido); solo cambian nombre e id_metricas, y
 * desde aquí mismo se puede BORRAR la marca (con una confirmación en línea).
 */
export function DialogoMarca({
  abierto,
  inicial,
  onCerrar,
}: {
  abierto: boolean;
  /** null = crear; con valor = editar esa marca. */
  inicial: MarcaEditable | null;
  onCerrar: () => void;
}) {
  const qc = useQueryClient();
  const esEditar = inicial !== null;
  const [etiqueta, setEtiqueta] = React.useState("");
  const [id, setId] = React.useState("");
  const [idMetricas, setIdMetricas] = React.useState("");
  const [confirmandoBorrado, setConfirmandoBorrado] = React.useState(false);

  React.useEffect(() => {
    if (abierto) {
      setEtiqueta(inicial?.etiqueta ?? "");
      setId(inicial?.id ?? "");
      setIdMetricas(inicial?.id_metricas ?? "");
      setConfirmandoBorrado(false);
    }
  }, [abierto, inicial]);

  const crear = useMutation({
    mutationFn: () =>
      api.crearMarca({ etiqueta, id: id.trim() || undefined, id_metricas: idMetricas.trim() || undefined }),
    onSuccess: (r) => {
      toast.success(r.mensaje || "Marca creada.");
      invalidarMarcas(qc);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const editar = useMutation({
    mutationFn: () => api.editarMarca(inicial!.id, { etiqueta, id_metricas: idMetricas.trim() }),
    onSuccess: (r) => {
      toast.success(r.mensaje || "Marca actualizada.");
      invalidarMarcas(qc);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.borrarMarca(inicial!.id),
    onSuccess: (r) => {
      toast.success(r?.mensaje ?? "Marca eliminada.");
      invalidarMarcas(qc);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const ocupado = crear.isPending || editar.isPending || borrar.isPending;
  const valido = etiqueta.trim() !== "";

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{esEditar ? "Editar marca" : "Añadir marca"}</DialogTitle>
          <DialogDescription>
            {esEditar
              ? "Cambia el nombre o el id de métricas. El id de la marca no se cambia."
              : "El id y el id de métricas se generan del nombre si los dejas vacíos."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="marca-etiqueta">Nombre</Label>
            <Input
              id="marca-etiqueta"
              value={etiqueta}
              onChange={(e) => setEtiqueta(e.target.value)}
              placeholder="Ej. Claro Sports"
              disabled={ocupado}
              autoFocus
            />
          </div>
          {esEditar ? (
            <div className="space-y-1">
              <Label>id</Label>
              <Input value={inicial?.id ?? ""} disabled />
            </div>
          ) : (
            <div className="space-y-1">
              <Label htmlFor="marca-id">id (opcional)</Label>
              <Input
                id="marca-id"
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="se genera del nombre (claro-sports)"
                disabled={ocupado}
              />
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="marca-id-metricas">id de métricas {esEditar ? "" : "(opcional)"}</Label>
            <Input
              id="marca-id-metricas"
              value={idMetricas}
              onChange={(e) => setIdMetricas(e.target.value)}
              placeholder="se genera del id (claro_sports)"
              disabled={ocupado}
            />
          </div>
        </div>

        {/* Pie: en edición, «Borrar marca» a la izquierda (con confirmación en línea). */}
        {confirmandoBorrado ? (
          <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/5 p-3">
            <p className="text-sm text-muted-foreground">
              ¿Borrar “{inicial?.etiqueta}”? Desaparece del catálogo y de los selectores. El
              contenido y las credenciales ya existentes no se borran (quedan inertes).
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmandoBorrado(false)} disabled={borrar.isPending}>
                Cancelar
              </Button>
              <Button variant="destructive" size="sm" onClick={() => borrar.mutate()} disabled={borrar.isPending}>
                {borrar.isPending ? "Borrando…" : "Sí, borrar"}
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-2 flex items-center justify-between gap-2">
            <div>
              {esEditar && (
                <Button
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setConfirmandoBorrado(true)}
                  disabled={ocupado}
                >
                  <Trash2 className="h-4 w-4" /> Borrar marca
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={onCerrar} disabled={ocupado}>
                Cancelar
              </Button>
              <Button onClick={() => (esEditar ? editar.mutate() : crear.mutate())} disabled={ocupado || !valido}>
                {crear.isPending || editar.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {esEditar ? "Guardar" : "Crear"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

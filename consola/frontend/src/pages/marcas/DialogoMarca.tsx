import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
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
 * canónico es inmutable (referencia el contenido); solo cambian nombre e id_metricas.
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

  React.useEffect(() => {
    if (abierto) {
      setEtiqueta(inicial?.etiqueta ?? "");
      setId(inicial?.id ?? "");
      setIdMetricas(inicial?.id_metricas ?? "");
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

  const guardando = crear.isPending || editar.isPending;
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
              disabled={guardando}
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
                disabled={guardando}
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
              disabled={guardando}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardando}>
            Cancelar
          </Button>
          <Button
            onClick={() => (esEditar ? editar.mutate() : crear.mutate())}
            disabled={guardando || !valido}
          >
            {guardando ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {esEditar ? "Guardar" : "Crear"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Diálogo de confirmación de borrado de una marca. */
export function DialogoBorrarMarca({
  marca,
  onCerrar,
}: {
  /** null = cerrado; con valor = confirmar borrado de esa marca. */
  marca: MarcaEditable | null;
  onCerrar: () => void;
}) {
  const qc = useQueryClient();
  const borrar = useMutation({
    mutationFn: () => api.borrarMarca(marca!.id),
    onSuccess: (r) => {
      toast.success(r?.mensaje ?? "Marca eliminada.");
      invalidarMarcas(qc);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={marca !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Borrar “{marca?.etiqueta}”</DialogTitle>
          <DialogDescription>
            La marca desaparecerá del catálogo y de todos los selectores. El contenido y las
            credenciales ya existentes no se borran (quedan inertes). ¿Continuar?
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={borrar.isPending}>
            Cancelar
          </Button>
          <Button variant="destructive" onClick={() => borrar.mutate()} disabled={borrar.isPending}>
            {borrar.isPending ? "Borrando…" : "Borrar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

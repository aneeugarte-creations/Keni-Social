import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Plus, Tag, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import type { Etiqueta } from "@/types";

import { CLASE_ETIQUETA_LABEL, CLAVE_ETIQUETAS } from "./lib";

/**
 * Gestión del CATÁLOGO de etiquetas editoriales TRANSVERSALES (ejes `campaña` y
 * `tipo`). Las líneas (`vertical`) y orígenes (`origen`) NO viven aquí: tienen sus
 * propios paneles arriba, con keywords/TTL/evergreen, así que este diálogo no los
 * duplica. Lee/escribe `/api/etiquetas`.
 */
export function DialogoEtiquetas({
  abierto,
  onCerrar,
  marcas,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: { id: string; nombre: string }[];
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["etiquetas", "transversales"],
    queryFn: ({ signal }) => api.etiquetas({}, signal),
    enabled: abierto,
  });
  const [nombre, setNombre] = React.useState("");
  const [clase, setClase] = React.useState("campania");
  const [marca, setMarca] = React.useState("");

  // Edición en línea de una etiqueta existente (renombrar / cambiar eje / marca).
  const [editandoId, setEditandoId] = React.useState<string | null>(null);
  const [editNombre, setEditNombre] = React.useState("");
  const [editClase, setEditClase] = React.useState("campania");
  const [editMarca, setEditMarca] = React.useState("");

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_ETIQUETAS });
    // El catálogo de etiquetas viaja también dentro de /api/publicaciones.
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
  };

  const empezarEdicion = (e: Etiqueta) => {
    setEditandoId(e.id);
    setEditNombre(e.nombre);
    setEditClase(e.clase);
    setEditMarca(e.marca || "");
  };
  const cancelarEdicion = () => setEditandoId(null);

  const crear = useMutation({
    mutationFn: () =>
      api.crearEtiqueta({ nombre: nombre.trim(), clase: clase as never, marca }),
    onSuccess: () => {
      invalidar();
      setNombre("");
      toast.success("Etiqueta creada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const actualizar = useMutation({
    mutationFn: (id: string) =>
      api.actualizarEtiqueta(id, {
        nombre: editNombre.trim(),
        clase: editClase as never,
        marca: editMarca,
      }),
    onSuccess: () => {
      invalidar();
      setEditandoId(null);
      toast.success("Etiqueta actualizada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.eliminarEtiqueta(id),
    onSuccess: () => {
      invalidar();
      toast.success("Etiqueta borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Solo los ejes transversales (campaña / tipo); líneas y orígenes se gestionan arriba.
  const etiquetas = (query.data?.etiquetas ?? []).filter(
    (e) => e.clase in CLASE_ETIQUETA_LABEL,
  );

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tag className="h-4 w-4" />
            Etiquetas editoriales
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Alta de etiqueta. */}
          <div className="grid grid-cols-[1fr_auto_auto_auto] items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="et-nombre">Nombre</Label>
              <Input
                id="et-nombre"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Ej. Mundial 2026"
                maxLength={60}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-clase">Eje</Label>
              <Select value={clase} onValueChange={setClase}>
                <SelectTrigger id="et-clase" aria-label="Eje" className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CLASE_ETIQUETA_LABEL).map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-marca">Marca</Label>
              <Select value={marca || "__global__"} onValueChange={(v) => setMarca(v === "__global__" ? "" : v)}>
                <SelectTrigger id="et-marca" aria-label="Marca" className="w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__global__">Global</SelectItem>
                  {marcas.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={() => crear.mutate()}
              disabled={nombre.trim().length === 0 || crear.isPending}
            >
              {crear.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Añadir
            </Button>
          </div>

          {/* Listado del catálogo. */}
          {query.isPending ? (
            <Skeleton className="h-24 w-full rounded-md" />
          ) : etiquetas.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aún no hay etiquetas. Crea la primera arriba.
            </p>
          ) : (
            <div className="space-y-1.5">
              {etiquetas.map((e) =>
                editandoId === e.id ? (
                  <div
                    key={e.id}
                    className="grid grid-cols-[1fr_auto_auto_auto_auto] items-end gap-2 rounded-md border border-border/60 px-2 py-1.5"
                  >
                    <div className="space-y-1.5">
                      <Label htmlFor={`et-edit-nombre-${e.id}`} className="sr-only">
                        Nombre
                      </Label>
                      <Input
                        id={`et-edit-nombre-${e.id}`}
                        value={editNombre}
                        onChange={(ev) => setEditNombre(ev.target.value)}
                        maxLength={60}
                      />
                    </div>
                    <Select value={editClase} onValueChange={setEditClase}>
                      <SelectTrigger aria-label="Eje" className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(CLASE_ETIQUETA_LABEL).map(([v, l]) => (
                          <SelectItem key={v} value={v}>
                            {l}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select
                      value={editMarca || "__global__"}
                      onValueChange={(v) => setEditMarca(v === "__global__" ? "" : v)}
                    >
                      <SelectTrigger aria-label="Marca" className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__global__">Global</SelectItem>
                        {marcas.map((m) => (
                          <SelectItem key={m.id} value={m.id}>
                            {m.nombre}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      size="icon"
                      aria-label={`Guardar etiqueta ${e.nombre}`}
                      className="h-9 w-9"
                      onClick={() => actualizar.mutate(e.id)}
                      disabled={editNombre.trim().length === 0 || actualizar.isPending}
                    >
                      {actualizar.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Cancelar edición"
                      className="h-9 w-9"
                      onClick={cancelarEdicion}
                      disabled={actualizar.isPending}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <FilaConAcciones
                    key={e.id}
                    como="div"
                    onPrimaria={() => empezarEdicion(e)}
                    etiquetaAcciones={`Acciones de la etiqueta ${e.nombre}`}
                    kebab="nunca"
                    realce
                    acciones={[
                      // "Editar" es la acción de click izquierdo (onPrimaria): no se duplica aquí.
                      {
                        etiqueta: "Borrar etiqueta",
                        icono: Trash2,
                        destructivo: true,
                        deshabilitado: borrar.isPending,
                        onClick: async () => {
                          if (
                            await confirmar({
                              mensaje: `¿Borrar la etiqueta "${e.nombre}"? Esta acción no se puede deshacer.`,
                              destructivo: true,
                              textoConfirmar: "Borrar",
                            })
                          ) {
                            borrar.mutate(e.id);
                          }
                        },
                      },
                    ]}
                    className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1.5 pr-10 text-sm transition-colors"
                  >
                    <Tag className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium">{e.nombre}</span>
                    <Badge variant="secondary" className="font-normal">
                      {CLASE_ETIQUETA_LABEL[e.clase] ?? e.clase}
                    </Badge>
                    <Badge variant="outline" className="font-normal">
                      {e.marca_nombre || "Global"}
                    </Badge>
                  </FilaConAcciones>
                ),
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

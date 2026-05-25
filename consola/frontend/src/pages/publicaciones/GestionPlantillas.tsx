/**
 * Diálogo de gestión (CRUD) de plantillas de post.
 *
 * Lista las plantillas guardadas y permite crear, editar y borrar. Cada
 * plantilla tiene nombre, marca y red opcionales, y un contenido reutilizable.
 * React Query + invalidación; toasts; modo claro/oscuro; texto es-MX.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { desdeMarca, desdeRed, marcaParam, redParam } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import type { MarcaDisponible, Plantilla, RedPublicacion } from "@/types";

import { CLAVE_PLANTILLAS } from "./plantillas";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Formulario de creación/edición de una plantilla (inline). */
function FormularioPlantilla({
  marcas,
  redes,
  plantilla,
  onCancelar,
  onListo,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  plantilla: Plantilla | null;
  onCancelar: () => void;
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState(plantilla?.nombre ?? "");
  const [marca, setMarca] = React.useState(desdeMarca(plantilla?.marca));
  const [red, setRed] = React.useState(desdeRed(plantilla?.red));
  const [contenido, setContenido] = React.useState(plantilla?.contenido ?? "");

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        nombre: nombre.trim(),
        marca: marcaParam(marca),
        red: redParam(red),
        contenido,
      };
      return plantilla
        ? api.actualizarPlantilla(plantilla.id, cuerpo)
        : api.crearPlantilla(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PLANTILLAS });
      toast.success(plantilla ? "Plantilla actualizada" : "Plantilla creada");
      onListo();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar =
    nombre.trim().length > 0 && contenido.trim().length > 0 && !guardar.isPending;

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5 sm:col-span-3">
          <Label htmlFor="plantilla-nombre">Nombre</Label>
          <Input
            id="plantilla-nombre"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Ej. Apertura noticia deportiva"
            maxLength={120}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="plantilla-marca">
            Marca <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <SelectorMarca
            id="plantilla-marca"
            marcas={marcas}
            valor={marca}
            onCambio={setMarca}
            ariaLabel="Marca"
            className="w-full"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="plantilla-red">
            Red <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <SelectorRed
            id="plantilla-red"
            redes={redes}
            valor={red}
            onCambio={setRed}
            etiquetaTodas="Cualquier red"
            ariaLabel="Red"
            className="w-full"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="plantilla-contenido">Contenido</Label>
        <Textarea
          id="plantilla-contenido"
          value={contenido}
          onChange={(e) => setContenido(e.target.value)}
          placeholder="Escribe aquí el copy reutilizable…"
          className="min-h-[8rem] font-mono text-sm"
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancelar} disabled={guardar.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          {plantilla ? "Guardar cambios" : "Crear plantilla"}
        </Button>
      </div>
    </div>
  );
}

/** Una fila de plantilla guardada con acciones de editar/borrar. */
function FilaPlantilla({
  plantilla,
  onEditar,
}: {
  plantilla: Plantilla;
  onEditar: (p: Plantilla) => void;
}) {
  const queryClient = useQueryClient();
  const borrar = useMutation({
    mutationFn: () => api.eliminarPlantilla(plantilla.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PLANTILLAS });
      toast.success(res?.mensaje ?? "Plantilla borrada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-border p-3">
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{plantilla.nombre}</span>
          {plantilla.marca && (
            <Badge variant="outline" className="font-normal">
              {plantilla.marca_nombre || plantilla.marca}
            </Badge>
          )}
          {plantilla.red && (
            <Badge variant="secondary" className="font-normal">
              {plantilla.red_nombre || plantilla.red}
            </Badge>
          )}
        </div>
        <p className="line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">
          {plantilla.contenido}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Editar plantilla"
          title="Editar"
          onClick={() => onEditar(plantilla)}
        >
          <Pencil className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Borrar plantilla"
          title="Borrar"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => borrar.mutate()}
          disabled={borrar.isPending}
        >
          {borrar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}

export function GestionPlantillas({
  abierto,
  onCerrar,
  marcas,
  redes,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const query = useQuery({
    queryKey: CLAVE_PLANTILLAS,
    queryFn: ({ signal }) => api.plantillas(signal),
    enabled: abierto,
  });

  // null = sin formulario; "nueva" = creando; objeto = editando esa plantilla.
  const [editando, setEditando] = React.useState<Plantilla | "nueva" | null>(null);

  React.useEffect(() => {
    if (!abierto) setEditando(null);
  }, [abierto]);

  const plantillas = query.data?.plantillas ?? [];

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Plantillas de post
          </DialogTitle>
          <DialogDescription>
            Guarda copys reutilizables para insertarlos rápido al componer una publicación.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {editando === "nueva" || editando ? (
            <FormularioPlantilla
              marcas={marcas}
              redes={redes}
              plantilla={editando === "nueva" ? null : editando}
              onCancelar={() => setEditando(null)}
              onListo={() => setEditando(null)}
            />
          ) : (
            <Button variant="outline" size="sm" onClick={() => setEditando("nueva")}>
              <Plus className="h-4 w-4" />
              Nueva plantilla
            </Button>
          )}

          {query.isPending ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando plantillas…</p>
          ) : query.isError ? (
            <p className="py-6 text-center text-sm text-destructive">{mensajeError(query.error)}</p>
          ) : plantillas.length === 0 ? (
            <p className="flex items-center justify-center gap-2 py-6 text-center text-sm text-muted-foreground">
              <X className="h-4 w-4" />
              Aún no hay plantillas. Crea la primera arriba.
            </p>
          ) : (
            <div className="space-y-2">
              {plantillas.map((p) => (
                <FilaPlantilla key={p.id} plantilla={p} onEditar={(pl) => setEditando(pl)} />
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

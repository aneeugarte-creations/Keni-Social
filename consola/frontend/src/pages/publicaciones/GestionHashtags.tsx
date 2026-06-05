/**
 * Diálogo de gestión (CRUD) de grupos de hashtags.
 *
 * Lista los grupos guardados y permite crear, editar y borrar. Cada grupo tiene
 * nombre, marca opcional y una lista de hashtags. React Query + invalidación;
 * toasts; modo claro/oscuro; texto es-MX.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Hash, Loader2, Plus, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { desdeMarca, marcaParam } from "@/components/comunes/selectores";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
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
import { api, mensajeError } from "@/lib/api";
import type { GrupoHashtags, MarcaDisponible } from "@/types";

import { CLAVE_HASHTAGS, parsearHashtags } from "./hashtags";

/** Formulario de creación/edición de un grupo (inline). */
function FormularioGrupo({
  marcas,
  grupo,
  onCancelar,
  onListo,
}: {
  marcas: MarcaDisponible[];
  grupo: GrupoHashtags | null;
  onCancelar: () => void;
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  // Al CREAR (sin grupo) arrancamos en la marca activa si es una opción válida;
  // al editar conservamos la marca del grupo.
  const marcaInicial =
    grupo?.marca ??
    (marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : undefined);
  const [nombre, setNombre] = React.useState(grupo?.nombre ?? "");
  const [marca, setMarca] = React.useState(desdeMarca(marcaInicial));
  const [texto, setTexto] = React.useState((grupo?.hashtags ?? []).join(" "));

  const hashtags = React.useMemo(() => parsearHashtags(texto), [texto]);

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        nombre: nombre.trim(),
        marca: marcaParam(marca),
        hashtags,
      };
      return grupo
        ? api.actualizarGrupoHashtags(grupo.id, cuerpo)
        : api.crearGrupoHashtags(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_HASHTAGS });
      toast.success(grupo ? "Grupo actualizado" : "Grupo creado");
      onListo();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar =
    nombre.trim().length > 0 && hashtags.length > 0 && !guardar.isPending;

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="grupo-nombre">Nombre</Label>
          <Input
            id="grupo-nombre"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Ej. Deportes"
            maxLength={80}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="grupo-marca">
            Marca <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <SelectorMarca
            id="grupo-marca"
            marcas={marcas}
            valor={marca}
            onCambio={setMarca}
            ariaLabel="Marca"
            className="w-full"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="grupo-hashtags">Hashtags</Label>
        <Textarea
          id="grupo-hashtags"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="#futbol #deportes #unotv — separa por espacios o comas"
          className="min-h-[5rem]"
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancelar} disabled={guardar.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          {grupo ? "Guardar cambios" : "Crear grupo"}
        </Button>
      </div>
    </div>
  );
}

/**
 * Una fila de grupo guardado. Click izquierdo sobre la fila = editar (acción
 * primaria); la única acción secundaria es BORRAR, que `FilaConAcciones` muestra
 * como un icono de papelera directo (sin kebab "⋮" ni menú).
 */
function FilaGrupo({
  grupo,
  onEditar,
}: {
  grupo: GrupoHashtags;
  onEditar: (g: GrupoHashtags) => void;
}) {
  const queryClient = useQueryClient();
  const borrar = useMutation({
    mutationFn: () => api.eliminarGrupoHashtags(grupo.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_HASHTAGS });
      toast.success(res?.mensaje ?? "Grupo borrado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Acción primaria = editar (click en la fila). Única secundaria = borrar, que se
  // pinta como icono de papelera directo (al ser una sola acción, sin kebab ni menú).
  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (await confirmar({ mensaje: `¿Borrar el grupo "${grupo.nombre}"?`, destructivo: true, textoConfirmar: "Borrar" }))
          borrar.mutate();
      },
      destructivo: true,
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      onPrimaria={() => onEditar(grupo)}
      acciones={acciones}
      etiquetaAcciones={`Acciones de "${grupo.nombre}"`}
      kebab="hover"
      className="rounded-md border border-border"
    >
      <div className="min-w-0 space-y-1.5 p-3 pr-10">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{grupo.nombre}</span>
          {grupo.marca && (
            <Badge variant="outline" className="font-normal">
              {grupo.marca_nombre || grupo.marca}
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {grupo.hashtags.map((h) => (
            <span key={h} className="text-xs text-muted-foreground">
              {h}
            </span>
          ))}
        </div>
      </div>
    </FilaConAcciones>
  );
}

export function GestionHashtags({
  abierto,
  onCerrar,
  marcas,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: MarcaDisponible[];
}) {
  const query = useQuery({
    queryKey: CLAVE_HASHTAGS,
    queryFn: ({ signal }) => api.hashtags(signal),
    enabled: abierto,
  });

  // null = sin formulario; "nuevo" = creando; objeto = editando ese grupo.
  const [editando, setEditando] = React.useState<GrupoHashtags | "nuevo" | null>(null);

  // Al cerrar, reseteamos el formulario.
  React.useEffect(() => {
    if (!abierto) setEditando(null);
  }, [abierto]);

  const grupos = query.data?.grupos ?? [];

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Hash className="h-5 w-5" />
            Grupos de hashtags
          </DialogTitle>
          <DialogDescription>
            Guarda conjuntos de hashtags reutilizables para insertarlos al componer.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {editando === "nuevo" || editando ? (
            <FormularioGrupo
              marcas={marcas}
              grupo={editando === "nuevo" ? null : editando}
              onCancelar={() => setEditando(null)}
              onListo={() => setEditando(null)}
            />
          ) : (
            <Button variant="outline" size="sm" onClick={() => setEditando("nuevo")}>
              <Plus className="h-4 w-4" />
              Nuevo grupo
            </Button>
          )}

          {query.isPending ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando grupos…</p>
          ) : query.isError ? (
            <p className="py-6 text-center text-sm text-destructive">
              {mensajeError(query.error)}
            </p>
          ) : grupos.length === 0 ? (
            <p className="flex items-center justify-center gap-2 py-6 text-center text-sm text-muted-foreground">
              <X className="h-4 w-4" />
              Aún no hay grupos. Crea el primero arriba.
            </p>
          ) : (
            <div className="space-y-2">
              {grupos.map((g) => (
                <FilaGrupo key={g.id} grupo={g} onEditar={(grupo) => setEditando(grupo)} />
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

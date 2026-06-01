/**
 * Diálogo de gestión (CRUD) de franjas de la cola de publicación.
 *
 * Cada franja es un hueco recurrente (día de semana + hora) opcionalmente
 * acotado a una marca/red. "Añadir a la cola" asigna la publicación al próximo
 * hueco libre. Lista legible (p. ej. "Lun 09:00 · X · UnoTV"). React Query +
 * invalidación; toasts; modo claro/oscuro; texto es-MX.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Clock, Loader2, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { MARCA_TODAS, marcaParam, RED_TODAS, redParam } from "@/components/comunes/selectores";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import type { Franja, MarcaDisponible, RedPublicacion } from "@/types";

import { CLAVE_FRANJAS, DIAS_SEMANA, nombreDiaCorto } from "./franjas";
import { EtiquetaRed } from "./insignias";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Formulario para añadir una franja nueva. */
function FormularioFranja({
  marcas,
  redes,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const queryClient = useQueryClient();
  const [dia, setDia] = React.useState("0");
  const [hora, setHora] = React.useState("09:00");
  const [marca, setMarca] = React.useState(MARCA_TODAS);
  const [red, setRed] = React.useState(RED_TODAS);

  const crear = useMutation({
    mutationFn: () =>
      api.crearFranja({
        dia_semana: Number(dia),
        hora,
        marca: marcaParam(marca),
        red: redParam(red),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_FRANJAS });
      toast.success("Franja añadida");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = !!hora && !crear.isPending;

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="franja-dia">Día</Label>
          <Select value={dia} onValueChange={setDia}>
            <SelectTrigger id="franja-dia">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DIAS_SEMANA.map((nombre, i) => (
                <SelectItem key={i} value={String(i)}>
                  {nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="franja-hora">Hora</Label>
          <Input
            id="franja-hora"
            type="time"
            value={hora}
            onChange={(e) => setHora(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="franja-marca">
            Marca <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <SelectorMarca
            id="franja-marca"
            marcas={marcas}
            valor={marca}
            onCambio={setMarca}
            ariaLabel="Marca"
            className="w-full"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="franja-red">
            Red <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <SelectorRed
            id="franja-red"
            redes={redes}
            valor={red}
            onCambio={setRed}
            ariaLabel="Red"
            className="w-full"
          />
        </div>
      </div>
      <div className="flex justify-end">
        <Button size="sm" onClick={() => crear.mutate()} disabled={!puedeCrear}>
          {crear.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Añadir franja
        </Button>
      </div>
    </div>
  );
}

/**
 * Una fila de franja. Las franjas no se editan (se recrean), así que la fila no
 * tiene acción primaria: borrar vive en el menú contextual (click derecho) y en
 * el kebab "⋮", con confirmación.
 */
function FilaFranja({ franja }: { franja: Franja }) {
  const queryClient = useQueryClient();
  const borrar = useMutation({
    mutationFn: () => api.eliminarFranja(franja.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_FRANJAS });
      toast.success(res?.mensaje ?? "Franja borrada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const etiquetaFranja = `${nombreDiaCorto(franja.dia_semana)} ${franja.hora}`;

  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: () => {
        if (window.confirm(`¿Borrar la franja "${etiquetaFranja}"?`)) borrar.mutate();
      },
      destructivo: true,
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      acciones={acciones}
      etiquetaAcciones={`Acciones de la franja "${etiquetaFranja}"`}
      kebab="hover"
      className="rounded-md border border-border"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 pr-10 text-sm">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <Clock className="h-3.5 w-3.5 text-muted-foreground" />
          {nombreDiaCorto(franja.dia_semana)} {franja.hora}
        </span>
        {franja.red && (
          <>
            <span className="text-muted-foreground">·</span>
            <EtiquetaRed red={franja.red} nombre={franja.red_nombre} className="text-xs" />
          </>
        )}
        {franja.marca && (
          <>
            <span className="text-muted-foreground">·</span>
            <Badge variant="outline" className="font-normal">
              {franja.marca_nombre || franja.marca}
            </Badge>
          </>
        )}
      </div>
    </FilaConAcciones>
  );
}

export function GestionFranjas({
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
    queryKey: CLAVE_FRANJAS,
    queryFn: ({ signal }) => api.franjas(signal),
    enabled: abierto,
  });

  const franjas = React.useMemo(() => {
    const lista = [...(query.data?.franjas ?? [])];
    lista.sort((a, b) =>
      a.dia_semana !== b.dia_semana
        ? a.dia_semana - b.dia_semana
        : a.hora.localeCompare(b.hora),
    );
    return lista;
  }, [query.data]);

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="h-5 w-5" />
            Franjas de la cola
          </DialogTitle>
          <DialogDescription>
            Define huecos recurrentes (día + hora). Al añadir una publicación a la cola se
            asigna al próximo hueco libre.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <FormularioFranja marcas={marcas} redes={redes} />

          {query.isPending ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando franjas…</p>
          ) : query.isError ? (
            <p className="py-6 text-center text-sm text-destructive">
              {mensajeError(query.error)}
            </p>
          ) : franjas.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Aún no hay franjas. Añade la primera arriba para poder encolar.
            </p>
          ) : (
            <div className="space-y-2">
              {franjas.map((f) => (
                <FilaFranja key={f.id} franja={f} />
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

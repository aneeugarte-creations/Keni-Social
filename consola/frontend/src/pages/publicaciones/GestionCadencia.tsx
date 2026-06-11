/**
 * Gestión (CRUD) de cadencias por red, como SECCIÓN INLINE del panel de ajustes de Programación
 * (capa base, colapsable), no un diálogo: los ajustes no se esconden tras un botón.
 *
 * Una cadencia es el scheduling por margen mínimo entre publicaciones de una
 * red, dentro de una ventana horaria (hora_inicio–hora_fin) y unos días,
 * opcionalmente acotada a una marca/red. Reemplaza a las franjas: en vez de
 * huecos recurrentes fijos, define cada cuántos minutos puede salir un post.
 *
 * UPSERT por (marca, red): guardar con la misma marca+red sobrescribe la
 * cadencia existente. React Query + invalidación; toasts; modo claro/oscuro;
 * texto es-MX.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Loader2, Save, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { MARCA_TODAS, marcaParam, RED_TODAS, redParam } from "@/components/comunes/selectores";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, mensajeError } from "@/lib/api";
import { horaCdmxAUtc, horaUtcACdmx } from "@/lib/fecha";
import type { Cadencia, MarcaDisponible, RedPublicacion } from "@/types";

import { DIAS_SEMANA_CORTO, nombreDiaCorto } from "./franjas";
import { EtiquetaRed } from "./insignias";

/** Clave de React Query para las cadencias. */
const CLAVE_CADENCIAS = ["cadencias"] as const;

/** Resumen legible de los días de una cadencia (p. ej. "Lun, Mié, Vie"). */
function resumenDias(dias: number[]): string {
  if (dias.length === 0) return "sin días";
  if (dias.length === 7) return "todos los días";
  return [...dias]
    .sort((a, b) => a - b)
    .map((d) => nombreDiaCorto(d))
    .join(", ");
}

/** Formulario para crear o actualizar (UPSERT por marca+red) una cadencia. */
function FormularioCadencia({
  marcas,
  redes,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  // Marca de la cadencia = switch global (si es una marca válida del catálogo);
  // si no, todas/sin marca. Es opcional: la cadencia puede ser global.
  const marca =
    marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : MARCA_TODAS;
  const [red, setRed] = React.useState(RED_TODAS);
  const [margen, setMargen] = React.useState("60");
  const [horaInicio, setHoraInicio] = React.useState("09:00");
  const [horaFin, setHoraFin] = React.useState("21:00");
  const [dias, setDias] = React.useState<number[]>([0, 1, 2, 3, 4]);
  const [activo, setActivo] = React.useState(true);

  function alternarDia(dia: number) {
    setDias((prev) =>
      prev.includes(dia) ? prev.filter((d) => d !== dia) : [...prev, dia],
    );
  }

  const margenNum = Number(margen);
  const margenValido = Number.isFinite(margenNum) && margenNum >= 1;

  const guardar = useMutation({
    mutationFn: () =>
      api.guardarCadencia({
        marca: marcaParam(marca),
        red: redParam(red),
        margen_min: margenNum,
        // El equipo escribe hora CDMX; el backend almacena UTC (instantes naive-UTC).
        hora_inicio: horaCdmxAUtc(horaInicio),
        hora_fin: horaCdmxAUtc(horaFin),
        dias: [...dias].sort((a, b) => a - b),
        activo,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_CADENCIAS });
      toast.success("Cadencia guardada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar =
    margenValido && !!horaInicio && !!horaFin && dias.length > 0 && !guardar.isPending;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="cadencia-red">
            Red <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <SelectorRed
            id="cadencia-red"
            redes={redes}
            valor={red}
            onCambio={setRed}
            ariaLabel="Red"
            className="w-full"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cadencia-margen">Margen entre posts (min)</Label>
          <Input
            id="cadencia-margen"
            type="number"
            min={1}
            value={margen}
            onChange={(e) => setMargen(e.target.value)}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="cadencia-inicio">Desde (hora CDMX)</Label>
            <Input
              id="cadencia-inicio"
              type="time"
              value={horaInicio}
              onChange={(e) => setHoraInicio(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cadencia-fin">Hasta (hora CDMX)</Label>
            <Input
              id="cadencia-fin"
              type="time"
              value={horaFin}
              onChange={(e) => setHoraFin(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Días</Label>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {DIAS_SEMANA_CORTO.map((nombre, i) => (
            <label
              key={i}
              className="flex cursor-pointer items-center gap-1.5 text-sm"
            >
              <Checkbox
                checked={dias.includes(i)}
                onCheckedChange={() => alternarDia(i)}
                aria-label={nombre}
              />
              {nombre}
            </label>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Switch
            id="cadencia-activo"
            checked={activo}
            onCheckedChange={setActivo}
            aria-label="Cadencia activa"
          />
          <Label htmlFor="cadencia-activo" className="cursor-pointer">
            Activa
          </Label>
        </div>
        <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Guardar
        </Button>
      </div>
    </div>
  );
}

/** Una fila de cadencia. Borrar vive en el menú contextual y el kebab, con confirmación. */
function FilaCadencia({ cadencia }: { cadencia: Cadencia }) {
  const queryClient = useQueryClient();
  const borrar = useMutation({
    mutationFn: () => api.eliminarCadencia(cadencia.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_CADENCIAS });
      toast.success(res?.mensaje ?? "Cadencia borrada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const etiquetaCadencia = `${cadencia.red_nombre || cadencia.red || "Todas"} · cada ${cadencia.margen_min} min`;

  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Borrar la cadencia "${etiquetaCadencia}"?`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        )
          borrar.mutate();
      },
      destructivo: true,
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      acciones={acciones}
      etiquetaAcciones={`Acciones de la cadencia "${etiquetaCadencia}"`}
      kebab="hover"
      className="rounded-md border border-border"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 pr-10 text-sm">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <Clock className="h-3.5 w-3.5 text-muted-foreground" />
          cada {cadencia.margen_min} min
        </span>
        <span className="text-muted-foreground">·</span>
        <span>
          {horaUtcACdmx(cadencia.hora_inicio)}–{horaUtcACdmx(cadencia.hora_fin)}
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">{resumenDias(cadencia.dias)}</span>
        {cadencia.red && (
          <>
            <span className="text-muted-foreground">·</span>
            <EtiquetaRed red={cadencia.red} nombre={cadencia.red_nombre} className="text-xs" />
          </>
        )}
        {cadencia.marca && (
          <>
            <span className="text-muted-foreground">·</span>
            <Badge variant="outline" className="font-normal">
              {cadencia.marca_nombre || cadencia.marca}
            </Badge>
          </>
        )}
        {!cadencia.activo && (
          <>
            <span className="text-muted-foreground">·</span>
            <Badge variant="outline" className="font-normal text-muted-foreground">
              Inactiva
            </Badge>
          </>
        )}
      </div>
    </FilaConAcciones>
  );
}

export function PanelCadencia({
  marcas,
  redes,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  // Sin gate `enabled`: la sección colapsable solo monta su contenido al desplegarse, así que la
  // query arranca justo entonces.
  const query = useQuery({
    queryKey: CLAVE_CADENCIAS,
    queryFn: ({ signal }) => api.cadencias(signal),
  });

  const cadencias = React.useMemo(() => {
    const lista = [...(query.data?.cadencias ?? [])];
    lista.sort(
      (a, b) =>
        a.marca_nombre.localeCompare(b.marca_nombre) ||
        a.red_nombre.localeCompare(b.red_nombre),
    );
    return lista;
  }, [query.data]);

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Cada cuántos minutos puede salir un post por red, dentro de una ventana horaria y unos
        días. Guardar con la misma marca y red sobrescribe la cadencia.
      </p>
      <FormularioCadencia marcas={marcas} redes={redes} />

      {query.isPending ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando cadencias…</p>
      ) : query.isError ? (
        <p className="py-6 text-center text-sm text-destructive">{mensajeError(query.error)}</p>
      ) : cadencias.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          Aún no hay cadencias. Define la primera arriba.
        </p>
      ) : (
        <div className="space-y-2">
          {cadencias.map((c) => (
            <FilaCadencia key={c.id} cadencia={c} />
          ))}
        </div>
      )}
    </div>
  );
}

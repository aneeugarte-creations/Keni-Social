// Diálogos de FRANJAS (de la semana y plantilla global). Partido de pages/Rota.tsx.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  CuerpoCrearFranjaSemana,
  FranjaSemana,
  PlantillaFranja,
} from "@/types";

// --- Dialog "Configurar franjas" (solo admin) -------------------------------

/** CUERPO «Esta semana» del diálogo Franjas (sin su propio Dialog: lo envuelve `DialogFranjas`). */
function CuerpoFranjasSemana({
  lunes,
  onCerrar,
}: {
  lunes: string;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const claveLista = ["rota", "franjas", lunes, marcaActiva] as const;
  const q = useQuery({
    queryKey: claveLista,
    queryFn: ({ signal }) =>
      api.listarFranjasSemana(lunes, marcaActiva ?? undefined, signal),
  });
  const franjas = (q.data?.franjas ?? [])
    .slice()
    .sort((a, b) => a.orden - b.orden);

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: claveLista });
    void queryClient.invalidateQueries({ queryKey: ["rota", "turnos"] });
  };

  const crear = useMutation({
    // GRID POR MARCA: crear franja exige marca concreta; en "Todas" el backend responde 400.
    mutationFn: (cuerpo: CuerpoCrearFranjaSemana) =>
      api.crearFranjaSemana(lunes, cuerpo, marcaActiva ?? undefined),
    onSuccess: () => {
      invalidar();
      toast.success("Franja añadida.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <>
      <p className="text-xs text-muted-foreground">
        Las franjas SOLO de la semana del {lunes} (puntual). «Descanso» = turno
        no-laboral.
      </p>
      {q.isPending ? (
        <Skeleton className="h-32 w-full rounded-md" />
      ) : (
        <div className="space-y-2">
          {franjas.map((f) => (
            <FilaFranjaSemana key={f.id} franja={f} onCambio={invalidar} />
          ))}
          <FormCrearFranjaSemana
            cargando={crear.isPending}
            onCrear={(cuerpo) => crear.mutate(cuerpo)}
          />
        </div>
      )}
      <DialogFooter>
        <Button variant="outline" onClick={onCerrar}>
          Cerrar
        </Button>
      </DialogFooter>
    </>
  );
}

export function FilaFranjaSemana({
  franja,
  onCambio,
}: {
  franja: FranjaSemana;
  onCambio: () => void;
}) {
  const [nombre, setNombre] = React.useState(franja.nombre);
  const [inicio, setInicio] = React.useState(franja.inicio);
  const [fin, setFin] = React.useState(franja.fin);
  const [orden, setOrden] = React.useState(String(franja.orden));

  const actualizar = useMutation({
    mutationFn: () =>
      api.actualizarFranjaSemana(franja.id, {
        nombre: nombre !== franja.nombre ? nombre : undefined,
        inicio: inicio !== franja.inicio ? inicio : undefined,
        fin: fin !== franja.fin ? fin : undefined,
        orden:
          Number.parseInt(orden, 10) !== franja.orden
            ? Number.parseInt(orden, 10)
            : undefined,
      }),
    onSuccess: () => {
      toast.success("Franja actualizada.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: (forzar: boolean) =>
      api.borrarFranjaSemana(franja.id, { forzar }),
    onSuccess: (res) => {
      const sufijo =
        res.turnos_borrados && res.turnos_borrados > 0
          ? ` (${res.turnos_borrados} turnos también)`
          : "";
      toast.success(`Franja borrada${sufijo}.`);
      onCambio();
    },
    onError: async (e) => {
      if (e instanceof ApiError && e.status === 409) {
        const asociados =
          (e.cuerpo?.turnos_asociados as number | undefined) ?? 0;
        if (
          await confirmar({
            mensaje: `Tiene ${asociados} turnos asociados. ¿Borrar también esos turnos?`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        ) {
          borrar.mutate(true);
        }
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const cambiada =
    nombre !== franja.nombre ||
    inicio !== franja.inicio ||
    fin !== franja.fin ||
    Number.parseInt(orden, 10) !== franja.orden;

  return (
    <div
      className={cn(
        "flex flex-wrap items-end gap-2 rounded border px-2 py-2",
        franja.es_descanso && "bg-muted/40",
      )}
    >
      <div className="flex-1 min-w-32">
        <Label className="text-xs text-muted-foreground">Nombre</Label>
        <Input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          className="h-8"
          disabled={franja.es_descanso}
          title={
            franja.es_descanso
              ? "La franja de descanso no se renombra (borra y crea otra)"
              : ""
          }
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Inicio</Label>
        <Input
          value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          placeholder="HH:MM"
          className="h-8"
          disabled={franja.es_descanso}
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Fin</Label>
        <Input
          value={fin}
          onChange={(e) => setFin(e.target.value)}
          placeholder="HH:MM"
          className="h-8"
          disabled={franja.es_descanso}
        />
      </div>
      <div className="w-20">
        <Label className="text-xs text-muted-foreground">Orden</Label>
        <Input
          value={orden}
          onChange={(e) => setOrden(e.target.value)}
          className="h-8"
        />
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={() => actualizar.mutate()}
        disabled={!cambiada || actualizar.isPending}
      >
        Guardar
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="text-destructive"
        onClick={() => borrar.mutate(false)}
        disabled={borrar.isPending}
      >
        Borrar
      </Button>
    </div>
  );
}

export function FormCrearFranjaSemana({
  cargando,
  onCrear,
}: {
  cargando: boolean;
  onCrear: (cuerpo: CuerpoCrearFranjaSemana) => void;
}) {
  const [nombre, setNombre] = React.useState("");
  const [inicio, setInicio] = React.useState("17:00");
  const [fin, setFin] = React.useState("01:00");
  const [orden, setOrden] = React.useState("2");
  const [esDescanso, setEsDescanso] = React.useState(false);

  const submit = () => {
    if (!nombre.trim()) {
      toast.error("Indica un nombre.");
      return;
    }
    onCrear({
      nombre: nombre.trim(),
      inicio,
      fin,
      orden: Number.parseInt(orden, 10) || 0,
      es_descanso: esDescanso,
    });
    setNombre("");
  };

  return (
    <div className="flex flex-wrap items-end gap-2 rounded border border-dashed px-2 py-2">
      <div className="flex-1 min-w-32">
        <Label className="text-xs text-muted-foreground">Añadir franja</Label>
        <Input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Cobertura nocturna"
          className="h-8"
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Inicio</Label>
        <Input
          value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          className="h-8"
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Fin</Label>
        <Input
          value={fin}
          onChange={(e) => setFin(e.target.value)}
          className="h-8"
        />
      </div>
      <div className="w-20">
        <Label className="text-xs text-muted-foreground">Orden</Label>
        <Input
          value={orden}
          onChange={(e) => setOrden(e.target.value)}
          className="h-8"
        />
      </div>
      <label className="flex items-center gap-1 text-xs">
        <input
          type="checkbox"
          checked={esDescanso}
          onChange={(e) => setEsDescanso(e.target.checked)}
        />
        Descanso
      </label>
      <Button size="sm" onClick={submit} disabled={cargando || !nombre.trim()}>
        <Plus className="h-4 w-4" /> Añadir
      </Button>
    </div>
  );
}

/** CUERPO «Plantilla por defecto» del diálogo Franjas (sin su propio Dialog).
 *
 * La plantilla es una LISTA flexible de franjas (igual de extensible que las de la semana): el
 * equipo puede definir 2, 3 o N franjas — p. ej. añadir «Nocturna». Es el molde del que parten
 * las semanas NUEVAS; «Descanso» la añade siempre la siembra, así que no se edita aquí. Se
 * guarda toda la lista de una vez (PATCH que reemplaza la plantilla). */
function CuerpoPlantillaFranjas({ onCerrar }: { onCerrar: () => void }) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "config", "franjas", marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.obtenerConfigFranjas(marcaActiva ?? undefined, signal),
  });
  const inicial = q.data?.franjas;
  const [filas, setFilas] = React.useState<PlantillaFranja[]>([]);

  React.useEffect(() => {
    if (inicial) setFilas(inicial.map((f) => ({ ...f })));
  }, [inicial]);

  const editar = (i: number, campo: keyof PlantillaFranja, valor: string) =>
    setFilas((prev) =>
      prev.map((f, j) => (j === i ? { ...f, [campo]: valor } : f)),
    );
  const quitar = (i: number) =>
    setFilas((prev) => prev.filter((_, j) => j !== i));
  const añadir = () =>
    setFilas((prev) => [...prev, { nombre: "", inicio: "00:00", fin: "08:00" }]);

  const guardar = useMutation({
    // GRID POR MARCA: la plantilla es por marca; en "Todas" el backend responde 400 accionable.
    mutationFn: () =>
      api.guardarConfigFranjas(
        {
          franjas: filas.map((f) => ({
            nombre: f.nombre.trim(),
            inicio: f.inicio.trim(),
            fin: f.fin.trim(),
          })),
        },
        marcaActiva ?? undefined,
      ),
    onSuccess: () => {
      toast.success("Plantilla de franjas guardada.");
      void queryClient.invalidateQueries({ queryKey: ["rota"] });
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const completas = filas.every(
    (f) => f.nombre.trim() && f.inicio.trim() && f.fin.trim(),
  );
  const sinCambios =
    !!inicial && JSON.stringify(filas) === JSON.stringify(inicial);
  const puedeGuardar = filas.length > 0 && completas && !sinCambios;

  return (
    <>
      <p className="text-xs text-muted-foreground">
        El MOLDE del que parten las semanas nuevas: estas franjas se crean en cada
        semana nueva. Puedes añadir las que quieras (p. ej. «Nocturna»). No
        reescribe las franjas que una semana ya tiene; «Descanso» se añade sola.
      </p>
      {q.isPending ? (
        <Skeleton className="h-32 w-full rounded-md" />
      ) : q.isError ? (
        <BloqueError
          titulo="No se pudo cargar la plantilla"
          mensaje={mensajeError(q.error)}
          onReintentar={() => void q.refetch()}
          cargando={q.isFetching}
        />
      ) : (
        <div className="space-y-2">
          {filas.map((f, i) => (
            <div
              // Índice como key: la lista es local y se reordena sólo al añadir/quitar al final.
              key={i}
              className="flex flex-wrap items-end gap-2 rounded border px-2 py-2"
            >
              <div className="min-w-32 flex-1">
                <Label className="text-xs text-muted-foreground">Nombre</Label>
                <Input
                  value={f.nombre}
                  onChange={(e) => editar(i, "nombre", e.target.value)}
                  placeholder="Mañana"
                  className="h-8"
                />
              </div>
              <div className="w-24">
                <Label className="text-xs text-muted-foreground">Inicio</Label>
                <Input
                  value={f.inicio}
                  onChange={(e) => editar(i, "inicio", e.target.value)}
                  placeholder="HH:MM"
                  className="h-8"
                />
              </div>
              <div className="w-24">
                <Label className="text-xs text-muted-foreground">Fin</Label>
                <Input
                  value={f.fin}
                  onChange={(e) => editar(i, "fin", e.target.value)}
                  placeholder="HH:MM"
                  className="h-8"
                />
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                onClick={() => quitar(i)}
                disabled={filas.length <= 1}
                title={
                  filas.length <= 1
                    ? "La plantilla necesita al menos una franja"
                    : ""
                }
              >
                Quitar
              </Button>
            </div>
          ))}
          <Button
            size="sm"
            variant="outline"
            className="w-full border-dashed"
            onClick={añadir}
          >
            <Plus className="h-4 w-4" /> Añadir franja
          </Button>
          <p className="text-xs text-muted-foreground">
            Horas en formato HH:MM (24:00 = medianoche del día siguiente). Lo que
            cae fuera de toda franja se asigna a «descanso».
          </p>
        </div>
      )}
      <DialogFooter>
        <Button variant="ghost" onClick={onCerrar}>
          Cancelar
        </Button>
        <Button
          onClick={() => guardar.mutate()}
          disabled={!puedeGuardar || guardar.isPending}
        >
          {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar
        </Button>
      </DialogFooter>
    </>
  );
}

/**
 * Diálogo «Franjas» UNIFICADO: una sola entrada (antes «Configurar franjas» + «Plantilla de
 * franjas», dos items que se confundían) con dos pestañas claras:
 *  - «Esta semana»: las franjas SOLO de la semana en vista (puntual).
 *  - «Plantilla por defecto»: la lista flexible de franjas (2, 3 o N) del que parten las
 *    semanas nuevas; se puede añadir «Nocturna» u otras.
 */
export function DialogFranjas({
  lunes,
  onCerrar,
}: {
  lunes: string;
  onCerrar: () => void;
}) {
  const [tab, setTab] = React.useState<"semana" | "plantilla">("semana");
  return (
    <Dialog open onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="gap-3 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Franjas</DialogTitle>
        </DialogHeader>
        {/* Segmentado (píldora blanca sobre pista gris), como el resto de toggles del producto. */}
        <div className="inline-flex w-fit rounded-md border border-border bg-muted p-0.5">
          {(
            [
              ["semana", "Esta semana"],
              ["plantilla", "Plantilla por defecto"],
            ] as const
          ).map(([clave, etiqueta]) => (
            <button
              key={clave}
              type="button"
              onClick={() => setTab(clave)}
              className={cn(
                "rounded-[5px] px-3 py-1 text-sm transition-colors",
                tab === clave
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {etiqueta}
            </button>
          ))}
        </div>
        {tab === "semana" ? (
          <CuerpoFranjasSemana lunes={lunes} onCerrar={onCerrar} />
        ) : (
          <CuerpoPlantillaFranjas onCerrar={onCerrar} />
        )}
      </DialogContent>
    </Dialog>
  );
}

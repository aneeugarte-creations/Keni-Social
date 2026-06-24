// Diálogos de FRANJAS (de la semana y plantilla global). Partido de pages/Rota.tsx.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Users } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  CuerpoCrearFranjaSemana,
  CuerpoGuardarConfigFranjas,
  FranjaSemana,
  PlantillaFranja,
} from "@/types";

// --- Dialog "Configurar franjas" (solo admin) -------------------------------

/** CUERPO «Esta semana» del diálogo Franjas (sin su propio Dialog: lo envuelve `DialogFranjas`). */
function CuerpoFranjasSemana({
  lunes,
  onCerrar,
  onAsignar,
}: {
  lunes: string;
  onCerrar: () => void;
  /** Atajo a «Asignar turnos» (poner quién trabaja cada franja). Oculto si no se pasa. */
  onAsignar?: () => void;
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
          {onAsignar && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed bg-muted/30 px-3 py-2">
              <p className="text-xs text-muted-foreground">
                ¿Quién trabaja cada franja? Asigna las personas a sus turnos.
              </p>
              <Button variant="outline" size="sm" onClick={onAsignar}>
                <Users className="h-4 w-4" /> Asignar personas
              </Button>
            </div>
          )}
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
  const ordenNum = Number.parseInt(orden, 10);
  const ordenValido = Number.isFinite(ordenNum);

  const actualizar = useMutation({
    mutationFn: () =>
      api.actualizarFranjaSemana(franja.id, {
        nombre: nombre !== franja.nombre ? nombre : undefined,
        inicio: inicio !== franja.inicio ? inicio : undefined,
        fin: fin !== franja.fin ? fin : undefined,
        orden: ordenNum !== franja.orden ? ordenNum : undefined,
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
    ordenNum !== franja.orden;

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
          aria-invalid={!ordenValido}
        />
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={() => actualizar.mutate()}
        disabled={!cambiada || !ordenValido || actualizar.isPending}
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
/** Fila de la plantilla con `_id` estable local (no se envía al backend), para usar como `key`. */
type FilaPlantilla = PlantillaFranja & { _id: string };

function CuerpoPlantillaFranjas({ onCerrar }: { onCerrar: () => void }) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "config", "franjas", marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.obtenerConfigFranjas(marcaActiva ?? undefined, signal),
  });
  const inicial = q.data?.franjas;
  // `_id` estable por fila para usarlo como `key`: sobrevive a quitar/añadir en cualquier posición.
  const idFila = React.useRef(0);
  const [filas, setFilas] = React.useState<FilaPlantilla[]>([]);

  React.useEffect(() => {
    if (inicial)
      setFilas(inicial.map((f) => ({ ...f, _id: `f${idFila.current++}` })));
  }, [inicial]);

  const editar = (id: string, campo: keyof PlantillaFranja, valor: string) =>
    setFilas((prev) =>
      prev.map((f) => (f._id === id ? { ...f, [campo]: valor } : f)),
    );
  const quitar = (id: string) =>
    setFilas((prev) => prev.filter((f) => f._id !== id));
  const añadir = () =>
    setFilas((prev) => [
      ...prev,
      { nombre: "", inicio: "00:00", fin: "08:00", _id: `f${idFila.current++}` },
    ]);

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
    !!inicial &&
    JSON.stringify(filas.map(({ _id: _, ...f }) => f)) ===
      JSON.stringify(inicial);
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
          {filas.map((f) => (
            <div
              key={f._id}
              className="flex flex-wrap items-end gap-2 rounded border px-2 py-2"
            >
              <div className="min-w-32 flex-1">
                <Label className="text-xs text-muted-foreground">Nombre</Label>
                <Input
                  value={f.nombre}
                  onChange={(e) => editar(f._id, "nombre", e.target.value)}
                  placeholder="Mañana"
                  className="h-8"
                />
              </div>
              <div className="w-24">
                <Label className="text-xs text-muted-foreground">Inicio</Label>
                <Input
                  value={f.inicio}
                  onChange={(e) => editar(f._id, "inicio", e.target.value)}
                  placeholder="HH:MM"
                  className="h-8"
                />
              </div>
              <div className="w-24">
                <Label className="text-xs text-muted-foreground">Fin</Label>
                <Input
                  value={f.fin}
                  onChange={(e) => editar(f._id, "fin", e.target.value)}
                  placeholder="HH:MM"
                  className="h-8"
                />
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                onClick={() => quitar(f._id)}
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
 * Diálogo «Franjas» UNIFICADO: una sola entrada con dos pestañas claras:
 *  - «Esta semana»: las franjas SOLO de la semana en vista (puntual).
 *  - «Plantilla por defecto»: la lista flexible de franjas (2, 3 o N) del que parten las
 *    semanas nuevas; se puede añadir «Nocturna» u otras.
 */
export function DialogFranjas({
  lunes,
  onCerrar,
  onAsignar,
}: {
  lunes: string;
  onCerrar: () => void;
  /** Atajo a «Asignar turnos» desde «Esta semana»; oculto si no se pasa (p. ej. semana aprobada). */
  onAsignar?: () => void;
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
          <CuerpoFranjasSemana lunes={lunes} onCerrar={onCerrar} onAsignar={onAsignar} />
        ) : (
          <CuerpoPlantillaFranjas onCerrar={onCerrar} />
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Dialog «Ajustes de turnos» (preferencias de visualización por marca, solo admin) -------

/**
 * Ajustes de presentación del calendario de turnos, por marca. Dos preferencias: si «Equipo»
 * muestra el rango horario junto a cada franja, y si la funcionalidad de tiempo libre/ausencias
 * (vacaciones, baja, descanso) está visible. Se guardan en la misma config por marca que las
 * franjas (PATCH parcial: solo toca el campo cambiado). La vista «Yo» no se ve afectada por el
 * primero (siempre muestra las horas propias).
 */
export function DialogoAjustesTurnos({ onCerrar }: { onCerrar: () => void }) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "config", "franjas", marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.obtenerConfigFranjas(marcaActiva ?? undefined, signal),
  });
  // Eco local por interruptor para feedback inmediato; al confirmar el servidor, la query manda.
  const [ecoHoras, setEcoHoras] = React.useState<boolean | null>(null);
  const [ecoTiempoLibre, setEcoTiempoLibre] = React.useState<boolean | null>(null);
  const mostrarHoras = ecoHoras ?? q.data?.mostrar_horas_equipo ?? false;
  const tiempoLibre = ecoTiempoLibre ?? q.data?.tiempo_libre_activo ?? true;

  const guardar = useMutation({
    mutationFn: (cambio: CuerpoGuardarConfigFranjas) =>
      api.guardarConfigFranjas(cambio, marcaActiva ?? undefined),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["rota"] });
    },
    onError: (e) => {
      setEcoHoras(null);
      setEcoTiempoLibre(null);
      toast.error(mensajeError(e));
    },
  });

  return (
    <Dialog open onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="gap-3 sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Ajustes de turnos</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Preferencias de visualización del calendario, por marca. El equipo las ajusta a su gusto.
        </p>
        {q.isPending ? (
          <Skeleton className="h-16 w-full rounded-md" />
        ) : q.isError ? (
          <BloqueError
            titulo="No se pudieron cargar los ajustes"
            mensaje={mensajeError(q.error)}
            onReintentar={() => void q.refetch()}
            cargando={q.isFetching}
          />
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex items-start justify-between gap-4 rounded-lg border bg-card p-3">
              <div>
                <Label htmlFor="ajuste-horas-equipo" className="text-sm font-medium">
                  Mostrar horas en el calendario de «Equipo»
                </Label>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Apagado, en «Equipo» se ve solo «Mañana / Tarde / Noche», sin el rango de horas:
                  cada persona tiene su propio horario dentro de la franja. La vista «Yo» siempre
                  muestra tus horas.
                </p>
              </div>
              <Switch
                id="ajuste-horas-equipo"
                checked={mostrarHoras}
                onCheckedChange={(v) => {
                  setEcoHoras(v);
                  guardar.mutate({ mostrar_horas_equipo: v });
                }}
                disabled={guardar.isPending}
                aria-label="Mostrar horas en el calendario de Equipo"
              />
            </div>
            <div className="flex items-start justify-between gap-4 rounded-lg border bg-card p-3">
              <div>
                <Label htmlFor="ajuste-tiempo-libre" className="text-sm font-medium">
                  Tiempo libre (vacaciones, baja, descanso)
                </Label>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Activado, el equipo puede registrar y ver el tiempo libre en el calendario y
                  gestionarlo. Apagado, esa función se oculta por completo.
                </p>
              </div>
              <Switch
                id="ajuste-tiempo-libre"
                checked={tiempoLibre}
                onCheckedChange={(v) => {
                  setEcoTiempoLibre(v);
                  guardar.mutate({ tiempo_libre_activo: v });
                }}
                disabled={guardar.isPending}
                aria-label="Activar tiempo libre y ausencias"
              />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

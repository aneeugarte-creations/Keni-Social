/**
 * Página CÓMPUTO Y COLA (`/maquina/computo`): la cola de generación POR DENTRO. Enseña el estado
 * en vivo (en curso / en cola / workers) y deja al humano PRIORIZAR, cancelar, reintentar y purgar
 * la cola in-place. `?proceso=` enfoca a un motor. Es la pestaña de aterrizaje del hub de la
 * máquina; el presupuesto y la economía viven en su pestaña hermana «Economía».
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Clock, Cpu, type LucideIcon, Trash2, Users } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { Kpi, TablaJobs } from "@/pages/maquina/cola-comun";
import { PROC_META } from "@/pages/monitor/comun";
import type { ColaJob, Proceso } from "@/types";

/** Card con la lista de jobs de un estado (en curso / esperando), o un vacío amable. */
function ColaCard({
  titulo,
  icono: Icono,
  jobs,
  vacio,
  borde,
  children,
}: {
  titulo: string;
  icono: LucideIcon;
  jobs: ColaJob[];
  vacio: string;
  borde?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className={borde}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icono className="h-4 w-4 text-sky-600" aria-hidden="true" />
          {titulo} <span className="font-normal text-muted-foreground">({jobs.length})</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {jobs.length === 0 ? (
          <p className="px-6 pb-6 text-sm text-muted-foreground">{vacio}</p>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

export default function Computo() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const { marcaActiva } = useMarcaActiva();
  const [searchParams] = useSearchParams();
  const crudoProceso = searchParams.get("proceso");
  const proceso: Proceso | undefined =
    crudoProceso === "investigacion" || crudoProceso === "produccion" ? crudoProceso : undefined;
  const qc = useQueryClient();
  const [cancelandoId, setCancelandoId] = React.useState<string | null>(null);
  const [priorizandoId, setPriorizandoId] = React.useState<string | null>(null);
  const [reintentandoId, setReintentandoId] = React.useState<string | null>(null);

  const cola = useQuery({
    queryKey: ["actividad", "cola", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.cola({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // Invalida la cola para repintar al instante tras una acción (la vista ya auto-refresca, pero
  // así el feedback es inmediato y no espera al siguiente tick).
  const refrescar = () => void qc.invalidateQueries({ queryKey: ["actividad", "cola"] });

  const cancelar = useMutation({
    mutationFn: (genId: string) => api.cancelarGeneracion(genId),
    onMutate: (genId: string) => setCancelandoId(genId),
    onSuccess: () => {
      toast.success("Generación cancelada.");
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
    onSettled: () => setCancelandoId(null),
  });
  const priorizar = useMutation({
    mutationFn: (genId: string) => api.colaPriorizar(genId),
    onMutate: (genId: string) => setPriorizandoId(genId),
    onSuccess: () => {
      toast.success("Job priorizado: adelanta al lote de fondo.");
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
    onSettled: () => setPriorizandoId(null),
  });
  const reintentar = useMutation({
    mutationFn: (genId: string) => api.colaReencolar(genId),
    onMutate: (genId: string) => setReintentandoId(genId),
    onSuccess: (r) => {
      toast.success(r.reencolado ? "Job reencolado: vuelve a la cola." : "El job ya no se podía reencolar.");
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
    onSettled: () => setReintentandoId(null),
  });
  const purgar = useMutation({
    mutationFn: () => api.colaPurgar(),
    onSuccess: (r) => {
      toast.success(
        r.purgados > 0 ? `Cola liberada (${r.purgados} en curso).` : "La cola ya estaba libre.",
      );
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (cola.isError) {
    return (
      <div className="space-y-4">
        <BloqueError
          titulo="No se pudo leer la cola"
          mensaje={mensajeError(cola.error)}
          onReintentar={() => void cola.refetch()}
          cargando={cola.isFetching}
        />
      </div>
    );
  }
  if (cola.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }

  const snap = cola.data;
  const enCurso = proceso ? snap.en_curso.filter((j) => j.proceso === proceso) : snap.en_curso;
  const esperando = proceso ? snap.esperando.filter((j) => j.proceso === proceso) : snap.esperando;

  return (
    <div className="space-y-6">
      {/* El título lo pinta la tira de pestañas del hub (Cómputo). La cola se auto-refresca
          (INTERVALO_VIVO_MS); el kebab queda solo para la acción admin de purgar. */}
      {esAdmin && (
        <AccionesPagina>
          <MenuAcciones>
            <ItemMenu
              icono={Trash2}
              className="text-destructive"
              disabled={purgar.isPending}
              onClick={async () => {
                if (
                  await confirmar({
                    titulo: "Liberar la cola",
                    mensaje:
                      "¿Liberar la cola? Cancela todo lo que esté activo (en curso + esperando) y libera la capacidad.",
                    destructivo: true,
                    textoConfirmar: "Liberar",
                  })
                ) {
                  purgar.mutate();
                }
              }}
            >
              Purgar cola
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      )}

      {/* Enfoque a un motor (?proceso=). */}
      {proceso && (
        <p className="text-sm text-muted-foreground">
          Enfocado a{" "}
          <strong className={PROC_META[proceso].texto}>{PROC_META[proceso].etiqueta}</strong>.{" "}
          <Link to="/maquina/computo" className="underline-offset-2 hover:underline">
            Ver ambos motores
          </Link>
        </p>
      )}

      {/* Estado en vivo. (El presupuesto y la parada de emergencia viven en «Economía».) */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Kpi
          icono={Cpu}
          titulo="En curso"
          valor={`${snap.procesando} / ${snap.capacidad.max_jobs}`}
          tono={snap.procesando >= snap.capacidad.max_jobs ? "alerta" : undefined}
        />
        <Kpi
          icono={Clock}
          titulo="En cola"
          valor={snap.conteo.pendientes}
          tono={snap.conteo.pendientes > 0 ? "espera" : undefined}
        />
        <Kpi
          icono={Users}
          titulo="Workers activos"
          valor={snap.workers_activos.length}
          tono={snap.workers_activos.length > 0 ? "ok" : undefined}
        />
      </div>

      {/* La cola por dentro: los dos estados en paralelo (de lado a lado en pantallas anchas). */}
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
        <ColaCard titulo="En curso" icono={Activity} jobs={enCurso} vacio="Sin generaciones en curso.">
          <TablaJobs
            jobs={enCurso}
            mostrarWorker
            esAdmin={esAdmin}
            onCancelar={(id) => cancelar.mutate(id)}
            cancelandoId={cancelandoId}
            onReintentar={(id) => reintentar.mutate(id)}
            reintentandoId={reintentandoId}
          />
        </ColaCard>

        <ColaCard
          titulo="Esperando"
          icono={Clock}
          jobs={esperando}
          vacio="Cola vacía."
          borde={esperando.length > 0 ? "border-amber-500/30" : undefined}
        >
          <TablaJobs
            jobs={esperando}
            mostrarWorker={false}
            esAdmin={esAdmin}
            onCancelar={(id) => cancelar.mutate(id)}
            cancelandoId={cancelandoId}
            onPriorizar={(id) => priorizar.mutate(id)}
            priorizandoId={priorizandoId}
            onReintentar={(id) => reintentar.mutate(id)}
            reintentandoId={reintentandoId}
          />
        </ColaCard>
      </div>
    </div>
  );
}

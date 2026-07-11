/**
 * Página CÓMPUTO Y COLA (`/maquina/agentes`): la cola de generación POR DENTRO. Enseña el estado
 * en vivo (en curso / en cola / workers) y deja al humano PRIORIZAR, cancelar, reintentar y purgar
 * la cola in-place. `?proceso=` enfoca a un motor. Es la pestaña de aterrizaje del hub «Agentes»;
 * el presupuesto y la economía viven en su pestaña hermana «Economía».
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, Clock, Cpu, type LucideIcon, Trash2, Users } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { Kpi, TablaBacklog, TablaDesglose, TablaJobs } from "@/pages/maquina/cola-comun";
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
          <Icono className="h-4 w-4 text-sky-600 dark:text-sky-400" aria-hidden="true" />
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
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [searchParams] = useSearchParams();
  const crudoProceso = searchParams.get("proceso");
  const proceso: Proceso | undefined =
    crudoProceso === "investigacion" || crudoProceso === "produccion" ? crudoProceso : undefined;
  const qc = useQueryClient();
  const [cancelandoId, setCancelandoId] = React.useState<string | null>(null);
  const [priorizandoId, setPriorizandoId] = React.useState<string | null>(null);
  const [reintentandoId, setReintentandoId] = React.useState<string | null>(null);
  const [eliminandoId, setEliminandoId] = React.useState<string | null>(null);

  const cola = useQuery({
    queryKey: ["actividad", "cola", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.cola({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // Foto completa por marca×etapa×estado (sin filtro): siempre visible bajo las listas.
  const desglose = useQuery({
    queryKey: ["actividad", "cola", "desglose"],
    queryFn: ({ signal }) => api.colaDesglose(signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // Embalse del tablero por marca×etapa (sin filtro): el backlog que precede a la cola de jobs.
  const backlog = useQuery({
    queryKey: ["produccion", "backlog"],
    queryFn: ({ signal }) => api.produccionBacklog(signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // Nombre legible de cada marca para la tabla de desglose (cae al id si no está en el catálogo).
  const catalogo = useQuery({
    queryKey: ["marcas-catalogo"],
    queryFn: ({ signal }) => api.catalogoMarcas(signal),
    staleTime: 60_000,
  });
  const nombrePorMarca = React.useMemo(() => {
    const m: Record<string, string> = {};
    for (const marca of catalogo.data?.marcas ?? []) m[marca.id] = marca.etiqueta;
    return m;
  }, [catalogo.data]);

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
    mutationFn: ({ genId, opts }: { genId: string; opts?: { prioridad?: number; a_tope?: boolean } }) =>
      api.colaPriorizar(genId, opts),
    onMutate: ({ genId }: { genId: string; opts?: { prioridad?: number; a_tope?: boolean } }) =>
      setPriorizandoId(genId),
    onSuccess: (r) => {
      const aplicada = r.prioridad;
      toast.success(
        aplicada != null ? `Prioridad fijada a ${aplicada}.` : "Job priorizado: adelanta al lote de fondo.",
      );
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
    onSettled: () => setPriorizandoId(null),
  });
  const eliminar = useMutation({
    mutationFn: (genId: string) => api.colaEliminar(genId),
    onMutate: (genId: string) => setEliminandoId(genId),
    onSuccess: () => {
      toast.success("Job eliminado de la cola.");
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
    onSettled: () => setEliminandoId(null),
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
  const limpiarHuerfanos = useMutation({
    mutationFn: () => api.colaLimpiarHuerfanos(),
    onSuccess: (r) => {
      toast.success(
        r.huerfanos_limpiados > 0
          ? `${r.huerfanos_limpiados} jobs huérfanos limpiados.`
          : "No quedaban jobs huérfanos.",
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
  // Con una marca seleccionada, los CONTEOS de jobs son los de la marca (cuadran con las listas de
  // abajo); el global se rotula aparte. La CAPACIDAD (slots/workers) es legítimamente global.
  const cm = marcaActiva ? snap.conteo_marca ?? null : null;
  const etqMarca = nombreActiva ?? marcaActiva ?? "";
  const huerf = snap.huerfanos ?? null;
  const totalHuerf = huerf ? huerf.pendientes + huerf.reclamados : 0;
  const enColaValor = cm ? cm.pendientes : snap.conteo.pendientes;

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
          <Link to="/maquina/agentes" className="underline-offset-2 hover:underline">
            Ver ambos motores
          </Link>
        </p>
      )}

      {/* Embalse del tablero: el backlog por marca×etapa que se acumula ANTES de la cola de jobs.
          Va arriba para leer la cadena de arriba abajo (embalse A→E → cola de jobs → publicado).
          Siempre visible, sin filtro de marca (es la foto completa, como el endpoint). */}
      {backlog.data && <TablaBacklog backlog={backlog.data} />}

      {/* Jobs huérfanos: parte del conteo global sin generación detrás (no se procesan). El botón
          de limpiarlos es admin (el back responde 403 si no lo es). */}
      {totalHuerf > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/50 bg-amber-50 px-4 py-3 dark:bg-amber-950/30">
          <p className="flex items-center gap-2 text-sm text-amber-900 dark:text-amber-200">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
            <span>
              <span className="font-semibold tabular-nums">{totalHuerf}</span> jobs huérfanos: sin
              generación, no se procesan.
              {!esAdmin && " Un administrador puede limpiarlos."}
            </span>
          </p>
          {esAdmin && (
            <Button
              size="sm"
              variant="outline"
              disabled={limpiarHuerfanos.isPending}
              onClick={() => limpiarHuerfanos.mutate()}
            >
              Limpiar huérfanos
            </Button>
          )}
        </div>
      )}

      {/* Estado en vivo. (El presupuesto y la parada de emergencia viven en «Economía».) Con marca
          activa los conteos son de la marca (cuadran con las listas); la capacidad sigue global. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Kpi
          icono={Cpu}
          titulo={cm ? `En curso · ${etqMarca}` : "En curso"}
          valor={cm ? cm.reclamados : `${snap.procesando} / ${snap.capacidad.max_jobs}`}
          subtitulo={cm ? `Global ${snap.procesando} / ${snap.capacidad.max_jobs} slots` : undefined}
          tono={
            cm
              ? cm.reclamados > 0
                ? "ok"
                : undefined
              : snap.procesando >= snap.capacidad.max_jobs
                ? "alerta"
                : undefined
          }
        />
        <Kpi
          icono={Clock}
          titulo={cm ? `En cola · ${etqMarca}` : "En cola"}
          valor={enColaValor}
          subtitulo={cm ? `Global ${snap.conteo.pendientes}` : undefined}
          tono={enColaValor > 0 ? "espera" : undefined}
        />
        <Kpi
          icono={Users}
          titulo={cm ? "Workers · global" : "Workers activos"}
          valor={snap.workers_activos.length}
          subtitulo={cm ? `${snap.procesando} / ${snap.capacidad.max_jobs} slots usados` : undefined}
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
            onEliminar={(id) => eliminar.mutate(id)}
            eliminandoId={eliminandoId}
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
            onPriorizar={(id, opts) => priorizar.mutate({ genId: id, opts })}
            priorizandoId={priorizandoId}
            onReintentar={(id) => reintentar.mutate(id)}
            reintentandoId={reintentandoId}
            onEliminar={(id) => eliminar.mutate(id)}
            eliminandoId={eliminandoId}
          />
        </ColaCard>
      </div>

      {/* Foto completa por marca×etapa×estado (siempre visible, sin filtro de marca). */}
      {desglose.data && (
        <TablaDesglose desglose={desglose.data} nombrePorMarca={nombrePorMarca} />
      )}
    </div>
  );
}

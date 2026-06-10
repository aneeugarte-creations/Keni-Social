import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowUp, Boxes, Clock, Coins, Cpu, Layers, RefreshCw, RotateCcw, Trash2, XCircle } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipNivelPresupuesto } from "@/components/comunes/ChipEstado";
import { AccionesPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { haceSegundos } from "@/lib/fecha";
import { costeUsd, numeroCompacto } from "@/lib/formato";
import { INTERVALO_SERIE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import {
  PanelAjustes,
  PanelMaquinaContenido,
  useGuardarAjuste,
} from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionEsfuerzo } from "@/pages/configuracion/SeccionEsfuerzo";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import { PanelSalud } from "@/pages/sistema/PanelSalud";
import type { ColaJob, ColaSerie, PresupuestoIA } from "@/types";

/** Tarjeta KPI: icono, valor grande y subtítulo. `tono` colorea el valor ante alerta. */
function Kpi({
  icono: Icono,
  titulo,
  valor,
  subtitulo,
  tono,
}: {
  icono: typeof Cpu;
  titulo: string;
  valor: React.ReactNode;
  subtitulo?: React.ReactNode;
  tono?: "alerta" | "ok" | "espera";
}) {
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icono className="h-4 w-4" aria-hidden="true" />
          {titulo}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 p-4 pt-0">
        <div
          className={cn(
            "text-2xl font-semibold tabular-nums",
            tono === "alerta" && "text-destructive",
            tono === "ok" && "text-emerald-600",
            tono === "espera" && "text-amber-600",
          )}
        >
          {valor}
        </div>
        {subtitulo && <div className="text-xs text-muted-foreground">{subtitulo}</div>}
      </CardContent>
    </Card>
  );
}

/** Tabla de jobs en vuelo (en curso o esperando), con acción de cancelar para admin. */
function TablaJobs({
  jobs,
  mostrarWorker,
  esAdmin,
  onCancelar,
  cancelandoId,
  onPriorizar,
  priorizandoId,
}: {
  jobs: ColaJob[];
  mostrarWorker: boolean;
  esAdmin: boolean;
  onCancelar: (genId: string) => void;
  cancelandoId: string | null;
  /** Solo la tabla «Esperando»: adelanta el job al lote de fondo (prioridad manual). */
  onPriorizar?: (genId: string) => void;
  priorizandoId?: string | null;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Generación</TableHead>
          <TableHead className="hidden sm:table-cell">Tipo</TableHead>
          <TableHead className="hidden md:table-cell">Marca</TableHead>
          {mostrarWorker && <TableHead className="hidden lg:table-cell">Worker</TableHead>}
          <TableHead>{mostrarWorker ? "Corriendo" : "En cola"}</TableHead>
          {esAdmin && <TableHead className="text-right">Acción</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((j) => (
          <TableRow key={j.job_id}>
            <TableCell className="font-medium">
              <span className="inline-flex items-center gap-1.5">
                {j.etiqueta || j.gen_id}
                {/* Prioridad de cola (1f3acd7d): un lanzamiento manual adelanta al lote de
                    fondo del pipeline. Solo se señala lo prioritario (>0). */}
                {j.prioridad > 0 && (
                  <Badge
                    variant="secondary"
                    className="border border-sky-500/30 bg-sky-500/10 text-[10px] text-sky-600"
                    title={`Prioridad ${j.prioridad}: adelanta en la cola al lote de fondo.`}
                  >
                    prioritario
                  </Badge>
                )}
              </span>
            </TableCell>
            <TableCell className="hidden sm:table-cell text-muted-foreground">{j.tipo || "—"}</TableCell>
            <TableCell className="hidden md:table-cell text-muted-foreground">{j.marca || "—"}</TableCell>
            {mostrarWorker && (
              <TableCell className="hidden lg:table-cell font-mono text-xs text-muted-foreground">
                {j.worker || "—"}
              </TableCell>
            )}
            <TableCell className="tabular-nums text-muted-foreground">
              {haceSegundos(mostrarWorker ? j.corriendo_hace_s : j.encolado_hace_s)}
            </TableCell>
            {esAdmin && (
              <TableCell className="text-right">
                <span className="inline-flex items-center gap-1">
                  {onPriorizar && j.prioridad <= 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={priorizandoId === j.gen_id}
                      title="Adelanta este job a todo el lote de fondo que espera."
                      onClick={() => onPriorizar(j.gen_id)}
                    >
                      <ArrowUp className="mr-1 h-3.5 w-3.5" />
                      Priorizar
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    disabled={cancelandoId === j.gen_id}
                    onClick={() => onCancelar(j.gen_id)}
                  >
                    <XCircle className="mr-1 h-3.5 w-3.5" />
                    Cancelar
                  </Button>
                </span>
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** Mini-gráfico de barras por día: encolados (entrada) vs completados/errores (salida). */
function SeriePorDia({ serie }: { serie: ColaSerie }) {
  // Indexa resultados por día para alinearlos con los encolados.
  const porDia = new Map<string, { completados: number; errores: number; cola_llena: number }>();
  for (const r of serie.resultados) porDia.set(r.dia, r);
  const dias = Array.from(
    new Set([...serie.encolados.map((e) => e.dia), ...serie.resultados.map((r) => r.dia)]),
  ).sort();
  const maximo = Math.max(
    1,
    ...serie.encolados.map((e) => e.n),
    ...serie.resultados.map((r) => r.completados + r.errores),
  );

  if (dias.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin actividad en la ventana.</p>;
  }
  return (
    <div className="space-y-2">
      {dias.map((dia) => {
        const enc = serie.encolados.find((e) => e.dia === dia)?.n ?? 0;
        const res = porDia.get(dia) ?? { completados: 0, errores: 0, cola_llena: 0 };
        return (
          <div key={dia} className="flex items-center gap-3 text-xs">
            <span className="w-20 shrink-0 tabular-nums text-muted-foreground">{dia.slice(5)}</span>
            <div className="flex h-4 flex-1 overflow-hidden rounded bg-muted">
              <div
                className="bg-amber-500/70"
                style={{ width: `${(enc / maximo) * 100}%` }}
                title={`${enc} encolados`}
              />
              <div
                className="bg-emerald-500/70"
                style={{ width: `${(res.completados / maximo) * 100}%` }}
                title={`${res.completados} completados`}
              />
              <div
                className="bg-destructive/70"
                style={{ width: `${(res.errores / maximo) * 100}%` }}
                title={`${res.errores} errores`}
              />
            </div>
            <span className="w-28 shrink-0 text-right tabular-nums text-muted-foreground">
              <span className="text-amber-600">{enc} enc</span> · {res.completados} ok
              {res.errores > 0 && (
                <span className="text-destructive"> · {res.errores} err</span>
              )}
            </span>
          </div>
        );
      })}
      <p className="text-[11px] text-muted-foreground">
        Barra ámbar = encolados, verde = completados, roja = errores.
      </p>
    </div>
  );
}


/**
 * Monitor de la cola de generación (pestaña del hub Producción): qué ocurre AHORA en la
 * cola (workers, claude -p en vuelo, esperando), throughput por día y estado de los daemons,
 * con control de admin (purgar la cola, cancelar un job). Sondeo en vivo cada pocos segundos.
 */
/** ECONOMÍA DE TOKENS de la generación, en el sitio donde se OPERA la cola.
 *
 * El estado (nivel/gasto/restante) viene en el mismo snapshot de la cola; el control
 * rápido es el kill switch (KENI_GENERACION_PAUSADA, ajuste editable en caliente). Los
 * knobs finos (presupuesto diario, margen manual, tope de contexto) viven en el panel
 * Configuración → «Máquina de contenido» (grupo `pipeline_topes`). */
function PanelPresupuesto({
  presupuesto,
  esAdmin,
  pausando,
  onPausar,
}: {
  presupuesto: PresupuestoIA;
  esAdmin: boolean;
  pausando: boolean;
  onPausar: (valor: boolean) => void;
}) {
  const conPresupuesto = presupuesto.presupuesto_tokens_dia > 0;
  const pct = presupuesto.pct_usado;
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
          <Coins className="h-4 w-4 text-muted-foreground" />
          Economía de tokens
          <ChipNivelPresupuesto nivel={presupuesto.nivel} />
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4 pt-2">
        <div className="space-y-1 text-sm">
          <p>
            Hoy:{" "}
            <span className="font-medium tabular-nums">
              {numeroCompacto(presupuesto.gastado.tokens)}
            </span>{" "}
            tokens · {costeUsd(presupuesto.gastado.coste_usd)} ·{" "}
            {presupuesto.gastado.generaciones} generación(es)
          </p>
          {conPresupuesto ? (
            <p className="text-xs text-muted-foreground">
              Presupuesto diario {numeroCompacto(presupuesto.presupuesto_tokens_dia)} tokens
              {presupuesto.restante_tokens != null && (
                <> · restan {numeroCompacto(presupuesto.restante_tokens)}</>
              )}
              {pct != null && <> · {pct.toFixed(0)}% usado</>}
              {" · al agotarse se corta el trabajo automático (lo manual sigue hasta el margen)"}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Sin presupuesto diario configurado (se fija en Configuración → Máquina de contenido).
            </p>
          )}
          {conPresupuesto && pct != null && (
            <div className="h-1.5 w-56 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-500" : "bg-emerald-500",
                )}
                style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
              />
            </div>
          )}
        </div>
        {esAdmin && (
          <label className="flex items-center gap-2 text-sm">
            <span className={cn(presupuesto.pausada ? "text-destructive" : "text-muted-foreground")}>
              {presupuesto.pausada ? "Generación pausada" : "Pausar generación"}
            </span>
            <Switch
              checked={presupuesto.pausada}
              disabled={pausando}
              onCheckedChange={(v) => onPausar(v)}
              aria-label="Pausar la generación con IA (kill switch)"
            />
          </label>
        )}
      </CardContent>
    </Card>
  );
}

// Grupos del catálogo que son TUNING DE SISTEMA (jobs, limpieza, alertas): se ajustan
// aquí porque es el Monitor quien vigila sus efectos (cola, daemons, salud).
const GRUPOS_SISTEMA = new Set(["automatismos_generales", "tuning"]);

export default function Monitor() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  // Pestañas del Monitor: «En vivo» (la cola, para todo el equipo) y «Salud» (la infra,
  // solo admin: era la página Sistema del avatar, consolidada aquí). El tab viaja en la
  // URL (?tab=salud) para que /sistema pueda redirigir y los enlaces profundos funcionen.
  const [searchParams, setSearchParams] = useSearchParams();
  const crudoTab = searchParams.get("tab");
  const tab =
    crudoTab === "ajustes" ? "ajustes" : esAdmin && crudoTab === "salud" ? "salud" : "vivo";
  const qc = useQueryClient();
  // El Monitor respeta el switch GLOBAL de marca (como Pipelines/Actividad): las listas de
  // jobs se acotan a la marca activa (null = "Todas", solo admin). La capacidad es global.
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [cancelandoId, setCancelandoId] = React.useState<string | null>(null);
  const [priorizandoId, setPriorizandoId] = React.useState<string | null>(null);

  const cola = useQuery({
    queryKey: ["actividad", "cola", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.cola({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  const serie = useQuery({
    queryKey: ["actividad", "cola", "series"],
    queryFn: ({ signal }) => api.colaSeries(14, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });

  const refrescar = () => {
    void qc.invalidateQueries({ queryKey: ["actividad", "cola"] });
  };

  const purgar = useMutation({
    mutationFn: () => api.colaPurgar(),
    onSuccess: (r) => {
      toast.success(
        r.purgados > 0 ? `Cola liberada (${r.purgados} en vuelo).` : "La cola ya estaba libre.",
      );
      refrescar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

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

  // Toggle REAL de un daemon: la MISMA mutación compartida que Configuración y el panel de la
  // máquina (una sola implementación del control); su onSuccess ya invalida ajustes + cola +
  // pipelines, así el estado «Activo/Apagado» y las vistas derivadas reflejan el cambio al
  // instante. `guardandoClave` se deriva de la mutación en vuelo (sin estado local paralelo).
  const guardarAjuste = useGuardarAjuste();
  const guardandoClave = guardarAjuste.isPending ? (guardarAjuste.variables?.clave ?? null) : null;

  return (
    <>
      <AccionesPagina>
        <Button
          variant="outline"
          size="sm"
          onClick={refrescar}
          disabled={cola.isFetching}
        >
          <RefreshCw className={cn("mr-1 h-4 w-4", cola.isFetching && "animate-spin")} />
          Actualizar
        </Button>
        {esAdmin && (
          <Button
            variant="destructive"
            size="sm"
            disabled={purgar.isPending}
            onClick={() => {
              if (
                window.confirm(
                  "¿Liberar la cola? Cancela todo lo que esté en vuelo (en curso + esperando) y libera la capacidad.",
                )
              ) {
                purgar.mutate();
              }
            }}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Purgar cola
          </Button>
        )}
      </AccionesPagina>

      <Tabs
        value={tab}
        onValueChange={(v) =>
          setSearchParams(v === "vivo" ? {} : { tab: v }, { replace: true })
        }
        className="mb-4"
      >
        <TabsList>
          <TabsTrigger value="vivo">En vivo</TabsTrigger>
          {esAdmin && <TabsTrigger value="salud">Salud</TabsTrigger>}
          <TabsTrigger value="ajustes">Ajustes</TabsTrigger>
        </TabsList>
      </Tabs>

      {tab === "salud" ? (
        <PanelSalud />
      ) : tab === "ajustes" ? (
        /* AJUSTES DE LO QUE ESTE MONITOR VIGILA (reparto contextual: cada ajuste vive en
           la página a la que afecta): la máquina de contenido (etapas/por marca/topes y
           economía de tokens), el tuning del sistema (jobs, limpieza, alertas) y el
           esfuerzo de la generación. Lo demás vive en su página (noticias, publicación,
           conexiones). */
        <div className="space-y-4">
          <PanelMaquinaContenido />
          {/* El proveedor de imagen IA alimenta la etapa ARTE del pipeline (autogen-arte
              y el «Generar con IA»): se configura junto a la máquina que lo consume, no
              en el editor de plantillas. Se oculta solo a un editor. */}
          <SeccionImagen />
          <PanelAjustes
            ids={GRUPOS_SISTEMA}
            titulo="Sistema"
            descripcion="Jobs simultáneos, limpiezas de fondo y alertas. Funcionan bien en sus valores por defecto; aplican en caliente."
          />
          <SeccionEsfuerzo />
        </div>
      ) : cola.isError ? (
        <BloqueError
          titulo="No se pudo leer la cola"
          mensaje={mensajeError(cola.error)}
          onReintentar={() => void cola.refetch()}
          cargando={cola.isFetching}
        />
      ) : cola.isPending ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          {cola.data.cola_llena && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                La cola está al tope ({cola.data.conteo.activos}/{cola.data.capacidad.tope}). La
                máquina espera (reintenta sola); los lanzamientos manuales siguen entrando y se
                despachan primero.
                {esAdmin && " Puedes purgar la cola para vaciarla."}
              </span>
            </div>
          )}

          {/* KPIs en vivo */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi
              icono={Cpu}
              titulo="En curso"
              valor={`${cola.data.procesando}/${cola.data.capacidad.max_jobs}`}
              subtitulo="claude -p en vuelo / slots"
              tono={cola.data.procesando >= cola.data.capacidad.max_jobs ? "alerta" : undefined}
            />
            <Kpi
              icono={Clock}
              titulo="Esperando"
              valor={`${cola.data.conteo.pendientes}/${cola.data.capacidad.max_cola}`}
              subtitulo="en cola, esperando un slot"
              tono={cola.data.conteo.pendientes > 0 ? "espera" : undefined}
            />
            <Kpi
              icono={Layers}
              titulo="Activos"
              valor={`${cola.data.conteo.activos}/${cola.data.capacidad.tope}`}
              subtitulo="en vuelo / tope total"
              tono={cola.data.cola_llena ? "alerta" : undefined}
            />
            <Kpi
              icono={Boxes}
              titulo="Slots libres"
              valor={cola.data.slots_libres}
              subtitulo={`${cola.data.workers_activos.length} worker(s) activo(s)`}
              tono={cola.data.slots_libres > 0 ? "ok" : undefined}
            />
          </div>

          {/* Economía de tokens: estado vivo + kill switch (los knobs, en Máquina de contenido) */}
          {cola.data.presupuesto && (
            <PanelPresupuesto
              presupuesto={cola.data.presupuesto}
              esAdmin={esAdmin}
              pausando={
                guardarAjuste.isPending &&
                guardandoClave === "KENI_GENERACION_PAUSADA"
              }
              onPausar={(valor) =>
                guardarAjuste.mutate({ clave: "KENI_GENERACION_PAUSADA", valor })
              }
            />
          )}

          {/* En curso */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Activity className="h-4 w-4 text-sky-600" />
                En curso ({cola.data.en_curso.length})
                {/* Las listas respetan el switch global de marca; la capacidad es global. */}
                {marcaActiva && (
                  <Badge variant="outline" className="font-normal text-muted-foreground">
                    {nombreActiva ?? marcaActiva}
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {cola.data.en_curso.length === 0 ? (
                <p className="p-4 pt-0 text-sm text-muted-foreground">
                  Ningún <code>claude -p</code>
                  {marcaActiva ? ` de ${nombreActiva ?? marcaActiva}` : ""} corriendo ahora mismo.
                </p>
              ) : (
                <TablaJobs
                  jobs={cola.data.en_curso}
                  mostrarWorker
                  esAdmin={esAdmin}
                  onCancelar={(id) => cancelar.mutate(id)}
                  cancelandoId={cancelandoId}
                />
              )}
            </CardContent>
          </Card>

          {/* Esperando */}
          {cola.data.esperando.length > 0 && (
            <Card className="border-amber-500/30">
              <CardHeader className="p-4 pb-2">
                <CardTitle className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-500">
                  <Clock className="h-4 w-4 text-amber-600" />
                  Esperando ({cola.data.esperando.length})
                  {marcaActiva && (
                    <Badge variant="outline" className="font-normal text-muted-foreground">
                      {nombreActiva ?? marcaActiva}
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <TablaJobs
                  onPriorizar={(id) => priorizar.mutate(id)}
                  priorizandoId={priorizandoId}
                  jobs={cola.data.esperando}
                  mostrarWorker={false}
                  esAdmin={esAdmin}
                  onCancelar={(id) => cancelar.mutate(id)}
                  cancelandoId={cancelandoId}
                />
              </CardContent>
            </Card>
          )}

          {/* Throughput por día */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <RotateCcw className="h-4 w-4 text-muted-foreground" />
                Últimos 14 días
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-2">
              {serie.isPending ? (
                <Skeleton className="h-40 w-full" />
              ) : serie.isError ? (
                <p className="text-sm text-muted-foreground">{mensajeError(serie.error)}</p>
              ) : (
                <SeriePorDia serie={serie.data} />
              )}
            </CardContent>
          </Card>

          {/* SIN formularios aquí: la máquina de contenido y los toggles de daemons se
              CONFIGURAN en Configuración (pestañas Máquina/Ajustes); la SALUD de los
              daemons se observa en la pestaña Salud. El Monitor opera: cancelar, purgar
              y el kill switch de arriba. */}
        </div>
      )}
    </>
  );
}

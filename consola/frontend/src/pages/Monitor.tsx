import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowUp, Boxes, Clock, Cpu, Layers, RefreshCw, RotateCcw, Trash2, XCircle } from "lucide-react";
import * as React from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipNivelPresupuesto } from "@/components/comunes/ChipEstado";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
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
import {
  DesgloseEconomiaProceso,
  PROC_META,
  resultadoDelDia,
  SerieProceso,
  TituloEconomia,
} from "@/pages/monitor/comun";
import { PipelineEnVivo } from "@/pages/monitor/PipelineEnVivo";
import { ZonaEstado } from "@/pages/sistema/Doctor";
import type { ColaJob, PresupuestoIA, Proceso, ResultadoDia } from "@/types";

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

/**
 * Monitor de la máquina de contenido (hub Producción): arriba la zona de ESTADO (el doctor +
 * temas bloqueados), después el PIPELINE EN VIVO (la tira de etapas con su toggle y conteos),
 * la economía de tokens (kill switch), las tablas en curso/esperando y el throughput por día,
 * con control de admin (purgar la cola, cancelar/priorizar un job). Sondeo en vivo cada pocos
 * segundos. La INFRA (recursos/daemons/backups/S3, antes pestaña «Salud») vive en /sistema.
 */
/** ECONOMÍA DE TOKENS de la generación, en el sitio donde se OPERA la cola.
 *
 * El estado (nivel/gasto/restante) viene en el mismo snapshot de la cola; el control
 * rápido es el kill switch (KENI_GENERACION_PAUSADA, ajuste editable en caliente). Los
 * knobs finos (presupuesto diario, margen manual, tope de contexto) viven en el panel
 * Configuración → «Máquina de contenido» (grupo `pipeline_topes`). */
function PanelPresupuesto({
  presupuesto,
  resHoy,
  esAdmin,
  pausando,
  onPausar,
}: {
  presupuesto: PresupuestoIA;
  /** Resultados de HOY de la serie (para el desglose de gasto por proceso). Null si no hay. */
  resHoy: ResultadoDia | null;
  esAdmin: boolean;
  pausando: boolean;
  onPausar: (valor: boolean) => void;
}) {
  const conPresupuesto = presupuesto.presupuesto_tokens_dia > 0;
  const pct = presupuesto.pct_usado;
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <TituloEconomia />
          <ChipNivelPresupuesto nivel={presupuesto.nivel} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4 pt-2">
        <div className="space-y-1.5 text-sm">
          <p>
            Hoy:{" "}
            <span className="font-medium tabular-nums">
              {numeroCompacto(presupuesto.gastado.tokens)}
            </span>{" "}
            tokens · {costeUsd(presupuesto.gastado.coste_usd)} ·{" "}
            {presupuesto.gastado.generaciones} generación(es) con coste
          </p>
          {/* Desglose del gasto de HOY por proceso (Investigación vs Producción). */}
          <DesgloseEconomiaProceso res={resHoy} />
          {conPresupuesto ? (
            <p className="text-xs text-muted-foreground">
              Presupuesto diario {numeroCompacto(presupuesto.presupuesto_tokens_dia)} tokens
              {presupuesto.restante_tokens != null && (
                <> · restan {numeroCompacto(presupuesto.restante_tokens)}</>
              )}
              {pct != null && <> · {pct.toFixed(0)}% usado</>}
            </p>
          ) : null}
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
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

export default function Monitor() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const crudoTab = searchParams.get("tab");
  // La antigua pestaña "Ajustes" vive ahora en el panel lateral de ajustes de la página;
  // los deep-links `?tab=ajustes` abren el panel directamente. La antigua pestaña «Salud»
  // (la infra) volvió a ser página propia (/sistema): se redirige más abajo, tras los hooks.
  const abrirAjustes = crudoTab === "ajustes";
  // Prefiltro por PROCESO (`?proceso=investigacion|produccion`, lo enlazará Noticias en
  // Fase 3): acota las vistas de cola (tablas y tira) al loop pedido. Inválido = sin filtro.
  const crudoProceso = searchParams.get("proceso");
  const proceso: Proceso | undefined =
    crudoProceso === "investigacion" || crudoProceso === "produccion" ? crudoProceso : undefined;
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

  // La antigua pestaña «Salud» (la infra) es ahora la página /sistema: los deep-links
  // viejos (?tab=salud, incl. la redirección legacy de /datos/sistema) siguen vivos.
  // (Tras TODOS los hooks, para no variar su orden entre renders.)
  if (crudoTab === "salud") return <Navigate to="/sistema" replace />;

  // Listas acotadas al prefiltro de proceso (afecta a las tablas; la capacidad es global).
  const enCurso = cola.data
    ? proceso
      ? cola.data.en_curso.filter((j) => j.proceso === proceso)
      : cola.data.en_curso
    : [];
  const esperando = cola.data
    ? proceso
      ? cola.data.esperando.filter((j) => j.proceso === proceso)
      : cola.data.esperando
    : [];
  const quitarProceso = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("proceso");
    setSearchParams(params, { replace: true });
  };

  return (
    <>
      <AccionesPagina>
        <MenuAcciones
          ajustesTitulo="Ajustes de la máquina"
          ajustesAbiertoInicial={abrirAjustes}
          ajustes={
            <>
              <PanelMaquinaContenido />
              <SeccionImagen />
              <PanelAjustes
                grupos={GRUPOS_SISTEMA}
                titulo="Sistema"
                descripcion="Jobs, limpiezas y alertas; sin reinicio."
              />
              <SeccionEsfuerzo />
            </>
          }
        >
          <ItemMenu icono={RefreshCw} onClick={refrescar} disabled={cola.isFetching}>
            Actualizar
          </ItemMenu>
          {esAdmin && (
            <ItemMenu
              icono={Trash2}
              className="text-destructive"
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
              Purgar cola
            </ItemMenu>
          )}
        </MenuAcciones>
      </AccionesPagina>

      {/* ZONA DE ESTADO (el doctor, visible para todos): con todo ok, una línea discreta;
          con problemas, los chequeos no-ok (admin solo ve además los suyos) + los temas
          bloqueados del pipeline. Va ARRIBA: es lo primero que responde «¿va bien la máquina?». */}
      <div className="mb-6">
        <ZonaEstado esAdmin={esAdmin} marca={marcaActiva ?? undefined} />
      </div>

      {cola.isError ? (
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
          {/* Prefiltro de proceso activo (?proceso=): se señala y se puede quitar. */}
          {proceso && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>
                Mostrando solo{" "}
                <strong className={PROC_META[proceso].texto}>{PROC_META[proceso].etiqueta}</strong>{" "}
                (tablas de jobs).
              </span>
              <Button variant="ghost" size="sm" onClick={quitarProceso}>
                Quitar filtro
              </Button>
            </div>
          )}

          {cola.data.cola_llena && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                La cola está al tope ({cola.data.conteo.activos}/{cola.data.capacidad.tope}).
                {esAdmin && " Puedes purgarla para vaciarla."}
              </span>
            </div>
          )}

          {/* KPIs en vivo del POOL COMPARTIDO. Investigación y Producción usan la MISMA cola y el
              MISMO pool: estos KPIs son la capacidad total; el desglose por loop va debajo. */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi
              icono={Cpu}
              titulo="En curso"
              valor={`${cola.data.procesando}/${cola.data.capacidad.max_jobs}`}
              subtitulo={`claude -p · ${cola.data.workers_activos.length} worker(s)`}
              tono={cola.data.procesando >= cola.data.capacidad.max_jobs ? "alerta" : undefined}
            />
            <Kpi
              icono={Clock}
              titulo="En cola"
              valor={`${cola.data.conteo.pendientes}/${cola.data.capacidad.max_cola}`}
              subtitulo="esperando un slot"
              tono={cola.data.conteo.pendientes > 0 ? "espera" : undefined}
            />
            <Kpi
              icono={Layers}
              titulo="Pool compartido"
              valor={`${cola.data.conteo.activos}/${cola.data.capacidad.tope}`}
              subtitulo="Investigación + Producción"
              tono={cola.data.cola_llena ? "alerta" : undefined}
            />
            <Kpi
              icono={Boxes}
              titulo="Slots libres"
              valor={cola.data.slots_libres}
              subtitulo={`de ${cola.data.capacidad.max_jobs} de cómputo`}
              tono={cola.data.slots_libres > 0 ? "ok" : undefined}
            />
          </div>

          {/* PIPELINE EN VIVO (Fase 2): la tira de etapas de la máquina (Selección →
              Validación → Copy → Arte) con el toggle maestro de cada etapa AL LADO de sus
              conteos vivos. Sustituye a las tarjetas por proceso: el mismo desglose del
              pool, pero al grano de etapa y con su control junto al estado. */}
          <PipelineEnVivo cola={cola.data} esAdmin={esAdmin} proceso={proceso} />

          {/* Economía de tokens: estado vivo + kill switch (los knobs, en Máquina de contenido) */}
          {cola.data.presupuesto && (
            <PanelPresupuesto
              presupuesto={cola.data.presupuesto}
              resHoy={resultadoDelDia(serie.data, cola.data.presupuesto.dia)}
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
                En curso ({enCurso.length})
                {/* Las listas respetan el switch global de marca; la capacidad es global. */}
                {marcaActiva && (
                  <Badge variant="outline" className="font-normal text-muted-foreground">
                    {nombreActiva ?? marcaActiva}
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {enCurso.length === 0 ? (
                <p className="p-4 pt-0 text-sm text-muted-foreground">
                  Ningún <code>claude -p</code>
                  {marcaActiva ? ` de ${nombreActiva ?? marcaActiva}` : ""} corriendo ahora mismo.
                </p>
              ) : (
                <TablaJobs
                  jobs={enCurso}
                  mostrarWorker
                  esAdmin={esAdmin}
                  onCancelar={(id) => cancelar.mutate(id)}
                  cancelandoId={cancelandoId}
                />
              )}
            </CardContent>
          </Card>

          {/* Esperando */}
          {esperando.length > 0 && (
            <Card className="border-amber-500/30">
              <CardHeader className="p-4 pb-2">
                <CardTitle className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-500">
                  <Clock className="h-4 w-4 text-amber-600" />
                  Esperando ({esperando.length})
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
                  jobs={esperando}
                  mostrarWorker={false}
                  esAdmin={esAdmin}
                  onCancelar={(id) => cancelar.mutate(id)}
                  cancelandoId={cancelandoId}
                />
              </CardContent>
            </Card>
          )}

          {/* Throughput por día: encolados (entrada) vs completados por proceso (salida). Los
              marcadores de etapa (coste 0) ya NO cuentan: «ok» es trabajo real, no auditoría. */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                <RotateCcw className="h-4 w-4 text-muted-foreground" />
                Últimos 14 días
                <span className="ml-1 inline-flex items-center gap-3 text-xs font-normal text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-amber-500/70" /> encolados
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-sky-500/70" /> investigación
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-emerald-500/70" /> producción
                  </span>
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-2">
              {serie.isPending ? (
                <Skeleton className="h-40 w-full" />
              ) : serie.isError ? (
                <p className="text-sm text-muted-foreground">{mensajeError(serie.error)}</p>
              ) : (
                <SerieProceso serie={serie.data} />
              )}
            </CardContent>
          </Card>

          {/* SIN formularios aquí: los maestros de etapa viven en la tira «Pipeline en
              vivo»; las excepciones por marca, topes y tuning, en el panel lateral de
              ajustes; la SALUD de la infra (daemons/recursos/backups), en /sistema. El
              Monitor opera: cancelar, priorizar, purgar y el kill switch de arriba. */}
        </div>
      )}
    </>
  );
}

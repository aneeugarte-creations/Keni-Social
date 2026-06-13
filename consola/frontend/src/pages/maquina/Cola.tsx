import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowUp,
  Boxes,
  Clock,
  Coins,
  Cpu,
  Layers,
  ListChecks,
  RefreshCw,
  RotateCcw,
  Trash2,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipNivelPresupuesto } from "@/components/comunes/ChipEstado";
import { confirmar } from "@/components/comunes/confirmar";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import { formatearDia, haceSegundos } from "@/lib/fecha";
import { costeUsd, duracion, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { INTERVALO_SERIE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import Produccion from "@/pages/Produccion";
import { SeccionColapsable } from "@/pages/configuracion/SeccionColapsable";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionMetricool } from "@/pages/configuracion/SeccionMetricool";
import {
  DesgloseEconomiaProceso,
  PROC_META,
  resultadoDelDia,
  SerieProceso,
} from "@/pages/monitor/comun";
import { ZonaEstado } from "@/pages/sistema/Doctor";
import { SeccionDaemons } from "@/pages/sistema/SeccionDaemons";
import type {
  ActividadPorDia,
  ActividadPorTipo,
  ActividadTotal,
  ColaJob,
  PresupuestoIA,
  Proceso,
  ResultadoDia,
} from "@/types";

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

/** PRESUPUESTO DIARIO editable in situ (KENI_PRESUPUESTO_TOKENS_DIA, admin): input compacto
 *  que guarda al salir del campo (blur/Enter) con la mutación compartida. 0 = sin límite
 *  (se muestra como «Sin límite»). El valor efectivo llega en el snapshot de la cola. */
function PresupuestoEditable({ valor }: { valor: number }) {
  const guardar = useGuardarAjuste();
  const [num, setNum] = React.useState(String(valor));
  React.useEffect(() => {
    setNum(String(valor));
  }, [valor]);
  const guardarNumero = () => {
    const n = Number(num);
    if (num.trim() !== "" && Number.isFinite(n) && n >= 0 && n !== valor) {
      guardar.mutate({ clave: "KENI_PRESUPUESTO_TOKENS_DIA", valor: Math.trunc(n) });
    } else {
      setNum(String(valor));
    }
  };
  return (
    <label className="inline-flex items-center gap-1.5">
      Presupuesto diario
      <Input
        type="number"
        min={0}
        step="1"
        value={num}
        onChange={(e) => setNum(e.target.value)}
        onBlur={guardarNumero}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        disabled={guardar.isPending}
        className="h-6 w-28 px-2 text-xs tabular-nums"
        aria-label="Presupuesto diario de tokens (0 = sin límite)"
      />
      tokens
      {valor === 0 && <span className="text-muted-foreground/80">(Sin límite)</span>}
    </label>
  );
}

/** ECONOMÍA DE TOKENS de la generación, en el sitio donde se OPERA la cola.
 *
 * El estado (nivel/gasto/restante) viene en el mismo snapshot de la cola. El control rápido
 * es la PARADA DE EMERGENCIA (KENI_GENERACION_PAUSADA, en caliente): corta TODA la
 * generación con IA, incluida la manual (no se encola nada y el worker no reclama nada;
 * lo que corre termina y lo encolado espera — `presupuesto_ia.NIVEL_PAUSADO`). El
 * presupuesto diario se edita aquí mismo; el margen manual vive en el drawer de ajustes de
 * los cockpits («Máquina de contenido», grupo `pipeline_topes`). Mutación PROPIA de este
 * panel (sin compartir el estado «guardando» con otros controles). */
function PanelPresupuesto({
  presupuesto,
  resHoy,
  esAdmin,
}: {
  presupuesto: PresupuestoIA;
  /** Resultados de HOY de la serie (para el desglose de gasto por proceso). Null si no hay. */
  resHoy: ResultadoDia | null;
  esAdmin: boolean;
}) {
  const guardar = useGuardarAjuste();
  const conPresupuesto = presupuesto.presupuesto_tokens_dia > 0;
  const pct = presupuesto.pct_usado;
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
            <Coins className="h-4 w-4 text-muted-foreground" />
            Presupuesto y parada de emergencia
          </CardTitle>
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
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            {esAdmin ? (
              <PresupuestoEditable valor={presupuesto.presupuesto_tokens_dia} />
            ) : (
              <span>
                Presupuesto diario{" "}
                {conPresupuesto
                  ? `${numeroCompacto(presupuesto.presupuesto_tokens_dia)} tokens`
                  : "Sin límite"}
              </span>
            )}
            {conPresupuesto && presupuesto.restante_tokens != null && (
              <span>· restan {numeroCompacto(presupuesto.restante_tokens)}</span>
            )}
            {conPresupuesto && pct != null && <span>· {pct.toFixed(0)}% usado</span>}
          </div>
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
          <div className="space-y-1 text-right">
            <label className="flex items-center justify-end gap-2 text-sm">
              <span
                className={cn(presupuesto.pausada ? "text-destructive" : "text-muted-foreground")}
              >
                {presupuesto.pausada ? "Generación parada" : "Parada de emergencia"}
              </span>
              <Switch
                checked={presupuesto.pausada}
                disabled={guardar.isPending}
                onCheckedChange={(v) =>
                  guardar.mutate({ clave: "KENI_GENERACION_PAUSADA", valor: v })
                }
                aria-label="Parada de emergencia: corta toda la generación con IA, incluida la manual"
              />
            </label>
            <p className="max-w-[26ch] text-[11px] leading-snug text-muted-foreground">
              Corta TODA la generación con IA, incluida la manual; lo que corre termina y lo
              encolado espera.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Fila de KPIs con los CONTEOS del periodo (toda la actividad de IA: generaciones del
 *  pipeline, manuales, runs de agente). Movidos aquí desde Producción: la economía de tokens
 *  vive JUNTA en el dashboard de Workers. */
function KpisTotales({ total }: { total: ActividadTotal }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <TarjetaKpi variante="card" etiqueta="Trabajos IA" valor={numeroCompleto(total.items)} />
      <TarjetaKpi variante="card" etiqueta="Coste total" valor={costeUsd(total.coste_usd)} />
      <TarjetaKpi
        variante="card"
        etiqueta="Tokens"
        valor={numeroCompacto(total.tokens)}
        titulo={numeroCompleto(total.tokens)}
      />
      <TarjetaKpi
        variante="card"
        etiqueta="Tiempo de cómputo"
        valor={total.duration_ms ? duracion(total.duration_ms) : "—"}
      />
    </div>
  );
}

/** Mini-tabla de desglose por TIPO de trabajo (movida desde Producción). */
function DesglosePorTipo({ filas }: { filas: ActividadPorTipo[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por tipo</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Tipo</TableHead>
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Sin actividad por tipo.
                </TableCell>
              </TableRow>
            ) : (
              filas.map((f) => (
                <TableRow key={f.tipo}>
                  <TableCell className="pl-6 font-medium">
                    {f.tipo ? etiquetaTipoGeneracion(f.tipo) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(f.tokens)}>
                    {numeroCompacto(f.tokens)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Mini-tabla de desglose por DÍA, más reciente primero (movida desde Producción). */
function DesglosePorDia({ filas }: { filas: ActividadPorDia[] }) {
  const ordenadas = React.useMemo(
    () => [...filas].sort((a, b) => b.dia.localeCompare(a.dia)),
    [filas],
  );
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por día</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Día</TableHead>
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordenadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                  Sin actividad por día.
                </TableCell>
              </TableRow>
            ) : (
              ordenadas.map((f) => (
                <TableRow key={f.dia}>
                  <TableCell className="pl-6 font-medium">{formatearDia(f.dia)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** TOTALES + desglose por tipo/día de la actividad IA (`GET /api/actividad/agregados`), parte
 *  del bloque «Economía de tokens». Query PROPIA (se monta solo cuando la sección está abierta),
 *  acotada por el switch global de marca como el resto. */
function SeccionEconomiaTotales() {
  const { marcaActiva } = useMarcaActiva();
  const agregados = useQuery({
    queryKey: ["actividad", "agregados", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.actividadAgregados({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });
  if (agregados.isPending) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (agregados.isError) {
    return (
      <BloqueError
        titulo="No se pudieron cargar los totales de gasto"
        mensaje={mensajeError(agregados.error)}
        onReintentar={() => void agregados.refetch()}
        cargando={agregados.isFetching}
      />
    );
  }
  const data = agregados.data;
  return (
    <div className="space-y-4">
      {data?.total && <KpisTotales total={data.total} />}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DesglosePorTipo filas={data?.por_tipo ?? []} />
        <DesglosePorDia filas={data?.por_dia ?? []} />
      </div>
    </div>
  );
}

/**
 * COLA compartida de la máquina (`/maquina/cola`): la vista GLOBAL del worker/cola que
 * comparten los dos motores (Investigación + Producción · ADR 0011). Arriba la ZONA DE
 * ESTADO (el doctor), después los KPIs de capacidad del pool ÚNICO, la economía de tokens
 * (presupuesto editable + parada de emergencia), las tablas en curso/esperando (cancelar/
 * priorizar, admin) y el throughput por día. Sondeo en vivo cada pocos segundos.
 *
 * Relocalizada desde el antiguo Monitor (hub Producción): la TIRA DE ETAPAS (PipelineEnVivo)
 * y el DRAWER DE AJUSTES por etapa NO viven aquí — pertenecen a los cockpits (Investigación
 * y Producción, fases 2B/2C); hoy se montan temporalmente en el cockpit de Producción.
 * El prefiltro `?proceso=investigacion|produccion` acota las tablas al loop pedido (los
 * cockpits enlazan aquí prefiltrado). La INFRA (recursos/daemons/backups/S3) vive en /sistema.
 */
export default function Cola() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const crudoTab = searchParams.get("tab");
  // Prefiltro por PROCESO (`?proceso=investigacion|produccion`): acota las vistas de cola
  // (tablas) al loop pedido. Los cockpits enlazan aquí prefiltrado. Inválido = sin filtro.
  const crudoProceso = searchParams.get("proceso");
  const proceso: Proceso | undefined =
    crudoProceso === "investigacion" || crudoProceso === "produccion" ? crudoProceso : undefined;
  const qc = useQueryClient();
  // La Cola respeta el switch GLOBAL de marca (como Pipelines/Actividad): las listas de
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

  // La antigua pestaña «Salud» (la infra) es ahora la página /sistema: los deep-links
  // viejos (?tab=salud, heredados del Monitor) siguen vivos. (Tras TODOS los hooks, para
  // no variar su orden entre renders.)
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
      <TituloPagina titulo="Workers" icono={ListChecks} />
      <AccionesPagina>
        <MenuAcciones
          ajustesTitulo="Conexiones de métricas"
          // Metricool (conexión de métricas de audiencia) NO gobierna cómo se produce copy/arte:
          // no es del cockpit de Producción. Vive aquí, en la Cola COMPARTIDA por ambos motores,
          // como conexión de la máquina. Solo admin (los secretos de conexión lo son).
          ajustes={esAdmin ? <SeccionMetricool /> : undefined}
        >
          <ItemMenu icono={RefreshCw} onClick={refrescar} disabled={cola.isFetching}>
            Actualizar
          </ItemMenu>
          {esAdmin && (
            <ItemMenu
              icono={Trash2}
              className="text-destructive"
              disabled={purgar.isPending}
              onClick={async () => {
                if (
                  await confirmar({
                    titulo: "Liberar la cola",
                    mensaje:
                      "¿Liberar la cola? Cancela todo lo que esté en vuelo (en curso + esperando) y libera la capacidad.",
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
          )}
        </MenuAcciones>
      </AccionesPagina>

      {/* ZONA DE ESTADO (el doctor, visible para todos): con todo ok, una línea discreta;
          con problemas, los chequeos no-ok (admin solo ve además los suyos) + los temas
          bloqueados del pipeline. Va ARRIBA: es lo primero que responde «¿va bien la máquina?». */}
      <div className="mb-6">
        <ZonaEstado esAdmin={esAdmin} marca={marcaActiva ?? undefined} />
      </div>

      {/* Dashboard de Workers, TODO JUNTO en secciones colapsables: (a) el pool reactivo
          (claude -p), (b) la economía de tokens y (c) los agentes (daemons que gastan tokens /
          actúan en el flujo). La infraestructura que NO toca el flujo vive en Sistema. */}
      <div className="space-y-2">
        {/* (a) POOL REACTIVO: los workers de claude -p bajo demanda. */}
        <SeccionColapsable
          titulo="Pool reactivo (claude -p)"
          abiertaInicial
          descripcion="Los workers que ejecutan claude -p bajo demanda: capacidad del pool compartido, jobs en curso/esperando, presupuesto y parada de emergencia."
        >
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
                    <strong className={PROC_META[proceso].texto}>
                      {PROC_META[proceso].etiqueta}
                    </strong>{" "}
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
              MISMO pool: estos KPIs son la capacidad total. Con marca activa se avisa: la
              capacidad no se filtra (las tablas sí). */}
          {marcaActiva && (
            <p className="text-xs text-muted-foreground">
              Los KPIs de capacidad son globales (no se filtran por{" "}
              {nombreActiva ?? marcaActiva}); las tablas de jobs de abajo sí.
            </p>
          )}
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

          {/* Economía de tokens: estado vivo + presupuesto editable + parada de emergencia
              (el margen manual y los topes por etapa, en el drawer de ajustes de los cockpits). */}
          {cola.data.presupuesto && (
            <PanelPresupuesto
              presupuesto={cola.data.presupuesto}
              resHoy={resultadoDelDia(serie.data, cola.data.presupuesto.dia)}
              esAdmin={esAdmin}
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

            </div>
          )}
        </SeccionColapsable>

        {/* (b) ECONOMÍA DE TOKENS, TODO JUNTO: totales + desglose por tipo/día (movidos de
            Producción) y el throughput por proceso de los últimos 14 días. El gasto de HOY por
            proceso vive en el panel de presupuesto del pool reactivo. */}
        <SeccionColapsable
          titulo="Economía de tokens"
          abiertaInicial
          descripcion="Cuánto gasta la máquina, junto: por proceso (Investigación vs Producción) y por tipo de trabajo; hoy y en los últimos 14 días."
        >
          <div className="space-y-4">
            <SeccionEconomiaTotales />

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
          </div>
        </SeccionColapsable>

        {/* (c) ACTIVIDAD: el FEED de todo lo que la máquina produce —runs del pipeline + actividad
            suelta, con coste/tokens/tiempo y detalle entrada/salida—. Es el historial de ejecución,
            compañero natural del pool en vivo y de la economía de tokens. Reutiliza la página
            Producción en modo `embebido` (sin su título/menú/enlace propios); cada tarjeta sigue
            enlazando a su detalle (`/datos/produccion/pipelines/:id` · `/actividad/:id`). */}
        <SeccionColapsable
          titulo="Actividad"
          abiertaInicial
          descripcion="El feed de lo que produce la máquina: runs del pipeline y actividad suelta de IA, con coste, tokens y tiempo. Cada tarjeta abre su detalle de entrada/salida."
        >
          <Produccion embebido />
        </SeccionColapsable>

        {/* (d) AGENTES: los daemons que gastan tokens / actúan en el flujo, agrupados por motor
            (Investigación / Producción / Flujo). La infra (métricas, GC, reaper…) vive en
            Sistema. Reusa SeccionDaemons con un filtro por `grupo` (sin duplicar). */}
        <SeccionColapsable
          titulo="Agentes (gastan tokens / actúan en el flujo)"
          abiertaInicial
          descripcion="Los daemons de Investigación, Producción y Flujo: estado, último barrido, intervalo y «Barrer ahora». La infraestructura vive en Sistema."
        >
          <SeccionDaemons
            grupos={["investigacion", "produccion", "flujo"]}
            agrupar
            titulo="Agentes"
          />
        </SeccionColapsable>
      </div>
    </>
  );
}

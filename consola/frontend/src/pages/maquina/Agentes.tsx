import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  Clock,
  Cpu,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
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
import { formatearDia, tiempoRelativo } from "@/lib/fecha";
import { costeUsd, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { INTERVALO_SERIE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import Produccion from "@/pages/Produccion";
import { Kpi, PanelPresupuesto, TablaJobs } from "@/pages/maquina/cola-comun";
import { SeccionColapsable } from "@/pages/configuracion/SeccionColapsable";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import { PROC_META, resultadoDelDia, SerieProceso } from "@/pages/monitor/comun";
import { ZonaEstado } from "@/pages/sistema/Doctor";
import { ChipEstadoDaemon, SeccionDaemons } from "@/pages/sistema/SeccionDaemons";
import type {
  ActividadPorDia,
  ActividadPorTipo,
  ActividadProcesoBloque,
  ColaMonitor,
  ColaSerie,
  LatidoDaemon,
  Proceso,
} from "@/types";

/** Los dos motores de la máquina (ADR 0011), en orden de flujo. */
const MOTORES: Proceso[] = ["investigacion", "produccion"];

/** Agente(s) IA (clase=ia) de cada motor: etiqueta humana. El on/off, estado y barrido vienen del
 *  latido del daemon (campo `clase`/`motor`); el resto del control (editar prompt, barrer, log)
 *  vive en la página de detalle del agente (`/maquina/agentes/{daemon}`), a la que la tarjeta
 *  enlaza entera. */
type AgenteMeta = {
  daemon: string;
  etiqueta: string;
};
const AGENTES_IA: Record<Proceso, AgenteMeta[]> = {
  investigacion: [{ daemon: "investigacion", etiqueta: "Investigación" }],
  produccion: [{ daemon: "produccion", etiqueta: "Producción" }],
};

/** Mini-tabla de desglose por TIPO de trabajo (de un motor). */
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

/** Mini-tabla de desglose por DÍA, más reciente primero (incluye tokens). */
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
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordenadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
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

/** TARJETA de un AGENTE IA (clase=ia) de un motor: el agente PROACTIVO que corre `claude -p`.
 *  La tarjeta ENTERA es un enlace a su página de detalle (`/maquina/agentes/{daemon}`), donde
 *  vive todo el control (editar prompt, barrer, log). Aquí queda limpia: icono, nombre, badge IA,
 *  estado, último barrido y el toggle on/off in-place (con stopPropagation para no navegar al
 *  togglear). Nada de expand ni botones internos. */
function TarjetaAgenteIA({
  latido,
  meta,
  onToggle,
  guardandoClave,
}: {
  latido: LatidoDaemon;
  meta: AgenteMeta;
  onToggle: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
}) {
  const solicitado = latido.barrido_solicitado !== "";
  const barrido = latido.ultimo_barrido ? tiempoRelativo(latido.ultimo_barrido) : "nunca";
  // El toggle no debe navegar al detalle: corta la propagación del clic/teclado del enlace.
  const noNavegar = (e: React.SyntheticEvent) => e.stopPropagation();
  return (
    <Link
      to={`/maquina/agentes/${meta.daemon}`}
      className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <Card className="cursor-pointer border-border transition-colors hover:border-keni-300">
        <CardHeader className="p-4 pb-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Bot className="h-4 w-4 text-sky-600" aria-hidden="true" />
                {meta.etiqueta}
                <Badge
                  variant="outline"
                  className="border-transparent bg-sky-500/15 text-[10px] text-sky-600 dark:text-sky-400"
                >
                  IA
                </Badge>
              </CardTitle>
            </div>
            {/* Toggle on/off IN-PLACE (clave_gate); no debe navegar al detalle al clicarlo. */}
            <div onClick={noNavegar} onKeyDown={noNavegar}>
              {latido.clave_gate ? (
                <Switch
                  checked={latido.activo}
                  disabled={guardandoClave === latido.clave_gate}
                  onCheckedChange={(v) => onToggle(latido.clave_gate as string, v)}
                  aria-label={`Encender/apagar el agente ${meta.daemon}`}
                />
              ) : (
                <span className="text-xs text-muted-foreground">Siempre activo</span>
              )}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <ChipEstadoDaemon estado={latido.estado} />
            {solicitado && (
              <Badge
                variant="outline"
                className="border-transparent bg-sky-500/15 text-sky-600 dark:text-sky-400"
              >
                Barrido solicitado
              </Badge>
            )}
            <span>· último barrido {barrido}</span>
          </div>
        </CardHeader>
      </Card>
    </Link>
  );
}

/** Bloque «Agentes IA» de un motor: las tarjetas de los daemons clase=ia de ese motor (desde el
 *  latido del API; el meta —etiqueta/subtítulo— se cruza por nombre). Solo admin (endpoint admin). */
function AgentesIaMotor({
  motor,
  daemons,
  onToggle,
  guardandoClave,
}: {
  motor: Proceso;
  daemons: LatidoDaemon[];
  onToggle: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
}) {
  // Cruza el meta (etiqueta) con el latido real; el orden lo fija AGENTES_IA.
  const porNombre = new Map(daemons.map((d) => [d.daemon, d]));
  const tarjetas = AGENTES_IA[motor]
    .map((meta) => ({ meta, latido: porNombre.get(meta.daemon) }))
    .filter((t): t is { meta: AgenteMeta; latido: LatidoDaemon } => !!t.latido);
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Agentes IA (proactivos)
      </h3>
      {tarjetas.length === 0 ? (
        <p className="text-sm text-muted-foreground">Sin latidos</p>
      ) : (
        tarjetas.map(({ meta, latido }) => (
          <TarjetaAgenteIA
            key={meta.daemon}
            latido={latido}
            meta={meta}
            onToggle={onToggle}
            guardandoClave={guardandoClave}
          />
        ))
      )}
    </div>
  );
}

/** Bloque «Workers» de un motor: el trozo del POOL COMPARTIDO atribuible a este proceso
 *  (procesando/pendientes de `por_proceso[motor]`) + las filas en curso/esperando de ESTE motor.
 *  La capacidad es compartida (se ve en la banda global); aquí solo la parte de este motor. */
function WorkersMotor({
  motor,
  cola,
  esAdmin,
  onCancelar,
  cancelandoId,
  onPriorizar,
  priorizandoId,
}: {
  motor: Proceso;
  cola: ColaMonitor;
  esAdmin: boolean;
  onCancelar: (genId: string) => void;
  cancelandoId: string | null;
  onPriorizar: (genId: string) => void;
  priorizandoId: string | null;
}) {
  const pp = cola.por_proceso?.[motor] ?? { procesando: 0, pendientes: 0 };
  const enCurso = cola.en_curso.filter((j) => j.proceso === motor);
  const esperando = cola.esperando.filter((j) => j.proceso === motor);
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Workers (reactivos)
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <Kpi
          icono={Cpu}
          titulo="En curso"
          valor={pp.procesando}
          tono={pp.procesando > 0 ? "ok" : undefined}
        />
        <Kpi
          icono={Clock}
          titulo="En cola"
          valor={pp.pendientes}
          tono={pp.pendientes > 0 ? "espera" : undefined}
        />
      </div>
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Activity className="h-4 w-4 text-sky-600" />
            En curso ({enCurso.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {enCurso.length === 0 ? (
            <p className="p-4 pt-0 text-sm text-muted-foreground">—</p>
          ) : (
            <TablaJobs
              jobs={enCurso}
              mostrarWorker
              esAdmin={esAdmin}
              onCancelar={onCancelar}
              cancelandoId={cancelandoId}
            />
          )}
        </CardContent>
      </Card>
      {esperando.length > 0 && (
        <Card className="border-amber-500/30">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-500">
              <Clock className="h-4 w-4 text-amber-600" />
              Esperando ({esperando.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <TablaJobs
              jobs={esperando}
              mostrarWorker={false}
              esAdmin={esAdmin}
              onCancelar={onCancelar}
              cancelandoId={cancelandoId}
              onPriorizar={onPriorizar}
              priorizandoId={priorizandoId}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** Bloque «Economía (tokens)» de un motor: el DESGLOSE SEPARADO POR MOTOR (de
 *  `agregados.por_proceso[motor]`): totales + serie del proceso + por tipo + por día. */
function EconomiaMotor({
  motor,
  bloque,
  serie,
  cargando,
}: {
  motor: Proceso;
  bloque: ActividadProcesoBloque | undefined;
  serie: ColaSerie | undefined;
  cargando: boolean;
}) {
  const total = bloque?.total;
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Economía (tokens) de {PROC_META[motor].etiqueta}
      </h3>
      {cargando ? (
        <Skeleton className="h-24 w-full rounded-xl" />
      ) : (
        <div className="grid grid-cols-3 gap-3">
          <TarjetaKpi
            variante="card"
            etiqueta="Trabajos IA"
            valor={numeroCompleto(total?.items ?? 0)}
          />
          <TarjetaKpi
            variante="card"
            etiqueta="Tokens"
            valor={numeroCompacto(total?.tokens ?? 0)}
            titulo={numeroCompleto(total?.tokens ?? 0)}
          />
          <TarjetaKpi variante="card" etiqueta="Coste" valor={costeUsd(total?.coste_usd ?? 0)} />
        </div>
      )}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <RotateCcw className="h-4 w-4 text-muted-foreground" />
            Últimos 14 días
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-2">
          {serie ? (
            <SerieProceso serie={serie} soloProceso={motor} />
          ) : (
            <Skeleton className="h-32 w-full" />
          )}
        </CardContent>
      </Card>
      <DesglosePorTipo filas={bloque?.por_tipo ?? []} />
      <DesglosePorDia filas={bloque?.por_dia ?? []} />
    </div>
  );
}

/**
 * COLUMNA de un MOTOR (Investigación o Producción). De arriba abajo: (1) agente(s) IA
 * proactivo(s) con su control in-place, (2) los Workers reactivos de ese proceso, (3) la
 * economía de tokens del motor (desglose separado), y (4) los servicios de la máquina NO-IA del
 * motor, en una sección APARTE y visualmente distinta. Los bloques (1) y (4) son de admin (leen
 * el endpoint admin de daemons); Workers y economía los ve también un editor.
 */
function ColumnaMotor({
  motor,
  esAdmin,
  daemons,
  daemonsError,
  cola,
  serie,
  bloqueEconomia,
  economiaCargando,
  onToggleDaemon,
  guardandoClave,
  onCancelar,
  cancelandoId,
  onPriorizar,
  priorizandoId,
}: {
  motor: Proceso;
  esAdmin: boolean;
  daemons: LatidoDaemon[] | null;
  daemonsError: boolean;
  cola: ColaMonitor;
  serie: ColaSerie | undefined;
  bloqueEconomia: ActividadProcesoBloque | undefined;
  economiaCargando: boolean;
  onToggleDaemon: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
  onCancelar: (genId: string) => void;
  cancelandoId: string | null;
  onPriorizar: (genId: string) => void;
  priorizandoId: string | null;
}) {
  const meta = PROC_META[motor];
  return (
    <section className="space-y-5">
      <h2 className={cn("flex items-center gap-2 text-lg font-semibold", meta.texto)}>
        <span className={cn("h-2.5 w-2.5 rounded-full", meta.barra)} aria-hidden="true" />
        {meta.etiqueta}
      </h2>

      {/* 1 · Agente(s) IA proactivo(s) — solo admin (endpoint de daemons). */}
      {esAdmin &&
        (daemonsError ? (
          <p className="text-sm text-muted-foreground">No se pudo leer el estado de los agentes.</p>
        ) : daemons === null ? (
          <Skeleton className="h-32 w-full rounded-xl" />
        ) : (
          <AgentesIaMotor
            motor={motor}
            daemons={daemons}
            onToggle={onToggleDaemon}
            guardandoClave={guardandoClave}
          />
        ))}

      {/* 2 · Workers reactivos del motor. */}
      <WorkersMotor
        motor={motor}
        cola={cola}
        esAdmin={esAdmin}
        onCancelar={onCancelar}
        cancelandoId={cancelandoId}
        onPriorizar={onPriorizar}
        priorizandoId={priorizandoId}
      />

      {/* 3 · Economía de tokens del motor (desglose separado). */}
      <EconomiaMotor
        motor={motor}
        bloque={bloqueEconomia}
        serie={serie}
        cargando={economiaCargando}
      />

      {/* 4 · Servicios de la máquina NO-IA del motor — sección aparte y distinta. */}
      {esAdmin && (
        <div className="rounded-xl border border-dashed border-border/70 bg-muted/30 p-2">
          <SeccionDaemons
            clases={["maquina"]}
            motor={motor}
            titulo="Servicios (no consumen IA)"
          />
        </div>
      )}
    </section>
  );
}

/**
 * Página AGENTES (`/maquina/agentes`): SOLO los procesos de IA de la máquina de contenido,
 * organizados en DOS COLUMNAS POR MOTOR (Investigación | Producción). Arriba, una BANDA GLOBAL
 * con lo compartido entre ambos motores una sola vez: la zona de estado (el doctor), el
 * presupuesto editable + la parada de emergencia (globales) y los dos KPIs de cómputo (en
 * curso / en cola), con enlace a «Cómputo y cola» para verla por dentro. Cada columna trae sus
 * tarjetas de agente IA (toggle in-place, clic = su detalle), sus Workers reactivos, su economía
 * de tokens desglosada y, aparte, sus servicios NO-IA. Sondeo en vivo.
 *
 * El prefiltro `?proceso=investigacion|produccion` (los cockpits enlazan aquí) ENFOCA la página
 * a un solo motor: muestra su columna a ancho completo. La actividad (feed cross-motor) vive
 * plegada al final.
 */
export default function Agentes() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const crudoTab = searchParams.get("tab");
  // Prefiltro por PROCESO (`?proceso=…`): enfoca la página a un solo motor (columna a ancho
  // completo). Inválido = ambas columnas.
  const crudoProceso = searchParams.get("proceso");
  const proceso: Proceso | undefined =
    crudoProceso === "investigacion" || crudoProceso === "produccion" ? crudoProceso : undefined;
  const qc = useQueryClient();
  // Respeta el switch GLOBAL de marca: las listas de jobs y la economía se acotan a la marca
  // activa (null = "Todas", solo admin). La capacidad del pool y el presupuesto son globales.
  const { marcaActiva } = useMarcaActiva();
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
  // Agregados de actividad IA (totales + por_proceso): la economía DESGLOSADA por motor.
  const agregados = useQuery({
    queryKey: ["actividad", "agregados", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.actividadAgregados({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });
  // Latidos de los daemons (agentes IA proactivos + servicios NO-IA): endpoint de ADMIN, así que
  // solo se pide para admin. Mismo queryKey que SeccionDaemons => una sola petición (dedupe).
  const daemonsQuery = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_VIVO_MS,
    enabled: esAdmin,
  });

  // Encendido/apagado IN-PLACE de un daemon: la mutación COMPARTIDA de ajustes; tras guardar,
  // refresca los latidos para que el switch/estado reflejen el nuevo gate al instante.
  const guardarAjuste = useGuardarAjuste();
  const onToggleDaemon = (clave: string, valor: boolean) =>
    guardarAjuste.mutate(
      { clave, valor },
      { onSuccess: () => void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] }) },
    );
  const guardandoClave = guardarAjuste.isPending ? (guardarAjuste.variables?.clave ?? null) : null;

  const refrescar = () => {
    void qc.invalidateQueries({ queryKey: ["actividad", "cola"] });
    if (esAdmin) void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] });
  };

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

  if (crudoTab === "salud") return <Navigate to="/sistema" replace />;

  const quitarProceso = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("proceso");
    setSearchParams(params, { replace: true });
  };

  // Motores a pintar: enfocado a uno (?proceso=) o ambos.
  const motores: Proceso[] = proceso ? [proceso] : MOTORES;
  const daemons = daemonsQuery.data?.daemons ?? null;

  return (
    <>
      <TituloPagina titulo="Agentes" icono={Bot} />
      <AccionesPagina>
        <MenuAcciones>
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
          )}
        </MenuAcciones>
      </AccionesPagina>

      {/* ===== BANDA GLOBAL (lo compartido por ambos motores, una sola vez) ===== */}
      {/* Doctor: con todo ok, una línea discreta; con problemas, los chequeos no-ok. */}
      <div className="mb-4">
        <ZonaEstado esAdmin={esAdmin} marca={marcaActiva ?? undefined} />
      </div>

      {/* Prefiltro de proceso (?proceso=): la página queda enfocada a ese motor. */}
      {proceso && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>
            Enfocado a{" "}
            <strong className={PROC_META[proceso].texto}>{PROC_META[proceso].etiqueta}</strong>.
          </span>
          <Button variant="ghost" size="sm" onClick={quitarProceso}>
            Ver ambos motores
          </Button>
        </div>
      )}

      <div className="mb-6 space-y-4">
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
          <>
            {/* Presupuesto + parada de emergencia (GLOBALES). */}
            {cola.data.presupuesto && (
              <PanelPresupuesto
                presupuesto={cola.data.presupuesto}
                resHoy={resultadoDelDia(serie.data, cola.data.presupuesto.dia)}
                esAdmin={esAdmin}
              />
            )}

            {/* Cómputo de la máquina: el ÚNICO límite real son los slots (concurrencia de
                `claude -p`); la cola que espera un slot no tiene tope. Cada contador es
                clicable: lleva a «Cómputo y cola» (detalle y control de la cola por dentro). */}
            <div className="grid grid-cols-2 gap-3">
              <Kpi
                icono={Cpu}
                titulo="En curso"
                valor={`${cola.data.procesando} / ${cola.data.capacidad.max_jobs}`}
                tono={cola.data.procesando >= cola.data.capacidad.max_jobs ? "alerta" : undefined}
                href={`/maquina/computo${proceso ? `?proceso=${proceso}` : ""}`}
              />
              <Kpi
                icono={Clock}
                titulo="En cola"
                valor={cola.data.conteo.pendientes}
                tono={cola.data.conteo.pendientes > 0 ? "espera" : undefined}
                href={`/maquina/computo${proceso ? `?proceso=${proceso}` : ""}`}
              />
            </div>
          </>
        )}
      </div>

      {/* ===== DOS COLUMNAS POR MOTOR ===== */}
      {cola.data && (
        <div
          className={cn(
            "grid grid-cols-1 gap-8",
            motores.length > 1 && "xl:grid-cols-2 xl:gap-6",
          )}
        >
          {motores.map((m) => (
            <ColumnaMotor
              key={m}
              motor={m}
              esAdmin={esAdmin}
              daemons={daemons}
              daemonsError={daemonsQuery.isError}
              cola={cola.data}
              serie={serie.data}
              bloqueEconomia={agregados.data?.por_proceso?.[m]}
              economiaCargando={agregados.isPending}
              onToggleDaemon={onToggleDaemon}
              guardandoClave={guardandoClave}
              onCancelar={(id) => cancelar.mutate(id)}
              cancelandoId={cancelandoId}
              onPriorizar={(id) => priorizar.mutate(id)}
              priorizandoId={priorizandoId}
            />
          ))}
        </div>
      )}

      {/* ===== ACTIVIDAD (feed cross-motor, plegado al final) ===== */}
      <div className="mt-8">
        <SeccionColapsable titulo="Actividad">
          <Produccion embebido />
        </SeccionColapsable>
      </div>
    </>
  );
}

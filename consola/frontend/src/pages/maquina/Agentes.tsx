import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowUp,
  Bot,
  Boxes,
  ChevronDown,
  Clock,
  Coins,
  Cpu,
  ExternalLink,
  FileText,
  Layers,
  Play,
  RefreshCw,
  RotateCcw,
  Trash2,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
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
import { formatearDia, haceSegundos, tiempoRelativo } from "@/lib/fecha";
import { costeUsd, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { INTERVALO_SERIE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import Produccion from "@/pages/Produccion";
import { SeccionColapsable } from "@/pages/configuracion/SeccionColapsable";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import {
  DesgloseEconomiaProceso,
  PROC_META,
  resultadoDelDia,
  SerieProceso,
} from "@/pages/monitor/comun";
import { ZonaEstado } from "@/pages/sistema/Doctor";
import {
  ChipEstadoDaemon,
  formatoIntervalo,
  SeccionDaemons,
} from "@/pages/sistema/SeccionDaemons";
import type {
  ActividadPorDia,
  ActividadPorTipo,
  ActividadProcesoBloque,
  ColaJob,
  ColaMonitor,
  ColaSerie,
  LatidoDaemon,
  PresupuestoIA,
  Proceso,
  ResultadoDia,
} from "@/types";

/** Los dos motores de la máquina (ADR 0011), en orden de flujo. */
const MOTORES: Proceso[] = ["investigacion", "produccion"];

/** Agente(s) IA (clase=ia) de cada motor: etiqueta humana + prompt(s) de la Biblioteca que
 *  editan in-place desde su tarjeta (el back NO expone el docId del prompt: vive aquí). El
 *  on/off, estado y barrido vienen del latido del daemon (campo `clase`/`motor`), no de aquí. */
type AgenteMeta = {
  daemon: string;
  etiqueta: string;
  sub: string;
  prompts: { etiqueta: string; docId: string }[];
};
const AGENTES_IA: Record<Proceso, AgenteMeta[]> = {
  investigacion: [
    {
      daemon: "investigacion",
      etiqueta: "Investigación",
      sub: "Criba y verifica las fuentes que alimentan el motor de reutilizar.",
      prompts: [{ etiqueta: "Prompt de validación", docId: "prompt/validacion" }],
    },
  ],
  produccion: [
    {
      daemon: "produccion",
      etiqueta: "Producción",
      sub: "Redacta el copy y genera el arte de los borradores.",
      prompts: [
        { etiqueta: "Prompt de copy", docId: "prompt/copy" },
        { etiqueta: "Prompt de arte", docId: "prompt/arte" },
      ],
    },
    {
      daemon: "sugerencias",
      etiqueta: "Sugerencias editoriales",
      sub: "Digest editorial con IA: ideas y ángulos para el equipo.",
      prompts: [{ etiqueta: "Prompt de sugerencias", docId: "prompt/sugerencias" }],
    },
  ],
};

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
 *  que guarda al salir del campo (blur/Enter). 0 = sin límite. */
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

/** PRESUPUESTO + gasto de HOY + PARADA DE EMERGENCIA: cabeza GLOBAL de la economía (ambos
 *  motores comparten presupuesto y kill switch). El gasto de hoy se desglosa por proceso
 *  (Investigación vs Producción). El presupuesto diario se edita aquí (admin) y la parada de
 *  emergencia (KENI_GENERACION_PAUSADA, en caliente) corta TODA la generación con IA. */
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
          <span className="text-xs text-muted-foreground">· global, compartido por ambos motores</span>
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
 *  Cabecera siempre visible (estado, último barrido, toggle on/off in-place); al CLICAR la
 *  tarjeta se EXPANDE y deja ajustar el resto AHÍ MISMO (editar su prompt, forzar un barrido) y
 *  un enlace «Ver log / detalle» a su página de detalle. Nada de drawer escondido. */
function TarjetaAgenteIA({
  latido,
  meta,
  onToggle,
  guardandoClave,
  onBarrer,
  barriendo,
  onAbrirPrompt,
}: {
  latido: LatidoDaemon;
  meta: AgenteMeta;
  onToggle: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
  onBarrer: (daemon: string) => void;
  barriendo: string | null;
  onAbrirPrompt: (docId: string) => void;
}) {
  const [abierta, setAbierta] = React.useState(false);
  const solicitado = latido.barrido_solicitado !== "";
  const barrido = latido.ultimo_barrido ? tiempoRelativo(latido.ultimo_barrido) : "nunca";
  // Detiene la propagación para que interactuar con los controles NO pliegue la tarjeta.
  const noPlegar = (e: React.SyntheticEvent) => e.stopPropagation();
  return (
    <Card
      role="button"
      tabIndex={0}
      aria-expanded={abierta}
      onClick={() => setAbierta((v) => !v)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setAbierta((v) => !v);
        }
      }}
      className="cursor-pointer border-sky-500/20 transition-colors hover:border-sky-500/40"
    >
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
            <p className="mt-0.5 text-xs text-muted-foreground">{meta.sub}</p>
          </div>
          {/* Toggle on/off IN-PLACE (clave_gate); no debe plegar la tarjeta al clicarlo. */}
          <div onClick={noPlegar} onKeyDown={noPlegar}>
            {latido.clave_gate ? (
              <Switch
                checked={latido.activo}
                disabled={guardandoClave === latido.clave_gate}
                onCheckedChange={(v) => onToggle(latido.clave_gate as string, v)}
                aria-label={`Encender/apagar el agente ${meta.daemon}`}
              />
            ) : (
              <span className="text-xs text-muted-foreground" title="Sin interruptor: corre siempre.">
                Siempre activo
              </span>
            )}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <ChipEstadoDaemon estado={latido.estado} />
          {solicitado && (
            <Badge
              variant="outline"
              className="border-transparent bg-sky-500/15 text-sky-600 dark:text-sky-400"
              title="El agente barrerá en su siguiente tick (≤ ~1 min)."
            >
              Barrido solicitado
            </Badge>
          )}
          <span>· último barrido {barrido}</span>
          <ChevronDown
            aria-hidden
            className={cn("ml-auto h-4 w-4 transition-transform", abierta && "rotate-180")}
          />
        </div>
      </CardHeader>
      {abierta && (
        <CardContent className="space-y-3 p-4 pt-0" onClick={noPlegar} onKeyDown={noPlegar}>
          <div className="text-xs text-muted-foreground">
            Intervalo {formatoIntervalo(latido.intervalo_seg)} · {latido.barridos} barridos
            {latido.errores > 0 && <span className="text-red-500"> · {latido.errores} err</span>}
            {latido.error_txt && latido.estado === "error" && (
              <span className="block truncate" title={latido.error_txt}>
                {latido.error_txt}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {meta.prompts.map((p) => (
              <Button
                key={p.docId}
                variant="outline"
                size="sm"
                onClick={() => onAbrirPrompt(p.docId)}
              >
                <FileText className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                {p.etiqueta}
              </Button>
            ))}
            {latido.barrible && (
              <Button
                variant="ghost"
                size="sm"
                disabled={barriendo === meta.daemon || solicitado}
                title={
                  solicitado
                    ? "Ya hay un barrido solicitado pendiente."
                    : "Fuerza un barrido inmediato (sin esperar al intervalo)."
                }
                onClick={() => onBarrer(meta.daemon)}
              >
                <Play className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                Barrer ahora
              </Button>
            )}
            <Button asChild variant="ghost" size="sm">
              <Link to={`/maquina/agentes/${meta.daemon}`}>
                <ExternalLink className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                Ver log / detalle
              </Link>
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

/** Bloque «Agentes IA» de un motor: las tarjetas de los daemons clase=ia de ese motor (desde el
 *  latido del API; el meta —prompt/etiqueta— se cruza por nombre). Solo admin (endpoint admin). */
function AgentesIaMotor({
  motor,
  daemons,
  onToggle,
  guardandoClave,
  onBarrer,
  barriendo,
  onAbrirPrompt,
}: {
  motor: Proceso;
  daemons: LatidoDaemon[];
  onToggle: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
  onBarrer: (daemon: string) => void;
  barriendo: string | null;
  onAbrirPrompt: (docId: string) => void;
}) {
  // Cruza el meta (prompt/etiqueta) con el latido real; el orden lo fija AGENTES_IA.
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
        <p className="text-sm text-muted-foreground">
          No hay latidos del agente aún (proceso sin iniciar o recién desplegado).
        </p>
      ) : (
        tarjetas.map(({ meta, latido }) => (
          <TarjetaAgenteIA
            key={meta.daemon}
            latido={latido}
            meta={meta}
            onToggle={onToggle}
            guardandoClave={guardandoClave}
            onBarrer={onBarrer}
            barriendo={barriendo}
            onAbrirPrompt={onAbrirPrompt}
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
      <p className="text-xs text-muted-foreground">
        El pool de cómputo es compartido (capacidad arriba); esto es la parte de{" "}
        {PROC_META[motor].etiqueta}.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Kpi
          icono={Cpu}
          titulo="En curso"
          valor={pp.procesando}
          subtitulo="claude -p de este motor"
          tono={pp.procesando > 0 ? "ok" : undefined}
        />
        <Kpi
          icono={Clock}
          titulo="En cola"
          valor={pp.pendientes}
          subtitulo="esperando slot"
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
            <p className="p-4 pt-0 text-sm text-muted-foreground">
              Ningún <code>claude -p</code> de {PROC_META[motor].etiqueta} corriendo ahora.
            </p>
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
  onBarrerDaemon,
  barriendoDaemon,
  onAbrirPrompt,
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
  onBarrerDaemon: (daemon: string) => void;
  barriendoDaemon: string | null;
  onAbrirPrompt: (docId: string) => void;
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
            onBarrer={onBarrerDaemon}
            barriendo={barriendoDaemon}
            onAbrirPrompt={onAbrirPrompt}
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
            descripcion={`Alimentan/operan el motor de ${meta.etiqueta} sin modelo (feeds, scheduler, GC).`}
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
 * presupuesto editable + la parada de emergencia (globales) y la capacidad del pool. Cada
 * columna trae sus agentes IA proactivos (control + prompt in-place), sus Workers reactivos, su
 * economía de tokens desglosada y, aparte, sus servicios NO-IA. Sondeo en vivo.
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
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [cancelandoId, setCancelandoId] = React.useState<string | null>(null);
  const [priorizandoId, setPriorizandoId] = React.useState<string | null>(null);
  // Overlay «editar prompt» ÚNICO para toda la página (lo abren las tarjetas de agente IA).
  const [promptDoc, setPromptDoc] = React.useState<string | null>(null);

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

  const barrerDaemon = useMutation({
    mutationFn: (daemon: string) => api.sistemaDaemonBarrer(daemon),
    onSuccess: (r) => {
      toast.success(`Barrido de «${r.daemon}» solicitado: correrá en su siguiente tick.`);
      void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const barriendoDaemon = barrerDaemon.isPending ? (barrerDaemon.variables ?? null) : null;

  const refrescar = () => {
    void qc.invalidateQueries({ queryKey: ["actividad", "cola"] });
    if (esAdmin) void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] });
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

  // Deep-link viejo del Monitor (`?tab=salud` = la infra): la infra es ahora /sistema. (Tras
  // TODOS los hooks, para no variar su orden entre renders.)
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

            {/* Capacidad del POOL GLOBAL (compartido por ambos motores). */}
            {cola.data.cola_llena && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  La cola está al tope ({cola.data.conteo.activos}/{cola.data.capacidad.tope}).
                  {esAdmin && " Puedes purgarla para vaciarla."}
                </span>
              </div>
            )}
            {marcaActiva && (
              <p className="text-xs text-muted-foreground">
                La capacidad del pool es global (no se filtra por {nombreActiva ?? marcaActiva});
                las listas de jobs de cada motor sí.
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
              onBarrerDaemon={(d) => barrerDaemon.mutate(d)}
              barriendoDaemon={barriendoDaemon}
              onAbrirPrompt={setPromptDoc}
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
        <SeccionColapsable
          titulo="Actividad"
          descripcion="El historial de ejecución cross-motor: runs del pipeline y actividad suelta de IA."
        >
          <Produccion embebido />
        </SeccionColapsable>
      </div>

      {/* Overlay «editar prompt» de las tarjetas de agente IA (in-place, sin navegar). */}
      <EditorPromptOverlay
        docId={promptDoc}
        abierto={promptDoc !== null}
        onCerrar={() => setPromptDoc(null)}
      />
    </>
  );
}

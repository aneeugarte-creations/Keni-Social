/**
 * Piezas COMPARTIDAS de la sala de máquinas entre Cómputo (`/maquina/agentes`) y Economía
 * (`/maquina/economia`): la tarjeta KPI, la tabla de jobs activos (con sus acciones admin) y el
 * panel de presupuesto + parada de emergencia. Viven aquí para que ambas superficies reusen el
 * mismo render y el mismo contrato sin duplicarlo (Cómputo usa Kpi/TablaJobs; Economía, el panel
 * de presupuesto).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  ArrowUpToLine,
  Coins,
  type Cpu,
  Gauge,
  PauseCircle,
  RotateCcw,
  SlidersHorizontal,
  Trash2,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { ChipNivelPresupuesto } from "@/components/comunes/ChipEstado";
import { confirmar, elegir } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, mensajeError } from "@/lib/api";
import { haceSegundos } from "@/lib/fecha";
import { costeUsd, numeroCompacto } from "@/lib/formato";
import { cn } from "@/lib/utils";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import { PROC_META } from "@/pages/monitor/comun";
import type {
  Backlog,
  BacklogEstimado,
  BacklogEtapas,
  ColaDesglose,
  ColaJob,
  ConteoCola,
  GateDiarioIA,
  PresupuestoIA,
  PresupuestoProcesoIA,
  Proceso,
} from "@/types";

/** Tarjeta KPI: icono, valor grande y subtítulo. `tono` colorea el valor ante alerta. Si se
 *  pasa `href`, la tarjeta ENTERA es un enlace con realce naranja al hover, en vez de un botón
 *  aparte. */
export function Kpi({
  icono: Icono,
  titulo,
  valor,
  subtitulo,
  tono,
  href,
}: {
  icono: typeof Cpu;
  titulo: string;
  valor: React.ReactNode;
  subtitulo?: React.ReactNode;
  tono?: "alerta" | "ok" | "espera";
  /** Si se pasa, la tarjeta navega aquí al hacer click (con realce de borde naranja). */
  href?: string;
}) {
  const cuerpo = (
    <Card className={cn("h-full", href && "transition-colors hover:border-keni-300")}>
      <CardContent className="space-y-1.5 p-5">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icono className="h-4 w-4" aria-hidden="true" />
          {titulo}
        </p>
        <div
          className={cn(
            "truncate text-2xl font-semibold tracking-tight tabular-nums",
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
  if (href) {
    return (
      <Link
        to={href}
        className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        {cuerpo}
      </Link>
    );
  }
  return cuerpo;
}

/** Celda TOKENS de un job. Si el job ESPERA (o corre sin métricas aún) muestra el estimado de la
 *  etapa con sufijo «est.» y, en segunda línea, el tamaño del prompt. Si CORRE y ya reportó tokens
 *  reales, los pinta in/out + el coste USD. Vacío/0 atenuado. */
function CeldaTokens({ job }: { job: ColaJob }) {
  const corriendo = job.estado === "reclamado";
  const tieneReales = corriendo && (job.tokens_in != null || job.tokens_out != null);
  if (tieneReales) {
    return (
      <div className="leading-tight tabular-nums">
        <span className="font-medium text-foreground">
          {numeroCompacto(job.tokens_in ?? 0)} in · {numeroCompacto(job.tokens_out ?? 0)} out
        </span>
        {job.coste_usd != null && (
          <span className="block text-muted-foreground">{costeUsd(job.coste_usd)}</span>
        )}
      </div>
    );
  }
  const est = job.tokens_estimados;
  if (est == null || est === 0) {
    return <span className="text-muted-foreground/50">—</span>;
  }
  return (
    <div className="leading-tight tabular-nums text-muted-foreground">
      <span>~{numeroCompacto(est)} est.</span>
      {job.prompt_chars > 0 && (
        <span className="block text-muted-foreground/70">{numeroCompacto(job.prompt_chars)} chars</span>
      )}
    </div>
  );
}

/** Tabla de jobs activos (en curso o esperando), con acciones admin in-place. */
export function TablaJobs({
  jobs,
  mostrarWorker,
  esAdmin,
  onCancelar,
  cancelandoId,
  onPriorizar,
  priorizandoId,
  onReintentar,
  reintentandoId,
  onEliminar,
  eliminandoId,
}: {
  jobs: ColaJob[];
  mostrarWorker: boolean;
  esAdmin: boolean;
  onCancelar: (genId: string) => void;
  cancelandoId: string | null;
  /** Solo la tabla «Esperando»: prioriza el job. Sin opts lo adelanta al lote de fondo (como hoy);
   *  con `prioridad` clava ese valor (0..100); con `a_tope` lo sube por encima de todo. */
  onPriorizar?: (genId: string, opts?: { prioridad?: number; a_tope?: boolean }) => void;
  priorizandoId?: string | null;
  /** Reintenta un job FALLIDO (lo devuelve a la cola). Solo se ofrece si gen_estado = error. */
  onReintentar?: (genId: string) => void;
  reintentandoId?: string | null;
  /** Saca el job de la cola (cancela su árbol si corría). Admin. */
  onEliminar?: (genId: string) => void;
  eliminandoId?: string | null;
}) {
  const navigate = useNavigate();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="pl-6">Generación</TableHead>
          <TableHead className="hidden sm:table-cell">Etapa</TableHead>
          <TableHead className="hidden text-right md:table-cell">Tokens</TableHead>
          <TableHead className="hidden lg:table-cell">Marca</TableHead>
          {mostrarWorker && <TableHead className="hidden xl:table-cell">Worker</TableHead>}
          <TableHead className="pr-6">{mostrarWorker ? "Corriendo" : "En cola"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((j) => {
          // La fila ENTERA lleva al detalle de la generación (click izquierdo). Las acciones admin
          // (Priorizar/Prioridad…/Reintentar/Cancelar/Eliminar) viven en su menú (click derecho /
          // long-press), mismo modelo que la tabla de Servicios: sin botones inline ni kebab.
          const acciones: EntradaMenuContextual[] = [];
          if (esAdmin) {
            if (onPriorizar && j.prioridad <= 0) {
              acciones.push({
                etiqueta: "Priorizar",
                icono: ArrowUp,
                onClick: () => onPriorizar(j.gen_id),
                deshabilitado: priorizandoId === j.gen_id,
              });
            }
            if (onPriorizar) {
              acciones.push({
                etiqueta: "Prioridad…",
                icono: SlidersHorizontal,
                onClick: async () => {
                  const valor = await elegir({
                    titulo: "Prioridad manual",
                    mensaje: `Fija la prioridad de «${j.etiqueta || j.gen_id}» (mayor = adelanta en la cola).`,
                    opciones: [
                      { valor: "25", etiqueta: "25 · baja" },
                      { valor: "50", etiqueta: "50 · media" },
                      { valor: "75", etiqueta: "75 · alta" },
                      { valor: "100", etiqueta: "100 · máxima" },
                    ],
                  });
                  if (valor) onPriorizar(j.gen_id, { prioridad: Number(valor) });
                },
                deshabilitado: priorizandoId === j.gen_id,
              });
              acciones.push({
                etiqueta: "Subir a tope",
                icono: ArrowUpToLine,
                onClick: () => onPriorizar(j.gen_id, { a_tope: true }),
                deshabilitado: priorizandoId === j.gen_id,
              });
            }
            if (onReintentar && j.gen_estado === "error") {
              acciones.push({
                etiqueta: "Reintentar",
                icono: RotateCcw,
                onClick: () => onReintentar(j.gen_id),
                deshabilitado: reintentandoId === j.gen_id,
              });
            }
            acciones.push({
              etiqueta: "Cancelar",
              icono: XCircle,
              destructivo: true,
              onClick: () => onCancelar(j.gen_id),
              deshabilitado: cancelandoId === j.gen_id,
            });
            if (onEliminar) {
              acciones.push({
                etiqueta: "Eliminar",
                icono: Trash2,
                destructivo: true,
                onClick: async () => {
                  if (
                    await confirmar({
                      titulo: "Eliminar de la cola",
                      mensaje:
                        "Eliminar saca el job de la cola y cancela su ejecución. ¿Seguro?",
                      destructivo: true,
                      textoConfirmar: "Eliminar",
                    })
                  ) {
                    onEliminar(j.gen_id);
                  }
                },
                deshabilitado: eliminandoId === j.gen_id,
              });
            }
          }
          return (
            <FilaConAcciones
              key={j.job_id}
              como="tr"
              kebab="nunca"
              acciones={acciones}
              onPrimaria={() =>
                navigate(`/maquina/actividad/generacion/${encodeURIComponent(j.gen_id)}`)
              }
              etiquetaAcciones={`Acciones de ${j.etiqueta || j.gen_id}`}
            >
              <TableCell className="pl-6 font-medium">
                <span className="inline-flex items-center gap-1.5">
                  {j.etiqueta || j.gen_id}
                  {j.prioridad > 0 && (
                    <Badge variant="info" className="text-[10px]">
                      prioritario
                    </Badge>
                  )}
                  {j.huerfano && (
                    <Badge variant="aviso" className="text-[10px]" title="Su generación ya no existe: no se procesa">
                      huérfano
                    </Badge>
                  )}
                </span>
              </TableCell>
              <TableCell className="hidden sm:table-cell text-muted-foreground">
                {j.etapa || j.tipo || "—"}
              </TableCell>
              <TableCell className="hidden text-right text-xs md:table-cell">
                <CeldaTokens job={j} />
              </TableCell>
              <TableCell className="hidden lg:table-cell text-muted-foreground">{j.marca || "—"}</TableCell>
              {mostrarWorker && (
                <TableCell className="hidden xl:table-cell font-mono text-xs text-muted-foreground">
                  {j.worker || "—"}
                </TableCell>
              )}
              <TableCell className="pr-6 tabular-nums text-muted-foreground">
                {haceSegundos(mostrarWorker ? j.corriendo_hace_s : j.encolado_hace_s)}
              </TableCell>
            </FilaConAcciones>
          );
        })}
      </TableBody>
    </Table>
  );
}

/** Dos celdas (pendientes · en curso) de un proceso en la tabla de desglose. «En curso» (reclamados)
 *  se realza cuando hay algo corriendo. */
function CeldasProceso({ c }: { c: ConteoCola }) {
  return (
    <>
      <TableCell className="text-right tabular-nums text-muted-foreground">{c.pendientes}</TableCell>
      <TableCell
        className={cn(
          "text-right tabular-nums",
          c.reclamados > 0 ? "font-medium text-foreground" : "text-muted-foreground",
        )}
      >
        {c.reclamados}
      </TableCell>
    </>
  );
}

/** Cola DESGLOSADA por marca×etapa×estado (`GET /api/actividad/cola/desglose`, foto completa sin
 *  filtro). Filas = marcas (la de feed sin id se rotula «Sin marca»), más una fila «Huérfanos» (jobs
 *  cuya generación ya no existe). Columnas = Investigación / Producción, cada una con Pendientes y En
 *  curso, más el total. `nombrePorMarca` resuelve el nombre legible de cada id. */
export function TablaDesglose({
  desglose,
  nombrePorMarca,
}: {
  desglose: ColaDesglose;
  nombrePorMarca: Record<string, string>;
}) {
  const huerfTotal = desglose.huerfanos.pendientes + desglose.huerfanos.reclamados;
  const nombreMarca = (id: string) =>
    id === "" ? "Sin marca (feed)" : nombrePorMarca[id] ?? id;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Cola por marca y etapa</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Marca</TableHead>
              <TableHead className="text-right">
                <span className={PROC_META.investigacion.texto}>Investigación</span> · pend.
              </TableHead>
              <TableHead className="text-right">curso</TableHead>
              <TableHead className="text-right">
                <span className={PROC_META.produccion.texto}>Producción</span> · pend.
              </TableHead>
              <TableHead className="text-right">curso</TableHead>
              <TableHead className="pr-6 text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {desglose.marcas.map((m) => (
              <TableRow key={m.marca || "__feed__"}>
                <TableCell className="pl-6 font-medium">{nombreMarca(m.marca)}</TableCell>
                <CeldasProceso c={m.por_proceso.investigacion} />
                <CeldasProceso c={m.por_proceso.produccion} />
                <TableCell className="pr-6 text-right tabular-nums text-muted-foreground">
                  {m.total.pendientes + m.total.reclamados}
                </TableCell>
              </TableRow>
            ))}
            {huerfTotal > 0 && (
              <TableRow className="bg-amber-50/60 dark:bg-amber-950/20">
                <TableCell className="pl-6 font-medium text-amber-700 dark:text-amber-400">
                  Huérfanos
                </TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground" colSpan={4}>
                  {desglose.huerfanos.pendientes} pend. · {desglose.huerfanos.reclamados} en curso ·
                  sin generación
                </TableCell>
                <TableCell className="pr-6 text-right tabular-nums text-amber-700 dark:text-amber-400">
                  {huerfTotal}
                </TableCell>
              </TableRow>
            )}
            {desglose.marcas.length === 0 && huerfTotal === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="px-6 py-6 text-sm text-muted-foreground">
                  Cola vacía: nada encolado ni en curso.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Las 6 etapas del backlog EN ORDEN DE CADENA (entrada → salida), con su rótulo humano y el
 *  significado para el tooltip. `acento` marca la etapa culpable de la avalancha (esperando_copy):
 *  los temas SIN copy que entran de golpe al activar «Generar copy». */
const ETAPAS_BACKLOG: {
  clave: keyof BacklogEtapas;
  etiqueta: string;
  descripcion: string;
  acento?: boolean;
}[] = [
  {
    clave: "pool_sin_admitir",
    etiqueta: "Pool",
    descripcion: "Noticias recolectadas (RSS/radar) que aún no entran al tablero.",
  },
  {
    clave: "pipeline_en_proceso",
    etiqueta: "En proceso",
    descripcion: "Temas admitidos esperando verificación o copy.",
  },
  {
    clave: "esperando_copy",
    etiqueta: "Esperando copy",
    descripcion:
      "Temas del tablero SIN copy esperando a que se active «Generar copy». Aquí se acumula la avalancha que entra de golpe al activar la marca.",
    acento: true,
  },
  {
    clave: "generando_copy",
    etiqueta: "Generando copy",
    descripcion: "Copy encolado o en curso.",
  },
  {
    clave: "generando_arte",
    etiqueta: "Generando arte",
    descripcion: "Con copy, esperando ilustración.",
  },
  {
    clave: "lista_para_revisar",
    etiqueta: "Lista para revisar",
    descripcion: "Completas, ya en la parrilla o revisión.",
  },
];

/** Celda de una etapa del backlog: el número (0 atenuado). La etapa `esperando_copy` se realza en
 *  ámbar por ser la cola oculta que provoca la avalancha. */
function CeldaBacklog({ n, acento }: { n: number; acento?: boolean }) {
  return (
    <TableCell
      className={cn(
        "text-right tabular-nums",
        acento && n > 0 && "bg-amber-50/60 font-semibold text-amber-700 dark:bg-amber-950/20 dark:text-amber-400",
        !(acento && n > 0) && (n > 0 ? "text-foreground" : "text-muted-foreground/50"),
      )}
    >
      {n}
    </TableCell>
  );
}

/** EMBUDO del backlog por marca×etapa (`GET /api/produccion/backlog`, foto completa sin filtro): el
 *  EMBALSE que se acumula ANTES de la cola de jobs. Filas = marcas; columnas = las 6 etapas EN ORDEN
 *  DE CADENA (entrada → salida) + el total. Resalta `esperando_copy`, la cola oculta de temas sin
 *  copy que entra de golpe al activar «Generar copy». `titulo` enmarca el mismo embudo según la
 *  página que lo monta (p. ej. el coste pendiente en Economía); la tabla y su nota no cambian. */
export function TablaBacklog({
  backlog,
  titulo = "Embalse del tablero (antes de la cola)",
}: {
  backlog: Backlog;
  titulo?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{titulo}</CardTitle>
        <p className="text-xs text-muted-foreground">
          El contenido se acumula a lo largo de la cadena ANTES de la cola de jobs. La columna{" "}
          <span className="font-medium text-amber-700 dark:text-amber-400">Esperando copy</span> es la
          que entra de golpe al activar «Generar copy» de una marca.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Marca</TableHead>
              {ETAPAS_BACKLOG.map((e) => (
                <TableHead
                  key={e.clave}
                  className={cn("text-right", e.acento && "text-amber-700 dark:text-amber-400")}
                  title={e.descripcion}
                >
                  {e.etiqueta}
                </TableHead>
              ))}
              <TableHead className="pr-6 text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {backlog.marcas.map((m) => (
              <TableRow key={m.marca}>
                <TableCell className="pl-6 font-medium">{m.nombre || m.marca}</TableCell>
                {ETAPAS_BACKLOG.map((e) => (
                  <CeldaBacklog key={e.clave} n={m.etapas[e.clave]} acento={e.acento} />
                ))}
                <TableCell
                  className={cn(
                    "pr-6 text-right font-medium tabular-nums",
                    m.total > 0 ? "text-foreground" : "text-muted-foreground/50",
                  )}
                >
                  {m.total}
                </TableCell>
              </TableRow>
            ))}
            {backlog.marcas.length === 0 && (
              <TableRow>
                <TableCell colSpan={ETAPAS_BACKLOG.length + 2} className="px-6 py-6 text-sm text-muted-foreground">
                  Sin marcas configuradas.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** TOPE editable in situ (admin): input compacto que guarda al salir del campo (blur/Enter).
 *  Reutilizable para los topes de tokens (global y por motor, enteros) y el cap de coste USD
 *  (`decimal`, step 0.01). 0 = sin límite. */
function PresupuestoEditable({
  valor,
  clave,
  etiqueta,
  unidad = "tokens",
  decimal = false,
}: {
  valor: number;
  /** Clave de ajuste (KENI_*) que persiste el tope. */
  clave: string;
  /** Etiqueta del campo (p. ej. "Presupuesto diario", "Cap USD/día", "Tope diario"). */
  etiqueta: string;
  /** Unidad mostrada tras el input ("tokens", "USD"). */
  unidad?: string;
  /** `true` para importes con decimales (USD); `false` trunca a entero (tokens). */
  decimal?: boolean;
}) {
  const guardar = useGuardarAjuste();
  const [num, setNum] = React.useState(String(valor));
  React.useEffect(() => {
    setNum(String(valor));
  }, [valor]);
  const guardarNumero = () => {
    const n = Number(num);
    if (num.trim() !== "" && Number.isFinite(n) && n >= 0 && n !== valor) {
      guardar.mutate({ clave, valor: decimal ? n : Math.trunc(n) });
    } else {
      setNum(String(valor));
    }
  };
  return (
    <Label className="inline-flex items-center gap-1.5">
      {etiqueta}
      <Input
        type="number"
        min={0}
        step={decimal ? "0.01" : "1"}
        value={num}
        onChange={(e) => setNum(e.target.value)}
        onBlur={guardarNumero}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        disabled={guardar.isPending}
        className="h-6 w-28 px-2 text-base tabular-nums md:text-xs"
        aria-label={`${etiqueta} (0 = sin límite)`}
      />
      {unidad}
      {valor === 0 && <span className="text-muted-foreground/80">(Sin límite)</span>}
    </Label>
  );
}

/** Env vars del tope diario de tokens por motor y dirección (IN/OUT). Los persiste `useGuardarAjuste`. */
const ENV_TOPE_MOTOR: Record<Proceso, { in: string; out: string }> = {
  investigacion: {
    in: "KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA",
    out: "KENI_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA",
  },
  produccion: {
    in: "KENI_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA",
    out: "KENI_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA",
  },
};

/** Forma de gasto por motor cuando el back aún no la emite (rollout): todo a cero, sin tope. */
const PROC_PRESUPUESTO_VACIO: PresupuestoProcesoIA = {
  tokens_in: 0,
  tokens_out: 0,
  tokens: 0,
  coste_usd: 0,
  generaciones: 0,
  presupuesto_tokens_in_dia: 0,
  presupuesto_tokens_out_dia: 0,
  restante_in: null,
  pct_in: null,
  restante_out: null,
  pct_out: null,
  nivel: "normal",
};

/** Barra de progreso del % usado (verde < 80, ámbar < 100, rojo ≥ 100). El relleno es una
 *  GRADACIÓN DE SEVERIDAD por umbral (no un estado discreto), así que va con color directo
 *  y no por `Badge`. */
function BarraPct({ pct, ancho = "w-full" }: { pct: number; ancho?: string }) {
  return (
    <div className={cn("h-1.5 overflow-hidden rounded-full bg-muted", ancho)}>
      <div
        className={cn(
          "h-full rounded-full",
          pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-500" : "bg-emerald-500",
        )}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  );
}

/** Una dirección (IN u OUT) de un motor: tokens gastados + su tope diario editable (admin) y, si hay
 *  tope, el % usado con una barra compacta. */
function FilaMotorDireccion({
  etiqueta,
  tokens,
  tope,
  pct,
  clave,
  esAdmin,
}: {
  etiqueta: "IN" | "OUT";
  tokens: number;
  tope: number;
  pct: number | null;
  /** Clave de ajuste (KENI_*) del tope de esta dirección. */
  clave: string;
  esAdmin: boolean;
}) {
  const conTope = tope > 0;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="w-8 shrink-0 text-muted-foreground">{etiqueta}</span>
      <span className="w-16 shrink-0 font-medium text-foreground">{numeroCompacto(tokens)}</span>
      {esAdmin ? (
        <PresupuestoEditable valor={tope} clave={clave} etiqueta="tope" unidad="" />
      ) : (
        <span>tope {conTope ? numeroCompacto(tope) : "—"}</span>
      )}
      {conTope && pct != null && <span>· {pct.toFixed(0)}%</span>}
      {conTope && pct != null && <BarraPct pct={pct} ancho="w-16" />}
    </div>
  );
}

/** Panel de un MOTOR (Investigación | Producción): tokens IN/OUT con un tope diario INDEPENDIENTE
 *  por dirección (editable por admin) y la línea de gasto USD · generaciones. Lee
 *  `presupuesto.por_proceso?.[motor]`; degrada a ceros si el back aún no lo emite. */
function PanelMotor({
  motor,
  datos,
  esAdmin,
  marca,
}: {
  motor: Proceso;
  datos: PresupuestoProcesoIA | undefined;
  esAdmin: boolean;
  /** Ámbito de marca: con marca, los topes se editan con la clave por-marca (`KENI_*::<marca>`). */
  marca?: string;
}) {
  const meta = PROC_META[motor];
  const p = datos ?? PROC_PRESUPUESTO_VACIO;
  const base = ENV_TOPE_MOTOR[motor];
  // Con ámbito de marca, el tope es el PROPIO de la marca (clave con sufijo `::<marca>`).
  const claves = marca ? { in: `${base.in}::${marca}`, out: `${base.out}::${marca}` } : base;
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className={cn("h-2.5 w-2.5 rounded-full", meta.barra)} aria-hidden="true" />
        <span className={meta.texto}>{meta.etiqueta}</span>
      </div>
      <div className="space-y-1.5 text-xs text-muted-foreground tabular-nums">
        <FilaMotorDireccion
          etiqueta="IN"
          tokens={p.tokens_in}
          tope={p.presupuesto_tokens_in_dia}
          pct={p.pct_in}
          clave={claves.in}
          esAdmin={esAdmin}
        />
        <FilaMotorDireccion
          etiqueta="OUT"
          tokens={p.tokens_out}
          tope={p.presupuesto_tokens_out_dia}
          pct={p.pct_out}
          clave={claves.out}
          esAdmin={esAdmin}
        />
      </div>
      <div className="text-xs text-muted-foreground tabular-nums">
        Gasto <span className="font-medium text-foreground">{costeUsd(p.coste_usd)}</span> ·{" "}
        {p.generaciones} gen
      </div>
    </div>
  );
}

/** Aviso del gate diario por % de UNA cuenta de Claude. Cuando el consumo del día de la cuenta
 *  alcanza su umbral, el FONDO de SUS marcas se pausa (lo manual de las personas sigue) y aparece
 *  la pantalla «Aceptar continuar (+10%)» (solo admin: sube el umbral del día de ESA cuenta y
 *  reanuda el fondo). A un no-admin solo le aparece que el fondo está en pausa por el consumo del
 *  día. `lineaSiNoPausada` controla si,
 *  sin pausa, se pinta una línea discreta de consumo (modo de una marca) o nada (modo "Todas", donde
 *  solo interesan las cuentas gateadas). Sin datos del % (rollout) no pinta nada. */
function AvisoGateCuenta({
  gate,
  esAdmin,
  lineaSiNoPausada,
}: {
  gate: GateDiarioIA;
  esAdmin: boolean;
  lineaSiNoPausada: boolean;
}) {
  const qc = useQueryClient();
  const aceptar = useMutation({
    mutationFn: () => api.gateDiarioAceptar(gate.cuenta),
    onSuccess: () => {
      toast.success(`Generación reanudada (cuenta ${gate.cuenta.toUpperCase()}): +10% para hoy.`);
      void qc.invalidateQueries({ queryKey: ["actividad", "cola"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Sin datos del % (la fuente aún no existe / rollout) no hay nada que decir.
  if (gate.consumo_hoy_pct == null) return null;
  const consumo = gate.consumo_hoy_pct;
  const etiquetaCuenta = `cuenta ${gate.cuenta.toUpperCase()}`;

  // No pausado: una línea discreta de consumo del día (solo cuando se pide; informativa).
  if (!gate.pausado_por_pct) {
    if (!lineaSiNoPausada) return null;
    return (
      <p className="text-xs text-muted-foreground tabular-nums">
        Consumo de hoy ({etiquetaCuenta}): {consumo.toFixed(1)}% del límite semanal · umbral del día{" "}
        {gate.umbral_pct.toFixed(1)}%
        {gate.aceptados_hoy > 0 && ` · +${gate.aceptados_hoy * gate.paso_pct}% aceptado`}
      </p>
    );
  }

  // Pausado por consumo del día: aviso prominente. Admin ve «Aceptar continuar (+10%)».
  return (
    <div className="space-y-3 rounded-lg border border-amber-500/50 bg-amber-50 p-4 dark:bg-amber-950/30">
      <div className="flex items-start gap-2">
        <PauseCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" aria-hidden="true" />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
            Generación pausada por el consumo del día ({etiquetaCuenta})
          </p>
          <p className="text-xs text-amber-800 dark:text-amber-300/90 tabular-nums">
            Hoy se ha consumido {consumo.toFixed(1)}% del límite semanal de la {etiquetaCuenta}{" "}
            (umbral del día {gate.umbral_pct.toFixed(1)}%). El fondo de sus marcas deja de encolar y
            ejecutar; los lanzamientos manuales del equipo siguen.
          </p>
        </div>
      </div>
      {esAdmin ? (
        <Button
          size="sm"
          onClick={() => aceptar.mutate()}
          disabled={aceptar.isPending}
          className="bg-amber-600 hover:bg-amber-700"
        >
          Aceptar continuar (+10%)
        </Button>
      ) : (
        <p className="text-xs text-amber-800 dark:text-amber-300/90">
          Un administrador puede aceptar +10% para reanudar el fondo de hoy de esta cuenta.
        </p>
      )}
    </div>
  );
}

/** Gate DIARIO por % del límite SEMANAL POR CUENTA. Sigue el SELECTOR DE MARCA activo (lo refleja el
 *  ámbito del presupuesto que trae la cola): con una marca seleccionada, el back manda el bloque de
 *  SU cuenta (`gate_diario`) y se pinta un único aviso (con línea discreta de consumo si no hay
 *  pausa); en "Todas" (sin marca, `gate_diario` null) se pintan los bloques de `gate_diario_cuentas`
 *  de las cuentas que estén gateadas (puede haber dos avisos). Hooks al tope del subcomponente; este
 *  solo decide qué bloques montar. */
function BloqueGateDiario({
  gate,
  gateCuentas,
  esAdmin,
}: {
  gate: GateDiarioIA | null | undefined;
  gateCuentas: Record<string, GateDiarioIA> | undefined;
  esAdmin: boolean;
}) {
  // Marca seleccionada: el back resolvió la cuenta de esa marca -> un único aviso (con línea discreta).
  if (gate) return <AvisoGateCuenta gate={gate} esAdmin={esAdmin} lineaSiNoPausada />;
  // "Todas": un aviso por cada cuenta GATEADA (las no pausadas no se pintan para no saturar).
  const cuentas = Object.values(gateCuentas ?? {}).filter((g) => g.pausado_por_pct);
  if (cuentas.length === 0) return null;
  return (
    <div className="space-y-3">
      {cuentas.map((g) => (
        <AvisoGateCuenta key={g.cuenta} gate={g} esAdmin={esAdmin} lineaSiNoPausada={false} />
      ))}
    </div>
  );
}

/** Niveles del dial de ritmo (de mayor a menor), en %. 100 = ritmo normal. */
const NIVELES_RITMO = [100, 75, 50, 25] as const;

/** DIAL DE RITMO de producción: botones segmentados (100/75/50/25 %) que escriben la clave de ajuste
 *  del ámbito (`KENI_RITMO` global o `KENI_RITMO::<marca>`). Baja el gasto sin apagar etapas: 100% =
 *  normal, 50% = mitad de trabajo nuevo por barrido. Solo admin lo cambia; el resto ve el % vigente. */
function DialRitmo({
  valor,
  clave,
  esAdmin,
  etiqueta,
  descripcion,
}: {
  /** % de ritmo vigente del ámbito (10..100). */
  valor: number;
  /** Clave de ajuste que persiste el ritmo (`KENI_RITMO` o `KENI_RITMO::<marca>`). */
  clave: string;
  esAdmin: boolean;
  etiqueta: string;
  descripcion: string;
}) {
  const guardar = useGuardarAjuste();
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-medium">
          <Gauge className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          {etiqueta}
        </span>
        <span className="text-sm font-semibold tabular-nums">{valor}%</span>
      </div>
      <p className="text-xs text-muted-foreground">{descripcion}</p>
      {esAdmin ? (
        <div className="inline-flex overflow-hidden rounded-md border" role="group" aria-label={etiqueta}>
          {NIVELES_RITMO.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={valor === n}
              disabled={guardar.isPending}
              onClick={() => {
                if (valor !== n) guardar.mutate({ clave, valor: n });
              }}
              className={cn(
                "border-r px-3 py-1 text-xs font-medium tabular-nums transition-colors last:border-r-0",
                valor === n ? "bg-keni text-white" : "hover:bg-muted",
              )}
            >
              {n}%
            </button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground tabular-nums">Ritmo vigente: {valor}%.</p>
      )}
    </div>
  );
}

/** PRESUPUESTO + gasto de HOY + PARADA DE EMERGENCIA. Su ÁMBITO lo fija `presupuesto.marca`: con
 *  marca activa edita los controles PROPIOS de esa marca (su cap USD `KENI_PRESUPUESTO_USD_DIA::marca`
 *  y su parada `KENI_GENERACION_PAUSADA::marca`) y muestra SU gasto; sin marca ("todas") opera los
 *  controles GLOBALES y, debajo, los dos motores con sus topes de tokens IN/OUT (que son globales,
 *  ADR 0011 — en la vista de marca se muestran como gasto sin tope editable). `nombreMarca` solo
 *  rotula la cabecera. */
export function PanelPresupuesto({
  presupuesto,
  esAdmin,
  nombreMarca,
  estimadoPendiente,
}: {
  presupuesto: PresupuestoIA;
  esAdmin: boolean;
  /** Nombre legible de la marca activa (solo para la cabecera); ausente = vista global. */
  nombreMarca?: string;
  /** Coste estimado de vaciar el backlog del ámbito (la marca activa o el total): cuánto costará
   *  generar lo que aún espera. Se muestra junto al gasto. Ausente = no se pinta esa línea. */
  estimadoPendiente?: BacklogEstimado;
}) {
  const guardar = useGuardarAjuste();
  const marca = presupuesto.marca || "";
  const conCapUsd = presupuesto.presupuesto_usd_dia > 0;
  const pctUsd = presupuesto.pct_usado_usd;
  const proyeccion = presupuesto.proyeccion_usd_dia;
  const pctProyectado = presupuesto.pct_proyectado_usd;
  // Aviso visual cuando la proyección de gasto supera el tope del día.
  const proyeccionExcede = conCapUsd && proyeccion != null && proyeccion > presupuesto.presupuesto_usd_dia;
  // Claves de ajuste con sufijo por marca cuando hay ámbito de marca (`KENI_*::<marca>`).
  const clavePausa = marca ? `KENI_GENERACION_PAUSADA::${marca}` : "KENI_GENERACION_PAUSADA";
  const claveUsd = marca ? `KENI_PRESUPUESTO_USD_DIA::${marca}` : "KENI_PRESUPUESTO_USD_DIA";
  const etiquetaUsd = marca ? "Presupuesto de la marca (tope)" : "Gasto global (tope)";
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            <Coins className="h-4 w-4 text-muted-foreground" />
            Control de gasto
            {marca && (
              <span className="font-normal text-muted-foreground">· {nombreMarca || marca}</span>
            )}
          </CardTitle>
          <ChipNivelPresupuesto nivel={presupuesto.nivel} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* DIAL DE RITMO: la palanca protagonista. El global siempre; debajo, el de la marca activa
            (ámbito-following, como los topes). Baja el trabajo nuevo por barrido sin apagar etapas. */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <DialRitmo
            valor={presupuesto.ritmo_global}
            clave="KENI_RITMO"
            esAdmin={esAdmin}
            etiqueta="Ritmo de producción (global)"
            descripcion="Baja el gasto sin apagar etapas. 100% = normal, 50% = mitad de trabajo nuevo por barrido."
          />
          {marca && (
            <DialRitmo
              valor={presupuesto.ritmo}
              clave={`KENI_RITMO::${marca}`}
              esAdmin={esAdmin}
              etiqueta={`Ritmo de ${nombreMarca || marca}`}
              descripcion="Ritmo propio de la marca: limita su trabajo nuevo por barrido sin tocar el resto."
            />
          )}
        </div>
        {/* Gate diario por % del límite semanal POR CUENTA: el aviso/pantalla de «Aceptar +10%»
            cuando el consumo del día de una cuenta pausa SUS marcas. Con marca activa, el de su
            cuenta; en "Todas", el de la(s) cuenta(s) gateada(s). Va arriba para que sea lo primero
            que se ve cuando hay pausa. */}
        <BloqueGateDiario
          gate={presupuesto.gate_diario}
          gateCuentas={presupuesto.gate_diario_cuentas}
          esAdmin={esAdmin}
        />
        {/* Cabecera: gasto de hoy (del ámbito) + parada de emergencia (global o de la marca). */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p className="text-sm">
            Hoy:{" "}
            <span className="font-medium tabular-nums">
              {numeroCompacto(presupuesto.gastado.tokens_in)}
            </span>{" "}
            in /{" "}
            <span className="font-medium tabular-nums">
              {numeroCompacto(presupuesto.gastado.tokens_out)}
            </span>{" "}
            out tok · {costeUsd(presupuesto.gastado.coste_usd)} · {presupuesto.gastado.generaciones} gen
          </p>
          {esAdmin && (
            <Label className="flex items-center gap-2 text-sm">
              <span
                className={cn(presupuesto.pausada ? "text-destructive" : "text-muted-foreground")}
              >
                {presupuesto.pausada ? "Generación parada" : "Parada de emergencia"}
              </span>
              <Switch
                checked={presupuesto.pausada}
                disabled={guardar.isPending}
                onCheckedChange={(v) => guardar.mutate({ clave: clavePausa, valor: v })}
                aria-label={
                  marca
                    ? "Parada de emergencia de la marca: corta toda su generación (fondo y manual)"
                    : "Parada de emergencia: corta toda la generación con IA, incluida la manual"
                }
              />
            </Label>
          )}
        </div>
        {/* Tope en USD del ámbito (global o de la marca): el control de coste editable por admin. */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {esAdmin ? (
            <PresupuestoEditable
              valor={presupuesto.presupuesto_usd_dia}
              clave={claveUsd}
              etiqueta={etiquetaUsd}
              unidad="USD"
              decimal
            />
          ) : (
            <span>
              {etiquetaUsd} {conCapUsd ? costeUsd(presupuesto.presupuesto_usd_dia) : "Sin límite"}
            </span>
          )}
          {conCapUsd && pctUsd != null && <span>· {pctUsd.toFixed(0)}% gasto</span>}
          {conCapUsd && pctUsd != null && <BarraPct pct={pctUsd} ancho="w-56" />}
        </div>
        {/* Proyección de gasto a fin de día (extrapolación del coste actual). Avisa en rojo si
            la proyección supera el tope. None al arranque del día (no se proyecta). */}
        {proyeccion != null && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className={cn(proyeccionExcede ? "text-destructive" : "text-muted-foreground")}>
              Proyección fin de día: {costeUsd(proyeccion)}
              {conCapUsd && pctProyectado != null && ` · ${pctProyectado.toFixed(0)}% del tope`}
            </span>
          </div>
        )}
        {/* Trabajo pendiente: lo que costará GENERAR el backlog que aún espera (no lo gastado hoy).
            Sigue el ámbito de marca (su estimado o el total). */}
        {estimadoPendiente && (estimadoPendiente.tokens > 0 || estimadoPendiente.coste_usd > 0) && (
          <p className="text-xs text-muted-foreground tabular-nums">
            Trabajo pendiente: ~{numeroCompacto(estimadoPendiente.tokens)} tokens ·{" "}
            {costeUsd(estimadoPendiente.coste_usd)} estimado
          </p>
        )}
        {/* Dos motores lado a lado (apilan en móvil): tokens IN/OUT con su tope por dirección,
            editable por admin. El tope es del ÁMBITO: global en "todas", propio de la marca cuando
            hay marca activa (clave `KENI_*::<marca>`). */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <PanelMotor
            motor="investigacion"
            datos={presupuesto.por_proceso?.investigacion}
            esAdmin={esAdmin}
            marca={marca}
          />
          <PanelMotor
            motor="produccion"
            datos={presupuesto.por_proceso?.produccion}
            esAdmin={esAdmin}
            marca={marca}
          />
        </div>
        {/* Apagar etapas concretas no vive aquí: son toggles por etapa en Contexto. */}
        <p className="text-xs text-muted-foreground">
          ¿Apagar etapas concretas?{" "}
          <Link to="/maquina/contexto" className="underline-offset-2 hover:underline">
            Ver Contexto
          </Link>
          .
        </p>
      </CardContent>
    </Card>
  );
}

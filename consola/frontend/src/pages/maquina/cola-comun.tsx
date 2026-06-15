/**
 * Piezas COMPARTIDAS de la cola/cómputo entre la página de Agentes (`/maquina/agentes`) y la de
 * Cómputo y cola (`/maquina/computo`): la tarjeta KPI, la tabla de jobs activos (con sus
 * acciones admin) y el panel de presupuesto + parada de emergencia. Viven aquí para que ambas
 * superficies reusen el mismo render y el mismo contrato sin duplicarlo.
 */
import { ArrowUp, Coins, type Cpu, RotateCcw, XCircle } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";

import { ChipNivelPresupuesto } from "@/components/comunes/ChipEstado";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { haceSegundos } from "@/lib/fecha";
import { costeUsd, numeroCompacto } from "@/lib/formato";
import { cn } from "@/lib/utils";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import { DesgloseEconomiaProceso } from "@/pages/monitor/comun";
import type { ColaJob, PresupuestoIA, ResultadoDia } from "@/types";

/** Tarjeta KPI: icono, valor grande y subtítulo. `tono` colorea el valor ante alerta. Si se
 *  pasa `href`, la tarjeta ENTERA es un enlace (el contador es el botón) con realce naranja al
 *  hover, en vez de un botón aparte. */
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
}: {
  jobs: ColaJob[];
  mostrarWorker: boolean;
  esAdmin: boolean;
  onCancelar: (genId: string) => void;
  cancelandoId: string | null;
  /** Solo la tabla «Esperando»: adelanta el job al lote de fondo (prioridad manual). */
  onPriorizar?: (genId: string) => void;
  priorizandoId?: string | null;
  /** Reintenta un job FALLIDO (lo devuelve a la cola). Solo se ofrece si gen_estado = error. */
  onReintentar?: (genId: string) => void;
  reintentandoId?: string | null;
}) {
  const navigate = useNavigate();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Generación</TableHead>
          <TableHead className="hidden sm:table-cell">Tipo</TableHead>
          <TableHead className="hidden md:table-cell">Marca</TableHead>
          {mostrarWorker && <TableHead className="hidden lg:table-cell">Worker</TableHead>}
          <TableHead>{mostrarWorker ? "Corriendo" : "En cola"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((j) => {
          // La fila ENTERA lleva al detalle de la generación (click izquierdo). Las acciones
          // admin (Priorizar/Reintentar/Cancelar) viven en su menú (click derecho / long-press),
          // mismo modelo que la tabla de Servicios: sin botones inline ni kebab.
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
          }
          return (
            <FilaConAcciones
              key={j.job_id}
              como="tr"
              kebab="nunca"
              acciones={acciones}
              onPrimaria={() =>
                navigate(`/datos/produccion/actividad/${encodeURIComponent(j.gen_id)}`)
              }
              etiquetaAcciones={`Acciones de ${j.etiqueta || j.gen_id}`}
            >
              <TableCell className="font-medium">
                <span className="inline-flex items-center gap-1.5">
                  {j.etiqueta || j.gen_id}
                  {j.prioridad > 0 && (
                    <Badge
                      variant="secondary"
                      className="border border-sky-500/30 bg-sky-500/10 text-[10px] text-sky-600"
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
            </FilaConAcciones>
          );
        })}
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
export function PanelPresupuesto({
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
          </div>
        )}
      </CardContent>
    </Card>
  );
}

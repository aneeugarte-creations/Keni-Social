/**
 * PanelPipeline — el pipeline CONSOLIDADO de un proceso (Investigación o Producción) como una
 * SECUENCIA VERTICAL de fases: una fila por fase, en orden de flujo y unidas por un conector (↓),
 * para que el recorrido se lea de arriba a abajo. NO va dentro de una caja: es la superficie misma
 * (sin «cajas dentro de cajas»). Cada fila es UNIFORME (mismo alto) y lleva:
 *   · su ICONO de tipo — 🤖 (LLM) / ⚙ (determinista) —,
 *   · su INTERRUPTOR (on/off) — el toggle ES el indicador de estado; no hay puntos de color —,
 *   · sus CONTEOS de cola (en curso · en cola) donde la fase tiene trabajos,
 *   · «Editar prompt» (las fases con prompt abren su doc de la Biblioteca en un overlay) y las
 *     «Excepciones por marca», en el menú de la fila.
 * En la cabecera, el maestro «Máquina» (`KENI_MAQUINA`): apagado, nada automático corre.
 *
 * Genérico: el llamante le pasa las FASES (`fases`), el mapa tipo-de-job→fase para los conteos
 * (`queuePorTipo`) y opcionalmente qué fase muestra el admision de verificación (`admisionEn`). Cada
 * fase resuelve su switch por la PRIMERA de sus `claves` presente en el catálogo; las que solo
 * tienen el maestro virtual del proceso lo indican con `heredada`.
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, ChevronDown, Cog, Users } from "lucide-react";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { ItemMenuContextual } from "@/components/comunes/MenuContextual";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_AJUSTES } from "@/pages/configuracion/lib";
import {
  ExcepcionesPorMarca,
  useGuardarAjuste,
} from "@/pages/configuracion/SeccionFuncionalidad";
import type { AjusteAdmin, ColaJob, ColaMonitor } from "@/types";

/** El interruptor GENERAL de la máquina (cabecera). Apagado, nada automático corre. */
const CLAVE_MAQUINA = "KENI_MAQUINA";

export interface FasePipeline {
  /** Nombre legible de la fase. */
  nombre: string;
  /** 🤖 (LLM) si es IA, ⚙ (determinista) si no. */
  es_ia: boolean;
  /** Claves del catálogo EN ORDEN; la primera presente gobierna el switch y el estado. */
  claves: readonly string[];
  /** Qué hace la fase. */
  ayuda: string;
  /** Doc de la Biblioteca cuyo prompt alimenta la fase («Editar prompt»). */
  doc?: string;
  /** Clave de cola de la fase (índice en los conteos): muestra sus en curso/en cola. */
  queue?: string;
  /** Clave BASE de los toggles por marca (grupo `automatizacion_marca_*`) + nota de alcance. */
  excepciones?: { base: string; nota: string };
  /** Nota cuando el switch gobierna un flag COMPARTIDO (fase sin flag propio). */
  heredada?: string;
}

function contar(jobs: ColaJob[], queuePorTipo: Record<string, string>): Record<string, number> {
  const c: Record<string, number> = {};
  for (const j of jobs) {
    const e = queuePorTipo[j.tipo];
    if (e) c[e] = (c[e] ?? 0) + 1;
  }
  return c;
}

/** Switch de UN ajuste bool con su PROPIA mutación (el «guardando» es de este control).
 *  `tono` se pasa al Switch: el maestro «Máquina» va en `estado` (verde on / rojo off). */
function SwitchAjuste({
  ajuste,
  ariaLabel,
  tono,
}: {
  ajuste: AjusteAdmin;
  ariaLabel: string;
  tono?: "neutro" | "estado";
}) {
  const guardar = useGuardarAjuste();
  return (
    <Switch
      checked={Boolean(ajuste.valor)}
      disabled={guardar.isPending}
      onCheckedChange={(v) => guardar.mutate({ clave: ajuste.clave, valor: v })}
      aria-label={ariaLabel}
      tono={tono}
    />
  );
}

/** Diálogo CONTROLADO de las EXCEPCIONES POR MARCA de una fase (clave `base::marca`). */
function DialogoExcepciones({
  etiqueta,
  base,
  nota,
  deEtapa,
  etapaActiva,
  abierto,
  onOpenChange,
}: {
  etiqueta: string;
  base: string;
  nota: string;
  deEtapa: AjusteAdmin[];
  etapaActiva: boolean;
  abierto: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const guardar = useGuardarAjuste();
  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{etiqueta} · excepciones por marca</DialogTitle>
          <DialogDescription>
            Sin tocar, cada marca sigue el switch global de la fase. Apágala para desviarse. {nota}
          </DialogDescription>
        </DialogHeader>
        <ExcepcionesPorMarca
          ajustes={deEtapa}
          onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
          guardando={guardar.isPending}
          maestros={{ [base]: etapaActiva }}
        />
      </DialogContent>
    </Dialog>
  );
}

export function PanelPipeline({
  titulo,
  fases,
  queuePorTipo,
  admisionEn,
  cola,
  esAdmin = true,
  chip,
}: {
  /** Título de la cabecera del panel. */
  titulo: string;
  /** Las fases del proceso, en orden de flujo. */
  fases: readonly FasePipeline[];
  /** Mapa tipo-de-job → clave de cola, para repartir los conteos por fase. */
  queuePorTipo: Record<string, string>;
  /** Clave de cola cuya fase muestra el admision de verificación (`cola.admision_verificacion`). */
  admisionEn?: string;
  /** Snapshot de la cola (conteos por fase). Sin él, las filas no muestran conteos. */
  cola?: ColaMonitor;
  /** Admin: lee/edita los switches del catálogo. No-admin: filas informativas. */
  esAdmin?: boolean;
  /** Indicador opcional en la cabecera (p. ej. jobs en curso del proceso). */
  chip?: React.ReactNode;
}) {
  // Doc abierto en el overlay «Editar prompt» (in-place, sin sacarte del cockpit).
  const [docEditando, setDocEditando] = React.useState<string | null>(null);
  // Fase cuyo diálogo de «Excepciones por marca» está abierto (o null).
  const [excepNombre, setExcepNombre] = React.useState<string | null>(null);

  // Catálogo de ajustes (solo admin: /api/ajustes devuelve 403 a un editor). Misma queryKey que
  // Configuración/drawer → React Query dedupe (cero peticiones extra).
  const { data } = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
    enabled: esAdmin,
  });
  const porClave = React.useMemo(() => {
    const mapa = new Map<string, AjusteAdmin>();
    for (const g of data?.grupos ?? []) for (const a of g.ajustes) mapa.set(a.clave, a);
    return mapa;
  }, [data]);
  const porMarca = React.useMemo(
    () =>
      (data?.grupos ?? [])
        .filter((g) => g.id.startsWith("automatizacion_marca"))
        .flatMap((g) => g.ajustes),
    [data],
  );

  const enCurso = cola ? contar(cola.en_curso, queuePorTipo) : {};
  const esperando = cola ? contar(cola.esperando, queuePorTipo) : {};

  const maquina = esAdmin ? porClave.get(CLAVE_MAQUINA) : undefined;
  const maquinaOn = Boolean(maquina?.valor);

  return (
    <section data-testid="panel-pipeline">
      {/* Cabecera (sin caja): título del proceso + indicador + maestro «Máquina». */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{titulo}</h3>
        <div className="flex flex-wrap items-center gap-3">
          {chip}
          {maquina && (
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">
                Máquina
                <span
                  className={cn(
                    "ml-1.5 text-xs font-medium",
                    maquinaOn ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400",
                  )}
                >
                  · {maquinaOn ? "on" : "off"}
                </span>
              </span>
              <SwitchAjuste
                ajuste={maquina}
                ariaLabel="Máquina (interruptor general de toda la auto-producción)"
                tono="estado"
              />
            </label>
          )}
        </div>
      </div>

      {/* Secuencia VERTICAL de fases, unidas por un conector (↓): el flujo se lee arriba→abajo. */}
      <ol className="w-full">
        {fases.map((e, i) => {
          const claveEfectiva = e.claves.find((c) => porClave.has(c));
          const ajuste = claveEfectiva ? porClave.get(claveEfectiva) : undefined;
          const doc = esAdmin ? e.doc : undefined;
          const deEtapa = e.excepciones
            ? porMarca.filter((a) => a.clave.startsWith(`${e.excepciones!.base}::`))
            : [];
          // «Editar prompt» es la acción de click izquierdo (abre el overlay): NO se
          // duplica en el menú contextual. El menú solo lleva las secundarias («Excepciones»).
          const editarPrompt = doc ? () => setDocEditando(doc) : undefined;
          const acciones: ItemMenuContextual[] = [];
          if (ajuste && e.excepciones && deEtapa.length > 0) {
            acciones.push({
              etiqueta: `Excepciones por marca de ${e.nombre}`,
              icono: Users,
              onClick: () => setExcepNombre(e.nombre),
            });
          }
          const conCola = e.queue !== undefined;
          const enCursoN = conCola ? (enCurso[e.queue!] ?? 0) : 0;
          const esperaN = conCola ? (esperando[e.queue!] ?? 0) : 0;
          const admision = e.queue !== undefined && e.queue === admisionEn ? cola?.admision_verificacion : undefined;
          return (
            <li key={e.nombre}>
              {/* Conector de flujo entre fases. */}
              {i > 0 && (
                <div className="flex justify-center py-1" aria-hidden="true">
                  <ChevronDown className="h-4 w-4 text-muted-foreground/40" />
                </div>
              )}
              <FilaConAcciones
                como="div"
                acciones={acciones}
                onPrimaria={editarPrompt}
                kebab="nunca"
                realce
                etiquetaAcciones={`Acciones de ${e.nombre}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-border/70 px-3.5 py-2.5"
              >
                {/* Izquierda: icono + nombre (línea 1) y ayuda/heredada (línea 2). Alto UNIFORME. */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    {e.es_ia ? (
                      <Bot className="h-4 w-4 shrink-0" aria-label="IA" />
                    ) : (
                      <Cog className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="determinista" />
                    )}
                    <span className="truncate">{e.nombre}</span>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {e.ayuda}
                    {e.heredada && <span className="text-muted-foreground/70"> · {e.heredada}</span>}
                  </p>
                </div>
                {/* Derecha: conteos de cola (1 línea) + el switch (indicador de estado). */}
                <div className="flex shrink-0 items-center gap-3">
                  {conCola && (
                    <span className="hidden text-right text-xs tabular-nums text-muted-foreground sm:block">
                      <span className={enCursoN > 0 ? "font-medium text-foreground" : undefined}>
                        {enCursoN} en curso
                      </span>{" "}
                      · {esperaN} en cola
                      {admision && <> · admision {admision.en_proceso}</>}
                    </span>
                  )}
                  {ajuste && (
                    <SwitchAjuste
                      ajuste={ajuste}
                      ariaLabel={`${ajuste.etiqueta} (switch de la fase ${e.nombre})`}
                    />
                  )}
                </div>
                {ajuste && e.excepciones && deEtapa.length > 0 && (
                  <DialogoExcepciones
                    etiqueta={e.nombre}
                    base={e.excepciones.base}
                    nota={e.excepciones.nota}
                    deEtapa={deEtapa}
                    etapaActiva={Boolean(ajuste.valor)}
                    abierto={excepNombre === e.nombre}
                    onOpenChange={(v) => setExcepNombre(v ? e.nombre : null)}
                  />
                )}
              </FilaConAcciones>
            </li>
          );
        })}
      </ol>

      <EditorPromptOverlay
        docId={docEditando}
        abierto={docEditando !== null}
        onCerrar={() => setDocEditando(null)}
      />
    </section>
  );
}

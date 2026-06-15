/**
 * PanelPipeline — el panel CONSOLIDADO de un pipeline (Investigación o Producción): una sola
 * superficie con TODAS las fases del proceso como TARJETAS GRANDES en orden de flujo. Cada
 * tarjeta lleva:
 *   · su ICONO de tipo — 🤖 (LLM) / ⚙ (determinista) —,
 *   · su INTERRUPTOR (on/off) — el toggle ES el indicador de estado; no hay puntos de color —,
 *   · sus CONTEOS de cola (en curso · en cola) donde la fase tiene trabajos (y el embudo opcional),
 *   · «Editar prompt» (las fases con prompt abren su doc de la Biblioteca en un overlay) y las
 *     «Excepciones por marca», en el menú de la tarjeta.
 * En la cabecera, el maestro «Máquina» (`KENI_MAQUINA`): apagado, nada automático corre.
 *
 * Genérico: el llamante le pasa las FASES (`fases`), el mapa tipo-de-job→fase para los conteos
 * (`queuePorTipo`) y opcionalmente qué fase muestra el embudo de verificación (`embudoEn`). Cada
 * fase resuelve su switch por la PRIMERA de sus `claves` presente en el catálogo; las que solo
 * tienen el maestro virtual del proceso lo indican con `heredada`.
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, Cog, SquarePen, Users } from "lucide-react";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { ItemMenuContextual } from "@/components/comunes/MenuContextual";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

/** Switch de UN ajuste bool con su PROPIA mutación (el «guardando» es de este control). */
function SwitchAjuste({ ajuste, ariaLabel }: { ajuste: AjusteAdmin; ariaLabel: string }) {
  const guardar = useGuardarAjuste();
  return (
    <Switch
      checked={Boolean(ajuste.valor)}
      disabled={guardar.isPending}
      onCheckedChange={(v) => guardar.mutate({ clave: ajuste.clave, valor: v })}
      aria-label={ariaLabel}
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
  embudoEn,
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
  /** Clave de cola cuya fase muestra el embudo de verificación (`cola.embudo_qa`). */
  embudoEn?: string;
  /** Snapshot de la cola (conteos por fase). Sin él, las tarjetas no muestran conteos. */
  cola?: ColaMonitor;
  /** Admin: lee/edita los switches del catálogo. No-admin: tarjetas informativas. */
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
    <Card data-testid="panel-pipeline">
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">{titulo}</CardTitle>
          <div className="flex flex-wrap items-center gap-3">
            {chip}
            {/* MAESTRO «Máquina» (KENI_MAQUINA): el interruptor general de TODA la auto-producción. */}
            {maquina && (
              <label className="flex items-center gap-2 text-sm">
                <span className={cn(maquinaOn ? "text-muted-foreground" : "text-destructive")}>
                  Máquina
                  <span className="ml-1.5 text-xs">{maquinaOn ? "· encendida" : "· apagada"}</span>
                </span>
                <SwitchAjuste
                  ajuste={maquina}
                  ariaLabel="Máquina (interruptor general de toda la auto-producción)"
                />
              </label>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-2">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {fases.map((e) => {
            const claveEfectiva = e.claves.find((c) => porClave.has(c));
            const ajuste = claveEfectiva ? porClave.get(claveEfectiva) : undefined;
            const doc = esAdmin ? e.doc : undefined;
            const deEtapa = e.excepciones
              ? porMarca.filter((a) => a.clave.startsWith(`${e.excepciones!.base}::`))
              : [];
            // Acciones de la tarjeta: «Editar prompt» (primaria, abre al click) y «Excepciones».
            const acciones: ItemMenuContextual[] = [];
            if (doc) {
              acciones.push({
                etiqueta: `Editar el prompt de ${e.nombre}`,
                icono: SquarePen,
                onClick: () => setDocEditando(doc),
              });
            }
            if (ajuste && e.excepciones && deEtapa.length > 0) {
              acciones.push({
                etiqueta: `Excepciones por marca de ${e.nombre}`,
                icono: Users,
                onClick: () => setExcepNombre(e.nombre),
              });
            }
            return (
              <FilaConAcciones
                key={e.nombre}
                como="div"
                acciones={acciones}
                onPrimaria={acciones[0]?.onClick}
                kebab="nunca"
                realce
                etiquetaAcciones={`Acciones de ${e.nombre}`}
                className="flex min-h-[5.5rem] flex-col rounded-lg border border-border/70 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
                    {e.es_ia ? (
                      <Bot className="h-4 w-4 shrink-0" aria-label="IA" />
                    ) : (
                      <Cog className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="determinista" />
                    )}
                    <span className="truncate">{e.nombre}</span>
                  </span>
                  {/* El switch ES el indicador de estado (no hay punto de color). */}
                  {ajuste && (
                    <SwitchAjuste
                      ajuste={ajuste}
                      ariaLabel={`${ajuste.etiqueta} (switch de la fase ${e.nombre})`}
                    />
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{e.ayuda}</p>
                {e.heredada && (
                  <p className="mt-0.5 text-[11px] text-muted-foreground/80">· {e.heredada}</p>
                )}
                {e.queue && (
                  <p className="mt-auto pt-1.5 text-xs tabular-nums text-muted-foreground">
                    <span
                      className={
                        (enCurso[e.queue] ?? 0) > 0 ? "font-medium text-foreground" : undefined
                      }
                    >
                      {enCurso[e.queue] ?? 0} en curso
                    </span>{" "}
                    · {esperando[e.queue] ?? 0} en cola
                  </p>
                )}
                {e.queue && e.queue === embudoEn && cola?.embudo_qa && (
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    Embudo: {cola.embudo_qa.en_vuelo} en vuelo
                    {cola.embudo_qa.tope_por_marca > 0 && (
                      <> · tope {cola.embudo_qa.tope_por_marca}/marca</>
                    )}
                  </p>
                )}
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
            );
          })}
        </div>
      </CardContent>

      <EditorPromptOverlay
        docId={docEditando}
        abierto={docEditando !== null}
        onCerrar={() => setDocEditando(null)}
      />
    </Card>
  );
}

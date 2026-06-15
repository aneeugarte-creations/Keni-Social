/**
 * RielInvestigacion — el PIPELINE de Investigación CONSOLIDADO: una sola superficie con TODAS las
 * fases del tramo aguas arriba como TARJETAS GRANDES en orden de flujo
 * (Recolectar · Agrupar · Fusionar · Traducir · Clasificar · Priorizar · Admitir · Verificar).
 *
 * Funde lo que antes eran DOS bloques (la tira informativa «Aguas arriba» y el control «Pipeline
 * en vivo» recortado a 2 etapas): cada fase es una tarjeta con
 *   · su ICONO de tipo — 🤖 (LLM) / ⚙ (determinista) —,
 *   · su INTERRUPTOR (on/off) — el toggle ES el indicador de estado; no hay puntos de color —,
 *   · sus CONTEOS de cola (en curso · en cola) donde la fase tiene trabajos, y el embudo de Verificar,
 *   · «Editar prompt» (las fases con prompt abren su doc de la Biblioteca en un overlay) y las
 *     «Excepciones por marca», en el menú de la tarjeta.
 * En la cabecera, el maestro «Máquina» (`KENI_MAQUINA`): apagado, nada automático corre.
 *
 * Cada fase resuelve su switch por su flag FÍSICO del catálogo; las fases sin flag propio
 * (Agrupar, Traducir, Admitir) caen al maestro virtual de Investigación (`KENI_INVESTIGACION`) y
 * lo indican con una nota («junto con Recolectar» / «con Investigación»): su toggle gobierna ese
 * flag compartido. El estado solo es legible/editable por admin (`/api/ajustes`).
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
import { ChipInvestigacion } from "@/pages/noticias/ChipInvestigacion";
import type { AjusteAdmin, ColaJob, ColaMonitor } from "@/types";

/** El interruptor GENERAL de la máquina (cabecera). Apagado, nada automático corre. */
const CLAVE_MAQUINA = "KENI_MAQUINA";
/** Maestro VIRTUAL de Investigación: respaldo de las fases sin flag físico propio. */
const MAESTRO_INVESTIGACION = "KENI_INVESTIGACION";

/** Las fases con trabajos en la cola: a cuál se asigna cada tipo de job. */
type QueueId = "recolectar" | "verificar";
const ETAPA_POR_TIPO: Record<string, QueueId> = {
  rss: "recolectar",
  "noticias-ia": "recolectar",
  insumos: "recolectar",
  pipeline: "verificar",
  verificacion: "verificar",
  "qa-editorial": "verificar",
};

function contar(jobs: ColaJob[]): Record<QueueId, number> {
  const c: Record<QueueId, number> = { recolectar: 0, verificar: 0 };
  for (const j of jobs) {
    const e = ETAPA_POR_TIPO[j.tipo];
    if (e) c[e] += 1;
  }
  return c;
}

interface Etapa {
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
  /** Fase con trabajos en cola: muestra sus conteos. */
  queue?: QueueId;
  /** Clave BASE de los toggles por marca (grupo `automatizacion_marca_*`) + nota de alcance. */
  excepciones?: { base: string; nota: string };
  /** Nota cuando el switch gobierna un flag COMPARTIDO (fase sin flag propio). */
  heredada?: string;
}

// El flujo COMPLETO del tramo aguas arriba (ADR 0011), en orden de ENTRADA a SALIDA.
const ETAPAS: readonly Etapa[] = [
  {
    nombre: "Recolectar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO_INVESTIGACION],
    ayuda: "Recolecta artículos de las fuentes",
    queue: "recolectar",
    excepciones: { base: MAESTRO_INVESTIGACION, nota: "Apaga Recolectar y Verificar juntas." },
  },
  {
    nombre: "Agrupar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO_INVESTIGACION],
    ayuda: "Agrupa las notas parecidas del mismo evento",
    heredada: "junto con Recolectar",
  },
  {
    nombre: "Fusionar",
    es_ia: true,
    claves: ["KENI_PIPELINE_FUSIONAR", MAESTRO_INVESTIGACION],
    ayuda: "Funde las notas agrupadas en una sola historia",
    doc: "prompt/fusionar",
  },
  {
    nombre: "Traducir",
    es_ia: true,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Adapta el texto al español de México",
    doc: "prompt/traducir",
    heredada: "con Investigación",
  },
  {
    nombre: "Clasificar",
    es_ia: true,
    claves: ["KENI_CLASIFICAR_MARCA_IA", MAESTRO_INVESTIGACION],
    ayuda: "Asigna marca a las notas de últimas horas",
    doc: "prompt/clasificar-marca",
  },
  {
    nombre: "Priorizar",
    es_ia: true,
    claves: ["KENI_PRIORIZAR_PERFIL_IA", MAESTRO_INVESTIGACION],
    ayuda: "Ordena por relevancia para tu marca",
    doc: "prompt/priorizar",
  },
  {
    nombre: "Admitir",
    es_ia: false,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Crea el tema admitido en la mesa de redacción",
    heredada: "con Investigación",
  },
  {
    nombre: "Verificar",
    es_ia: true,
    claves: ["KENI_PIPELINE_VERIFICAR", MAESTRO_INVESTIGACION],
    ayuda: "Contrasta las fuentes antes de pasar a la mesa",
    doc: "prompt/verificar",
    queue: "verificar",
    excepciones: { base: MAESTRO_INVESTIGACION, nota: "Apaga Recolectar y Verificar juntas." },
  },
] as const;

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

export function RielInvestigacion({
  cola,
  esAdmin = true,
}: {
  /** Snapshot de la cola (conteos por fase). Sin él, las tarjetas no muestran conteos. */
  cola?: ColaMonitor;
  /** Admin: lee/edita los switches del catálogo. No-admin: tarjetas informativas. */
  esAdmin?: boolean;
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

  const enCurso = cola ? contar(cola.en_curso) : { recolectar: 0, verificar: 0 };
  const esperando = cola ? contar(cola.esperando) : { recolectar: 0, verificar: 0 };

  const maquina = esAdmin ? porClave.get(CLAVE_MAQUINA) : undefined;
  const maquinaOn = Boolean(maquina?.valor);

  return (
    <Card data-testid="riel-investigacion">
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">Pipeline en vivo</CardTitle>
          <div className="flex flex-wrap items-center gap-3">
            <ChipInvestigacion />
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
          {ETAPAS.map((e) => {
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
                data-testid={`etapa-${e.nombre.toLowerCase()}`}
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
                  {/* El switch ES el indicador de estado (no hay punto de color). Las fases sin
                      flag propio gobiernan el compartido; las informativas (no-admin) no lo pintan. */}
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
                    <span className={enCurso[e.queue] > 0 ? "font-medium text-foreground" : undefined}>
                      {enCurso[e.queue]} en curso
                    </span>{" "}
                    · {esperando[e.queue]} en cola
                  </p>
                )}
                {/* Verificar acota aparte de la cola compartida: su embudo (en vuelo + tope/marca). */}
                {e.queue === "verificar" && cola?.embudo_qa && (
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

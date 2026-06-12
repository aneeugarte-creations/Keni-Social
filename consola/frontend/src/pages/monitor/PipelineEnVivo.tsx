/**
 * PIPELINE EN VIVO (Fase 2 de la consolidación del Monitor): la máquina de contenido como
 * una tira de etapas — Selección → Validación → Copy → Arte — con, EN CADA ETAPA, su
 * interruptor maestro AL LADO de su estado (conteos vivos del snapshot de la cola), en vez
 * de esconder el control en un drawer.
 *
 * Los toggles son los MISMOS ajustes maestros del catálogo (`/api/ajustes`, grupos
 * maestros_investigacion/maestros_produccion) con la MISMA mutación compartida
 * (`useGuardarAjuste`): una sola implementación del control. Investigación es UN maestro
 * que gobierna Selección y Validación a la vez: el switch vive en Selección y Validación
 * muestra el mismo estado (sin segundo switch para no duplicar el control).
 *
 * Los conteos salen de las listas en_curso/esperando del snapshot (respetan el switch
 * global de marca, como las tablas de abajo): cada job se asigna a su etapa con un mapa
 * EXPLÍCITO tipo→etapa; lo que no mapea cae en «Otros». Publicación no aparece: hoy no
 * hay jobs de cola de esa etapa (cuando los haya, se añade al mapa).
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_AJUSTES } from "@/pages/configuracion/lib";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import type { AjusteAdmin, ColaJob, ColaMonitor, Proceso } from "@/types";

import { PROC_META } from "./comun";

type EtapaId = "seleccion" | "validacion" | "copy" | "arte";

/** Las etapas de la tira, en orden de flujo. `clave` = su ajuste maestro del catálogo;
 *  `conSwitch:false` = la gobierna el maestro de otra etapa (solo muestra el estado). */
const ETAPAS: {
  id: EtapaId;
  etiqueta: string;
  proceso: Proceso;
  clave: string;
  conSwitch: boolean;
  descripcion: string;
}[] = [
  {
    id: "seleccion",
    etiqueta: "Selección",
    proceso: "investigacion",
    clave: "KENI_INVESTIGACION",
    conSwitch: true,
    descripcion:
      "Recolecta, deduplica, clasifica y rankea noticias para el pool. El maestro «Investigación» enciende Selección y Validación a la vez.",
  },
  {
    id: "validacion",
    etiqueta: "Validación",
    proceso: "investigacion",
    clave: "KENI_INVESTIGACION",
    conSwitch: false,
    descripcion: "Criba/QA de la fuente antes de escribir copy. Se enciende con Selección (maestro «Investigación»).",
  },
  {
    id: "copy",
    etiqueta: "Copy",
    proceso: "produccion",
    clave: "KENI_PRODUCCION",
    conSwitch: true,
    descripcion: "Redacta el copy que convierte una noticia verificada en pieza publicable.",
  },
  {
    id: "arte",
    etiqueta: "Arte",
    proceso: "produccion",
    clave: "KENI_PIPELINE_ARTE",
    conSwitch: true,
    descripcion: "Genera imagen por IA para los temas con copy y sin imagen.",
  },
];

/** Mapa EXPLÍCITO tipo de job → etapa de la tira. Lo que no mapea cae en «Otros». */
const ETAPA_POR_TIPO: Record<string, EtapaId> = {
  // Selección: trabajos del pool de noticias (ingesta/cajones).
  rss: "seleccion",
  "noticias-ia": "seleccion",
  insumos: "seleccion",
  // Validación: la criba/QA de la fuente (los jobs `pipeline` de la cola son esa criba)
  // y las verificaciones editoriales.
  pipeline: "validacion",
  verificacion: "validacion",
  "qa-editorial": "validacion",
  // Copy: redacción (manual o del pipeline).
  copy: "copy",
  autogen: "copy",
  // Arte: imagen IA.
  imagen: "arte",
};

type Conteos = Record<EtapaId | "otros", number>;

function contar(jobs: ColaJob[]): Conteos {
  const c: Conteos = { seleccion: 0, validacion: 0, copy: 0, arte: 0, otros: 0 };
  for (const j of jobs) c[ETAPA_POR_TIPO[j.tipo] ?? "otros"] += 1;
  return c;
}

/** Punto de estado ON/OFF de una etapa sin switch propio (la gobierna otro maestro). */
function PuntoEstado({ activo }: { activo: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px]",
        activo ? "text-emerald-600" : "text-muted-foreground",
      )}
      title="Se gobierna con el maestro «Investigación» (el switch de Selección)."
    >
      <span
        className={cn("h-2 w-2 rounded-full", activo ? "bg-emerald-500" : "bg-muted-foreground/40")}
        aria-hidden="true"
      />
      {activo ? "Activa" : "Apagada"}
    </span>
  );
}

export function PipelineEnVivo({
  cola,
  esAdmin,
  proceso,
}: {
  cola: ColaMonitor;
  esAdmin: boolean;
  /** Prefiltro de proceso (`?proceso=`): atenúa las etapas del otro loop. */
  proceso?: Proceso;
}) {
  const enCurso = contar(cola.en_curso);
  const esperando = contar(cola.esperando);
  const otros = enCurso.otros + esperando.otros;

  // Los maestros del catálogo (solo admin: /api/ajustes devuelve 403 a un editor). Misma
  // queryKey que Configuración/drawer: React Query dedupe (cero peticiones extra).
  const ajustes = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
    enabled: esAdmin,
  });
  const guardar = useGuardarAjuste();
  const guardandoClave = guardar.isPending ? (guardar.variables?.clave ?? null) : null;
  const porClave = React.useMemo(() => {
    const mapa = new Map<string, AjusteAdmin>();
    for (const g of ajustes.data?.grupos ?? []) for (const a of g.ajustes) mapa.set(a.clave, a);
    return mapa;
  }, [ajustes.data]);

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm">Pipeline en vivo</CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-2">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch">
          {ETAPAS.map((e, i) => {
            const ajuste = esAdmin ? porClave.get(e.clave) : undefined;
            const fuera = proceso != null && proceso !== e.proceso;
            return (
              <React.Fragment key={e.id}>
                {i > 0 && (
                  <ChevronRight
                    className="hidden h-4 w-4 shrink-0 self-center text-muted-foreground/60 lg:block"
                    aria-hidden="true"
                  />
                )}
                <div
                  className={cn(
                    "min-w-0 flex-1 rounded-lg border border-border/70 p-3",
                    fuera && "opacity-40",
                  )}
                  title={e.descripcion}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
                      <span
                        className={cn("h-2 w-2 shrink-0 rounded-full", PROC_META[e.proceso].barra)}
                        aria-hidden="true"
                      />
                      <span className="truncate">{e.etiqueta}</span>
                    </span>
                    {ajuste &&
                      (e.conSwitch ? (
                        <Switch
                          checked={Boolean(ajuste.valor)}
                          disabled={guardandoClave === e.clave}
                          onCheckedChange={(v) => guardar.mutate({ clave: e.clave, valor: v })}
                          aria-label={`${ajuste.etiqueta} (maestro de ${e.etiqueta})`}
                        />
                      ) : (
                        <PuntoEstado activo={Boolean(ajuste.valor)} />
                      ))}
                  </div>
                  <p className="mt-1.5 text-xs tabular-nums text-muted-foreground">
                    <span className={enCurso[e.id] > 0 ? "font-medium text-foreground" : undefined}>
                      {enCurso[e.id]} en curso
                    </span>{" "}
                    · {esperando[e.id]} en cola
                  </p>
                  {/* La Validación es el único punto donde Investigación acota aparte de la
                      cola compartida: su embudo de QA (en vuelo + tope por marca). */}
                  {e.id === "validacion" && cola.embudo_qa && (
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Embudo: {cola.embudo_qa.en_vuelo} en vuelo
                      {cola.embudo_qa.tope_por_marca > 0 && (
                        <> · tope {cola.embudo_qa.tope_por_marca}/marca</>
                      )}
                    </p>
                  )}
                </div>
              </React.Fragment>
            );
          })}
        </div>
        {otros > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            Otros trabajos (fuera de la tira): {enCurso.otros} en curso · {esperando.otros} en cola.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

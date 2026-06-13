/**
 * PIPELINE EN VIVO (Fase 2 de la consolidación del Monitor): la máquina de contenido como
 * una tira de etapas — Selección → Validación → Copy → Arte — con, EN CADA ETAPA, su
 * interruptor FÍSICO al lado de su estado (conteos vivos del snapshot de la cola) y un
 * acceso a sus EXCEPCIONES POR MARCA, en vez de esconder los controles en un drawer.
 *
 * JERARQUÍA DE PARO (de más global a más fino):
 *   1. «Máquina» (`KENI_MAQUINA`, cabecera de la tira): el interruptor general; apagado,
 *      NADA automático corre aunque las etapas estén encendidas.
 *   2. El switch de cada etapa: su clave FÍSICA del catálogo (`KENI_PIPELINE_SELECCION`/
 *      `_VALIDACION`/`_COPY`/`_ARTE`), una clave por etapa, sin fan-out. Las claves
 *      VIRTUALES `KENI_INVESTIGACION`/`KENI_PRODUCCION` ya no se pintan aquí (siguen en el
 *      catálogo para las excepciones por marca, la API/MCP y el riel de Noticias).
 *   3. Las excepciones por marca de cada etapa (diálogo del icono de la etapa): las claves
 *      por-marca existentes (`KENI_INVESTIGACION::m` —gobierna Selección y Validación a la
 *      vez—, `KENI_PRODUCCION::m`, `KENI_PIPELINE_ARTE::m`).
 *
 * Los toggles usan la MISMA mutación compartida (`useGuardarAjuste`), pero CADA control
 * monta su propia instancia: el estado «guardando» es por control, sin el race visual de
 * un `guardandoClave` global compartido entre componentes.
 *
 * Los conteos salen de las listas en_curso/esperando del snapshot (respetan el switch
 * global de marca, como las tablas de abajo): cada job se asigna a su etapa con un mapa
 * EXPLÍCITO tipo→etapa; lo que no mapea cae en «Otros». Publicación no aparece: hoy no
 * hay jobs de cola de esa etapa (cuando los haya, se añade al mapa).
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Users } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
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
import type { AjusteAdmin, ColaJob, ColaMonitor, Proceso } from "@/types";

import { PROC_META } from "./comun";

type EtapaId = "seleccion" | "validacion" | "copy" | "arte";

/** El interruptor GENERAL de la máquina (cabecera de la tira). */
const CLAVE_MAQUINA = "KENI_MAQUINA";

/** Las etapas de la tira, en orden de flujo. `clave` = su interruptor FÍSICO del catálogo;
 *  `excepciones` = la clave BASE de sus toggles por marca (los del grupo
 *  `automatizacion_marca_*` del catálogo) + la nota que explica su alcance. */
const ETAPAS: {
  id: EtapaId;
  etiqueta: string;
  proceso: Proceso;
  clave: string;
  descripcion: string;
  excepciones: { base: string; nota: string };
}[] = [
  {
    id: "seleccion",
    etiqueta: "Selección",
    proceso: "investigacion",
    clave: "KENI_PIPELINE_SELECCION",
    descripcion: "Recolecta, deduplica, clasifica y rankea noticias para el pool.",
    excepciones: {
      base: "KENI_INVESTIGACION",
      nota: "La excepción es por PROCESO: apagar «Investigación» en una marca apaga Selección y Validación a la vez para esa marca.",
    },
  },
  {
    id: "validacion",
    etiqueta: "Validación",
    proceso: "investigacion",
    clave: "KENI_PIPELINE_VALIDACION",
    descripcion: "Criba/QA de la fuente antes de escribir copy.",
    excepciones: {
      base: "KENI_INVESTIGACION",
      nota: "La excepción es por PROCESO: apagar «Investigación» en una marca apaga Selección y Validación a la vez para esa marca.",
    },
  },
  {
    id: "copy",
    etiqueta: "Copy",
    proceso: "produccion",
    clave: "KENI_PIPELINE_COPY",
    descripcion: "Redacta el copy que convierte una noticia verificada en pieza publicable.",
    excepciones: {
      base: "KENI_PRODUCCION",
      nota: "Apagar «Producción» en una marca la deja sin copy automático.",
    },
  },
  {
    id: "arte",
    etiqueta: "Arte",
    proceso: "produccion",
    clave: "KENI_PIPELINE_ARTE",
    descripcion: "Genera imagen por IA para los temas con copy y sin imagen.",
    excepciones: {
      base: "KENI_PIPELINE_ARTE",
      nota: "Apagar «Arte IA» en una marca la deja sin imagen por IA.",
    },
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

/** Switch de UN ajuste bool con su PROPIA mutación: el estado «guardando» es de este control,
 *  no un `guardandoClave` global que parpadee entre componentes (race visual). */
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

/** Acceso (icono → diálogo) a las EXCEPCIONES POR MARCA de una etapa de la tira: los toggles
 *  por-marca existentes del catálogo (clave `base::marca`), con el patrón único
 *  `ExcepcionesPorMarca`. Con el switch físico de la etapa apagado, las excepciones se ven
 *  apagadas/deshabilitadas (no aplican hasta encender la etapa). */
function ExcepcionesEtapa({
  etiqueta,
  base,
  nota,
  ajustes,
  etapaActiva,
}: {
  etiqueta: string;
  base: string;
  nota: string;
  ajustes: AjusteAdmin[];
  etapaActiva: boolean;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const guardar = useGuardarAjuste();
  const deEtapa = ajustes.filter((a) => a.clave.startsWith(`${base}::`));
  if (deEtapa.length === 0) return null;
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 w-6 p-0 text-muted-foreground"
        onClick={() => setAbierto(true)}
        title={`Excepciones por marca de ${etiqueta}`}
        aria-label={`Excepciones por marca de ${etiqueta}`}
      >
        <Users className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
      <Dialog open={abierto} onOpenChange={setAbierto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{etiqueta} · excepciones por marca</DialogTitle>
            <DialogDescription>
              Sin tocar, cada marca sigue el switch global de la etapa. Apágala para desviarse.{" "}
              {nota}
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
    </>
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

  // Los ajustes del catálogo (solo admin: /api/ajustes devuelve 403 a un editor). Misma
  // queryKey que Configuración/drawer: React Query dedupe (cero peticiones extra).
  const ajustes = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
    enabled: esAdmin,
  });
  const porClave = React.useMemo(() => {
    const mapa = new Map<string, AjusteAdmin>();
    for (const g of ajustes.data?.grupos ?? []) for (const a of g.ajustes) mapa.set(a.clave, a);
    return mapa;
  }, [ajustes.data]);
  const porMarca = React.useMemo(
    () =>
      (ajustes.data?.grupos ?? [])
        .filter((g) => g.id.startsWith("automatizacion_marca"))
        .flatMap((g) => g.ajustes),
    [ajustes.data],
  );

  const maquina = esAdmin ? porClave.get(CLAVE_MAQUINA) : undefined;
  const maquinaOn = Boolean(maquina?.valor);

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">Pipeline en vivo</CardTitle>
          {/* MAESTRO «Máquina» (KENI_MAQUINA): el interruptor general de TODA la
              auto-producción. Apagado, ninguna etapa corre en automático aunque sus
              switches estén encendidos (lo manual no depende de él). */}
          {maquina && (
            <label className="flex items-center gap-2 text-sm">
              <span className={cn(maquinaOn ? "text-muted-foreground" : "text-destructive")}>
                Máquina
                <span className="ml-1.5 text-xs">
                  {maquinaOn
                    ? "· encendida"
                    : "· apagada: para toda la auto-producción"}
                </span>
              </span>
              <SwitchAjuste
                ajuste={maquina}
                ariaLabel="Máquina (interruptor general de toda la auto-producción)"
              />
            </label>
          )}
        </div>
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
                    {ajuste && (
                      <span className="flex shrink-0 items-center gap-1">
                        <ExcepcionesEtapa
                          etiqueta={e.etiqueta}
                          base={e.excepciones.base}
                          nota={e.excepciones.nota}
                          ajustes={porMarca}
                          etapaActiva={Boolean(ajuste.valor)}
                        />
                        <SwitchAjuste
                          ajuste={ajuste}
                          ariaLabel={`${ajuste.etiqueta} (switch de la etapa ${e.etiqueta})`}
                        />
                      </span>
                    )}
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

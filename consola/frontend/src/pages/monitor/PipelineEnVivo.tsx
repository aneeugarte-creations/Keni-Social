/**
 * PIPELINE EN VIVO (Fase 2 de la consolidación del Monitor): la máquina de contenido como
 * una tira de etapas — Recolectar → Verificar → Redactar → Ilustrar — con, EN CADA ETAPA, su
 * interruptor FÍSICO al lado de su estado (conteos vivos del snapshot de la cola) y un
 * acceso a sus EXCEPCIONES POR MARCA, en vez de esconder los controles en un drawer.
 *
 * JERARQUÍA DE PARO (de más global a más fino):
 *   1. «Máquina» (`KENI_MAQUINA`, cabecera de la tira): el interruptor general; apagado,
 *      NADA automático corre aunque las etapas estén encendidas.
 *   2. El switch de cada etapa: su clave FÍSICA del catálogo (`KENI_PIPELINE_RECOLECTAR`/
 *      `_VERIFICAR`/`_REDACTAR`/`_ILUSTRAR`), una clave por etapa, sin fan-out. Las claves
 *      VIRTUALES `KENI_INVESTIGACION`/`KENI_PRODUCCION` ya no se pintan aquí (siguen en el
 *      catálogo para las excepciones por marca, la API/MCP y la línea de Noticias).
 *   3. Las excepciones por marca de cada etapa (diálogo del icono de la etapa): las claves
 *      por-marca existentes (`KENI_INVESTIGACION::m` —gobierna Recolectar y Verificar a la
 *      vez—, `KENI_PRODUCCION::m`, `KENI_PIPELINE_ILUSTRAR::m`).
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
import { Bot, ChevronRight, Cog, SquarePen, Users } from "lucide-react";
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
import type { AjusteAdmin, ColaJob, ColaMonitor, Proceso } from "@/types";

import { PROC_META } from "./comun";

type EtapaId = "recolectar" | "verificar" | "redactar" | "ilustrar";

/** El interruptor GENERAL de la máquina (cabecera de la tira). */
const CLAVE_MAQUINA = "KENI_MAQUINA";

/** Las etapas de la tira, en orden de flujo. `clave` = su interruptor FÍSICO del catálogo;
 *  `es_ia` distingue 🤖 (LLM) de ⚙ (determinista); `excepciones` = la clave BASE de sus
 *  toggles por marca (los del grupo `automatizacion_marca_*` del catálogo) + la nota que
 *  explica su alcance. */
const ETAPAS: {
  id: EtapaId;
  etiqueta: string;
  proceso: Proceso;
  clave: string;
  es_ia: boolean;
  descripcion: string;
  excepciones: { base: string; nota: string };
}[] = [
  {
    id: "recolectar",
    etiqueta: "Recolectar",
    proceso: "investigacion",
    clave: "KENI_PIPELINE_RECOLECTAR",
    es_ia: false,
    descripcion: "Recolecta, deduplica, clasifica y prioriza noticias para el pool.",
    excepciones: {
      base: "KENI_INVESTIGACION",
      nota: "Apaga Recolectar y Verificar juntas.",
    },
  },
  {
    id: "verificar",
    etiqueta: "Verificar",
    proceso: "investigacion",
    clave: "KENI_PIPELINE_VERIFICAR",
    es_ia: true,
    descripcion: "Criba/verificación de la fuente antes de escribir copy.",
    excepciones: {
      base: "KENI_INVESTIGACION",
      nota: "Apaga Recolectar y Verificar juntas.",
    },
  },
  {
    id: "redactar",
    etiqueta: "Redactar",
    proceso: "produccion",
    clave: "KENI_PIPELINE_REDACTAR",
    es_ia: true,
    descripcion: "Redacta el copy que convierte una noticia verificada en pieza publicable.",
    excepciones: {
      base: "KENI_PRODUCCION",
      nota: "Apagar «Producción» en una marca la deja sin copy automático.",
    },
  },
  {
    id: "ilustrar",
    etiqueta: "Ilustrar",
    proceso: "produccion",
    clave: "KENI_PIPELINE_ILUSTRAR",
    es_ia: true,
    descripcion: "Genera imagen por IA para los temas con copy y sin imagen.",
    excepciones: {
      base: "KENI_PIPELINE_ILUSTRAR",
      nota: "Apagar «Ilustrar» en una marca la deja sin imagen por IA.",
    },
  },
];

/** Mapa EXPLÍCITO tipo de job → etapa de la tira. Lo que no mapea cae en «Otros». */
const ETAPA_POR_TIPO: Record<string, EtapaId> = {
  // Recolectar: trabajos del pool de noticias (recolección/cajones).
  rss: "recolectar",
  "noticias-ia": "recolectar",
  insumos: "recolectar",
  // Verificar: la criba/verificación de la fuente (los jobs `pipeline` de la cola son esa
  // criba) y las verificaciones editoriales.
  pipeline: "verificar",
  verificacion: "verificar",
  "qa-editorial": "verificar",
  // Redactar: redacción (manual o del pipeline).
  copy: "redactar",
  autogen: "redactar",
  // Ilustrar: imagen IA.
  imagen: "ilustrar",
};

type Conteos = Record<EtapaId | "otros", number>;

function contar(jobs: ColaJob[]): Conteos {
  const c: Conteos = { recolectar: 0, verificar: 0, redactar: 0, ilustrar: 0, otros: 0 };
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

/** Diálogo CONTROLADO de las EXCEPCIONES POR MARCA de una etapa: los toggles por-marca
 *  existentes del catálogo (clave `base::marca`), con el patrón único `ExcepcionesPorMarca`.
 *  Ya no pinta su propio disparador: lo abre la acción «Excepciones por marca» del menú de la
 *  etapa (click derecho / long-press). Con el switch físico de la etapa apagado, las
 *  excepciones se ven apagadas/deshabilitadas (no aplican hasta encender la etapa). */
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
  );
}

export function PipelineEnVivo({
  cola,
  esAdmin,
  proceso,
  soloProceso,
  docPorEtapa,
}: {
  cola: ColaMonitor;
  esAdmin: boolean;
  /** Prefiltro de proceso (`?proceso=`): atenúa las etapas del otro loop. */
  proceso?: Proceso;
  /** RECORTA la tira a las etapas de UN solo motor (Producción → Redactar/Ilustrar; Investigación →
   *  Recolectar/Verificar). A diferencia de `proceso` (que solo atenúa), aquí las etapas del
   *  otro motor NO se pintan: cada cockpit muestra únicamente sus etapas. */
  soloProceso?: Proceso;
  /** «Editar prompt» por etapa (doc de la Biblioteca, p. ej. `prompt/redactar`): pinta un lápiz
   *  junto al nombre de la etapa que abre el editor en un OVERLAY (encima de la página, sin
   *  navegar). Solo admin (la Biblioteca es de admin). */
  docPorEtapa?: Partial<Record<EtapaId, string>>;
}) {
  // Doc abierto en el overlay «Editar prompt» (in-place, sin sacarte del cockpit).
  const [docEditando, setDocEditando] = React.useState<string | null>(null);
  // Etapa cuyo diálogo de «Excepciones por marca» está abierto (o null).
  const [excepEtapa, setExcepEtapa] = React.useState<EtapaId | null>(null);
  // Recorte por motor: el cockpit de Producción pide solo Redactar/Ilustrar; el de Investigación,
  // solo Recolectar/Verificar. Sin `soloProceso`, la tira completa (las cuatro etapas).
  const etapas = soloProceso ? ETAPAS.filter((e) => e.proceso === soloProceso) : ETAPAS;
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
                <span className="ml-1.5 text-xs">{maquinaOn ? "· encendida" : "· apagada"}</span>
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
          {etapas.map((e, i) => {
            const ajuste = esAdmin ? porClave.get(e.clave) : undefined;
            const fuera = proceso != null && proceso !== e.proceso;
            const doc = docPorEtapa?.[e.id];
            const deEtapa = porMarca.filter((a) => a.clave.startsWith(`${e.excepciones.base}::`));
            // Acciones de la etapa. El switch (on/off) es el control PRINCIPAL y va inline.
            // De las acciones de CONFIG: la primera es el click izquierdo (acción primaria) y
            // TODAS viven en el menú (click derecho / long-press). Sin iconos sueltos: la pista
            // es el realce naranja del borde al hover.
            const acciones: ItemMenuContextual[] = [];
            if (esAdmin && doc) {
              acciones.push({
                etiqueta: `Editar el prompt de ${e.etiqueta}`,
                icono: SquarePen,
                onClick: () => setDocEditando(doc),
              });
            }
            if (ajuste && deEtapa.length > 0) {
              acciones.push({
                etiqueta: `Excepciones por marca de ${e.etiqueta}`,
                icono: Users,
                onClick: () => setExcepEtapa(e.id),
              });
            }
            const accionPrimaria = acciones[0]?.onClick;
            return (
              <React.Fragment key={e.id}>
                {i > 0 && (
                  <ChevronRight
                    className="hidden h-4 w-4 shrink-0 self-center text-muted-foreground/60 lg:block"
                    aria-hidden="true"
                  />
                )}
                <FilaConAcciones
                  como="div"
                  acciones={acciones}
                  onPrimaria={accionPrimaria}
                  kebab="nunca"
                  realce
                  etiquetaAcciones={`Acciones de ${e.etiqueta}`}
                  className={cn(
                    "min-w-0 flex-1 rounded-lg border border-border/70 p-3",
                    fuera && "opacity-40",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
                      <span
                        className={cn("h-2 w-2 shrink-0 rounded-full", PROC_META[e.proceso].barra)}
                        aria-hidden="true"
                      />
                      {e.es_ia ? (
                        <Bot className="h-3.5 w-3.5 shrink-0" aria-label="IA" />
                      ) : (
                        <Cog className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="determinista" />
                      )}
                      <span className="truncate">{e.etiqueta}</span>
                    </span>
                    {/* El switch de la etapa es el control PRINCIPAL: se queda inline. */}
                    {ajuste && (
                      <SwitchAjuste
                        ajuste={ajuste}
                        ariaLabel={`${ajuste.etiqueta} (switch de la etapa ${e.etiqueta})`}
                      />
                    )}
                  </div>
                  <p className="mt-1.5 text-xs tabular-nums text-muted-foreground">
                    <span className={enCurso[e.id] > 0 ? "font-medium text-foreground" : undefined}>
                      {enCurso[e.id]} en curso
                    </span>{" "}
                    · {esperando[e.id]} en cola
                  </p>
                  {/* Verificar es el único punto donde Investigación acota aparte de la
                      cola compartida: su embudo de verificación (en vuelo + tope por marca). */}
                  {e.id === "verificar" && cola.embudo_qa && (
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Embudo: {cola.embudo_qa.en_vuelo} en vuelo
                      {cola.embudo_qa.tope_por_marca > 0 && (
                        <> · tope {cola.embudo_qa.tope_por_marca}/marca</>
                      )}
                    </p>
                  )}
                  {ajuste && deEtapa.length > 0 && (
                    <DialogoExcepciones
                      etiqueta={e.etiqueta}
                      base={e.excepciones.base}
                      nota={e.excepciones.nota}
                      deEtapa={deEtapa}
                      etapaActiva={Boolean(ajuste.valor)}
                      abierto={excepEtapa === e.id}
                      onOpenChange={(v) => setExcepEtapa(v ? e.id : null)}
                    />
                  )}
                </FilaConAcciones>
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
      <EditorPromptOverlay
        docId={docEditando}
        abierto={!!docEditando}
        onCerrar={() => setDocEditando(null)}
      />
    </Card>
  );
}

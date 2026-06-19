/**
 * PanelPipeline — el pipeline CONSOLIDADO de un proceso (Investigación o Producción) como una
 * SECUENCIA VERTICAL de fases: una fila por fase, en orden de flujo y unidas por un conector (↓),
 * para que el recorrido se lea de arriba a abajo. NO va dentro de una caja: es la superficie misma
 * (sin «cajas dentro de cajas»). Cada fila es UNIFORME (mismo alto) y lleva:
 *   · su ICONO de tipo — 🤖 (LLM) / ⚙ (determinista) —,
 *   · su INTERRUPTOR (on/off) — el toggle ES el indicador de estado; no hay puntos de color —,
 *   · sus CONTEOS de cola (en curso · en cola) donde la fase tiene trabajos,
 *   · al clicar la fila NAVEGA a la subpágina de la fase (Prompt · Acompaña · Logs) vía
 *     `onAbrirFase`; las «Excepciones por marca» van en el menú de la fila. No hay overlay.
 * El maestro del proceso y el interruptor general «Máquina» (`KENI_MAQUINA`) NO van aquí: viven
 * junto a las pestañas de Contexto (`ControlesMaquina`). Apagados, nada automático corre.
 *
 * Genérico: el llamante le pasa las FASES (`fases`), el mapa tipo-de-job→fase para los conteos
 * (`queuePorTipo`) y opcionalmente qué fase muestra el admision de verificación (`admisionEn`). Cada
 * fase resuelve su switch por la PRIMERA de sus `claves` presente en el catálogo; las que solo
 * tienen el maestro virtual del proceso NO pintan switch por fila (lo gobierna `ControlesMaquina`).
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, ChevronDown, Cog, Users } from "lucide-react";
import * as React from "react";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { Badge } from "@/components/ui/badge";
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
import { tieneContenido } from "@/pages/maquina/fases";
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
  /** Doc de la Prompts cuyo prompt alimenta la fase («Editar prompt»). */
  doc?: string;
  /** Sub-prompts que esta fase INYECTA en su propio prompt (no son etapas ni se lanzan solos):
   *  el detalle de la fase los lista para editarlos. P. ej. los envoltorios de red dentro de
   *  Redactar. Cada uno abre su doc en el overlay. */
  subPrompts?: readonly { nombre: string; doc: string; ayuda: string }[];
  /** Clave de cola de la fase (índice en los conteos): muestra sus en curso/en cola. */
  queue?: string;
  /** Clave BASE de los toggles por marca (grupo `automatizacion_marca_*`) + nota de alcance. */
  excepciones?: { base: string; nota: string };
  /** Nota descriptiva extra junto a la fase (p. ej. qué hace su switch: «el switch auto-aprueba las
   *  de bajo riesgo»). Se añade a la línea de ayuda de la fila. */
  heredada?: string;
  /** `true` si la fase inyecta el CONTEXTO editorial de la marca (voz, líneas, tropicalización,
   *  reglas): la pestaña «Contexto» del detalle muestra la estrategia de marca. */
  contextoMarca?: boolean;
  /** Clave de etapa del feed de runs (`GET /api/pipelines?etapa=`): la pestaña «Logs» del detalle
   *  lista el HISTÓRICO real de runs paradas en esta etapa. Sin ella, Logs solo muestra la cola viva. */
  etapa?: string;
  /** Aviso ROJO junto al nombre de la fase: la marca como acción de RIESGO real (p. ej. Publicar
   *  postea de verdad, no en simulación). Se pinta como Badge destructivo en la fila. */
  precaucion?: string;
  /** Abre una ETAPA distinta del flujo: en vez del conector ↓, la fila lleva encima un divisor con
   *  esta etiqueta. Marca que lo que sigue NO corre en la secuencia automática anterior (p. ej.
   *  «Cadena de aprobación»: la Crítica IA corre tras los OK humanos, no justo tras Ilustrar). */
  seccion?: string;
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

/**
 * Fila VISUAL de una entrada del pipeline (alto uniforme): icono de tipo (🤖/⚙) + nombre (línea 1)
 * y ayuda (línea 2) a la izquierda; un slot `derecha` (conteos, switch, chevron…) a la derecha.
 * La comparten las ETAPAS del pipeline y los SERVICIOS no-IA (mismo formato).
 */
export function FilaFasePipeline({
  esIa,
  nombre,
  ayuda,
  precaucion,
  derecha,
  onPrimaria,
  acciones = [],
  etiquetaAcciones,
}: {
  esIa: boolean;
  nombre: string;
  ayuda?: React.ReactNode;
  /** Aviso ROJO junto al nombre: marca la fase como acción de riesgo real (p. ej. Publicar). */
  precaucion?: string;
  derecha?: React.ReactNode;
  onPrimaria?: () => void;
  acciones?: ItemMenuContextual[];
  etiquetaAcciones?: string;
}) {
  return (
    <FilaConAcciones
      como="div"
      acciones={acciones}
      onPrimaria={onPrimaria}
      kebab="nunca"
      realce
      etiquetaAcciones={etiquetaAcciones}
      className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-card px-3.5 py-2.5"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          {esIa ? (
            <Bot className="h-4 w-4 shrink-0" aria-label="IA" />
          ) : (
            <Cog className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="determinista" />
          )}
          <span className="truncate">{nombre}</span>
          {precaucion && (
            <Badge variant="error" className="shrink-0 px-1.5 py-0 text-[10px] font-medium">
              {precaucion}
            </Badge>
          )}
        </div>
        {ayuda != null && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{ayuda}</p>
        )}
      </div>
      {derecha != null && <div className="flex shrink-0 items-center gap-3">{derecha}</div>}
    </FilaConAcciones>
  );
}

/**
 * Controles de la máquina, pensados para ir JUNTO a las pestañas de Contexto: el maestro del proceso
 * activo (`claveMaestro`: enciende/apaga todas sus fases) y el interruptor general «Máquina». Cada
 * toggle ES su indicador de estado (verde on / rojo off). Sin admin no pinta nada.
 */
export function ControlesMaquina({
  claveMaestro,
  esAdmin = true,
  marcaActiva = null,
}: {
  /** Maestro VIRTUAL del proceso activo (`KENI_INVESTIGACION`/`KENI_PRODUCCION`). */
  claveMaestro?: string;
  esAdmin?: boolean;
  /** Marca activa del workspace. Con una marca CONCRETA, el maestro lee/escribe
   *  `claveMaestro::marca` (el backend hace fan-out a las etapas de esa marca); con `null`
   *  ("Todas"), el maestro GLOBAL. Así el on/off del proceso aplica a la marca en la que trabajas. */
  marcaActiva?: string | null;
}) {
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
  const maquina = esAdmin ? porClave.get(CLAVE_MAQUINA) : undefined;
  const maquinaOn = Boolean(maquina?.valor);
  // Con marca concreta, el maestro de esa marca (`::marca`); en "Todas", el global.
  const claveMaestroEf = claveMaestro && marcaActiva ? `${claveMaestro}::${marcaActiva}` : claveMaestro;
  const maestro = esAdmin && claveMaestroEf ? porClave.get(claveMaestroEf) : undefined;
  const maestroOn = Boolean(maestro?.valor);
  if (!maestro && !maquina) return null;
  return (
    <div className="flex flex-wrap items-center gap-3">
      {maestro && (
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">
            {maestro.etiqueta}
            <span
              className={cn(
                "ml-1.5 text-xs font-medium",
                maestroOn ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400",
              )}
            >
              · {maestroOn ? "on" : "off"}
            </span>
          </span>
          <SwitchAjuste
            ajuste={maestro}
            ariaLabel={`${maestro.etiqueta} (maestro del proceso: enciende/apaga todas sus fases)`}
            tono="estado"
          />
        </label>
      )}
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
  );
}

export function PanelPipeline({
  fases,
  queuePorTipo,
  admisionEn,
  cola,
  esAdmin = true,
  claveMaestro,
  marcaActiva = null,
  onAbrirFase,
}: {
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
  /** Maestro VIRTUAL del proceso (`KENI_INVESTIGACION`/`KENI_PRODUCCION`): apaga TODAS sus fases a la
   *  vez. Las fases que resuelven su switch a ESTA clave (las que no tienen flag físico propio) NO
   *  muestran un switch por fila —eso colapsaría el proceso entero al tocar una sola fase—: NO pintan
   *  nada a la derecha; el maestro se surfacea como control único junto a las pestañas
   *  (`ControlesMaquina`), no aquí. */
  claveMaestro?: string;
  /** Marca activa del workspace. Con una marca CONCRETA, el switch de cada fase opera sobre
   *  `clave::marca` (su override por marca; el backend ya lo honra), así apagar una fase en una
   *  marca NO afecta al resto. En "Todas" (`null`), el switch global. Las fases sin variante por
   *  marca (p. ej. Clasificar, pre-marca) caen al global. */
  marcaActiva?: string | null;
  /** Si se pasa, el click izquierdo de cada fila NAVEGA al detalle de esa fase (su subpágina
   *  Prompt · Contexto · Logs) en vez de abrir el overlay de prompt. Es el modo de «Contexto». */
  onAbrirFase?: (fase: FasePipeline) => void;
}) {
  // Fase cuyo diálogo de «Excepciones por marca» está abierto (o null).
  const [excepNombre, setExcepNombre] = React.useState<string | null>(null);
  const navegable = onAbrirFase !== undefined;

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

  // Clave efectiva (primera presente en el catálogo) de cada fase, en orden. Sirve para detectar
  // SEGUIDORAS: fases cuyo switch NO debe ser editable por fila porque lo gobierna otro control —el
  // maestro de proceso (cabecera) o la fase DUEÑA de un flag granular compartido—. Sin esto, varias
  // fases pintaban el switch del maestro y tocar una apagaba el proceso entero (bug «apaga todos»).
  const efectivas = React.useMemo(
    () => fases.map((e) => e.claves.find((c) => porClave.has(c))),
    [fases, porClave],
  );
  // Índice de la PRIMERA fase que gobierna cada clave efectiva (su «dueña»): solo ella la edita.
  const duenoDeClave = React.useMemo(() => {
    const m = new Map<string, number>();
    efectivas.forEach((c, i) => {
      if (c && !m.has(c)) m.set(c, i);
    });
    return m;
  }, [efectivas]);

  const enCurso = cola ? contar(cola.en_curso, queuePorTipo) : {};
  const esperando = cola ? contar(cola.esperando, queuePorTipo) : {};

  return (
    <section data-testid="panel-pipeline">
      {/* Secuencia VERTICAL de fases, unidas por un conector (↓): el flujo se lee arriba→abajo. */}
      <ol className="w-full">
        {fases.map((e, i) => {
          const claveEfectiva = efectivas[i];
          // Con marca concreta, el switch opera sobre la variante por marca (`clave::marca`) si
          // existe en el catálogo; si no (fase pre-marca como Clasificar), cae al global. La
          // ESTRUCTURA (dueña/seguidora/maestro) se sigue resolviendo por la clave global.
          const claveSwitch =
            claveEfectiva && marcaActiva && porClave.has(`${claveEfectiva}::${marcaActiva}`)
              ? `${claveEfectiva}::${marcaActiva}`
              : claveEfectiva;
          const ajuste = claveSwitch ? porClave.get(claveSwitch) : undefined;
          // El switch de la fila es editable SOLO si la fase es la DUEÑA de su clave efectiva y esa
          // clave NO es el maestro de proceso (compartido): así Recolectar/Verificar/Redactar/Ilustrar
          // controlan cada uno SU clave y el maestro queda como control único de la cabecera. El resto
          // SIGUE a otro control (el maestro, o la fase dueña de un flag granular compartido).
          const esMaestroProceso = claveEfectiva !== undefined && claveEfectiva === claveMaestro;
          const esDuena = claveEfectiva !== undefined && duenoDeClave.get(claveEfectiva) === i;
          const switchEditable = Boolean(ajuste) && esDuena && !esMaestroProceso;
          const deEtapa = e.excepciones
            ? porMarca.filter((a) => a.clave.startsWith(`${e.excepciones!.base}::`))
            : [];
          const acciones: ItemMenuContextual[] = [];
          if (ajuste && e.excepciones && deEtapa.length > 0) {
            acciones.push({
              etiqueta: `Excepciones por marca de ${e.nombre}`,
              icono: Users,
              onClick: () => setExcepNombre(e.nombre),
            });
          }
          // Una fila SOLO es clicable/navegable si la fase tiene contenido propio que mostrar en su
          // subpágina (Prompt · Contexto · Logs). Las que solo tienen toggle (p. ej. Publicar) se
          // pintan como fila CON su switch, pero sin click izquierdo (su detalle no aportaría nada).
          const navegableFase = navegable && tieneContenido(e);
          const conCola = e.queue !== undefined;
          const enCursoN = conCola ? (enCurso[e.queue!] ?? 0) : 0;
          const esperaN = conCola ? (esperando[e.queue!] ?? 0) : 0;
          const admision = e.queue !== undefined && e.queue === admisionEn ? cola?.admision_verificacion : undefined;
          return (
            <li key={e.nombre}>
              {/* Entre fases: un conector ↓ (misma secuencia) o, si la fase abre una etapa distinta
                  (`seccion`), un divisor etiquetado que rompe la lectura secuencial. */}
              {i > 0 &&
                (e.seccion ? (
                  <div className="flex items-center gap-2 py-2">
                    <div className="h-px flex-1 bg-border" />
                    <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {e.seccion}
                    </span>
                    <div className="h-px flex-1 bg-border" />
                  </div>
                ) : (
                  <div className="flex justify-center py-1" aria-hidden="true">
                    <ChevronDown className="h-4 w-4 text-muted-foreground/40" />
                  </div>
                ))}
              <FilaFasePipeline
                esIa={e.es_ia}
                nombre={e.nombre}
                precaucion={e.precaucion}
                ayuda={
                  <>
                    {e.ayuda}
                    {e.heredada && <span className="text-muted-foreground/70"> · {e.heredada}</span>}
                  </>
                }
                onPrimaria={navegableFase ? () => onAbrirFase!(e) : undefined}
                acciones={acciones}
                etiquetaAcciones={`Acciones de ${e.nombre}`}
                derecha={
                  <>
                    {conCola && (
                      <span className="hidden text-right text-xs tabular-nums text-muted-foreground sm:block">
                        <span className={enCursoN > 0 ? "font-medium text-foreground" : undefined}>
                          {enCursoN} en curso
                        </span>{" "}
                        · {esperaN} en cola
                        {admision && <> · admision {admision.en_proceso}</>}
                      </span>
                    )}
                    {switchEditable && ajuste && (
                      <SwitchAjuste
                        ajuste={ajuste}
                        ariaLabel={`${ajuste.etiqueta} (switch de la fase ${e.nombre})`}
                      />
                    )}
                  </>
                }
              />
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
            </li>
          );
        })}
      </ol>
    </section>
  );
}

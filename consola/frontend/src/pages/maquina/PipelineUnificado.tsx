/**
 * PipelineUnificado — vista única FUENTE→FEED: los bloques del pipeline completo
 * (Ingesta → Procesar → Admitir → Producir → Aprobar) en una secuencia vertical.
 * Cada etapa tiene su propio toggle; las CRÍTICAS apagadas cortan el flujo posterior.
 *
 * Las secciones y etapas se DERIVAN de las dos máquinas de `fases.ts` (fuente única): no hay tabla
 * de etapas propia. `fases.ts` aporta por fase el `grupo` (sección), el `tipo` (criticidad/cascada),
 * la `clave` (toggle), la `queue` (conteos) y los `ajustes` (⚙).
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Settings2, Users } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import { CLAVE_AJUSTES } from "@/pages/configuracion/lib";
import {
  ExcepcionesPorMarca,
  FilaAjuste,
  useGuardarAjuste,
} from "@/pages/configuracion/SeccionFuncionalidad";
import {
  FASES_INVESTIGACION,
  FASES_PRODUCCION,
  QUEUE_INVESTIGACION,
  QUEUE_PRODUCCION,
  slugFase,
  tieneContenido,
} from "@/pages/maquina/fases";
import { SeccionCadenaAprobacion } from "@/pages/maquina/SeccionCadenaAprobacion";
import { ServiciosMaquina } from "@/pages/maquina/ServiciosMaquina";
import { FilaFasePipeline, type FasePipeline } from "@/pages/monitor/PanelPipeline";
import type { AjusteAdmin, ColaJob } from "@/types";

type TipoEtapa = "CRITICA" | "OPCIONAL";

interface Etapa {
  nombre: string;
  tipo: TipoEtapa;
  es_ia: boolean;
  ayuda: string;
  proceso: "investigacion" | "produccion";
  clave?: string;
  navegable?: boolean;
  /** Clave de cola de la etapa (índice en los conteos en_curso/esperando), si tiene jobs. */
  queue?: string;
  /** Knobs OPERACIONALES de la etapa (claves del catálogo) que se editan en su popover ⚙
   *  (umbrales/cupos/filtros), aparte de su toggle on/off. */
  ajustes?: readonly string[];
}

// Job-tipo → cola de la etapa (para los conteos en curso/en cola), unión de los dos motores.
const QUEUE_POR_TIPO: Record<string, string> = { ...QUEUE_INVESTIGACION, ...QUEUE_PRODUCCION };

function contarPorCola(jobs: ColaJob[]): Record<string, number> {
  const c: Record<string, number> = {};
  for (const j of jobs) {
    const e = QUEUE_POR_TIPO[j.tipo];
    if (e) c[e] = (c[e] ?? 0) + 1;
  }
  return c;
}

interface Fase {
  numero: string;
  titulo: string;
  etapas: Etapa[];
}

const CLAVE_MAQUINA = "KENI_MAQUINA";

/** Glifos de sección, por orden de aparición del `grupo` en las dos máquinas. */
const NUMEROS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"] as const;

/** Una fase del catálogo (`fases.ts`) → la ETAPA operable de esta vista. `fases.ts` es la fuente
 *  única: el toggle es su primera `clave`, la criticidad/cascada su `tipo` (OPCIONAL por defecto),
 *  los conteos su `queue`, los knobs ⚙ sus `ajustes` y la navegación, si tiene contenido propio. */
function aEtapa(f: FasePipeline, proceso: Etapa["proceso"]): Etapa {
  return {
    nombre: f.nombre,
    tipo: f.tipo ?? "OPCIONAL",
    es_ia: f.es_ia,
    ayuda: f.ayuda,
    proceso,
    clave: f.claves[0],
    navegable: tieneContenido(f),
    queue: f.queue,
    ajustes: f.ajustes,
  };
}

/**
 * Las secciones numeradas del pipeline FUENTE→FEED, DERIVADAS de las dos máquinas (`fases.ts`, la
 * fuente única). Recorre Investigación y luego Producción en orden de flujo, agrupa las fases
 * CONSECUTIVAS por su `grupo` (el encabezado «Ingesta», «Procesar el pool»…) y numera cada bloque
 * por orden de aparición. Sin lista de etapas propia: lo que se ve aquí es lo que vive en `fases.ts`.
 */
function construirPipeline(): Fase[] {
  const fuentes: { f: FasePipeline; proceso: Etapa["proceso"] }[] = [
    ...FASES_INVESTIGACION.map((f) => ({ f, proceso: "investigacion" as const })),
    ...FASES_PRODUCCION.map((f) => ({ f, proceso: "produccion" as const })),
  ];
  const fases: Fase[] = [];
  for (const { f, proceso } of fuentes) {
    const titulo = f.grupo ?? "Otras";
    let seccion = fases.find((s) => s.titulo === titulo);
    if (!seccion) {
      seccion = { numero: NUMEROS[fases.length] ?? "•", titulo, etapas: [] };
      fases.push(seccion);
    }
    seccion.etapas.push(aEtapa(f, proceso));
  }
  return fases;
}

const PIPELINE: Fase[] = construirPipeline();

const TODAS_LAS_ETAPAS: Etapa[] = PIPELINE.flatMap((f) => f.etapas);

function claveConMarca(clave: string, marcaActiva: string | null, porClave: Map<string, AjusteAdmin>): string {
  if (marcaActiva && porClave.has(`${clave}::${marcaActiva}`)) {
    return `${clave}::${marcaActiva}`;
  }
  return clave;
}

/** Nombre de marca de un ajuste por marca: su etiqueta es «Nombre · Etapa»; tomamos «Nombre».
 *  Si no encaja, cae al sufijo `::marca` de la clave. */
function nombreDeMarcaAjuste(a: AjusteAdmin): string {
  const izq = a.etiqueta.split("·")[0]?.trim();
  if (izq) return izq;
  return a.clave.split("::")[1] ?? a.clave;
}

interface Cascada {
  cortados: Set<string>;
  cutNombre: string | null;
  primerCortado: string | null;
}

function calcularCascada(
  marcaActiva: string | null,
  porClave: Map<string, AjusteAdmin>,
): Cascada {
  const cortados = new Set<string>();
  let cutNombre: string | null = null;
  let primerCortado: string | null = null;
  let cortando = false;

  for (const etapa of TODAS_LAS_ETAPAS) {
    if (cortando) {
      cortados.add(etapa.nombre);
      if (!primerCortado) primerCortado = etapa.nombre;
    } else if (etapa.tipo === "CRITICA" && etapa.clave) {
      const ajuste = porClave.get(claveConMarca(etapa.clave, marcaActiva, porClave));
      if (ajuste && !ajuste.valor) {
        cutNombre = etapa.nombre;
        cortando = true;
      }
    }
  }

  return { cortados, cutNombre, primerCortado };
}

export function PipelineUnificado({
  esAdmin = false,
  marcaActiva = null,
}: {
  esAdmin?: boolean;
  marcaActiva?: string | null;
}) {
  const navigate = useNavigate();
  const guardar = useGuardarAjuste();
  const [excepEtapa, setExcepEtapa] = React.useState<string | null>(null);
  const [ajustesEtapa, setAjustesEtapa] = React.useState<string | null>(null);

  const { data } = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
    enabled: esAdmin,
  });

  // Cola viva: conteos en curso / en cola por etapa (los mismos que la traza del Monitor).
  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
    enabled: esAdmin,
  });
  const enCurso = React.useMemo(
    () => (cola.data ? contarPorCola(cola.data.en_curso) : {}),
    [cola.data],
  );
  const esperando = React.useMemo(
    () => (cola.data ? contarPorCola(cola.data.esperando) : {}),
    [cola.data],
  );

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

  // La cascada (crítica apaga lo posterior) es POR MARCA: solo se pinta con una marca concreta.
  // En «Todas las marcas» (la matriz) cada marca diverge, así que no hay un único corte que pintar.
  const cascada = React.useMemo(
    () =>
      marcaActiva
        ? calcularCascada(marcaActiva, porClave)
        : { cortados: new Set<string>(), cutNombre: null, primerCortado: null },
    [marcaActiva, porClave],
  );

  const ajusteMaquina = esAdmin ? porClave.get(CLAVE_MAQUINA) : undefined;

  const excepEtapaObj = excepEtapa
    ? TODAS_LAS_ETAPAS.find((e) => e.nombre === excepEtapa)
    : null;
  const excepDeEtapa = excepEtapaObj?.clave
    ? porMarca.filter((a) => a.clave.startsWith(`${excepEtapaObj.clave}::`))
    : [];

  // Etapa cuyo diálogo de AJUSTES (knobs operacionales) está abierto, y sus claves.
  const ajustesEtapaObj = ajustesEtapa
    ? TODAS_LAS_ETAPAS.find((e) => e.nombre === ajustesEtapa)
    : null;

  const renderDerecha = (etapa: Etapa): React.ReactNode => {
    const conteos = etapa.queue ? (
      <span className="hidden text-right text-xs tabular-nums text-muted-foreground sm:block">
        <span className={(enCurso[etapa.queue] ?? 0) > 0 ? "font-medium text-foreground" : undefined}>
          {enCurso[etapa.queue] ?? 0} en curso
        </span>{" "}
        · {esperando[etapa.queue] ?? 0} en cola
      </span>
    ) : null;
    let control: React.ReactNode = null;
    if (esAdmin && etapa.clave) {
      const claveBase = etapa.clave;
      // MATRIZ: en «Todas las marcas» cada etapa con toggle por marca muestra UN switch por marca
      // (con su etiqueta), para ver y gobernar todas a la vez. Con una marca concreta, su columna.
      const deMarca = porMarca.filter((a) => a.clave.startsWith(`${claveBase}::`));
      if (marcaActiva === null && deMarca.length > 0) {
        control = (
          <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
            {deMarca.map((a) => (
              <label key={a.clave} className="flex items-center gap-1.5 text-xs">
                <span className="text-muted-foreground">{nombreDeMarcaAjuste(a)}</span>
                <Switch
                  checked={Boolean(a.valor)}
                  disabled={guardar.isPending}
                  onCheckedChange={(v) => guardar.mutate({ clave: a.clave, valor: v })}
                  aria-label={`${a.etiqueta}`}
                />
              </label>
            ))}
          </div>
        );
      } else {
        const ajuste = porClave.get(claveConMarca(claveBase, marcaActiva, porClave));
        control = ajuste ? (
          <Switch
            checked={Boolean(ajuste.valor)}
            disabled={guardar.isPending}
            onCheckedChange={(v) => guardar.mutate({ clave: ajuste.clave, valor: v })}
            aria-label={`${ajuste.etiqueta} (${etapa.nombre})`}
          />
        ) : (
          <span className="text-xs text-muted-foreground">vía env</span>
        );
      }
    }
    const tuning =
      esAdmin && etapa.ajustes && etapa.ajustes.length > 0 ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setAjustesEtapa(etapa.nombre);
          }}
          aria-label={`Ajustes de ${etapa.nombre}`}
          title={`Ajustes de ${etapa.nombre}`}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Settings2 className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : null;
    if (!conteos && !control && !tuning) return null;
    return (
      <div className="flex shrink-0 items-center gap-3">
        {conteos}
        {tuning}
        {control}
      </div>
    );
  };

  return (
    <div className="mt-4 space-y-4">
      {/* Master controls: admin only */}
      {esAdmin && ajusteMaquina && (
        <section className="rounded-lg border border-border bg-card p-4">
          <p className="mb-3 text-sm font-semibold">Estado global</p>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium">Auto</p>
                <p className="text-xs text-muted-foreground">Toda la auto-producción</p>
              </div>
              <Switch
                tono="estado"
                checked={Boolean(ajusteMaquina.valor)}
                disabled={guardar.isPending}
                onCheckedChange={(v) => guardar.mutate({ clave: ajusteMaquina.clave, valor: v })}
                aria-label="Auto (interruptor general de toda la auto-producción)"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              El empuje manual desde Noticias funciona aunque «Auto» esté apagado.
            </p>
          </div>
        </section>
      )}

      {/* Direction hint */}
      <p className="text-xs font-medium text-muted-foreground">FUENTE → FEED</p>

      {/* Pipeline phases */}
      {PIPELINE.map((fase, fi) => (
        <section key={fase.titulo} aria-labelledby={`pipeline-fase-${fi}`}>
          {fi > 0 && (
            <div className="flex justify-center py-2" aria-hidden="true">
              <ChevronDown className="h-4 w-4 text-muted-foreground/40" />
            </div>
          )}
          <div className="mb-2 flex items-center gap-1.5">
            <span className="text-sm" aria-hidden="true">
              {fase.numero}
            </span>
            <h3 id={`pipeline-fase-${fi}`} className="text-sm font-semibold">
              {fase.titulo}
            </h3>
          </div>
          <ol>
            {fase.etapas.map((etapa, ei) => {
              const esCortado = cascada.cortados.has(etapa.nombre);
              const esPrimerCortado = etapa.nombre === cascada.primerCortado;
              const claveEf = etapa.clave
                ? claveConMarca(etapa.clave, marcaActiva, porClave)
                : undefined;
              const ajuste = claveEf ? porClave.get(claveEf) : undefined;
              const esOpcionalOff =
                !esCortado &&
                etapa.tipo === "OPCIONAL" &&
                ajuste !== undefined &&
                !ajuste.valor;
              const deEtapa = etapa.clave
                ? porMarca.filter((a) => a.clave.startsWith(`${etapa.clave}::`))
                : [];

              return (
                <li key={etapa.nombre}>
                  {ei > 0 && (
                    <div className="flex justify-center py-1" aria-hidden="true">
                      <ChevronDown className="h-4 w-4 text-muted-foreground/40" />
                    </div>
                  )}
                  {esPrimerCortado && (
                    <div
                      data-testid="cut-marker"
                      className="mb-1 rounded border border-amber-200 bg-amber-50 px-3 py-1.5 text-center text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-400"
                    >
                      ↓ no llega — apagado en {cascada.cutNombre}
                    </div>
                  )}
                  <div
                    className={cn(
                      "transition-opacity",
                      esCortado && "opacity-50",
                      esOpcionalOff && "opacity-60",
                    )}
                  >
                    <FilaFasePipeline
                      esIa={etapa.es_ia}
                      nombre={etapa.nombre}
                      ayuda={etapa.ayuda}
                      onPrimaria={
                        etapa.navegable
                          ? () =>
                              navigate(
                                `/maquina/contexto/${etapa.proceso}/${slugFase(etapa.nombre)}`,
                              )
                          : undefined
                      }
                      acciones={
                        esAdmin && deEtapa.length > 0
                          ? [
                              {
                                etiqueta: `Excepciones por marca de ${etapa.nombre}`,
                                icono: Users,
                                onClick: () => setExcepEtapa(etapa.nombre),
                              },
                            ]
                          : []
                      }
                      etiquetaAcciones={`Acciones de ${etapa.nombre}`}
                      derecha={renderDerecha(etapa)}
                    />
                  </div>
                </li>
              );
            })}
          </ol>
          {/* Umbral de likes de la cadena de aprobación: parte de «Aprobar y publicar». */}
          {esAdmin && fase.titulo === "Aprobar y publicar" && (
            <div className="mt-3">
              <SeccionCadenaAprobacion marcaActiva={marcaActiva} />
            </div>
          )}
        </section>
      ))}

      {/* Servicios (daemons de mantenimiento, no-IA): bajo el pipeline, solo admin. */}
      {esAdmin && (
        <div className="space-y-3 border-t border-border pt-4">
          <ServiciosMaquina motor="investigacion" />
          <ServiciosMaquina motor="produccion" />
        </div>
      )}

      {/* Per-brand exceptions dialog */}
      {excepEtapaObj?.clave && (
        <Dialog
          open={excepEtapa !== null}
          onOpenChange={(v) => {
            if (!v) setExcepEtapa(null);
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{excepEtapa} · excepciones por marca</DialogTitle>
              <DialogDescription>
                Sin tocar, cada marca sigue el switch global de la fase.
              </DialogDescription>
            </DialogHeader>
            <ExcepcionesPorMarca
              ajustes={excepDeEtapa}
              onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
              guardando={guardar.isPending}
              maestros={{
                [excepEtapaObj.clave]: Boolean(porClave.get(excepEtapaObj.clave)?.valor),
              }}
            />
          </DialogContent>
        </Dialog>
      )}

      {/* Per-stage operational settings dialog (⚙) */}
      {ajustesEtapaObj?.ajustes && (
        <Dialog
          open={ajustesEtapa !== null}
          onOpenChange={(v) => {
            if (!v) setAjustesEtapa(null);
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{ajustesEtapa} · ajustes</DialogTitle>
              <DialogDescription>
                Knobs operacionales de esta etapa. Las excepciones por marca van en su propio menú.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              {ajustesEtapaObj.ajustes.map((clave) => {
                const a = porClave.get(clave);
                return a ? (
                  <FilaAjuste
                    key={clave}
                    ajuste={a}
                    onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
                    guardando={guardar.isPending}
                  />
                ) : (
                  <p key={clave} className="text-xs text-muted-foreground">
                    {clave} · vía env
                  </p>
                );
              })}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

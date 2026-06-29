/**
 * PipelineUnificado — vista única FUENTE→FEED: los 5 bloques del pipeline completo
 * (Ingesta → Procesar → Admitir → Producir → Aprobar) en una secuencia vertical.
 * Cada etapa tiene su propio toggle; las CRÍTICAS apagadas cortan el flujo posterior.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Users } from "lucide-react";
import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
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
  PanelAjustes,
  PanelInvestigacion,
  PanelMaquinaPublicacion,
  useGuardarAjuste,
} from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import { QUEUE_INVESTIGACION, QUEUE_PRODUCCION, slugFase } from "@/pages/maquina/fases";
import { SeccionCadenaAprobacion } from "@/pages/maquina/SeccionCadenaAprobacion";
import { ServiciosMaquina } from "@/pages/maquina/ServiciosMaquina";
import { FilaFasePipeline } from "@/pages/monitor/PanelPipeline";
import type { AjusteAdmin, ColaJob } from "@/types";

type TipoEtapa = "CRITICA" | "OPCIONAL" | "FIJO";

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
const CLAVE_PAUSA = "KENI_GENERACION_PAUSADA";

const PIPELINE: Fase[] = [
  {
    numero: "①",
    titulo: "Ingesta",
    etapas: [
      {
        nombre: "Recolectar",
        tipo: "CRITICA",
        es_ia: false,
        ayuda: "Recolecta artículos de las fuentes y agrupa las notas idénticas",
        proceso: "investigacion",
        clave: "KENI_PIPELINE_RECOLECTAR",
        queue: "recolectar",
        navegable: true,
      },
      {
        nombre: "Google Trends",
        tipo: "OPCIONAL",
        es_ia: false,
        ayuda: "Ingiere las tendencias de Google al pool, como fuente extra",
        proceso: "investigacion",
        clave: "KENI_TRENDS",
        navegable: true,
      },
    ],
  },
  {
    numero: "②",
    titulo: "Procesar el pool",
    etapas: [
      {
        nombre: "Fusionar",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Funde las notas del mismo hecho",
        proceso: "investigacion",
        clave: "KENI_PIPELINE_FUSIONAR",
        navegable: true,
      },
      {
        nombre: "Traducir",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Adapta el texto al español de México",
        proceso: "investigacion",
        clave: "KENI_PIPELINE_TRADUCIR",
        navegable: true,
      },
      {
        nombre: "Clasificar",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Asigna marca a las notas sin marca",
        proceso: "investigacion",
        clave: "KENI_CLASIFICAR_MARCA_IA",
        navegable: true,
      },
      {
        nombre: "Priorizar",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Ordena por relevancia para la marca",
        proceso: "investigacion",
        clave: "KENI_PRIORIZAR_PERFIL_IA",
        navegable: true,
      },
    ],
  },
  {
    numero: "③",
    titulo: "Admitir a la mesa",
    etapas: [
      {
        nombre: "Verificar",
        tipo: "CRITICA",
        es_ia: true,
        ayuda: "Contrasta las fuentes antes de la mesa (la noticia propia/portal se salta este paso)",
        proceso: "investigacion",
        clave: "KENI_PIPELINE_VERIFICAR",
        queue: "verificar",
        navegable: true,
      },
      {
        nombre: "Admitir",
        tipo: "CRITICA",
        es_ia: false,
        ayuda: "Crea el tema admitido en la mesa de redacción",
        proceso: "investigacion",
        clave: "KENI_PIPELINE_ADMITIR",
        navegable: true,
      },
    ],
  },
  {
    numero: "④",
    titulo: "Producir copy",
    etapas: [
      {
        nombre: "Decisor",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Elige el formato (foto o carrusel) antes de redactar",
        proceso: "produccion",
        clave: "KENI_PIPELINE_DECISOR",
        queue: "decisor",
        navegable: true,
      },
      {
        nombre: "Redactar",
        tipo: "CRITICA",
        es_ia: true,
        ayuda: "Redacta el copy que convierte la noticia en pieza",
        proceso: "produccion",
        clave: "KENI_PIPELINE_REDACTAR",
        queue: "redactar",
        navegable: true,
      },
      {
        nombre: "Keywords",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Propone hashtags y la imagen clave para el buscador de stock",
        proceso: "produccion",
        clave: "KENI_PIPELINE_SUGERIR_HASHTAGS",
        queue: "sugerir-hashtags",
        navegable: true,
      },
      {
        nombre: "Ilustrar",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Genera imagen por IA para los temas con copy y sin imagen",
        proceso: "produccion",
        clave: "KENI_PIPELINE_ILUSTRAR",
        queue: "ilustrar",
        navegable: true,
      },
      {
        nombre: "Stock",
        tipo: "OPCIONAL",
        es_ia: false,
        ayuda: "Adjunta una foto de stock de referencia (sin licencia) para los temas sin imagen",
        proceso: "produccion",
        clave: "KENI_PIPELINE_STOCK",
        navegable: true,
      },
    ],
  },
  {
    numero: "⑤",
    titulo: "Aprobar y publicar",
    etapas: [
      {
        nombre: "Avance",
        tipo: "FIJO",
        es_ia: false,
        ayuda: "Pasa el borrador completo a la cola de revisión",
        proceso: "produccion",
      },
      {
        nombre: "Crítica",
        tipo: "OPCIONAL",
        es_ia: true,
        ayuda: "Revisión IA con visión tras los OK humanos",
        proceso: "produccion",
        clave: "KENI_CRITICA_IA",
        navegable: true,
      },
      {
        nombre: "Pre-aprobación",
        tipo: "OPCIONAL",
        es_ia: false,
        ayuda: "Auto-aprueba las piezas de bajo riesgo",
        proceso: "produccion",
        clave: "KENI_AUTO_PREAPROBACION",
      },
      {
        nombre: "Programar",
        tipo: "FIJO",
        es_ia: false,
        ayuda: "Programa la pieza aprobada a su próximo hueco",
        proceso: "produccion",
      },
      {
        nombre: "Publicar",
        tipo: "CRITICA",
        es_ia: false,
        ayuda: "Publica de verdad en la red (apagado = simulación)",
        proceso: "produccion",
        clave: "KENI_PUBLICAR_REAL",
      },
    ],
  },
];

const TODAS_LAS_ETAPAS: Etapa[] = PIPELINE.flatMap((f) => f.etapas);

function claveConMarca(clave: string, marcaActiva: string | null, porClave: Map<string, AjusteAdmin>): string {
  if (marcaActiva && porClave.has(`${clave}::${marcaActiva}`)) {
    return `${clave}::${marcaActiva}`;
  }
  return clave;
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
  const [searchParams] = useSearchParams();
  const [excepEtapa, setExcepEtapa] = React.useState<string | null>(null);

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

  const cascada = React.useMemo(
    () => calcularCascada(marcaActiva, porClave),
    [marcaActiva, porClave],
  );

  const clavePausaEf = claveConMarca(CLAVE_PAUSA, marcaActiva, porClave);
  const ajusteMaquina = esAdmin ? porClave.get(CLAVE_MAQUINA) : undefined;
  const ajustePausa = esAdmin ? porClave.get(clavePausaEf) : undefined;

  // Ajustes del «⋮» del header: los DOS motores juntos (antes uno por pestaña).
  const ajustesDrawer = (
    <>
      <PanelInvestigacion />
      <PanelMaquinaPublicacion />
      <SeccionImagen />
      <PanelAjustes
        grupos={["automatismos_generales", "tuning"]}
        titulo="Sistema"
        descripcion="Automatismos, jobs, limpiezas, alertas y esfuerzo de razonamiento; sin reinicio."
      />
    </>
  );

  const excepEtapaObj = excepEtapa
    ? TODAS_LAS_ETAPAS.find((e) => e.nombre === excepEtapa)
    : null;
  const excepDeEtapa = excepEtapaObj?.clave
    ? porMarca.filter((a) => a.clave.startsWith(`${excepEtapaObj.clave}::`))
    : [];

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
    if (etapa.tipo === "FIJO") {
      control = (
        <Badge variant="outline" className="text-[10px] font-normal" data-testid="fijo-badge">
          fijo
        </Badge>
      );
    } else if (esAdmin && etapa.clave) {
      const ajuste = porClave.get(claveConMarca(etapa.clave, marcaActiva, porClave));
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
    if (!conteos && !control) return null;
    return (
      <div className="flex shrink-0 items-center gap-3">
        {conteos}
        {control}
      </div>
    );
  };

  return (
    <div className="mt-4 space-y-4">
      {/* Master controls: admin only */}
      {esAdmin && (ajusteMaquina || ajustePausa) && (
        <section className="rounded-lg border border-border bg-card p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-sm font-semibold">Estado global</p>
            <MenuAcciones
              etiqueta="Ajustes de la máquina"
              ajustesTitulo="Ajustes de la máquina"
              ajustesAbiertoInicial={searchParams.get("tab") === "ajustes"}
              ajustes={ajustesDrawer}
            />
          </div>
          <div className="space-y-3">
            {ajusteMaquina && (
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
            )}
            {ajusteMaquina && ajustePausa && <div className="h-px bg-border" aria-hidden="true" />}
            {ajustePausa && (
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">Pausa de emergencia</p>
                  <p className="text-xs text-muted-foreground">Detiene incluso el empuje manual</p>
                </div>
                <Switch
                  tono="estado"
                  checked={Boolean(ajustePausa.valor)}
                  disabled={guardar.isPending}
                  onCheckedChange={(v) => guardar.mutate({ clave: ajustePausa.clave, valor: v })}
                  aria-label="Pausa de emergencia"
                />
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              El empuje manual desde Noticias funciona aunque «Auto» esté apagado; solo lo detiene
              la pausa de emergencia.
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

      {/* Legend */}
      <p className="text-xs text-muted-foreground">
        🔴 crítica = apaga lo que viene después · 🟡 opcional = solo se oscurece
      </p>

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
    </div>
  );
}

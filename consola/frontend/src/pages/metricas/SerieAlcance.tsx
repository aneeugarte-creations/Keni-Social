/**
 * Alcance y frecuencia de cuenta del periodo (estrategia digital).
 *
 * El alcance (usuarios ÚNICOS que vieron la cuenta) es un FLUJO diario, no un stock ni un
 * volumen aditivo. Por sí sola, la serie día a día es ruido: lo accionable son los RATIOS
 * que la cuenta puede leer de un vistazo:
 *  - Frecuencia media diaria = impresiones ÷ alcance. Cuántas veces vio tu contenido la
 *    persona promedio cada día. Subir con alcance plano = saturación de la misma audiencia.
 *  - Amplificación = alcance medio diario ÷ seguidores. Cuánto escapa el contenido de tu
 *    propia burbuja (>1 = el algoritmo te distribuye a gente nueva).
 *
 * Solo Instagram expone alcance de cuenta (reach diario); el resto de redes no lo mide, así
 * que los dos denominadores (impresiones, seguidores) se piden SIEMPRE en su corte de
 * Instagram para casar con el alcance. Si la fuente no trae serie de alcance se dice con
 * honestidad en vez de inventar una línea. Distinto de las IMPRESIONES (volumen, aditivo),
 * la cifra de cabecera del periodo; aquí mandan el alcance único y su lectura en ratio.
 */
import { useQuery } from "@tanstack/react-query";
import { LineChart } from "@tremor/react";
import { Radar } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { numeroCompacto, numeroCompleto, redEnFoco, rendimientoRel } from "@/lib/formato";
import type { PuntoAlcance, PuntoSeguidores, PuntoSerie } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";
import { useVistaConfig } from "./vistaConfig";

/** Punto de color del tooltip por serie, coherente con `colors` del LineChart (Tremor). */
const PUNTO: Record<string, string> = { Alcance: "bg-sky-500", Impresiones: "bg-slate-400" };

/** "12 may" a partir de una fecha ISO (AAAA-MM-DD), en es-MX. */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(d);
}

/** Último valor CONOCIDO de Instagram en una serie de seguidores (la base actual). */
function seguidoresIgActual(puntos: PuntoSeguidores[]): number | null {
  for (let i = puntos.length - 1; i >= 0; i--) {
    const v = puntos[i].por_red.instagram;
    if (v != null) return v;
  }
  return null;
}

export function SerieAlcance({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);
  // El bloque es inherentemente de Instagram (única red con alcance de cuenta): si el filtro
  // global enfoca otra red, ni alcance ni ratios aplican y el bloque degrada a vacío honesto.
  const igEnFoco = redEnFoco(red, "instagram");

  const alcanceQuery = useQuery({
    queryKey: ["metricas", "serie-alcance", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasSerieAlcance({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Los dos denominadores van SIEMPRE en su corte de Instagram (la red del alcance), sin el
  // formato global: el alcance es de cuenta (no por pieza), así que casarlo con impresiones
  // filtradas por formato mezclaría planos. Solo se piden cuando IG está en foco.
  const impresionesQuery = useQuery({
    queryKey: ["metricas", "tendencia", rangoActual ?? "", marca_ ?? "todas", "instagram", "alcance"],
    queryFn: ({ signal }) =>
      api.metricasTendencia({ rango: rangoActual, marca: marca_, red: "instagram" }, signal),
    enabled: Boolean(rangoActual) && igEnFoco,
    staleTime: 2 * 60_000,
  });
  const seguidoresQuery = useQuery({
    queryKey: ["metricas", "seguidores", rangoActual ?? "", marca_ ?? "todas", "instagram", "alcance"],
    queryFn: ({ signal }) =>
      api.metricasSeguidores({ rango: rangoActual, marca: marca_, red: "instagram" }, signal),
    enabled: Boolean(rangoActual) && igEnFoco,
    staleTime: 2 * 60_000,
  });

  const { data, isPending, isError } = alcanceQuery;

  // Alcance ÚNICO de Instagram por día. Un día sin dato es un hueco honesto, no un 0 inventado.
  const alcancePorFecha = new Map<string, number>();
  for (const p of (data?.puntos ?? []) as PuntoAlcance[]) {
    alcancePorFecha.set(p.fecha, p.por_red.instagram ?? p.total);
  }
  // Impresiones IG por día (`visualizaciones` = impresiones en IG). Insumo de la frecuencia.
  const impresionesPorFecha = new Map<string, number>();
  for (const p of (impresionesQuery.data?.puntos ?? []) as PuntoSerie[]) {
    impresionesPorFecha.set(p.fecha, p.visualizaciones);
  }

  // Serie graficable: alcance (protagonista) + impresiones (contexto). La franja entre las dos
  // líneas ES la frecuencia. Un día sin impresiones deja hueco en su línea (no un 0 falso).
  const fechas = [...alcancePorFecha.keys()].sort((a, b) => a.localeCompare(b));
  const hayImpresiones = fechas.some((f) => impresionesPorFecha.has(f));
  const datos = fechas.map((f) => ({
    fecha: fechaCorta(f),
    Alcance: alcancePorFecha.get(f) ?? null,
    Impresiones: impresionesPorFecha.get(f) ?? null,
  }));

  // Frecuencia media diaria = Σ impresiones ÷ Σ alcance sobre los días con AMBOS datos (media
  // ponderada por alcance, robusta a un día de poco alcance). No usamos un alcance único de
  // periodo —no existe sin duplicar personas—, así que la frecuencia es por día.
  let sumaImpr = 0;
  let sumaAlcanceConImpr = 0;
  for (const f of fechas) {
    const a = alcancePorFecha.get(f);
    const i = impresionesPorFecha.get(f);
    if (a != null && a > 0 && i != null) {
      sumaImpr += i;
      sumaAlcanceConImpr += a;
    }
  }
  const frecuencia = sumaAlcanceConImpr > 0 ? sumaImpr / sumaAlcanceConImpr : null;

  // Amplificación = alcance medio diario ÷ seguidores IG (base actual). Sin seguidores → "—".
  const alcances = fechas
    .map((f) => alcancePorFecha.get(f))
    .filter((v): v is number => v != null && v > 0);
  const alcanceMedio = alcances.length
    ? alcances.reduce((s, v) => s + v, 0) / alcances.length
    : null;
  const seguidoresIg = seguidoresIgActual((seguidoresQuery.data?.puntos ?? []) as PuntoSeguidores[]);
  const amplificacion =
    alcanceMedio != null && seguidoresIg != null && seguidoresIg > 0
      ? alcanceMedio / seguidoresIg
      : null;

  return (
    <Seccion
      id="alcance-serie"
      titulo="Alcance y frecuencia"
      icono={Radar}
      descripcion="Alcance = usuarios ÚNICOS que vieron la cuenta cada día (solo lo mide Instagram). Lo accionable son los ratios: cuántas veces vio tu contenido la persona promedio (frecuencia) y cuánto escapa de tu base de seguidores (amplificación)."
    >
      <Card className="space-y-4 p-4 sm:p-6">
        {isPending ? (
          <Skeleton className="h-56 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No se pudo cargar la serie de alcance.
          </p>
        ) : fechas.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No hay alcance de cuenta para este periodo (solo Instagram lo mide).
          </p>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TarjetaKpi
                etiqueta="Frecuencia media diaria"
                valor={rendimientoRel(frecuencia)}
                titulo="Impresiones ÷ alcance: veces que la persona promedio vio la cuenta al día"
              />
              <TarjetaKpi
                etiqueta="Amplificación"
                valor={rendimientoRel(amplificacion)}
                titulo="Alcance diario ÷ seguidores: cuánto escapa el contenido de tu base"
              />
            </div>
            {/* Alternativa textual del chart para lectores de pantalla. */}
            <div
              role="img"
              aria-label={`Alcance e impresiones diarias del periodo (${data.etiqueta_rango})`}
            >
              <LineChart
                data={datos}
                index="fecha"
                categories={hayImpresiones ? ["Alcance", "Impresiones"] : ["Alcance"]}
                colors={hayImpresiones ? ["sky", "slate"] : ["sky"]}
                valueFormatter={numeroCompacto}
                showLegend={hayImpresiones}
                showAnimation
                startEndOnly
                curveType="monotone"
                className="h-56"
                customTooltip={({ payload, active }) =>
                  active && payload?.length ? (
                    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
                      <p className="text-muted-foreground">{payload[0]?.payload?.fecha}</p>
                      {payload.map((serie) => {
                        const nombre = String(serie.dataKey ?? "");
                        return (
                          <p
                            key={nombre}
                            className="flex items-center gap-2 font-medium tabular-nums"
                          >
                            <span
                              className={`inline-block h-2 w-2 shrink-0 rounded-full ${PUNTO[nombre] ?? "bg-muted-foreground"}`}
                              aria-hidden
                            />
                            {nombre}: {numeroCompleto(Number(serie.value ?? 0))}
                          </p>
                        );
                      })}
                    </div>
                  ) : null
                }
              />
            </div>
          </>
        )}
      </Card>
    </Seccion>
  );
}

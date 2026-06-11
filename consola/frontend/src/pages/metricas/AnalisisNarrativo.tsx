/**
 * Análisis narrativo del periodo: "qué cambió y por qué" + siguiente paso.
 *
 * Capa de lectura para un equipo de redes NO técnico sobre `GET /metricas/analisis`:
 * top movimientos (qué marca subió/bajó y la pieza que lo explica) y una sugerencia
 * accionable ya redactada por el backend. Es el resumen ejecutivo de la página, por
 * eso es una Card SIEMPRE visible (no colapsable) justo después de los KPIs.
 *
 * Los textos se pintan con los formateadores es-MX de `@/lib/formato`; el backend
 * entrega nombres de marca ya resueltos y `siguiente_paso.texto` como frase completa.
 */
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ExternalLink,
  Minus,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, plural, porcentaje, variacion } from "@/lib/formato";
import type { AnalisisDiario, MovimientoAnalisis } from "@/types";

import { MARCA_TODAS } from "./Controles";

/** Enlace externo a una pieza (nueva pestaña), con el icono de "sale de la app". */
function EnlacePieza({ url, children }: { url: string; children: React.ReactNode }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 underline-offset-2 hover:underline"
    >
      {children}
      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
    </a>
  );
}

/**
 * Un movimiento del periodo: icono de dirección + lectura en una frase y, si la hay,
 * la pieza que lo explica. GUARDIA: el backend emite `variacion_vis_pct = 0.0` cuando
 * la base es 0 (división imposible); "subió 0.0 %" OCULTARÍA un arranque desde cero,
 * así que ese caso se redacta como castellano natural —«estrenó vistas (antes 0)»—
 * con la insignia "Nuevo" FUERA de la frase, al final de la línea (incrustar el badge
 * dentro de la oración se leía «subió [Nuevo] en vistas»).
 */
function Movimiento({ m }: { m: MovimientoAnalisis }) {
  const sube = m.direccion === "sube";
  const baja = m.direccion === "baja";
  const Icono = sube ? TrendingUp : baja ? TrendingDown : Minus;
  const claseIcono = sube
    ? "text-emerald-600 dark:text-emerald-400"
    : baja
      ? "text-red-600 dark:text-red-400"
      : "text-muted-foreground";
  const esArranque = m.direccion !== "estable" && m.variacion_vis_pct === 0;
  const verbo = sube ? "subió" : "bajó";

  return (
    <li className="flex items-start gap-3">
      <Icono className={`mt-0.5 h-4 w-4 shrink-0 ${claseIcono}`} aria-hidden="true" />
      <div className="min-w-0 space-y-0.5">
        {/* div (no <p>): la insignia "Nuevo" es un <div> y anidarlo en <p> es HTML inválido. */}
        <div className="text-sm">
          <span className="font-medium">{m.marca}</span>{" "}
          {!sube && !baja
            ? "se mantuvo estable"
            : esArranque
              ? "estrenó vistas (antes 0)"
              : `${verbo} ${variacion(m.variacion_vis_pct)} en vistas`}
          {` · ${numeroCompacto(m.visualizaciones)} vistas en el periodo`}
          {m.engagement_pct != null && ` · ${porcentaje(m.engagement_pct)} de engagement`}
          {esArranque && (
            <>
              {" "}
              <Badge variant="ok">Nuevo</Badge>
            </>
          )}
        </div>
        {m.pieza && (
          <p className="text-sm text-muted-foreground">
            {"La explica: "}
            {m.pieza.url ? (
              <EnlacePieza url={m.pieza.url}>
                <span className="min-w-0">“{m.pieza.titulo}”</span>
              </EnlacePieza>
            ) : (
              <>“{m.pieza.titulo}”</>
            )}
            {` — ${nombreRed(m.pieza.plataforma)} · ${porcentaje(m.pieza.engagement_pct)} de engagement`}
          </p>
        )}
      </div>
    </li>
  );
}

/** Cuerpo de la tarjeta con datos ya cargados: movimientos, pie, avisos y paso. */
function CuerpoAnalisis({ data }: { data: AnalisisDiario }) {
  const sinMovimientos = data.movimientos.length === 0 && data.siguiente_paso === null;
  if (sinMovimientos) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Sin movimientos destacables en este periodo.
        {data.marcas_estables > 0 &&
          ` ${plural(data.marcas_estables, "marca estable", "marcas estables")}.`}
      </p>
    );
  }

  const partesPie: string[] = [];
  if (data.movimientos_resto > 0) {
    partesPie.push(
      `${plural(data.movimientos_resto, "movimiento menor", "movimientos menores")} más`,
    );
  }
  if (data.marcas_estables > 0) {
    partesPie.push(plural(data.marcas_estables, "marca estable", "marcas estables"));
  }

  return (
    <div className="space-y-4">
      {data.movimientos.length > 0 && (
        <ul className="space-y-3">
          {data.movimientos.map((m) => (
            <Movimiento key={m.marca_id} m={m} />
          ))}
        </ul>
      )}
      {partesPie.length > 0 && (
        <p className="text-xs text-muted-foreground">{partesPie.join(" · ")}</p>
      )}
      {data.cobertura_parcial.length > 0 && (
        <p
          className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200"
          role="status"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            Datos parciales de: {data.cobertura_parcial.join(", ")}
          </span>
        </p>
      )}
      {data.siguiente_paso && (
        <div className="rounded-lg border-l-4 border-emerald-500 bg-muted/40 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Siguiente paso
          </p>
          <p className="text-sm">{data.siguiente_paso.texto}</p>
          {data.siguiente_paso.pieza?.url && (
            <p className="mt-1 text-sm text-muted-foreground">
              <EnlacePieza url={data.siguiente_paso.pieza.url}>Ver la pieza</EnlacePieza>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function AnalisisNarrativo({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "analisis", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasAnalisis({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    // 2 min: misma frescura que el resto de secciones; "Actualizar" invalida igualmente.
    staleTime: 2 * 60_000,
  });

  if (isPending) return <Skeleton className="h-40 w-full rounded-xl" />;

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Qué cambió y por qué</CardTitle>
          {data?.es_muestra && <Badge variant="aviso">Datos de muestra</Badge>}
        </div>
        {data && <CardDescription>{data.etiqueta_rango}</CardDescription>}
      </CardHeader>
      <CardContent>
        {isError || !data ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No se pudo cargar el análisis del periodo.
          </p>
        ) : (
          <CuerpoAnalisis data={data} />
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Análisis del periodo: lectura multi-dimensión "qué pasó y por qué" + siguiente paso.
 *
 * Capa de lectura para un equipo de redes NO técnico sobre `GET /metricas/analisis`:
 * una lista de HALLAZGOS jerarquizados (lo más relevante primero) que cubren dimensiones
 * distintas —vistas por marca, red que empujó, formato que despunta, seguidores (con la
 * señal de variación representativa), engagement, pieza estrella y la variación propia del
 * periodo (semana ≠ mes)— más una sugerencia accionable ya redactada por el backend. Es el
 * resumen ejecutivo de la página: va en el encuadre uniforme (`<Seccion>`) con su contenido
 * en una Card, justo tras los KPIs.
 *
 * El backend entrega cada hallazgo como una frase completa en es-MX; esta capa la sirve
 * apetecible: las cifras grandes de la prosa se compactan al vuelo (174.961.503 → "175 M",
 * 11.9% → "12%") y la pieza que respalda un hallazgo va en una línea con "↳" —sin verbo—
 * con su título en frase (sin MAYÚSCULAS gritadas ni emojis, truncado en palabra). El
 * título íntegro queda en el `title` del enlace.
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
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, porcentaje, tituloLimpio } from "@/lib/formato";
import type { AnalisisDiario, HallazgoAnalisis } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";
import { useVistaConfig } from "./vistaConfig";

/**
 * Compacta las cifras DENTRO de la prosa del backend para que se sientan cantidades y no
 * números de serie: miles con punto → compacto es-MX vía `numeroCompacto` (solo ≥10.000;
 * "4.400" se queda), porcentajes con decimal → entero ("11.9%" → "12%", conserva el signo).
 * El resto de la frase queda intacto.
 */
function redondearProsa(texto: string): string {
  let t = texto.replace(
    /([+-]?)(\d+(?:\.\d+)?)\s*%/g,
    (_m, signo: string, num: string) => `${signo}${Math.round(Number(num))}%`,
  );
  t = t.replace(/\d{1,3}(?:\.\d{3})+/g, (m) => {
    const n = Number(m.replace(/\./g, ""));
    return n < 10_000 ? m : numeroCompacto(n);
  });
  return t;
}

/**
 * Si el título viene GRITADO (≥50% de sus letras en mayúsculas), baja a minúsculas cada
 * palabra íntegramente en mayúsculas (≥2 letras) y capitaliza la primera letra de la frase.
 * Las palabras ya mixtas ("And I Love Her", "TikTok") no se tocan; un título normal con
 * algún acrónimo ("Final de la Liga MX") no dispara el umbral y queda íntegro.
 */
function frasear(t: string): string {
  const letras = t.replace(/[^\p{L}]/gu, "");
  if (!letras) return t;
  const mayus = letras.replace(/[^\p{Lu}]/gu, "").length;
  if (mayus / letras.length < 0.5) return t;
  const bajado = t.replace(/\p{Lu}[\p{Lu}\p{N}]+/gu, (w) => w.toLowerCase());
  const i = bajado.search(/\p{L}/u);
  return i < 0 ? bajado : bajado.slice(0, i) + bajado[i].toUpperCase() + bajado.slice(i + 1);
}

/** Título de pieza apetecible para la línea "↳": sin emojis, sin gritos, corto. */
function tituloApetecible(t: string): string {
  return tituloLimpio(frasear(t), 64);
}

/** Enlace externo a una pieza (nueva pestaña), con el icono de "sale de la app". */
function EnlacePieza({ url, children }: { url: string; children: React.ReactNode }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-w-0 items-center gap-1 underline-offset-2 hover:underline"
    >
      {children}
      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
    </a>
  );
}

/**
 * Un hallazgo del periodo: icono de dirección + la frase del backend con las cifras
 * compactadas y, si el hallazgo apunta a una pieza, la pieza en una línea "↳" (título en
 * frase, enlazado, con su red legible y engagement redondeado).
 */
function Hallazgo({ h }: { h: HallazgoAnalisis }) {
  const sube = h.direccion === "sube";
  const baja = h.direccion === "baja";
  const Icono = sube ? TrendingUp : baja ? TrendingDown : Minus;
  const claseIcono = sube
    ? "text-emerald-600 dark:text-emerald-400"
    : baja
      ? "text-red-600 dark:text-red-400"
      : "text-muted-foreground";

  return (
    <li className="flex items-start gap-3">
      <Icono className={`mt-0.5 h-4 w-4 shrink-0 ${claseIcono}`} aria-hidden="true" />
      <div className="min-w-0 space-y-1">
        <p className="text-sm leading-relaxed">{redondearProsa(h.texto)}</p>
        {h.pieza && (
          <p className="flex min-w-0 items-baseline gap-2 text-sm text-muted-foreground">
            <span aria-hidden="true" className="shrink-0">
              ↳
            </span>
            <span className="min-w-0">
              {h.pieza.url ? (
                <EnlacePieza url={h.pieza.url}>
                  <span className="truncate" title={h.pieza.titulo}>
                    «{tituloApetecible(h.pieza.titulo)}»
                  </span>
                </EnlacePieza>
              ) : (
                <span title={h.pieza.titulo}>«{tituloApetecible(h.pieza.titulo)}»</span>
              )}
              {` — ${nombreRed(h.pieza.plataforma)} · ${redondearProsa(porcentaje(h.pieza.engagement_pct))} eng.`}
            </span>
          </p>
        )}
      </div>
    </li>
  );
}

/** Cuerpo de la tarjeta con datos ya cargados: hallazgos, aviso de cobertura y paso. */
function CuerpoAnalisis({ data }: { data: AnalisisDiario }) {
  const sinHallazgos = data.hallazgos.length === 0 && data.siguiente_paso === null;
  if (sinHallazgos) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Sin datos suficientes para una lectura del periodo.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {data.hallazgos.length > 0 && (
        <ul className="space-y-4">
          {data.hallazgos.map((h, i) => (
            <Hallazgo key={`${h.dimension}-${i}`} h={h} />
          ))}
        </ul>
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
          <p className="text-sm leading-relaxed">{data.siguiente_paso.texto}</p>
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
  const red = useVistaConfig((s) => s.red);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "analisis", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasAnalisis({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    // 2 min: misma frescura que el resto de secciones; "Actualizar" invalida igualmente.
    staleTime: 2 * 60_000,
  });

  return (
    <Seccion
      id="analisis"
      titulo="Análisis del periodo"
      icono={Sparkles}
      descripcion={data?.etiqueta_rango}
    >
      <Card>
        <CardContent className="pt-6">
          {isPending ? (
            <Skeleton className="h-40 w-full rounded-xl" />
          ) : isError || !data ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No se pudo cargar el análisis del periodo.
            </p>
          ) : (
            <CuerpoAnalisis data={data} />
          )}
        </CardContent>
      </Card>
    </Seccion>
  );
}

/**
 * Análisis del periodo: lectura multi-dimensión "qué pasó y por qué" + siguiente paso.
 *
 * Capa de lectura para un equipo de redes NO técnico sobre `GET /metricas/analisis`.
 * El panel reparte los hallazgos en dos columnas de igual peso —«Qué funcionó»
 * (izquierda, esmeralda) y «Qué vigilar» (derecha, rojo)— según el `grupo` que ya
 * clasifica el backend; los hallazgos sin valencia van en una franja de contexto
 * discreta bajo las columnas. Positivo a la izquierda porque en lectura LTR la
 * primera posición fija el marco (convención pros/contras y retrospectivas).
 *
 * Cada hallazgo con valencia es una fila ANCLA | FRASE: la cifra ancla (`cifra`,
 * ya formateada por el backend) va en una columna estrecha alineada a la derecha,
 * compartiendo línea base con la frase, y lleva debajo una micro-etiqueta
 * (`etiqueta`) que la nombra; la frase es autónoma (no repite el ancla). La cifra
 * se colorea solo si es una variación con signo (+/−); los niveles van en tinta.
 * Si el hallazgo apunta a una pieza, esta cuelga en gris con «↳» y sangría
 * francesa. Tono «susurro»: hairlines, versalitas con tracking amplio y color
 * únicamente donde significa.
 *
 * Las cifras grandes de la prosa se compactan al vuelo (174.961.503 → "175 M",
 * 11.9% → "12%") y los títulos de pieza se sirven en frase (sin MAYÚSCULAS
 * gritadas ni emojis, truncados en palabra); el título íntegro queda en el
 * `title` del enlace.
 */
import { useQuery } from "@tanstack/react-query";
import { Eye, ExternalLink, Sparkles, TrendingUp } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, porcentaje, tituloLimpio } from "@/lib/formato";
import { cn } from "@/lib/utils";
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
      className="underline decoration-border decoration-1 underline-offset-2 transition-colors hover:text-foreground hover:decoration-muted-foreground"
    >
      {children}
      <ExternalLink className="ml-0.5 inline h-3 w-3 shrink-0 align-[-1px]" aria-hidden="true" />
    </a>
  );
}

/** Línea de pieza «↳ "título" — Red · X% eng.» con sangría francesa. */
function LineaPieza({ pieza }: { pieza: NonNullable<HallazgoAnalisis["pieza"]> }) {
  return (
    <p className="mt-1.5 -indent-[18px] pl-[18px] text-[13px] leading-5 text-muted-foreground">
      <span aria-hidden="true" className="mr-1.5 text-muted-foreground/60">
        ↳
      </span>
      {pieza.url ? (
        <EnlacePieza url={pieza.url}>
          <span title={pieza.titulo}>«{tituloApetecible(pieza.titulo)}»</span>
        </EnlacePieza>
      ) : (
        <span title={pieza.titulo}>«{tituloApetecible(pieza.titulo)}»</span>
      )}
      {` — ${nombreRed(pieza.plataforma)} · ${redondearProsa(porcentaje(pieza.engagement_pct))} eng.`}
    </p>
  );
}

/**
 * Una fila ANCLA | FRASE de las columnas del panel. La cifra ancla se colorea solo si
 * es una variación con signo; los niveles (15%, 1/21…) van en tinta normal para que el
 * color siga significando dirección, no decoración.
 */
function FilaHallazgo({ h }: { h: HallazgoAnalisis }) {
  const cifra = h.cifra ? redondearProsa(h.cifra) : null;
  const varia = cifra?.startsWith("+") ? "pos" : cifra?.startsWith("-") ? "neg" : null;
  return (
    <article className="grid grid-cols-[84px_1fr] items-baseline gap-x-3.5">
      <div className="min-w-0">
        <p
          className={cn(
            "whitespace-nowrap text-right text-[15px] font-semibold leading-5 tracking-tight tabular-nums",
            varia === "pos" && "text-emerald-700 dark:text-emerald-400",
            varia === "neg" && "text-red-600 dark:text-red-400",
          )}
        >
          {cifra}
        </p>
        {h.etiqueta && (
          <p className="mt-[3px] whitespace-nowrap text-right text-[9.5px] font-medium uppercase leading-[11px] tracking-[0.08em] text-muted-foreground/80">
            {h.etiqueta}
          </p>
        )}
      </div>
      <div className="min-w-0">
        <p className="text-sm leading-5 tabular-nums">{redondearProsa(h.texto)}</p>
        {h.pieza && <LineaPieza pieza={h.pieza} />}
      </div>
    </article>
  );
}

/** Una columna del panel: encabezado en versalitas de color + filas con aire regular. */
function Columna({ lado, filas }: { lado: "funciono" | "vigilar"; filas: HallazgoAnalisis[] }) {
  const pos = lado === "funciono";
  const Icono = pos ? TrendingUp : Eye;
  const titulo = pos ? "Qué funcionó" : "Qué vigilar";
  return (
    <section className="min-w-0 px-6 pb-8 pt-6" aria-label={titulo}>
      <h3
        className={cn(
          "mb-6 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase leading-none tracking-[0.13em]",
          pos ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400",
        )}
      >
        <Icono className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        {titulo}
      </h3>
      <div className="space-y-[30px]">
        {filas.map((h, i) => (
          <FilaHallazgo key={`${h.dimension}-${i}`} h={h} />
        ))}
      </div>
    </section>
  );
}

/** Cuerpo de la tarjeta con datos ya cargados: columnas, contexto y paso. */
function CuerpoAnalisis({ data }: { data: AnalisisDiario }) {
  const sinHallazgos = data.hallazgos.length === 0 && data.siguiente_paso === null;
  if (sinHallazgos) {
    return (
      <p className="px-6 py-10 text-center text-sm text-muted-foreground">
        Sin datos suficientes para una lectura del periodo.
      </p>
    );
  }

  const positivos = data.hallazgos.filter((h) => h.grupo === "positivo");
  const vigilar = data.hallazgos.filter((h) => h.grupo === "vigilar");
  const contexto = data.hallazgos.filter((h) => h.grupo !== "positivo" && h.grupo !== "vigilar");
  const dosColumnas = positivos.length > 0 && vigilar.length > 0;

  return (
    <div>
      {(positivos.length > 0 || vigilar.length > 0) && (
        <div className={cn("grid", dosColumnas && "md:grid-cols-2 md:divide-x md:divide-border")}>
          {positivos.length > 0 && <Columna lado="funciono" filas={positivos} />}
          {vigilar.length > 0 && (
            <div className={cn("min-w-0", dosColumnas && "border-t md:border-t-0")}>
              <Columna lado="vigilar" filas={vigilar} />
            </div>
          )}
        </div>
      )}
      {contexto.length > 0 && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t bg-muted/30 px-6 py-3">
          <span className="text-[10.5px] font-semibold uppercase leading-none tracking-[0.13em] text-muted-foreground">
            Contexto
          </span>
          <p className="text-[13px] leading-relaxed text-muted-foreground tabular-nums">
            {contexto.map((h, i) => (
              <span key={`${h.dimension}-${i}`}>
                {i > 0 && <span className="mx-1.5 text-muted-foreground/50">·</span>}
                {redondearProsa(h.texto)}
              </span>
            ))}
          </p>
        </div>
      )}
      {data.siguiente_paso && (
        <div className="p-6 pt-4">
          <div className="rounded-r-lg border-l-2 border-emerald-700 bg-muted/30 px-4 py-4 dark:border-emerald-400">
            <p className="mb-2 text-[10.5px] font-semibold uppercase leading-none tracking-[0.13em] text-emerald-700 dark:text-emerald-400">
              Siguiente paso
            </p>
            <p className="text-sm leading-relaxed tabular-nums">{data.siguiente_paso.texto}</p>
            {data.siguiente_paso.pieza?.url && (
              <p className="mt-1.5 text-[13px] text-muted-foreground">
                <EnlacePieza url={data.siguiente_paso.pieza.url}>Ver la pieza</EnlacePieza>
              </p>
            )}
          </div>
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
        <CardContent className="p-0">
          {isPending ? (
            <Skeleton className="h-40 w-full rounded-xl" />
          ) : isError || !data ? (
            <p className="px-6 py-10 text-center text-sm text-muted-foreground">
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

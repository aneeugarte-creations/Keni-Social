/**
 * Panorama de piezas: scatter temporal de TODO lo publicado en el rango — una "nube"
 * de puntos que cuenta la historia de un vistazo.
 *
 * Cada punto es una pieza, en su FECHA REAL de publicación:
 *   - X  = fecha de publicación (eje temporal; etiquetas por semana y por mes).
 *   - Y  = vistas en escala LOGARÍTMICA.
 *   - Tamaño = engagement %.
 *   - Color y FORMA = red social (la forma distingue redes sin depender solo del color).
 *
 * Un ÚNICO <Scatter> con el color por punto (así ninguna red tapa a otra) y un jitter
 * pequeño y determinista que separa piezas del mismo día sin falsear su posición. Antes se
 * "aplastaban" al lunes y se agrupaban por banda de vistas, lo que apilaba redes distintas
 * en el centro de la semana y hacía parecer que cada semana era de una sola red. Brillo
 * propio con un glow acotado (se desactiva con muchísimos puntos, por rendimiento).
 *
 * El panel y los colores se adaptan al TEMA (claro = fondo blanco; oscuro = casi negro con
 * glow), vía las variables del sistema de diseño.
 *
 * Tiene query y PERIODO PROPIOS (selector 7 d / 30 d / 90 d / 1 año, independiente del rango
 * global del dashboard) y paga sus propias llamadas a la API; solo `EvolucionRedes` comparte
 * caché (misma `queryKey`) con `PiezasConsolidada`.
 */
import { useQuery } from "@tanstack/react-query";
import { Telescope } from "lucide-react";
import * as React from "react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { marcaParam } from "@/components/comunes/selectores";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import { nombreRed, numeroCompacto, numeroCompleto, porcentaje, redCanonica } from "@/lib/formato";
import type { PiezaListado } from "@/types";

import { colorDe } from "./coloresRed";
import { MARCA_TODAS } from "./Controles";
import { tokenRango } from "./rango";
import { SeccionColapsable } from "./SeccionColapsable";

/** Radio base (px) de las burbujas según engagement. */
const R_MIN = 3;
const R_MAX = 10;
/** Jitter (± px) para separar piezas del mismo día/altura sin falsear su posición. */
const JITTER_X = 7;
const JITTER_Y = 5;
/** A partir de cuántos puntos se desactiva el glow (drop-shadow es caro por punto). */
const MAX_PUNTOS_GLOW = 300;

/** Periodos seleccionables (días hacia atrás desde hoy; máx. 366 por el límite del backend). */
const PERIODOS: Array<{ dias: number; label: string }> = [
  { dias: 7, label: "7 d" },
  { dias: 30, label: "30 d" },
  { dias: 90, label: "90 d" },
  { dias: 364, label: "1 año" },
];

/** Punto del scatter ya preparado para recharts. */
interface PuntoDato {
  x: number; // timestamp (ms) — FECHA REAL de publicación
  y: number; // log10(visualizaciones) — eje vertical (vistas)
  r: number; // radio en px (deriva de engagement)
  jx: number; // jitter horizontal (px) — separa piezas del mismo día
  jy: number; // jitter vertical (px)
  red: string; // red canónica
  fill: string; // color de la red (por punto: un solo Scatter, sin tapados)
  id: string;
  titulo: string;
  publicado: string;
  visualizaciones: number;
  engagement_pct: number;
}

/** Timestamp (ms) de una fecha ISO `AAAA-MM-DD`, o null si no es válida. */
function tsDeISO(iso: string): number | null {
  const [a, m, d] = (iso || "").split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return null;
  return new Date(a, m - 1, d).getTime();
}

/** Fecha legible larga es-MX ("3 may 2021"). */
function fechaLarga(iso: string): string {
  const t = tsDeISO(iso);
  if (t == null) return "—";
  return new Date(t).toLocaleDateString("es-MX", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Etiqueta de semana: día del mes ("7", "14", …). */
function fmtDiaSemana(ts: number): string {
  return String(new Date(ts).getDate());
}

/** Etiqueta de mes + año capitalizada ("May 2021"), como la referencia. */
function fmtMes(ts: number): string {
  const d = new Date(ts);
  const mes = d.toLocaleDateString("es-MX", { month: "short" }).replace(".", "");
  return `${mes.charAt(0).toUpperCase()}${mes.slice(1)} ${d.getFullYear()}`;
}

/** Hash determinista de un id a [0,1) — para textura estable (no salta en cada render). */
function hash01(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967296;
}

/**
 * Forma SVG de cada red, centrada en (x, y) con "radio" r — además del color, la FORMA
 * distingue la red (accesible sin depender solo del color): facebook = círculo,
 * instagram = cuadrado, tiktok = triángulo, youtube = rombo, X = cruz. La usan los
 * puntos del scatter y la leyenda (mismo lenguaje visual en ambos sitios).
 */
function formaRed(
  red: string,
  x: number,
  y: number,
  r: number,
  props: React.SVGAttributes<SVGElement>,
): React.ReactElement {
  switch (red) {
    case "instagram": // cuadrado
      return <rect x={x - r} y={y - r} width={2 * r} height={2 * r} {...props} />;
    case "tiktok": // triángulo
      return <polygon points={`${x},${y - r} ${x + r},${y + r} ${x - r},${y + r}`} {...props} />;
    case "youtube": // rombo (cuadrado rotado 45°: vértices a distancia r del centro)
      return <polygon points={`${x},${y - r} ${x + r},${y} ${x},${y + r} ${x - r},${y}`} {...props} />;
    case "x": {
      // cruz (signo +): brazos de medio-grosor t
      const t = r * 0.4;
      return (
        <path
          d={`M ${x - t} ${y - r} H ${x + t} V ${y - t} H ${x + r} V ${y + t} H ${x + t} V ${y + r} H ${x - t} V ${y + t} H ${x - r} V ${y - t} H ${x - t} Z`}
          {...props}
        />
      );
    }
    default: // facebook (y cualquier otra red): círculo
      return <circle cx={x} cy={y} r={r} {...props} />;
  }
}

/** Punto del scatter: la forma de su red, con su color (`payload.fill`), trazo de
 *  contraste (legible sobre fondo claro) y brillo propio acotado. */
function Punto(props: { cx?: number; cy?: number; payload?: PuntoDato; glow?: boolean }) {
  const { cx, cy, payload, glow = true } = props;
  if (cx == null || cy == null || !payload) return null;
  const { r, fill, red, jx, jy } = payload;
  return formaRed(red, cx + jx, cy + jy, r, {
    fill,
    fillOpacity: 0.85,
    stroke: "hsl(var(--foreground))",
    strokeOpacity: 0.25,
    strokeWidth: 1,
    style: glow ? { filter: `drop-shadow(0 0 ${Math.min(2, r * 0.45)}px ${fill})` } : undefined,
  });
}

/** Tooltip (tematizado) con el detalle de la pieza bajo el cursor. */
function TooltipPanorama(props: { active?: boolean; payload?: Array<{ payload: PuntoDato }> }) {
  const p = props.active ? props.payload?.[0]?.payload : undefined;
  if (!p) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="mb-1 max-w-[16rem] truncate font-medium" title={p.titulo}>
        {p.titulo || "(sin título)"}
      </p>
      <ul className="space-y-0.5 text-muted-foreground">
        <li className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: colorDe(p.red) }}
          />
          {nombreRed(p.red)} · {fechaLarga(p.publicado)}
        </li>
        <li>
          Vistas:{" "}
          <span className="tabular-nums text-foreground">{numeroCompleto(p.visualizaciones)}</span>
        </li>
        <li>
          Engagement:{" "}
          <span className="tabular-nums text-foreground">{porcentaje(p.engagement_pct)}</span>
        </li>
      </ul>
    </div>
  );
}

export function PanoramaPiezas({
  marcaActual = MARCA_TODAS,
  desnudo = false,
}: {
  /** Marca global del dashboard (switch de la barra superior): acota la consulta. */
  marcaActual?: string;
  /** `true` => solo el gráfico, sin el `SeccionColapsable` (título/colapso). */
  desnudo?: boolean;
}) {
  const marca_ = marcaParam(marcaActual);

  // El Panorama tiene su PROPIO selector de periodo (no usa el rango global de arriba): pide
  // los últimos `dias` días (máx. 366 por el límite del backend). Por eso usa su propia queryKey.
  const [dias, setDias] = React.useState(364);
  // Día de HOY en zona CDMX (no la del navegador): ancla del rango. Como entra en las deps
  // del memo (y por tanto en la queryKey vía el token), el rango rota solo si la pestaña
  // queda abierta de un día para otro.
  const hoyIso = hoyCDMX();
  const rangoPeriodo = React.useMemo(() => {
    const iso = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate(),
      ).padStart(2, "0")}`;
    // Anclado a mediodía para que la resta de días no derive con los cambios de hora.
    const desde = new Date(`${hoyIso}T12:00:00`);
    desde.setDate(desde.getDate() - dias);
    return tokenRango(iso(desde), hoyIso);
  }, [dias, hoyIso]);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado-periodo", rangoPeriodo, marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoPeriodo, marca: marca_ }, signal),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo<PiezaListado[]>(() => data?.piezas ?? [], [data]);

  const { puntos, redesPresentes, ticksMes, ticksSemana, domainX, total, ticksY } =
    React.useMemo(() => {
      // Puntos válidos: con fecha parseable y números finitos.
      const base = piezas
        .map((p) => {
          const x = tsDeISO(p.publicado);
          if (x == null) return null;
          if (!Number.isFinite(p.engagement_pct) || !Number.isFinite(p.visualizaciones))
            return null;
          return { p, x };
        })
        .filter((v): v is { p: PiezaListado; x: number } => v !== null);

      const totalPuntos = base.length;

      // Radio adaptativo al nº de puntos; dentro de eso, engagement modula el tamaño.
      const factorTam = totalPuntos <= 30 ? 1.3 : totalPuntos <= 150 ? 1.0 : 0.75;
      const engs = base.map((b) => b.p.engagement_pct);
      const minE = engs.length ? Math.min(...engs) : 0;
      const maxE = engs.length ? Math.max(...engs) : 0;
      const radio = (e: number): number => {
        const r =
          maxE <= minE
            ? (R_MIN + R_MAX) / 2
            : R_MIN + (R_MAX - R_MIN) * Math.sqrt((e - minE) / (maxE - minE));
        return r * factorTam;
      };

      // Cada pieza en su FECHA REAL (no se aplasta a la semana): así las redes se ven
      // mezcladas día a día, reflejando la realidad. Color por punto (un solo Scatter) y
      // jitter pequeño y determinista para separar piezas del mismo día sin falsear su sitio.
      const flat: PuntoDato[] = base.map(({ p, x }) => {
        const red = redCanonica(p.plataforma) || "otra";
        return {
          x,
          y: Math.log10(Math.max(1, p.visualizaciones)),
          r: radio(p.engagement_pct),
          jx: (hash01(p.id + "x") - 0.5) * 2 * JITTER_X,
          jy: (hash01(p.id + "y") - 0.5) * 2 * JITTER_Y,
          red,
          fill: colorDe(red),
          id: p.id,
          titulo: p.titulo,
          publicado: p.publicado,
          visualizaciones: p.visualizaciones,
          engagement_pct: p.engagement_pct,
        };
      });

      // Ticks del eje Y (log): potencias de 10 (1, 10, 100, 1K, …) hasta el máximo.
      const maxViews = totalPuntos ? Math.max(...base.map((b) => b.p.visualizaciones)) : 1;
      const maxExp = Math.max(1, Math.ceil(Math.log10(Math.max(10, maxViews))));
      const ticks = Array.from({ length: maxExp + 1 }, (_, i) => i);

      // Rango temporal REAL + dominio con un pequeño margen a los lados.
      const xs = base.map((b) => b.x);
      const minX = xs.length ? Math.min(...xs) : 0;
      const maxX = xs.length ? Math.max(...xs) : 0;
      const PAD_MS = 3 * 24 * 60 * 60 * 1000;
      const dom: [number, number] = [minX - PAD_MS, maxX + PAD_MS];

      // Meses del rango (para el eje de meses y las marcas semanales).
      const inicio = new Date(minX);
      let yy = inicio.getFullYear();
      let mm = inicio.getMonth();
      const fin = new Date(maxX);
      const finY = fin.getFullYear();
      const finM = fin.getMonth();
      const meses: number[] = [];
      while (yy < finY || (yy === finY && mm <= finM)) {
        meses.push(new Date(yy, mm, 1).getTime());
        mm++;
        if (mm > 11) {
          mm = 0;
          yy++;
        }
      }

      // Ticks de MES dentro del dominio + el borde izquierdo etiquetado. Dedup; muestreo ~7.
      const candidatosMes = [dom[0], ...meses]
        .filter((t) => t >= dom[0] && t <= dom[1])
        .sort((a, b) => a - b);
      const vistosMes = new Set<string>();
      const mesesUnicos: number[] = [];
      for (const t of candidatosMes) {
        const k = fmtMes(t);
        if (!vistosMes.has(k)) {
          vistosMes.add(k);
          mesesUnicos.push(t);
        }
      }
      const pasoMes = Math.max(1, Math.ceil(mesesUnicos.length / 7));
      const ticksMesF = mesesUnicos.filter((_, i) => i % pasoMes === 0);

      // Ticks de DÍA: un tick por cada día del rango (etiqueta = día del mes). Si hay
      // muchísimos (rango largo), se muestrean para que no se amontonen. Iteramos por
      // día de calendario (no sumando ms) para no derivar con los cambios de hora.
      const dias: number[] = [];
      const cur = new Date(minX);
      cur.setHours(0, 0, 0, 0);
      while (cur.getTime() <= maxX) {
        dias.push(cur.getTime());
        cur.setDate(cur.getDate() + 1);
      }
      const MAX_TICKS_DIA = 45;
      const pasoDia = Math.max(1, Math.ceil(dias.length / MAX_TICKS_DIA));
      const ticksSemF = dias.filter((_, i) => i % pasoDia === 0);

      // Redes presentes (orden canónico) para la leyenda.
      const orden = ["facebook", "instagram", "tiktok", "youtube", "x"];
      const presentes = Array.from(new Set(flat.map((p) => p.red))).sort(
        (a, b) => (orden.indexOf(a) + 1 || 99) - (orden.indexOf(b) + 1 || 99),
      );

      return {
        puntos: flat,
        redesPresentes: presentes,
        ticksMes: ticksMesF,
        ticksSemana: ticksSemF,
        domainX: dom,
        total: totalPuntos,
        ticksY: ticks,
      };
    }, [piezas]);

  const conGlow = total <= MAX_PUNTOS_GLOW;

  // Selector de periodo (segmentado) — siempre visible, también en carga/vacío.
  const selectorPeriodo = (
    <div className="inline-flex rounded-md border border-border p-0.5" role="group" aria-label="Periodo">
      {PERIODOS.map((p) => (
        <button
          key={p.dias}
          type="button"
          onClick={() => setDias(p.dias)}
          aria-pressed={dias === p.dias}
          className={cn(
            "rounded px-2.5 py-1.5 text-xs transition-colors",
            dias === p.dias
              ? "bg-accent font-medium text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {p.label}
        </button>
      ))}
    </div>
  );

  const contenido = isPending ? (
        <Skeleton className="h-[420px] w-full rounded-xl" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar el panorama de piezas.
        </p>
      ) : total === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aún no hay piezas publicadas en este periodo.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card p-6">
          {/* Leyenda: redes presentes con su color Y su forma (la misma del scatter) +
              rótulo de honestidad de la escala (eje log) y de la codificación por tamaño. */}
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {redesPresentes.map((red) => (
              <span
                key={red}
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
              >
                <svg className="h-3 w-3" viewBox="0 0 12 12" aria-hidden="true">
                  {formaRed(red, 6, 6, 4, {
                    fill: colorDe(red),
                    stroke: "hsl(var(--foreground))",
                    strokeOpacity: 0.25,
                    strokeWidth: 1,
                  })}
                </svg>
                {nombreRed(red)}
              </span>
            ))}
            <span className="ml-auto inline-flex items-center gap-1.5">
              <span className="inline-flex items-center gap-1" aria-hidden="true">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
                <span className="h-3 w-3 rounded-full bg-muted-foreground" />
              </span>
              <span className="text-xs text-muted-foreground">
                Eje vertical: vistas en escala logarítmica · tamaño del punto = engagement
              </span>
            </span>
          </div>

          <ResponsiveContainer width="100%" height={384}>
            <ScatterChart margin={{ top: 12, right: 22, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} strokeDasharray="3 3" />
              {/* Eje de DÍAS (día del mes), pegado al gráfico. En rangos largos (> 90 d) se
                  oculta (height 0, sin ticks): sería una fila de números 1-31 sin valor. El
                  eje debe existir igualmente porque el Scatter lo referencia por xAxisId. */}
              <XAxis
                xAxisId="sem"
                type="number"
                dataKey="x"
                domain={domainX}
                ticks={ticksSemana}
                interval={0}
                tickFormatter={fmtDiaSemana}
                tick={dias > 90 ? false : { fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                tickLine={false}
                axisLine={dias > 90 ? false : { stroke: "hsl(var(--border))" }}
                height={dias > 90 ? 0 : 16}
              />
              {/* Eje de MESES, debajo, como contexto del periodo. */}
              <XAxis
                xAxisId="mes"
                type="number"
                dataKey="x"
                domain={domainX}
                ticks={ticksMes}
                interval={0}
                tickFormatter={fmtMes}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11, fontWeight: 600 }}
                tickLine={false}
                axisLine={false}
                height={18}
              />
              <YAxis
                type="number"
                dataKey="y"
                domain={[-0.2, ticksY[ticksY.length - 1] + 0.2]}
                ticks={ticksY}
                tickFormatter={(v: number) => numeroCompacto(Math.pow(10, v))}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={48}
              />
              <Tooltip
                cursor={{ stroke: "hsl(var(--muted-foreground))", strokeOpacity: 0.3 }}
                content={<TooltipPanorama />}
              />
              {/* UN solo Scatter con TODOS los puntos: el color va por punto (payload.fill),
                  así ninguna red tapa a otra (no hay capas por red). */}
              <Scatter xAxisId="sem" data={puntos} shape={<Punto glow={conGlow} />} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      );

  if (desnudo) {
    return (
      <div className="space-y-3">
        <div className="flex justify-end">{selectorPeriodo}</div>
        {contenido}
      </div>
    );
  }
  return (
    <SeccionColapsable
      titulo="Panorama de piezas"
      icono={Telescope}
      descripcion="Cada punto es una pieza: altura = vistas (escala logarítmica), tamaño = engagement, color = red. Este panorama usa su propio periodo (selector de la derecha), independiente del periodo global de arriba."
      acciones={selectorPeriodo}
    >
      {contenido}
    </SeccionColapsable>
  );
}

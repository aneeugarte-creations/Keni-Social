/**
 * Correlación seguidores ganados ↔ piezas publicadas (estrategia digital).
 *
 * Cruza, por marca×red×día, cuántos seguidores se ganaron contra cuántas piezas se
 * publicaron: un SCATTER (recharts) muestra todos los puntos del periodo filtrado
 * (x = piezas del día, y = seguidores ganados, color = red) y la tabla queda como
 * drill-down del día, con `seguidores_por_post` como ratio crudo y un enlace a la pieza
 * estrella. Sobre los pares visibles se muestra el COEFICIENTE de correlación (ρ de
 * Spearman con su n; ver estadistica.ts), suprimido cuando n es insuficiente.
 * RENDERIZA la `nota` del backend (correlación ≠ causalidad) de forma visible
 * para no inducir lecturas causales. La tabla es ORDENABLE por columna numérica; el foco
 * de red lo manda el selector GLOBAL (solo se muestran las redes seleccionadas).
 *
 * Mismo stack y estados honestos (carga / vacío / error) que el resto de Métricas: si la
 * fuente no expone los datos (sin seguidores), lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, GitCompareArrows, Info } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import {
  nombreMarca,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  plural,
  porcentaje,
  redCanonica,
  redEnFoco,
  REDES_CANONICAS,
} from "@/lib/formato";
import type { ItemCorrelacion, MarcaDisponible, PostEstrella } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import type { ColumnaMeta } from "./columnasMeta";
import { colorDe } from "./coloresRed";
import { MARCA_TODAS } from "./Controles";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";
import { N_MINIMA_CORRELACION, spearman } from "./estadistica";
import { Seccion } from "./Seccion";
import { useOrdenTabla } from "./useOrdenTabla";

/** Tabla por día configurable (`vistaConfig.columnas[TABLA_CORRELACION]`). */
const TABLA_CORRELACION = "correlacion";

/** Columnas de la tabla por día (orden base + etiquetas del editor de campos). */
const COLUMNAS: ColumnaMeta[] = [
  { id: "marca", etiqueta: "Marca" },
  { id: "red", etiqueta: "Red" },
  { id: "seguidores_ganados", etiqueta: "Seguidores" },
  { id: "n_posts", etiqueta: "Piezas" },
  { id: "seguidores_por_post", etiqueta: "Seg. por pieza" },
  { id: "post_estrella", etiqueta: "Pieza estrella" },
];

const COLUMNAS_BASE = COLUMNAS.map((c) => c.id);

/** Seguidores por post: ratio crudo con un decimal ("—" si no aplica). */
function ratio(v: number | null): string {
  return v == null ? "—" : v.toLocaleString("es-MX", { maximumFractionDigits: 1 });
}

/** Seguidores ganados: un CONTEO con signo (NO un porcentaje). Ej.: "+1,234" / "−56". */
function seguidoresNeto(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "0";
  return `${n > 0 ? "+" : "−"}${numeroCompleto(Math.abs(n))}`;
}

/**
 * Resumen estadístico del scatter: ρ de Spearman sobre los pares día–red visibles
 * (x = piezas del día, y = seguidores ganados). Spearman y no Pearson porque son
 * conteos con outliers (ver estadistica.ts). Con n < N_MINIMA_CORRELACION el
 * coeficiente se SUPRIME («n insuficiente»): nunca un número espurio.
 */
function ResumenCorrelacion({ items }: { items: ItemCorrelacion[] }) {
  const n = items.length;
  const rho = React.useMemo(
    () =>
      n >= N_MINIMA_CORRELACION
        ? spearman(
            items.map((it) => it.n_posts),
            items.map((it) => it.seguidores_ganados),
          )
        : null,
    [items, n],
  );
  const pares = plural(n, "par día–red", "pares día–red");
  const texto =
    n < N_MINIMA_CORRELACION
      ? `Insuficientes observaciones (n < ${N_MINIMA_CORRELACION})`
      : rho == null
        ? `Correlación no calculable: sin variación en los datos (${pares}).`
        : `Correlación (ρ de Spearman, robusta a valores extremos): ${rho.toLocaleString(
            "es-MX",
            { minimumFractionDigits: 2, maximumFractionDigits: 2 },
          )} · n = ${pares}.`;
  return <p className="text-xs text-muted-foreground tabular-nums">{texto}</p>;
}

/** "Lun 1 jun 2026" a partir de una fecha ISO (AAAA-MM-DD), en es-MX (cabecera del pager). */
function etiquetaDia(iso: string): string {
  const [a, m, d] = iso.split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return iso;
  const texto = new Date(a, m - 1, d).toLocaleDateString("es-MX", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  // Solo la PRIMERA letra en mayúscula (sin `capitalize` CSS, que pondría en
  // mayúscula cada palabra: "Lun 1 Jun 2026" ✗).
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function Correlacion({
  marcas,
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada fila. */
  marcas: MarcaDisponible[];
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);
  const formato = useVistaConfig((s) => s.formato);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "correlacion", rangoActual ?? "", marca_ ?? "todas", red ?? "todas", formato ?? "todos"],
    queryFn: ({ signal }) => api.metricasCorrelacion({ rango: rangoActual, marca: marca_, red: red ?? undefined, formato: formato ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const items = React.useMemo(() => data?.items ?? [], [data]);

  // Items del periodo en foco de red (selector global): alimentan el scatter.
  const visibles = React.useMemo(
    () => items.filter((it) => redEnFoco(red, it.red)),
    [items, red],
  );

  return (
    <Seccion
      id="correlacion"
      titulo="Seguidores frente a piezas"
      icono={GitCompareArrows}
      descripcion="Con la pieza que mejor rindió cada día"
      tablaId={TABLA_CORRELACION}
      columnas={COLUMNAS}
      contentClassName="space-y-4"
    >
      {isPending ? (
        <Skeleton className="h-64 w-full rounded-lg" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar la correlación de seguidores.
        </p>
      ) : items.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aún no hay datos de seguidores para este periodo
        </p>
      ) : (
        <>
          {/* Scatter + nota + coeficiente en su propia tarjeta. */}
          <Card className="space-y-4 p-4 sm:p-6">
            {/* La nota del backend (correlación, no causalidad) SIEMPRE visible, con el
                nombre técnico del ratio traducido a la etiqueta de la tabla. */}
            <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{data.nota.replace("'seguidores_por_post'", "«Seg. por pieza»")}</span>
            </p>
            {/* Coeficiente (o su supresión honesta) sobre los pares visibles del filtro. */}
            {visibles.length > 0 && <ResumenCorrelacion items={visibles} />}
            {/* Scatter con TODOS los puntos del periodo filtrado; la tabla de abajo es el
                drill-down del día. */}
            {visibles.length > 0 && <GraficaCorrelacion items={visibles} marcas={marcas} />}
          </Card>
          {/* Drill-down del día en su propia tarjeta (con su editor de campos). */}
          <Card className="overflow-hidden py-2">
            <TablaCorrelacion items={items} marcas={marcas} red={red} />
          </Card>
        </>
      )}
    </Seccion>
  );
}

/** Punto del scatter ya preparado para recharts (uno por marca×red×día). */
interface PuntoDispersion {
  x: number; // n_posts — piezas publicadas ese día
  y: number; // seguidores_ganados
  fecha: string;
  marca: string;
  red: string; // canónica
  fill: string; // color de la red (coloresRed.ts)
}

/** Forma de cada punto: círculo con el color de su red y trazo de contraste. */
function PuntoCorrelacion(props: { cx?: number; cy?: number; payload?: PuntoDispersion }) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null || !payload) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill={payload.fill}
      fillOpacity={0.85}
      stroke="hsl(var(--foreground))"
      strokeOpacity={0.25}
      strokeWidth={1}
    />
  );
}

/** Tooltip (tematizado) con fecha, marca, red, seguidores y piezas del punto. */
function TooltipCorrelacion(props: {
  active?: boolean;
  payload?: Array<{ payload: PuntoDispersion }>;
  marcas: MarcaDisponible[];
}) {
  const p = props.active ? props.payload?.[0]?.payload : undefined;
  if (!p) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="mb-1 font-medium">{etiquetaDia(p.fecha)}</p>
      <ul className="space-y-0.5 text-muted-foreground">
        <li className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full ring-1 ring-foreground/25"
            style={{ backgroundColor: p.fill }}
          />
          {nombreMarca(p.marca, props.marcas)} · {nombreRed(p.red)}
        </li>
        <li>
          Seguidores: <span className="tabular-nums text-foreground">{seguidoresNeto(p.y)}</span>
        </li>
        <li>
          Piezas: <span className="tabular-nums text-foreground">{numeroCompleto(p.x)}</span>
        </li>
      </ul>
    </div>
  );
}

/**
 * Scatter seguidores ganados ↔ piezas publicadas: un punto por marca×red×día con el
 * color canónico de su red. Es la vista que sustenta la afirmación de "correlación";
 * la tabla de abajo queda como drill-down del día.
 */
function GraficaCorrelacion({
  items,
  marcas,
}: {
  items: ItemCorrelacion[];
  marcas: MarcaDisponible[];
}) {
  const { puntos, redesPresentes } = React.useMemo(() => {
    const flat: PuntoDispersion[] = items.map((it) => {
      const red = redCanonica(it.red);
      return {
        x: it.n_posts,
        y: it.seguidores_ganados,
        fecha: it.fecha,
        marca: it.marca,
        red,
        fill: colorDe(red),
      };
    });
    // Leyenda: redes presentes en orden canónico (+ las fuera de catálogo al final).
    const extras = Array.from(new Set(flat.map((p) => p.red))).filter(
      (r) => !(REDES_CANONICAS as readonly string[]).includes(r),
    );
    const presentes = [
      ...REDES_CANONICAS.filter((r) => flat.some((p) => p.red === r)),
      ...extras,
    ];
    return { puntos: flat, redesPresentes: presentes };
  }, [items]);

  return (
    /* role=img: alternativa textual del scatter (nº de puntos y redes presentes). */
    <div
      role="img"
      aria-label={`Seguidores frente a piezas publicadas: ${plural(
        puntos.length,
        "punto",
      )} por día y red (${redesPresentes.map(nombreRed).join(", ")})`}
    >
      {/* Leyenda de redes con su color (trazo de contraste para el tema claro). */}
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {redesPresentes.map((red) => (
          <span
            key={red}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
          >
            <span
              className="h-2.5 w-2.5 rounded-full ring-1 ring-foreground/25"
              style={{ backgroundColor: colorDe(red) }}
            />
            {nombreRed(red)}
          </span>
        ))}
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height={224}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 14, left: 8 }}>
            <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey="x"
              allowDecimals={false}
              tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "hsl(var(--border))" }}
              label={{
                value: "Piezas publicadas en el día",
                position: "insideBottom",
                offset: -10,
                fill: "hsl(var(--muted-foreground))",
                fontSize: 11,
              }}
            />
            <YAxis
              type="number"
              dataKey="y"
              tickFormatter={numeroCompacto}
              tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={48}
              label={{
                value: "Seguidores ganados",
                angle: -90,
                position: "insideLeft",
                fill: "hsl(var(--muted-foreground))",
                fontSize: 11,
              }}
            />
            <Tooltip
              cursor={{ stroke: "hsl(var(--muted-foreground))", strokeOpacity: 0.3 }}
              content={<TooltipCorrelacion marcas={marcas} />}
            />
            <Scatter data={puntos} shape={<PuntoCorrelacion />} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

type ClaveCorrelacion = "seguidores_ganados" | "n_posts" | "seguidores_por_post";

// Accesores de orden de la tabla (constante de módulo: identidad estable entre renders).
const ACCESORES_CORRELACION: Record<
  ClaveCorrelacion,
  (it: ItemCorrelacion) => number | null
> = {
  seguidores_ganados: (it) => it.seguidores_ganados,
  n_posts: (it) => it.n_posts,
  seguidores_por_post: (it) => it.seguidores_por_post,
};

function TablaCorrelacion({
  items,
  marcas,
  red,
}: {
  items: ItemCorrelacion[];
  marcas: MarcaDisponible[];
  /** Foco de red global (`vistaConfig.red`, CSV): solo se muestran las redes en foco. */
  red: string | null;
}) {
  // Foco de red global antes de paginar/ordenar.
  const visibles = React.useMemo(
    () => items.filter((it) => redEnFoco(red, it.red)),
    [items, red],
  );

  // Paginación POR DÍA: un día por página, del más reciente al más antiguo.
  const dias = React.useMemo(() => {
    const set = new Set<string>();
    for (const it of visibles) if (it.fecha) set.add(it.fecha);
    return Array.from(set).sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  }, [visibles]);

  const [diaIdx, setDiaIdx] = React.useState(0);
  // Clamp EN RENDER (sin useEffect de reset): si el filtro encoge la lista nunca se
  // pinta un frame imposible tipo "día 10 de 5".
  const idx = Math.min(diaIdx, Math.max(dias.length - 1, 0));

  const diaActual = dias[idx] ?? "";
  const itemsDelDia = React.useMemo(
    () => visibles.filter((it) => it.fecha === diaActual),
    [visibles, diaActual],
  );

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<ItemCorrelacion, ClaveCorrelacion>(
    itemsDelDia,
    ACCESORES_CORRELACION,
    { clave: "seguidores_ganados", direccion: "desc" },
  );

  // Orden y visibilidad de columnas del editor de campos (kebab de la sección).
  const cfg = useVistaConfig((s) => s.columnas[TABLA_CORRELACION]) ?? {
    orden: COLUMNAS_BASE,
    ocultas: [],
  };
  const columnas = columnasVisibles(COLUMNAS_BASE, cfg);

  const etiquetaDe = (id: string) => COLUMNAS.find((c) => c.id === id)?.etiqueta ?? id;

  // Solo las columnas numéricas son ordenables; sus ids coinciden con `ClaveCorrelacion`.
  const encabezado = (id: string) => {
    if (id === "marca" || id === "red" || id === "post_estrella") {
      return <TableHead key={id}>{etiquetaDe(id)}</TableHead>;
    }
    const clave = id as ClaveCorrelacion;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear="right"
      >
        {etiquetaDe(id)}
      </CabeceraOrdenable>
    );
  };

  const celda = (it: ItemCorrelacion, id: string) => {
    switch (id) {
      case "marca":
        return (
          <TableCell key={id} className="font-medium">
            {nombreMarca(it.marca, marcas)}
          </TableCell>
        );
      case "red":
        return (
          <TableCell key={id} className="text-muted-foreground">
            {nombreRed(it.red)}
          </TableCell>
        );
      case "seguidores_ganados":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {seguidoresNeto(it.seguidores_ganados)}
          </TableCell>
        );
      case "n_posts":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {it.n_posts}
          </TableCell>
        );
      case "seguidores_por_post":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {ratio(it.seguidores_por_post)}
          </TableCell>
        );
      case "post_estrella":
        return (
          <TableCell key={id} className="max-w-[18rem]">
            <PiezaEstrella post={it.post_estrella} />
          </TableCell>
        );
      default:
        return null;
    }
  };

  if (dias.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No hay datos para la red seleccionada.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* Pager por día */}
      <div className="flex items-center justify-between gap-3 px-4 pt-2">
        <div>
          <p className="text-sm font-semibold text-foreground">{etiquetaDia(diaActual)}</p>
          <p className="text-xs text-muted-foreground">
            {plural(itemsDelDia.length, "combinación", "combinaciones")} de marca y red · día{" "}
            {idx + 1} de {dias.length}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => setDiaIdx(Math.max(0, idx - 1))}
            disabled={idx <= 0}
            aria-label="Día más reciente"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => setDiaIdx(Math.min(dias.length - 1, idx + 1))}
            disabled={idx >= dias.length - 1}
            aria-label="Día más antiguo"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>{columnas.map(encabezado)}</TableRow>
          </TableHeader>
          <TableBody>
            {/* Solo combinaciones CON datos ese día: una red sin actividad (o que no publica
                el formato filtrado) no se pinta como fila "—", se omite. */}
            {filasOrdenadas.map((it) => (
              <TableRow key={`${it.marca}-${it.red}-${it.fecha}`}>
                {columnas.map((id) => celda(it, id))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function PiezaEstrella({ post }: { post: PostEstrella | null }) {
  if (!post) return <span className="text-muted-foreground">—</span>;

  const contenido = (
    <>
      <span className="block truncate" title={post.titulo}>
        {post.titulo}
      </span>
      <span className="text-xs text-muted-foreground tabular-nums">
        {porcentaje(post.engagement_pct)} de engagement
      </span>
    </>
  );

  if (!post.url) return <div>{contenido}</div>;

  return (
    <a
      href={post.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group inline-flex max-w-full items-center gap-1 hover:underline"
      title={`Engagement ${porcentaje(post.engagement_pct)}`}
    >
      <span className="min-w-0">{contenido}</span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0 opacity-60 group-hover:opacity-100" aria-hidden="true" />
    </a>
  );
}

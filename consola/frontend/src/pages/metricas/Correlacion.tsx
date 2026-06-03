/**
 * Correlación seguidores ganados ↔ piezas publicadas (estrategia digital).
 *
 * Cruza, por marca×red×día, cuántos seguidores se ganaron contra cuántas piezas se
 * publicaron, con `seguidores_por_post` como ratio crudo y un enlace a la pieza estrella
 * de ese día. RENDERIZA la `nota` del backend (correlación ≠ causalidad) de forma visible
 * para no inducir lecturas causales. La tabla es ORDENABLE por columna numérica y
 * FILTRABLE por red (cliente).
 *
 * Mismo stack y estados honestos (carga / vacío / error) que el resto de Métricas: si la
 * fuente no expone los datos (sin seguidores), lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, GitCompareArrows, Info } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { nombreMarca, nombreRed, numeroCompleto, porcentaje } from "@/lib/formato";
import type { ItemCorrelacion, MarcaDisponible, PostEstrella } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";

const RED_TODAS = "__todas__";

/** Seguidores por post: ratio crudo con un decimal ("—" si no aplica). */
function ratio(v: number | null): string {
  return v == null ? "—" : v.toLocaleString("es-MX", { maximumFractionDigits: 1 });
}

/** Seguidores ganados: un CONTEO con signo (NO un porcentaje). Ej.: "+1,234" / "−56". */
function seguidoresNeto(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "0";
  return `${n > 0 ? "+" : "−"}${numeroCompleto(Math.abs(n))}`;
}

/** "lun 1 jun 2026" a partir de una fecha ISO (AAAA-MM-DD), en es-MX (cabecera del pager). */
function etiquetaDia(iso: string): string {
  const [a, m, d] = iso.split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return iso;
  return new Date(a, m - 1, d).toLocaleDateString("es-MX", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
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
  const [redFiltro, setRedFiltro] = React.useState(RED_TODAS);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "correlacion", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasCorrelacion({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const items = React.useMemo(() => data?.items ?? [], [data]);
  const redesDisponibles = React.useMemo(
    () => Array.from(new Set(items.map((it) => it.red).filter(Boolean))).sort(),
    [items],
  );

  // El filtro de red solo tiene sentido cuando hay datos cargados.
  const filtroRed =
    !isPending && !isError && items.length > 0 ? (
      <Select value={redFiltro} onValueChange={setRedFiltro}>
        <SelectTrigger className="w-full sm:w-44" aria-label="Filtrar por red">
          <SelectValue placeholder="Red" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={RED_TODAS}>Todas las redes</SelectItem>
          {redesDisponibles.map((r) => (
            <SelectItem key={r} value={r}>
              {nombreRed(r)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    ) : undefined;

  return (
    <SeccionColapsable
      titulo="Seguidores vs publicación"
      icono={GitCompareArrows}
      descripcion="Por día y red: seguidores ganados frente a piezas publicadas, con la pieza que mejor rindió ese día."
      acciones={filtroRed}
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
          La fuente activa no expone seguidores aún para este periodo.
        </p>
      ) : (
        <>
          {/* La nota del backend (correlación, no causalidad) SIEMPRE visible. */}
          <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{data.nota}</span>
          </p>
          <TablaCorrelacion items={items} marcas={marcas} redFiltro={redFiltro} />
        </>
      )}
    </SeccionColapsable>
  );
}

type ClaveCorrelacion = "seguidores_ganados" | "n_posts" | "seguidores_por_post";

function TablaCorrelacion({
  items,
  marcas,
  redFiltro,
}: {
  items: ItemCorrelacion[];
  marcas: MarcaDisponible[];
  redFiltro: string;
}) {
  // Filtro de red (cliente) antes de paginar/ordenar.
  const visibles = React.useMemo(
    () => (redFiltro === RED_TODAS ? items : items.filter((it) => it.red === redFiltro)),
    [items, redFiltro],
  );

  // Paginación POR DÍA: un día por página, del más reciente al más antiguo.
  const dias = React.useMemo(() => {
    const set = new Set<string>();
    for (const it of visibles) if (it.fecha) set.add(it.fecha);
    return Array.from(set).sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  }, [visibles]);

  const [diaIdx, setDiaIdx] = React.useState(0);
  React.useEffect(() => {
    setDiaIdx((i) => (i >= dias.length ? 0 : i));
  }, [dias.length]);

  const diaActual = dias[Math.min(diaIdx, Math.max(dias.length - 1, 0))] ?? "";
  const itemsDelDia = React.useMemo(
    () => visibles.filter((it) => it.fecha === diaActual),
    [visibles, diaActual],
  );

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<ItemCorrelacion, ClaveCorrelacion>(
    itemsDelDia,
    {
      seguidores_ganados: (it) => it.seguidores_ganados,
      n_posts: (it) => it.n_posts,
      seguidores_por_post: (it) => it.seguidores_por_post,
    },
    { clave: "seguidores_ganados", direccion: "desc" },
  );

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
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold capitalize text-foreground">{etiquetaDia(diaActual)}</p>
          <p className="text-xs text-muted-foreground">
            {itemsDelDia.length} {itemsDelDia.length === 1 ? "marca·red" : "marca·red"} · día{" "}
            {diaIdx + 1} de {dias.length}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => setDiaIdx((i) => Math.max(0, i - 1))}
            disabled={diaIdx <= 0}
            aria-label="Día más reciente"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => setDiaIdx((i) => Math.min(dias.length - 1, i + 1))}
            disabled={diaIdx >= dias.length - 1}
            aria-label="Día más antiguo"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Marca</TableHead>
              <TableHead>Red</TableHead>
              <CabeceraOrdenable
                activa={estado.clave === "seguidores_ganados"}
                direccion={estado.direccion}
                onClick={() => alClicar("seguidores_ganados")}
                alinear="right"
              >
                Seguidores
              </CabeceraOrdenable>
              <CabeceraOrdenable
                activa={estado.clave === "n_posts"}
                direccion={estado.direccion}
                onClick={() => alClicar("n_posts")}
                alinear="right"
              >
                Posts
              </CabeceraOrdenable>
              <CabeceraOrdenable
                activa={estado.clave === "seguidores_por_post"}
                direccion={estado.direccion}
                onClick={() => alClicar("seguidores_por_post")}
                alinear="right"
              >
                Seg./post
              </CabeceraOrdenable>
              <TableHead>Pieza estrella</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filasOrdenadas.map((it) => (
              <TableRow key={`${it.marca}-${it.red}-${it.fecha}`}>
                <TableCell className="font-medium">{nombreMarca(it.marca, marcas)}</TableCell>
                <TableCell className="text-muted-foreground">{nombreRed(it.red)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {seguidoresNeto(it.seguidores_ganados)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{it.n_posts}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {ratio(it.seguidores_por_post)}
                </TableCell>
                <TableCell className="max-w-[18rem]">
                  <PiezaEstrella post={it.post_estrella} />
                </TableCell>
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
        {porcentaje(post.engagement_pct)} eng.
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

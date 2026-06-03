/**
 * Correlación seguidores ganados ↔ piezas publicadas (estrategia digital).
 *
 * Cruza, por marca×red×día, cuántos seguidores se ganaron contra cuántas piezas se
 * publicaron, con `seguidores_por_post` como ratio crudo y un enlace a la pieza estrella
 * de ese día. RENDERIZA la `nota` del backend (correlación ≠ causalidad) de forma visible
 * para no inducir lecturas causales.
 *
 * Mismo stack y estados honestos (carga / vacío / error) que el resto de Métricas: si la
 * fuente no expone los datos (sin seguidores), lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, GitCompareArrows, Info } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { nombreMarca, nombreRed, porcentaje, variacion } from "@/lib/formato";
import type { ItemCorrelacion, MarcaDisponible, PostEstrella } from "@/types";

import { MARCA_TODAS } from "./Controles";

/** "12 may" a partir de una fecha ISO (AAAA-MM-DD), en es-MX. */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(d);
}

/** Seguidores por post: ratio crudo con un decimal ("—" si no aplica). */
function ratio(v: number | null): string {
  return v == null ? "—" : v.toLocaleString("es-MX", { maximumFractionDigits: 1 });
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

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "correlacion", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasCorrelacion({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <GitCompareArrows className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Seguidores vs publicación</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          Por día y red: seguidores ganados frente a piezas publicadas, con la pieza que
          mejor rindió ese día.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending ? (
          <Skeleton className="h-64 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudo cargar la correlación de seguidores.
          </p>
        ) : data.items.length === 0 ? (
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
            <TablaCorrelacion items={data.items} marcas={marcas} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function TablaCorrelacion({
  items,
  marcas,
}: {
  items: ItemCorrelacion[];
  marcas: MarcaDisponible[];
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Fecha</TableHead>
            <TableHead>Marca</TableHead>
            <TableHead>Red</TableHead>
            <TableHead className="text-right">Seguidores</TableHead>
            <TableHead className="text-right">Posts</TableHead>
            <TableHead className="text-right">Seg./post</TableHead>
            <TableHead>Pieza estrella</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((it) => (
            <TableRow key={`${it.marca}-${it.red}-${it.fecha}`}>
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {fechaCorta(it.fecha)}
              </TableCell>
              <TableCell className="font-medium">{nombreMarca(it.marca, marcas)}</TableCell>
              <TableCell className="text-muted-foreground">{nombreRed(it.red)}</TableCell>
              <TableCell className="text-right tabular-nums">
                {variacion(it.seguidores_ganados)}
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

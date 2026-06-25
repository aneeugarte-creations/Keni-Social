/**
 * Demografía de la audiencia de una marca×red (estrategia digital).
 *
 * Pinta quién es la audiencia de la cuenta (género, edad, país, ciudad) y con qué mezcla de
 * formatos se publica (`postsTypes`). La fuente la da por CUENTA, así que es una vista marca×
 * red con selectores propios (no el foco global): Instagram trae el reparto demográfico
 * completo; Facebook, el país de los seguidores. Las distribuciones demográficas son
 * porcentajes; la mezcla de formatos son conteos. Si la red elegida no expone demografía
 * (`distribuciones` vacío) se dice con honestidad en vez de inventar barras.
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "@tremor/react";
import { PieChart } from "lucide-react";
import * as React from "react";

import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { nombreFormato, nombreMarca, nombreRed, numeroCompleto, porcentaje } from "@/lib/formato";
import type { MarcaDisponible, PuntoDistribucion } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";

/** Redes que exponen demografía de cuenta (IG: reparto completo; FB: país de seguidores). */
const REDES_DEMOGRAFIA = ["instagram", "facebook"] as const;

/** Género legible a partir del id de la fuente (Metricool: `M`/`F`/`U`). Desconocido → tal cual. */
function generoLegible(clave: string): string {
  const m: Record<string, string> = { M: "Hombres", F: "Mujeres", U: "Sin especificar" };
  return m[clave] ?? clave;
}

/** Configuración de presentación de cada distribución: etiqueta, unidad y formato de la clave. */
interface MetaDistribucion {
  etiqueta: string;
  /** "pct" = porcentaje (demografía); "conteo" = nº de piezas (mezcla de formatos). */
  unidad: "pct" | "conteo";
  /** Color Tremor de las barras. */
  color: string;
  /** Transforma la clave cruda a su forma legible (género, formato…). */
  clave?: (c: string) => string;
}

// Orden de presentación + metadatos. Las distribuciones fuera de este catálogo se pintan
// igualmente al final, con la clave cruda y como porcentaje (degradación honesta).
const META: Record<string, MetaDistribucion> = {
  gender: { etiqueta: "Género", unidad: "pct", color: "violet", clave: generoLegible },
  age: { etiqueta: "Edad", unidad: "pct", color: "indigo" },
  country: { etiqueta: "País", unidad: "pct", color: "sky" },
  city: { etiqueta: "Ciudad", unidad: "pct", color: "cyan" },
  page_follows_country: { etiqueta: "País (seguidores)", unidad: "pct", color: "sky" },
  postsTypes: { etiqueta: "Mezcla de formatos", unidad: "conteo", color: "amber", clave: nombreFormato },
};

const ORDEN_META = Object.keys(META);

/** Una distribución como tarjeta con su gráfica de barras (las más grandes arriba, top 12). */
function DistribucionCard({ metrica, puntos }: { metrica: string; puntos: PuntoDistribucion[] }) {
  const meta: MetaDistribucion = META[metrica] ?? { etiqueta: metrica, unidad: "pct", color: "violet" };
  const legible = meta.clave ?? ((c: string) => c);
  const fmt = meta.unidad === "pct" ? porcentaje : numeroCompleto;
  // Mayores primero; en listas largas (país/ciudad) limitamos a 12 para que la gráfica
  // siga siendo legible (la cola se omite, no se falsea).
  const datos = [...puntos]
    .sort((a, b) => b.valor - a.valor)
    .slice(0, 12)
    .map((p) => ({ clave: legible(p.clave), Valor: p.valor }));
  if (datos.length === 0) return null;
  return (
    <Card className="space-y-3 p-4 sm:p-5">
      <p className="text-sm font-medium">{meta.etiqueta}</p>
      <div role="img" aria-label={`Distribución por ${meta.etiqueta.toLowerCase()}`}>
        <BarChart
          data={datos}
          index="clave"
          categories={["Valor"]}
          colors={[meta.color]}
          layout="vertical"
          valueFormatter={fmt}
          showLegend={false}
          showAnimation
          className="h-64"
        />
      </div>
    </Card>
  );
}

export function Demografia({
  marcas,
  marcaActual = MARCA_TODAS,
}: {
  marcas: MarcaDisponible[];
  marcaActual?: string;
}) {
  // Selectores PROPIOS (la demografía es por cuenta, no agregable): marca concreta + una red.
  // La marca arranca en la del foco global si es concreta; si no (o "Todas"), la primera.
  const marcaInicial = marcas.some((m) => m.id === marcaActual) ? marcaActual : marcas[0]?.id ?? "";
  const [marcaSel, setMarcaSel] = React.useState(marcaInicial);
  const [redSel, setRedSel] = React.useState<string>(REDES_DEMOGRAFIA[0]);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "demografia", marcaSel, redSel],
    queryFn: ({ signal }) => api.metricasDemografia({ marca: marcaSel, red: redSel }, signal),
    enabled: Boolean(marcaSel && redSel),
    staleTime: 5 * 60_000,
  });

  // Distribuciones ordenadas: primero las del catálogo (en su orden), luego las demás.
  const distribuciones = data?.distribuciones ?? {};
  const claves = React.useMemo(() => {
    const presentes = Object.keys(distribuciones).filter((k) => (distribuciones[k] ?? []).length > 0);
    const enCatalogo = ORDEN_META.filter((k) => presentes.includes(k));
    const resto = presentes.filter((k) => !ORDEN_META.includes(k));
    return [...enCatalogo, ...resto];
  }, [distribuciones]);

  const selectores = (
    <div className="flex items-center gap-2">
      <Select value={marcaSel} onValueChange={setMarcaSel}>
        <SelectTrigger className="h-8 w-[160px] text-xs" aria-label="Marca">
          <SelectValue placeholder="Marca">{nombreMarca(marcaSel, marcas)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {marcas.map((m) => (
            <SelectItem key={m.id} value={m.id} className="text-xs">
              {m.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={redSel} onValueChange={setRedSel}>
        <SelectTrigger className="h-8 w-[130px] text-xs" aria-label="Red">
          <SelectValue placeholder="Red">{nombreRed(redSel)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {REDES_DEMOGRAFIA.map((r) => (
            <SelectItem key={r} value={r} className="text-xs">
              {nombreRed(r)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <Seccion
      id="demografia"
      titulo="Demografía de la audiencia"
      icono={PieChart}
      descripcion="Quién sigue la cuenta (género, edad, lugar) y con qué mezcla de formatos se publica. La fuente la da por cuenta: elige marca y red."
      acciones={selectores}
    >
      {isPending ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
      ) : isError ? (
        <Card className="p-6">
          <p className="py-6 text-center text-sm text-muted-foreground">
            No se pudo cargar la demografía.
          </p>
        </Card>
      ) : claves.length === 0 ? (
        <Card className="p-6">
          <p className="py-6 text-center text-sm text-muted-foreground">
            {nombreRed(redSel)} no expone demografía de audiencia para esta marca.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {claves.map((k) => (
            <DistribucionCard key={k} metrica={k} puntos={distribuciones[k]} />
          ))}
        </div>
      )}
    </Seccion>
  );
}

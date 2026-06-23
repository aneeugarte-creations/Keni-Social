/**
 * Crosstab de rendimiento marca×red×formato (estrategia digital).
 *
 * Una tabla-mapa de calor: cada fila es una combinación marca×red×formato del periodo
 * con su número de piezas, engagement promedio y `rendimiento_relativo_medio` (promedio
 * por pieza de: vistas de la pieza ÷ mediana de vistas de su grupo marca×red; media del
 * grupo si la mediana es 0). El rendimiento relativo se colorea para leer de un vistazo
 * qué formatos alcanzan por encima (≥1.05×, verde) o por debajo (≤0.95×, rojo) de su grupo.
 *
 * Mismo stack y estados honestos (carga / vacío / error) que el resto de Métricas: si la
 * fuente no expone celdas, lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { Grid3x3 } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
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
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import {
  nombreFormato,
  nombreMarca,
  nombreRed,
  numeroCompleto,
  porcentaje,
  redCanonica,
  REDES_CANONICAS,
  rendimientoRel,
} from "@/lib/formato";
import type { CeldaCrosstab, MarcaDisponible } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import type { ColumnaMeta } from "./columnasMeta";
import { MARCA_TODAS } from "./Controles";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";
import { PieMostrarMas } from "./PieMostrarMas";
import { Seccion } from "./Seccion";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";

/** Id de tabla del editor de columnas (clave en `vistaConfig.columnas`). */
const TABLA_CROSSTAB = "crosstab";

/**
 * Columnas FIJAS del cruce (dimensiones marca/red/formato + métricas). El mapa de calor
 * es solo el color de la celda "Rendimiento", no columnas derivadas de datos: el conjunto
 * es estable, así que admite editor de columnas.
 */
const COLUMNAS: ColumnaMeta[] = [
  { id: "marca", etiqueta: "Marca" },
  { id: "red", etiqueta: "Red" },
  { id: "formato", etiqueta: "Formato" },
  { id: "n_piezas", etiqueta: "Piezas" },
  { id: "visualizaciones", etiqueta: "Vistas" },
  { id: "engagement_pct", etiqueta: "Engagement" },
  { id: "rendimiento", etiqueta: "Rendimiento" },
];

const IDS_BASE = COLUMNAS.map((c) => c.id);

/** Etiqueta legible de una columna por id. */
function etiquetaCol(id: string): string {
  return COLUMNAS.find((c) => c.id === id)?.etiqueta ?? id;
}

/**
 * Color del rendimiento relativo (>1 rinde por encima de la mediana de su grupo, <1
 * por debajo). `null` = no hay base para compararlo (grupo de una sola pieza, etc.).
 */
function claseRendimiento(v: number | null): string {
  if (v == null) return "text-muted-foreground";
  if (v >= 1.05) return "text-emerald-700 dark:text-emerald-300";
  if (v <= 0.95) return "text-red-700 dark:text-red-300";
  return "text-foreground";
}

export function Crosstab({
  marcas,
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada celda. */
  marcas: MarcaDisponible[];
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "crosstab", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasCrosstab({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  return (
    <Seccion
      id="crosstab"
      titulo="Rendimiento por formato"
      icono={Grid3x3}
      tablaId={TABLA_CROSSTAB}
      columnas={COLUMNAS}
      descripcion={
        <>
          Rendimiento = promedio por pieza de (vistas ÷ mediana de vistas de su grupo marca×red); si la mediana es 0 se usa la media.{" "}
          <span className="text-emerald-700 dark:text-emerald-300">Verde (≥1.05×)</span>,{" "}
          <span className="text-red-700 dark:text-red-300">rojo (≤0.95×)</span>; neutro entre medias.
        </>
      }
    >
      {isPending ? (
        <Skeleton className="h-64 w-full rounded-lg" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar el rendimiento por formato.
        </p>
      ) : data.celdas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aún no hay cruce por formato para este periodo (la fuente de métricas no lo
          entrega).
        </p>
      ) : (
        <TablaCrosstab celdas={data.celdas} marcas={marcas} />
      )}
    </Seccion>
  );
}

type ClaveCrosstab = "n_piezas" | "visualizaciones" | "engagement_pct" | "rendimiento";

/** Accesores de orden por columna (constante de módulo: referencia estable entre renders). */
const ACCESORES: Record<ClaveCrosstab, (c: CeldaCrosstab) => number | null> = {
  n_piezas: (c) => c.n_piezas,
  visualizaciones: (c) => c.visualizaciones,
  engagement_pct: (c) => c.engagement_pct,
  rendimiento: (c) => c.rendimiento_relativo_medio,
};

function TablaCrosstab({
  celdas,
  marcas,
}: {
  celdas: CeldaCrosstab[];
  marcas: MarcaDisponible[];
}) {
  // Orden por defecto: rendimiento relativo descendente (lo que más rinde, arriba).
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CeldaCrosstab, ClaveCrosstab>(
    celdas,
    ACCESORES,
    { clave: "rendimiento", direccion: "desc" },
  );

  // "Todas las tablas, todas las redes": la dimensión RED del cruce SIEMPRE incluye las 5
  // redes canónicas (facebook, instagram, tiktok, youtube, x) por cada marca presente.
  // Por cada marca×red sin ninguna celda en el periodo añadimos una fila placeholder con
  // "—" (no inventamos ceros ni la omitimos —incluida X, no contratada en el piloto—).
  const marcasPresentes: string[] = [];
  const combosConDatos = new Set<string>();
  for (const c of celdas) {
    if (!marcasPresentes.includes(c.marca)) marcasPresentes.push(c.marca);
    combosConDatos.add(`${c.marca}::${redCanonica(c.red)}`);
  }
  const filasVacias: Array<{ marca: string; red: string }> = [];
  for (const marca of marcasPresentes) {
    for (const red of REDES_CANONICAS) {
      if (!combosConDatos.has(`${marca}::${red}`)) filasVacias.push({ marca, red });
    }
  }

  // Recorte a 5 filas CON DATOS (post-orden); los placeholders "—" solo al desplegar.
  const { visibles, expandido, alternar, hayMas } = useFilasPlegables(filasOrdenadas, 5);

  // Qué columnas se ven y en qué orden lo decide el editor de columnas (id "crosstab").
  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_CROSSTAB]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);

  const encabezado = (id: string) => {
    if (id === "marca" || id === "red" || id === "formato") {
      return <TableHead key={id}>{etiquetaCol(id)}</TableHead>;
    }
    const clave = id as ClaveCrosstab;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear="right"
      >
        {etiquetaCol(id)}
      </CabeceraOrdenable>
    );
  };

  const celda = (c: CeldaCrosstab, id: string) => {
    switch (id) {
      case "marca":
        return (
          <TableCell key={id} className="font-medium">
            {nombreMarca(c.marca, marcas)}
          </TableCell>
        );
      case "red":
        return (
          <TableCell key={id} className="text-muted-foreground">
            {nombreRed(c.red)}
          </TableCell>
        );
      case "formato":
        return (
          <TableCell key={id} className="text-muted-foreground">
            {nombreFormato(c.formato)}
          </TableCell>
        );
      case "n_piezas":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {c.n_piezas}
          </TableCell>
        );
      case "visualizaciones":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {numeroCompleto(c.visualizaciones)}
          </TableCell>
        );
      case "engagement_pct":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {porcentaje(c.engagement_pct)}
          </TableCell>
        );
      default:
        return (
          <TableCell
            key={id}
            className={cn(
              "text-right font-medium tabular-nums",
              claseRendimiento(c.rendimiento_relativo_medio),
            )}
            title="Promedio por pieza de: vistas ÷ mediana de vistas de su grupo marca×red (media del grupo si la mediana es 0)"
          >
            {rendimientoRel(c.rendimiento_relativo_medio)}
          </TableCell>
        );
    }
  };

  const celdaVacia = (marca: string, red: string, id: string) => {
    if (id === "marca") {
      return (
        <TableCell key={id} className="font-medium">
          {nombreMarca(marca, marcas)}
        </TableCell>
      );
    }
    if (id === "red") {
      return <TableCell key={id}>{nombreRed(red)}</TableCell>;
    }
    if (id === "formato") {
      return <TableCell key={id}>—</TableCell>;
    }
    return (
      <TableCell key={id} className="text-right tabular-nums">
        —
      </TableCell>
    );
  };

  return (
    <Card className="overflow-hidden py-2">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>{columnas.map(encabezado)}</TableRow>
          </TableHeader>
          <TableBody>
            {visibles.map((c) => (
              <TableRow key={`${c.marca}-${c.red}-${c.formato ?? "sin"}`}>
                {columnas.map((id) => celda(c, id))}
              </TableRow>
            ))}
            {/* Marca×red canónica sin datos en el periodo: fila presente con "—" (no se omite).
                Solo se muestran al desplegar (o si la tabla no se recorta). */}
            {(expandido || !hayMas) &&
              filasVacias.map(({ marca, red }) => (
                <TableRow key={`vacia-${marca}-${red}`} className="text-muted-foreground">
                  {columnas.map((id) => celdaVacia(marca, red, id))}
                </TableRow>
              ))}
          </TableBody>
          {hayMas && (
            <PieMostrarMas
              expandido={expandido}
              onAlternar={alternar}
              colSpan={columnas.length}
            />
          )}
        </Table>
      </div>
    </Card>
  );
}

/**
 * Desglose de interacciones por marca×red (estrategia digital).
 *
 * Descompone el engagement bruto del periodo en sus partes (likes, comentarios,
 * compartidos, guardados, video_views) por cada celda marca×red. Pinta un BarChart
 * apilado (una barra por marca×red, segmentada por tipo de interacción) y una tabla
 * con el detalle y los `totales` del periodo. Separación clara por marca y por red.
 *
 * Mismo stack (Tremor) y estados honestos (carga / vacío / error) que el resto de
 * Métricas: si la fuente no expone celdas, lo dice en vez de inventar. La sección es
 * colapsable y filtra client-side por red y por marca (selectores en la cabecera).
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "@tremor/react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
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
import {
  nombreMarca,
  nombreRed,
  numeroCompacto,
  REDES_CANONICAS,
  type RedCanonica,
} from "@/lib/formato";
import type { CeldaDesglose, MarcaDisponible } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { PieMostrarMas } from "./PieMostrarMas";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";

// Componentes del engagement bruto: orden y color estables en la barra apilada.
const COMPONENTES: Array<{ clave: keyof CeldaDesglose; etiqueta: string; color: string }> = [
  { clave: "likes", etiqueta: "Likes", color: "rose" },
  { clave: "comentarios", etiqueta: "Comentarios", color: "blue" },
  { clave: "compartidos", etiqueta: "Compartidos", color: "emerald" },
  { clave: "guardados", etiqueta: "Guardados", color: "amber" },
  { clave: "video_views", etiqueta: "Reproducciones", color: "violet" },
];

const ETIQUETAS = COMPONENTES.map((c) => c.etiqueta);
const COLORES = COMPONENTES.map((c) => c.color);

/** Centinela "sin filtro" para los selectores de red/marca. */
const TODAS = "__todas__";

export function DesgloseInteracciones({
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

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "desglose", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasDesglose({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Filtro client-side por red, derivado de las celdas del periodo. La marca la acota
  // el switch global de la barra superior (la consulta ya viene scopeada).
  const [redFiltro, setRedFiltro] = React.useState(TODAS);

  const celdas = React.useMemo(() => data?.celdas ?? [], [data]);
  // "Todas las tablas, todas las redes": el selector ofrece SIEMPRE las 5 redes canónicas
  // (no solo las que traen datos), así el operador puede enfocar cualquiera —incluida X, que
  // en el piloto no está contratada en Metricool— y, si no hay datos, la tabla lo dice con "—".
  // El filtro por red NO se aplica recortando celdas aquí: `construirRejilla` deriva las marcas
  // del conjunto completo y restringe las redes a `redFiltro`, de modo que enfocar una red sin
  // datos sigue mostrando esa red como fila "—" para cada marca (no se vacía la tabla).
  const redesDisp = REDES_CANONICAS;

  const acciones = (
    <Select value={redFiltro} onValueChange={setRedFiltro}>
      <SelectTrigger className="w-full sm:w-40" aria-label="Filtrar por red">
        <SelectValue placeholder="Red" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={TODAS}>Todas las redes</SelectItem>
        {redesDisp.map((r) => (
          <SelectItem key={r} value={r}>
            {nombreRed(r)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-tight">Desglose de interacciones</h2>
        <div className="flex flex-wrap items-center gap-2">{acciones}</div>
      </div>
      <p className="text-sm text-muted-foreground">
        De qué se compone el engagement de cada marca y red: likes, comentarios, compartidos,
        guardados y reproducciones del periodo.
      </p>
      {isPending ? (
        <Skeleton className="h-72 w-full rounded-lg" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar el desglose de interacciones.
        </p>
      ) : data.celdas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          La fuente activa no expone el desglose de interacciones para este periodo.
        </p>
      ) : (
        <>
          <GraficaApilada celdas={celdas} marcas={marcas} redFiltro={redFiltro} />
          <TablaDesglose
            celdas={celdas}
            totales={data.totales}
            marcas={marcas}
            redFiltro={redFiltro}
          />
        </>
      )}
    </section>
  );
}

/** Una entrada de la rejilla marca×red: la celda real o `undefined` si esa red no trae datos. */
type EntradaRejilla = { marca: string; red: RedCanonica; celda: CeldaDesglose | undefined };

/**
 * Construye la rejilla marca×red completa: por cada marca presente (en su orden de aparición)
 * y cada red canónica objetivo (todas, o la única bajo filtro) devuelve la celda real o
 * `undefined`. Así "todas las tablas, todas las redes": una red sin datos no se omite, aparece
 * como entrada vacía que el render pinta con "—" (tabla) o sin barra (gráfica).
 */
function construirRejilla(celdas: CeldaDesglose[], redFiltro: string): EntradaRejilla[] {
  const redesObjetivo =
    redFiltro === TODAS
      ? REDES_CANONICAS
      : REDES_CANONICAS.filter((r) => r === redFiltro);
  // Marcas en orden de primera aparición en las celdas (estable, sin reordenar).
  const marcasOrden: string[] = [];
  const porClave = new Map<string, CeldaDesglose>();
  for (const c of celdas) {
    if (!marcasOrden.includes(c.marca)) marcasOrden.push(c.marca);
    porClave.set(`${c.marca}::${c.red.toLowerCase()}`, c);
  }
  const rejilla: EntradaRejilla[] = [];
  for (const marca of marcasOrden) {
    for (const red of redesObjetivo) {
      rejilla.push({ marca, red, celda: porClave.get(`${marca}::${red}`) });
    }
  }
  return rejilla;
}

function GraficaApilada({
  celdas,
  marcas,
  redFiltro,
}: {
  celdas: CeldaDesglose[];
  marcas: MarcaDisponible[];
  redFiltro: string;
}) {
  // Una barra por marca×red canónica: las redes sin datos quedan en 0 (sin barra) pero
  // conservan su entrada/etiqueta en el eje, para no "desaparecer" de la gráfica.
  const datos = construirRejilla(celdas, redFiltro).map(({ marca, red, celda }) => ({
    grupo: `${nombreMarca(marca, marcas)} · ${nombreRed(red)}`,
    Likes: celda?.likes ?? 0,
    Comentarios: celda?.comentarios ?? 0,
    Compartidos: celda?.compartidos ?? 0,
    Guardados: celda?.guardados ?? 0,
    Reproducciones: celda?.video_views ?? 0,
  }));
  return (
    <BarChart
      data={datos}
      index="grupo"
      categories={ETIQUETAS}
      colors={COLORES}
      valueFormatter={numeroCompacto}
      stack
      showAnimation
      className="h-72"
    />
  );
}

type ClaveDesglose = keyof CeldaDesglose;

function TablaDesglose({
  celdas,
  totales,
  marcas,
  redFiltro,
}: {
  celdas: CeldaDesglose[];
  totales: Record<string, number>;
  marcas: MarcaDisponible[];
  redFiltro: string;
}) {
  // Rejilla marca×red COMPLETA: las redes sin datos van como entradas con `celda` undefined,
  // que el orden empuja al final (`null` no es un 0 real) y el render pinta con "—".
  const rejilla = React.useMemo(
    () => construirRejilla(celdas, redFiltro),
    [celdas, redFiltro],
  );

  // Cada componente del engagement + nº de piezas es ordenable. Para entradas sin celda
  // devolvemos `null`: `useOrdenTabla` las manda al final en cualquier dirección.
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<EntradaRejilla, ClaveDesglose>(
    rejilla,
    {
      likes: (e) => e.celda?.likes ?? null,
      comentarios: (e) => e.celda?.comentarios ?? null,
      compartidos: (e) => e.celda?.compartidos ?? null,
      guardados: (e) => e.celda?.guardados ?? null,
      video_views: (e) => e.celda?.video_views ?? null,
      n_piezas: (e) => e.celda?.n_piezas ?? null,
      // El resto de claves de CeldaDesglose no se usan como orden, pero el tipo las exige.
      marca: (e) => e.marca,
      red: (e) => e.red,
      interacciones: (e) => e.celda?.interacciones ?? null,
      visualizaciones: (e) => e.celda?.visualizaciones ?? null,
      engagement_pct: (e) => e.celda?.engagement_pct ?? null,
    } as Record<ClaveDesglose, (e: EntradaRejilla) => number | string | null>,
  );

  // Recorte a 5 filas (post-orden): las visibles son el top 5 según la columna activa.
  const { visibles, expandido, alternar, hayMas } = useFilasPlegables(filasOrdenadas, 5);

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Red</TableHead>
            {COMPONENTES.map((c) => (
              <CabeceraOrdenable
                key={c.clave as string}
                activa={estado.clave === c.clave}
                direccion={estado.direccion}
                onClick={() => alClicar(c.clave)}
                alinear="right"
              >
                {c.etiqueta}
              </CabeceraOrdenable>
            ))}
            <CabeceraOrdenable
              activa={estado.clave === "n_piezas"}
              direccion={estado.direccion}
              onClick={() => alClicar("n_piezas")}
              alinear="right"
            >
              Piezas
            </CabeceraOrdenable>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibles.map(({ marca, red, celda }) => (
            <TableRow
              key={`${marca}-${red}`}
              className={celda ? undefined : "text-muted-foreground"}
            >
              <TableCell className="font-medium">{nombreMarca(marca, marcas)}</TableCell>
              <TableCell className="text-muted-foreground">{nombreRed(red)}</TableCell>
              {COMPONENTES.map((comp) => (
                <TableCell key={comp.clave} className="text-right tabular-nums">
                  {celda ? numeroCompacto(celda[comp.clave] as number) : "—"}
                </TableCell>
              ))}
              <TableCell className="text-right tabular-nums">{celda ? celda.n_piezas : "—"}</TableCell>
            </TableRow>
          ))}
          <TableRow className="border-t-2 font-medium">
            <TableCell>Total</TableCell>
            <TableCell />
            {COMPONENTES.map((comp) => (
              <TableCell key={comp.clave} className="text-right tabular-nums">
                {numeroCompacto(totales[comp.clave] ?? 0)}
              </TableCell>
            ))}
            <TableCell className="text-right tabular-nums">
              {totales.n_piezas ?? 0}
            </TableCell>
          </TableRow>
        </TableBody>
        {hayMas && (
          <PieMostrarMas
            expandido={expandido}
            onAlternar={alternar}
            colSpan={COMPONENTES.length + 3}
          />
        )}
      </Table>
    </div>
  );
}

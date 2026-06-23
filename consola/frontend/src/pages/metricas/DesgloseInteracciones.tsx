/**
 * Desglose de interacciones por marca×red (estrategia digital).
 *
 * Descompone las interacciones del periodo en sus partes (me gusta, comentarios,
 * compartidos, guardados, reproducciones) por cada celda marca×red. Pinta un BarChart
 * apilado (una barra por marca×red, segmentada SOLO por interacciones: las
 * reproducciones son consumo, no interacción, y aplastarían al resto) y una tabla con
 * las 5 columnas, el detalle y los `totales` del periodo.
 *
 * La gráfica ofrece dos modos: "Proporción" (apilado al 100 %, cada barra normalizada a
 * su composición) y "Volumen" (apilado absoluto). El modo proporción es el predeterminado
 * porque los "me gusta" superan en órdenes de magnitud a comentarios/compartidos/guardados
 * y, en volumen absoluto, aplastan al resto hasta hacerlos invisibles; normalizar a 100 %
 * vuelve legible cada segmento y compara composición entre marcas/redes aunque difieran en
 * volumen.
 *
 * Mismo stack (Tremor) y estados honestos (carga / vacío / error) que el resto de
 * Métricas: si la fuente no expone celdas, lo dice en vez de inventar. La sección es
 * colapsable; el foco de red lo manda el selector GLOBAL de la cabecera (solo se muestran
 * las redes seleccionadas).
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "@tremor/react";
import { Activity } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup } from "@/components/ui/toggle-group";
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
  porcentaje,
  redesObjetivo,
  type RedCanonica,
} from "@/lib/formato";
import type { CeldaDesglose, MarcaDisponible } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { useVistaConfig } from "./vistaConfig";
import { PieMostrarMas } from "./PieMostrarMas";
import { SeccionColapsable } from "./SeccionColapsable";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";

// Componentes que la GRÁFICA apila: solo interacciones (orden y color estables).
// Las reproducciones (video_views) son consumo, no interacción, y su volumen
// aplastaría al resto de segmentos; viven solo en la tabla.
// OJO: el color codifica el COMPONENTE de interacción (no la red, que aquí es parte del
// eje); la paleta por red (coloresRed.ts) no aplica a esta gráfica.
const COMPONENTES_GRAFICA: Array<{ clave: keyof CeldaDesglose; etiqueta: string; color: string }> =
  [
    { clave: "likes", etiqueta: "Me gusta", color: "rose" },
    { clave: "comentarios", etiqueta: "Comentarios", color: "blue" },
    { clave: "compartidos", etiqueta: "Compartidos", color: "emerald" },
    { clave: "guardados", etiqueta: "Guardados", color: "amber" },
  ];

// La TABLA sí conserva las 5 columnas (reproducciones incluidas).
const COMPONENTES_TABLA: Array<{ clave: keyof CeldaDesglose; etiqueta: string }> = [
  ...COMPONENTES_GRAFICA,
  { clave: "video_views", etiqueta: "Reproducciones" },
];

const ETIQUETAS = COMPONENTES_GRAFICA.map((c) => c.etiqueta);
const COLORES = COMPONENTES_GRAFICA.map((c) => c.color);

/** Modo de la gráfica: proporción (apilado al 100 %) o volumen (apilado absoluto). */
type ModoGrafica = "proporcion" | "volumen";

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
  const red = useVistaConfig((s) => s.red);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "desglose", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasDesglose({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Modo de la gráfica. Por defecto "proporcion": los "me gusta" eclipsan al resto en
  // volumen absoluto, así que normalizar a 100 % es lo que deja legibles los segmentos.
  const [modo, setModo] = React.useState<ModoGrafica>("proporcion");

  const celdas = React.useMemo(() => data?.celdas ?? [], [data]);
  // El foco de red lo manda el selector GLOBAL (`vistaConfig.red`): la rejilla solo cubre
  // las redes seleccionadas; una en foco sin datos sigue como fila "—" para cada marca.
  const redes = redesObjetivo(red);

  const acciones = (
    <ToggleGroup<ModoGrafica>
      ariaLabel="Modo de la gráfica"
      valor={modo}
      onCambio={setModo}
      opciones={[
        { valor: "proporcion", etiqueta: "Proporción" },
        { valor: "volumen", etiqueta: "Volumen" },
      ]}
    />
  );

  return (
    <SeccionColapsable
      id="desglose"
      titulo="Desglose de interacciones"
      icono={Activity}
      acciones={acciones}
    >
      {isPending ? (
        <Skeleton className="h-72 w-full rounded-lg" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar el desglose de interacciones.
        </p>
      ) : data.celdas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aún no hay desglose de interacciones para este periodo.
        </p>
      ) : (
        <div className="space-y-4">
          {/* Alternativa textual del chart: los totales del periodo por componente. */}
          <div
            role="img"
            aria-label={`Desglose de interacciones por marca y red: Me gusta ${numeroCompacto(
              data.totales.likes ?? 0,
            )}, Comentarios ${numeroCompacto(
              data.totales.comentarios ?? 0,
            )}, Compartidos ${numeroCompacto(
              data.totales.compartidos ?? 0,
            )}, Guardados ${numeroCompacto(data.totales.guardados ?? 0)}`}
          >
            <GraficaApilada celdas={celdas} marcas={marcas} redes={redes} modo={modo} />
          </div>
          <TablaDesglose
            celdas={celdas}
            totales={data.totales}
            marcas={marcas}
            redes={redes}
          />
        </div>
      )}
    </SeccionColapsable>
  );
}

/** Una entrada de la rejilla marca×red: la celda real o `undefined` si esa red no trae datos. */
type EntradaRejilla = { marca: string; red: RedCanonica; celda: CeldaDesglose | undefined };

/**
 * Construye la rejilla marca×red: por cada marca presente (en su orden de aparición) y cada
 * red EN FOCO (`redes`) devuelve la celda real o `undefined`. Una red en foco sin datos no se
 * omite: aparece como entrada vacía que el render pinta con "—" (tabla) o sin barra (gráfica).
 * Las redes fuera del foco no entran en la rejilla.
 */
function construirRejilla(
  celdas: CeldaDesglose[],
  redes: readonly string[],
): EntradaRejilla[] {
  // Marcas en orden de primera aparición en las celdas (estable, sin reordenar).
  const marcasOrden: string[] = [];
  const porClave = new Map<string, CeldaDesglose>();
  for (const c of celdas) {
    if (!marcasOrden.includes(c.marca)) marcasOrden.push(c.marca);
    porClave.set(`${c.marca}::${c.red.toLowerCase()}`, c);
  }
  const rejilla: EntradaRejilla[] = [];
  for (const marca of marcasOrden) {
    for (const red of redes) {
      rejilla.push({ marca, red: red as RedCanonica, celda: porClave.get(`${marca}::${red}`) });
    }
  }
  return rejilla;
}

function GraficaApilada({
  celdas,
  marcas,
  redes,
  modo,
}: {
  celdas: CeldaDesglose[];
  marcas: MarcaDisponible[];
  redes: readonly string[];
  modo: ModoGrafica;
}) {
  const proporcion = modo === "proporcion";
  // Una barra por marca×red canónica: las redes sin datos quedan en 0 (sin barra) pero
  // conservan su entrada/etiqueta en el eje, para no "desaparecer" de la gráfica.
  // Solo interacciones: las reproducciones quedan fuera de la pila (ver COMPONENTES_GRAFICA).
  // En modo proporción cada barra se normaliza a su composición (segmentos que suman 100 %);
  // una barra sin interacciones se queda toda en 0 (sin pila).
  const datos = construirRejilla(celdas, redes).map(({ marca, red, celda }) => {
    const valores = {
      "Me gusta": celda?.likes ?? 0,
      Comentarios: celda?.comentarios ?? 0,
      Compartidos: celda?.compartidos ?? 0,
      Guardados: celda?.guardados ?? 0,
    };
    const grupo = `${nombreMarca(marca, marcas)} · ${nombreRed(red)}`;
    if (!proporcion) return { grupo, ...valores };
    const total = ETIQUETAS.reduce((s, e) => s + valores[e as keyof typeof valores], 0);
    if (total === 0) return { grupo, ...valores };
    return {
      grupo,
      "Me gusta": (valores["Me gusta"] / total) * 100,
      Comentarios: (valores.Comentarios / total) * 100,
      Compartidos: (valores.Compartidos / total) * 100,
      Guardados: (valores.Guardados / total) * 100,
    };
  });
  return (
    <BarChart
      data={datos}
      index="grupo"
      categories={ETIQUETAS}
      colors={COLORES}
      valueFormatter={proporcion ? porcentaje : numeroCompacto}
      maxValue={proporcion ? 100 : undefined}
      stack
      showAnimation
      className="h-72"
    />
  );
}

type ClaveDesglose = keyof CeldaDesglose;

// Accesores de orden como constante de módulo: identidad ESTABLE entre renders,
// requisito de `useOrdenTabla` para no anular su memo interno. Para entradas sin
// celda devolvemos `null`: el hook las manda al final en cualquier dirección.
const ACCESORES_DESGLOSE = {
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
} as Record<ClaveDesglose, (e: EntradaRejilla) => number | string | null>;

function TablaDesglose({
  celdas,
  totales,
  marcas,
  redes,
}: {
  celdas: CeldaDesglose[];
  totales: Record<string, number>;
  marcas: MarcaDisponible[];
  redes: readonly string[];
}) {
  // Rejilla marca×red (solo redes en foco): una red en foco sin datos va como entrada con
  // `celda` undefined, que el orden empuja al final (`null` no es un 0 real) y se pinta "—".
  const rejilla = React.useMemo(
    () => construirRejilla(celdas, redes),
    [celdas, redes],
  );

  // Cada componente del desglose + nº de piezas es ordenable (accesores estables arriba).
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<EntradaRejilla, ClaveDesglose>(
    rejilla,
    ACCESORES_DESGLOSE,
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
            {COMPONENTES_TABLA.map((c) => (
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
              {COMPONENTES_TABLA.map((comp) => (
                <TableCell key={comp.clave} className="text-right tabular-nums">
                  {celda ? numeroCompleto(celda[comp.clave] as number) : "—"}
                </TableCell>
              ))}
              <TableCell className="text-right tabular-nums">{celda ? celda.n_piezas : "—"}</TableCell>
            </TableRow>
          ))}
          <TableRow className="border-t-2 font-medium">
            <TableCell>Total</TableCell>
            <TableCell />
            {COMPONENTES_TABLA.map((comp) => (
              <TableCell key={comp.clave} className="text-right tabular-nums">
                {numeroCompleto(totales[comp.clave] ?? 0)}
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
            colSpan={COMPONENTES_TABLA.length + 3}
          />
        )}
      </Table>
    </div>
  );
}

/**
 * Desglose de interacciones por marca×red (estrategia digital).
 *
 * Descompone las interacciones del periodo en sus partes (me gusta, comentarios,
 * compartidos, guardados, reproducciones) por cada celda marca×red. Pinta un BarChart
 * apilado (una barra por marca×red, segmentada SOLO por interacciones: las
 * reproducciones son consumo, no interacción, y aplastarían al resto) y una tabla con
 * el detalle por columna y los `totales` del periodo.
 *
 * La gráfica ofrece dos modos: "Proporción" (apilado al 100 %, cada barra normalizada a
 * su composición) y "Volumen" (apilado absoluto). El modo proporción es el predeterminado
 * porque los "me gusta" superan en órdenes de magnitud a comentarios/compartidos/guardados
 * y, en volumen absoluto, aplastan al resto hasta hacerlos invisibles; normalizar a 100 %
 * vuelve legible cada segmento y compara composición entre marcas/redes aunque difieran en
 * volumen.
 *
 * Mismo stack (Tremor) y estados honestos (carga / vacío / error) que el resto de
 * Métricas: si la fuente no expone celdas, lo dice en vez de inventar. Encuadre UNIFORME
 * (`Seccion`): cabecera fuera del contenido, con el toggle de modo a la izquierda del
 * editor de campos. Qué columnas de la TABLA se ven y en qué orden lo decide ese editor
 * (`vistaConfig.columnas.desglose`). El foco de red lo manda el selector GLOBAL de la
 * cabecera (solo se muestran las redes seleccionadas).
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "@tremor/react";
import { Activity } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup } from "@/components/ui/toggle-group";
import {
  Table,
  TableBody,
  TableCell,
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
import type { ColumnaMeta } from "./columnasMeta";
import { MARCA_TODAS } from "./Controles";
import { PieMostrarMas } from "./PieMostrarMas";
import { Seccion } from "./Seccion";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

/** Id de tabla del desglose (clave en `vistaConfig.columnas`). */
const TABLA_DESGLOSE = "desglose";

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

const ETIQUETAS = COMPONENTES_GRAFICA.map((c) => c.etiqueta);
const COLORES = COMPONENTES_GRAFICA.map((c) => c.color);

// Columnas configurables de la TABLA (orden base + etiquetas legibles). Incluye marca y
// red como columnas controlables; el editor de campos las reordena/oculta como al resto.
const COLUMNAS: ColumnaMeta[] = [
  { id: "marca", etiqueta: "Marca" },
  { id: "red", etiqueta: "Red" },
  { id: "likes", etiqueta: "Me gusta" },
  { id: "comentarios", etiqueta: "Comentarios" },
  { id: "compartidos", etiqueta: "Compartidos" },
  { id: "guardados", etiqueta: "Guardados" },
  { id: "video_views", etiqueta: "Reproducciones" },
  { id: "n_piezas", etiqueta: "Piezas" },
];

const IDS_BASE = COLUMNAS.map((c) => c.id);
const ETIQUETA_COL = new Map(COLUMNAS.map((c) => [c.id, c.etiqueta]));
// Columnas de texto (alineadas a la izquierda); el resto son numéricas a la derecha.
const COLUMNAS_TEXTO = new Set(["marca", "red"]);

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
  const formato = useVistaConfig((s) => s.formato);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "desglose", rangoActual ?? "", marca_ ?? "todas", red ?? "todas", formato ?? "todos"],
    queryFn: ({ signal }) => api.metricasDesglose({ rango: rangoActual, marca: marca_, red: red ?? undefined, formato: formato ?? undefined }, signal),
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
    <Seccion
      id="desglose"
      titulo="Desglose de interacciones"
      icono={Activity}
      acciones={acciones}
      tablaId={TABLA_DESGLOSE}
      columnas={COLUMNAS}
      contentClassName="space-y-4"
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
        <>
          <Card className="p-4 sm:p-6">
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
          </Card>
          <Card className="overflow-hidden py-2">
            <TablaDesglose celdas={celdas} marcas={marcas} redes={redes} />
          </Card>
        </>
      )}
    </Seccion>
  );
}

/** Una entrada de la rejilla marca×red: la celda real o `undefined` si esa red no trae datos. */
type EntradaRejilla = { marca: string; red: RedCanonica; celda: CeldaDesglose | undefined };

/**
 * Construye la rejilla marca×red SOLO con las combinaciones que tienen datos (dentro de las
 * redes EN FOCO). Una marca×red sin datos NO se emite: una fila entera de "—" es ruido (p.ej.
 * con el foco en "foto", las redes donde no se publican fotos no aparecen). Las redes fuera
 * del foco tampoco entran.
 */
function construirRejilla(
  celdas: CeldaDesglose[],
  redes: readonly string[],
): EntradaRejilla[] {
  const enFoco = new Set(redes.map((r) => r.toLowerCase()));
  // Marcas en orden de primera aparición en las celdas (estable, sin reordenar).
  const marcasOrden: string[] = [];
  const porClave = new Map<string, CeldaDesglose>();
  for (const c of celdas) {
    if (!enFoco.has(c.red.toLowerCase())) continue;
    if (!marcasOrden.includes(c.marca)) marcasOrden.push(c.marca);
    porClave.set(`${c.marca}::${c.red.toLowerCase()}`, c);
  }
  const rejilla: EntradaRejilla[] = [];
  for (const marca of marcasOrden) {
    for (const red of redes) {
      const celda = porClave.get(`${marca}::${red.toLowerCase()}`);
      if (celda) rejilla.push({ marca, red: red as RedCanonica, celda });
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
  marca: (e) => e.marca,
  red: (e) => e.red,
  // El resto de claves de CeldaDesglose no se usan como orden, pero el tipo las exige.
  interacciones: (e) => e.celda?.interacciones ?? null,
  visualizaciones: (e) => e.celda?.visualizaciones ?? null,
  engagement_pct: (e) => e.celda?.engagement_pct ?? null,
} as Record<ClaveDesglose, (e: EntradaRejilla) => number | string | null>;

function TablaDesglose({
  celdas,
  marcas,
  redes,
}: {
  celdas: CeldaDesglose[];
  marcas: MarcaDisponible[];
  redes: readonly string[];
}) {
  // Orden y visibilidad de columnas efectivos (editor de campos / vistas guardadas).
  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_DESGLOSE]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);

  // Rejilla marca×red SOLO con combinaciones con datos (en foco): las vacías se omiten.
  const rejilla = React.useMemo(
    () => construirRejilla(celdas, redes),
    [celdas, redes],
  );

  // Totales de la fila final: suma de las filas MOSTRADAS (no del backend, que no cuenta
  // `n_piezas`), así el Total cuadra exactamente con lo que se ve, incluidas las Piezas.
  const totalFila = React.useMemo(() => {
    const t: Record<string, number> = {};
    for (const { celda } of rejilla) {
      if (!celda) continue;
      for (const id of IDS_BASE) {
        if (COLUMNAS_TEXTO.has(id)) continue;
        t[id] = (t[id] ?? 0) + (Number(celda[id as keyof CeldaDesglose]) || 0);
      }
    }
    return t;
  }, [rejilla]);

  // Cada columna es ordenable (accesores estables arriba), incluidas marca y red.
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<EntradaRejilla, ClaveDesglose>(
    rejilla,
    ACCESORES_DESGLOSE,
  );

  // Recorte a 5 filas (post-orden): las visibles son el top 5 según la columna activa.
  const { visibles, expandido, alternar, hayMas } = useFilasPlegables(filasOrdenadas, 5);

  const cabecera = (id: string) => {
    const clave = id as ClaveDesglose;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear={COLUMNAS_TEXTO.has(id) ? "left" : "right"}
      >
        {ETIQUETA_COL.get(id) ?? id}
      </CabeceraOrdenable>
    );
  };

  const celdaFila = ({ marca, red, celda }: EntradaRejilla, id: string) => {
    if (id === "marca") {
      return (
        <TableCell key={id} className="font-medium">
          {nombreMarca(marca, marcas)}
        </TableCell>
      );
    }
    if (id === "red") {
      return (
        <TableCell key={id} className="text-muted-foreground">
          {nombreRed(red)}
        </TableCell>
      );
    }
    if (id === "n_piezas") {
      return (
        <TableCell key={id} className="text-right tabular-nums">
          {celda ? celda.n_piezas : "—"}
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className="text-right tabular-nums">
        {celda ? numeroCompleto(celda[id as ClaveDesglose] as number) : "—"}
      </TableCell>
    );
  };

  const celdaTotal = (id: string) => {
    if (id === "marca") {
      return <TableCell key={id}>Total</TableCell>;
    }
    if (id === "red") {
      return <TableCell key={id} />;
    }
    return (
      <TableCell key={id} className="text-right tabular-nums">
        {numeroCompleto(totalFila[id] ?? 0)}
      </TableCell>
    );
  };

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>{columnas.map(cabecera)}</TableRow>
        </TableHeader>
        <TableBody>
          {visibles.map((fila) => (
            <TableRow
              key={`${fila.marca}-${fila.red}`}
              className={fila.celda ? undefined : "text-muted-foreground"}
            >
              {columnas.map((id) => celdaFila(fila, id))}
            </TableRow>
          ))}
          <TableRow className="border-t-2 font-medium">{columnas.map(celdaTotal)}</TableRow>
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
  );
}

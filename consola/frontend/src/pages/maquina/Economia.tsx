/**
 * Página ECONOMÍA (`/maquina/economia`): la CONTABILIDAD de la máquina de contenido, separada de
 * la operación de la cola (`/maquina/computo`). Reúne el gasto: el presupuesto + la parada de
 * emergencia (POR MARCA si hay marca activa; GLOBAL en "todas"), un AGREGADO de todas las pestañas
 * y la economía de tokens de las 4 PESTAÑAS de Contexto, dispuestas en parejas paralelas
 * (Investigación ‖ Producción arriba, Herramientas ‖ Desarrollo debajo). Cada pestaña trae sus
 * KPIs (trabajos IA · tokens · coste), una tabla por DÍA (desplegable a su desglose por etapa) y
 * otra por ETAPA del pipeline (desplegable a su serie por día).
 *
 * Todo sale de `/api/actividad/economia` (ledger `gasto_ia`): la MISMA fuente para totales y
 * desgloses, así que cuadra. Respeta el switch de marca: una marca activa acota el desglose a sus
 * filas; "todas" muestra el AGREGADO global. El presupuesto se sirve por separado (la cola, que ya
 * respeta el switch de marca). `?proceso=` enfoca a una sola pestaña; la ventana (Día/7/30) la fija
 * el usuario con un selector.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearDia } from "@/lib/fecha";
import { costeUsd, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { INTERVALO_SERIE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import { PanelPresupuesto } from "@/pages/maquina/cola-comun";
import { PROC_META } from "@/pages/monitor/comun";
import type {
  EconomiaCelda,
  EconomiaDia,
  EconomiaEtapaConDias,
  EconomiaProcesoBloque,
  PestanaEconomia,
} from "@/types";

/** Las 4 pestañas de Contexto. El orden de PAREJAS importa: los dos motores (ADR 0011) arriba,
 *  Herramientas y Desarrollo (agentes sueltos) debajo. Cada pareja se pinta en paralelo. */
const PAREJAS: readonly (readonly [PestanaEconomia, PestanaEconomia])[] = [
  ["investigacion", "produccion"],
  ["herramientas", "desarrollo"],
];
const PESTANAS: readonly PestanaEconomia[] = PAREJAS.flat();
// Color por CATEGORÍA (identifica la pestaña en cabeceras y puntos), no un estado de trabajo: por
// eso va con color directo, igual que `PROC_META`, y no por `Badge`/`ChipEstado`.
const META: Record<PestanaEconomia, { etiqueta: string; barra: string; texto: string }> = {
  investigacion: PROC_META.investigacion,
  produccion: PROC_META.produccion,
  herramientas: { etiqueta: "Herramientas", barra: "bg-violet-500/70", texto: "text-violet-600" },
  desarrollo: { etiqueta: "Desarrollo", barra: "bg-amber-500/70", texto: "text-amber-600" },
};

/** Ventanas de tiempo del selector (días que pide la economía). */
const VENTANAS: readonly { dias: number; etiqueta: string }[] = [
  { dias: 1, etiqueta: "Día" },
  { dias: 7, etiqueta: "7 días" },
  { dias: 30, etiqueta: "30 días" },
];
const VENTANA_DEFECTO = 7;

const CELDA_CERO: EconomiaCelda = { items: 0, tokens: 0, coste_usd: 0 };

/** Línea discreta de "sin datos": una sola fila, no una tarjeta enorme con hueco. */
function LineaVacia({ texto }: { texto: string }) {
  return <p className="px-6 py-3 text-sm text-muted-foreground">{texto}</p>;
}

/** Tres celdas numéricas (items · tokens · coste) reutilizadas por todas las filas. Una fila SIN
 *  actividad (items 0) muestra «—» en vez de ceros: así las tablas paralelas mantienen TODAS sus
 *  entradas (mismo nº de filas) sin huecos ni asimetrías. */
function CeldasGasto({ celda }: { celda: EconomiaCelda }) {
  if (celda.items === 0) {
    return (
      <>
        <TableCell className="text-right text-muted-foreground">—</TableCell>
        <TableCell className="text-right text-muted-foreground">—</TableCell>
        <TableCell className="pr-6 text-right text-muted-foreground">—</TableCell>
      </>
    );
  }
  return (
    <>
      <TableCell className="text-right tabular-nums">{numeroCompleto(celda.items)}</TableCell>
      <TableCell className="text-right tabular-nums" title={numeroCompleto(celda.tokens)}>
        {numeroCompacto(celda.tokens)}
      </TableCell>
      <TableCell className="pr-6 text-right tabular-nums">{costeUsd(celda.coste_usd)}</TableCell>
    </>
  );
}

/** Cabecera de columnas compartida: primera columna libre + Items · Tokens · Coste. */
function CabeceraGasto({ primera }: { primera: string }) {
  return (
    <TableHeader>
      <TableRow>
        <TableHead className="pl-6">{primera}</TableHead>
        <TableHead className="text-right">Items</TableHead>
        <TableHead className="text-right">Tokens</TableHead>
        <TableHead className="pr-6 text-right">Coste</TableHead>
      </TableRow>
    </TableHeader>
  );
}

/** Botón-celda de la primera columna: chevron que gira al abrir + etiqueta. */
function CeldaDesplegable({
  abierto,
  etiqueta,
  onToggle,
  aria,
}: {
  abierto: boolean;
  etiqueta: string;
  onToggle: () => void;
  aria: string;
}) {
  return (
    <TableCell className="pl-4 font-medium">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={abierto}
        aria-label={aria}
        className="flex items-center gap-1.5 text-left hover:text-foreground"
      >
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            abierto && "rotate-90",
          )}
          aria-hidden="true"
        />
        {etiqueta}
      </button>
    </TableCell>
  );
}

/** Conjunto de claves abiertas (filas desplegadas) con toggle. */
function useDesplegables() {
  const [abierto, setAbierto] = React.useState<Set<string>>(() => new Set());
  const toggle = (clave: string) =>
    setAbierto((prev) => {
      const sig = new Set(prev);
      if (sig.has(clave)) sig.delete(clave);
      else sig.add(clave);
      return sig;
    });
  return { abierto, toggle };
}

/** Celda de la primera columna SIN desplegable (filas vacías o sub-filas): sangrada como las que
 *  sí lo llevan, para que la columna no «baile» entre filas con y sin chevron. */
function CeldaSimple({ etiqueta, sangria = "pl-9" }: { etiqueta: string; sangria?: string }) {
  return <TableCell className={cn(sangria, "font-medium text-muted-foreground")}>{etiqueta}</TableCell>;
}

/** Tabla POR DÍA (más reciente primero). Muestra EXACTAMENTE los días de `diasVisibles` (la unión
 *  de días con actividad en CUALQUIER pestaña): así las tablas paralelas tienen las MISMAS filas, sin
 *  huecos ni asimetrías. Un día sin actividad en ESTA pestaña va con «—» y sin desplegable; uno con
 *  actividad despliega su desglose por ETAPA del pipeline. */
function TablaPorDia({ filas, diasVisibles }: { filas: EconomiaDia[]; diasVisibles: string[] }) {
  const porDia = React.useMemo(() => new Map(filas.map((f) => [f.dia, f])), [filas]);
  const { abierto, toggle } = useDesplegables();
  const CELDA_DIA_CERO: EconomiaDia = { dia: "", items: 0, tokens: 0, coste_usd: 0, por_etapa: [] };
  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por día</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {diasVisibles.length === 0 ? (
          <LineaVacia texto="Sin actividad en la ventana" />
        ) : (
          <Table>
            <CabeceraGasto primera="Día" />
            <TableBody>
              {diasVisibles.map((dia) => {
                const f = porDia.get(dia) ?? { ...CELDA_DIA_CERO, dia };
                const open = abierto.has(f.dia);
                const vacio = f.items === 0;
                return (
                  <React.Fragment key={f.dia}>
                    <TableRow>
                      {vacio ? (
                        <CeldaSimple etiqueta={formatearDia(f.dia)} />
                      ) : (
                        <CeldaDesplegable
                          abierto={open}
                          etiqueta={formatearDia(f.dia)}
                          onToggle={() => toggle(f.dia)}
                          aria={`Desglose por etapa de ${formatearDia(f.dia)}`}
                        />
                      )}
                      <CeldasGasto celda={f} />
                    </TableRow>
                    {open &&
                      f.por_etapa.map((e) => (
                        <TableRow key={`${f.dia}-${e.etapa}`} className="bg-muted/30">
                          <TableCell className="pl-11 text-sm text-muted-foreground">
                            {e.etapa}
                          </TableCell>
                          <CeldasGasto celda={e} />
                        </TableRow>
                      ))}
                  </React.Fragment>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/** Tabla POR ETAPA del pipeline (ordenada por coste desc): cada etapa despliega su serie por DÍA. */
function TablaPorEtapa({ filas }: { filas: EconomiaEtapaConDias[] }) {
  const conActividad = React.useMemo(() => filas.filter((f) => f.items > 0), [filas]);
  const { abierto, toggle } = useDesplegables();
  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por etapa</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {conActividad.length === 0 ? (
          <LineaVacia texto="Sin actividad por etapa" />
        ) : (
          <Table>
            <CabeceraGasto primera="Etapa" />
            <TableBody>
              {conActividad.map((f) => {
                const open = abierto.has(f.etapa);
                const dias = f.por_dia
                  .filter((d) => d.items > 0)
                  .sort((a, b) => b.dia.localeCompare(a.dia));
                return (
                  <React.Fragment key={f.etapa}>
                    <TableRow>
                      <CeldaDesplegable
                        abierto={open}
                        etiqueta={f.etapa}
                        onToggle={() => toggle(f.etapa)}
                        aria={`Desglose por día de ${f.etapa}`}
                      />
                      <CeldasGasto celda={f} />
                    </TableRow>
                    {open &&
                      dias.map((d) => (
                        <TableRow key={`${f.etapa}-${d.dia}`} className="bg-muted/30">
                          <TableCell className="pl-11 text-sm text-muted-foreground">
                            {formatearDia(d.dia)}
                          </TableCell>
                          <CeldasGasto celda={d} />
                        </TableRow>
                      ))}
                  </React.Fragment>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/** Una pestaña: cabecera con su color + KPIs del periodo + tablas Por día / Por etapa (apiladas).
 *  `diasVisibles` (común a las 4 pestañas) hace que las tablas Por día sean simétricas. */
function ColumnaPestana({
  pestana,
  bloque,
  cargando,
  diasVisibles,
}: {
  pestana: PestanaEconomia;
  bloque: EconomiaProcesoBloque | undefined;
  cargando: boolean;
  diasVisibles: string[];
}) {
  const meta = META[pestana];
  const total = bloque?.total ?? CELDA_CERO;
  return (
    <section className="space-y-4">
      <div className="space-y-3">
        <h2 className={cn("flex items-center gap-2 text-base font-semibold tracking-tight", meta.texto)}>
          <span className={cn("h-2 w-2 rounded-full", meta.barra)} aria-hidden="true" />
          {meta.etiqueta}
        </h2>
        {cargando ? (
          <Skeleton className="h-24 w-full rounded-xl" />
        ) : (
          <div className="grid grid-cols-3 gap-4">
            <TarjetaKpi variante="borde" etiqueta="Trabajos IA" valor={numeroCompleto(total.items)} />
            <TarjetaKpi
              variante="borde"
              etiqueta="Tokens"
              valor={numeroCompacto(total.tokens)}
              titulo={numeroCompleto(total.tokens)}
            />
            <TarjetaKpi variante="borde" etiqueta="Coste" valor={costeUsd(total.coste_usd)} />
          </div>
        )}
      </div>
      {cargando ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : (
        <div className="space-y-4">
          <TablaPorDia filas={bloque?.por_dia ?? []} diasVisibles={diasVisibles} />
          <TablaPorEtapa filas={bloque?.por_etapa ?? []} />
        </div>
      )}
    </section>
  );
}

export default function Economia() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [searchParams, setSearchParams] = useSearchParams();
  const crudo = searchParams.get("proceso");
  const foco: PestanaEconomia | undefined = PESTANAS.includes(crudo as PestanaEconomia)
    ? (crudo as PestanaEconomia)
    : undefined;

  // Ventana de tiempo (Día / 7 / 30): la fija el usuario con un selector; reenfoca todo.
  const [dias, setDias] = React.useState<number>(VENTANA_DEFECTO);
  const etiquetaVentana = VENTANAS.find((v) => v.dias === dias)?.etiqueta ?? `${dias} días`;

  // Presupuesto + parada de emergencia: la cola lo trae, ya con el ámbito de marca (estado(marca)).
  const cola = useQuery({
    queryKey: ["actividad", "cola", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.cola({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  // Economía agrupada en las 4 pestañas (ledger gasto_ia). Respeta el switch de marca.
  const economia = useQuery({
    queryKey: ["actividad", "economia", dias, marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.economia({ dias, marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });

  const quitarFoco = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("proceso");
    setSearchParams(params, { replace: true });
  };

  const bloqueDe = (p: PestanaEconomia) => economia.data?.por_proceso?.[p];
  // Agregado de TODAS las pestañas (la foto global del periodo), bajo el presupuesto.
  const agregado = React.useMemo<EconomiaCelda>(() => {
    const pp = economia.data?.por_proceso;
    if (!pp) return CELDA_CERO;
    return PESTANAS.reduce(
      (acc, p) => {
        const t = pp[p]?.total;
        if (t) {
          acc.items += t.items;
          acc.tokens += t.tokens;
          acc.coste_usd += t.coste_usd;
        }
        return acc;
      },
      { items: 0, tokens: 0, coste_usd: 0 },
    );
  }, [economia.data]);

  // Días VISIBLES en las tablas Por día: la UNIÓN de días con actividad en CUALQUIER pestaña,
  // recientes primero. Común a las 4 tablas -> mismas filas, simétricas y sin huecos (los días
  // sin gasto en una pestaña salen con «—»). Vacío si no hubo actividad en toda la ventana.
  const diasVisibles = React.useMemo<string[]>(() => {
    const pp = economia.data?.por_proceso;
    if (!pp) return [];
    const activos = new Set<string>();
    for (const p of PESTANAS)
      for (const d of pp[p]?.por_dia ?? []) if (d.items > 0) activos.add(d.dia);
    return [...activos].sort((a, b) => b.localeCompare(a));
  }, [economia.data]);

  const parejas: readonly (readonly PestanaEconomia[])[] = foco ? [[foco]] : PAREJAS;

  return (
    <>
      {/* Prefiltro de pestaña (?proceso=): la página queda enfocada a esa pestaña. */}
      {foco && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>
            Enfocado a <strong className={META[foco].texto}>{META[foco].etiqueta}</strong>.
          </span>
          <Button variant="ghost" size="sm" onClick={quitarFoco}>
            Ver las 4 pestañas
          </Button>
        </div>
      )}

      {/* Presupuesto + parada de emergencia (GLOBAL o de la marca activa). */}
      <div className="mb-6">
        {cola.isError ? (
          <BloqueError
            titulo="No se pudo leer el presupuesto"
            mensaje={mensajeError(cola.error)}
            onReintentar={() => void cola.refetch()}
            cargando={cola.isFetching}
          />
        ) : cola.isPending ? (
          <Skeleton className="h-28 w-full rounded-xl" />
        ) : (
          cola.data.presupuesto && (
            <PanelPresupuesto
              presupuesto={cola.data.presupuesto}
              esAdmin={esAdmin}
              nombreMarca={nombreActiva ?? undefined}
            />
          )
        )}
      </div>

      {/* Agregado de TODAS las pestañas (mismas tarjetas KPI que cada pestaña) + selector de ventana
          (un solo selector, no 3 filtros). */}
      <section className="mb-6 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">
            Total{" "}
            <span className="font-normal text-muted-foreground">
              · 4 pestañas · {etiquetaVentana.toLowerCase()}
            </span>
          </h2>
          <Select value={String(dias)} onValueChange={(v) => setDias(Number(v))}>
            <SelectTrigger className="w-36 shrink-0" aria-label="Ventana de tiempo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {VENTANAS.map((v) => (
                <SelectItem key={v.dias} value={String(v.dias)}>
                  {v.etiqueta}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <TarjetaKpi variante="borde" etiqueta="Trabajos IA" valor={numeroCompleto(agregado.items)} />
          <TarjetaKpi
            variante="borde"
            etiqueta="Tokens"
            valor={numeroCompacto(agregado.tokens)}
            titulo={numeroCompleto(agregado.tokens)}
          />
          <TarjetaKpi variante="borde" etiqueta="Coste" valor={costeUsd(agregado.coste_usd)} />
        </div>
      </section>

      {economia.isError ? (
        <BloqueError
          titulo="No se pudo leer la economía"
          mensaje={mensajeError(economia.error)}
          onReintentar={() => void economia.refetch()}
          cargando={economia.isFetching}
        />
      ) : (
        // Pestañas en parejas paralelas: Investigación ‖ Producción, luego Herramientas ‖ Desarrollo.
        <div className="space-y-8">
          {parejas.map((pareja, i) => (
            <div key={i} className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              {pareja.map((p) => (
                <ColumnaPestana
                  key={p}
                  pestana={p}
                  bloque={bloqueDe(p)}
                  cargando={economia.isPending}
                  diasVisibles={diasVisibles}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

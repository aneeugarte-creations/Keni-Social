/**
 * Página ECONOMÍA (`/maquina/economia`): la CONTABILIDAD de la máquina de contenido, separada de
 * la operación de la cola (`/maquina/computo`). Reúne el gasto: el presupuesto + la parada de
 * emergencia (POR MARCA si hay marca activa; GLOBAL en "todas") y la economía de tokens agrupada
 * en las 4 PESTAÑAS de Contexto (Investigación · Producción · Herramientas · Desarrollo), cada una
 * con sus KPIs (trabajos IA · tokens · coste), una tabla por DÍA (desplegable a su desglose por
 * etapa/prompt) y otra por ETAPA (desplegable a su serie por día).
 *
 * Todo sale de `/api/actividad/economia` (ledger `gasto_ia`): la MISMA fuente para totales y
 * desgloses, así que cuadra. Respeta el switch de marca: una marca activa acota el desglose a sus
 * filas; "todas" muestra el AGREGADO global. El presupuesto se sirve por separado (la cola, que ya
 * respeta el switch de marca). `?proceso=` enfoca a una sola pestaña; la ventana (Día/7/30) la fija
 * el propio usuario.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Button } from "@/components/ui/button";
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
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearDia } from "@/lib/fecha";
import { costeUsd, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
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

/** Las 4 pestañas de Contexto, en orden de flujo, con su etiqueta y color. Reusa la meta de los
 *  dos motores (ADR 0011) y añade Herramientas y Desarrollo. */
const PESTANAS: readonly PestanaEconomia[] = [
  "investigacion",
  "produccion",
  "herramientas",
  "desarrollo",
];
const META: Record<PestanaEconomia, { etiqueta: string; barra: string; texto: string }> = {
  investigacion: PROC_META.investigacion,
  produccion: PROC_META.produccion,
  herramientas: { etiqueta: "Herramientas", barra: "bg-violet-500/70", texto: "text-violet-600" },
  desarrollo: { etiqueta: "Desarrollo", barra: "bg-amber-500/70", texto: "text-amber-600" },
};

/** Las ventanas de tiempo seleccionables (días que pide la economía). */
const VENTANAS: readonly { dias: number; etiqueta: string }[] = [
  { dias: 1, etiqueta: "Día" },
  { dias: 7, etiqueta: "7 días" },
  { dias: 30, etiqueta: "30 días" },
];
const VENTANA_DEFECTO = 7;

/** Etiqueta legible de una etapa (= `tipo` del ledger); "—" si viene vacía. */
function etiquetaEtapa(tipo: string): string {
  return tipo ? etiquetaTipoGeneracion(tipo) : "—";
}

/** Línea discreta de "sin datos": una sola fila, no una tarjeta enorme con hueco. */
function LineaVacia({ texto }: { texto: string }) {
  return <p className="px-6 py-3 text-sm text-muted-foreground">{texto}</p>;
}

/** Tres celdas numéricas (items · tokens · coste) reutilizadas por todas las filas. */
function CeldasGasto({ celda }: { celda: EconomiaCelda }) {
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

/** Hook de conjunto de claves abiertas (filas desplegadas) con toggle. */
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

/** Tabla POR DÍA (más reciente primero): cada día despliega su desglose por ETAPA (prompt). */
function TablaPorDia({ filas }: { filas: EconomiaDia[] }) {
  const conActividad = React.useMemo(
    () => filas.filter((f) => f.items > 0).sort((a, b) => b.dia.localeCompare(a.dia)),
    [filas],
  );
  const { abierto, toggle } = useDesplegables();
  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por día</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {conActividad.length === 0 ? (
          <LineaVacia texto="Sin actividad por día" />
        ) : (
          <Table>
            <CabeceraGasto primera="Día" />
            <TableBody>
              {conActividad.map((f) => {
                const open = abierto.has(f.dia);
                return (
                  <React.Fragment key={f.dia}>
                    <TableRow>
                      <CeldaDesplegable
                        abierto={open}
                        etiqueta={formatearDia(f.dia)}
                        onToggle={() => toggle(f.dia)}
                        aria={`Desglose por etapa de ${formatearDia(f.dia)}`}
                      />
                      <CeldasGasto celda={f} />
                    </TableRow>
                    {open &&
                      f.por_etapa.map((e) => (
                        <TableRow key={`${f.dia}-${e.tipo}`} className="bg-muted/30">
                          <TableCell className="pl-11 text-sm text-muted-foreground">
                            {etiquetaEtapa(e.tipo)}
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

/** Tabla POR ETAPA (prompt; ordenada por coste desc): cada etapa despliega su serie por DÍA. */
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
                const open = abierto.has(f.tipo);
                const dias = f.por_dia
                  .filter((d) => d.items > 0)
                  .sort((a, b) => b.dia.localeCompare(a.dia));
                return (
                  <React.Fragment key={f.tipo || "—"}>
                    <TableRow>
                      <CeldaDesplegable
                        abierto={open}
                        etiqueta={etiquetaEtapa(f.tipo)}
                        onToggle={() => toggle(f.tipo)}
                        aria={`Desglose por día de ${etiquetaEtapa(f.tipo)}`}
                      />
                      <CeldasGasto celda={f} />
                    </TableRow>
                    {open &&
                      dias.map((d) => (
                        <TableRow key={`${f.tipo}-${d.dia}`} className="bg-muted/30">
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

/** Cabecera de una pestaña + sus KPIs (Trabajos IA · Tokens · Coste) del periodo. */
function CabeceraKpis({
  pestana,
  bloque,
  cargando,
}: {
  pestana: PestanaEconomia;
  bloque: EconomiaProcesoBloque | undefined;
  cargando: boolean;
}) {
  const meta = META[pestana];
  const total = bloque?.total ?? { items: 0, tokens: 0, coste_usd: 0 };
  return (
    <section className="space-y-3">
      <h2 className={cn("flex items-center gap-2 text-lg font-semibold", meta.texto)}>
        <span className={cn("h-2.5 w-2.5 rounded-full", meta.barra)} aria-hidden="true" />
        {meta.etiqueta}
      </h2>
      {cargando ? (
        <Skeleton className="h-24 w-full rounded-xl" />
      ) : (
        <div className="grid grid-cols-3 gap-3">
          <TarjetaKpi variante="card" etiqueta="Trabajos IA" valor={numeroCompleto(total.items)} />
          <TarjetaKpi
            variante="card"
            etiqueta="Tokens"
            valor={numeroCompacto(total.tokens)}
            titulo={numeroCompleto(total.tokens)}
          />
          <TarjetaKpi variante="card" etiqueta="Coste" valor={costeUsd(total.coste_usd)} />
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

  // Ventana de tiempo (Día / 7 / 30): la fija el usuario; reenfoca todas las tablas y KPIs.
  const [dias, setDias] = React.useState<number>(VENTANA_DEFECTO);

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

  const pestanas: readonly PestanaEconomia[] = foco ? [foco] : PESTANAS;
  const bloqueDe = (p: PestanaEconomia) => economia.data?.por_proceso?.[p];

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

      {/* Selector de ventana (Día / 7 días / 30 días): sustituye al fijo a 7 días, sin icono. */}
      <div className="mb-4 flex items-center gap-1" role="group" aria-label="Ventana de tiempo">
        {VENTANAS.map((v) => (
          <Button
            key={v.dias}
            variant={v.dias === dias ? "default" : "outline"}
            size="sm"
            onClick={() => setDias(v.dias)}
            aria-pressed={v.dias === dias}
          >
            {v.etiqueta}
          </Button>
        ))}
      </div>

      {economia.isError ? (
        <BloqueError
          titulo="No se pudo leer la economía"
          mensaje={mensajeError(economia.error)}
          onReintentar={() => void economia.refetch()}
          cargando={economia.isFetching}
        />
      ) : (
        // Cada pestaña: cabecera + KPIs y, debajo, las dos tablas (por día | por etapa) a la par.
        <div className="space-y-8">
          {pestanas.map((p) => {
            const bloque = bloqueDe(p);
            return (
              <div key={p} className="space-y-4">
                <CabeceraKpis pestana={p} bloque={bloque} cargando={economia.isPending} />
                {economia.isPending ? (
                  <Skeleton className="h-40 w-full rounded-xl" />
                ) : (
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 xl:gap-6">
                    <TablaPorDia filas={bloque?.por_dia ?? []} />
                    <TablaPorEtapa filas={bloque?.por_etapa ?? []} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

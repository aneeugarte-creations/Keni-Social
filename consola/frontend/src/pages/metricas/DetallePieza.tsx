/**
 * Detalle de UNA pieza del periodo (modal): métricas + granulares + curva histórica.
 *
 * Se abre desde `ListaPiezas` al clicar una fila. Muestra todo lo que la fuente sabe de
 * la pieza (agregados + desglose granular) y, perezosamente por su `id`, su CURVA
 * HISTÓRICA (snapshots acumulados, ADR 0007) con KPIs de VELOCIDAD si hay suficientes
 * puntos.
 *
 * Honestidad de cobertura: el histórico solo existe para las piezas que la Consola está
 * SIGUIENDO (con `id_post_metricool`). Para la mayoría de piezas de Metricool aún no hay
 * snapshots → mostramos "sin histórico todavía (esta pieza aún no se está siguiendo)",
 * nunca una curva inventada.
 */
import { useQuery } from "@tanstack/react-query";
import { AreaChart } from "@tremor/react";
import { ExternalLink, Gauge } from "lucide-react";

import { AyudaInfo } from "@/components/comunes/AyudaInfo";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatearDia, formatearFechaHoraCorta } from "@/lib/fecha";
import {
  costeUsd,
  nombreFormato,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  rendimientoRel,
  tiempoVis,
} from "@/lib/formato";
import type { PiezaConImpulso } from "@/types";

/** Una métrica granular: muestra "—" cuando la fuente no la trae (null), no un 0 falso. */
function granular(valor: number | null): string {
  return valor == null ? "—" : numeroCompleto(valor);
}

/** Nota de transparencia de la métrica "Vistas" (fuente Metricool), según la red.
 *
 * En Reels de Facebook/Instagram, Metricool cuenta reproducciones INICIALES y excluye
 * repeticiones (loops), así que puede quedar por debajo del contador nativo de la red. Esa
 * precisión solo aplica a Meta; en el resto de redes la definición es otra, así que el texto
 * genérico no afirma nada falso para TikTok/YouTube/X. */
function notaVistas(plataforma: string): string {
  if (plataforma === "facebook" || plataforma === "instagram") {
    return (
      "Fuente: Metricool. En Facebook e Instagram cuenta reproducciones iniciales; no incluye " +
      "repeticiones (loops), por lo que puede ser menor que el contador que muestra la red."
    );
  }
  return (
    "Fuente: Metricool; la definición de vistas/reproducciones varía por red y puede diferir " +
    "del contador nativo de la plataforma."
  );
}

/** Fecha+hora corta en CDMX de un ts ISO (UTC); vacía/no parseable → "—". */
function fechaHoraCorta(ts: string): string {
  return formatearFechaHoraCorta(ts) || "—";
}

export function DetallePieza({
  pieza,
  abierto,
  onOpenChange,
}: {
  /** Pieza a detallar; null = sin selección (el modal queda cerrado). */
  pieza: PiezaConImpulso | null;
  abierto: boolean;
  onOpenChange: (abierto: boolean) => void;
}) {
  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        {pieza ? <Publicacion pieza={pieza} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function Publicacion({ pieza }: { pieza: PiezaConImpulso }) {
  const titulo = pieza.titulo || "(sin título)";

  // Bloque de impulso/inversión: solo cuando la fuente aporta ALGUNO de estos granulares
  // (red que separa pagado/orgánico, gasto, visionado o marcadores a nivel post). Cada dato
  // se pinta solo si viene; "—" si viene pero es null.
  const tieneImpulso =
    pieza.impresiones !== undefined ||
    pieza.impresiones_pagadas !== undefined ||
    pieza.impresiones_organicas !== undefined ||
    pieza.gasto !== undefined ||
    pieza.tasa_visionado_completo !== undefined ||
    pieza.marcadores !== undefined;

  return (
    <>
      <DialogHeader>
        <DialogTitle className="pr-6">{titulo}</DialogTitle>
        <DialogDescription>
          {nombreRed(pieza.plataforma)} · {nombreFormato(pieza.formato)} ·{" "}
          {formatearDia(pieza.publicado)}
          {pieza.url ? (
            <>
              {" · "}
              <a
                href={pieza.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 underline-offset-4 hover:underline"
              >
                Abrir en la red
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            </>
          ) : null}
        </DialogDescription>
      </DialogHeader>

      {/* Agregados principales. En móvil apilados (3 columnas no caben en un diálogo de 360px). */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Kpi
          etiqueta="Vistas"
          valor={numeroCompacto(pieza.visualizaciones)}
          info={notaVistas(pieza.plataforma)}
        />
        <Kpi etiqueta="Interacciones" valor={numeroCompacto(pieza.interacciones)} />
        <Kpi etiqueta="Engagement" valor={porcentaje(pieza.engagement_pct)} />
      </div>

      {/* Desglose granular (— cuando la fuente no lo trae). */}
      <div>
        <h3 className="mb-2 text-sm font-medium">Desglose</h3>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
          {/* Alcance único: solo Meta lo mide; "—" en el resto (degradación honesta). */}
          <Dato etiqueta="Alcance único" valor={granular(pieza.alcance)} />
          <Dato etiqueta="Me gusta" valor={granular(pieza.likes)} />
          <Dato etiqueta="Comentarios" valor={granular(pieza.comentarios)} />
          <Dato etiqueta="Compartidos" valor={granular(pieza.compartidos)} />
          <Dato etiqueta="Guardados" valor={granular(pieza.guardados)} />
          <Dato etiqueta="Reproducciones" valor={granular(pieza.video_views)} />
          <Dato etiqueta="Clics enlace" valor={granular(pieza.clics_enlace)} />
          <Dato
            etiqueta="Tiempo promedio"
            valor={pieza.tiempo_medio_vis_s == null ? "—" : tiempoVis(pieza.tiempo_medio_vis_s)}
          />
          <Dato
            etiqueta="Rend. relativo"
            valor={rendimientoRel(pieza.rendimiento_relativo)}
          />
        </dl>
      </div>

      {/* Impulso e inversión: paid vs orgánico, gasto y visionado. Solo si la fuente los trae. */}
      {tieneImpulso && (
        <div>
          <h3 className="mb-2 text-sm font-medium">Impulso e inversión</h3>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
            {pieza.impresiones !== undefined && (
              <Dato etiqueta="Impresiones" valor={granular(pieza.impresiones)} />
            )}
            {pieza.impresiones_pagadas !== undefined && (
              <Dato etiqueta="Impresiones pagadas" valor={granular(pieza.impresiones_pagadas)} />
            )}
            {pieza.impresiones_organicas !== undefined && (
              <Dato
                etiqueta="Impresiones orgánicas"
                valor={granular(pieza.impresiones_organicas)}
              />
            )}
            {pieza.gasto !== undefined && (
              <Dato
                etiqueta="Gasto"
                valor={pieza.gasto == null ? "—" : costeUsd(pieza.gasto)}
              />
            )}
            {pieza.tasa_visionado_completo !== undefined && (
              <Dato
                etiqueta="Visionado completo"
                valor={
                  pieza.tasa_visionado_completo == null
                    ? "—"
                    : porcentaje(pieza.tasa_visionado_completo * 100)
                }
              />
            )}
            {pieza.marcadores !== undefined && (
              <Dato etiqueta="Marcadores" valor={granular(pieza.marcadores)} />
            )}
          </dl>
        </div>
      )}

      <Historico piezaId={pieza.id} />
    </>
  );
}

function Historico({ piezaId }: { piezaId: string }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "pieza-historico", piezaId],
    queryFn: ({ signal }) => api.metricasPiezaHistorico({ id: piezaId }, signal),
    staleTime: 2 * 60_000,
  });

  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 text-sm font-medium">
        <Gauge className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        Curva histórica
      </h3>
      {isPending ? (
        <Skeleton className="h-44 w-full rounded-lg" />
      ) : isError ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No se pudo cargar el histórico de la pieza.
        </p>
      ) : data.puntos.length === 0 ? (
        // Honestidad de cobertura: sin snapshots no inventamos una curva.
        <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          Sin histórico todavía.
        </p>
      ) : (
        <CurvaHistorica data={data} />
      )}
    </div>
  );
}

function CurvaHistorica({
  data,
}: {
  data: NonNullable<Awaited<ReturnType<typeof api.metricasPiezaHistorico>>>;
}) {
  const datos = data.puntos.map((p) => ({
    momento: fechaHoraCorta(p.ts),
    Vistas: p.visualizaciones,
    Interacciones: p.interacciones,
  }));

  return (
    <div className="space-y-3">
      <AreaChart
        data={datos}
        index="momento"
        categories={["Vistas", "Interacciones"]}
        colors={["orange", "violet"]}
        valueFormatter={numeroCompacto}
        showLegend
        showAnimation
        startEndOnly
        curveType="monotone"
        className="h-44"
      />
      {data.velocidad ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Kpi
            etiqueta="% en las primeras 24 h"
            valor={
              data.velocidad.pct_en_primeras_24h == null
                ? "—"
                : porcentaje(data.velocidad.pct_en_primeras_24h)
            }
          />
          <Kpi
            etiqueta="Crecimiento diario promedio"
            valor={
              data.velocidad.delta_medio_por_dia == null
                ? "—"
                : numeroCompacto(data.velocidad.delta_medio_por_dia)
            }
          />
          <Kpi etiqueta="Mediciones" valor={numeroCompleto(data.velocidad.n_snapshots)} />
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Velocidad no disponible: se necesitan al menos 2 mediciones.
        </p>
      )}
    </div>
  );
}

function Kpi({
  etiqueta,
  valor,
  info,
}: {
  etiqueta: string;
  valor: string;
  /** Nota de transparencia opcional: pinta un icono "i" que la despliega al clicar. */
  info?: string;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        {etiqueta}
        {info ? <AyudaInfo texto={info} etiqueta={`Qué es ${etiqueta}`} /> : null}
      </p>
      <p className="text-base font-semibold tabular-nums">{valor}</p>
    </div>
  );
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{etiqueta}</dt>
      <dd className="font-medium tabular-nums">{valor}</dd>
    </div>
  );
}

/**
 * MesaNoticias — la vista de CANDIDATAS segmentada por las líneas del plan.
 *
 * El layout ES el plan del día: una cabecera con el progreso ("4 de 12 hoy" + chips por
 * línea) y una sección por línea con sus top candidatas rankeadas. Última hora va primero
 * con sus tarjetas en rojo; lo que el plan no contempla queda plegado en "Fuera del plan".
 * Una sección con cupo sin cubrir y pocas candidatas ES la alerta visual: ahí hay que mirar.
 *
 * Datos: GET /api/noticias/mesa (un solo payload con líneas + cupos + progreso + top-N).
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Loader2, Newspaper, Target } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { etiquetaLinea } from "@/lib/lineas";
import { cn } from "@/lib/utils";
import type { MesaLinea, RespuestaMesa } from "@/types";

import { TarjetaHistoria } from "./TarjetaHistoria";

/** Refresco automático de la mesa (sensación "live", igual que la lista clásica). */
const REFETCH_INTERVAL_MS = 45_000;

/** Candidatas visibles por sección, plegado/expandido ("Ver las N" pide más al back). */
const POR_LINEA_PLEGADO = 5;
const POR_LINEA_EXPANDIDO = 20;

export const CLAVE_MESA = (marca: string, porLinea: number) =>
  ["noticias", "mesa", marca, porLinea] as const;

// ── Cabecera: el plan de hoy ──────────────────────────────────────────────────

function BarraPlanDia({ data, nombre }: { data: RespuestaMesa; nombre: string | null }) {
  if (!data.plan) return null;
  const objetivo = Math.max(1, data.total_objetivo);
  const avance = Math.min(100, (data.total_generados / objetivo) * 100);
  return (
    <div className="mb-4 space-y-2" data-testid="barra-plan-dia">
      <div className="flex flex-wrap items-center gap-2">
        <Target className="h-4 w-4 text-emerald-600" />
        <span className="text-sm font-medium">Plan de hoy{nombre ? ` — ${nombre}` : ""}</span>
        <span className="text-sm tabular-nums text-muted-foreground">
          {data.total_generados} de {data.total_objetivo}
        </span>
        <div className="h-1.5 w-40 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${avance}%` }} />
        </div>
        <Link
          to="/operacion/programacion"
          className="ml-auto text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          Ajustar plan →
        </Link>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {data.lineas.map((l) => {
          const completa = l.generados >= l.cupo;
          return (
            <Badge
              key={l.linea}
              variant="outline"
              className={cn(
                "gap-1 text-xs tabular-nums",
                completa && "border-emerald-500 text-emerald-700",
              )}
              data-testid={`chip-linea-${l.linea}`}
            >
              {etiquetaLinea(l.linea)} {l.generados}/{l.cupo}
              {completa ? " ✓" : ""}
            </Badge>
          );
        })}
      </div>
    </div>
  );
}

// ── Sección por línea ─────────────────────────────────────────────────────────

function SeccionLinea({
  linea,
  clave,
  expandida,
  onToggleExpandida,
}: {
  linea: MesaLinea;
  clave: readonly unknown[];
  expandida: boolean;
  onToggleExpandida: () => void;
}) {
  const etiqueta = etiquetaLinea(linea.linea);
  const hayMas = linea.en_pool > linea.historias.length || expandida;
  return (
    <section className="space-y-2" data-testid={`seccion-${linea.linea}`}>
      <div className="flex flex-wrap items-baseline gap-2 border-b pb-1">
        <h3 className="text-sm font-semibold">{etiqueta}</h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {linea.generados} de {linea.cupo} hoy
        </span>
        {hayMas && linea.en_pool > 0 && (
          <button
            type="button"
            className="ml-auto text-xs text-muted-foreground hover:text-foreground hover:underline"
            onClick={onToggleExpandida}
          >
            {expandida ? "Ver menos" : `Ver las ${linea.en_pool}`}
          </button>
        )}
      </div>
      {linea.historias.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sin candidatas por ahora.</p>
      ) : (
        <div className="space-y-2">
          {linea.historias.map((h) => (
            <TarjetaHistoria key={h.id} historia={h} clavesAInvalidar={[clave]} />
          ))}
        </div>
      )}
    </section>
  );
}

// ── La mesa ───────────────────────────────────────────────────────────────────

export function MesaNoticias({ marca, nombre }: { marca: string; nombre: string | null }) {
  // "Ver las N" por sección: con cualquier sección expandida se piden más por línea (el
  // payload es uno solo; las plegadas siguen mostrando 5).
  const [expandidas, setExpandidas] = React.useState<Set<string>>(() => new Set());
  const [fueraAbierto, setFueraAbierto] = React.useState(false);
  const porLinea = expandidas.size > 0 || fueraAbierto ? POR_LINEA_EXPANDIDO : POR_LINEA_PLEGADO;
  const clave = CLAVE_MESA(marca, porLinea);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.noticias.mesa({ marca, porLinea }, signal),
    staleTime: 20_000,
    refetchInterval: REFETCH_INTERVAL_MS,
    // El refetch no debe "bailar" las tarjetas bajo el cursor: conserva el dato anterior.
    placeholderData: keepPreviousData,
  });

  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar la mesa"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  const data = query.data;
  const alternarExpandida = (linea: string) =>
    setExpandidas((prev) => {
      const next = new Set(prev);
      if (next.has(linea)) next.delete(linea);
      else next.add(linea);
      return next;
    });

  const fuera = data.fuera_de_plan;
  const vacia =
    data.lineas.every((l) => l.en_pool === 0) && fuera.en_pool === 0;

  return (
    <div className="space-y-6">
      <BarraPlanDia data={data} nombre={nombre} />
      {query.isFetching && !query.isPending && (
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" aria-label="Actualizando" />
      )}

      {vacia && (
        <EstadoVacio
          icono={Newspaper}
          titulo="Sin candidatas por ahora"
          texto="Las candidatas aparecerán aquí"
        />
      )}

      {data.lineas
        .filter((l) => l.cupo > 0 || l.en_pool > 0)
        .map((l) => (
          <SeccionLinea
            key={l.linea}
            linea={l}
            clave={clave}
            expandida={expandidas.has(l.linea)}
            onToggleExpandida={() => alternarExpandida(l.linea)}
          />
        ))}

      {/* Fuera del plan (plegado por defecto): líneas de feed que el plan no contempla. */}
      {fuera.en_pool > 0 && (
        <section data-testid="seccion-fuera-de-plan">
          <button
            type="button"
            className="flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-foreground"
            onClick={() => setFueraAbierto((v) => !v)}
            aria-expanded={fueraAbierto}
          >
            {fueraAbierto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            Fuera del plan · {fuera.en_pool} candidata{fuera.en_pool !== 1 ? "s" : ""}
          </button>
          {fueraAbierto && (
            <div className="mt-2 space-y-2">
              {fuera.historias.map((h) => (
                <TarjetaHistoria key={h.id} historia={h} clavesAInvalidar={[clave]} />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

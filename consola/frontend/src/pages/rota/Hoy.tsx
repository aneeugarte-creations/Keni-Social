import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Hand } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { mesDeFecha } from "@/lib/rota-calendario";
import { KpiCobertura } from "@/pages/tareas/KpiCobertura";
import { FilaAgenda } from "@/pages/tareas/PanoramaAgenda";
import type { Item } from "@/pages/tareas/tipos";
import { useTablero } from "@/pages/tareas/useTablero";

/**
 * HOME «Hoy» de Turnos: lo primero que ve el trabajador, para responder «¿cuándo entro y qué
 * cubro?» sin navegar. Tres bloques + cierre:
 *  1) Tu próximo turno (hero): de `misTurnosMes`, el turno de HOY o el siguiente del mes.
 *  2) Por cubrir hoy: los huecos del día (sin dueño, sin turno) — desplegar la fila para coger.
 *  3) Lo mío hoy: lo que cubro/llevo hoy.
 *  +) KPI «Cobertura de hoy» como cierre y enlace a la agenda completa.
 * Reusa `useTablero` (UNA derivación de cobertura) y `FilaAgenda` (que ya oculta las acciones de
 * admin al no-admin vía `AccionesItem`/`AccionUrgente`): «Hoy» no añade nada exclusivo de admin.
 */
export function Hoy({ onVerAgenda }: { onVerAgenda: () => void }) {
  const { marcaActiva } = useMarcaActiva();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const marca = marcaActiva && marcaActiva !== MARCA_ACTIVA_TODAS ? marcaActiva : undefined;

  const t = useTablero(marca, usuario?.id ?? null);
  const [abiertas, setAbiertas] = React.useState<Set<string>>(new Set());
  const toggle = (clave: string) =>
    setAbiertas((prev) => {
      const n = new Set(prev);
      if (n.has(clave)) n.delete(clave);
      else n.add(clave);
      return n;
    });

  // Hero «próximo turno»: misma queryKey que «Mi mes» (VistaMesYo) → cache compartida. El turno de
  // HOY (CDMX) o, si hoy libra, el siguiente del mes en curso.
  const mes = mesDeFecha(new Date());
  const turnoQ = useQuery({
    queryKey: ["rota", "mis-turnos-mes", mes, marcaActiva],
    queryFn: ({ signal }) => api.misTurnosMes({ mes, marca: marca ?? undefined }, signal),
  });
  const misTurnos = turnoQ.data?.mis_turnos ?? [];
  const turnoHoy = misTurnos.find((tn) => tn.fecha === t.hoy);
  const proximo =
    turnoHoy ??
    misTurnos
      .filter((tn) => tn.fecha >= t.hoy)
      .sort((a, b) => a.fecha.localeCompare(b.fecha) || (a.inicio || "").localeCompare(b.inicio || ""))[0];

  // Ítems de HOY (orden = su fecha): los huecos por cubrir y lo mío.
  const itemsHoy = t.items.filter((i) => i.orden === t.hoy);
  const porCubrirHoy = itemsHoy.filter(t.esPorCubrir);
  const mioHoy = itemsHoy.filter(t.esMio);

  const fila = (i: Item) => (
    <FilaAgenda
      key={i.clave}
      item={i}
      abierta={abiertas.has(i.clave)}
      onToggle={() => toggle(i.clave)}
      catalogos={t.catalogos}
    />
  );

  return (
    <div className="space-y-5">
      {/* 1) HERO: tu próximo turno */}
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <CalendarClock className="h-5 w-5 shrink-0 text-muted-foreground" />
          {turnoQ.isLoading ? (
            <Skeleton className="h-5 w-48" />
          ) : proximo ? (
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                {turnoHoy ? "Tu turno hoy" : "Tu próximo turno"}
              </span>
              <span className="text-base font-semibold">{proximo.franja_nombre}</span>
              {proximo.inicio && (
                <span className="tabular-nums text-sm text-muted-foreground">
                  {proximo.inicio}–{proximo.fin}
                </span>
              )}
              {!turnoHoy && <span className="text-sm text-muted-foreground">· {proximo.fecha}</span>}
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">Hoy libras. No tienes turno asignado.</span>
          )}
        </CardContent>
      </Card>

      {t.hayError && t.sinDatos ? (
        <BloqueError
          titulo="No se pudo cargar la agenda de hoy"
          mensaje={mensajeError(t.error)}
          onReintentar={t.reintentar}
          cargando={t.isFetching}
        />
      ) : t.cargando ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-md" />
          ))}
        </div>
      ) : (
        <>
          {/* 2) POR CUBRIR HOY */}
          <section className="space-y-2">
            <h2 className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
              <Hand className="h-3.5 w-3.5" /> Por cubrir hoy
              <span className="tabular-nums">({porCubrirHoy.length})</span>
            </h2>
            {porCubrirHoy.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nada pendiente. Todo lo de hoy tiene quien lo cubra.</p>
            ) : (
              <div className="space-y-2">{porCubrirHoy.map(fila)}</div>
            )}
          </section>

          {/* 3) LO MÍO HOY */}
          <section className="space-y-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              Lo mío hoy <span className="tabular-nums">({mioHoy.length})</span>
            </h2>
            {mioHoy.length === 0 ? (
              <p className="text-sm text-muted-foreground">No tienes nada asignado para hoy.</p>
            ) : (
              <div className="space-y-2">{mioHoy.map(fila)}</div>
            )}
          </section>

          {/* +) KPI de cierre + enlace a la agenda completa */}
          <KpiCobertura
            eventos={t.eventosHoy}
            claims={t.claimsCobertura}
            turnos={t.turnosHoy}
            franjas={t.franjasHoy}
            ausencias={t.ausencias}
            hechas={t.hechasHoy}
            onIrASinCubrir={onVerAgenda}
          />
          <div className="flex justify-end">
            <Button variant="ghost" size="sm" onClick={onVerAgenda}>
              Ver toda la agenda →
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

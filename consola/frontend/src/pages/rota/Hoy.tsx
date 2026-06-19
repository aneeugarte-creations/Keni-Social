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
import { COBERTURA_TEXTO } from "@/lib/estado-color";
import { mesDeFecha } from "@/lib/rota-calendario";
import { cn } from "@/lib/utils";
import { FilaAgenda } from "@/pages/tareas/PanoramaAgenda";
import type { Item } from "@/pages/tareas/tipos";
import { useTablero } from "@/pages/tareas/useTablero";

/**
 * HOME «Hoy» de Turnos: la vista PERSONAL del trabajador, para responder «¿cuándo entro y qué
 * llevo hoy?» sin navegar ni mezclarse con el tablero del equipo. Dos bloques + cierre:
 *  1) Tu próximo turno (hero): de `misTurnosMes`, el turno de HOY o el siguiente del mes.
 *  2) Lo mío hoy: lo que cubro/llevo hoy.
 *  +) Aviso compacto de cuántos huecos quedan por cubrir hoy, con salto a «Cobertura».
 * El KPI del equipo y la LISTA de huecos para coger viven en «Cobertura» (y el KPI también en el
 * panel de coordinación de «Gestión»), no aquí: «Hoy» es TU día, no el del equipo. Reusa
 * `useTablero` (UNA derivación de cobertura) y `FilaAgenda`.
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
          {/* LO MÍO HOY: lo que cubres/llevas hoy (lo único exclusivamente tuyo). */}
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

          {/* Cierre: «Hoy» es tu día. El KPI del equipo y la lista de huecos para coger viven en
              «Cobertura»; aquí solo el aviso de cuántos quedan por cubrir hoy y el salto allí. */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
            {porCubrirHoy.length > 0 ? (
              <span className="flex items-center gap-1.5 text-sm">
                <Hand className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                <span className={cn("font-medium", COBERTURA_TEXTO["sin-cubrir"])}>
                  {`${porCubrirHoy.length} por cubrir hoy`}
                </span>
              </span>
            ) : (
              <span className="text-sm text-muted-foreground">Todo lo de hoy tiene quien lo cubra.</span>
            )}
            <Button variant="ghost" size="sm" onClick={onVerAgenda}>
              Ver toda la agenda →
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

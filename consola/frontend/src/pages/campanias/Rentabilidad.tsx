/**
 * Calculadora de rentabilidad de una campaña: dado lo que se vendió y el margen mínimo a
 * proteger, deriva el TOPE de pauta que se puede invertir sin comprometer esa venta.
 *
 * Pedido explícito de Mariana (sesión 2026-06-30): "se vendió en tanto, ¿puedo meterla
 * hasta tanto?" — que cualquiera del equipo (no solo quien vendió) pueda ver el tope sin
 * rehacer la cuenta a mano. Solo se muestra si la campaña tiene un `precio_venta` definido
 * (0 = sin definir); nunca se le enseña al cliente (ver `PanelCampania`, gateado igual que
 * "Orgánico vs pagado" + redactado server-side en modo cliente/enlace público).
 */
import { Calculator } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Campania, InorganicoCampania } from "@/types";

import { Bloque } from "@/pages/metricas/Bloque";
import { Seccion } from "@/pages/metricas/Seccion";
import { calcularRentabilidad } from "./formato";

function dinero(v: number, moneda: string): string {
  return `${v.toLocaleString("es-MX", { maximumFractionDigits: 0 })} ${moneda}`.trim();
}

function Dato({
  etiqueta,
  valor,
  destacar,
}: {
  etiqueta: string;
  valor: string;
  /** Resalta el valor (rose si se pasó el tope, el color por defecto si no). */
  destacar?: "rose" | "default";
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs text-muted-foreground">{etiqueta}</p>
      <p
        className={cn(
          "text-xl font-semibold tabular-nums",
          destacar === "rose" && "text-rose-600 dark:text-rose-400",
        )}
      >
        {valor}
      </p>
    </div>
  );
}

/** Bloque "Rentabilidad": oculto si la campaña no tiene precio de venta definido. La moneda
 * es la del gasto de pauta (`inorganico.moneda`); sin gasto todavía se usa MXN por defecto
 * (el precio de venta se piensa siempre en pesos, ver transcripción). */
export function BloqueRentabilidad({
  campania,
  inorganico,
}: {
  campania: Campania;
  inorganico: InorganicoCampania;
}) {
  const calc = calcularRentabilidad(campania, inorganico.gasto);
  if (!calc) return null;
  const moneda = inorganico.moneda || "MXN";

  return (
    <Bloque id="campania-rentabilidad" titulo="Rentabilidad">
      <Seccion
        id="campania-rentabilidad"
        titulo="Rentabilidad"
        icono={Calculator}
        descripcion="Cuánta pauta cabe en esta venta sin bajar del margen objetivo."
      >
        <Card
          className={cn(
            calc.sobreTope && "border-rose-300/60 bg-rose-50/40 dark:border-rose-500/30 dark:bg-rose-500/5",
          )}
        >
          <CardContent className="space-y-3 p-5">
            <div className="flex flex-wrap gap-x-8 gap-y-2">
              <Dato etiqueta="Precio de venta" valor={dinero(campania.precio_venta, moneda)} />
              <Dato etiqueta="Margen objetivo" valor={`${campania.margen_objetivo_pct}%`} />
              <Dato etiqueta="Tope de pauta" valor={dinero(calc.tope, moneda)} />
              <Dato
                etiqueta="Gastado en pauta este periodo"
                valor={dinero(inorganico.gasto, moneda)}
              />
              <Dato
                etiqueta={calc.sobreTope ? "Por encima del tope" : "Disponible"}
                valor={dinero(Math.abs(calc.disponible), moneda)}
                destacar={calc.sobreTope ? "rose" : "default"}
              />
            </div>
            {calc.sobreTope && (
              <p className="text-xs text-rose-600 dark:text-rose-400" role="alert">
                El gasto de pauta de este periodo ya superó el tope que protege el margen
                objetivo.
              </p>
            )}
          </CardContent>
        </Card>
      </Seccion>
    </Bloque>
  );
}

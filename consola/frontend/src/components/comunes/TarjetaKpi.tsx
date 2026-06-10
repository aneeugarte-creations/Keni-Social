/**
 * Tarjeta KPI genérica: etiqueta pequeña + valor destacado.
 *
 * Unifica el componente local `TarjetaKpi` de `pages/comercial/Detalle.tsx`
 * con la tarjeta inline equivalente que usaban varias páginas de métricas,
 * evitando la duplicación de estilos y estructura.
 *
 * Modos:
 * - `variante="borde"` (por defecto): borde sutil, sin fondo; usada en Comercial.
 * - `variante="card"` : envuelta en Card de shadcn; usada en el dashboard de Métricas.
 */
import * as React from "react";

import { Card, CardContent } from "@/components/ui/card";

interface TarjetaKpiProps {
  /** Etiqueta descriptiva de la métrica (gris, pequeña). */
  etiqueta: string;
  /** Valor formateado a mostrar (grande, semibold). */
  valor: string;
  /**
   * Tooltip con el valor sin abreviar (opcional). Si no se pasa, el tooltip
   * muestra el propio `valor`.
   */
  titulo?: string;
  /**
   * Variante visual.
   * - `"borde"` (por defecto): caja con borde, sin Card de shadcn.
   * - `"card"`: envuelta en Card de shadcn con padding interior.
   */
  variante?: "borde" | "card";
  /**
   * Insignia opcional alineada a la derecha de la etiqueta (p. ej. un BadgeDelta
   * con la variación vs el periodo anterior). Si no se pasa, la fila de la
   * etiqueta se ve igual que siempre.
   */
  insignia?: React.ReactNode;
}

export function TarjetaKpi({
  etiqueta,
  valor,
  titulo,
  variante = "borde",
  insignia,
}: TarjetaKpiProps) {
  if (variante === "card") {
    return (
      <Card>
        <CardContent className="space-y-1.5 p-5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">{etiqueta}</p>
            {insignia}
          </div>
          <p
            className="truncate text-2xl font-semibold tracking-tight tabular-nums"
            title={titulo ?? valor}
          >
            {valor}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">{etiqueta}</p>
        {insignia}
      </div>
      <p className="truncate text-xl font-semibold tabular-nums" title={titulo ?? valor}>
        {valor}
      </p>
    </div>
  );
}

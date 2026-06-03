/**
 * Tabla por red: una fila por plataforma con las métricas agregadas de TODAS las
 * marcas del reporte (espejo de `TablaCuentas`, pero por red en vez de por marca).
 *
 * El backend (`/api/metricas/reporte` › `por_red`) suma `por_plataforma` de cada
 * cuenta por plataforma; cuando hay una marca filtrada, el reporte solo trae sus
 * cuentas, así que esta tabla queda acotada a esa marca (deseado). Las columnas
 * numéricas van alineadas a la derecha con cifras tabulares para la lectura
 * comparada y son ORDENABLES (clic en la cabecera). Al pie, una fila de TOTALES, y
 * bajo la tabla un mini-reparto "% de vistas por red" (barra), como en
 * GraficaMarcas. `alcance` es `null` cuando ninguna cuenta mide alcance en esa red
 * (#138): se muestra "—" en vez de un 0 falso.
 */
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { nombreRed, numeroCompacto, numeroCompleto, porcentaje } from "@/lib/formato";
import type { RedMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { useOrdenTabla } from "./useOrdenTabla";

type ClaveRed = "visualizaciones" | "interacciones" | "engagement_pct";

/** Columnas numéricas en el mismo orden y formato que la tabla por marca. */
const COLUMNAS: Array<{ clave: ClaveRed; etiqueta: string }> = [
  { clave: "visualizaciones", etiqueta: "Vistas" },
  { clave: "interacciones", etiqueta: "Interacciones" },
  { clave: "engagement_pct", etiqueta: "Engagement" },
];

/** Formatea el valor de una columna. */
function valorCelda(r: RedMetrica, clave: ClaveRed): string {
  if (clave === "engagement_pct") {
    return porcentaje(r.engagement_pct);
  }
  return numeroCompleto(r[clave]);
}

/** Totales del periodo por red: suma de las brutas + engagement global derivado. */
function calcularTotales(redes: RedMetrica[]): {
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
} {
  const visualizaciones = redes.reduce((s, r) => s + r.visualizaciones, 0);
  const interacciones = redes.reduce((s, r) => s + r.interacciones, 0);
  const engagement_pct = visualizaciones > 0 ? (interacciones / visualizaciones) * 100 : 0;
  return { visualizaciones, interacciones, engagement_pct };
}

export function TablaRedes({ redes }: { redes: RedMetrica[] }) {
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<RedMetrica, ClaveRed>(redes, {
    visualizaciones: (r) => r.visualizaciones,
    interacciones: (r) => r.interacciones,
    engagement_pct: (r) => r.engagement_pct,
  });

  const totales = calcularTotales(redes);

  // Reparto "% de vistas por red", ordenado de mayor a menor (como GraficaMarcas).
  const totalVis = totales.visualizaciones;
  const reparto = [...redes]
    .sort((a, b) => b.visualizaciones - a.visualizaciones)
    .map((r) => ({
      red: r.red,
      visualizaciones: r.visualizaciones,
      pct: totalVis > 0 ? Math.round((r.visualizaciones / totalVis) * 100) : 0,
    }));

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Detalle por red</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Red</TableHead>
              {COLUMNAS.map((c) => (
                <CabeceraOrdenable
                  key={c.clave}
                  activa={estado.clave === c.clave}
                  direccion={estado.direccion}
                  onClick={() => alClicar(c.clave)}
                  alinear="right"
                  className="pr-6 last:pr-6"
                >
                  {c.etiqueta}
                </CabeceraOrdenable>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {redes.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={COLUMNAS.length + 1}
                  className="py-8 text-center text-muted-foreground"
                >
                  No hay redes para mostrar en este rango.
                </TableCell>
              </TableRow>
            ) : (
              <>
                {filasOrdenadas.map((r) => (
                  <TableRow key={r.red}>
                    <TableCell className="pl-6 font-medium">{nombreRed(r.red)}</TableCell>
                    {COLUMNAS.map((c) => (
                      <TableCell
                        key={c.clave}
                        className="pr-6 text-right tabular-nums last:pr-6"
                      >
                        {valorCelda(r, c.clave)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
                <TableRow className="border-t-2 font-medium">
                  <TableCell className="pl-6">Total</TableCell>
                  {COLUMNAS.map((c) => (
                    <TableCell
                      key={c.clave}
                      className="pr-6 text-right tabular-nums last:pr-6"
                    >
                      {c.clave === "engagement_pct"
                        ? porcentaje(totales.engagement_pct)
                        : numeroCompleto(totales[c.clave])}
                    </TableCell>
                  ))}
                </TableRow>
              </>
            )}
          </TableBody>
        </Table>

        {redes.length > 0 && (
          <div className="space-y-3 border-t border-border px-6 py-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Reparto de vistas por red
            </p>
            <ul className="space-y-3">
              {reparto.map((it) => (
                <li key={it.red}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="truncate text-sm text-foreground">
                      {nombreRed(it.red)}
                    </span>
                    <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                      {numeroCompacto(it.visualizaciones)}
                      <span className="ml-1.5 text-xs text-muted-foreground/70">
                        {it.pct}%
                      </span>
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-[#1e3a8a] transition-all dark:bg-[#1e3a8a]"
                      style={{ width: `${it.pct}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

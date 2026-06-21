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
 * se muestra "—" en vez de un 0 falso.
 */
import * as React from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { nombreRed, numeroCompleto, porcentaje, redCanonica, REDES_CANONICAS } from "@/lib/formato";
import type { RedMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";

const RED_TODAS = "__todas__";

type ClaveRed = "visualizaciones" | "interacciones" | "engagement_pct";

/** Columnas numéricas en el mismo orden y formato que la tabla por marca. */
const COLUMNAS: Array<{ clave: ClaveRed; etiqueta: string }> = [
  { clave: "visualizaciones", etiqueta: "Vistas" },
  { clave: "interacciones", etiqueta: "Interacciones" },
  { clave: "engagement_pct", etiqueta: "Engagement" },
];

/** Accesores de ordenación (constante de módulo: identidad estable para el useMemo del hook). */
const ACCESORES: Record<ClaveRed, (r: RedMetrica) => number> = {
  visualizaciones: (r) => r.visualizaciones,
  interacciones: (r) => r.interacciones,
  engagement_pct: (r) => r.engagement_pct,
};

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

export function TablaRedes({
  redes,
  desnudo = false,
}: {
  redes: RedMetrica[];
  /** `true` => solo la tabla + reparto, sin el `SeccionColapsable` (para deslizar). */
  desnudo?: boolean;
}) {
  const [redFiltro, setRedFiltro] = React.useState(RED_TODAS);
  // TODAS las redes canónicas en el selector (no solo las que traen datos): el operador
  // puede enfocar cualquiera y, si no tiene datos en el rango, la tabla lo dice con "—".
  const redesDisponibles = REDES_CANONICAS;

  // Filas tras aplicar el filtro de red (cliente). `visibles` alimenta orden, totales y reparto.
  const visibles = redFiltro === RED_TODAS ? redes : redes.filter((r) => r.red === redFiltro);

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<RedMetrica, ClaveRed>(
    visibles,
    ACCESORES,
  );

  const totales = calcularTotales(visibles);

  // "Todas las tablas, todas las redes": además de las filas con datos (ya ordenadas),
  // pintamos una fila "—" por cada red canónica que no aparezca en el periodo —incluida X,
  // que en el piloto no está contratada en Metricool—. Así ninguna red desaparece.
  const objetivoRedes =
    redFiltro === RED_TODAS ? REDES_CANONICAS : REDES_CANONICAS.filter((r) => r === redFiltro);
  const conDatos = new Set(visibles.map((r) => redCanonica(r.red)));
  const redesFaltantes = objetivoRedes.filter((r) => !conDatos.has(r));

  const filtroRed = (
    <Select value={redFiltro} onValueChange={setRedFiltro}>
      <SelectTrigger className="w-full sm:w-44" aria-label="Filtrar por red">
        <SelectValue placeholder="Red" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={RED_TODAS}>Todas las redes</SelectItem>
        {redesDisponibles.map((r) => (
          <SelectItem key={r} value={r}>
            {nombreRed(r)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const cuerpo = (
      <>
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
            {/* Redes sin datos en el periodo: fila presente con "—" (no se omiten). */}
            {redesFaltantes.map((red) => (
              <TableRow key={red} className="text-muted-foreground">
                <TableCell className="pl-6 font-medium">{nombreRed(red)}</TableCell>
                {COLUMNAS.map((c) => (
                  <TableCell key={c.clave} className="pr-6 text-right tabular-nums last:pr-6">
                    —
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {visibles.length > 0 && (
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
            )}
          </TableBody>
        </Table>
      </>
  );

  if (desnudo) {
    return (
      <div className="space-y-3">
        <div className="flex justify-end">{filtroRed}</div>
        {cuerpo}
      </div>
    );
  }
  return (
    <SeccionColapsable titulo="Detalle por red" acciones={filtroRed} contentClassName="p-0">
      {cuerpo}
    </SeccionColapsable>
  );
}

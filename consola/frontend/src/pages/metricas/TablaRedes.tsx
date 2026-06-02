/**
 * Tabla por red: una fila por plataforma con las métricas agregadas de TODAS las
 * marcas del reporte (espejo de `TablaCuentas`, pero por red en vez de por marca).
 *
 * El backend (`/api/metricas/reporte` › `por_red`) suma `por_plataforma` de cada
 * cuenta por plataforma; cuando hay una marca filtrada, el reporte solo trae sus
 * cuentas, así que esta tabla queda acotada a esa marca (deseado). Las columnas
 * numéricas van alineadas a la derecha con cifras tabulares para la lectura
 * comparada. `alcance` es `null` cuando ninguna cuenta mide alcance en esa red
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
import { numeroCompleto, porcentaje } from "@/lib/formato";
import type { RedMetrica } from "@/types";

/**
 * Nombre legible de una red a partir de su id de plataforma (`red`). El backend
 * emite el id crudo (p. ej. `instagram`, `tiktok`); aquí lo traducimos a su forma
 * de marca. Para ids desconocidos, capitaliza la primera letra (degradación honesta,
 * sin inventar un nombre).
 */
const NOMBRES_RED: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
  youtube: "YouTube",
  x: "X",
  twitter: "X",
  linkedin: "LinkedIn",
  threads: "Threads",
};

function nombreRed(red: string): string {
  const conocida = NOMBRES_RED[red.toLowerCase()];
  if (conocida) return conocida;
  return red ? red.charAt(0).toUpperCase() + red.slice(1) : "—";
}

/** Columnas numéricas en el mismo orden y formato que la tabla por marca. */
const COLUMNAS: Array<{
  clave: "visualizaciones" | "alcance" | "interacciones" | "engagement_pct";
  etiqueta: string;
}> = [
  { clave: "visualizaciones", etiqueta: "Vistas" },
  { clave: "alcance", etiqueta: "Alcance" },
  { clave: "interacciones", etiqueta: "Interacciones" },
  { clave: "engagement_pct", etiqueta: "Engagement" },
];

/** Formatea el valor de una columna; `alcance` null se muestra "—" (no es un 0 real). */
function valorCelda(r: RedMetrica, clave: (typeof COLUMNAS)[number]["clave"]): string {
  if (clave === "alcance") {
    return r.alcance == null ? "—" : numeroCompleto(r.alcance);
  }
  if (clave === "engagement_pct") {
    return porcentaje(r.engagement_pct);
  }
  return numeroCompleto(r[clave]);
}

export function TablaRedes({ redes }: { redes: RedMetrica[] }) {
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
                <TableHead key={c.clave} className="pr-6 text-right last:pr-6">
                  {c.etiqueta}
                </TableHead>
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
              redes.map((r) => (
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
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

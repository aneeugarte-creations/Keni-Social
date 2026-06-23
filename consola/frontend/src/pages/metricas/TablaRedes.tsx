/**
 * Tabla por red: una fila por plataforma con las métricas agregadas de TODAS las
 * marcas del reporte (espejo de `TablaCuentas`, pero por red en vez de por marca).
 *
 * El backend (`/api/metricas/reporte` › `por_red`) suma `por_plataforma` de cada
 * cuenta por plataforma; cuando hay una marca filtrada, el reporte solo trae sus
 * cuentas, así que esta tabla queda acotada a esa marca (deseado). Las columnas
 * numéricas van alineadas a la derecha con cifras tabulares para la lectura
 * comparada y son ORDENABLES (clic en la cabecera). Qué columnas se ven y en qué
 * orden lo decide el panel "Configurar vista" (`vistaConfig.columnas.redes`). Al pie,
 * una fila de TOTALES. Cada red canónica sin datos aparece igualmente como fila con
 * "—" (incluida X, no contratada en el piloto), nunca un 0 falso.
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
import { idsColumnas, TABLA_REDES } from "./columnasMeta";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

const RED_TODAS = "__todas__";

type ClaveRed = "visualizaciones" | "alcance" | "interacciones" | "engagement_pct";

/** Etiqueta legible de cada columna numérica (misma forma que la tabla por marca). */
const ETIQUETA_METRICA: Record<ClaveRed, string> = {
  visualizaciones: "Vistas",
  alcance: "Alcance",
  interacciones: "Interacciones",
  engagement_pct: "Engagement",
};

/** Accesores de ordenación (constante de módulo: identidad estable para el useMemo del hook).
 * El alcance es `null` cuando la red no lo mide (TikTok/YouTube); a efectos de orden vale 0. */
const ACCESORES: Record<ClaveRed, (r: RedMetrica) => number> = {
  visualizaciones: (r) => r.visualizaciones,
  alcance: (r) => r.alcance ?? 0,
  interacciones: (r) => r.interacciones,
  engagement_pct: (r) => r.engagement_pct,
};

const IDS_BASE = idsColumnas(TABLA_REDES);

/** Formatea el valor de una columna. El alcance `null` (red que no lo mide) se pinta "—". */
function valorCelda(r: RedMetrica, clave: ClaveRed): string {
  if (clave === "engagement_pct") {
    return porcentaje(r.engagement_pct);
  }
  if (clave === "alcance") {
    return r.alcance === null ? "—" : numeroCompleto(r.alcance);
  }
  return numeroCompleto(r[clave]);
}

/** Totales del periodo por red: suma de las brutas + engagement global derivado.
 * `alcance` suma solo las redes que lo miden; `null` si ninguna lo hace (no se inventa 0). */
function calcularTotales(redes: RedMetrica[]): {
  visualizaciones: number;
  alcance: number | null;
  interacciones: number;
  engagement_pct: number;
} {
  const visualizaciones = redes.reduce((s, r) => s + r.visualizaciones, 0);
  const interacciones = redes.reduce((s, r) => s + r.interacciones, 0);
  const conAlcance = redes.filter((r) => r.alcance !== null);
  const alcance = conAlcance.length > 0 ? conAlcance.reduce((s, r) => s + (r.alcance ?? 0), 0) : null;
  const engagement_pct = visualizaciones > 0 ? (interacciones / visualizaciones) * 100 : 0;
  return { visualizaciones, alcance, interacciones, engagement_pct };
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

  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_REDES]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);

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

  const encabezado = (id: string) => {
    if (id === "red") {
      return (
        <TableHead key={id} className="pl-6">
          Red
        </TableHead>
      );
    }
    const clave = id as ClaveRed;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear="right"
        className="pr-6 last:pr-6"
      >
        {ETIQUETA_METRICA[clave]}
      </CabeceraOrdenable>
    );
  };

  const celda = (r: RedMetrica, id: string) => {
    if (id === "red") {
      return (
        <TableCell key={id} className="pl-6 font-medium">
          {nombreRed(r.red)}
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className="pr-6 text-right tabular-nums last:pr-6">
        {valorCelda(r, id as ClaveRed)}
      </TableCell>
    );
  };

  const celdaFaltante = (red: string, id: string) => {
    if (id === "red") {
      return (
        <TableCell key={id} className="pl-6 font-medium">
          {nombreRed(red)}
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className="pr-6 text-right tabular-nums last:pr-6">
        —
      </TableCell>
    );
  };

  const celdaTotal = (id: string) => {
    if (id === "red") {
      return (
        <TableCell key={id} className="pl-6">
          Total
        </TableCell>
      );
    }
    let contenido: string;
    if (id === "engagement_pct") {
      contenido = porcentaje(totales.engagement_pct);
    } else if (id === "alcance") {
      contenido = totales.alcance === null ? "—" : numeroCompleto(totales.alcance);
    } else {
      contenido = numeroCompleto(totales[id as "visualizaciones" | "interacciones"]);
    }
    return (
      <TableCell key={id} className="pr-6 text-right tabular-nums last:pr-6">
        {contenido}
      </TableCell>
    );
  };

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
    <Table>
      <TableHeader>
        <TableRow>{columnas.map(encabezado)}</TableRow>
      </TableHeader>
      <TableBody>
        {filasOrdenadas.map((r) => (
          <TableRow key={r.red}>{columnas.map((id) => celda(r, id))}</TableRow>
        ))}
        {/* Redes sin datos en el periodo: fila presente con "—" (no se omiten). */}
        {redesFaltantes.map((red) => (
          <TableRow key={red} className="text-muted-foreground">
            {columnas.map((id) => celdaFaltante(red, id))}
          </TableRow>
        ))}
        {visibles.length > 0 && (
          <TableRow className="border-t-2 font-medium">{columnas.map(celdaTotal)}</TableRow>
        )}
      </TableBody>
    </Table>
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

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
 * una fila de TOTALES. El foco de red lo manda el selector GLOBAL: solo se muestran las
 * redes seleccionadas; una en foco sin datos aparece como fila "—" (nunca un 0 falso),
 * y una fuera del foco no se muestra.
 */
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  nombreRed,
  numeroCompleto,
  porcentaje,
  redCanonica,
  redEnFoco,
  redesObjetivo,
} from "@/lib/formato";
import type { RedMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { idsColumnas, TABLA_REDES } from "./columnasMeta";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

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
  // El foco de red lo manda el selector GLOBAL de la cabecera (`vistaConfig.red`): no hay
  // filtro de red propio de la tabla (uno solo, no varios que confundan).
  const red = useVistaConfig((s) => s.red);

  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_REDES]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);

  // Filas tras aplicar el foco de red global. `visibles` alimenta orden, totales y reparto.
  const visibles = redes.filter((r) => redEnFoco(red, r.red));

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<RedMetrica, ClaveRed>(
    visibles,
    ACCESORES,
  );

  const totales = calcularTotales(visibles);

  // Las redes EN FOCO sin datos en el periodo se pintan igualmente como fila "—" (no
  // desaparecen); las redes fuera del foco no se muestran en absoluto.
  const conDatos = new Set(visibles.map((r) => redCanonica(r.red)));
  const redesFaltantes = redesObjetivo(red).filter((r) => !conDatos.has(r));

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
    return cuerpo;
  }
  return (
    <SeccionColapsable titulo="Detalle por red" contentClassName="p-0">
      {cuerpo}
    </SeccionColapsable>
  );
}

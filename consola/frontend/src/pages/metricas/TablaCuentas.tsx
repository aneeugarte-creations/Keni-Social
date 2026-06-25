/**
 * Tabla por cuenta: una fila por cuenta con sus métricas bien formateadas.
 *
 * Las columnas numéricas van alineadas a la derecha con cifras tabulares para
 * facilitar la lectura comparada entre filas, y son ORDENABLES (clic en la
 * cabecera, asc/desc con indicador visual). Qué columnas se ven y en qué orden lo
 * decide el panel "Configurar vista" (`vistaConfig.columnas.cuentas`); la ordenación
 * por columna es independiente. Al pie, una fila de TOTALES: suma de
 * vistas/interacciones y engagement global (interacciones ÷ vistas). Cada fila ofrece
 * además, en su menú de acciones (kebab / click derecho), "Generar copy", que abre esa
 * marca ya preseleccionada en Generar copy.
 */
import { Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { marcaCanonicaDesdeMetricas } from "@/components/comunes/selectores";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { numeroCompleto, porcentaje } from "@/lib/formato";
import type { CuentaMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { idsColumnas, metaColumnas, TABLA_CUENTAS } from "./columnasMeta";
import { PieMostrarMas } from "./PieMostrarMas";
import { Seccion } from "./Seccion";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

type ClaveCuenta = "visualizaciones" | "impresiones" | "interacciones" | "engagement_pct";

/** Etiqueta legible de cada columna numérica. El VOLUMEN por marca son las impresiones
 * (aditivas, sumables); el alcance único no es agregable por cuenta y se lee como tendencia
 * en su propia sección, no aquí. */
const ETIQUETA_METRICA: Record<ClaveCuenta, string> = {
  visualizaciones: "Vistas",
  impresiones: "Impresiones",
  interacciones: "Interacciones",
  engagement_pct: "Engagement",
};

/** Accesores de ordenación (constante de módulo: identidad estable para el useMemo del hook). */
const ACCESORES: Record<ClaveCuenta, (c: CuentaMetrica) => number> = {
  visualizaciones: (c) => c.visualizaciones,
  impresiones: (c) => c.impresiones,
  interacciones: (c) => c.interacciones,
  engagement_pct: (c) => c.engagement_pct,
};

const IDS_BASE = idsColumnas(TABLA_CUENTAS);

/** Formatea el valor de una columna. */
function valorCelda(c: CuentaMetrica, clave: ClaveCuenta): string {
  if (clave === "engagement_pct") {
    return porcentaje(c.engagement_pct);
  }
  return numeroCompleto(c[clave]);
}

/** Totales del periodo: suma de las métricas brutas + engagement global derivado. */
function calcularTotales(cuentas: CuentaMetrica[]): {
  visualizaciones: number;
  impresiones: number;
  interacciones: number;
  engagement_pct: number;
} {
  const visualizaciones = cuentas.reduce((s, c) => s + c.visualizaciones, 0);
  const impresiones = cuentas.reduce((s, c) => s + c.impresiones, 0);
  const interacciones = cuentas.reduce((s, c) => s + c.interacciones, 0);
  // Engagement global = interacciones totales ÷ vistas totales (no la media de %).
  const engagement_pct = visualizaciones > 0 ? (interacciones / visualizaciones) * 100 : 0;
  return { visualizaciones, impresiones, interacciones, engagement_pct };
}

export function TablaCuentas({
  cuentas,
  onVerPiezas,
}: {
  cuentas: CuentaMetrica[];
  /** Drill-down: ver las piezas de esta marca (id crudo de métricas). */
  onVerPiezas?: (marcaId: string) => void;
}) {
  const navigate = useNavigate();

  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_CUENTAS]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CuentaMetrica, ClaveCuenta>(
    cuentas,
    ACCESORES,
  );

  const totales = calcularTotales(cuentas);

  // Recorte a 5 filas (sobre el conjunto YA ORDENADO): el "top 5" sigue el orden activo.
  const { visibles, expandido, alternar, hayMas } = useFilasPlegables(filasOrdenadas, 5);

  const encabezado = (id: string) => {
    if (id === "marca") {
      return (
        <TableHead key={id} className="pl-6">
          Marca
        </TableHead>
      );
    }
    const clave = id as ClaveCuenta;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear="right"
      >
        {ETIQUETA_METRICA[clave]}
      </CabeceraOrdenable>
    );
  };

  const celda = (c: CuentaMetrica, id: string) => {
    if (id === "marca") {
      return (
        <TableCell key={id} className="pl-6 font-medium">
          {onVerPiezas ? (
            <button
              type="button"
              onClick={() => onVerPiezas(c.marca_id)}
              className="text-left underline-offset-4 hover:underline focus-visible:outline-none focus-visible:underline"
              title={`Ver piezas de ${c.marca}`}
            >
              {c.marca}
            </button>
          ) : (
            c.marca
          )}
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className="text-right tabular-nums">
        {valorCelda(c, id as ClaveCuenta)}
      </TableCell>
    );
  };

  const celdaTotal = (id: string) => {
    if (id === "marca") {
      return (
        <TableCell key={id} className="pl-6">
          Total
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className="text-right tabular-nums">
        {id === "engagement_pct"
          ? porcentaje(totales.engagement_pct)
          : numeroCompleto(totales[id as "visualizaciones" | "impresiones" | "interacciones"])}
      </TableCell>
    );
  };

  const tabla = (
    <Table>
      <TableHeader>
        <TableRow>{columnas.map(encabezado)}</TableRow>
      </TableHeader>
      <TableBody>
        {cuentas.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={columnas.length}
              className="py-8 text-center text-muted-foreground"
            >
              No hay marcas para mostrar en este periodo.
            </TableCell>
          </TableRow>
        ) : (
          <>
            {visibles.map((c) => {
              const acciones: EntradaMenuContextual[] = [
                {
                  etiqueta: "Generar copy",
                  icono: Sparkles,
                  onClick: () =>
                    navigate("/generacion", {
                      state: { marca: marcaCanonicaDesdeMetricas(c.marca_id) },
                    }),
                },
              ];
              return (
                <FilaConAcciones
                  key={c.marca_id}
                  como="tr"
                  acciones={acciones}
                  etiquetaAcciones={`Acciones de ${c.marca}`}
                  kebab="nunca"
                >
                  {columnas.map((id) => celda(c, id))}
                </FilaConAcciones>
              );
            })}
            {/* Fila de totales: suma de las brutas + engagement global derivado. */}
            <TableRow className="border-t-2 font-medium">{columnas.map(celdaTotal)}</TableRow>
          </>
        )}
      </TableBody>
      {hayMas && (
        <PieMostrarMas
          expandido={expandido}
          onAlternar={alternar}
          colSpan={columnas.length}
        />
      )}
    </Table>
  );

  return (
    <Seccion
      id="marca-detalle"
      titulo="Detalle por marca"
      tablaId={TABLA_CUENTAS}
      columnas={metaColumnas(TABLA_CUENTAS)}
    >
      <Card className="overflow-hidden py-2">{tabla}</Card>
    </Seccion>
  );
}

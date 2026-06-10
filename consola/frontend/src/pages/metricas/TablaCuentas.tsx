/**
 * Tabla por cuenta: una fila por cuenta con las cuatro métricas bien formateadas.
 *
 * Las columnas numéricas van alineadas a la derecha con cifras tabulares para
 * facilitar la lectura comparada entre filas, y son ORDENABLES (clic en la
 * cabecera, asc/desc con indicador visual). Al pie, una fila de TOTALES: suma de
 * vistas/alcance/interacciones y engagement global (interacciones ÷ vistas). Cada
 * fila ofrece además, en su menú de acciones (kebab / click derecho), "Generar
 * copy", que abre esa marca ya preseleccionada en Generar copy.
 */
import { Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { marcaCanonicaDesdeMetricas } from "@/components/comunes/selectores";
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
import { METRICAS, valorMetrica, type ClaveMetrica } from "./metricas-meta";
import { PieMostrarMas } from "./PieMostrarMas";
import { SeccionColapsable } from "./SeccionColapsable";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";

/** Accesores de ordenación (constante de módulo: identidad estable para el useMemo del hook). */
const ACCESORES: Record<ClaveMetrica, (c: CuentaMetrica) => number> = {
  visualizaciones: (c) => c.visualizaciones,
  interacciones: (c) => c.interacciones,
  engagement_pct: (c) => c.engagement_pct,
};

/** Totales del periodo: suma de las métricas brutas + engagement global derivado. */
function calcularTotales(cuentas: CuentaMetrica[]): {
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
} {
  const visualizaciones = cuentas.reduce((s, c) => s + c.visualizaciones, 0);
  const interacciones = cuentas.reduce((s, c) => s + c.interacciones, 0);
  // Engagement global = interacciones totales ÷ vistas totales (no la media de %).
  const engagement_pct = visualizaciones > 0 ? (interacciones / visualizaciones) * 100 : 0;
  return { visualizaciones, interacciones, engagement_pct };
}

export function TablaCuentas({
  cuentas,
  onVerPiezas,
  desnudo = false,
}: {
  cuentas: CuentaMetrica[];
  /** Drill-down: ver las piezas de esta marca (id crudo de métricas). */
  onVerPiezas?: (marcaId: string) => void;
  /**
   * `true` => renderiza SOLO la tabla (sin el `SeccionColapsable` de título/recuadro), para
   * mostrarla directamente bajo el gráfico de "Por marca". Mantiene el recorte a 5 filas +
   * "Mostrar más".
   */
  desnudo?: boolean;
}) {
  const navigate = useNavigate();

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CuentaMetrica, ClaveMetrica>(
    cuentas,
    ACCESORES,
  );

  const totales = calcularTotales(cuentas);

  // Recorte a 5 filas (sobre el conjunto YA ORDENADO): el "top 5" sigue el orden activo.
  const { visibles, expandido, alternar, hayMas } = useFilasPlegables(filasOrdenadas, 5);

  const tabla = (
      <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Marca</TableHead>
              {METRICAS.map((m) => (
                <CabeceraOrdenable
                  key={m.clave}
                  activa={estado.clave === m.clave}
                  direccion={estado.direccion}
                  onClick={() => alClicar(m.clave)}
                  alinear="right"
                >
                  {m.etiqueta}
                </CabeceraOrdenable>
              ))}
              <TableHead className="w-10 pr-6">
                <span className="sr-only">Acciones</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cuentas.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={METRICAS.length + 2}
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
                      kebab="siempre"
                      claseKebab="pr-6"
                    >
                      <TableCell className="pl-6 font-medium">
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
                      {METRICAS.map((m) => (
                        <TableCell key={m.clave} className="text-right tabular-nums">
                          {m.completo(valorMetrica(c, m.clave))}
                        </TableCell>
                      ))}
                    </FilaConAcciones>
                  );
                })}
                {/* Fila de totales: suma de las brutas + engagement global derivado. */}
                <TableRow className="border-t-2 font-medium">
                  <TableCell className="pl-6">Total</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(totales.visualizaciones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(totales.interacciones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {porcentaje(totales.engagement_pct)}
                  </TableCell>
                  <TableCell className="pr-6" />
                </TableRow>
              </>
            )}
          </TableBody>
          {hayMas && (
            <PieMostrarMas
              expandido={expandido}
              onAlternar={alternar}
              colSpan={METRICAS.length + 2}
            />
          )}
        </Table>
  );

  if (desnudo) return tabla;
  return (
    <SeccionColapsable titulo="Detalle por marca" contentClassName="p-0">
      {tabla}
    </SeccionColapsable>
  );
}

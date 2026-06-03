/**
 * Mejores días y horas para publicar (estrategia digital).
 *
 * Un HEATMAP día-de-la-semana × hora: 7 filas (Lun..Dom) × 24 columnas (00..23). Cada
 * celda agrega las piezas publicadas en esa franja del periodo y se colorea por su
 * engagement (o por sus vistas, con un toggle) para leer de un vistazo CUÁNDO conviene
 * publicar. La celda con mejor rendimiento (`mejor`, con un mínimo de piezas) se resalta.
 *
 * Estados honestos (carga / vacío / error) como el resto de Métricas: las piezas sin hora
 * de publicación se OMITEN aguas arriba, así que si la fuente no aporta hora el heatmap
 * sale vacío y lo decimos, en vez de inventar la medianoche.
 */
import { useQuery } from "@tanstack/react-query";
import { Clock } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { numeroCompacto, porcentaje } from "@/lib/formato";
import type { CeldaHorario } from "@/types";

import { MARCA_TODAS } from "./Controles";

// Etiquetas de los días en español, indexadas por `date.weekday()` (0=lunes..6=domingo).
const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const HORAS = Array.from({ length: 24 }, (_, h) => h);

// Métrica que pinta el color del heatmap.
type Metrica = "engagement" | "vistas";

function valorCelda(c: CeldaHorario, metrica: Metrica): number {
  return metrica === "engagement" ? c.engagement_pct : c.visualizaciones;
}

/**
 * Intensidad 0..1 de una celda respecto al máximo del heatmap (escala lineal). Una
 * celda sin datos (no presente) no llama a esto: se pinta en gris.
 */
function intensidad(valor: number, maximo: number): number {
  if (maximo <= 0) return 0;
  return Math.min(1, valor / maximo);
}

/**
 * Color de fondo de una celda según su intensidad. Mezcla una base translúcida para
 * que el gradiente sea legible en claro y oscuro (más intenso = más fuerte).
 */
function estiloCelda(t: number): React.CSSProperties {
  // 0.08..0.95 de opacidad: incluso una celda con datos bajos se distingue del gris.
  const alpha = 0.08 + t * 0.87;
  return { backgroundColor: `rgba(16, 185, 129, ${alpha.toFixed(3)})` };
}

function dosDigitos(n: number): string {
  return n.toString().padStart(2, "0");
}

export function MejoresHorarios({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const [metrica, setMetrica] = React.useState<Metrica>("engagement");

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "horarios", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasHorarios({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <CardTitle className="text-base">Mejores horas y días para publicar</CardTitle>
          </div>
          <div className="flex gap-1" role="group" aria-label="Métrica del mapa de calor">
            <Button
              type="button"
              size="sm"
              variant={metrica === "engagement" ? "default" : "outline"}
              onClick={() => setMetrica("engagement")}
            >
              Engagement
            </Button>
            <Button
              type="button"
              size="sm"
              variant={metrica === "vistas" ? "default" : "outline"}
              onClick={() => setMetrica("vistas")}
            >
              Vistas
            </Button>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          Mapa de calor día × hora del periodo: cada celda agrega las piezas publicadas en
          esa franja. Cuanto más intenso, mejor rinde. Las piezas sin hora de publicación
          se omiten.
        </p>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-64 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudieron cargar los mejores horarios.
          </p>
        ) : data.celdas.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            La fuente activa no aporta la hora de publicación para este periodo.
          </p>
        ) : (
          <Heatmap celdas={data.celdas} mejor={data.mejor} metrica={metrica} />
        )}
      </CardContent>
    </Card>
  );
}

function Heatmap({
  celdas,
  mejor,
  metrica,
}: {
  celdas: CeldaHorario[];
  mejor: CeldaHorario | null;
  metrica: Metrica;
}) {
  // Índice (dia*24+hora) -> celda, para un acceso O(1) al pintar la rejilla 7×24.
  const porClave = new Map<number, CeldaHorario>();
  for (const c of celdas) porClave.set(c.dia_semana * 24 + c.hora, c);
  const maximo = Math.max(...celdas.map((c) => valorCelda(c, metrica)), 0);
  const esMejor = (dia: number, hora: number) =>
    mejor != null && mejor.dia_semana === dia && mejor.hora === hora;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5" aria-label="Mapa de calor de horarios">
          <thead>
            <tr>
              <th className="w-10" aria-hidden="true" />
              {HORAS.map((h) => (
                <th
                  key={h}
                  className="px-0 text-center text-[10px] font-normal text-muted-foreground tabular-nums"
                >
                  {dosDigitos(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DIAS.map((nombreDia, dia) => (
              <tr key={dia}>
                <th
                  scope="row"
                  className="pr-2 text-right text-xs font-medium text-muted-foreground"
                >
                  {nombreDia}
                </th>
                {HORAS.map((hora) => {
                  const c = porClave.get(dia * 24 + hora);
                  const resaltada = esMejor(dia, hora);
                  if (!c) {
                    return (
                      <td key={hora} className="p-0">
                        <div
                          className="h-6 w-6 rounded-sm bg-muted/40"
                          title={`${nombreDia} ${dosDigitos(hora)}:00 — sin piezas`}
                        />
                      </td>
                    );
                  }
                  const t = intensidad(valorCelda(c, metrica), maximo);
                  const titulo =
                    `${nombreDia} ${dosDigitos(hora)}:00 — ${c.n_piezas} ` +
                    `pieza${c.n_piezas === 1 ? "" : "s"}, ` +
                    `${numeroCompacto(c.visualizaciones)} vistas, ` +
                    `${porcentaje(c.engagement_pct)} eng.`;
                  return (
                    <td key={hora} className="p-0">
                      <div
                        className={cn(
                          "h-6 w-6 rounded-sm",
                          resaltada && "ring-2 ring-offset-1 ring-amber-500 dark:ring-offset-background",
                        )}
                        style={estiloCelda(t)}
                        title={titulo}
                        data-mejor={resaltada ? "true" : undefined}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {mejor != null ? (
        <p className="text-sm text-muted-foreground">
          Mejor franja:{" "}
          <span className="font-medium text-foreground">
            {DIAS[mejor.dia_semana]} {dosDigitos(mejor.hora)}:00
          </span>{" "}
          — {porcentaje(mejor.engagement_pct)} de engagement sobre {mejor.n_piezas}{" "}
          pieza{mejor.n_piezas === 1 ? "" : "s"}.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Aún no hay una franja con piezas suficientes para destacarla como la mejor.
        </p>
      )}
    </div>
  );
}

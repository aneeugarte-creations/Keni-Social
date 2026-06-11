/**
 * RendimientoFuentes — evaluación EDITORIAL de las fuentes (¿cuáles aportan de verdad?).
 *
 * Tabla por fuente sobre la ventana elegida (7/30 días): artículos aportados, historias en
 * las que participó, cuántas ABRIÓ (publicó primero — la fuente que rompe), cuántas acabaron
 * usadas (promovidas al tablero) y su tasa de uso. Con esto el equipo decide qué fuentes
 * sobran y dónde faltan. Marca-aware.
 */

import { useQuery } from "@tanstack/react-query";
import { TrendingUp } from "lucide-react";
import * as React from "react";

import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";

export function RendimientoFuentes() {
  const { marcaActiva } = useMarcaActiva();
  const [dias, setDias] = React.useState(7);

  const query = useQuery({
    queryKey: ["noticias", "fuentes-stats", marcaActiva ?? "", dias],
    queryFn: ({ signal }) =>
      api.noticias.statsFuentes({ marca: marcaActiva ?? undefined, dias }, signal),
    staleTime: 60_000,
  });

  const fuentes = query.data?.fuentes ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <TrendingUp className="h-4 w-4" />
          Rendimiento por fuente
        </CardTitle>
        <Select value={String(dias)} onValueChange={(v) => setDias(Number(v))}>
          <SelectTrigger className="w-32" aria-label="Ventana de días">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 días</SelectItem>
            <SelectItem value="30">30 días</SelectItem>
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent>
        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            {mensajeError(query.error)}
          </p>
        ) : fuentes.length === 0 ? (
          <EstadoVacioTexto
            texto="Sin datos en esta ventana aún."
            className="py-4"
          />
        ) : (
          <>
            <Table data-testid="tabla-rendimiento">
              <TableHeader>
                <TableRow>
                  <TableHead>Fuente</TableHead>
                  <TableHead className="text-right">Artículos</TableHead>
                  <TableHead className="text-right">Historias</TableHead>
                  <TableHead className="text-right" title="Historias que esta fuente publicó primero">
                    Abrió
                  </TableHead>
                  <TableHead className="text-right" title="Historias suyas que acabaron en el tablero">
                    Usadas
                  </TableHead>
                  <TableHead className="text-right">% uso</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fuentes.map((f) => (
                  <TableRow key={f.fuente_id}>
                    <TableCell className="max-w-64">
                      <span className="truncate font-medium">{f.fuente_nombre || f.fuente_id}</span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{f.items}</TableCell>
                    <TableCell className="text-right tabular-nums">{f.historias}</TableCell>
                    <TableCell className="text-right tabular-nums">{f.primeras}</TableCell>
                    <TableCell className="text-right tabular-nums">{f.usadas}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Math.round((f.tasa_uso ?? 0) * 100)}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-2 text-[11px] text-muted-foreground">
              «Abrió» = primer medio. «% uso» = tasa de uso en tablero.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

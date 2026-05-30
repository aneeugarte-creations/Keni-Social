/**
 * Tabla por cuenta: una fila por cuenta con las cuatro métricas bien formateadas.
 *
 * Las columnas numéricas van alineadas a la derecha con cifras tabulares para
 * facilitar la lectura comparada entre filas. Cada fila ofrece además un enlace
 * "Generar copy" que abre esa marca ya preseleccionada en Generar copy.
 */
import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { marcaCanonicaDesdeMetricas } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CuentaMetrica } from "@/types";

import { METRICAS, valorMetrica } from "./metricas-meta";

export function TablaCuentas({ cuentas }: { cuentas: CuentaMetrica[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Detalle por cuenta</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Cuenta</TableHead>
              {METRICAS.map((m) => (
                <TableHead key={m.clave} className="text-right">
                  {m.etiqueta}
                </TableHead>
              ))}
              <TableHead className="pr-6 text-right">
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
                  No hay cuentas para mostrar en este rango.
                </TableCell>
              </TableRow>
            ) : (
              cuentas.map((c) => (
                <TableRow key={c.marca_id}>
                  <TableCell className="pl-6 font-medium">{c.marca}</TableCell>
                  {METRICAS.map((m) => (
                    <TableCell key={m.clave} className="text-right tabular-nums">
                      {m.completo(valorMetrica(c, m.clave))}
                    </TableCell>
                  ))}
                  <TableCell className="pr-6 text-right">
                    <Button asChild variant="ghost" size="sm" className="h-8">
                      <Link
                        to="/generacion"
                        state={{ marca: marcaCanonicaDesdeMetricas(c.marca_id) }}
                        title={`Generar copy para ${c.marca}`}
                      >
                        <Sparkles className="h-4 w-4" />
                        Generar copy
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

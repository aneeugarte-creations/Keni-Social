import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { iconoPlataforma, nombrePlataforma } from "@/pages/marcas/plataformas";
import { tiempoRelativo } from "@/pages/publicaciones/meta";
import type { ConteoCuenta, NumerosMarca } from "@/types";

const CLAVE_NUMEROS = ["marcas", "numeros"];

/** Entero con separador de miles (es-MX), o «—» si no hay dato (no es 0). */
function fmtEntero(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("es-MX").format(n);
}

/** Decimal con 1 cifra (posts/día), o «—» si no hay dato. */
function fmtDia(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(n);
}

/** Las tres celdas numéricas de una fila (mismo ancho y alineación en todas las filas). */
function CeldasNumero({ c }: { c: ConteoCuenta }) {
  return (
    <>
      <td className="w-32 px-3 py-1.5 text-right tabular-nums">{fmtEntero(c.seguidores)}</td>
      <td className="w-28 px-3 py-1.5 text-right tabular-nums">{fmtEntero(c.posts_totales)}</td>
      <td className="w-24 px-3 py-1.5 text-right tabular-nums">{fmtDia(c.posts_dia)}</td>
    </>
  );
}

/** Bloque de una marca: fila de sumatorio (la marca) + una fila por cuenta (red). */
function BloqueMarca({ marca }: { marca: NumerosMarca }) {
  return (
    <>
      {/* Sumatorio de la marca. */}
      <tr className="border-b border-border bg-muted/40 font-medium">
        <td className="py-2 pl-3 pr-2">{marca.etiqueta}</td>
        <CeldasNumero c={marca.total} />
      </tr>
      {/* Una línea por cuenta (red). */}
      {marca.redes.map((red) => {
        const Icono = iconoPlataforma(red.plataforma);
        return (
          <tr key={red.plataforma} className="border-b border-border last:border-0">
            <td className="py-1.5 pl-8 pr-2">
              <span className="flex items-center gap-2 text-muted-foreground">
                <Icono className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {nombrePlataforma(red.plataforma)}
              </span>
            </td>
            <CeldasNumero c={red} />
          </tr>
        );
      })}
    </>
  );
}

/**
 * MONITOR DE NÚMEROS (admin): una lista plana, marca a marca, red a red. Por marca,
 * una fila de sumatorio; debajo, una fila por cuenta con sus números: seguidores,
 * posts totales y posts/día. Solo conteos —sin análisis, sin engagement—; los datos
 * salen de la caché de métricas (instantáneo), la misma que alimenta Analíticas.
 */
export function MonitorNumeros() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_NUMEROS,
    queryFn: ({ signal }) => api.getMarcasNumeros(signal),
  });

  if (isPending) {
    return (
      <Card className="p-4">
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-7 w-full" />
          ))}
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar el monitor de marcas"
        mensaje={mensajeError(error)}
        onReintentar={() => void refetch()}
        cargando={isFetching}
      />
    );
  }

  const vacio = data.marcas.every((m) => m.redes.length === 0);

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
        <p className="text-xs text-muted-foreground">
          {vacio
            ? "Sin cuentas conectadas. Conéctalas en la pestaña «Conexiones»."
            : data.generado_en
              ? `Actualizado ${tiempoRelativo(data.generado_en)}`
              : "Conteos por marca y red (Postproxy)"}
        </p>
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => void refetch()} disabled={isFetching}>
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Actualizar
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="py-2 pl-3 pr-2 text-left font-medium">Cuenta</th>
              <th className="w-32 px-3 py-2 text-right font-medium">Seguidores</th>
              <th className="w-28 px-3 py-2 text-right font-medium">Posts</th>
              <th className="w-24 px-3 py-2 text-right font-medium">Posts/día</th>
            </tr>
          </thead>
          <tbody>
            {data.marcas.map((marca) => (
              <BloqueMarca key={marca.marca} marca={marca} />
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-border font-semibold">
              <td className="py-2 pl-3 pr-2">Total</td>
              <CeldasNumero c={data.totales} />
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}

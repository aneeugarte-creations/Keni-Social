/**
 * Descubrimiento — el canal AUTOMÁTICO de noticias (Google Trends), paralelo a las fuentes
 * manuales (RSS). Un daemon vuelca una muestra de las tendencias —con sus noticias— al pool,
 * que el equipo cura como cualquier otra noticia. No sustituye a las fuentes: descubre temas
 * calientes; para profundizar están los feeds RSS directos.
 *
 * Muestra el estado del canal (activo/geos/intervalo/muestra por tema) y su rendimiento
 * editorial agregado en la ventana (qué aporta de verdad: historias, abrió, usadas). Marca-aware.
 */

import { useQuery } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import * as React from "react";

import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";

/** Una métrica del aporte editorial del canal (etiqueta + valor). */
function Metrica({ etiqueta, valor }: { etiqueta: string; valor: string | number }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <div className="text-2xl font-semibold tabular-nums">{valor}</div>
      <div className="text-xs text-muted-foreground">{etiqueta}</div>
    </div>
  );
}

export function Descubrimiento() {
  const { marcaActiva } = useMarcaActiva();
  const [dias, setDias] = React.useState(7);

  const query = useQuery({
    queryKey: ["noticias", "descubrimiento", marcaActiva ?? "", dias],
    queryFn: ({ signal }) =>
      api.noticias.descubrimiento({ marca: marcaActiva ?? undefined, dias }, signal),
    staleTime: 60_000,
  });

  const data = query.data;
  const stats = data?.stats ?? null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Radar className="h-4 w-4" />
          Google Trends
          {data ? (
            <Badge variant={data.activo ? "default" : "secondary"}>
              {data.activo ? "Activo" : "En pausa"}
            </Badge>
          ) : null}
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
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Canal automático: descubre los temas que suben en búsquedas y vuelca una muestra al
          pool de noticias. No sustituye a tus fuentes; las complementa señalando qué está
          caliente. Cada nota se cura como cualquier otra.
        </p>

        {query.isPending ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[72px] w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            {mensajeError(query.error)}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">
                Geografías: {data?.geos.length ? data.geos.join(", ") : "—"}
              </Badge>
              <Badge variant="outline">Barrido cada {data?.intervalo_min} min</Badge>
              <Badge variant="outline">{data?.max_por_tema} noticias por tema</Badge>
            </div>

            {stats ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metrica etiqueta="Temas aportados" valor={stats.items} />
                <Metrica etiqueta="Historias" valor={stats.historias} />
                <Metrica etiqueta="Abrió (primer medio)" valor={stats.primeras} />
                <Metrica
                  etiqueta="Usadas en tablero"
                  valor={`${stats.usadas} · ${Math.round((stats.tasa_uso ?? 0) * 100)}%`}
                />
              </div>
            ) : (
              <EstadoVacioTexto
                texto={
                  data?.activo
                    ? "Sin aportes en esta ventana aún."
                    : "El canal está en pausa: no ha aportado en esta ventana."
                }
                className="py-4"
              />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

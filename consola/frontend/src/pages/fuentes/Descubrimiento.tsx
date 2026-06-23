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
import { Flame, Radar, TrendingUp } from "lucide-react";
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

/**
 * Lista de TÉRMINOS en tendencia AHORA (en vivo desde Google Trends). Es lo que está sonando este
 * momento, no lo del pool: por eso vive aparte y se recarga con su propio ritmo (5 min).
 */
function ListaTerminos() {
  const query = useQuery({
    queryKey: ["noticias", "descubrimiento", "terminos"],
    queryFn: ({ signal }) => api.noticias.descubrimientoTerminos(signal),
    staleTime: 5 * 60_000,
  });

  const data = query.data;
  const terminos = data?.terminos ?? [];
  const variosGeos = (data?.geos.length ?? 0) > 1;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <TrendingUp className="h-4 w-4" />
          Términos en tendencia ahora
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            {mensajeError(query.error)}
          </p>
        ) : terminos.length === 0 ? (
          <EstadoVacioTexto
            texto="Google Trends no devolvió términos ahora mismo. Reinténtalo en un momento."
            className="py-4"
          />
        ) : (
          <ol className="space-y-2">
            {terminos.map((t, i) => (
              <li
                key={`${t.geo}-${t.termino}`}
                className="rounded-md border p-3"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {i + 1}.
                  </span>
                  <span className="font-medium">{t.termino}</span>
                  {t.trafico ? (
                    <Badge variant="secondary" className="gap-1">
                      <Flame className="h-3 w-3" />
                      {t.trafico}
                    </Badge>
                  ) : null}
                  {variosGeos ? <Badge variant="outline">{t.geo}</Badge> : null}
                </div>
                {t.noticias.length ? (
                  <ul className="mt-1.5 space-y-0.5 pl-6">
                    {t.noticias.map((n) => (
                      <li key={n.url || n.titulo} className="text-xs text-muted-foreground">
                        {n.url ? (
                          <a
                            href={n.url}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:text-foreground hover:underline"
                          >
                            {n.titulo}
                          </a>
                        ) : (
                          <span>{n.titulo}</span>
                        )}
                        {n.fuente ? (
                          <span className="text-muted-foreground/70"> · {n.fuente}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ol>
        )}
        {data?.errores.length ? (
          <p className="text-[11px] text-muted-foreground">
            No se pudo leer: {data.errores.join("; ")}.
          </p>
        ) : null}
      </CardContent>
    </Card>
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
    <div className="space-y-6">
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
    <ListaTerminos />
    </div>
  );
}

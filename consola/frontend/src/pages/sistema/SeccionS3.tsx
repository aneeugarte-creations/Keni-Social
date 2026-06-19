import { useMutation, useQuery } from "@tanstack/react-query";
import { Database, RefreshCw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import type { RespuestaProbarS3, RespuestaS3 } from "@/types";

import { formatoBytes } from "./lib";

/** Badge de salud para el bucket S3. */
function BadgeSalud({ salud }: { salud: RespuestaS3["salud"] }) {
  if (salud === "ok") {
    return <Badge variant="ok">Conectado</Badge>;
  }
  if (salud === "err") {
    return <Badge variant="destructive">Error de conexión</Badge>;
  }
  return <Badge variant="secondary">Sin configurar</Badge>;
}

export function Dato({
  etiqueta,
  valor,
}: {
  etiqueta: string;
  valor: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1 last:border-0">
      <dt className="shrink-0 text-muted-foreground">{etiqueta}</dt>
      <dd className="truncate text-right font-medium tabular-nums">{valor}</dd>
    </div>
  );
}

/** Sección de almacenamiento S3/Garage: estado, uso y prueba de conexión. */
export function SeccionS3() {
  const query = useQuery({
    queryKey: ["sistema", "s3"],
    queryFn: ({ signal }) => api.sistemaS3(signal),
  });

  const probar = useMutation({
    mutationFn: () => api.probarS3(),
    onSuccess: (r: RespuestaProbarS3) => {
      if (r.salud === "ok") {
        toast.success("Conexión con el almacenamiento correcta.");
        void query.refetch();
      } else {
        toast.error(r.error ?? "No se pudo conectar con el almacenamiento.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (query.isPending) {
    return <Skeleton className="h-40 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer el estado del almacenamiento"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const s3 = query.data;
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="flex items-center gap-2">
            <Database className="h-4 w-4" aria-hidden="true" />
            Almacenamiento de objetos (S3 / Garage)
          </span>
          <BadgeSalud salud={s3.salud} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        {!s3.configurado ? (
          <p className="text-sm text-muted-foreground">
            S3 no configurado: media en disco local.
          </p>
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              <Dato etiqueta="Endpoint" valor={s3.endpoint ?? "—"} />
              <Dato etiqueta="Bucket" valor={s3.bucket ?? "—"} />
              <Dato etiqueta="Región" valor={s3.region ?? "—"} />
              <Dato
                etiqueta="Objetos"
                valor={
                  s3.objetos == null
                    ? "—"
                    : `${s3.objetos.toLocaleString("es-MX")}${s3.truncado ? "+" : ""}`
                }
              />
              <Dato etiqueta="Tamaño total" valor={formatoBytes(s3.bytes)} />
            </dl>
            {s3.error && <Aviso>{s3.error}</Aviso>}
            {s3.truncado && (
              <p className="text-xs text-muted-foreground">
                Conteo truncado por volumen: la cifra es un mínimo.
              </p>
            )}
            <div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => probar.mutate()}
                disabled={probar.isPending}
              >
                {probar.isPending ? (
                  <Spinner className="mr-2 h-4 w-4" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
                )}
                Probar conexión
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

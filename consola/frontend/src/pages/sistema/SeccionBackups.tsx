import { useQuery } from "@tanstack/react-query";
import { DatabaseBackup } from "lucide-react";

import { Aviso } from "@/components/comunes/Aviso";
import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";

import { INTERVALO_RECURSOS_MS, formatoBytes } from "./lib";

/**
 * Sección de backups locales del panel Sistema: último run del keni-backup del host
 * (ok/fallo + verificación), edad del último dump y tamaños. Solo observabilidad: el
 * panel no puede tocar los backups (mount de solo lectura).
 */
export function SeccionBackups() {
  const query = useQuery({
    queryKey: ["sistema", "backups"],
    queryFn: ({ signal }) => api.sistemaBackups(signal),
    refetchInterval: INTERVALO_RECURSOS_MS * 4, // cambia como mucho una vez al día
  });

  if (query.isPending) {
    return <Skeleton className="h-32 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer el estado de los backups"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { configurado, estado, dumps, ultimo_dump, atrasado, error } = query.data;

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <DatabaseBackup className="h-4 w-4" aria-hidden="true" />
          Backups locales
          {configurado && (
            <span className="ml-auto flex gap-1.5">
              {atrasado && <Badge variant="error">Atrasado</Badge>}
              {estado &&
                (estado.ok ? (
                  <Badge variant="ok">
                    {estado.verificado ? "OK · verificado" : "OK"}
                  </Badge>
                ) : (
                  <Badge variant="error">Falló: {estado.paso}</Badge>
                ))}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 p-4 pt-0 text-sm">
        {!configurado ? (
          <p className="text-muted-foreground">
            Este despliegue no tiene el directorio de backups montado (solo disponible
            en el servidor hosted).
          </p>
        ) : (
          <>
            {ultimo_dump ? (
              <p className="text-muted-foreground">
                Último dump de Postgres{" "}
                <span className="text-foreground">
                  {tiempoRelativo(ultimo_dump.modificado)}
                </span>{" "}
                · {formatoBytes(ultimo_dump.bytes)} · {dumps} dumps retenidos
              </p>
            ) : (
              <p className="text-destructive">
                No hay ningún dump de Postgres en el directorio de backups.
              </p>
            )}
            {estado && (
              <p className="text-xs text-muted-foreground">
                Último run {estado.stamp} · {Math.round(estado.duracion_seg)} s ·
                volúmenes:{" "}
                {estado.volumenes
                  .map((v) => `${v.volumen} ${formatoBytes(v.bytes)}`)
                  .join(" · ") || "—"}
                {!estado.ok && estado.error && (
                  <span className="text-destructive"> · {estado.error}</span>
                )}
              </p>
            )}
            {error && <Aviso icono={false}>{error}</Aviso>}
          </>
        )}
      </CardContent>
    </Card>
  );
}

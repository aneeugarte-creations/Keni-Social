import { useQuery } from "@tanstack/react-query";
import { DatabaseBackup } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";

import { INTERVALO_RECURSOS_MS, formatoBytes } from "./lib";

function Chip({
  tono,
  children,
}: {
  tono: "ok" | "mal" | "aviso";
  children: React.ReactNode;
}) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-transparent",
        tono === "ok" && "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
        tono === "mal" && "bg-red-500/15 text-red-600 dark:text-red-400",
        tono === "aviso" && "bg-amber-500/15 text-amber-600 dark:text-amber-400",
      )}
    >
      {children}
    </Badge>
  );
}

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
              {atrasado && <Chip tono="mal">Atrasado</Chip>}
              {estado &&
                (estado.ok ? (
                  <Chip tono="ok">
                    {estado.verificado ? "OK · verificado" : "OK"}
                  </Chip>
                ) : (
                  <Chip tono="mal">Falló: {estado.paso}</Chip>
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
              <p className="text-red-500">
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
                  <span className="text-red-500"> · {estado.error}</span>
                )}
              </p>
            )}
            {error && <p className="text-xs text-amber-600">{error}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}

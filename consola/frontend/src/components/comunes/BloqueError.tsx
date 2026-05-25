import { AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Bloque de error reutilizable: icono, título, mensaje en español y botón
 * "Reintentar". Sustituye las copias duplicadas que vivían en Métricas,
 * Publicaciones, Conexiones, Fuentes y Estado.
 *
 * El mensaje cae a un texto genérico si no se proporciona uno.
 */
export function BloqueError({
  titulo,
  mensaje,
  onReintentar,
  cargando = false,
  className,
}: {
  titulo: string;
  mensaje?: string;
  onReintentar: () => void;
  /** Deshabilita el botón y anima el icono mientras se reintenta. */
  cargando?: boolean;
  className?: string;
}) {
  return (
    <Card className={cn("border-destructive/40", className)}>
      <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="h-6 w-6" />
        </div>
        <div className="space-y-1">
          <p className="font-medium">{titulo}</p>
          <p className="max-w-md text-sm text-muted-foreground">
            {mensaje ?? "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."}
          </p>
        </div>
        <Button onClick={onReintentar} disabled={cargando}>
          <RefreshCw className={cn("h-4 w-4", cargando && "animate-spin")} />
          Reintentar
        </Button>
      </CardContent>
    </Card>
  );
}

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
    <Card className={className}>
      <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
        <AlertCircle className="h-6 w-6 text-destructive" aria-hidden="true" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">{titulo}</p>
          <p className="max-w-md text-sm text-muted-foreground">
            {mensaje ?? "Ocurrió un problema. Vuelve a intentarlo."}
          </p>
        </div>
        <Button variant="outline" onClick={onReintentar} disabled={cargando}>
          <RefreshCw className={cn("h-4 w-4", cargando && "animate-spin")} />
          Reintentar
        </Button>
      </CardContent>
    </Card>
  );
}

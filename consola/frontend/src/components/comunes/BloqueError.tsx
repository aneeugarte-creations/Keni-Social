import { AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useConexionDegradada } from "@/lib/estado-red";
import { cn } from "@/lib/utils";

/**
 * Bloque de error reutilizable: icono, título, mensaje en español y botón
 * "Reintentar".
 *
 * El mensaje cae a un texto genérico si no se proporciona uno.
 *
 * NUNCA durante una indisponibilidad del back: si la conexión está degradada (back desplegando/
 * caído), CUALQUIER sección que falle al leer su dato NO debe pintar un error rojo alarmante —el
 * AppShell ya muestra un único velo "Estamos actualizando" sobre el contenido—. Una actualización
 * es esperada, no un fallo; nada de un muro de tarjetas rojas ("No se pudo leer X"). Devolvemos
 * `null` y dejamos que el velo global hable por todas. El error rojo se reserva para fallos REALES
 * de una sección con el back sano.
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
  if (useConexionDegradada()) return null;
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

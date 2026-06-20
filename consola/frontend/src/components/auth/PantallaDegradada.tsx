import { Loader2, RefreshCw } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSesion } from "@/hooks/sesion-contexto";

/** Cada cuánto reintenta el `me` sola la pantalla degradada (ms). */
const INTERVALO_REINTENTO_MS = 5_000;

/**
 * Estado degradado HONESTO del arranque: el `me` inicial falló por algo que NO es "sin
 * sesión" (red caída, timeout, 502/503/504 mientras el back despliega o cae). En vez de
 * un login engañoso, un 502/403 crudo o una ruedita infinita, decimos la verdad —puede
 * estar actualizándose— y reintentamos solos cada pocos segundos, con un botón manual.
 * En cuanto un `me` responde (200 o 401), el provider apaga `errorConexion` y la puerta
 * sale de aquí hacia la app o el login.
 */
export function PantallaDegradada() {
  const { refrescar } = useSesion();
  const [reintentando, setReintentando] = React.useState(false);

  const reintentar = React.useCallback(async () => {
    setReintentando(true);
    try {
      await refrescar();
    } finally {
      setReintentando(false);
    }
  }, [refrescar]);

  // Auto-reintento mientras se muestra esta pantalla: el back puede volver en cualquier
  // momento (fin de un deploy, reinicio); no obligamos al usuario a recargar.
  React.useEffect(() => {
    const id = setInterval(() => {
      void reintentar();
    }, INTERVALO_REINTENTO_MS);
    return () => clearInterval(id);
  }, [reintentar]);

  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Funcionalidad no disponible</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>
            No podemos conectar con la consola. Puede estar actualizándose. Reintentando…
          </p>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={() => void reintentar()}
            disabled={reintentando}
          >
            {reintentando ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <RefreshCw className="h-4 w-4" aria-hidden />
            )}
            Reintentar
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

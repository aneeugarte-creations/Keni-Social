import { AlertTriangle, RefreshCw, RotateCw } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/**
 * Frontera de error (React error boundary): atrapa cualquier excepción lanzada
 * durante el render de una página y muestra un mensaje legible en vez de dejar la
 * app en blanco (React desmonta TODO el árbol si un error escapa sin frontera).
 *
 * Cubre dos casos reales:
 *  - Un `TypeError` en una página (p. ej. acceso a un dato con forma inesperada):
 *    se aísla a esa página; el resto de la consola sigue navegable.
 *  - "Failed to fetch dynamically imported module": ocurre cuando hay un deploy
 *    nuevo mientras la pestaña está abierta y el chunk con hash viejo ya no existe
 *    en el servidor. En ese caso la única salida es recargar (trae el index.html
 *    nuevo), así que ofrecemos un botón de "Recargar la app".
 *
 * El padre debe forzar el remontaje al cambiar de ruta (key={pathname}) para que,
 * tras un error, navegar a otra sección limpie el estado de error.
 */

/** True si el error es un fallo al cargar un chunk lazy (deploy nuevo en curso). */
function esErrorDeChunk(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : String(error ?? "");
  return (
    /dynamically imported module/i.test(msg) ||
    /importing a module script failed/i.test(msg) ||
    /failed to fetch/i.test(msg)
  );
}

interface Props {
  children: React.ReactNode;
}

interface Estado {
  error: Error | null;
}

export class FronteraError extends React.Component<Props, Estado> {
  state: Estado = { error: null };

  static getDerivedStateFromError(error: Error): Estado {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Deja rastro en consola para depurar (Sentry/observabilidad podría engancharse aquí).
    console.error("Frontera de error atrapó una excepción de página:", error, info);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const chunk = esErrorDeChunk(error);
    return (
      <Card className="mx-auto mt-8 max-w-lg">
        <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
          <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden="true" />
          <div className="space-y-1">
            <p className="text-sm font-medium text-foreground">
              {chunk ? "Hay una versión nueva de la consola" : "Esta página tuvo un problema"}
            </p>
            <p className="max-w-md text-sm text-muted-foreground">
              {chunk
                ? "Se publicó una actualización mientras tenías la pestaña abierta. Recarga para cargar la versión nueva."
                : "Algo falló al mostrar esta sección. Puedes reintentar o ir a otra parte de la consola desde el menú."}
            </p>
          </div>
          {chunk ? (
            <Button onClick={() => window.location.reload()}>
              <RotateCw className="h-4 w-4" />
              Recargar la app
            </Button>
          ) : (
            <Button variant="outline" onClick={() => this.setState({ error: null })}>
              <RefreshCw className="h-4 w-4" />
              Reintentar
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }
}

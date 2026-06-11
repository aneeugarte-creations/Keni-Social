import { AlertTriangle, Home, Loader2, RefreshCw, RotateCw } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { recargaSegura } from "@/lib/version";

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
 *    en el servidor. La única salida es recargar (trae el index.html nuevo), así que
 *    lo hacemos AUTOMÁTICAMENTE (`recargaSegura`, con guard anti-bucle). Solo si el
 *    guard sospecha un bucle (recargó hace nada y volvió a fallar) caemos al botón
 *    manual, para no atrapar al usuario en un ciclo de recargas.
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
  /** En un error de chunk: ¿se disparó la recarga automática? (false = guard anti-bucle). */
  recargando: boolean;
}

export class FronteraError extends React.Component<Props, Estado> {
  state: Estado = { error: null, recargando: false };

  static getDerivedStateFromError(error: Error): Estado {
    // Optimista: si es un error de chunk asumimos que vamos a recargar (lo confirma
    // `componentDidCatch`), así el primer render ya muestra "Actualizando…" y no el botón.
    return { error, recargando: esErrorDeChunk(error) };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Deja rastro en consola para depurar (Sentry/observabilidad podría engancharse aquí).
    console.error("Frontera de error atrapó una excepción de página:", error, info);
    // Deploy nuevo: el chunk viejo ya no existe. Recarga sola (trae el index.html nuevo).
    // `recargaSegura` devuelve false si sospecha un bucle: ahí mostramos el botón manual.
    if (esErrorDeChunk(error)) {
      const recargando = recargaSegura();
      if (!recargando) this.setState({ recargando: false });
    }
  }

  render() {
    const { error, recargando } = this.state;
    if (!error) return this.props.children;

    const chunk = esErrorDeChunk(error);

    // Caso normal de deploy: estamos recargando solos. Mensaje breve, sin botón.
    if (chunk && recargando) {
      return (
        <Card className="mx-auto mt-8 max-w-lg">
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">
              Hay una versión nueva de la consola. Actualizando…
            </p>
          </CardContent>
        </Card>
      );
    }

    return (
      <Card className="mx-auto mt-8 max-w-lg">
        <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
          <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden="true" />
          <div className="space-y-1">
            <p className="text-sm font-medium text-foreground">
              {chunk ? "Hay una versión nueva de la consola" : "Algo salió mal"}
            </p>
            <p className="max-w-md text-sm text-muted-foreground">
              {chunk
                ? "Se publicó una actualización mientras tenías la pestaña abierta. Recarga para continuar."
                : "Esta sección tuvo un problema al mostrarse. Puedes reintentar, recargar la consola o volver al feed del equipo."}
            </p>
          </div>
          {chunk ? (
            <Button onClick={() => window.location.reload()}>
              <RotateCw className="h-4 w-4" />
              Recargar
            </Button>
          ) : (
            // Crash de render (no chunk): tres salidas. "Reintentar" remonta los
            // hijos in-place (sirve si el fallo era transitorio); "Recargar" hace
            // una recarga completa (limpia todo el estado del SPA); "Volver al
            // feed" lleva a la home. Usamos un <a> normal (no react-router) porque
            // la frontera está fuera del Router en main.tsx: una navegación dura a
            // la home también limpia el estado de error.
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button
                variant="outline"
                onClick={() => this.setState({ error: null, recargando: false })}
              >
                <RefreshCw className="h-4 w-4" />
                Reintentar
              </Button>
              <Button variant="outline" onClick={() => window.location.reload()}>
                <RotateCw className="h-4 w-4" />
                Recargar
              </Button>
              <Button asChild>
                <a href="/operacion/feed">
                  <Home className="h-4 w-4" />
                  Volver al feed
                </a>
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }
}

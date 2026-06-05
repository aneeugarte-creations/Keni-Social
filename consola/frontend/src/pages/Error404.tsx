import { ArrowLeft, Compass, Home } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/**
 * Página 404: la URL pedida no corresponde a ninguna ruta del SPA. Se renderiza
 * desde el catch-all del router (`path: "*"`) EN LUGAR de rebotar en silencio al
 * feed, para que quede claro que la dirección no existe (typo, enlace viejo no
 * cubierto por una redirección, etc.).
 *
 * Vive dentro del AppShell (sidebar + topbar siguen ahí) y bajo la frontera de
 * error por ruta, así que navegar a otra sección desde aquí limpia el estado.
 */
export default function Error404() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <Card className="mx-auto mt-8 max-w-lg">
      <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
        <Compass className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">Página no encontrada (404)</p>
          <p className="max-w-md text-sm text-muted-foreground">
            No encontramos la página que buscabas. Puede que el enlace esté
            desactualizado o que la dirección tenga un error.
          </p>
          <p className="max-w-md break-all pt-1 font-mono text-xs text-muted-foreground">
            {location.pathname}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button asChild>
            <Link to="/operacion/feed">
              <Home className="h-4 w-4" />
              Volver al feed
            </Link>
          </Button>
          <Button variant="outline" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-4 w-4" />
            Atrás
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

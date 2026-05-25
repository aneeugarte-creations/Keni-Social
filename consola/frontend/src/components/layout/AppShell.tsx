import { Loader2, Menu, X } from "lucide-react";
import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Sidebar } from "@/components/layout/Sidebar";
import { Wordmark } from "@/components/layout/Wordmark";
import { NAVEGACION } from "@/components/layout/navegacion";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Fallback mientras se descarga el chunk de una pagina (lazy/Suspense). */
function CargandoPagina() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin" aria-label="Cargando" />
    </div>
  );
}

/** Busca la etiqueta de la ruta activa para mostrarla como titulo en la topbar. */
function tituloDeRuta(pathname: string): string {
  for (const grupo of NAVEGACION) {
    const item = grupo.items.find((i) => pathname.startsWith(i.ruta));
    if (item) return item.etiqueta;
  }
  return "Consola";
}

/**
 * Cascaron de la aplicacion: sidebar a la izquierda, topbar con el titulo de la
 * seccion y el area de contenido (Outlet del router) a ancho completo. En
 * pantallas chicas el sidebar se vuelve un panel deslizable.
 */
export function AppShell() {
  const location = useLocation();
  const [menuAbierto, setMenuAbierto] = React.useState(false);

  // Cierra el menu movil al cambiar de ruta.
  React.useEffect(() => {
    setMenuAbierto(false);
  }, [location.pathname]);

  const titulo = tituloDeRuta(location.pathname);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      {/* Sidebar fijo (escritorio). */}
      <aside className="hidden md:block">
        <Sidebar />
      </aside>

      {/* Sidebar deslizable (movil). */}
      {menuAbierto && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setMenuAbierto(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 z-50 animate-in slide-in-from-left">
            <Sidebar onNavegar={() => setMenuAbierto(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label={menuAbierto ? "Cerrar menú" : "Abrir menú"}
            onClick={() => setMenuAbierto((v) => !v)}
          >
            {menuAbierto ? <X /> : <Menu />}
          </Button>

          {/* Marca (solo movil; en escritorio vive en el sidebar). */}
          <div className="md:hidden">
            <Wordmark />
          </div>

          {/* Titulo de la seccion activa (escritorio), estilo Vercel. */}
          <h1 className="hidden text-sm font-medium text-foreground md:block">{titulo}</h1>
        </header>

        <main className={cn("flex-1 overflow-y-auto")}>
          <div className="w-full px-6 py-6 lg:px-8">
            <React.Suspense fallback={<CargandoPagina />}>
              <Outlet />
            </React.Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Loader2, Menu, X } from "lucide-react";
import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";

import { IndicadorEstado } from "@/components/layout/IndicadorEstado";
import { Sidebar } from "@/components/layout/Sidebar";
import { Wordmark } from "@/components/layout/Wordmark";
import { appDeRuta } from "@/components/layout/apps-scope";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { hidratarLimites } from "@/pages/publicaciones/meta";
import type { AppCatalogo } from "@/types";

/** Fallback mientras se descarga el chunk de una pagina (lazy/Suspense). */
function CargandoPagina() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin" aria-label="Cargando" />
    </div>
  );
}

/** Clave de localStorage del estado colapsado del sidebar (rail). */
const CLAVE_SIDEBAR_COLAPSADO = "keni:sidebar-colapsado";

/**
 * Título de la topbar según el path. Dentro de una app, busca el item de nav que
 * mejor matchea (prefijo más largo) y usa su etiqueta; si no, cae a la etiqueta
 * de la app. Fuera de apps (Panel, ajustes) cae a "Consola".
 */
function tituloDeRuta(pathname: string, apps: AppCatalogo[]): string {
  const app = appDeRuta(apps, pathname);
  if (!app) return pathname.startsWith("/panel") ? "Panel" : "Consola";
  let mejor = app.etiqueta;
  let mejorLargo = -1;
  for (const item of app.nav) {
    if (
      (pathname === item.ruta || pathname.startsWith(`${item.ruta}/`)) &&
      item.ruta.length > mejorLargo
    ) {
      mejorLargo = item.ruta.length;
      mejor = item.etiqueta;
    }
  }
  return mejor;
}

/**
 * Cascaron de la aplicacion: sidebar a la izquierda, topbar con el titulo de la
 * seccion, y el area de contenido (Outlet del router). En pantallas chicas el
 * sidebar se vuelve un panel deslizable.
 */
export function AppShell() {
  const location = useLocation();
  const [menuAbierto, setMenuAbierto] = React.useState(false);

  // Estado colapsado del sidebar (rail de solo iconos), persistido en
  // localStorage para que sobreviva al refresco. Inicializa leyéndolo (lazy).
  const [colapsado, setColapsado] = React.useState<boolean>(() => {
    try {
      return localStorage.getItem(CLAVE_SIDEBAR_COLAPSADO) === "1";
    } catch {
      return false;
    }
  });
  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_SIDEBAR_COLAPSADO, colapsado ? "1" : "0");
    } catch {
      // localStorage no disponible (modo privado / SSR): el estado vive en memoria.
    }
  }, [colapsado]);
  const alternarColapsado = React.useCallback(() => setColapsado((v) => !v), []);

  // Hidrata la caché de límites de caracteres desde la fuente única del backend
  // (`GET /api/limites`, #112). Mientras carga, `metaRed().limite` usa la semilla
  // (espejo del backend). Si falla, la semilla sigue siendo válida (sin romper).
  const limitesQuery = useQuery({
    queryKey: ["limites"],
    queryFn: ({ signal }) => api.limites(signal),
    staleTime: Infinity,
  });
  React.useEffect(() => {
    if (limitesQuery.data) hidratarLimites(limitesQuery.data.limites);
  }, [limitesQuery.data]);

  // Catálogo de apps (cajón de apps · ADR 0005): el título de la topbar sale de la
  // app actual y su nav (data-driven). Comparte queryKey con el Sidebar, así se
  // resuelve una sola vez. Mientras carga, `apps` es [] y el título cae a "Consola".
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });
  const apps = catalogoQuery.data?.apps ?? [];

  // Cierra el menu movil al cambiar de ruta.
  React.useEffect(() => {
    setMenuAbierto(false);
  }, [location.pathname]);

  const titulo = tituloDeRuta(location.pathname, apps);

  // El sidebar se muestra SIEMPRE ahora: ya no hay launcher `/` sin barra. Las
  // apps viven dentro del sidebar como grupos de acordeón.
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      {/* Sidebar fijo (escritorio). En rail (colapsado) queda estrecho. */}
      <aside className="hidden md:block">
        <Sidebar colapsado={colapsado} onToggleColapsar={alternarColapsado} />
      </aside>

      {/* Sidebar deslizable (movil). Siempre completo (sin rail en móvil). */}
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

          {/* Indicador de salud del sistema, alineado a la derecha de la topbar. */}
          <div className="ml-auto flex items-center">
            <IndicadorEstado />
          </div>
        </header>

        <main className={cn("flex-1 overflow-y-auto")}>
          {/* Contenido a ancho completo (estilo Vercel/edit-consola), no centrado. */}
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

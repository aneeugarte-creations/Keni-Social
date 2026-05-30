import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Loader2, Menu, X } from "lucide-react";
import * as React from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { FronteraError } from "@/components/comunes/FronteraError";
import { IndicadorEstado } from "@/components/layout/IndicadorEstado";
import { PaletaProvider } from "@/components/layout/PaletaComandos";
import { Sidebar } from "@/components/layout/Sidebar";
import { Wordmark } from "@/components/layout/Wordmark";
import { appDeRuta, hojasDeApp, rutaPrimaria } from "@/components/layout/apps-scope";
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

/** Etiquetas de las pantallas de shell (fuera de apps) que no son Panel. */
const ETIQUETAS_SHELL: Record<string, string> = {
  "/configuracion": "Configuración",
  "/mi-cuenta": "Mi cuenta",
  "/usuarios": "Usuarios",
};

/**
 * Breadcrumb derivado del path. Dentro de una app devuelve `{ app, pagina }`:
 * `app` (etiqueta + ruta primaria, para enlazarla) y `pagina` (la HOJA que mejor
 * matchea por prefijo más largo entre `hojasDeApp`, que incluye las sub-páginas
 * aplanadas de los hubs). Fuera de apps no hay `app`: Panel → "Panel"; ajustes →
 * el nombre de la pantalla; resto → "Consola".
 */
interface Migaja {
  app?: { etiqueta: string; ruta: string };
  pagina: string;
}

function migajaDeRuta(pathname: string, apps: AppCatalogo[]): Migaja {
  const app = appDeRuta(apps, pathname);
  if (!app) {
    if (pathname.startsWith("/panel")) return { pagina: "Panel" };
    for (const [ruta, etiqueta] of Object.entries(ETIQUETAS_SHELL)) {
      if (pathname === ruta || pathname.startsWith(`${ruta}/`)) return { pagina: etiqueta };
    }
    return { pagina: "Consola" };
  }
  // Hoja actual: prefijo más largo entre las hojas APLANADAS de la app (cubre las
  // sub-páginas de hubs, p.ej. /analiticas/metricas). Cae a la etiqueta de la app.
  let pagina = app.etiqueta;
  let mejorLargo = -1;
  for (const hoja of hojasDeApp(app)) {
    if (
      (pathname === hoja.ruta || pathname.startsWith(`${hoja.ruta}/`)) &&
      hoja.ruta.length > mejorLargo
    ) {
      mejorLargo = hoja.ruta.length;
      pagina = hoja.etiqueta;
    }
  }
  return { app: { etiqueta: app.etiqueta, ruta: rutaPrimaria(app) }, pagina };
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

  const migaja = migajaDeRuta(location.pathname, apps);

  // El sidebar se muestra SIEMPRE ahora: ya no hay launcher `/` sin barra. Las
  // apps viven dentro del sidebar como grupos de acordeón. `PaletaProvider` monta
  // la paleta de comandos (⌘K) una sola vez y registra su listener global.
  return (
    <PaletaProvider>
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

          {/* Breadcrumb de la sección activa (escritorio): "App › Página". La
              App es un enlace a su 1ª página; la Página es texto. Fuera de apps,
              solo se muestra la pantalla (Panel / ajustes) sin "›". */}
          <nav aria-label="Ruta" className="hidden min-w-0 items-center gap-1.5 text-sm md:flex">
            {migaja.app && (
              <>
                <Link
                  to={migaja.app.ruta}
                  className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                >
                  {migaja.app.etiqueta}
                </Link>
                <ChevronRight
                  className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60"
                  aria-hidden="true"
                />
              </>
            )}
            <span className="truncate font-medium text-foreground" aria-current="page">
              {migaja.pagina}
            </span>
          </nav>

          {/* Indicador de salud del sistema, alineado a la derecha de la topbar. */}
          <div className="ml-auto flex items-center">
            <IndicadorEstado />
          </div>
        </header>

        <main className={cn("flex-1 overflow-y-auto")}>
          {/* Contenido a ancho completo (estilo Vercel/edit-consola), no centrado. */}
          <div className="w-full px-6 py-6 lg:px-8">
            {/* Frontera de error por ruta: aísla un fallo de página (TypeError,
                chunk lazy de un deploy nuevo) en vez de tumbar toda la app. La
                `key` por pathname la remonta al navegar, limpiando el estado. */}
            <FronteraError key={location.pathname}>
              <React.Suspense fallback={<CargandoPagina />}>
                <Outlet />
              </React.Suspense>
            </FronteraError>
          </div>
        </main>
      </div>
    </div>
    </PaletaProvider>
  );
}

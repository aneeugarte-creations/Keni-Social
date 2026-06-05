import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Loader2, Menu, X } from "lucide-react";
import * as React from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { FronteraError } from "@/components/comunes/FronteraError";
import { CampanaNotificaciones } from "@/components/layout/CampanaNotificaciones";
import { PaletaProvider } from "@/components/layout/PaletaComandos";
import { Sidebar } from "@/components/layout/Sidebar";
import { SubnavHub } from "@/components/layout/SubnavHub";
import { SwitchMarca } from "@/components/layout/SwitchMarca";
import { Wordmark } from "@/components/layout/Wordmark";
import { pestanasDeRuta } from "@/components/layout/hub-tabs";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useDetectorActualizacion } from "@/lib/version";
import { hidratarLimites } from "@/pages/publicaciones/meta";
import type { GrupoNavCatalogo } from "@/types";

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

/** Etiquetas de las pantallas de shell (fuera de apps): ajustes del avatar. */
const ETIQUETAS_SHELL: Record<string, string> = {
  "/configuracion": "Configuración",
  "/mi-cuenta": "Mi cuenta",
  "/usuarios": "Usuarios",
  "/sistema": "Sistema",
};

/** Un segmento del breadcrumb. Con `ruta` es un enlace; sin ella, texto. */
interface Migaja {
  etiqueta: string;
  ruta?: string;
}

/**
 * Breadcrumb derivado del path, en la MISMA estructura que el sidebar por flujo (NO
 * por el nombre de app A/B/C, que ya no se ve en la nav). Recorre los bloques de
 * `navegacion` y busca la entrada (hub o página) que contiene la ruta:
 *   - hub con 2+ pestañas → `[hub (enlace), pestaña activa (actual)]`,
 *   - página suelta (o hub de una sola hoja) → `[página]`.
 * Las pantallas de shell (ajustes del avatar) caen a su nombre; lo desconocido,
 * a "Consola". El último segmento es el actual.
 */
function migajaDeRuta(pathname: string, navegacion: GrupoNavCatalogo[]): Migaja[] {
  for (const bloque of navegacion) {
    for (const item of bloque.items) {
      if (pathname === item.ruta || pathname.startsWith(`${item.ruta}/`)) {
        const pestanas = pestanasDeRuta(pathname);
        if (pestanas && pestanas.length >= 2) {
          // Pestaña activa = la de prefijo más largo que matchea la ruta.
          const activa = [...pestanas]
            .sort((a, b) => b.ruta.length - a.ruta.length)
            .find((t) => pathname === t.ruta || pathname.startsWith(`${t.ruta}/`));
          return [
            { etiqueta: item.etiqueta, ruta: item.ruta },
            { etiqueta: activa?.etiqueta ?? item.etiqueta },
          ];
        }
        return [{ etiqueta: item.etiqueta }];
      }
    }
  }
  for (const [ruta, etiqueta] of Object.entries(ETIQUETAS_SHELL)) {
    if (pathname === ruta || pathname.startsWith(`${ruta}/`)) return [{ etiqueta }];
  }
  return [{ etiqueta: "Consola" }];
}

/**
 * Cascaron de la aplicacion: sidebar a la izquierda, topbar con el titulo de la
 * seccion, y el area de contenido (Outlet del router). En pantallas chicas el
 * sidebar se vuelve un panel deslizable.
 */
export function AppShell() {
  const location = useLocation();
  const [menuAbierto, setMenuAbierto] = React.useState(false);

  // Detecta un deploy nuevo y recarga en la siguiente navegación (sin pedirlo a mano).
  useDetectorActualizacion();

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

  // Catálogo (ADR 0005): el breadcrumb sale de la nav de flujo ya agrupada por el
  // backend (`navegacion`), igual que el Sidebar. Comparte queryKey, así se resuelve
  // una sola vez. Mientras carga, `navegacion` es [] y el breadcrumb cae a su fallback.
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });
  const navegacion = catalogoQuery.data?.navegacion ?? [];

  // Cierra el menu movil al cambiar de ruta.
  React.useEffect(() => {
    setMenuAbierto(false);
  }, [location.pathname]);

  const migaja = migajaDeRuta(location.pathname, navegacion);

  // El sidebar se muestra SIEMPRE ahora: ya no hay launcher `/` sin barra. Las
  // apps viven dentro del sidebar como grupos de acordeón. `PaletaProvider` monta
  // la paleta de comandos (⌘K) una sola vez y registra su listener global.
  return (
    <PaletaProvider>
    <div className="flex h-dvh w-full overflow-hidden bg-background">
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
        {/* `relative z-30`: el topbar y todo su subárbol (incluido el cajón de
            notificaciones, que se despliega hacia el contenido) deben pintar SOBRE el
            `<main>`. El `backdrop-blur` del header ya crea un contexto de apilamiento
            propio; sin un z-index explícito ese contexto vale `auto` y, al ir el header
            ANTES que `<main>` en el DOM, el feed lo tapa. z-30 lo eleva sobre el
            contenido pero queda por debajo de overlays en portal (menú móvil z-40,
            diálogos z-50, toasts z-[100]). */}
        <header className="relative z-30 flex h-12 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:px-6">
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

          {/* Breadcrumb de la sección activa (escritorio), espejo del sidebar de flujo:
              "Hub › Pestaña" en una hoja de hub, o solo la página suelta. El hub es un
              enlace; el último segmento es la página/pestaña actual (texto). */}
          <nav aria-label="Ruta" className="hidden min-w-0 items-center gap-1.5 text-sm md:flex">
            {migaja.map((crumb, i) => {
              const ultimo = i === migaja.length - 1;
              return (
                <React.Fragment key={`${crumb.etiqueta}-${i}`}>
                  {i > 0 && (
                    <ChevronRight
                      className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60"
                      aria-hidden="true"
                    />
                  )}
                  {ultimo ? (
                    <span className="truncate font-medium text-foreground" aria-current="page">
                      {crumb.etiqueta}
                    </span>
                  ) : crumb.ruta ? (
                    <Link
                      to={crumb.ruta}
                      className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {crumb.etiqueta}
                    </Link>
                  ) : (
                    <span className="shrink-0 text-muted-foreground">{crumb.etiqueta}</span>
                  )}
                </React.Fragment>
              );
            })}
          </nav>

          {/* Marca activa (workspace) a la derecha de la topbar. El switch de marca
              manda en toda la consola: la marca activa filtra implícitamente lo que
              se ve (deriva del perfil, ver SwitchMarca). */}
          <div className="ml-auto flex items-center gap-3">
            <CampanaNotificaciones />
            <SwitchMarca />
          </div>
        </header>

        <main className={cn("flex-1 overflow-y-auto")}>
          {/* Contenido a ancho completo (estilo Vercel/edit-consola), no centrado. */}
          <div className="w-full px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
            {/* Frontera de error por ruta: aísla un fallo de página (TypeError,
                chunk lazy de un deploy nuevo) en vez de tumbar toda la app. La
                `key` por pathname la remonta al navegar, limpiando el estado. */}
            {/* Pestañas del hub actual (Investigación, Revisión, …): los hubs son
                UNA entrada en el sidebar y su sub-nav vive aquí, sobre el contenido.
                Fuera del boundary: un fallo de página no debe tumbar la sub-nav. */}
            <SubnavHub />
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

import { useQuery } from "@tanstack/react-query";
import { Loader2, Menu, X } from "lucide-react";
import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";

import { FronteraError } from "@/components/comunes/FronteraError";
import { CampanaNotificaciones } from "@/components/layout/CampanaNotificaciones";
import { PaletaProvider } from "@/components/layout/PaletaComandos";
import { EncabezadoSeccion } from "@/components/layout/EncabezadoSeccion";
import { ProveedorEncabezado, type EncabezadoCtx } from "@/components/layout/encabezado";
import { Sidebar } from "@/components/layout/Sidebar";
import { SwitchFiltrosContenido } from "@/components/layout/SwitchFiltrosContenido";
import { SwitchMarca } from "@/components/layout/SwitchMarca";
import { Wordmark } from "@/components/layout/Wordmark";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useDetectorActualizacion } from "@/lib/version";
import { hidratarLimites } from "@/pages/publicaciones/meta";

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

  // Huecos de la barra de cabecera unificada (`EncabezadoSeccion`): inicio (título de página
  // plana) y acciones (menú "⋯"). Las páginas portalizan ahí su título/acciones vía contexto,
  // así caen siempre en la misma barra y quedan alineados. `tituloCount` cuenta los títulos
  // montados para que la barra tome su borde solo cuando hay título (o pestañas).
  const [slotInicio, setSlotInicio] = React.useState<HTMLElement | null>(null);
  const [slotAcciones, setSlotAcciones] = React.useState<HTMLElement | null>(null);
  const [tituloCount, setTituloCount] = React.useState(0);
  const registrarTitulo = React.useCallback(() => {
    setTituloCount((n) => n + 1);
    return () => setTituloCount((n) => n - 1);
  }, []);
  const ctxEncabezado = React.useMemo<EncabezadoCtx>(
    () => ({ slotInicio, slotAcciones, registrarTitulo }),
    [slotInicio, slotAcciones, registrarTitulo],
  );

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

  // Cierra el menu movil al cambiar de ruta.
  React.useEffect(() => {
    setMenuAbierto(false);
  }, [location.pathname]);

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

          {/* Filtros y workspace a la derecha de la topbar. Los switches GLOBALES mandan
              en toda la consola: la MARCA filtra implícitamente lo que se ve (deriva del
              perfil, ver SwitchMarca); RED y LÍNEA filtran la superficie de contenido/feed
              y solo se pintan en sus rutas (SwitchFiltrosContenido decide su visibilidad). */}
          <div className="ml-auto flex items-center gap-3">
            <SwitchFiltrosContenido />
            <CampanaNotificaciones />
            <SwitchMarca />
          </div>
        </header>

        <main className={cn("flex-1 overflow-y-auto")}>
          {/* Contenido a ancho completo (estilo Vercel/edit-consola), no centrado. */}
          <div className="w-full px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
            {/* Cabecera de sección UNIFICADA (misma altura/ancho/posición en todas las
                páginas): pestañas del hub, o el título de la página plana, más las acciones
                a la derecha. Las páginas portalizan título/acciones a sus huecos vía el
                proveedor de contexto (envuelve también al `<Outlet/>`). Vive FUERA del
                boundary: un fallo de página no debe tumbar la barra de navegación. */}
            <ProveedorEncabezado value={ctxEncabezado}>
              <EncabezadoSeccion
                refInicio={setSlotInicio}
                refAcciones={setSlotAcciones}
                tituloPresente={tituloCount > 0}
              />
              <FronteraError key={location.pathname}>
                <React.Suspense fallback={<CargandoPagina />}>
                  <Outlet />
                </React.Suspense>
              </FronteraError>
            </ProveedorEncabezado>
          </div>
        </main>
      </div>
    </div>
    </PaletaProvider>
  );
}

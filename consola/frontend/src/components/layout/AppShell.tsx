import { useQuery } from "@tanstack/react-query";
import { Loader2, Menu, X } from "lucide-react";
import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";

import { FronteraError } from "@/components/comunes/FronteraError";
import { CampanaNotificaciones } from "@/components/layout/CampanaNotificaciones";
import { ControlContexto } from "@/components/layout/ControlContexto";
import { PaletaProvider } from "@/components/layout/PaletaComandos";
import { EncabezadoSeccion } from "@/components/layout/EncabezadoSeccion";
import { ProveedorEncabezado, type EncabezadoCtx } from "@/components/layout/encabezado";
import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { useEsEscritorio } from "@/hooks/use-media-query";
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

  // Editor de contenido (Imagen / Vídeo): la barra superior se viste con el degradado naranja de
  // marca (estilo Canva) y su cromo pasa a blanco. El degradado y el recoloreado del cromo viven
  // en `.topbar-editor` (index.css), acotados a esta cabecera; los menús desplegables, que se
  // pintan inline dentro de la barra, restauran sus tokens allí para seguir siendo legibles.
  const enEditor =
    location.pathname.startsWith("/contenido/imagen") ||
    location.pathname.startsWith("/contenido/video");

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

  // Huecos de la barra de cabecera unificada (`EncabezadoSeccion`, ahora dentro del topbar):
  // inicio (título de página plana) y acciones (menú "⋮"). Las páginas portalizan ahí su
  // título/acciones vía contexto, así caen siempre en la misma barra y quedan alineados.
  // El header siempre está presente (con su propio borde), así que ya no hace falta contar
  // títulos para decidir la visibilidad de la barra; `registrarTitulo` queda como no-op estable
  // para no romper el contrato de `<TituloPagina/>`.
  const [slotInicio, setSlotInicio] = React.useState<HTMLElement | null>(null);
  const [slotAcciones, setSlotAcciones] = React.useState<HTMLElement | null>(null);
  // MÓVIL: las acciones de página NO caben en la topbar (una sola fila de h-12 que ya
  // lleva hamburguesa + sección + contexto + campana; un selector de 200px la desborda
  // y quedaba CORTADO, p. ej. los atajos de Métricas). Bajo `md` el portal de acciones
  // apunta a una FILA PROPIA debajo del header (oculta si la página no porta acciones).
  const [slotAccionesMovil, setSlotAccionesMovil] = React.useState<HTMLElement | null>(null);
  const esEscritorio = useEsEscritorio();
  const registrarTitulo = React.useCallback(() => () => {}, []);
  const ctxEncabezado = React.useMemo<EncabezadoCtx>(
    () => ({
      slotInicio,
      slotAcciones: esEscritorio ? slotAcciones : slotAccionesMovil,
      registrarTitulo,
    }),
    [slotInicio, slotAcciones, slotAccionesMovil, esEscritorio, registrarTitulo],
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
        <header
          className={cn(
            "relative z-30 flex h-12 shrink-0 items-center gap-3 border-b border-border px-4 lg:px-6",
            enEditor
              ? "topbar-editor"
              : "bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60",
          )}
        >
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label={menuAbierto ? "Cerrar menú" : "Abrir menú"}
            onClick={() => setMenuAbierto((v) => !v)}
          >
            {menuAbierto ? <X /> : <Menu />}
          </Button>

          {/* Sección (dropdown del hub o título de página plana) + acciones, donde antes
              estaban los breadcrumbs. Recibe los huecos por props (no consume el contexto):
              el Provider solo envuelve al `<Outlet/>`, que es quien portaliza título/acciones
              a estos huecos. */}
          {enEditor ? (
            <>
              {/* EDITOR (patrón Canva): las HERRAMIENTAS van CENTRADAS en la barra, no
                  apiladas tras el título. Tres zonas: título a la izquierda y contexto a la
                  derecha como flancos `flex-1` de base 0 (iguales => el carril central queda
                  en el centro REAL de la barra y, si falta sitio, ceden antes de solaparse),
                  y el hueco de acciones entre ambos. En móvil el portal de acciones apunta a
                  su fila bajo el header (como siempre): el carril queda vacío y `empty:hidden`
                  lo quita del flujo. */}
              <div className="flex h-full min-w-0 flex-1 items-center">
                <EncabezadoSeccion refInicio={setSlotInicio} />
              </div>
              <div ref={setSlotAcciones} className="flex h-full min-w-0 items-center justify-center empty:hidden" />
              <div className="flex flex-1 items-center justify-end gap-2">
                <ControlContexto />
                <CampanaNotificaciones />
              </div>
            </>
          ) : (
            <>
              <EncabezadoSeccion refInicio={setSlotInicio} refAcciones={setSlotAcciones} />

              {/* A la derecha de la topbar: el control de CONTEXTO unificado (marca + red + línea
                  en un solo dropdown; los filtros de red/línea solo se ofrecen en sus rutas) y las
                  notificaciones. */}
              <div className="ml-auto flex items-center gap-2">
                <ControlContexto />
                <CampanaNotificaciones />
              </div>
            </>
          )}
        </header>

        {/* Acciones de página en MÓVIL: fila propia bajo el header (el portal de
            `AccionesPagina` apunta aquí bajo `md`). `empty:hidden` la colapsa del todo
            en páginas sin acciones; `flex-wrap` deja que selectores y botones respiren
            en columna o en varias líneas sin desbordar el viewport. */}
        <div
          ref={setSlotAccionesMovil}
          className="flex flex-wrap items-center gap-2 border-b border-border bg-background px-4 py-2 empty:hidden md:hidden"
        />

        {/* `overflow-x-hidden`: el scroll real es VERTICAL. Sin esto, `overflow-y-auto`
            promueve el eje X a `auto` (regla CSS: si un eje no es `visible`, el otro `visible`
            pasa a `auto`), y un hijo más ancho que el viewport (una tarjeta del feed, una URL
            larga) deja arrastrar TODA la superficie de lado en móvil. Clampar X lo impide. */}
        <main className={cn("min-w-0 flex-1 overflow-y-auto overflow-x-hidden")}>
          {/* Contenido a ancho completo (estilo Vercel/edit-consola), no centrado. */}
          <div className="w-full min-w-0 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
            {/* Las páginas portalizan su título/acciones a los huecos de la barra superior vía
                el proveedor de contexto, que envuelve al `<Outlet/>`. La cabecera de sección
                (pestañas/título) ya se pinta en el header, no aquí. */}
            <ProveedorEncabezado value={ctxEncabezado}>
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

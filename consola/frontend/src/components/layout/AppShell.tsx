import { useQuery } from "@tanstack/react-query";
import { Loader2, Menu, X } from "lucide-react";
import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";

import { FronteraError } from "@/components/comunes/FronteraError";
import { PanelActualizando } from "@/components/comunes/PanelActualizando";
import { CampanaNotificaciones } from "@/components/layout/CampanaNotificaciones";
import { ControlContexto } from "@/components/layout/ControlContexto";
import { PaletaProvider } from "@/components/layout/PaletaComandos";
import { EncabezadoSeccion } from "@/components/layout/EncabezadoSeccion";
import { ProveedorEncabezado, type EncabezadoCtx } from "@/components/layout/encabezado";
import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { useEsEscritorio } from "@/hooks/use-media-query";
import { api } from "@/lib/api";
import { useConexionDegradada, useMotivoConexion } from "@/lib/estado-red";
import { cn } from "@/lib/utils";
import { useDetectorActualizacion } from "@/lib/version";
import { hidratarLimites } from "@/pages/piezas/meta";

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

  // Editor de contenido (Imagen / Vídeo): la barra superior comparte la MISMA superficie clara
  // que el resto de la app (sin degradado de marca). Lo único propio del editor es el LAYOUT de la
  // barra —el carril de herramientas CENTRADO entre título y contexto—, que pinta la rama `enEditor`
  // del JSX más abajo; el color/cromo es idéntico (decisión de diseño: chrome sobrio, el naranja
  // queda como acento puntual, no como campo).
  const enEditor =
    location.pathname.startsWith("/publicaciones/imagen") ||
    location.pathname.startsWith("/publicaciones/video");

  // Detecta un deploy nuevo y recarga en la siguiente navegación (sin pedirlo a mano).
  useDetectorActualizacion();

  // Back desplegando/caído (varias queries seguidas fallan por red/proxy): un ÚNICO velo calmado
  // "Estamos actualizando" cubre el contenido. Sustituye al banner ámbar y, con el guard de
  // `BloqueError`, garantiza que NUNCA aparezca un muro de errores rojos por sección.
  const conexionDegradada = useConexionDegradada();
  const motivoConexion = useMotivoConexion();

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

  // Huecos de la barra superior que las páginas rellenan por portal (vía contexto): inicio
  // (título de página plana, junto a las pestañas en `EncabezadoSeccion`) y acciones (el menú
  // "⋮" y demás controles, en el flanco derecho de la barra, antes del contexto global). Así
  // caen siempre en la misma barra y quedan alineados.
  // El header siempre está presente (con su propio borde), así que su visibilidad no depende
  // de contar títulos; `registrarTitulo` es un no-op estable que mantiene el contrato de
  // `<TituloPagina/>`.
  const [slotInicio, setSlotInicio] = React.useState<HTMLElement | null>(null);
  const [slotAcciones, setSlotAcciones] = React.useState<HTMLElement | null>(null);
  // Hueco del FLANCO DERECHO (guardado/exportar del editor, vía `AccionesPaginaFin`). Solo se
  // monta en las rutas del editor; en el resto queda null y ese portal cae a `slotAcciones`.
  const [slotAccionesFin, setSlotAccionesFin] = React.useState<HTMLElement | null>(null);
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
      // En móvil ambos huecos apuntan a la misma fila bajo el header: guardado/exportar y
      // herramientas conviven allí con wrap.
      slotAccionesFin: esEscritorio ? slotAccionesFin : slotAccionesMovil,
      registrarTitulo,
    }),
    [slotInicio, slotAcciones, slotAccionesFin, slotAccionesMovil, esEscritorio, registrarTitulo],
  );

  // Hidrata la caché de límites de caracteres desde la fuente única del backend
  // (`GET /api/limites`). Mientras carga, `metaRed().limite` usa los valores base
  // (espejo del backend). Si falla, los valores base siguen siendo válidos (sin romper).
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

  // Las apps viven dentro del sidebar como grupos de acordeón. `PaletaProvider` monta
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

      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* `relative z-30`: el topbar y todo su subárbol (incluido el cajón de
            notificaciones, que se despliega hacia el contenido) deben pintar SOBRE el
            `<main>`. El `backdrop-blur` del header ya crea un contexto de apilamiento
            propio; sin un z-index explícito ese contexto vale `auto` y, al ir el header
            ANTES que `<main>` en el DOM, el feed lo tapa. z-30 lo eleva sobre el
            contenido pero queda por debajo de overlays en portal (menú móvil z-40,
            diálogos z-50, toasts z-[100]). */}
        <header
          className={cn(
            "relative z-30 flex h-12 shrink-0 items-center gap-3 px-4 lg:px-6",
            // Cromo unificado en TODA la app, editor incluido: blanco translúcido + hairline
            // inferior + cromo oscuro por defecto.
            "border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60",
          )}
        >
          <Button
            variant="ghost"
            size="icon"
            // h-8 w-8: todo el cromo de la barra mide 32px (size icon por defecto son 36).
            className="h-8 w-8 md:hidden"
            aria-label={menuAbierto ? "Cerrar menú" : "Abrir menú"}
            onClick={() => setMenuAbierto((v) => !v)}
          >
            {menuAbierto ? <X /> : <Menu />}
          </Button>

          {/* Sección (dropdown del hub o título de página plana) + acciones. Recibe los huecos
              por props (no consume el contexto): el Provider solo envuelve al `<Outlet/>`, que
              es quien portaliza título/acciones a estos huecos. */}
          {enEditor ? (
            <>
              {/* EDITOR (patrón Canva): las HERRAMIENTAS van CENTRADAS en la barra, no
                  apiladas tras el título. Tres zonas: título a la izquierda y contexto a la
                  derecha como flancos `flex-1` de base 0 (iguales => el carril central queda
                  en el centro REAL de la barra y, si falta sitio, ceden antes de solaparse),
                  y el hueco de acciones entre ambos. El flanco derecho lleva además el hueco
                  de GUARDADO/EXPORTAR (`AccionesPaginaFin`), antes del contexto de marca. En
                  móvil ambos portales apuntan a la fila bajo el header (como siempre): los
                  huecos quedan vacíos y `empty:hidden` los quita del flujo. */}
              <div className="flex h-full min-w-0 flex-1 items-center">
                <EncabezadoSeccion refInicio={setSlotInicio} />
              </div>
              <div ref={setSlotAcciones} className="flex h-full min-w-0 items-center justify-center empty:hidden" />
              <div className="flex flex-1 items-center justify-end gap-2">
                <div ref={setSlotAccionesFin} className="flex min-w-0 items-center gap-1 empty:hidden" />
                {/* Hairline entre las acciones del DOCUMENTO (guardado/exportar) y el contexto
                    GLOBAL (marca + campana): marca el límite de grupo sin añadir otra medida
                    de gap. Solo en escritorio: en móvil el slot fin va vacío (portaliza a la
                    fila bajo el header) y el separador quedaría suelto. */}
                <div aria-hidden className="hidden h-5 w-px bg-[hsl(var(--foreground)/0.15)] md:block" />
                <ControlContexto />
                <CampanaNotificaciones />
              </div>
            </>
          ) : (
            <>
              {/* La cabecera de sección (pestañas/título) ocupa la IZQUIERDA y CRECE para empujar
                  el flanco derecho a la esquina. */}
              <div className="flex h-full min-w-0 flex-1 items-center">
                <EncabezadoSeccion refInicio={setSlotInicio} />
              </div>

              {/* Flanco derecho, de dentro hacia la esquina: las ACCIONES de la página que ésta
                  portalice (el menú "⋮", los controles de la máquina…) y, pegado al borde, el
                  contexto GLOBAL persistente (marca + red + línea en un dropdown; los filtros de
                  red/línea solo en sus rutas) + las notificaciones. Sacar las acciones aquí, lejos
                  de las pestañas, evita que el "⋮" caiga en el camino de lectura de la navegación. */}
              <div className="flex items-center gap-2">
                <div ref={setSlotAcciones} className="peer flex min-w-0 items-center gap-1 empty:hidden" />
                {/* Hairline entre las acciones de SECCIÓN y el contexto GLOBAL: marca el límite de
                    grupo sin añadir otra medida de gap. Solo cuando hay acciones (el `peer` no está
                    vacío) y en escritorio. */}
                <div
                  aria-hidden
                  className="hidden h-5 w-px bg-[hsl(var(--foreground)/0.15)] md:peer-[:not(:empty)]:block"
                />
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
          {/* Publicacion a ancho completo (estilo Vercel/edit-consola), no centrado. El gap
              SUPERIOR (barra → primer control de la página) es ajustado (`pt-2` = 8px) para
              que TODAS las páginas respiren igual que la galería del editor (Fotos/Miniaturas
              pega bajo la barra); el inferior se mantiene holgado (`pb-4 sm:pb-6`). */}
          <div className="w-full min-w-0 px-4 pt-2 pb-4 sm:px-6 sm:pb-6 lg:px-8">
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

        {/* VELO "Estamos actualizando": cubre el contenido (no el topbar ni el sidebar reales)
            mientras el back está caído/desplegando. Es el equivalente in-app de la página de
            mantenimiento del front; la barra avanza por curva y el velo se retira solo en cuanto
            una query vuelve a responder (el detector apaga `conexionDegradada`). z-20: bajo el
            topbar (z-30) y los overlays en portal (menú móvil z-40, diálogos z-50). */}
        {conexionDegradada && (
          <div className="absolute inset-x-0 bottom-0 top-12 z-20 grid place-items-center bg-background/80 p-6 backdrop-blur">
            {/* `deploy` => barra de progreso (vuelve solo); avería => aviso honesto sin barra. */}
            <PanelActualizando variante={motivoConexion === "deploy" ? "deploy" : "incidente"} />
          </div>
        )}
      </div>
    </div>
    </PaletaProvider>
  );
}

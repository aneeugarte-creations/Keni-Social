import { useQuery } from "@tanstack/react-query";
import { ChevronRight, LayoutDashboard, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import * as React from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { appDeRuta, hojasDeApp, rutaPrimaria } from "@/components/layout/apps-scope";
import { iconoDe } from "@/components/layout/navegacion";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AppCatalogo } from "@/types";

/** Buscador del sidebar estilo Vercel: input blanco con icono y atajo de teclado "F". */
function BuscadorSidebar() {
  const ref = React.useRef<HTMLInputElement>(null);

  // Atajo "F" para enfocar el buscador (se ignora si ya estas escribiendo).
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "f" && e.key !== "F") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      // En movil/escritorio hay dos instancias: enfoca solo la visible.
      if (!ref.current || ref.current.offsetParent === null) return;
      e.preventDefault();
      ref.current.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={ref}
        type="text"
        placeholder="Buscar…"
        aria-label="Buscar"
        className="h-9 w-full rounded-md border border-border bg-card pl-9 pr-9 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
      <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        F
      </kbd>
    </div>
  );
}

/** Clases de un item del sidebar (estilo shadcn: activo resaltado con acento). */
function clasesItem({ isActive }: { isActive: boolean }) {
  return cn(
    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
    isActive
      ? "bg-accent font-medium text-foreground"
      : "font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

/** Clases del item PADRE de una app (cabecera colapsable del acordeón). */
function clasesPadre(activa: boolean) {
  return cn(
    "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
    activa
      ? "font-medium text-foreground"
      : "font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

/** Clases de una HOJA (nivel 2, indentada bajo el padre-app). */
function clasesHoja({ isActive }: { isActive: boolean }) {
  return cn(
    "flex items-center gap-2 rounded-md py-1.5 pl-9 pr-3 text-[13px] transition-colors",
    isActive
      ? "bg-accent font-medium text-foreground"
      : "font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

/** Clases de un icono del rail (barra colapsada, solo iconos). */
function clasesIconoRail(activa: boolean) {
  return cn(
    "flex h-10 w-10 items-center justify-center rounded-md transition-colors",
    activa
      ? "bg-accent text-foreground"
      : "text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

/**
 * Las HOJAS de UNA app: nivel 2 PLANO del sidebar. `hojasDeApp` aplana la nav
 * (los hubs aportan sus sub-pestañas como hojas directas; el resto aporta su
 * propia entrada), así que NO hay nivel-hub ni encabezados de sección: el nombre
 * de la app (el padre) ya nombra el grupo. 2 niveles máximo: App → hoja.
 */
function HojasDeApp({
  app,
  onNavegar,
}: {
  app: AppCatalogo;
  onNavegar?: () => void;
}) {
  const hojas = hojasDeApp(app);

  return (
    <ul className="mt-0.5 space-y-0.5">
      {hojas.map((hoja) => {
        const Icono = hoja.icono;
        return (
          <li key={hoja.ruta}>
            <NavLink
              to={hoja.ruta}
              end={hoja.end}
              onClick={onNavegar}
              title={hoja.descripcion}
              className={({ isActive }) => clasesHoja({ isActive })}
            >
              <Icono className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>{hoja.etiqueta}</span>
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Barra lateral fija de la consola. De arriba a abajo: avatar/cuenta, buscador,
 * una entrada GLOBAL fija a **Panel**, y luego las apps del catálogo como grupos
 * de **acordeón**: cada app es un item padre COLAPSABLE (icono + nombre +
 * chevron) que, al abrirse, muestra sus secciones (y para cada hub, sus
 * sub-pestañas indentadas, vía el registro `hub-tabs`). Es un acordeón: abrir una
 * app cierra las demás; la app de la ruta actual se abre automáticamente. Sin
 * encabezados de sección: el nombre de la app ya nombra su grupo.
 *
 * Toda la barra puede COLAPSARSE a un **rail** estrecho de solo iconos (Panel +
 * los iconos de cada app); en rail, un click en el icono de una app re-expande la
 * barra y abre esa app. El estado colapsado lo controla el AppShell (persistido
 * en localStorage) vía `colapsado`/`onToggleColapsar`.
 */
export function Sidebar({
  onNavegar,
  colapsado = false,
  onToggleColapsar,
}: {
  onNavegar?: () => void;
  colapsado?: boolean;
  onToggleColapsar?: () => void;
}) {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  // Sidebar DATA-DRIVEN (cajón de apps · ADR 0005): se hidrata de `/api/catalogo`
  // (apps activas + su nav, filtradas por los flags del backend). Ya no hay
  // launcher: las apps viven aquí como grupos de acordeón. `staleTime: Infinity`:
  // el catálogo solo cambia con un redeploy (flags).
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });

  const apps = catalogoQuery.data?.apps ?? [];
  const appActual = appDeRuta(apps, pathname);

  // Acordeón: solo una app abierta. Por defecto la app de la ruta actual. Si el
  // usuario abre otra manualmente, se respeta; al cambiar de ruta a otra app, la
  // nueva app actual se abre automáticamente (cierra las demás).
  const [appAbierta, setAppAbierta] = React.useState<string | undefined>(appActual?.id);
  const appActualId = appActual?.id;
  React.useEffect(() => {
    if (appActualId) setAppAbierta(appActualId);
  }, [appActualId]);

  // ---------- Rail (barra colapsada a solo iconos) ----------
  if (colapsado) {
    return (
      <nav
        aria-label="Navegación principal"
        className="flex h-full w-16 flex-col border-r border-border bg-background"
      >
        <div className="flex h-12 items-center justify-center border-b border-border">
          <CuentaUsuario soloIcono />
        </div>

        <div className="flex flex-1 flex-col items-center gap-1 overflow-y-auto py-3">
          <Tooltip label="Panel" side="right">
            <NavLink
              to="/panel"
              onClick={onNavegar}
              className={({ isActive }) => clasesIconoRail(isActive)}
            >
              <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
            </NavLink>
          </Tooltip>

          <hr className="my-1 w-8 border-border" />

          {apps.map((app) => {
            const Icono = iconoDe(app.icono);
            const activa = app.id === appActualId;
            return (
              <Tooltip key={app.id} label={app.etiqueta} side="right">
                <button
                  type="button"
                  aria-label={app.etiqueta}
                  className={clasesIconoRail(activa)}
                  onClick={() => {
                    // Click en rail: re-expande la barra y abre esa app, y navega
                    // a su ruta primaria si no estamos ya dentro de ella.
                    setAppAbierta(app.id);
                    onToggleColapsar?.();
                    if (!activa) navigate(rutaPrimaria(app));
                  }}
                >
                  <Icono className="h-4 w-4" aria-hidden="true" />
                </button>
              </Tooltip>
            );
          })}
        </div>

        <div className="flex justify-center border-t border-border py-3">
          <Tooltip label="Expandir barra" side="right">
            <button
              type="button"
              aria-label="Expandir barra"
              className={clasesIconoRail(false)}
              onClick={onToggleColapsar}
            >
              <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
            </button>
          </Tooltip>
        </div>
      </nav>
    );
  }

  // ---------- Barra completa (acordeón de apps) ----------
  return (
    <nav
      aria-label="Navegación principal"
      className="flex h-full w-64 flex-col border-r border-border bg-background"
    >
      <div className="flex h-12 items-center border-b border-border px-2">
        <CuentaUsuario />
      </div>

      <div className="px-3 pt-3">
        <BuscadorSidebar />
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto px-3 py-4">
        {/* Panel: entrada GLOBAL fija (no es app de catálogo), siempre arriba. */}
        <ul className="space-y-0.5">
          <li>
            <NavLink to="/panel" onClick={onNavegar} className={clasesItem}>
              <LayoutDashboard className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Panel</span>
            </NavLink>
          </li>
        </ul>

        <hr className="border-border" />

        {/* Apps del catálogo como acordeón (sin encabezado de sección). */}
        <ul className="space-y-0.5">
          {apps.map((app) => {
            const Icono = iconoDe(app.icono);
            const abierta = app.id === appAbierta;
            const activa = app.id === appActualId;
            return (
              <li key={app.id}>
                <button
                  type="button"
                  aria-expanded={abierta}
                  aria-controls={`app-hojas-${app.id}`}
                  className={clasesPadre(activa)}
                  onClick={() => {
                    // El título de la app NO es un click muerto: abre su acordeón
                    // (cierra las demás) Y navega a su 1ª hoja. Si la app ya está
                    // abierta, solo togglea cerrado (sin re-navegar de balde).
                    setAppAbierta((actual) => (actual === app.id ? undefined : app.id));
                    if (app.id !== appAbierta && !activa) {
                      navigate(rutaPrimaria(app));
                      onNavegar?.();
                    }
                  }}
                >
                  <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="flex-1 text-left">{app.etiqueta}</span>
                  <ChevronRight
                    className={cn(
                      "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                      abierta && "rotate-90",
                    )}
                    aria-hidden="true"
                  />
                </button>
                {abierta && (
                  <div id={`app-hojas-${app.id}`}>
                    <HojasDeApp app={app} onNavegar={onNavegar} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      {/* Toggle del rail (colapsar toda la barra a solo iconos). */}
      {onToggleColapsar && (
        <div className="border-t border-border px-3 py-2">
          <button
            type="button"
            aria-label="Colapsar barra"
            className={cn(clasesItem({ isActive: false }), "w-full")}
            onClick={onToggleColapsar}
          >
            <PanelLeftClose className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>Colapsar</span>
          </button>
        </div>
      )}

      <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
        <span>Herramienta local · 127.0.0.1</span>
        <span className="ml-2 inline-flex items-center rounded-full border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium tracking-wider text-muted-foreground">
          beta
        </span>
      </div>
    </nav>
  );
}

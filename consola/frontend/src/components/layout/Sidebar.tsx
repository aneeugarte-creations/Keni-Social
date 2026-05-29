import { useQuery } from "@tanstack/react-query";
import { ChevronRight, LayoutDashboard, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import * as React from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { usePaletaComandos } from "@/hooks/paleta-contexto";
import { appDeRuta, hojasDeApp, rutaPrimaria } from "@/components/layout/apps-scope";
import { iconoDe } from "@/components/layout/navegacion";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AppCatalogo } from "@/types";

/** Clave de localStorage del conjunto de apps abiertas del acordeón (multi-abierto). */
const CLAVE_APPS_ABIERTAS = "keni:sidebar-apps-abiertas";

/** Lee el conjunto de apps abiertas persistido (lista de ids). Tolerante a fallos. */
function leerAppsAbiertas(): Set<string> {
  try {
    const crudo = localStorage.getItem(CLAVE_APPS_ABIERTAS);
    if (!crudo) return new Set();
    const ids = JSON.parse(crudo);
    return Array.isArray(ids) ? new Set(ids.filter((x): x is string => typeof x === "string")) : new Set();
  } catch {
    return new Set();
  }
}

/**
 * Trigger del buscador: botón que ABRE la paleta de comandos (⌘K). Sustituye al
 * antiguo input falso (que solo se enfocaba con "F" y no filtraba nada). Muestra
 * "Buscar…" con el hint ⌘K a la derecha.
 */
function BuscadorSidebar() {
  const { abrir } = usePaletaComandos();
  return (
    <button
      type="button"
      onClick={abrir}
      aria-label="Buscar páginas"
      aria-keyshortcuts="Meta+K Control+K"
      className="flex h-9 w-full items-center gap-2 rounded-md border border-border bg-card px-3 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="flex-1 text-left">Buscar…</span>
      <kbd className="pointer-events-none rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        ⌘K
      </kbd>
    </button>
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

/**
 * Clases de una HOJA (nivel 2, indentada bajo el padre-app). Minimalismo: las
 * hojas van en TEXTO (sin icono). El estado activo se marca con una barra/acento
 * a la izquierda (`border-l-2 border-foreground` + texto en `font-medium`), no
 * con icono. Inactivas llevan un borde transparente para que no salte el layout.
 */
function clasesHoja({ isActive }: { isActive: boolean }) {
  return cn(
    "flex items-center rounded-r-md border-l-2 py-1.5 pl-7 pr-3 text-[13px] transition-colors",
    isActive
      ? "border-foreground bg-accent/50 font-medium text-foreground"
      : "border-transparent font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
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
      {hojas.map((hoja) => (
        <li key={hoja.ruta}>
          <NavLink
            to={hoja.ruta}
            end={hoja.end}
            onClick={onNavegar}
            title={hoja.descripcion}
            className={({ isActive }) => clasesHoja({ isActive })}
          >
            <span>{hoja.etiqueta}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

/**
 * Barra lateral fija de la consola. De arriba a abajo: avatar/cuenta, buscador,
 * una entrada GLOBAL fija a **Panel**, y luego las apps del catálogo como grupos
 * de **acordeón PERMISIVO** (multi-abierto): cada app es un item padre
 * COLAPSABLE (icono + nombre + chevron) que, al abrirse, muestra sus hojas (en
 * texto, sin icono; el icono solo a nivel de app). Varias apps pueden estar
 * abiertas a la vez; el conjunto se persiste en localStorage. La app de la ruta
 * actual se asegura abierta automáticamente (se añade, sin cerrar las demás).
 * Sin encabezados de sección: el nombre de la app ya nombra su grupo.
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

  // Acordeón PERMISIVO (multi-abierto): varias apps pueden estar expandidas a la
  // vez. El conjunto de ids abiertos se persiste en localStorage para que
  // sobreviva al refresco. Inicializa leyéndolo (lazy).
  const [appsAbiertas, setAppsAbiertas] = React.useState<Set<string>>(leerAppsAbiertas);
  const appActualId = appActual?.id;

  // La app de la ruta actual se asegura ABIERTA (se añade al conjunto) sin cerrar
  // las demás.
  React.useEffect(() => {
    if (!appActualId) return;
    setAppsAbiertas((actual) => {
      if (actual.has(appActualId)) return actual;
      const siguiente = new Set(actual);
      siguiente.add(appActualId);
      return siguiente;
    });
  }, [appActualId]);

  // Persiste el conjunto de apps abiertas (lista de ids). Tolerante a fallos.
  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_APPS_ABIERTAS, JSON.stringify([...appsAbiertas]));
    } catch {
      // localStorage no disponible: el estado vive en memoria.
    }
  }, [appsAbiertas]);

  // Alterna el abierto/cerrado de una app SIN tocar las demás.
  const alternarApp = React.useCallback((id: string) => {
    setAppsAbiertas((actual) => {
      const siguiente = new Set(actual);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });
  }, []);

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
                    // Click en rail: re-expande la barra y abre esa app (sin
                    // cerrar las demás), y navega a su ruta primaria si no
                    // estamos ya dentro de ella.
                    setAppsAbiertas((actual) => new Set(actual).add(app.id));
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
            const abierta = appsAbiertas.has(app.id);
            const activa = app.id === appActualId;
            return (
              <li key={app.id}>
                <button
                  type="button"
                  aria-expanded={abierta}
                  aria-controls={`app-hojas-${app.id}`}
                  className={clasesPadre(activa)}
                  onClick={() => {
                    // El título de la app NO es un click muerto: ALTERNA su
                    // acordeón (sin cerrar las demás: multi-abierto) Y, al abrir,
                    // navega a su 1ª hoja si no estás ya dentro. Si ya estaba
                    // abierta, solo togglea cerrado (sin re-navegar de balde).
                    alternarApp(app.id);
                    if (!abierta && !activa) {
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
    </nav>
  );
}

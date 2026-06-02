import { useQuery } from "@tanstack/react-query";
import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { NavLink } from "react-router-dom";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { iconoDe } from "@/components/layout/navegacion";
import { usePaletaComandos } from "@/hooks/paleta-contexto";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Trigger del buscador: botón que ABRE la paleta de comandos (⌘K). Muestra
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
 * Barra lateral fija de la consola. La navegación se agrupa por MOMENTO DEL FLUJO
 * (no por dueño de app): el backend (`/api/catalogo` → `navegacion`, ADR 0005)
 * entrega los bloques ya ordenados y etiquetados — `Operación` (checkpoints diarios) ·
 * `Contenido` (herramientas para crear/editar a mano) · `Datos` (lo que alimenta o
 * refleja la automatización). Cada bloque pinta su encabezado y, debajo,
 * sus entradas como enlaces (icono + nombre). Los hubs (Investigación, Revisión,
 * Analíticas, Parrilla) son UNA entrada; su sub-navegación vive como pestañas
 * in-page (`SubnavHub`), no en el sidebar: así la barra no lista herramientas que se
 * usan dentro de un flujo, no sueltas.
 *
 * Toda la barra puede COLAPSARSE a un **rail** estrecho de solo iconos (los mismos
 * items, agrupados por bloque con un separador). El estado colapsado lo controla el
 * AppShell (persistido en localStorage) vía `colapsado`/`onToggleColapsar`.
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
  // Sidebar DATA-DRIVEN (ADR 0005): se hidrata de `/api/catalogo`. El backend ya
  // agrupa la nav por bloque de flujo (apps activas según flags + el Panel del
  // shell) y la ordena; aquí solo la pintamos. `staleTime: Infinity`: el catálogo
  // solo cambia con un redeploy (flags).
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });

  const bloques = catalogoQuery.data?.navegacion ?? [];

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
          {bloques.map((bloque, i) => (
            <div key={bloque.etiqueta || i} className="flex flex-col items-center gap-1">
              {i > 0 && <hr className="my-1 w-8 border-border" />}
              {bloque.items.map((item) => {
                const Icono = iconoDe(item.icono);
                return (
                  <Tooltip key={item.ruta} label={item.etiqueta} side="right">
                    <NavLink
                      to={item.ruta}
                      onClick={onNavegar}
                      aria-label={item.etiqueta}
                      className={({ isActive }) => clasesIconoRail(isActive)}
                    >
                      <Icono className="h-4 w-4" aria-hidden="true" />
                    </NavLink>
                  </Tooltip>
                );
              })}
            </div>
          ))}
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

  // ---------- Barra completa (bloques de flujo con encabezado) ----------
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

      <div className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
        {bloques.map((bloque, i) => (
          <div key={bloque.etiqueta || i} className="space-y-0.5">
            {bloque.etiqueta && (
              <p className="px-3 pb-1 pt-1 text-xs font-medium uppercase tracking-wider text-muted-foreground/80">
                {bloque.etiqueta}
              </p>
            )}
            <ul className="space-y-0.5">
              {bloque.items.map((item) => {
                const Icono = iconoDe(item.icono);
                return (
                  <li key={item.ruta}>
                    <NavLink
                      to={item.ruta}
                      onClick={onNavegar}
                      title={item.descripcion}
                      className={clasesItem}
                    >
                      <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span>{item.etiqueta}</span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
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

import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard, LayoutGrid, Search } from "lucide-react";
import * as React from "react";
import { NavLink, useLocation } from "react-router-dom";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { appDeRuta, gruposDeApp } from "@/components/layout/apps-scope";
import { subPestanasDe } from "@/components/layout/hub-tabs";
import { navegacionParaRol } from "@/components/layout/navegacion";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

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

/** Clases de una SUB-pestaña (indentada, tipografía algo menor que el padre). */
function clasesSubItem({ isActive }: { isActive: boolean }) {
  return cn(
    "flex items-center gap-2 rounded-md py-1.5 pl-9 pr-3 text-[13px] transition-colors",
    isActive
      ? "bg-accent font-medium text-foreground"
      : "font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

/**
 * Barra lateral fija de la consola. Solo se renderiza cuando hay scope que
 * mostrar (dentro de una app o en `/panel`); en el launcher `/` el AppShell no la
 * monta. De arriba a abajo: el avatar, una entrada GLOBAL fija a **Panel**, las
 * secciones de la app actual (cada hub expande sus sub-pestañas indentadas, vía
 * el registro compartido `hub-tabs`) y, al pie, **⊞ Apps** para volver al
 * catálogo. Resalta la ruta activa con el color de acento (shadcn).
 */
export function Sidebar({ onNavegar }: { onNavegar?: () => void }) {
  const { usuario } = useSesion();
  const { pathname } = useLocation();

  // Sidebar DATA-DRIVEN con SCOPE por app (cajón de apps · ADR 0005): se hidrata de
  // `/api/catalogo` (apps activas + su nav, filtradas por los flags del backend).
  // Detectamos la app ACTUAL según el path y mostramos SOLO su nav; sus hubs
  // expanden las sub-pestañas del registro compartido. En `/panel` no hay app: el
  // sidebar queda escueto (Panel activo + Apps). `staleTime: Infinity`: el catálogo
  // solo cambia con un redeploy (flags).
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });

  const apps = catalogoQuery.data?.apps ?? [];
  const appActual = appDeRuta(apps, pathname);
  const grupos = appActual ? gruposDeApp(appActual) : [];
  const navegacion = navegacionParaRol(usuario?.rol === "admin", grupos);

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
        {/* Panel: entrada GLOBAL fija (no es app de catálogo), siempre arriba. */}
        <ul className="space-y-0.5">
          <li>
            <NavLink to="/panel" onClick={onNavegar} className={clasesItem}>
              <LayoutDashboard className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Panel</span>
            </NavLink>
          </li>
        </ul>

        {/* Separador + secciones de la app actual (cada hub expande sus tabs). */}
        {navegacion.length > 0 && (
          <>
            <hr className="border-border" />
            {appActual && (
              <p className="px-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                {appActual.etiqueta}
              </p>
            )}
            {navegacion.map((grupo, idx) => (
              <div key={grupo.etiqueta || `__bloque-${idx}`}>
                {grupo.etiqueta !== "" && (
                  <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    {grupo.etiqueta}
                  </p>
                )}
                <ul className="space-y-0.5">
                  {grupo.items.map((item) => {
                    const Icono = item.icono;
                    const subPestanas = subPestanasDe(item.ruta);
                    return (
                      <li key={item.ruta}>
                        <NavLink
                          to={item.ruta}
                          onClick={onNavegar}
                          title={item.descripcion}
                          // Un hub comparte prefijo con sus sub-rutas: si tiene
                          // sub-pestañas, marca activo solo en match exacto para no
                          // resaltar el padre a la vez que la pestaña.
                          end={subPestanas ? true : undefined}
                          className={clasesItem}
                        >
                          <Icono className="h-4 w-4 shrink-0" />
                          <span>{item.etiqueta}</span>
                        </NavLink>
                        {subPestanas && (
                          <ul className="mt-0.5 space-y-0.5">
                            {subPestanas.map((tab) => {
                              const IconoTab = tab.icono;
                              return (
                                <li key={tab.ruta}>
                                  <NavLink
                                    to={tab.ruta}
                                    end={tab.end}
                                    onClick={onNavegar}
                                    className={clasesSubItem}
                                  >
                                    <IconoTab className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                                    <span>{tab.etiqueta}</span>
                                  </NavLink>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </>
        )}

        {/* Separador + volver al cajón de apps (launcher). Nunca en `/`. */}
        <hr className="border-border" />
        <ul className="space-y-0.5">
          <li>
            <NavLink to="/" onClick={onNavegar} end className={clasesItem}>
              <LayoutGrid className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Apps</span>
            </NavLink>
          </li>
        </ul>
      </div>

      <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
        <span>Herramienta local · 127.0.0.1</span>
        <span className="ml-2 inline-flex items-center rounded-full border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium tracking-wider text-muted-foreground">
          beta
        </span>
      </div>
    </nav>
  );
}

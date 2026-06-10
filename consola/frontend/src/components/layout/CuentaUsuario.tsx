import { ChevronsUpDown, Lightbulb, LogOut, Settings2, UserCog, Users, Webhook } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { useSesion } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";
import type { RolUsuario } from "@/types";

/** Etiqueta legible del rol para mostrar bajo el nombre. */
const ROL_LABEL: Record<RolUsuario, string> = {
  admin: "Administrador",
  editor: "Editor",
};

function etiquetaRol(rol: RolUsuario): string {
  return ROL_LABEL[rol] ?? rol;
}

interface OpcionMenu {
  ruta: string;
  etiqueta: string;
  icono: typeof UserCog;
  /** Si es `true`, solo se muestra para el rol admin. */
  soloAdmin?: boolean;
}

/**
 * Opciones del dropdown del avatar (= "Ajustes"). Se sacaron del sidebar
 * principal para reducir su carga cognitiva: ahora viven aquí, accesibles
 * desde cualquier pantalla con un clic en el avatar.
 */
const OPCIONES: OpcionMenu[] = [
  { ruta: "/mi-cuenta", etiqueta: "Mi cuenta", icono: UserCog },
  { ruta: "/configuracion", etiqueta: "Configuración", icono: Settings2 },
  { ruta: "/sugerencias", etiqueta: "Feedback", icono: Lightbulb },
  { ruta: "/webhooks", etiqueta: "Webhooks", icono: Webhook, soloAdmin: true },
  { ruta: "/usuarios", etiqueta: "Usuarios", icono: Users, soloAdmin: true },
];

/**
 * Bloque de cuenta del sidebar (estilo selector de cuenta de Vercel): avatar con
 * degradado, nombre del usuario actual y su rol. Al pulsarlo abre un menú con
 * los Ajustes (Mi cuenta, Configuración, Sugerencias y -para admin- Usuarios)
 * y la acción "Cerrar sesión" (POST /api/auth/logout → vuelve al login). El
 * usuario sale del contexto de sesión; si todavía no hay (carga), no pinta nada.
 *
 * Con `soloIcono` (rail colapsado) pinta solo el avatar como disparador del
 * menú, sin el nombre/rol ni el chevron.
 */
export function CuentaUsuario({
  className,
  soloIcono = false,
}: {
  className?: string;
  soloIcono?: boolean;
}) {
  const { usuario, cerrarSesion } = useSesion();
  const [abierto, setAbierto] = React.useState(false);
  const [cerrando, setCerrando] = React.useState(false);
  const contenedorRef = React.useRef<HTMLDivElement>(null);

  // Cierra el menú al pulsar fuera o con Escape.
  React.useEffect(() => {
    if (!abierto) return;
    function alPulsarFuera(e: MouseEvent) {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
      }
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);

  if (!usuario) return null;

  async function alCerrarSesion() {
    setCerrando(true);
    setAbierto(false);
    await cerrarSesion();
    // No reseteamos `cerrando`: la pantalla de login reemplaza este árbol.
  }

  const opcionesVisibles = OPCIONES.filter((o) => !o.soloAdmin || usuario.rol === "admin");

  return (
    <div
      ref={contenedorRef}
      className={cn("relative", soloIcono ? "w-auto" : "w-full", className)}
    >
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-label={soloIcono ? `${usuario.usuario} · ${etiquetaRol(usuario.rol)}` : undefined}
        className={cn(
          "flex items-center rounded-md text-left transition-colors hover:bg-accent",
          soloIcono ? "justify-center p-1.5" : "w-full gap-2.5 px-2 py-1.5",
        )}
      >
        {/* Avatar de degradado (estilo Vercel). */}
        <span
          className="h-5 w-5 shrink-0 rounded-full ring-1 ring-border"
          style={{
            backgroundImage: "linear-gradient(135deg, #ff9670 0%, #ff5a1f 45%, #d12d07 100%)",
          }}
          aria-hidden="true"
        />
        {!soloIcono && (
          <>
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate text-sm font-medium text-foreground">
                {usuario.usuario}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {etiquetaRol(usuario.rol)}
              </span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          </>
        )}
      </button>

      {abierto && (
        <div
          role="menu"
          aria-label="Cuenta"
          className={cn(
            "absolute top-full z-50 mt-1 overflow-hidden rounded-md border border-border bg-popover py-1 text-popover-foreground shadow-md",
            soloIcono ? "left-0 w-48" : "left-0 right-0",
          )}
        >
          {opcionesVisibles.map(({ ruta, etiqueta, icono: Icono }) => (
            <Link
              key={ruta}
              to={ruta}
              role="menuitem"
              onClick={() => setAbierto(false)}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-accent"
            >
              <Icono className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              {etiqueta}
            </Link>
          ))}
          <div className="my-1 border-t border-border" aria-hidden="true" />
          <button
            type="button"
            role="menuitem"
            onClick={() => void alCerrarSesion()}
            disabled={cerrando}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-accent disabled:opacity-50"
          >
            <LogOut className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}

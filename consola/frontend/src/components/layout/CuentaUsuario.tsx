import { ChevronsUpDown, LayoutGrid, Lightbulb, LogOut, ServerCog, UserCog, Users, Webhook } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { MenuFlotante, type EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { origenBajoDisparador, type PosicionMenu } from "@/components/comunes/menuPos";
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
  /** Si es `true`, solo se muestra para superadmin (gestión de usuarios). */
  soloSuperadmin?: boolean;
}

/**
 * Opciones del dropdown del avatar (= "Ajustes").
 */
const OPCIONES: OpcionMenu[] = [
  { ruta: "/mi-cuenta", etiqueta: "Mi cuenta", icono: UserCog },
  { ruta: "/sugerencias", etiqueta: "Feedback", icono: Lightbulb },
  { ruta: "/webhooks", etiqueta: "Webhooks", icono: Webhook, soloAdmin: true },
  { ruta: "/marcas", etiqueta: "Marcas", icono: LayoutGrid, soloAdmin: true },
  { ruta: "/usuarios", etiqueta: "Usuarios", icono: Users, soloSuperadmin: true },
  { ruta: "/sistema", etiqueta: "Sistema", icono: ServerCog, soloAdmin: true },
];

/**
 * Bloque de cuenta del sidebar (estilo selector de cuenta de Vercel): avatar con
 * degradado, nombre del usuario actual y su rol. Al pulsarlo abre un menú con
 * los Ajustes (Mi cuenta, Sugerencias, opciones de admin y -solo superadmin- Usuarios)
 * y la acción "Cerrar sesión" (POST /api/auth/logout → vuelve al login). El
 * usuario sale del contexto de sesión; si todavía no hay (carga), no pinta nada.
 *
 * Con `soloIcono` (rail colapsado) pinta solo el avatar como disparador del
 * menú, sin el nombre/rol ni el chevron.
 */
export function CuentaUsuario({
  className,
  soloIcono = false,
  onAbiertoChange,
}: {
  className?: string;
  soloIcono?: boolean;
  /** Avisa cuando el menú abre/cierra (lo usa el sidebar para no colapsar con el menú abierto). */
  onAbiertoChange?: (abierto: boolean) => void;
}) {
  const { usuario, cerrarSesion } = useSesion();
  const navigate = useNavigate();
  // El menú abierto se representa por su posición (null = cerrado). `MenuFlotante` gestiona el
  // cierre al pulsar fuera, con Escape y la navegación por teclado.
  const [pos, setPos] = React.useState<PosicionMenu | null>(null);
  const [cerrando, setCerrando] = React.useState(false);
  const abierto = pos !== null;

  // Notifica el estado del menú hacia arriba (el dock no debe colapsar mientras está abierto).
  React.useEffect(() => {
    onAbiertoChange?.(abierto);
  }, [abierto, onAbiertoChange]);

  if (!usuario) return null;

  async function alCerrarSesion() {
    setCerrando(true);
    setPos(null);
    await cerrarSesion();
    // No reseteamos `cerrando`: la pantalla de login reemplaza este árbol.
  }

  const esSuperadmin = usuario.es_superadmin === true;
  const opcionesVisibles = OPCIONES.filter(
    (o) =>
      (!o.soloAdmin || usuario.rol === "admin") && (!o.soloSuperadmin || esSuperadmin),
  );
  // Nombre humano si lo tiene; si no, el login.
  const nombreMostrar = usuario.nombre?.trim() || usuario.usuario;

  // Ajustes (navegación) + separador + cerrar sesión, como items del menú flotante compartido.
  const items: EntradaMenuContextual[] = [
    ...opcionesVisibles.map(({ ruta, etiqueta, icono }) => ({
      etiqueta,
      icono,
      onClick: () => navigate(ruta),
    })),
    { separador: true },
    {
      etiqueta: "Cerrar sesión",
      icono: LogOut,
      onClick: () => void alCerrarSesion(),
      deshabilitado: cerrando,
    },
  ];

  const alternar = (e: React.MouseEvent) => {
    if (abierto) {
      setPos(null);
      return;
    }
    setPos(origenBajoDisparador(e.currentTarget.getBoundingClientRect()));
  };

  return (
    <div className={cn("relative", soloIcono ? "w-auto" : "w-full", className)}>
      <button
        type="button"
        onClick={alternar}
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-label={soloIcono ? `${nombreMostrar} · ${etiquetaRol(usuario.rol)}` : undefined}
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
                {nombreMostrar}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {etiquetaRol(usuario.rol)}
              </span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          </>
        )}
      </button>

      {pos &&
        createPortal(
          <MenuFlotante
            pos={pos}
            items={items}
            etiqueta="Cuenta"
            onClose={() => setPos(null)}
          />,
          document.body,
        )}
    </div>
  );
}

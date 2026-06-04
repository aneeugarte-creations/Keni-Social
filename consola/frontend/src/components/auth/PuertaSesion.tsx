import { Loader2 } from "lucide-react";

import { PantallaCambiarPassword } from "@/components/auth/PantallaCambiarPassword";
import { PantallaLogin } from "@/components/auth/PantallaLogin";
import { useSesion } from "@/hooks/sesion-contexto";

/** Pantalla de carga a pantalla completa mientras se resuelve el `me` inicial. */
function CargandoSesion() {
  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-background text-muted-foreground">
      <Loader2 className="h-6 w-6 animate-spin" aria-label="Cargando" />
    </div>
  );
}

/**
 * Puerta de sesión: decide qué se renderiza según el estado de la sesión.
 *   - Mientras se resuelve `GET /api/auth/me`: pantalla de carga.
 *   - Sin sesión (401): pantalla de login.
 *   - Con sesión pero `debe_cambiar_password`: cambio de contraseña forzado.
 *   - Con sesión normal: la app (children, es decir el router).
 */
export function PuertaSesion({ children }: { children: React.ReactNode }) {
  const { usuario, cargando } = useSesion();

  if (cargando) return <CargandoSesion />;
  if (!usuario) return <PantallaLogin />;
  if (usuario.debe_cambiar_password) return <PantallaCambiarPassword />;

  return <>{children}</>;
}

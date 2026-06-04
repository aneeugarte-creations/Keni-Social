import { Navigate } from "react-router-dom";

import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";

/**
 * Guard de la pestaña Turnos (rota de cobertura): solo aplica a Claro Sports (separación
 * de contextos multitenant). Para otra marca concreta, Turnos no existe en ese contexto y
 * redirige a Programación (el resto del hub Calendario sí es para todas las marcas). "Todas"
 * (admin) sí puede entrar. Reacciona a cambiar de marca estando dentro: redirige al instante.
 */
export function GuardTurnos({ children }: { children: React.ReactNode }) {
  const { marcaActiva } = useMarcaActiva();
  if (!rutaVisibleParaMarca("/operacion/calendario/turnos", marcaActiva)) {
    return <Navigate to="/operacion/calendario/calendario" replace />;
  }
  return <>{children}</>;
}

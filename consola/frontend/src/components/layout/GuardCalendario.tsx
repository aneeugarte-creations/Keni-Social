import { Navigate, Outlet } from "react-router-dom";

import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";

/**
 * Guard del hub Calendario: solo aplica a Claro Sports (separación de contextos
 * multitenant). Si la marca activa del switch global es otra marca concreta, la sección no
 * existe para ese contexto y redirige al Feed. "Todas" (admin) sí puede entrar. Como lee la
 * marca activa, también reacciona a cambiar de marca estando dentro: redirige al instante.
 */
export function GuardCalendario() {
  const { marcaActiva } = useMarcaActiva();
  if (!rutaVisibleParaMarca("/operacion/calendario", marcaActiva)) {
    return <Navigate to="/operacion/feed" replace />;
  }
  return <Outlet />;
}

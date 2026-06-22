import * as React from "react";

import { PanelActualizando } from "@/components/comunes/PanelActualizando";
import { useSesion } from "@/hooks/sesion-contexto";

/** Cada cuánto reintenta el `me` sola la pantalla degradada (ms). */
const INTERVALO_REINTENTO_MS = 5_000;

/**
 * Estado degradado HONESTO del arranque: el `me` inicial falló por algo que NO es "sin
 * sesión" (red caída, timeout, 502/503/504 mientras el back despliega o cae). En vez de
 * un login engañoso, un 502/403 crudo o una ruedita infinita, mostramos el MISMO panel
 * calmado "Estamos actualizando la consola" que la página de mantenimiento del front, con
 * una barra de progreso y un botón de reintento. Reintentamos solos cada pocos segundos.
 * En cuanto un `me` responde (200 o 401), el provider apaga `errorConexion` y la puerta
 * sale de aquí hacia la app o el login.
 */
export function PantallaDegradada() {
  const { refrescar } = useSesion();
  const [reintentando, setReintentando] = React.useState(false);

  const reintentar = React.useCallback(async () => {
    setReintentando(true);
    try {
      await refrescar();
    } finally {
      setReintentando(false);
    }
  }, [refrescar]);

  // Auto-reintento mientras se muestra esta pantalla: el back puede volver en cualquier
  // momento (fin de un deploy, reinicio); no obligamos al usuario a recargar.
  React.useEffect(() => {
    const id = setInterval(() => {
      void reintentar();
    }, INTERVALO_REINTENTO_MS);
    return () => clearInterval(id);
  }, [reintentar]);

  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-background p-4">
      <PanelActualizando onReintentar={() => void reintentar()} reintentando={reintentando} />
    </div>
  );
}

import { AlertTriangle } from "lucide-react";

import { useConexionDegradada } from "@/lib/estado-red";

/**
 * Banner sticky de conexión degradada DURANTE el uso. Cuando varias queries seguidas fallan
 * por red (sin respuesta o 502/503/504 del proxy, p. ej. un deploy en curso) avisa sin sacar
 * al usuario de su pantalla; el primer éxito de cualquier query lo retira solo (la app sigue
 * reintentando de fondo). El estado vive en `lib/estado-red`, alimentado por el `QueryCache`.
 */
export function BannerConexion() {
  const degradada = useConexionDegradada();
  if (!degradada) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
      <span>Problemas de conexión con la consola. Puede estar actualizándose. Reintentando…</span>
    </div>
  );
}

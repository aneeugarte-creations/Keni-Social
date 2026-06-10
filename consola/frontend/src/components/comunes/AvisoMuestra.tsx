import { Badge } from "@/components/ui/badge";

/**
 * Aviso, no alarmante, de que las cifras en pantalla son de MUESTRA (sintéticas) y
 * no datos reales del cliente. Mientras no haya APIs reales conectadas, todo sale
 * de un modelo determinista; que nadie lo confunda con lo real.
 */
export function AvisoMuestra({
  texto = "Las cifras son de demostración, no datos reales del cliente.",
}: {
  texto?: string;
}) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300"
    >
      <Badge variant="aviso">Datos de muestra (sintéticos)</Badge>
      <span>{texto}</span>
    </div>
  );
}

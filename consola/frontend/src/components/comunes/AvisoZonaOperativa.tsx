import { Aviso } from "@/components/comunes/Aviso";
import {
  ETIQUETA_ZONA_OPERATIVA,
  etiquetaZona,
  zonaDisplay,
  zonaDisplayDifiereDeOperativa,
} from "@/lib/fecha";

/**
 * Aviso de DESAJUSTE de zona: recuerda que los horarios OPERATIVOS (publicación, parrilla,
 * turnos) van en la zona del equipo (CDMX), NO en la zona de display que el usuario configuró
 * en su cuenta. Solo se pinta cuando ambas difieren; en el caso normal (equipo en CDMX) no
 * renderiza nada. Así, quien cambia su zona sabe que esta pantalla usa otra por defecto.
 *
 * `que` personaliza el sujeto ("Estos horarios" por defecto): p. ej. "La hora de publicación".
 */
export function AvisoZonaOperativa({ que = "Estos horarios", className }: { que?: string; className?: string }) {
  if (!zonaDisplayDifiereDeOperativa()) return null;
  // Etiqueta de la zona de display del usuario (p. ej. "GMT+2"); el `Date` actual basta para el offset.
  const tuZona = etiquetaZona(new Date()) || zonaDisplay();
  return (
    <Aviso className={className}>
      {que} van en <strong>{ETIQUETA_ZONA_OPERATIVA}</strong>, la zona del equipo — no en tu zona
      de visualización ({tuZona}).
    </Aviso>
  );
}

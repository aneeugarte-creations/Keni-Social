/**
 * Aviso NO FATAL de "contract drift" en producción.
 *
 * Cuando una respuesta del backend no cumple el contrato (`esquema.gen.json`) y NO
 * estamos en DEV, la validación no debe romper la página: solo deja constancia.
 * Aquí se centraliza ese aviso: un log ESTRUCTURADO (para soporte/telemetría) y un
 * toast no bloqueante. El toast se THROTTLEA por contrato (un poll de una lista
 * podría disparar el mismo drift muchas veces por minuto) para no inundar la UI.
 */
import { toast } from "sonner";

// Una entrada de toast por contrato cada `_VENTANA_MS` (el log sí sale siempre).
const _ULTIMO_TOAST = new Map<string, number>();
const _VENTANA_MS = 60_000;

function _debeAvisar(contrato: string): boolean {
  const ahora = Date.now();
  const previo = _ULTIMO_TOAST.get(contrato) ?? 0;
  if (ahora - previo < _VENTANA_MS) return false;
  _ULTIMO_TOAST.set(contrato, ahora);
  return true;
}

/**
 * Registra un drift de contrato sin romper la ejecución. Log estructurado siempre;
 * toast como mucho una vez por minuto y contrato.
 */
export function avisarDriftContrato(contrato: string, errores: string[]): void {
  // Log estructurado: fácil de filtrar en consola/telemetría.
  console.warn("[contract-drift]", { contrato, errores });
  if (!_debeAvisar(contrato)) return;
  try {
    toast.warning("Aviso técnico: una respuesta no coincide con el contrato esperado.", {
      description: `Contrato «${contrato}». La página sigue funcionando; revisa la consola.`,
    });
  } catch {
    // Sin toaster montado (p. ej. en un test): el log basta.
  }
}

/**
 * Elegibilidad del OK humano ("me gusta") de una pieza, a partir de su cadena de aprobación.
 *
 * Las reglas las DECIDE el backend (los dos OK los dan dos personas DISTINTAS —el autor
 * incluido, puede dar uno de los dos—; cualquiera del equipo puede darlo, sin requisito de
 * cargo; el OK humano solo cuando toca su nivel, no mientras la IA verifica). Aquí solo
 * REPLICAMOS esas reglas para habilitar/deshabilitar el botón y explicar por qué, antes de
 * pedirlo. La fuente de verdad sigue siendo el servidor.
 */
import type { CadenaAprobacion, NivelAprobacion } from "@/types";

/** Niveles AUTOMÁTICOS, fuera del flujo del OK humano: la PRE-aprobación verificación (por su etiqueta) y la
 *  CRÍTICA IA final (por su cargo reservado, espejo de `colaboracion.CARGO_IA_CRITICO`). Cuando el
 *  nivel ACTUAL es uno de estos, el botón de OK humano no aplica (lo decide la máquina). */
const ETIQUETA_REVISION = "revision";
const CARGO_IA_CRITICO = "ia-critico";
const esNivelIA = (n: NivelAprobacion) =>
  n.etiqueta.trim().toLowerCase() === ETIQUETA_REVISION ||
  (n.cargo_requerido ?? "").trim().toLowerCase() === CARGO_IA_CRITICO;

export interface Elegibilidad {
  /** ¿Puede ESTE usuario dar su OK ahora mismo? (habilita el botón "Me gusta"). */
  puedeDar: boolean;
  /** Por qué NO puede, en una frase (tooltip del botón deshabilitado). "" si sí puede. */
  motivo: string;
}

/**
 * ¿Puede `usuario` dar el OK humano a la pieza cuya cadena es `cadena`?
 *
 * `cadena` undefined (aún cargando o pieza sin cadena) => no se puede (sin motivo: no es un
 * bloqueo, es que todavía no aplica). El autor SÍ puede dar uno de los dos OK; el único
 * requisito es que los dos los den personas distintas ("ya diste tu OK" bloquea repetir).
 */
export function elegibilidadOK(
  cadena: CadenaAprobacion | undefined,
  usuario: { id?: string } | null | undefined,
): Elegibilidad {
  if (!cadena || (cadena.niveles?.length ?? 0) === 0) return { puedeDar: false, motivo: "" };
  const niveles = cadena.niveles;
  const humanos = niveles.filter((n) => !esNivelIA(n));
  const nivelActual = niveles.find((n) => n.id === cadena.nivel_actual) ?? null;

  const yaDioOK = !!usuario?.id && humanos.some((n) => n.decisor_id === usuario.id);
  const tocaHumano = !!nivelActual && !esNivelIA(nivelActual);

  // Dos personas DISTINTAS: "ya diste tu OK" bloquea repetir (el segundo par de ojos no vale si es
  // la misma persona). El autor NO está bloqueado: puede dar uno de los dos OK (espeja el backend).
  if (yaDioOK)
    return { puedeDar: false, motivo: "Ya diste tu OK; falta el de otra persona." };
  if (nivelActual && !tocaHumano)
    return { puedeDar: false, motivo: "Esperando la verificación de la IA antes del OK del equipo." };

  const puedeDar = !!nivelActual && tocaHumano && !yaDioOK;
  return { puedeDar, motivo: "" };
}

/**
 * UMBRAL de dislikes que rechaza la pieza: dos (de dos personas), o tantos como niveles
 * humanos tenga una cadena más corta. Espeja `dominio.colaboracion.umbral_rechazo` del
 * backend — FUENTE ÚNICA en frontend (la consume también el panel `CadenaAprobacion`).
 */
export function umbralDislikes(cadena: Pick<CadenaAprobacion, "niveles">): number {
  const humanos = (cadena.niveles ?? []).filter((n) => !esNivelIA(n));
  return Math.min(2, humanos.length || 1);
}

/**
 * ¿El PRÓXIMO dislike rechaza la pieza (la devuelve a redacción y resetea la cadena)?
 * Es el gate de la confirmación del botón "No me gusta": el dislike decisivo es
 * irreversible con un clic y los OK ya dados se pierden.
 */
export function esDislikeDecisivo(cadena: Pick<CadenaAprobacion, "niveles">): boolean {
  const humanos = (cadena.niveles ?? []).filter((n) => !esNivelIA(n));
  const disDados = humanos.filter((n) => n.decision === "rechazado");
  return disDados.length + 1 >= umbralDislikes(cadena);
}

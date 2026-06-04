/**
 * Elegibilidad del OK humano ("me gusta") de una pieza, a partir de su cadena de aprobación.
 *
 * Las reglas las DECIDE el backend (no apruebas tu propia pieza; cada OK lo da una persona
 * distinta; el OK humano solo cuando toca su nivel, no mientras la IA verifica). Aquí solo
 * REPLICAMOS esas reglas para habilitar/deshabilitar el botón y explicar por qué, antes de
 * pedirlo. La fuente de verdad sigue siendo el servidor.
 */
import type { CadenaAprobacion, NivelAprobacion } from "@/types";

/** El nivel automático de IA (QA Editorial) se reconoce por su etiqueta reservada. */
const ETIQUETA_QA = "qa editorial";
const esNivelIA = (n: NivelAprobacion) => n.etiqueta.trim().toLowerCase() === ETIQUETA_QA;

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
 * bloqueo, es que todavía no aplica). Admin puede desatascar (salta autor / "ya dio OK").
 */
export function elegibilidadOK(
  cadena: CadenaAprobacion | undefined,
  usuario: { id?: string; rol?: string } | null | undefined,
  autorPiezaId: string,
): Elegibilidad {
  if (!cadena || (cadena.niveles?.length ?? 0) === 0) return { puedeDar: false, motivo: "" };
  const niveles = cadena.niveles;
  const humanos = niveles.filter((n) => !esNivelIA(n));
  const nivelActual = niveles.find((n) => n.id === cadena.nivel_actual) ?? null;

  const esAdmin = usuario?.rol === "admin";
  const esAutor = !!usuario?.id && !!autorPiezaId && usuario.id === autorPiezaId;
  const yaDioOK = !!usuario?.id && humanos.some((n) => n.decisor_id === usuario.id);
  const tocaHumano = !!nivelActual && !esNivelIA(nivelActual);

  // "Ya diste tu OK" bloquea a TODOS, incluido el admin: el segundo par de ojos no vale si es la
  // misma persona (espeja la regla del backend). El admin solo desatasca aprobar SU propia pieza.
  if (yaDioOK)
    return { puedeDar: false, motivo: "Ya diste tu OK; falta el de otra persona." };
  if (!esAdmin && esAutor)
    return { puedeDar: false, motivo: "No puedes dar OK a tu propia pieza; el OK lo da otra persona." };
  if (nivelActual && !tocaHumano)
    return { puedeDar: false, motivo: "Esperando la verificación de la IA antes del OK del equipo." };

  const puedeDar = !!nivelActual && tocaHumano && !yaDioOK && (esAdmin || !esAutor);
  return { puedeDar, motivo: "" };
}

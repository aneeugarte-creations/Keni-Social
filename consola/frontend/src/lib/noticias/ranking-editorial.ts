/**
 * Ranking EDITORIAL — traduce las señales del motor a lenguaje de redacción.
 *
 * El equipo de redes no piensa en "score 0.82": piensa en "la confirmaron Reuters y BBC
 * hace 15 minutos". Estas funciones PURAS arman la frase de corroboración de la tarjeta,
 * el nivel de prioridad (alta/media/baja, nunca el número crudo) y la explicación
 * "¿por qué rankea así?" a partir del contrato `Historia` (timeline de fuentes +
 * score_desglose que persiste el daemon).
 */

import { tiempoRelativo } from "@/lib/fecha";
import type { FuenteHistoria, Historia } from "@/types";

/** Nivel de prioridad legible (la posición en la sección ya comunica el orden fino). */
export function nivelPrioridad(score: number): "alta" | "media" | "baja" {
  if (score >= 0.5) return "alta";
  if (score >= 0.3) return "media";
  return "baja";
}

/** Timeline de fuentes de la historia; cae a los enlaces si el back aún no manda `fuentes`. */
function fuentesDe(h: Historia): FuenteHistoria[] {
  if (h.fuentes && h.fuentes.length > 0) return h.fuentes;
  const vistas = new Set<string>();
  const salida: FuenteHistoria[] = [];
  for (const e of h.enlaces ?? []) {
    const nombre = (e.fuente || "").trim();
    if (!nombre || vistas.has(nombre)) continue;
    vistas.add(nombre);
    salida.push({
      fuente: nombre,
      fuente_id: "",
      peso: e.tier === "potente" ? 2 : 1,
      tier: e.tier ?? "normal",
      primer_visto: e.publicado_en ?? "",
      n_items: 1,
    });
  }
  return salida;
}

/** "Reuters, AP y Milenio" (hasta `max` nombres; el resto como "+2"). */
function listaNombres(fuentes: FuenteHistoria[], max = 3): string {
  const nombres = fuentes.map((f) => f.fuente).filter(Boolean);
  const visibles = nombres.slice(0, max);
  const resto = nombres.length - visibles.length;
  let texto =
    visibles.length <= 1
      ? (visibles[0] ?? "")
      : `${visibles.slice(0, -1).join(", ")} y ${visibles[visibles.length - 1]}`;
  if (resto > 0) texto += ` (+${resto})`;
  return texto;
}

/**
 * La FRASE de corroboración de la tarjeta — sustituye a la nube de badges:
 *   - "Reuters y AP la confirmaron casi a la vez"  (última hora)
 *   - "Confirmada por Reuters, Milenio y El Universal · la abrió Reuters hace 42 min"
 *   - "Única fuente: Récord · hace 1 h — espera corroboración"
 *   - "Señal dudosa: única fuente no confiable o titular sensacionalista"
 */
export function fraseCorroboracion(h: Historia): string {
  if (h.verificacion === "dudosa") {
    return "Señal dudosa: única fuente no confiable o titular sensacionalista";
  }
  const fuentes = fuentesDe(h);
  if (h.n_fuentes <= 1) {
    const nombre = fuentes[0]?.fuente || h.primera_fuente_nombre || "una fuente";
    const hace = h.ultimo_visto ? ` · ${tiempoRelativo(h.ultimo_visto)}` : "";
    return `Única fuente: ${nombre}${hace} — espera corroboración`;
  }
  const potentes = fuentes.filter((f) => f.tier === "potente");
  if (h.breaking === 1 && potentes.length >= 2) {
    return `${listaNombres(potentes)} la confirmaron casi a la vez`;
  }
  let frase = `Confirmada por ${listaNombres(fuentes)}`;
  const primera = fuentes[0]?.fuente || h.primera_fuente_nombre;
  const abierta = fuentes[0]?.primer_visto || h.primer_visto;
  if (primera && abierta) frase += ` · la abrió ${primera} ${tiempoRelativo(abierta)}`;
  if (h.ultimo_visto && h.ultimo_visto !== abierta) {
    frase += ` · última ${tiempoRelativo(h.ultimo_visto)}`;
  }
  return frase;
}

/**
 * "¿Por qué rankea así?" — el desglose del score traducido a frases editoriales (una por
 * señal activa). Es el tooltip del punto de prioridad y la lista del detalle.
 */
export function factoresRanking(h: Historia): string[] {
  const d = h.score_desglose ?? {};
  const factores: string[] = [];
  if (h.n_fuentes > 1) {
    factores.push(`La confirman ${h.n_fuentes} medios`);
  }
  if ((d.velocidad ?? 0) >= 0.4) {
    factores.push("Está creciendo rápido: varias fuentes se sumaron en poco tiempo");
  }
  if ((d.frescura ?? 0) >= 0.5 && h.ultimo_visto) {
    factores.push(`Es fresca: la última nota es de ${tiempoRelativo(h.ultimo_visto)}`);
  }
  if ((d.viralidad ?? 0) >= 0.3) {
    factores.push("Trae señal de viralidad (se está moviendo en redes)");
  }
  if (d.palabras && d.palabras.length > 0) {
    factores.push(`Encaja con la marca por: ${d.palabras.slice(0, 5).join(", ")}`);
  }
  if (factores.length === 0) {
    factores.push(h.score_razon || "Historia única, sin señales fuertes todavía");
  }
  return factores;
}

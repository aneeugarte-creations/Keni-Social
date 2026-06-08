/**
 * Panel de ESTADO de la aprobación de una pieza (la cara amable de la cadena), como en una red
 * social interna. SOLO MUESTRA estado —la acción (dar OK / rechazar) vive en la fila de acciones
 * del post (`PostFeed`), igual que el "me gusta" y "comentar"—:
 *
 *   - Un veredicto de IA arriba (QA Editorial): 🟢 lista · 🟡 revisar · 🔴 no publicar.
 *   - Los OK del equipo como "likes": cuántos van (p. ej. "OK 1/2") y DE QUIÉN.
 *   - El desenlace: "Lista para publicar" (cadena aprobada) · "Rechazada" (vuelve a redacción) ·
 *     o cuántos OK faltan.
 *
 * Componente PURO de presentación: sin estado, sin mutaciones, sin sesión. El gate (no apruebas
 * tu propia pieza, "otro par de ojos") lo resuelven el backend y `elegibilidadOK` (sobre el botón
 * de la fila de acciones). NO crea backend.
 */
import { Check, Sparkles } from "lucide-react";

import type { CadenaAprobacion as TCadena, NivelAprobacion } from "@/types";

/** El nivel automático de IA (QA Editorial) se reconoce por su etiqueta reservada. */
const ETIQUETA_QA = "qa editorial";
const esNivelIA = (n: NivelAprobacion) => n.etiqueta.trim().toLowerCase() === ETIQUETA_QA;

/** Semáforo de la "aprobación de IA": del nivel QA de la cadena, o del veredicto suelto. */
function pintaIA(
  nivelIA: NivelAprobacion | undefined,
  veredicto: string | undefined,
): { emoji: string; texto: string; clase: string } | null {
  // Si hay nivel QA en la cadena, su decisión manda; si no, el último veredicto de la pieza.
  const v = nivelIA
    ? nivelIA.decision === "aprobado"
      ? "listo"
      : nivelIA.decision === "rechazado"
        ? "no_publicar"
        : "revisar"
    : (veredicto || "").trim().toLowerCase();
  if (v === "listo") return { emoji: "🟢", texto: "IA: lista", clase: "text-emerald-600 dark:text-emerald-400" };
  if (v === "no_publicar") return { emoji: "🔴", texto: "IA: no publicar", clase: "text-red-600 dark:text-red-400" };
  if (v === "revisar") return { emoji: "🟡", texto: "IA: revisar", clase: "text-amber-600 dark:text-amber-400" };
  return null; // sin veredicto: no afirmamos nada sobre la IA.
}

export function CadenaAprobacion({
  cadena,
  veredictoIA,
}: {
  cadena: TCadena;
  /** Veredicto de QA suelto (cuando la IA no es un nivel de la cadena). Pinta el semáforo. */
  veredictoIA?: string;
}) {
  const niveles = [...cadena.niveles].sort((a, b) => a.nivel - b.nivel);
  const humanos = niveles.filter((n) => !esNivelIA(n));
  const nivelIA = niveles.find(esNivelIA);
  const okDados = humanos.filter((n) => n.decision === "aprobado");
  const disDados = humanos.filter((n) => n.decision === "rechazado");
  const totalOK = humanos.length || 1;
  // Dos dislikes (de dos personas) rechazan la pieza; en una cadena más corta basta con tantos
  // como niveles tenga. Espeja `dominio.colaboracion.umbral_rechazo`.
  const umbralDislike = Math.min(2, humanos.length || 1);
  const ia = pintaIA(nivelIA, veredictoIA);

  const lista = cadena.estado === "aprobado";
  const rechazada = cadena.estado === "rechazado";

  return (
    <section className="border-t border-border px-4 py-3" aria-label="Estado de aprobación de la pieza">
      {/* Veredicto de IA (la "aprobación de IA"). */}
      {ia && (
        <p className={"mb-2 flex items-center gap-1.5 text-xs font-medium " + ia.clase}>
          <Sparkles className="h-3.5 w-3.5" />
          {ia.emoji} {ia.texto}
        </p>
      )}

      {/* Los OK del equipo: solo el conteo (auto-explicativo) y de quién. Sin etiqueta "OK" ni
          icono: el "x/total" basta. */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className="font-medium tabular-nums">
          {okDados.length}/{totalOK}
        </span>
        {okDados.length > 0 && (
          <span className="text-muted-foreground">
            · {okDados.map((n) => n.decisor_nombre || "alguien").join(", ")}
          </span>
        )}
      </div>

      {/* Los dislikes acumulados (solo si hay alguno): dos rechazan la pieza. MISMO estilo que el
          conteo de OK (solo "x/total" + de quién), pero en ROJO para distinguirlos; sin etiqueta
          "Dislikes" ni icono. */}
      {disDados.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span className="font-medium tabular-nums text-red-600 dark:text-red-400">
            {disDados.length}/{umbralDislike}
          </span>
          <span className="text-muted-foreground">
            · {disDados.map((n) => n.decisor_nombre || "alguien").join(", ")}
          </span>
        </div>
      )}

      {/* Desenlace de la cadena. */}
      {lista ? (
        <p className="mt-2 flex items-center gap-1.5 text-sm font-medium text-emerald-600 dark:text-emerald-400">
          <Check className="h-4 w-4" />
          Lista para publicar
        </p>
      ) : rechazada ? (
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">
          Rechazada; la pieza vuelve a la redacción.
        </p>
      ) : null}
    </section>
  );
}

/**
 * Panel de ESTADO de la aprobación de una pieza (la cara amable de la cadena), como en una red
 * social interna. SOLO MUESTRA estado —la acción (dar OK / rechazar) vive en la fila de acciones
 * del post (`PostFeed`), igual que el "me gusta" y "comentar"—:
 *
 *   - Un veredicto de IA arriba (QA Editorial), como Badge ok/aviso/error: lista · revisar ·
 *     no publicar (mismas variantes que `META_VEREDICTOS`).
 *   - Los OK del equipo como "likes": cuántos van (p. ej. "OK 1/2") y DE QUIÉN.
 *   - El desenlace: "Lista para publicar" (cadena aprobada) · "Rechazada" (vuelve a redacción) ·
 *     o cuántos OK faltan.
 *
 * Componente PURO de presentación: sin estado, sin mutaciones, sin sesión. El gate (no apruebas
 * tu propia pieza, "otro par de ojos") lo resuelven el backend y `elegibilidadOK` (sobre el botón
 * de la fila de acciones). NO crea backend.
 */
import { Check, Loader2, MessageSquare, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { plural } from "@/lib/formato";
import type { CadenaAprobacion as TCadena, NivelAprobacion } from "@/types";

import { TEXTO_ERROR, TEXTO_OK } from "./formato";

/** El nivel automático de IA (QA Editorial) se reconoce por su etiqueta reservada. */
const ETIQUETA_QA = "qa editorial";
const esNivelIA = (n: NivelAprobacion) => n.etiqueta.trim().toLowerCase() === ETIQUETA_QA;

/** Veredicto de la "aprobación de IA": del nivel QA de la cadena, o del veredicto suelto. */
function pintaIA(
  nivelIA: NivelAprobacion | undefined,
  veredicto: string | undefined,
): { texto: string; variante: "ok" | "aviso" | "error" } | null {
  // Si hay nivel QA en la cadena, su decisión manda; si no, el último veredicto de la pieza.
  const v = nivelIA
    ? nivelIA.decision === "aprobado"
      ? "listo"
      : nivelIA.decision === "rechazado"
        ? "no_publicar"
        : "revisar"
    : (veredicto || "").trim().toLowerCase();
  if (v === "listo") return { texto: "IA: lista", variante: "ok" };
  if (v === "no_publicar") return { texto: "IA: no publicar", variante: "error" };
  if (v === "revisar") return { texto: "IA: revisar", variante: "aviso" };
  return null; // sin veredicto: no afirmamos nada sobre la IA.
}

export function CadenaAprobacion({
  cadena,
  veredictoIA,
  sinResolver = 0,
  onForzar,
  forzando = false,
}: {
  cadena: TCadena;
  /** Veredicto de QA suelto (cuando la IA no es un nivel de la cadena). Pinta el badge. */
  veredictoIA?: string;
  /** Comentarios sin resolver: > 0 añade la línea de bloqueo dentro del panel ("lo que falta"). */
  sinResolver?: number;
  /** Override admin/coordinador: si llega y la cadena sigue abierta, pinta al pie el botón
   *  discreto "Forzar aprobación" (la confirmación la pone el llamador). */
  onForzar?: () => void;
  /** Mutación de forzar en vuelo: deshabilita el botón (sin segundo clic que reabra el
   *  confirm) y pinta el spinner. */
  forzando?: boolean;
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
      {/* Veredicto de IA (la "aprobación de IA"), con las variantes de META_VEREDICTOS. */}
      {ia && (
        <Badge variant={ia.variante} className="mb-2 gap-1">
          <Sparkles className="h-3 w-3" aria-hidden="true" />
          {ia.texto}
        </Badge>
      )}

      {/* Los OK del equipo: el conteo con su icono (no solo color) y de quién. */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span
          className="inline-flex items-center gap-1 font-medium tabular-nums"
          title={`OK del equipo: ${okDados.length} de ${totalOK}`}
          aria-label={`OK del equipo: ${okDados.length} de ${totalOK}`}
        >
          <ThumbsUp className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          {okDados.length}/{totalOK}
        </span>
        {okDados.length > 0 && (
          <span className="text-muted-foreground">
            · {okDados.map((n) => n.decisor_nombre || "alguien").join(", ")}
          </span>
        )}
      </div>

      {/* Los dislikes acumulados (solo si hay alguno): dos rechazan la pieza. MISMO patrón que el
          conteo de OK (icono + "x/total" + de quién), en ROJO para distinguirlos. */}
      {disDados.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span
            className={`inline-flex items-center gap-1 font-medium tabular-nums ${TEXTO_ERROR}`}
            title={`Dislikes: ${disDados.length} de ${umbralDislike}`}
            aria-label={`Dislikes: ${disDados.length} de ${umbralDislike}`}
          >
            <ThumbsDown className="h-3.5 w-3.5" aria-hidden="true" />
            {disDados.length}/{umbralDislike}
          </span>
          <span className="text-muted-foreground">
            · {disDados.map((n) => n.decisor_nombre || "alguien").join(", ")}
          </span>
        </div>
      )}

      {/* Desenlace de la cadena. */}
      {lista ? (
        <p className={`mt-2 flex items-center gap-1.5 text-sm font-medium ${TEXTO_OK}`}>
          <Check className="h-4 w-4" />
          Lista para publicar
        </p>
      ) : rechazada ? (
        <p className={`mt-2 text-sm ${TEXTO_ERROR}`}>
          Rechazada; la pieza vuelve a la redacción.
        </p>
      ) : null}

      {/* Lo que falta: comentarios sin resolver (bloquean publicar, como en un PR). */}
      {sinResolver > 0 && (
        <p className="mt-2 flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-300">
          <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
          Falta resolver {plural(sinResolver, "comentario")} antes de publicar
        </p>
      )}

      {/* Override (admin/coordinador): discreto, al pie, fuera del camino del doble clic del
          like. Solo mientras la cadena siga abierta. Botón real (target ≥24px, WCAG 2.5.8);
          el margen negativo compensa el padding para no mover el texto del pie. */}
      {onForzar && !lista && !rechazada && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onForzar}
          disabled={forzando}
          className="-mx-2 mt-1 h-8 px-2 text-xs text-muted-foreground hover:text-foreground"
        >
          {forzando && <Loader2 className="h-3 w-3 animate-spin" />}
          Forzar aprobación (saltar la cadena)
        </Button>
      )}
    </section>
  );
}

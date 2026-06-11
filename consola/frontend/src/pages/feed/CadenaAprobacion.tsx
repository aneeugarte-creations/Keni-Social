/**
 * Panel de ESTADO de la aprobación de una pieza (la cara amable de la cadena), como en una red
 * social interna. SOLO MUESTRA estado —la acción (dar OK / rechazar) vive en la fila de acciones
 * del post (`PostFeed`), igual que el "me gusta" y "comentar"—:
 *
 *   - Los OK del equipo como "likes": cuántos van (p. ej. "OK 1/2") y DE QUIÉN.
 *   - El desenlace: "Lista para publicar" (cadena aprobada) · "Rechazada" (vuelve a redacción) ·
 *     o cuántos OK faltan.
 *
 * NO se muestra el veredicto de IA (QA Editorial): de cara al equipo, menos IA — el feed enseña
 * solo decisiones humanas y lo que falta. El nivel QA sigue EXISTIENDO en la cadena (lo filtramos
 * de los "humanos"), solo no se pinta como badge.
 *
 * Componente PURO de presentación: sin estado, sin mutaciones, sin sesión. El gate (no apruebas
 * tu propia pieza, "otro par de ojos") lo resuelven el backend y `elegibilidadOK` (sobre el botón
 * de la fila de acciones). NO crea backend.
 */
import { Check, MessageSquare, ThumbsDown, ThumbsUp } from "lucide-react";

import { plural } from "@/lib/formato";
import type { CadenaAprobacion as TCadena, NivelAprobacion } from "@/types";

import { umbralDislikes } from "./aprobacion";
import { TEXTO_AVISO, TEXTO_ERROR, TEXTO_OK } from "./formato";

/** El nivel automático de IA (QA Editorial) se reconoce por su etiqueta reservada: se EXCLUYE del
 *  conteo de OK humanos (no se pinta su veredicto). */
const ETIQUETA_QA = "qa editorial";
const esNivelIA = (n: NivelAprobacion) => n.etiqueta.trim().toLowerCase() === ETIQUETA_QA;

export function CadenaAprobacion({
  cadena,
  sinResolver = 0,
}: {
  cadena: TCadena;
  /** Comentarios sin resolver: > 0 añade la línea de bloqueo dentro del panel ("lo que falta"). */
  sinResolver?: number;
}) {
  const niveles = [...cadena.niveles].sort((a, b) => a.nivel - b.nivel);
  const humanos = niveles.filter((n) => !esNivelIA(n));
  const okDados = humanos.filter((n) => n.decision === "aprobado");
  const disDados = humanos.filter((n) => n.decision === "rechazado");
  const totalOK = humanos.length || 1;
  // Dos dislikes (de dos personas) rechazan la pieza; la regla vive en `aprobacion.ts`
  // (fuente única, junto a `esDislikeDecisivo`).
  const umbralDislike = umbralDislikes(cadena);

  const lista = cadena.estado === "aprobado";
  const rechazada = cadena.estado === "rechazado";

  return (
    <section className="border-t border-border px-4 py-3" aria-label="Estado de aprobación de la pieza">
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
        <p className={`mt-2 flex items-center gap-1.5 text-sm ${TEXTO_AVISO}`}>
          <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
          Falta resolver {plural(sinResolver, "comentario")} antes de publicar
        </p>
      )}

      {/* El override de forzar (admin/coordinación) ya no vive aquí: se ofrece en el toast
          del primer OK (PostFeed), con su confirmación. El panel queda solo-estado. */}
    </section>
  );
}

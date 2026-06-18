/**
 * Panel de ESTADO de la aprobación de una pieza (la cara amable de la cadena), como en una red
 * social interna. SOLO MUESTRA estado —la acción (dar OK / rechazar) vive en la fila de acciones
 * del post (`PostFeed`), igual que el "me gusta" y "comentar"—:
 *
 *   - Los OK del equipo como "likes": cuántos van (p. ej. "OK 1/2") y DE QUIÉN.
 *   - El desenlace: "Lista para publicar" (cadena aprobada) · "Rechazada" (vuelve a redacción) ·
 *     o cuántos OK faltan.
 *
 * NO se muestra el revision de la PRE-aprobación de IA (verificación Editorial): de cara al equipo, menos
 * IA — el feed enseña solo decisiones humanas y lo que falta. El nivel verificación sigue EXISTIENDO en la
 * cadena (lo filtramos de los "humanos"), solo no se pinta como badge.
 *
 * SÍ se muestra, en cambio, el estado de la CRÍTICA IA (nivel automático AL FINAL, tras los dos
 * OK humanos): "En crítica IA…" mientras el crítico revisa, y un aviso si rechazó la pieza. Es la
 * última red antes de programar; el equipo necesita verla (y su comentario, vía `sinResolver`).
 * Ambos niveles automáticos se EXCLUYEN del conteo de OK humanos.
 *
 * Componente PURO de presentación: sin estado, sin mutaciones, sin sesión. El gate ("otro par
 * de ojos": dos personas distintas, el autor incluido) lo resuelven el backend y `elegibilidadOK`
 * (sobre el botón de la fila de acciones). NO crea backend.
 */
import { Bot, Check, MessageSquare, ThumbsDown, ThumbsUp } from "lucide-react";

import { plural } from "@/lib/formato";
import type { CadenaAprobacion as TCadena, NivelAprobacion } from "@/types";

import { umbralDislikes } from "./aprobacion";
import { TEXTO_AVISO, TEXTO_ERROR, TEXTO_OK } from "./formato";

/** PRE-aprobación de IA (verificación Editorial), por su etiqueta reservada: se EXCLUYE del conteo de OK
 *  humanos y no se pinta su revision (menos IA de cara al equipo). */
const ETIQUETA_REVISION = "revision";
const esNivelRevision = (n: NivelAprobacion) => n.etiqueta.trim().toLowerCase() === ETIQUETA_REVISION;

/** CRÍTICA IA (nivel automático AL FINAL): se reconoce por su cargo reservado (espejo del backend
 *  `colaboracion.CARGO_IA_CRITICO`). Se EXCLUYE del conteo humano, pero SÍ se muestra su estado. */
const CARGO_IA_CRITICO = "ia-critico";
const esCriticaIA = (n: NivelAprobacion) =>
  (n.cargo_requerido ?? "").trim().toLowerCase() === CARGO_IA_CRITICO;

/** Cualquier nivel AUTOMÁTICO (pre-aprobación verificación o crítica final): fuera del conteo de OK humanos. */
const esNivelAutomatico = (n: NivelAprobacion) => esNivelRevision(n) || esCriticaIA(n);

export function CadenaAprobacion({
  cadena,
  sinResolver = 0,
}: {
  cadena: TCadena;
  /** Comentarios sin resolver: > 0 añade la línea de bloqueo dentro del panel ("lo que falta"). */
  sinResolver?: number;
}) {
  const niveles = [...cadena.niveles].sort((a, b) => a.nivel - b.nivel);
  const humanos = niveles.filter((n) => !esNivelAutomatico(n));
  const okDados = humanos.filter((n) => n.decision === "aprobado");
  const disDados = humanos.filter((n) => n.decision === "rechazado");
  const totalOK = humanos.length || 1;
  // Crítica IA: existe solo si el flag la añadió. Su estado se enseña cuando los humanos ya
  // cerraron su parte (entonces el crítico está revisando / ya votó); antes no se anuncia.
  const ia = niveles.find(esCriticaIA);
  const humanosOk = humanos.length > 0 && humanos.every((n) => n.decision === "aprobado");
  const criticaEnCurso = !!ia && humanosOk && ia.decision === "pendiente";
  const criticaRechazo = !!ia && ia.decision === "rechazado";
  // Crítica IA aprobada = su "like" (el 3er OK, el de la máquina): se muestra explícito para que el
  // equipo vea que la IA también dio el visto bueno, no solo el desenlace "Lista para publicar".
  const criticaAprobada = !!ia && ia.decision === "aprobado";
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

      {/* Crítica IA (última red antes de programar): en curso o rechazó la pieza. El detalle del
          problema llega como comentario sin resolver (línea de abajo). */}
      {criticaEnCurso && (
        <p className="mt-2 flex items-center gap-1.5 text-sm text-muted-foreground">
          <Bot className="h-3.5 w-3.5 animate-pulse" aria-hidden="true" />
          En crítica IA…
        </p>
      )}
      {criticaRechazo && (
        <p className={`mt-2 flex items-center gap-1.5 text-sm font-medium ${TEXTO_AVISO}`}>
          <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          La crítica IA rechazó esta pieza; revisa el comentario.
        </p>
      )}
      {criticaAprobada && (
        <p className={`mt-2 flex items-center gap-1.5 text-sm font-medium ${TEXTO_OK}`}>
          <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          Crítica IA: aprobada
        </p>
      )}

      {/* Desenlace de la cadena. */}
      {lista ? (
        <p className={`mt-2 flex items-center gap-1.5 text-sm font-medium ${TEXTO_OK}`}>
          <Check className="h-4 w-4" />
          Lista para publicar
        </p>
      ) : rechazada ? (
        <p className={`mt-2 text-sm ${TEXTO_ERROR}`}>
          Rechazada
        </p>
      ) : null}

      {/* Lo que falta: comentarios sin resolver (bloquean publicar, como en un PR). */}
      {sinResolver > 0 && (
        <p className={`mt-2 flex items-center gap-1.5 text-sm ${TEXTO_AVISO}`}>
          <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
          Resuelve {plural(sinResolver, "comentario")} antes de publicar
        </p>
      )}
    </section>
  );
}

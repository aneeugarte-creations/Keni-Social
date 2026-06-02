/**
 * PANEL "DALE EL OK" de una pieza en el feed (la cara amable de la cadena de aprobación):
 * en vez de pintar la cadena multinivel cruda, la presenta como una RED SOCIAL interna —
 *
 *   - Un veredicto de IA arriba (QA Editorial): 🟢 lista · 🟡 revisar · 🔴 no publicar.
 *   - Los OK del equipo como "likes": cuántos van (p. ej. "OK 1/2") y DE QUIÉN.
 *   - Un único botón "Dar mi OK" (aprueba el nivel humano que toca) + "Rechazar".
 *   - Cuando junta la aprobación de IA + los OK que faltan, la pieza pasa SOLA a
 *     "Lista para publicar" (el backend deriva `aprobado` al quedar toda la cadena aprobada).
 *
 * Cada OK = aprobar un nivel humano de la cadena (`api.decidirNivelAprobacion`). El backend
 * es la fuente de verdad de las reglas (no apruebas tu propia pieza; cada OK lo da una
 * persona distinta), aquí solo deshabilitamos y explicamos antes de pedirlo. NO crea backend.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Sparkles, ThumbsUp, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import type { CadenaAprobacion as TCadena, NivelAprobacion } from "@/types";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

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
  plataformaId,
  autorPiezaId,
  veredictoIA,
}: {
  cadena: TCadena;
  /** Id de la `contenido_plataforma` (== `Publicacion.id`); clave de las queries. */
  plataformaId: string;
  /** Autor de la pieza: no puede dar OK a su propia pieza (salvo admin). */
  autorPiezaId: string;
  /** Veredicto de QA suelto (cuando la IA no es un nivel de la cadena). Pinta el semáforo. */
  veredictoIA?: string;
}) {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();

  const niveles = [...cadena.niveles].sort((a, b) => a.nivel - b.nivel);
  const humanos = niveles.filter((n) => !esNivelIA(n));
  const nivelIA = niveles.find(esNivelIA);
  const okDados = humanos.filter((n) => n.decision === "aprobado");
  const totalOK = humanos.length || 1;
  const nivelActual = niveles.find((n) => n.id === cadena.nivel_actual) ?? null;
  const ia = pintaIA(nivelIA, veredictoIA);

  // ¿Puede ESTE usuario dar su OK ahora? El backend revalida; aquí explicamos antes de pedir.
  const esAdmin = usuario?.rol === "admin";
  const esAutor = !!usuario?.id && !!autorPiezaId && usuario.id === autorPiezaId;
  const yaDioOK = !!usuario?.id && humanos.some((n) => n.decisor_id === usuario.id);
  // El OK humano solo se puede dar si el nivel que toca es humano (no el de IA pendiente).
  const tocaHumano = !!nivelActual && !esNivelIA(nivelActual);
  const motivoBloqueo = esAutor
    ? "No puedes dar OK a tu propia pieza; el OK lo da otra persona."
    : yaDioOK
      ? "Ya diste tu OK; falta el de otra persona."
      : !tocaHumano && nivelActual
        ? "Esperando la verificación de la IA antes del OK del equipo."
        : "";
  const puedeOK = !!nivelActual && tocaHumano && (esAdmin || (!esAutor && !yaDioOK));

  const decidir = useMutation({
    mutationFn: (decision: "aprobado" | "rechazado") =>
      api.decidirNivelAprobacion(cadena.nivel_actual, decision),
    onSuccess: (_res, decision) => {
      void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", plataformaId] });
      void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success(decision === "aprobado" ? "¡OK dado!" : "Pieza rechazada.");
    },
    onError: (e: unknown) => toast.error(mensajeError(e)),
  });
  const ocupado = decidir.isPending;

  const lista = cadena.estado === "aprobado";
  const rechazada = cadena.estado === "rechazado";

  return (
    <section className="border-t border-border px-4 py-3" aria-label="Aprobación de la pieza">
      {/* Veredicto de IA (la "aprobación de IA"). */}
      {ia && (
        <p className={"mb-2 flex items-center gap-1.5 text-xs font-medium " + ia.clase}>
          <Sparkles className="h-3.5 w-3.5" />
          {ia.emoji} {ia.texto}
        </p>
      )}

      {/* Los OK del equipo como "likes": cuántos y de quién. */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className="inline-flex items-center gap-1 font-medium">
          <ThumbsUp className="h-4 w-4 text-sky-600 dark:text-sky-400" />
          OK {okDados.length}/{totalOK}
        </span>
        {okDados.length > 0 && (
          <span className="text-muted-foreground">
            · {okDados.map((n) => n.decisor_nombre || "alguien").join(", ")}
          </span>
        )}
      </div>

      {/* Estado / acción según dónde esté la pieza. */}
      {lista ? (
        <p className="mt-2 flex items-center gap-1.5 text-sm font-medium text-emerald-600 dark:text-emerald-400">
          <Check className="h-4 w-4" />
          Lista para publicar
        </p>
      ) : rechazada ? (
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">
          Rechazada; la pieza vuelve a la redacción.
        </p>
      ) : (
        <div className="mt-2 flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="positive"
              size="sm"
              onClick={() => decidir.mutate("aprobado")}
              disabled={ocupado || !puedeOK}
              title={puedeOK ? "Da tu OK a esta pieza" : motivoBloqueo}
            >
              {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <ThumbsUp className="h-4 w-4" />}
              Dar mi OK
            </Button>
            {puedeOK && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => decidir.mutate("rechazado")}
                disabled={ocupado}
              >
                <XCircle className="h-4 w-4" />
                Rechazar
              </Button>
            )}
          </div>
          {!puedeOK && motivoBloqueo && (
            <p className="text-xs text-muted-foreground">{motivoBloqueo}</p>
          )}
          {okDados.length < totalOK && (
            <Badge variant="aviso" className="w-fit">
              Faltan {totalOK - okDados.length} OK para que quede lista
            </Badge>
          )}
        </div>
      )}
    </section>
  );
}

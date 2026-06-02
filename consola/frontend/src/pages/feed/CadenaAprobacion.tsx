/**
 * UI de la APROBACION MULTINIVEL de una pieza en el feed (follow-up #4): pinta la cadena de
 * niveles (p. ej. Edición → Coordinación → Dirección) con su estado por nivel y deja DECIDIR
 * el nivel que toca, respetando las reglas del backend (`dominio/colaboracion.py`):
 *
 *   - Se decide POR ORDEN: solo el primer nivel `pendiente` (`nivel_actual`) acepta decisión.
 *     Los anteriores ya están decididos; los posteriores se muestran en espera (deshabilitados).
 *   - "Otro par de ojos": el decisor NO puede ser el autor de la pieza (salvo admin). Aquí se
 *     deshabilita el control y se explica; el backend es la fuente de verdad (responde 409).
 *   - Un RECHAZO en cualquier nivel para la cadena (la pieza vuelve a borrador). Si la cadena
 *     ya está rechazada o totalmente aprobada, no hay decisión pendiente.
 *
 * Consume los endpoints existentes (`api.cadenaAprobacion` / `api.decidirNivelAprobacion`); NO
 * crea backend nuevo. El estado global (badge) y los niveles vienen del servidor.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, CircleDashed, Clock, Loader2, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import type { CadenaAprobacion as TCadena, DecisionAprobacion, NivelAprobacion } from "@/types";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

/** Etiqueta humana + variante de badge para la decisión de UN nivel. */
function pintaDecision(decision: DecisionAprobacion): {
  texto: string;
  variant: "ok" | "error" | "aviso";
  Icono: typeof Check;
} {
  if (decision === "aprobado") return { texto: "Aprobado", variant: "ok", Icono: Check };
  if (decision === "rechazado") return { texto: "Rechazado", variant: "error", Icono: XCircle };
  return { texto: "Pendiente", variant: "aviso", Icono: Clock };
}

/** Resumen del estado GLOBAL de la cadena (el badge de cabecera). */
function pintaEstadoCadena(estado: TCadena["estado"]): { texto: string; variant: "ok" | "error" | "aviso" | "secondary" } {
  switch (estado) {
    case "aprobado":
      return { texto: "Aprobada", variant: "ok" };
    case "rechazado":
      return { texto: "Rechazada", variant: "error" };
    case "pendiente":
      return { texto: "En aprobación", variant: "aviso" };
    default:
      return { texto: "Sin cadena", variant: "secondary" };
  }
}

function Fila({
  nivel,
  esActual,
  total,
}: {
  nivel: NivelAprobacion;
  esActual: boolean;
  total: number;
}) {
  const { texto, variant, Icono } = pintaDecision(nivel.decision);
  // Niveles posteriores al actual (aún sin decidir y no es su turno): en espera.
  const enEspera = nivel.decision === "pendiente" && !esActual;
  return (
    <li
      className={
        "flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs " +
        (esActual ? "border-amber-400/60 bg-amber-500/5" : "border-border")
      }
    >
      <span className="font-medium tabular-nums text-muted-foreground">
        {nivel.nivel}/{total}
      </span>
      <span className="font-medium text-foreground">{nivel.etiqueta || "Nivel"}</span>
      {nivel.cargo_requerido && (
        <span className="text-muted-foreground">· cargo: {nivel.cargo_requerido}</span>
      )}
      <Badge variant={enEspera ? "secondary" : variant} className="ml-auto gap-1">
        {enEspera ? <CircleDashed className="h-3 w-3" /> : <Icono className="h-3 w-3" />}
        {enEspera ? "En espera" : texto}
      </Badge>
      {nivel.decision !== "pendiente" && nivel.decisor_nombre && (
        <span className="text-muted-foreground">por {nivel.decisor_nombre}</span>
      )}
    </li>
  );
}

export function CadenaAprobacion({
  cadena,
  plataformaId,
  autorPiezaId,
}: {
  cadena: TCadena;
  /** Id de la `contenido_plataforma` (== `Publicacion.id`); clave de las queries. */
  plataformaId: string;
  /** Autor de la pieza: el gate "otro par de ojos" le impide decidir (salvo admin). */
  autorPiezaId: string;
}) {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  const [comentario, setComentario] = React.useState("");

  const niveles = [...cadena.niveles].sort((a, b) => a.nivel - b.nivel);
  const total = niveles.length;
  const estado = pintaEstadoCadena(cadena.estado);
  const nivelActual = niveles.find((n) => n.id === cadena.nivel_actual) ?? null;

  // Gate "otro par de ojos" del lado cliente (el backend lo revalida): un autor no-admin no
  // puede decidir su propia pieza. Sirve para deshabilitar y explicar antes de pedir al server.
  const esAdmin = usuario?.rol === "admin";
  const esAutor = !!usuario?.id && !!autorPiezaId && usuario.id === autorPiezaId;
  const bloqueadoPorAutor = esAutor && !esAdmin;

  const decidir = useMutation({
    mutationFn: (decision: "aprobado" | "rechazado") =>
      api.decidirNivelAprobacion(cadena.nivel_actual, decision, comentario.trim() || undefined),
    onSuccess: (_res, decision) => {
      setComentario("");
      void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", plataformaId] });
      void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success(decision === "aprobado" ? "Nivel aprobado." : "Pieza rechazada.");
    },
    onError: (e: unknown) => toast.error(mensajeError(e)),
  });
  const ocupado = decidir.isPending;

  return (
    <section className="border-t border-border px-4 py-3" aria-label="Cadena de aprobación">
      <div className="mb-2 flex items-center gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Aprobación multinivel
        </h4>
        <Badge variant={estado.variant} className="ml-auto">
          {estado.texto}
        </Badge>
      </div>

      <ol className="flex flex-col gap-1.5">
        {niveles.map((nivel) => (
          <Fila key={nivel.id} nivel={nivel} esActual={nivel.id === cadena.nivel_actual} total={total} />
        ))}
      </ol>

      {/* Decisión del nivel que toca por orden (solo si la cadena espera decisión). */}
      {nivelActual ? (
        <div className="mt-3 flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">
            Toca decidir: <span className="font-medium text-foreground">{nivelActual.etiqueta || "este nivel"}</span>
          </p>
          {bloqueadoPorAutor ? (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              No puedes aprobar tu propia pieza; debe revisarla otra persona.
            </p>
          ) : (
            <>
              <textarea
                value={comentario}
                onChange={(e) => setComentario(e.target.value)}
                placeholder="Comentario para esta decisión (opcional)"
                rows={2}
                disabled={ocupado}
                className="w-full resize-y rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="positive"
                  size="sm"
                  onClick={() => decidir.mutate("aprobado")}
                  disabled={ocupado}
                >
                  {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Aprobar nivel
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => decidir.mutate("rechazado")}
                  disabled={ocupado}
                >
                  {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                  Rechazar
                </Button>
              </div>
            </>
          )}
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">
          {cadena.estado === "rechazado"
            ? "La cadena fue rechazada; la pieza vuelve a la redacción."
            : cadena.estado === "aprobado"
              ? "Todos los niveles están aprobados."
              : "No hay ningún nivel pendiente de decisión."}
        </p>
      )}
    </section>
  );
}

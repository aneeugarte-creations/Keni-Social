/**
 * Chat en vivo con un Ralph: conversación independiente (mensajes tú/ralph), input
 * para enviar, indicador "escribiendo…" y botón de matar. La respuesta del Ralph se
 * acumula token a token desde su stream SSE (gestionado por el store). El render del
 * texto del Ralph reusa `Markdown`; el del humano va en texto plano.
 */
import { Maximize2, Minimize2, Send, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { COLOR_ESTADO, ETIQUETA_ESTADO } from "./PanelRalphs";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/Markdown";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import { formatearHora } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import { ETIQUETA_MODELO, useRalphStore } from "@/store/ralphStore";

/** Hora (HH:MM + etiqueta de zona) de un mensaje, en la zona de display del usuario; "" si inválida. */
function horaCorta(iso: string): string {
  return formatearHora(iso);
}

export function ChatRalph({ id }: { id: string }) {
  const ralph = useRalphStore((s) => s.ralphs.find((r) => r.id === id));
  const mensajes = useRalphStore((s) => s.conversaciones[id]);
  const escribiendo = useRalphStore((s) => s.escribiendo[id]);
  const enviarMensaje = useRalphStore((s) => s.enviarMensaje);
  const matar = useRalphStore((s) => s.matar);
  const seleccionar = useRalphStore((s) => s.seleccionar);

  const [texto, setTexto] = React.useState("");
  const [matando, setMatando] = React.useState(false);
  const [expandido, setExpandido] = React.useState(false);
  const finRef = React.useRef<HTMLDivElement | null>(null);

  // Autoscroll al fondo cuando llegan deltas o cambia el indicador de escritura.
  React.useEffect(() => {
    finRef.current?.scrollIntoView({ block: "end" });
  }, [mensajes, escribiendo]);

  if (!ralph) return null;

  const enviar = async () => {
    const limpio = texto.trim();
    if (!limpio) return;
    setTexto("");
    try {
      await enviarMensaje(id, limpio);
    } catch {
      toast.error("No se pudo enviar el mensaje.");
    }
  };

  const onMatar = async () => {
    setMatando(true);
    try {
      await matar(id);
    } catch {
      toast.error("No se pudo detener el Ralph.");
      setMatando(false);
    }
  };

  const conversacion = mensajes ?? [];

  return (
    <>
      {/* En pantalla completa, un velo cubre la app; clic fuera del panel lo contrae. */}
      {expandido && (
        <div
          className="fixed inset-0 z-40 bg-black/40"
          onClick={() => setExpandido(false)}
          aria-hidden
        />
      )}
      <div
        className={cn(
          "flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xl",
          expandido
            ? "fixed inset-3 z-50 sm:inset-8"
            : "h-[480px] max-h-[calc(100vh-7rem)] w-[380px] max-w-[calc(100vw-3rem)]",
        )}
      >
      {/* Cabecera: nombre + estado + modelo, expandir, matar y cerrar. */}
      <header className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", COLOR_ESTADO[ralph.estado])} />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold leading-tight">{ralph.nombre}</p>
          <p className="truncate text-xs text-muted-foreground">
            {ralph.tipo === "dev" ? "Desarrollo" : "Asistente"} ·{" "}
            {ETIQUETA_ESTADO[ralph.estado]} · {ETIQUETA_MODELO[ralph.modelo]}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1">
          <Tooltip label={expandido ? "Salir de pantalla completa" : "Pantalla completa"} side="top">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setExpandido((v) => !v)}
              aria-label={expandido ? "Salir de pantalla completa" : "Pantalla completa"}
            >
              {expandido ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>
          </Tooltip>
          <Tooltip label="Detener Ralph" side="top">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onMatar} disabled={matando}>
              {matando ? <Spinner className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
            </Button>
          </Tooltip>
          <Tooltip label="Cerrar chat" side="top">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => seleccionar(null)}>
              <X className="h-4 w-4" />
            </Button>
          </Tooltip>
        </div>
      </header>

      {/* Conversación. */}
      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {conversacion.length === 0 && (
          <p className="mt-8 text-center text-sm text-muted-foreground">
            Aún no hay mensajes. Escríbele a {ralph.nombre}.
          </p>
        )}
        {conversacion.map((m) => {
          const hora = horaCorta(m.creado);
          return (
            <div key={m.id} className={cn("flex", m.autor === "tu" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                  m.autor === "tu"
                    ? "bg-keni text-primary-foreground"
                    : "bg-muted text-foreground",
                )}
              >
                {m.autor === "tu" ? (
                  <p className="whitespace-pre-wrap break-words">{m.texto}</p>
                ) : (
                  <Markdown>{m.texto}</Markdown>
                )}
                {hora && (
                  <p
                    className={cn(
                      "mt-1 text-right text-[10px] leading-none",
                      m.autor === "tu" ? "text-primary-foreground/70" : "text-muted-foreground",
                    )}
                  >
                    {hora}
                  </p>
                )}
              </div>
            </div>
          );
        })}
        {escribiendo && (
          <div className="flex justify-start">
            <div className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
              {ralph.nombre} está escribiendo…
            </div>
          </div>
        )}
        <div ref={finRef} />
      </div>

      {/* Input. */}
      <div className="flex items-end gap-2 border-t border-border p-2">
        <AutoTextarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            // Enter envía; Shift+Enter inserta salto de línea.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void enviar();
            }
          }}
          placeholder={`Mensaje para ${ralph.nombre}…`}
          maxHeight={120}
          className="min-h-[40px] flex-1"
        />
        <Button
          variant="brand"
          size="icon"
          className="h-10 w-10 shrink-0"
          onClick={enviar}
          disabled={!texto.trim()}
          aria-label="Enviar"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
      </div>
    </>
  );
}

/**
 * Panel de MENSAJES DIRECTOS (solo lectura): por cada red, sus conversaciones con la
 * audiencia. Cada conversación se pinta como un hilo tipo chat; la alineación de cada
 * mensaje (entrante/saliente) la decide `heuristica.ts`. `adjuntos` se muestra como un
 * contador, no se descargan las imágenes.
 */
import { Paperclip } from "lucide-react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import { iconoRed, nombreRed } from "@/pages/piezas/meta";
import type { Conversacion, ConversacionesPorRed, MensajeDM } from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { avatarAudiencia, esMensajeEntrante, nombreAudiencia } from "./heuristica";

function Mensaje({
  mensaje,
  entrante,
}: {
  mensaje: MensajeDM;
  entrante: boolean;
}) {
  return (
    <div className={cn("flex", entrante ? "justify-start" : "justify-end")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-3 py-2 text-sm",
          entrante
            ? "bg-muted text-foreground"
            : "bg-primary text-primary-foreground",
        )}
      >
        {mensaje.texto && <p className="whitespace-pre-wrap break-words">{mensaje.texto}</p>}
        {mensaje.adjuntos > 0 && (
          <p
            className={cn(
              "mt-1 inline-flex items-center gap-1 text-xs",
              entrante ? "text-muted-foreground" : "text-primary-foreground/80",
            )}
          >
            <Paperclip className="h-3 w-3" aria-hidden="true" />
            {mensaje.adjuntos} {mensaje.adjuntos === 1 ? "adjunto" : "adjuntos"}
          </p>
        )}
        {!mensaje.texto && mensaje.adjuntos === 0 && (
          <p className="text-xs italic opacity-70">(sin texto)</p>
        )}
        {mensaje.fecha && (
          <p
            className={cn(
              "mt-1 text-[10px]",
              entrante ? "text-muted-foreground" : "text-primary-foreground/70",
            )}
          >
            {formatearFechaHoraCorta(mensaje.fecha)}
          </p>
        )}
      </div>
    </div>
  );
}

function TarjetaConversacion({ conversacion }: { conversacion: Conversacion }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3 space-y-0 pb-3">
        <AvatarPersona
          nombre={nombreAudiencia(conversacion)}
          avatar={avatarAudiencia(conversacion)}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{nombreAudiencia(conversacion)}</p>
          {conversacion.actualizado && (
            <p className="text-xs text-muted-foreground">
              {formatearFechaHoraCorta(conversacion.actualizado)}
            </p>
          )}
        </div>
        {conversacion.pendiente && <Badge variant="aviso">Pendiente</Badge>}
      </CardHeader>
      <CardContent className="space-y-2">
        {conversacion.mensajes.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin mensajes.</p>
        ) : (
          conversacion.mensajes.map((m, i) => (
            <Mensaje
              key={m.id ?? i}
              mensaje={m}
              entrante={esMensajeEntrante(m, conversacion.participantes)}
            />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function GrupoRed({ grupo }: { grupo: ConversacionesPorRed }) {
  const Icono = iconoRed(grupo.red);
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Icono className="h-4 w-4" aria-hidden="true" />
        {nombreRed(grupo.red)}
        <span className="text-muted-foreground">({grupo.conversaciones.length})</span>
      </h3>
      {grupo.conversaciones.map((c) => (
        <TarjetaConversacion key={c.id} conversacion={c} />
      ))}
    </section>
  );
}

export function PanelConversaciones({ porRed }: { porRed: ConversacionesPorRed[] }) {
  const conDatos = porRed.filter((g) => g.conversaciones.length > 0);
  if (conDatos.length === 0) {
    return (
      <EstadoVacio
        titulo="Sin mensajes directos"
        texto="No hay conversaciones de Facebook ni Instagram para esta marca."
      />
    );
  }
  return (
    <div className="space-y-6">
      {conDatos.map((g) => (
        <GrupoRed key={g.red} grupo={g} />
      ))}
    </div>
  );
}

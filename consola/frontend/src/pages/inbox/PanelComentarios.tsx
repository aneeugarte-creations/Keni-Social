/**
 * Panel de COMENTARIOS (solo lectura): por cada red, los comentarios de la audiencia
 * sobre las publicaciones del periodo. Cada tarjeta lleva el contexto de la publicación
 * comentada (texto recortado, miniatura y enlace), el comentario (autor, texto, fecha y
 * enlace permanente) y sus respuestas anidadas (un nivel).
 */
import { ExternalLink } from "lucide-react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import { iconoRed, nombreRed } from "@/pages/piezas/meta";
import type {
  AutorComentario,
  Comentario,
  ComentariosPorRed,
  RespuestaComentarioInbox,
} from "@/types";

import { AvatarPersona } from "./AvatarPersona";

/** Texto de la publicación recortado para el contexto (las publicaciones pueden ser largas). */
function recortar(texto: string, max = 140): string {
  const t = texto.trim();
  return t.length > max ? `${t.slice(0, max).trimEnd()}…` : t;
}

function nombreAutor(autor: AutorComentario | null): string {
  const n = autor?.nombre?.trim();
  return n && n !== "" ? n : "Sin nombre";
}

function ContextoPublicacion({ comentario }: { comentario: Comentario }) {
  const tieneTexto = comentario.post_texto && comentario.post_texto.trim() !== "";
  const miniatura = comentario.post_media[0];
  if (!tieneTexto && !miniatura && !comentario.post_enlace) return null;
  return (
    <div className="flex items-start gap-3 rounded-md border bg-muted/40 p-2">
      {miniatura && (
        <img
          src={miniatura}
          alt="Publicación comentada"
          className="h-12 w-12 shrink-0 rounded object-cover"
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      )}
      <div className="min-w-0 flex-1 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Publicación</span>
        {tieneTexto && (
          <p className="mt-0.5 break-words">{recortar(comentario.post_texto as string)}</p>
        )}
        {comentario.post_enlace && (
          <a
            href={comentario.post_enlace}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-primary hover:underline"
          >
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
            Ver publicación
          </a>
        )}
      </div>
    </div>
  );
}

function Respuesta({ respuesta }: { respuesta: RespuestaComentarioInbox }) {
  return (
    <div className="flex items-start gap-2">
      <AvatarPersona
        nombre={nombreAutor(respuesta.autor)}
        avatar={respuesta.autor?.avatar ?? null}
        className="h-6 w-6"
      />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-medium">{nombreAutor(respuesta.autor)}</span>
          {respuesta.fecha && (
            <span className="text-muted-foreground">
              {formatearFechaHoraCorta(respuesta.fecha)}
            </span>
          )}
          {respuesta.pendiente && <Badge variant="aviso">Pendiente</Badge>}
        </p>
        {respuesta.texto && (
          <p className="mt-0.5 whitespace-pre-wrap break-words text-sm">{respuesta.texto}</p>
        )}
      </div>
    </div>
  );
}

function TarjetaComentario({ comentario }: { comentario: Comentario }) {
  return (
    <Card>
      <CardHeader className="space-y-3 pb-3">
        <ContextoPublicacion comentario={comentario} />
        <div className="flex items-start gap-3">
          <AvatarPersona
            nombre={nombreAutor(comentario.autor)}
            avatar={comentario.autor?.avatar ?? null}
          />
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{nombreAutor(comentario.autor)}</span>
              {comentario.fecha && (
                <span className="text-xs text-muted-foreground">
                  {formatearFechaHoraCorta(comentario.fecha)}
                </span>
              )}
              {comentario.pendiente && <Badge variant="aviso">Pendiente</Badge>}
            </p>
            {comentario.texto && (
              <p className="mt-1 whitespace-pre-wrap break-words text-sm">{comentario.texto}</p>
            )}
            {comentario.permalink && (
              <a
                href={comentario.permalink}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline"
              >
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
                Ver comentario
              </a>
            )}
          </div>
        </div>
      </CardHeader>
      {comentario.respuestas.length > 0 && (
        <CardContent className="space-y-3 border-l-2 border-muted pb-4 pl-4">
          {comentario.respuestas.map((r) => (
            <Respuesta key={r.id} respuesta={r} />
          ))}
        </CardContent>
      )}
    </Card>
  );
}

function GrupoRed({ grupo }: { grupo: ComentariosPorRed }) {
  const Icono = iconoRed(grupo.red);
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Icono className="h-4 w-4" aria-hidden="true" />
        {nombreRed(grupo.red)}
        <span className="text-muted-foreground">({grupo.comentarios.length})</span>
      </h3>
      {grupo.comentarios.map((c) => (
        <TarjetaComentario key={c.id} comentario={c} />
      ))}
    </section>
  );
}

export function PanelComentarios({ porRed }: { porRed: ComentariosPorRed[] }) {
  const conDatos = porRed.filter((g) => g.comentarios.length > 0);
  if (conDatos.length === 0) {
    return (
      <EstadoVacio
        titulo="Sin comentarios"
        texto="No hay comentarios de Facebook ni Instagram en el periodo seleccionado."
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

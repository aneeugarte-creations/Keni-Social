/**
 * Cajón PRESIDENCIA (Fuentes → Internas): la nota que llega por WhatsApp desde presidencia
 * (texto + 4-5 imágenes y algún video) se vuelca aquí TAL CUAL y el sistema genera
 * AUTOMÁTICAMENTE la pieza CARRUSEL del feed: portada = primera imagen con la placa de
 * marca; el resto del media va en crudo, en orden, como slides. El copy se redacta en
 * segundo plano con la nota íntegra; la pieza fluye por el gate humano normal.
 *
 * Es un cajón de UnoTV (como Portal/Corresponsales): visible con esa marca activa o en "Todas".
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Crown, Loader2, Send } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { EditorCarrusel } from "@/components/media/EditorCarrusel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { SlideCarrusel } from "@/lib/carrusel";
import type { NotaPresidencia } from "@/types";

// Marca del cajón: las notas de presidencia son de UnoTV (mismo criterio que Portal/SMS).
const MARCA_CAJON = "unotv";

const CLAVE_NOTAS = ["presidencia", "notas"] as const;

function BadgeEstadoPieza({ nota }: { nota: NotaPresidencia }) {
  if (nota.estado_pieza === "generando") {
    return (
      <Badge variant="aviso" className="gap-1" title="Redactando copy automático...">
        <Loader2 className="h-3 w-3 animate-spin" />
        Generando…
      </Badge>
    );
  }
  if (nota.estado_pieza === "lista") {
    return (
      <Badge variant="ok" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        En el feed
      </Badge>
    );
  }
  return <Badge variant="secondary">Sin pieza</Badge>;
}

export default function CajonPresidencia() {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const [titulo, setTitulo] = React.useState("");
  const [texto, setTexto] = React.useState("");
  // El media de la nota, en el ORDEN de publicación: la PRIMERA imagen será la portada
  // (con placa); el resto va en crudo como slides. Reusa el editor de slides del carrusel.
  const [media, setMedia] = React.useState<SlideCarrusel[]>([]);

  const notasQuery = useQuery({
    queryKey: CLAVE_NOTAS,
    queryFn: ({ signal }) => api.notasPresidencia({ marca: MARCA_CAJON }, signal),
    // Mientras alguna nota siga generando su copy, refrescamos para ver el "En el feed".
    refetchInterval: (q) =>
      (q.state.data?.notas ?? []).some((n) => n.estado_pieza === "generando") ? 4000 : false,
  });

  const crearMut = useMutation({
    mutationFn: () =>
      api.crearNotaPresidencia({
        marca: MARCA_CAJON,
        texto: texto.trim(),
        titulo: titulo.trim() || undefined,
        media: media.map((s) => ({ tipo: s.tipo, objeto: s.objeto })),
      }),
    onSuccess: () => {
      setTitulo("");
      setTexto("");
      setMedia([]);
      void queryClient.invalidateQueries({ queryKey: CLAVE_NOTAS });
      toast.success(
        "Nota enviada: la pieza carrusel ya está en el feed y el copy se está redactando.",
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Cajón de UnoTV: con otra marca activa no se muestra (en "Todas" sí).
  if (marcaActiva && marcaActiva !== MARCA_CAJON) return null;

  const hayImagen = media.some((s) => s.tipo === "imagen");
  const puedeEnviar = texto.trim().length > 0 && hayImagen && !crearMut.isPending;
  const notas = notasQuery.data?.notas ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Crown className="h-4 w-4 text-muted-foreground" />
          Presidencia
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="presidencia-titulo" className="text-xs text-muted-foreground">
            Título
          </Label>
          <Input
            id="presidencia-titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Opcional: título de la nota"
          />
        </div>
        <Textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={5}
          aria-label="Texto de la nota de presidencia"
        />
        {/* El media de la nota: el editor de slides reusa la subida imagen/video y el orden.
            Aquí la lista ES el carrusel entero (base 1) y la PRIMERA imagen queda marcada
            como portada (sube de posición la que quieras de portada). */}
        <EditorCarrusel
          slides={media}
          onCambio={setMedia}
          idPrefijo="presidencia"
          base={1}
          marcarPortada
          etiqueta="Media de la nota"
        />
        {!hayImagen && media.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Se necesita imagen para portada del carrusel.
          </p>
        )}
        <div className="flex justify-end">
          <Button
            className="gap-1"
            onClick={() => crearMut.mutate()}
            disabled={!puedeEnviar}
            aria-label="Enviar nota de presidencia al feed"
            title={
              puedeEnviar
                ? undefined
                : "Completa nota e imagen"
            }
          >
            {crearMut.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {crearMut.isPending ? "Enviando…" : "Enviar al feed"}
          </Button>
        </div>

        {/* Notas recientes con el estado de su pieza. */}
        {notas.length > 0 && (
          <div className="space-y-2 border-t pt-3">
            <p className="text-xs font-medium text-muted-foreground">
              {notas.length} nota{notas.length !== 1 ? "s" : ""} volcada
              {notas.length !== 1 ? "s" : ""}
            </p>
            <ul className="space-y-2">
              {notas.map((n) => (
                <li
                  key={n.id}
                  className="flex items-start justify-between gap-2 rounded-md border p-2.5 text-sm"
                  data-testid="nota-presidencia"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium leading-snug">
                      {n.titulo || "(sin título)"}
                    </p>
                    {n.texto && (
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                        {n.texto}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <BadgeEstadoPieza nota={n} />
                    {/* La pieza vive en el feed (agrupada por idea, con el título de la nota). */}
                    <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
                      <Link to="/operacion/feed">Ver en el feed</Link>
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

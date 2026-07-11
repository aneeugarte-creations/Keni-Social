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
import { Crown, Send } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { EditorCarrusel } from "@/components/media/EditorCarrusel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { SlideCarrusel } from "@/lib/carrusel";

import { BadgeEstadoPieza } from "./BadgeEstadoPieza";

// Marca del cajón: las notas de presidencia son de UnoTV (mismo criterio que Portal/SMS).
const MARCA_CAJON = "unotv";

const CLAVE_NOTAS = ["presidencia", "notas"] as const;

export default function CajonPresidencia() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
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
          <Aviso>Se necesita imagen para portada del carrusel.</Aviso>
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
              <Spinner className="h-4 w-4" />
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
                // Click izquierdo = ir al feed (la pieza vive ahí, agrupada por idea). El
                // realce naranja del borde al hover/foco es la pista de que es accionable.
                <FilaConAcciones
                  key={n.id}
                  como="li"
                  realce
                  acciones={[]}
                  onPrimaria={() => navigate("/operacion/feed")}
                  className="flex items-start justify-between gap-2 rounded-md border p-3 text-sm"
                >
                  <div className="min-w-0" data-testid="nota-presidencia">
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
                    <BadgeEstadoPieza
                      estado={n.estado_pieza}
                      tituloGenerando="Redactando copy automático..."
                    />
                  </div>
                </FilaConAcciones>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

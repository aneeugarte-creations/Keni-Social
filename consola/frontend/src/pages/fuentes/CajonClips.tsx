/**
 * Cajón CLIPS (Fuentes → Internas, Claro Sports): el video/foto que llega por WhatsApp a los
 * grupos de Claro Sports (Envíos Mundial, Ramón Mundial, Videos AS Claro, ClaroSports PS…) se
 * vuelca aquí TAL CUAL —un pie/contexto + el media— y el sistema genera AUTOMÁTICAMENTE la pieza:
 * un VIDEO → pieza de video (en las 5 redes); FOTOS → carrusel (portada con placa + slides).
 * El copy se redacta en segundo plano; la pieza fluye por el gate humano normal.
 *
 * Es un cajón de Claro Sports: visible con esa marca activa o en "Todas".
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard, Film, Images, Send } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { EditorCarrusel } from "@/components/media/EditorCarrusel";
import { Badge } from "@/components/ui/badge";
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

// Marca del cajón: los clips son de Claro Sports (mismo criterio que los feeds deportivos).
const MARCA_CAJON = "claro-sports";

const CLAVE_CLIPS = ["clips", "lista"] as const;

export default function CajonClips() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { marcaActiva } = useMarcaActiva();
  const [titulo, setTitulo] = React.useState("");
  const [texto, setTexto] = React.useState("");
  // El media del clip. Un VIDEO solo → pieza de video; FOTOS → carrusel (1ª imagen = portada).
  const [media, setMedia] = React.useState<SlideCarrusel[]>([]);

  const clipsQuery = useQuery({
    queryKey: CLAVE_CLIPS,
    queryFn: ({ signal }) => api.clips({ marca: MARCA_CAJON }, signal),
    // Mientras algún clip siga generando su copy, refrescamos para ver el "En el feed".
    refetchInterval: (q) =>
      (q.state.data?.clips ?? []).some((c) => c.estado_pieza === "generando") ? 4000 : false,
  });

  const crearMut = useMutation({
    mutationFn: () =>
      api.crearClip({
        marca: MARCA_CAJON,
        texto: texto.trim(),
        titulo: titulo.trim() || undefined,
        media: media.map((s) => ({ tipo: s.tipo, objeto: s.objeto })),
      }),
    onSuccess: () => {
      setTitulo("");
      setTexto("");
      setMedia([]);
      void queryClient.invalidateQueries({ queryKey: CLAVE_CLIPS });
      toast.success("Clip enviado: la pieza ya está en el feed y el copy se está redactando.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Cajón de Claro Sports: con otra marca activa no se muestra (en "Todas" sí).
  if (marcaActiva && marcaActiva !== MARCA_CAJON) return null;

  const hayVideo = media.some((s) => s.tipo === "video");
  // Un clip de video es UNA sola pieza de video: si hay video, no puede haber nada más.
  const videoInvalido = hayVideo && media.length > 1;
  const formato = hayVideo ? "video" : "carrusel";
  const puedeEnviar =
    texto.trim().length > 0 && media.length > 0 && !videoInvalido && !crearMut.isPending;
  const clips = clipsQuery.data?.clips ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Clapperboard className="h-4 w-4 text-muted-foreground" />
          Clips
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="clips-titulo" className="text-xs text-muted-foreground">
            Título
          </Label>
          <Input
            id="clips-titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Opcional: título del clip…"
          />
        </div>
        <Textarea
          placeholder="Pie o contexto del clip (de WhatsApp)…"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={4}
          aria-label="Texto del clip"
        />
        <EditorCarrusel
          slides={media}
          onCambio={setMedia}
          idPrefijo="clips"
          base={1}
          marcarPortada
          etiqueta="Video o fotos"
        />
        {videoInvalido && <Aviso>1 video o varias fotos (no ambos).</Aviso>}
        {media.length > 0 && !videoInvalido && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {hayVideo ? <Film className="h-3.5 w-3.5" /> : <Images className="h-3.5 w-3.5" />}
            Se publicará como {formato}.
          </p>
        )}
        <div className="flex justify-end">
          <Button
            className="gap-1"
            onClick={() => crearMut.mutate()}
            disabled={!puedeEnviar}
            aria-label="Enviar clip al feed"
            title={puedeEnviar ? undefined : "Completa el contexto y sube el media"}
          >
            {crearMut.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {crearMut.isPending ? "Enviando…" : "Enviar al feed"}
          </Button>
        </div>

        {/* Clips recientes con el estado de su pieza. */}
        {clips.length > 0 && (
          <div className="space-y-2 border-t pt-3">
            <p className="text-xs font-medium text-muted-foreground">
              {clips.length} clip{clips.length !== 1 ? "s" : ""} volcado
              {clips.length !== 1 ? "s" : ""}
            </p>
            <ul className="space-y-2">
              {clips.map((c) => (
                // Click izquierdo = ir al feed (la acción natural del clip ya volcado). El
                // realce naranja del borde al hover/foco es la pista de que es accionable.
                <FilaConAcciones
                  key={c.id}
                  como="li"
                  realce
                  acciones={[]}
                  onPrimaria={() => navigate("/operacion/feed")}
                  className="flex items-start justify-between gap-2 rounded-md border p-2.5 text-sm"
                >
                  <div className="min-w-0" data-testid="clip-item">
                    <p className="truncate font-medium leading-snug">{c.titulo || "(sin título)"}</p>
                    {c.texto && (
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{c.texto}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {c.formato && (
                      <Badge variant="outline" className="gap-1 text-xs">
                        {c.formato === "video" ? (
                          <Film className="h-3 w-3" />
                        ) : (
                          <Images className="h-3 w-3" />
                        )}
                        {c.formato === "video" ? "Video" : "Carrusel"}
                      </Badge>
                    )}
                    <BadgeEstadoPieza
                      estado={c.estado_pieza}
                      tituloGenerando="La IA redacta el copy; la pieza saldrá al terminar."
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

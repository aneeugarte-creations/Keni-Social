/**
 * Un POST del Feed de ideación (Flujo D, Fase 4): una pieza presentada como en una red
 * social interna, no como una tarjeta de kanban. Muestra, de arriba a abajo:
 *
 *  1. Cabecera: autor + marca + red + etapa IA en vivo (badge que pulsa mientras trabaja).
 *  2. Material original: el título del tema (lo que "posteó" el equipo).
 *  3. Copy generado por la IA: el cuerpo del post (`contenido`), tal como acompañará a la
 *     publicación, dentro de una previa fiel de la red (`VistaPreviaRed`) con su arte/formato.
 *  4. Acciones EN LÍNEA: aprobar / rechazar la pieza (gate humano) sin salir del feed, más
 *     un toggle para abrir el hilo de comentarios del equipo (reusa `Comentarios`).
 *
 * Reusa el motor existente: cuando la pieza tiene una CADENA de niveles, se pinta la UI
 * multinivel completa (`CadenaAprobacion`: estado por nivel + decisión por orden, respetando
 * "otro par de ojos" y "un rechazo para la cadena") sobre `api.decidirNivelAprobacion`. Si
 * NO hay cadena (pieza sin aprobación configurada), cae al camino SIMPLE aprobar/rechazar
 * (`aprobar`/`rechazar` de `api/aprobacion`, que forwardea a la cadena multinivel). En ambos
 * casos la cadena de gobernanza (`cadenaAprobacion`) avisa de firmas/comentarios pendientes.
 * NO crea backend nuevo.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, MessageSquare, Send, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { Comentarios } from "@/components/contenido/Comentarios";
import { VistaPreviaRed } from "@/components/preview/VistaPreviaRed";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { EtiquetaRed } from "@/pages/publicaciones/insignias";
import { tiempoRelativo } from "@/pages/publicaciones/meta";
import type { Publicacion } from "@/types";

import { CadenaAprobacion } from "./CadenaAprobacion";
import { etapaDePublicacion } from "./etapa";
import { BadgeEtapa } from "./TarjetaEtapa";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

export function PostFeed({ publicacion }: { publicacion: Publicacion }) {
  const queryClient = useQueryClient();
  const [comentariosAbierto, setComentariosAbierto] = React.useState(false);

  const etapa = etapaDePublicacion(publicacion);
  const enRevision = publicacion.estado === "en_revision";

  // Cadena de aprobación: alimenta tanto la UI MULTINIVEL (estado por nivel + decisión por
  // orden) como los avisos de gobernanza (firmas / comentarios sin resolver). Se carga
  // perezosamente cuando la pieza está en revisión (es cuando importa el gate). Si NO hay
  // cadena, el motor simple `aprobar`/`rechazar` forwardea a la cadena multinivel.
  const cadenaQuery = useQuery({
    queryKey: ["cadena-aprobacion", publicacion.id],
    queryFn: ({ signal }) => api.cadenaAprobacion(publicacion.id, signal),
    enabled: enRevision,
  });
  const cadena = cadenaQuery.data;
  const sinResolver = cadena?.comentarios_sin_resolver ?? 0;
  // Hay cadena configurada => pintamos el panel "dale el OK"; si no, camino simple (legado).
  const tieneCadena = (cadena?.niveles?.length ?? 0) > 0;
  // Borrador con copy ya generado: el equipo puede mandarlo a revisión para juntar los OK.
  const listoParaOK = publicacion.estado === "borrador" && !!publicacion.contenido;

  const tras = (mensaje: string) => () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", publicacion.id] });
    toast.success(mensaje);
  };
  const onError = (e: unknown) => toast.error(mensajeError(e));

  // Mandar a revisión: monta la cadena (IA + Edición + Coordinación) y abre los OK del equipo.
  const pedirOK = useMutation({
    mutationFn: () => api.enviarARevision(publicacion.id),
    onSuccess: tras("Pieza lista para que el equipo dé su OK."),
    onError,
  });
  // Fallback para piezas legadas que estén en revisión SIN cadena (aprobar/rechazar forwardea).
  const aprobar = useMutation({
    mutationFn: () => api.aprobarPublicacion(publicacion.id),
    onSuccess: tras("Pieza aprobada."),
    onError,
  });
  const rechazar = useMutation({
    mutationFn: () => api.rechazarPublicacion(publicacion.id),
    onSuccess: tras("Devuelta a borrador."),
    onError,
  });
  const ocupado = aprobar.isPending || rechazar.isPending;

  // El cuerpo del post: el copy que la IA generó (`contenido`); si aún no hay, mostramos
  // el material original como marcador para que el post no quede vacío en "generando copy".
  const cuerpo = publicacion.contenido || publicacion.titulo;
  const imagen = publicacion.imagen_url || publicacion.imagen || publicacion.imagen_fuente;

  return (
    <article className="rounded-xl border border-border bg-background shadow-sm">
      {/* Cabecera: quién posteó · marca · red · etapa IA en vivo. */}
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 pb-2 pt-3 text-xs text-muted-foreground">
        <Autor nombre={publicacion.autor_nombre} className="text-xs font-medium text-foreground" />
        <span>·</span>
        <span>{publicacion.marca_nombre}</span>
        <span>·</span>
        <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} className="text-xs" />
        {publicacion.enviado_a_revision_en && (
          <span className="ml-auto tabular-nums">{tiempoRelativo(publicacion.enviado_a_revision_en)}</span>
        )}
        <BadgeEtapa etapa={etapa} className={publicacion.enviado_a_revision_en ? "" : "ml-auto"} />
      </header>

      {/* Título del material original (lo que "posteó" el equipo). */}
      {publicacion.titulo && (
        <h3 className="px-4 pb-2 text-sm font-semibold leading-snug">{publicacion.titulo}</h3>
      )}

      {/* El post tal como se verá en la red: copy IA + arte/formato. */}
      <div className="px-4">
        <VistaPreviaRed
          red={publicacion.red}
          marca={publicacion.marca_nombre}
          contenido={cuerpo}
          copy_in={publicacion.copy_in}
          imagen_url={imagen || undefined}
        />
      </div>

      {/* Acciones en línea: pedir OK / dar OK (legado) / comentar. El gate vive en el panel. */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        {listoParaOK ? (
          // Borrador con copy: el equipo lo manda a revisión para empezar a juntar los OK.
          <Button size="sm" onClick={() => pedirOK.mutate()} disabled={pedirOK.isPending}>
            {pedirOK.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Pedir OK del equipo
          </Button>
        ) : enRevision && !tieneCadena && !cadenaQuery.isLoading ? (
          // Fallback (piezas legadas en revisión SIN cadena): aprobar/rechazar forwardea.
          <>
            <Button variant="positive" size="sm" onClick={() => aprobar.mutate()} disabled={ocupado}>
              {aprobar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Dar mi OK
            </Button>
            <Button variant="outline" size="sm" onClick={() => rechazar.mutate()} disabled={ocupado}>
              {rechazar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              Rechazar
            </Button>
          </>
        ) : !enRevision ? (
          <span className="text-sm text-muted-foreground">
            {etapa === "aprobada" || etapa === "programada" || etapa === "publicada"
              ? publicacion.revisor_nombre
                ? `Lista para publicar · último OK: ${publicacion.revisor_nombre}`
                : "Lista para publicar"
              : "La IA todavía está preparando esta pieza."}
          </span>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          onClick={() => setComentariosAbierto((v) => !v)}
          aria-expanded={comentariosAbierto}
        >
          <MessageSquare className="h-4 w-4" />
          {comentariosAbierto ? "Ocultar comentarios" : "Comentar"}
        </Button>
      </div>

      {/* Panel "dale el OK": veredicto de IA + OK del equipo (cuántos y de quién) + acción. */}
      {enRevision && tieneCadena && cadena && (
        <CadenaAprobacion
          cadena={cadena}
          plataformaId={publicacion.id}
          autorPiezaId={publicacion.autor_id}
          veredictoIA={publicacion.veredicto}
        />
      )}

      {/* Aviso de comentarios sin resolver (bloquean programar). */}
      {enRevision && sinResolver > 0 && (
        <div className="border-t border-border px-4 py-2 text-xs text-amber-600 dark:text-amber-400">
          {sinResolver} comentario(s) sin resolver antes de programar.
        </div>
      )}

      {/* Hilo de comentarios del equipo (reusa el componente existente). */}
      {comentariosAbierto && publicacion.contenido_id && (
        <div className="border-t border-border px-4 py-3">
          <Comentarios contenidoId={publicacion.contenido_id} />
        </div>
      )}
    </article>
  );
}

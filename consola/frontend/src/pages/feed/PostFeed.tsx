/**
 * Un POST del Feed de ideación (Flujo D, Fase 4): una pieza presentada como en una red
 * social interna, no como una tarjeta de kanban. Muestra, de arriba a abajo:
 *
 *  1. Cabecera EN UNA LÍNEA: autor + marca + red (un solo logo) + formato + etapa IA en vivo.
 *  2. Copy generado por la IA: el cuerpo del post (`contenido`), dentro de una previa fiel de la
 *     red (`VistaPreviaRed`, variante limpia: sin chrome social falso ni cabecera duplicada).
 *  3. Acciones EN LÍNEA, iguales en TODA pieza (como un post): "Me gusta" (el OK humano) y
 *     "Comentar"; "Rechazar" cuando puedes decidir. El "me gusta" se habilita solo cuando te
 *     toca el OK (`elegibilidadOK`); en otros estados se ve deshabilitado y el tooltip explica.
 *  4. Panel de ESTADO de la cadena (`CadenaAprobacion`, solo lectura): veredicto de IA + OK del
 *     equipo (cuántos y de quién) + lo que falta. La acción vive en la fila, no aquí.
 *
 * El OK/rechazo van por `aprobar`/`rechazar` de `api/aprobacion`, que forwardean al nivel ACTUAL
 * de la cadena multinivel (respetando "otro par de ojos" y "un rechazo para la cadena"); el gate
 * lo decide el backend, `elegibilidadOK` solo habilita/explica. NO crea backend nuevo.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, MessageSquare, ThumbsUp, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { Comentarios } from "@/components/contenido/Comentarios";
import { VistaPreviaRed } from "@/components/preview/VistaPreviaRed";
import { Button } from "@/components/ui/button";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import { plural } from "@/lib/formato";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { EtiquetaRed } from "@/pages/publicaciones/insignias";
import { tamanoRed, tiempoRelativo } from "@/pages/publicaciones/meta";
import type { Publicacion } from "@/types";

import { elegibilidadOK } from "./aprobacion";
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
  const { usuario } = useSesion();
  const [comentariosAbierto, setComentariosAbierto] = React.useState(false);

  const etapa = etapaDePublicacion(publicacion);
  const enRevision = publicacion.estado === "en_revision";
  const yaAprobada = etapa === "aprobada" || etapa === "programada" || etapa === "publicada";
  const tam = tamanoRed(publicacion.red);

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

  const tras = (mensaje: string) => () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", publicacion.id] });
    toast.success(mensaje);
  };
  const onError = (e: unknown) => toast.error(mensajeError(e));

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

  // ¿Puede ESTE usuario dar su "me gusta" (OK humano) ahora? Lo decide el backend; aquí
  // habilitamos/explicamos antes de pedirlo. `aprobar`/`rechazar` (legado) forwardean al
  // nivel ACTUAL de la cadena, así que un OK cierra el nivel humano que toca.
  const { puedeDar, motivo } = elegibilidadOK(cadena, usuario, publicacion.autor_id);
  // Texto del botón "Me gusta" según el estado de la pieza (tooltip cuando está deshabilitado).
  const tituloLike = puedeDar
    ? "Dale tu OK (me gusta) a esta pieza"
    : yaAprobada
      ? publicacion.revisor_nombre
        ? `Aprobada · último OK: ${publicacion.revisor_nombre}`
        : "Aprobada"
      : enRevision
        ? motivo || "Esperando turno para tu OK"
        : "La IA aún prepara esta pieza; podrás darle tu OK cuando esté lista.";

  // El cuerpo del post: el copy que la IA generó (`contenido`); si aún no hay, mostramos
  // el material original como marcador para que el post no quede vacío en "generando copy".
  const cuerpo = publicacion.contenido || publicacion.titulo;
  const imagen = publicacion.imagen_url || publicacion.imagen || publicacion.imagen_fuente;

  return (
    <article className="rounded-xl border border-border bg-background shadow-sm">
      {/* Cabecera EN UNA SOLA LÍNEA: quién posteó · marca · red (un solo logo) · formato · etapa.
          El logo/red y el formato NO se repiten en la previa (va en variante limpia, sin su propia
          cabecera): aquí están una vez y ya. */}
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 pb-2 pt-3 text-xs text-muted-foreground">
        <Autor nombre={publicacion.autor_nombre} className="text-xs font-medium text-foreground" />
        <span>·</span>
        <span>{publicacion.marca_nombre}</span>
        <span>·</span>
        <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} className="text-xs" />
        {tam && (
          <span
            className="rounded-full border border-border px-2 py-0.5 tabular-nums"
            title={`Imagen recomendada para ${publicacion.red_nombre}: relación ${tam.ratio}, ${tam.px} px. Cada red recorta a su formato.`}
          >
            {tam.ratio} · {tam.px} px
          </span>
        )}
        {publicacion.enviado_a_revision_en && (
          <span className="ml-auto tabular-nums">{tiempoRelativo(publicacion.enviado_a_revision_en)}</span>
        )}
        <BadgeEtapa etapa={etapa} className={publicacion.enviado_a_revision_en ? "" : "ml-auto"} />
      </header>

      {/* El post tal como se verá en la red: copy IA + arte/formato. Variante LIMPIA: sin el
          chrome social simulado ni el pie "Mockup aproximado" — el feed enseña la pieza real,
          no una maqueta de Facebook. (El título del material original NO se pinta: es el tema
          que "posteó" el equipo, no el copy publicable, y solo confundía.) */}
      <div className="px-4">
        <VistaPreviaRed
          red={publicacion.red}
          marca={publicacion.marca_nombre}
          contenido={cuerpo}
          copy_in={publicacion.copy_in}
          imagen_url={imagen || undefined}
          variante="limpia"
        />
      </div>

      {/* Acciones en línea, IGUAL en TODAS las piezas (como un post de red social): "Me gusta"
          (el OK humano) y "Comentar". El "me gusta" se habilita solo cuando te toca dar el OK
          (pieza en revisión y eres elegible); en los demás estados se ve igual pero deshabilitado,
          con un tooltip que explica por qué (la IA aún la prepara, ya está aprobada, ya diste tu
          OK…). "Rechazar" aparece solo cuando puedes decidir. */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <Button
          variant={puedeDar ? "positive" : "ghost"}
          size="sm"
          onClick={() => aprobar.mutate()}
          disabled={!puedeDar || ocupado}
          title={tituloLike}
        >
          {aprobar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : yaAprobada ? (
            <Check className="h-4 w-4" />
          ) : (
            <ThumbsUp className="h-4 w-4" />
          )}
          Me gusta
        </Button>
        {puedeDar && (
          <Button variant="outline" size="sm" onClick={() => rechazar.mutate()} disabled={ocupado}>
            {rechazar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <XCircle className="h-4 w-4" />
            )}
            Rechazar
          </Button>
        )}
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

      {/* Panel de ESTADO (solo en revisión y con cadena): veredicto de IA + OK del equipo
          (cuántos y de quién) + lo que falta. La acción vive arriba, en la fila. */}
      {enRevision && tieneCadena && cadena && (
        <CadenaAprobacion cadena={cadena} veredictoIA={publicacion.veredicto} />
      )}

      {/* Aviso de comentarios sin resolver (bloquean programar). */}
      {enRevision && sinResolver > 0 && (
        <div className="border-t border-border px-4 py-2 text-xs text-amber-600 dark:text-amber-400">
          {plural(sinResolver, "comentario")} sin resolver antes de programar.
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

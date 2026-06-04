/**
 * Un POST del Feed de ideación (Flujo D, Fase 4): una pieza presentada como en una red
 * social interna, no como una tarjeta de kanban. Muestra, de arriba a abajo:
 *
 *  1. Cabecera EN UNA LÍNEA: autor + marca + red (un solo logo) + formato + etapa IA en vivo.
 *  2. Copy generado por la IA: el cuerpo del post (`contenido`), dentro de una previa fiel de la
 *     red (`VistaPreviaRed`, variante limpia: sin chrome social falso ni cabecera duplicada).
 *  3. Acciones EN LÍNEA, iguales en TODA pieza (como un post): "Me gusta" (el OK humano),
 *     "Editar" (copy, copy-in, foto+plantilla, vía `DialogoEditar`) y "Comentar"; "Rechazar"
 *     cuando puedes decidir. El "me gusta" se habilita solo cuando te toca el OK
 *     (`elegibilidadOK`); en otros estados se ve deshabilitado y el aviso explica qué falta.
 *  4. Panel de ESTADO de la cadena (`CadenaAprobacion`, solo lectura): veredicto de IA + OK del
 *     equipo (cuántos y de quién) + lo que falta. La acción vive en la fila, no aquí.
 *
 * El OK/rechazo van por `aprobar`/`rechazar` de `api/aprobacion`, que forwardean al nivel ACTUAL
 * de la cadena multinivel (respetando "otro par de ojos" y "un rechazo para la cadena"); el gate
 * lo decide el backend, `elegibilidadOK` solo habilita/explica. NO crea backend nuevo.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Loader2, MessageSquare, ThumbsUp, XCircle } from "lucide-react";
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
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
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
  const [editando, setEditando] = React.useState(false);

  const etapa = etapaDePublicacion(publicacion);
  const enRevision = publicacion.estado === "en_revision";
  const yaAprobada = etapa === "aprobada" || etapa === "programada" || etapa === "publicada";
  const tam = tamanoRed(publicacion.red);
  // Autogenerada por la IA: sin autor humano (las piezas de la tubería —pipeline/rss/radar— no
  // tienen autor; las que postea el equipo SÍ). En ese caso la firma es "IA", no "desconocido".
  const generadaPorIA = !publicacion.autor_nombre?.trim();

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

  // Por qué el "me gusta" está bloqueado (qué falta). Ya NO es un texto fijo en la tarjeta: se
  // muestra como TOAST al intentar darle like cuando no toca. Explica el gate (en revisión: tu
  // pieza / ya diste OK / espera turno) o, antes, qué le falta a la pieza.
  const motivoBloqueo = yaAprobada
    ? publicacion.revisor_nombre
      ? `Ya aprobada · último OK: ${publicacion.revisor_nombre}`
      : "Esta pieza ya está aprobada."
    : enRevision
      ? motivo || "Espera tu turno para dar el OK."
      : etapa === "generando_copy"
        ? "Falta el copy: la IA aún lo está redactando."
        : etapa === "generando_arte"
          ? "Falta la imagen: ábrela y súbela (se le aplicará la plantilla)."
          : "Aún no está en revisión: entra sola cuando se guarde con todo el contenido.";

  // "Me gusta": si te toca, da el OK; si no, explica por qué con un toast (no bloquea en silencio).
  const onLike = () => {
    if (puedeDar) {
      aprobar.mutate();
      return;
    }
    toast(motivoBloqueo);
  };

  // El cuerpo del post: el copy que la IA generó (`contenido`); si aún no hay, mostramos
  // el material original como marcador para que el post no quede vacío en "generando copy".
  const cuerpo = publicacion.contenido || publicacion.titulo;
  const imagen = publicacion.imagen_url || publicacion.imagen || publicacion.imagen_fuente;

  return (
    // Toda la tarjeta abre el editor al hacer clic (cabecera + previa + panel de estado); la zona
    // de botones y el hilo de comentarios NO (paran la propagación). Teclado: Enter/Espacio.
    <div
      role="button"
      tabIndex={0}
      onClick={() => setEditando(true)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setEditando(true);
        }
      }}
      title="Abrir para editar"
      aria-label="Abrir para editar"
      className="cursor-pointer rounded-xl border border-border bg-background text-left shadow-sm transition-colors hover:border-primary/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {/* Cabecera EN UNA SOLA LÍNEA: quién posteó · marca · red (un solo logo) · formato · tiempo.
          El logo/red y el formato NO se repiten en la previa (va en variante limpia, sin su propia
          cabecera): aquí están una vez y ya. La etapa baja a la fila de acciones. */}
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 pb-2 pt-3 text-xs text-muted-foreground">
        {generadaPorIA ? (
          <span
            className="inline-flex items-center gap-1 text-xs font-medium text-foreground"
            title="Pieza autogenerada por la IA"
          >
            <Bot className="h-3.5 w-3.5" aria-hidden="true" />
            IA
          </span>
        ) : (
          <Autor nombre={publicacion.autor_nombre} className="text-xs font-medium text-foreground" />
        )}
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
      </header>

      {/* El post tal como se verá en la red: variante LIMPIA = tarjeta uniforme (imagen 4:5 a
          ancho completo con distintivo de plataforma + copy debajo), igual para toda red. La
          imagen va a sangre (sin gutter); el copy ya trae su propio padding interno. (El título
          del material original NO se pinta: es el tema que "posteó" el equipo, no el copy.) */}
      <VistaPreviaRed
        red={publicacion.red}
        marca={publicacion.marca_nombre}
        contenido={cuerpo}
        copy_in={publicacion.copy_in}
        imagen_url={imagen || undefined}
        variante="limpia"
      />

      {/* Acciones: badge de ETAPA (izq) + iconos me gusta / rechazar / comentar (der). Esta zona
          NO abre el editor (para la propagación). El "me gusta" da el OK si te toca; si no, un toast
          explica por qué. "Rechazar" solo cuando puedes decidir. */}
      <div
        className="flex items-center gap-2 px-4 py-3"
        onClick={(e) => e.stopPropagation()}
      >
        <BadgeEtapa etapa={etapa} />
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant={puedeDar ? "positive" : "ghost"}
            size="icon"
            className="h-8 w-8"
            onClick={onLike}
            disabled={ocupado}
            title={tituloLike}
            aria-label="Me gusta"
          >
            {aprobar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : yaAprobada ? (
              <Check className="h-4 w-4" />
            ) : (
              <ThumbsUp className="h-4 w-4" />
            )}
          </Button>
          {puedeDar && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => rechazar.mutate()}
              disabled={ocupado}
              title="Rechazar"
              aria-label="Rechazar"
            >
              {rechazar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setComentariosAbierto((v) => !v)}
            aria-expanded={comentariosAbierto}
            title={comentariosAbierto ? "Ocultar comentarios" : "Comentar"}
            aria-label="Comentar"
          >
            <MessageSquare className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Editor rico (reusa el de Publicaciones): copy + imagen (placa con titular inline). Se MONTA
          solo al editar. Es un modal (portal): los clics dentro no abren otra vez la tarjeta. */}
      {editando && <DialogoEditar publicacion={publicacion} onCerrar={() => setEditando(false)} />}

      {/* Panel de ESTADO (solo en revisión y con cadena): veredicto de IA + OK del equipo
          (cuántos y de quién) + lo que falta. */}
      {enRevision && tieneCadena && cadena && (
        <CadenaAprobacion cadena={cadena} veredictoIA={publicacion.veredicto} />
      )}

      {/* Aviso de comentarios sin resolver (bloquean programar). */}
      {enRevision && sinResolver > 0 && (
        <div className="border-t border-border px-4 py-2 text-xs text-amber-600 dark:text-amber-400">
          {plural(sinResolver, "comentario")} sin resolver antes de programar.
        </div>
      )}

      {/* Hilo de comentarios del equipo. No abre el editor (para la propagación: tiene inputs). */}
      {comentariosAbierto && publicacion.contenido_id && (
        <div
          className="border-t border-border px-4 py-3"
          onClick={(e) => e.stopPropagation()}
        >
          <Comentarios contenidoId={publicacion.contenido_id} />
        </div>
      )}
    </div>
  );
}

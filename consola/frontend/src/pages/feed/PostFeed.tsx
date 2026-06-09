/**
 * Un POST del Feed de ideación (Flujo D, Fase 4): una pieza presentada como en una red
 * social interna, no como una tarjeta de kanban. Muestra, de arriba a abajo:
 *
 *  1. Cabecera EN UNA LÍNEA: autor + marca + red (un solo logo) + formato + etapa IA en vivo.
 *  2. Copy generado por la IA: el cuerpo del post (`contenido`), dentro de una previa fiel de la
 *     red (`VistaPreviaRed`, variante limpia: sin chrome social falso ni cabecera duplicada).
 *  3. Acciones EN LÍNEA, iguales en TODA pieza (como un post): "Me gusta" (el OK humano),
 *     "No me gusta" (dislike), "Editar" (copy, copy-in, foto+plantilla, vía `DialogoEditar`) y
 *     "Comentar". Like y dislike son un TOGGLE de tu reacción: un dislike tras tu like lo quita
 *     (vuelve a neutro) y el siguiente lo marca; el like quita tu dislike. El "me gusta" (marcar
 *     OK) y el "marcar dislike" solo se habilitan cuando te toca decidir (`elegibilidadOK`);
 *     QUITAR tu propia reacción siempre puedes. Dos dislikes (dos personas) rechazan la pieza.
 *  4. Panel de ESTADO de la cadena (`CadenaAprobacion`, solo lectura): veredicto de IA + OK del
 *     equipo (cuántos y de quién) + lo que falta. La acción vive en la fila, no aquí.
 *
 * Like/dislike/deshacer van por `aprobar`/`rechazar`/`deshacer` de `api/aprobacion`, que
 * forwardean al nivel ACTUAL de la cadena multinivel (respetando "otro par de ojos" y "dos
 * dislikes para rechazar"); el gate lo decide el backend, `elegibilidadOK` solo habilita/explica.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Inbox, Loader2, MessageSquare, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { confirmar } from "@/components/comunes/confirmar";
import { DistintivoRed } from "@/components/comunes/DistintivoRed";
import { Comentarios } from "@/components/contenido/Comentarios";
import { VistaPreviaRed } from "@/components/preview/VistaPreviaRed";
import { Button } from "@/components/ui/button";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { plural } from "@/lib/formato";
import {
  CLAVE_PUBLICACIONES,
  claveCadenaAprobacion,
  remplazarPublicacionEnCaches,
} from "@/pages/publicaciones/claves";
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
import { tiempoRelativo } from "@/pages/publicaciones/meta";
import type { Publicacion, RespuestaPublicacion } from "@/types";

import { elegibilidadOK } from "./aprobacion";
import { CadenaAprobacion } from "./CadenaAprobacion";
import { etapaDePublicacion } from "./etapa";
import { BadgeEtapa } from "./TarjetaEtapa";
import { CadenasLoteContexto } from "./use-cadenas-lote";

export function PostFeed({ publicacion }: { publicacion: Publicacion }) {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  const [comentariosAbierto, setComentariosAbierto] = React.useState(false);
  const [editando, setEditando] = React.useState(false);

  const etapa = etapaDePublicacion(publicacion);
  const enRevision = publicacion.estado === "en_revision";
  const yaAprobada = etapa === "aprobada" || etapa === "programada" || etapa === "publicada";
  // Autogenerada por la IA: sin autor humano (las piezas de la tubería —pipeline/rss/radar— no
  // tienen autor; las que postea el equipo SÍ). En ese caso la firma es "IA", no "desconocido".
  const generadaPorIA = !publicacion.autor_nombre?.trim();

  // Cadena de aprobación: alimenta tanto la UI MULTINIVEL (estado por nivel + decisión por
  // orden) como los avisos de gobernanza (firmas / comentarios sin resolver). Se carga
  // perezosamente cuando la pieza está en revisión (es cuando importa el gate). Si NO hay
  // cadena, el motor simple `aprobar`/`rechazar` forwardea a la cadena multinivel.
  // Se carga en revisión (cuando importa el OK) y también en piezas aprobadas pendientes de salir
  // (ahí el gate de comentarios sin resolver bloquea PROGRAMAR/publicar, como el "merge" de un PR).
  //
  // ANTI-N+1: dentro del feed, el padre pide las cadenas de la página en UN lote
  // (`useCadenasLote`) y las SIEMBRA en esta misma clave. Mientras el lote está en vuelo,
  // esta query queda deshabilitada (si no, cada tarjeta dispararía su GET en paralelo);
  // al aterrizar, encuentra el dato sembrado fresco (staleTime) y no refetchea. Fuera del
  // feed (sin contexto) o si el lote falla, carga individual como siempre.
  const lote = React.useContext(CadenasLoteContexto);
  const cadenaQuery = useQuery({
    queryKey: claveCadenaAprobacion(publicacion.id),
    queryFn: ({ signal }) => api.cadenaAprobacion(publicacion.id, signal),
    enabled:
      (enRevision || etapa === "aprobada") && !(lote?.pendiente(publicacion.id) ?? false),
    staleTime: 30_000,
  });
  const cadena = cadenaQuery.data;
  // Comentarios SIN RESOLVER: como en GitHub, bloquean publicar hasta marcarse resueltos. La cifra
  // viene de la cadena (cuenta los hilos abiertos del tema). Mientras carga es 0 (no bloquea de más).
  const sinResolver = cadena?.comentarios_sin_resolver ?? 0;
  // OK HUMANOS ya dados (decisor con id propio, no el reservado "auto" del QA/pre-aprobación). Si
  // los hay, editar el contenido los PERDERÁ (el backend resetea a borrador), así que avisamos.
  const aprobacionesHumanas = (cadena?.niveles ?? []).filter(
    (n) => n.decision === "aprobado" && n.decisor_id !== "" && n.decisor_id !== "auto",
  ).length;
  const tieneAprobaciones =
    etapa === "aprobada" || etapa === "programada" || aprobacionesHumanas > 0;
  // Hay cadena configurada => pintamos el panel "dale el OK"; si no, camino simple (legado).
  const tieneCadena = (cadena?.niveles?.length ?? 0) > 0;

  // Tras una reacción: actualiza SOLO la pieza afectada en las cachés de listados (antes se
  // invalidaba `CLAVE_PUBLICACIONES` entero, que refetcheaba TODAS las páginas del scroll
  // infinito por cada like) e invalida únicamente SU cadena. El kanban (`contenido`) se marca
  // stale en bloque: es otra superficie y se refresca al montarse.
  const tras = (mensaje: string) => (res?: RespuestaPublicacion) => {
    if (res?.publicacion) {
      remplazarPublicacionEnCaches(queryClient, res.publicacion);
    } else {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    }
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    void queryClient.invalidateQueries({ queryKey: claveCadenaAprobacion(publicacion.id) });
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
    // Un dislike NO devuelve a borrador por sí solo: hacen falta dos (de dos personas). El back
    // refleja el desenlace; aquí solo confirmamos que tu dislike quedó registrado.
    onSuccess: tras("Dislike registrado."),
    onError,
  });
  // Retira TU decisión (quitar tu like o tu dislike): tu nivel vuelve a pendiente.
  const deshacer = useMutation({
    mutationFn: () => api.deshacerAprobacion(publicacion.id),
    onSuccess: tras("Quitamos tu reacción."),
    onError,
  });
  // OVERRIDE: forzar la aprobación saltándose la cadena (admin/coordinador). Lo decide el backend;
  // aquí solo mostramos la acción y avisamos con un pop-up de que se salta el visto bueno del equipo.
  const forzar = useMutation({
    mutationFn: () => api.forzarAprobacion(publicacion.id),
    onSuccess: tras("Aprobación forzada (cadena saltada)."),
    onError,
  });
  const ocupado =
    aprobar.isPending || rechazar.isPending || forzar.isPending || deshacer.isPending;
  // TU reacción en esta pieza, leída de la cadena: el nivel que TÚ decidiste (si lo hay). "like"
  // si lo aprobaste, "dislike" si lo rechazaste, "neutral" si aún no decidiste. Es lo que hace
  // el toggle: con un like puesto, el dislike lo quita; desde neutro, el dislike lo marca.
  const miNivel = (cadena?.niveles ?? []).find(
    (n) =>
      !!usuario?.id &&
      n.decisor_id === usuario.id &&
      (n.decision === "aprobado" || n.decision === "rechazado"),
  );
  const miReaccion: "like" | "dislike" | "neutral" =
    miNivel?.decision === "aprobado"
      ? "like"
      : miNivel?.decision === "rechazado"
        ? "dislike"
        : "neutral";
  // ¿Esta sesión puede FORZAR? Admin o cargo de coordinación (o candidato a coordinador). El
  // backend es la fuente de verdad (403 si no); esto solo decide si se muestra el botón.
  const puedeForzar =
    usuario?.rol === "admin" ||
    (usuario?.cargo ?? "").startsWith("coordinador") ||
    !!usuario?.puede_coordinar;
  const onForzar = async () => {
    const ok = await confirmar({
      titulo: "Saltar la cadena de aprobación",
      mensaje:
        "Vas a aprobar esta pieza directamente, sin el visto bueno del resto del equipo: te saltas la cadena de aprobación. ¿Continuar?",
      textoConfirmar: "Forzar aprobación",
    });
    if (ok) forzar.mutate();
  };

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
  const esVideo = (publicacion.formato ?? "").trim().toLowerCase() === "video";
  const motivoBloqueo = yaAprobada
    ? publicacion.revisor_nombre
      ? `Ya aprobada · último OK: ${publicacion.revisor_nombre}`
      : "Esta pieza ya está aprobada."
    : enRevision
      ? motivo || "Espera tu turno para dar el OK."
      : etapa === "generando_copy"
        ? "Falta el copy: la IA aún lo está redactando."
        : etapa === "generando_arte"
          ? esVideo
            ? "Falta el video: ábrela y sube el clip."
            : "Falta la imagen: ábrela y súbela (se le aplicará la plantilla)."
          : "Aún no está en revisión: entra sola cuando se guarde con todo el contenido.";

  // "Me gusta": el like NUNCA quita tu like (eso es trabajo del dislike). Si tienes un dislike,
  // un like lo retira primero (un clic más dará el OK). En neutro y si te toca, da el OK (con el
  // gate de comentarios sin resolver). Si YA diste tu OK o no te toca, cae al manejo de "no
  // toca": un segundo like ofrece FORZAR la aprobación (saltar la cadena) a quien pueda; al resto
  // le explica con un toast por qué no puede dar el OK (no bloquea en silencio).
  const onLike = () => {
    if (miReaccion === "dislike") {
      deshacer.mutate(); // retira tu dislike antes de poder dar el OK
      return;
    }
    if (miReaccion === "neutral") {
      if (sinResolver > 0) {
        toast(`Resuelve ${plural(sinResolver, "comentario")} antes de aprobar y publicar.`);
        setComentariosAbierto(true);
        return;
      }
      if (puedeDar) {
        aprobar.mutate();
        return;
      }
    }
    // Ya diste tu OK (segundo like) o no te toca: si puedes FORZAR (admin/coordinador), el toast
    // ofrece saltarte la cadena; si no, explica por qué no puedes dar el OK.
    if (puedeForzar && enRevision && !yaAprobada) {
      toast(motivoBloqueo, {
        action: { label: "Forzar", onClick: () => void onForzar() },
      });
      return;
    }
    toast(motivoBloqueo);
  };

  // "No me gusta" (toggle): con tu like puesto, lo quita (vuelve a neutro); si ya tenías dislike,
  // lo quita (toggle off); desde neutro, si te toca, marca tu dislike (rechaza el nivel actual).
  // Dos dislikes de dos personas distintas rechazan la pieza (lo decide el backend). Si no te
  // toca decidir, un toast explica por qué. Marcar dislike NO depende de comentarios sin resolver
  // (ese gate es para publicar, no para objetar).
  const onDislike = () => {
    if (miReaccion === "like" || miReaccion === "dislike") {
      deshacer.mutate(); // "se quita el like" (o quita tu dislike si ya estaba marcado)
      return;
    }
    if (puedeDar) {
      rechazar.mutate(); // "se marca con dislike"
      return;
    }
    toast(motivoBloqueo);
  };

  // Abre el editor. Si la pieza ya tiene aprobaciones, AVISA primero: editarla las pierde (vuelve a
  // borrador y habrá que aprobarla de nuevo). Igual que reescribir un PR ya aprobado.
  const abrirEditor = async () => {
    if (tieneAprobaciones) {
      const ok = await confirmar({
        titulo: "Se perderán las aprobaciones",
        mensaje:
          "Esta pieza ya tiene el visto bueno del equipo. Si la editas, volverá a borrador y tendrá que aprobarse otra vez desde cero. ¿Quieres continuar?",
        textoConfirmar: "Editar de todas formas",
        textoCancelar: "Dejar como está",
      });
      if (!ok) return;
    }
    setEditando(true);
  };

  // El cuerpo del post: el copy que la IA generó (`contenido`); si aún no hay, mostramos
  // el material original como marcador para que el post no quede vacío en "generando copy".
  const cuerpo = publicacion.contenido || publicacion.titulo;
  const imagen = publicacion.imagen_url || publicacion.imagen || publicacion.imagen_fuente;

  return (
    // El editor se abre SOLO al pulsar la imagen (área interactiva de la pieza). La cabecera, el
    // copy (con su "leer más"), las acciones y los comentarios NO abren el editor.
    <div className="rounded-xl border border-border bg-background text-left shadow-sm">
      {/* Cabecera EN UNA SOLA LÍNEA: quién posteó (IA/autor) + distintivo de plataforma/formato ·
          tiempo. El distintivo (logo de red + icono de foto/vídeo, sin nombre ni dos burbujas) va
          JUNTO al logo de IA/autor, no sobre la imagen, para no taparla. */}
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
          <Autor
            nombre={publicacion.autor_nombre}
            conPrefijo={false}
            className="text-xs font-medium text-foreground"
          />
        )}
        <DistintivoRed red={publicacion.red} formato={publicacion.formato} />
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
        onAbrir={() => void abrirEditor()}
        variante="limpia"
      />

      {/* Acciones: badge de ETAPA (izq) + iconos me gusta / no me gusta / comentar (der). Esta
          zona NO abre el editor (para la propagación). Like y dislike son un TOGGLE de tu
          reacción; marcar OK / marcar dislike solo cuando te toca, quitar tu reacción siempre. */}
      <div
        className="flex items-center gap-2 px-4 py-3"
        onClick={(e) => e.stopPropagation()}
      >
        <BadgeEtapa etapa={etapa} formato={publicacion.formato} />
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            // El icono va en VERDE solo cuando TÚ ya diste tu OK; si aún no lo has dado (p. ej.
            // 0/2), queda negro/neutro.
            className={
              "h-8 w-8" +
              (miReaccion === "like"
                ? " text-emerald-600 hover:text-emerald-600 dark:text-emerald-400"
                : "")
            }
            onClick={onLike}
            disabled={ocupado}
            title={
              miReaccion === "like"
                ? puedeForzar
                  ? "Ya diste tu OK · pulsa para forzar la aprobación (saltar la cadena)"
                  : "Ya diste tu OK; falta el de otra persona"
                : miReaccion === "dislike"
                  ? "Quita tu dislike para poder dar el OK"
                  : sinResolver > 0
                    ? `Resuelve ${plural(sinResolver, "comentario")} antes de aprobar`
                    : tituloLike
            }
            aria-label="Me gusta"
            aria-pressed={miReaccion === "like"}
          >
            {aprobar.isPending || (deshacer.isPending && miReaccion === "dislike") ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : yaAprobada ? (
              <Check className="h-4 w-4" />
            ) : (
              <ThumbsUp className="h-4 w-4" />
            )}
          </Button>
          {/* Dislike: visible cuando puedes marcarlo (te toca) o cuando tienes una reacción que
              quitar (tu like o tu dislike). Dos dislikes de dos personas rechazan la pieza. */}
          {enRevision && (puedeDar || miReaccion !== "neutral") && (
            <Button
              variant="ghost"
              size="icon"
              // Igual que el OK pero en ROJO: solo cuando TÚ ya marcaste tu dislike; si no, negro/neutro.
              className={
                "h-8 w-8" +
                (miReaccion === "dislike" ? " text-red-600 hover:text-red-600 dark:text-red-400" : "")
              }
              onClick={onDislike}
              disabled={ocupado}
              title={
                miReaccion === "like"
                  ? "Quitar tu OK"
                  : miReaccion === "dislike"
                    ? "Quitar tu dislike"
                    : "No me gusta"
              }
              aria-label={miReaccion === "like" ? "Quitar tu OK" : "No me gusta"}
              aria-pressed={miReaccion === "dislike"}
            >
              {rechazar.isPending || (deshacer.isPending && miReaccion !== "neutral") ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ThumbsDown className="h-4 w-4" />
              )}
            </Button>
          )}
          {/* El OVERRIDE de forzar (admin/coordinador) ya NO es un icono en la tarjeta: se ofrece
              como acción discreta "Forzar" en el toast al intentar dar el OK sin que toque. */}
          {/* Comentar. Con hilos SIN RESOLVER muestra una bandeja (Inbox) con el conteo y en ámbar:
              avisa de que hay conversación pendiente que bloquea publicar (como en un PR). */}
          <Button
            variant="ghost"
            size="icon"
            className={
              sinResolver > 0
                ? "relative h-8 w-8 text-amber-600 dark:text-amber-400"
                : "relative h-8 w-8"
            }
            onClick={() => setComentariosAbierto((v) => !v)}
            aria-expanded={comentariosAbierto}
            title={
              sinResolver > 0
                ? `${plural(sinResolver, "comentario")} sin resolver`
                : comentariosAbierto
                  ? "Ocultar comentarios"
                  : "Comentar"
            }
            aria-label={sinResolver > 0 ? `${plural(sinResolver, "comentario")} sin resolver` : "Comentar"}
          >
            {sinResolver > 0 ? <Inbox className="h-4 w-4" /> : <MessageSquare className="h-4 w-4" />}
            {sinResolver > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold leading-none text-white tabular-nums">
                {sinResolver}
              </span>
            )}
          </Button>
        </div>
      </div>

      {/* Editor rico (reusa el de Publicaciones): copy + imagen (placa con titular inline). Se MONTA
          solo al editar. Es un modal (portal): los clics dentro no abren otra vez la tarjeta. */}
      {editando && <DialogoEditar publicacion={publicacion} onCerrar={() => setEditando(false)} />}

      {/* Enlace al PROCESO IA de esta pieza (su run del pipeline): dedup/fusión, jerarquización y
          criba. Solo en piezas que NACIERON del pipeline (`pipeline_id`); las manuales/radar/rss no
          tienen run que mostrar, así nadie busca un pipeline inexistente. */}
      {publicacion.pipeline_id && (
        <Link
          to={`/datos/actividad/pipelines/${encodeURIComponent(publicacion.pipeline_id)}`}
          onClick={(e) => e.stopPropagation()}
          className="flex w-full items-center gap-1.5 border-t border-border px-4 py-2 text-left text-xs text-muted-foreground hover:bg-muted/40"
          title="Ver el proceso de IA que produjo esta pieza (dedup, jerarquización, criba)"
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          Ver proceso IA
        </Link>
      )}

      {/* Panel de ESTADO (solo en revisión y con cadena): veredicto de IA + OK del equipo
          (cuántos y de quién) + lo que falta. */}
      {enRevision && tieneCadena && cadena && (
        <CadenaAprobacion cadena={cadena} veredictoIA={publicacion.veredicto} />
      )}

      {/* Aviso de comentarios sin resolver: bloquean aprobar/programar hasta marcarse resueltos. */}
      {sinResolver > 0 && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setComentariosAbierto(true);
          }}
          className="flex w-full items-center gap-1.5 border-t border-border px-4 py-2 text-left text-xs text-amber-600 hover:bg-amber-500/5 dark:text-amber-400"
        >
          <Inbox className="h-3.5 w-3.5" aria-hidden="true" />
          {plural(sinResolver, "comentario")} sin resolver antes de publicar.
        </button>
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

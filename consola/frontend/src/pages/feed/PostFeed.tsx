/**
 * Un POST del Feed de ideación (Flujo D, Fase 4): una pieza presentada como en una red
 * social interna, no como una tarjeta de kanban. Muestra, de arriba a abajo:
 *
 *  1. Cabecera EN UNA LÍNEA: autor + marca + red (un solo logo) + formato + etapa IA en vivo.
 *  2. Copy generado por la IA: el cuerpo del post (`contenido`), dentro de una previa fiel de la
 *     red (`VistaPreviaRed`, variante limpia: sin chrome social falso ni cabecera duplicada).
 *  3. Acciones EN LÍNEA, iguales en TODA pieza (como un post): "Me gusta" (el OK humano),
 *     "No me gusta" (dislike), "Editar" (copy, copy-in, foto+plantilla, vía `DialogoEditar`) y
 *     "Comentar". Cada botón es un TOGGLE estándar de SU PROPIA reacción: un segundo like quita
 *     tu OK; un segundo dislike quita tu dislike; un like con dislike puesto lo retira primero.
 *     El "marcar OK" y el "marcar dislike" solo se habilitan cuando te toca decidir
 *     (`elegibilidadOK`); QUITAR tu propia reacción siempre puedes. Dos dislikes (dos personas)
 *     rechazan la pieza. El override de FORZAR vive como botón discreto al pie del panel de
 *     estado (no escondido en un toast).
 *  4. Panel de ESTADO de la cadena (`CadenaAprobacion`, solo lectura): veredicto de IA + OK del
 *     equipo (cuántos y de quién) + lo que falta. La acción vive en la fila, no aquí.
 *
 * Like/dislike/deshacer van por `aprobar`/`rechazar`/`deshacer` de `api/aprobacion`, que
 * forwardean al nivel ACTUAL de la cadena multinivel (respetando "otro par de ojos" y "dos
 * dislikes para rechazar"); el gate lo decide el backend, `elegibilidadOK` solo habilita/explica.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CalendarClock,
  Copy,
  GitBranch,
  Loader2,
  MessageSquare,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { confirmar } from "@/components/comunes/confirmar";
import { DistintivoRed } from "@/components/comunes/DistintivoRed";
import { Comentarios } from "@/components/contenido/Comentarios";
import { VistaPreviaRed } from "@/components/preview/VistaPreviaRed";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHora, formatearFechaHoraCorta } from "@/lib/fecha";
import { plural } from "@/lib/formato";
import { cn } from "@/lib/utils";
import {
  CLAVE_PUBLICACIONES,
  claveCadenaAprobacion,
  remplazarPublicacionEnCaches,
} from "@/pages/publicaciones/claves";
import { DialogoClonar } from "@/pages/publicaciones/DialogoClonar";
import { DialogoEditar } from "@/pages/publicaciones/DialogoEditar";
import { tiempoRelativo } from "@/pages/publicaciones/meta";
import type { Publicacion, RespuestaPublicacion } from "@/types";

import { elegibilidadOK, esDislikeDecisivo } from "./aprobacion";
import { CadenaAprobacion } from "./CadenaAprobacion";
import { etapaDePublicacion } from "./etapa";
import { TEXTO_AVISO, TEXTO_ERROR, TEXTO_OK } from "./formato";
import { BadgeEtapa } from "./TarjetaEtapa";
import { CadenasLoteContexto } from "./use-cadenas-lote";

export function PostFeed({ publicacion }: { publicacion: Publicacion }) {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  const [comentariosAbierto, setComentariosAbierto] = React.useState(false);
  const [editando, setEditando] = React.useState(false);
  const [clonando, setClonando] = React.useState(false);
  // El hilo se abre al FONDO de la tarjeta (fuera del viewport en tarjetas altas): al abrirlo,
  // acércalo a la vista. Llamada opcional: jsdom no implementa scrollIntoView.
  const comentariosRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (comentariosAbierto) comentariosRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [comentariosAbierto]);

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
  // Cadena AÚN en vuelo (lote anti-N+1 o query individual sin aterrizar): el tooltip/toast del
  // like lo dice tal cual, sin inventarse un "espera tu turno" que todavía no consta.
  const cadenaCargando = enRevision && !cadena && !cadenaQuery.isError;
  // OK HUMANOS ya dados (decisor con id propio, no el reservado "auto" del QA/pre-aprobación). Si
  // los hay, editar el contenido los PERDERÁ (el backend resetea a borrador), así que avisamos.
  const aprobacionesHumanas = (cadena?.niveles ?? []).filter(
    (n) => n.decision === "aprobado" && n.decisor_id !== "" && n.decisor_id !== "auto",
  ).length;
  const tieneAprobaciones = yaAprobada || aprobacionesHumanas > 0;
  // Hay cadena configurada => pintamos el panel "dale el OK"; si no, camino simple (legado).
  const tieneCadena = (cadena?.niveles?.length ?? 0) > 0;

  // Tras una reacción: actualiza SOLO la pieza afectada en las cachés de listados (antes se
  // invalidaba `CLAVE_PUBLICACIONES` entero, que refetcheaba TODAS las páginas del scroll
  // infinito por cada like) e invalida únicamente SU cadena. El kanban (`contenido`) se marca
  // stale en bloque: es otra superficie y se refresca al montarse.
  const actualizarCaches = (res?: RespuestaPublicacion) => {
    if (res?.publicacion) {
      remplazarPublicacionEnCaches(queryClient, res.publicacion);
      if (res.publicacion.estado !== publicacion.estado) {
        // El cambio de ESTADO mueve la pieza de pestaña: refresca los conteos exactos de los
        // badges (3 queries `limite=1`, baratas; lo mismo que hace el botón Actualizar). Si no,
        // el número viejo desmiente la acción que el usuario acaba de ver.
        void queryClient.invalidateQueries({
          queryKey: [...CLAVE_PUBLICACIONES, "conteo-feed"],
        });
      }
    } else {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    }
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    void queryClient.invalidateQueries({ queryKey: claveCadenaAprobacion(publicacion.id) });
  };
  const tras = (mensaje: string) => (res?: RespuestaPublicacion) => {
    actualizarCaches(res);
    toast.success(mensaje);
  };
  const onError = (e: unknown) => toast.error(mensajeError(e));

  // Fallback para piezas legadas que estén en revisión SIN cadena (aprobar/rechazar forwardea).
  // El toast dice lo que DE VERDAD pasó: tu OK puede ser 1 de 2 (la pieza sigue en revisión) o
  // cerrar la cadena (queda aprobada/lista para salir). Como tu reacción siempre se puede
  // retirar, el toast ofrece "Deshacer" (patrón Gmail) salvo en estados finales distintos.
  const aprobar = useMutation({
    mutationFn: () => api.aprobarPublicacion(publicacion.id),
    onSuccess: (res) => {
      const cerrada =
        !!res?.publicacion &&
        ["aprobado", "programado", "publicado"].includes(res.publicacion.estado);
      actualizarCaches(res);
      // "ok": el spinner gira en el pulgar de ARRIBA y el toast final dice "Quitamos tu OK."
      // Si quien dio el OK puede FORZAR (admin/coordinación), el override vive AQUÍ, en el
      // toast del primer OK —no como botón permanente en la tarjeta—: acaba de dar su OK y
      // puede cerrar la cadena sin esperar el segundo; "Deshacer" queda como botón cancel.
      toast.success(
        cerrada
          ? "Pieza aprobada: lista para publicar."
          : "Tu OK quedó registrado; falta el de otra persona.",
        cerrada || !puedeForzar
          ? { action: { label: "Deshacer", onClick: () => deshacer.mutate("ok") } }
          : {
              action: { label: "Forzar aprobación", onClick: () => void onForzar() },
              cancel: { label: "Deshacer", onClick: () => deshacer.mutate("ok") },
            },
      );
    },
    onError,
  });
  const rechazar = useMutation({
    mutationFn: () => api.rechazarPublicacion(publicacion.id),
    // Un dislike NO devuelve a borrador por sí solo: hacen falta dos (de dos personas). El back
    // refleja el desenlace; el toast lo cuenta tal cual. "Deshacer" solo mientras la pieza siga
    // en revisión (devuelta a redacción es otro estado: no se deshace desde un toast).
    onSuccess: (res) => {
      actualizarCaches(res);
      if (res?.publicacion?.estado === "borrador") {
        // Rechazo definitivo: la tarjeta sale de la vista filtrada al instante; no se abre el
        // hilo (el confirm previo ya invitó a comentar antes).
        toast.success("Pieza rechazada: vuelve a redacción.");
        return;
      }
      // Primer dislike: la objeción sin porqué no le sirve a quien arregla la pieza — se abre
      // el hilo (hace scroll y deja el textarea a mano) para apuntar el motivo.
      setComentariosAbierto(true);
      toast.success("Dislike registrado; con un segundo dislike la pieza se rechaza.", {
        action: { label: "Deshacer", onClick: () => deshacer.mutate(undefined) },
      });
    },
    onError,
  });
  // Retira TU decisión (quitar tu like o tu dislike): tu nivel vuelve a pendiente. El `origen`
  // afina el toast: "ok" = togglear tu like; "like" = pulsaste OK teniendo un dislike puesto
  // (explica el paso intermedio y ofrece completar el OK en un clic); sin origen, el genérico.
  const deshacer = useMutation({
    mutationFn: (_origen?: "like" | "ok") => api.deshacerAprobacion(publicacion.id),
    onSuccess: (res, origen) => {
      if (origen === "like") {
        actualizarCaches(res);
        toast("Dislike retirado; pulsa de nuevo para dar tu OK.", {
          action: { label: "Dar OK", onClick: () => aprobar.mutate() },
        });
        return;
      }
      tras(origen === "ok" ? "Quitamos tu OK." : "Quitamos tu reacción.")(res);
    },
    onError,
  });
  // OVERRIDE: forzar la aprobación saltándose la cadena (admin/coordinador). Lo decide el backend;
  // aquí solo mostramos la acción y avisamos con un pop-up de que se salta el visto bueno del equipo.
  const forzar = useMutation({
    mutationFn: () => api.forzarAprobacion(publicacion.id),
    onSuccess: tras("Aprobación forzada (cadena saltada)."),
    onError,
  });
  // QUITAR DE ESTA RED: borra SOLO la pieza de esta red (la fila por plataforma); la idea y
  // sus demás redes se conservan. Si era la única red, el backend se lleva también la idea
  // (no deja un tema vacío). Es la forma de "salir solo en 3 redes": quitar las otras 2.
  const borrar = useMutation({
    mutationFn: () => api.eliminarPublicacion(publicacion.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success(`Pieza quitada de ${publicacion.red_nombre}.`);
    },
    onError,
  });
  const onBorrar = async () => {
    const ok = await confirmar({
      titulo: `Quitar de ${publicacion.red_nombre}`,
      mensaje:
        `Se borra solo la pieza de ${publicacion.red_nombre}; la idea y sus demás redes se ` +
        "conservan. Si es la única red, se borra la idea entera. ¿Continuar?",
      textoConfirmar: "Quitar",
    });
    if (ok) borrar.mutate();
  };
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

  // Por qué el "me gusta" está bloqueado (qué falta): FUENTE ÚNICA del tooltip del botón y del
  // toast al pulsarlo cuando no toca. Explica el gate (en revisión: tu pieza / ya diste OK /
  // espera turno) o, antes, qué le falta a la pieza. Si la cadena no pudo cargarse, lo dice
  // (sin inventarse un "espera tu turno" que no consta).
  const esVideo = (publicacion.formato ?? "").trim().toLowerCase() === "video";
  const motivoBloqueo = yaAprobada
    ? publicacion.revisor_nombre
      ? `Ya aprobada · último OK: ${publicacion.revisor_nombre}`
      : "Esta pieza ya está aprobada."
    : enRevision
      ? cadenaQuery.isError
        ? "No se pudo cargar el estado de aprobación; reintenta."
        : cadenaCargando
          ? "Cargando el estado de aprobación…"
          : motivo || "Espera tu turno para dar el OK."
      : etapa === "generando_copy"
        ? "Falta el copy: la IA aún lo está redactando."
        : etapa === "generando_arte"
          ? esVideo
            ? "Falta el video: ábrela y sube el clip."
            : "Falta la imagen: ábrela y súbela (se le aplicará la plantilla)."
          : "Aún no está en revisión: entra sola cuando se guarde con todo el contenido.";
  // Tooltip del "me gusta" cuando SÍ puedes; bloqueado, manda `motivoBloqueo` (fuente única).
  const tituloLike = puedeDar ? "Dale tu OK (me gusta) a esta pieza" : motivoBloqueo;

  // "Me gusta" como TOGGLE estándar de tu OK: con tu like puesto, lo quita; con tu dislike
  // puesto, lo retira primero (un clic más dará el OK); en neutro, comprueba PRIMERO si te toca
  // (`puedeDar`, con su motivo si no) y SOLO entonces el gate de comentarios sin resolver —el
  // orden importa: al autor de la pieza se le explica la elegibilidad, no se le manda a resolver
  // comentarios de un OK que no puede dar—.
  const onLike = () => {
    if (miReaccion === "like") {
      deshacer.mutate("ok"); // toggle off: quita tu OK
      return;
    }
    if (miReaccion === "dislike") {
      deshacer.mutate("like"); // retira tu dislike antes de poder dar el OK
      return;
    }
    if (!puedeDar) {
      // Falta material del equipo (foto/clip o copy): el toast lleva la acción que resuelve el
      // bloqueo (abrir el editor), clave en táctil donde no hay hover que enseñe dónde editar.
      if (
        !enRevision &&
        !yaAprobada &&
        (etapa === "generando_arte" || etapa === "generando_copy")
      ) {
        toast(motivoBloqueo, {
          action: { label: "Abrir", onClick: () => void abrirEditor() },
        });
        return;
      }
      toast(motivoBloqueo);
      return;
    }
    if (sinResolver > 0) {
      toast(`Resuelve ${plural(sinResolver, "comentario")} antes de aprobar y publicar.`);
      setComentariosAbierto(true);
      return;
    }
    aprobar.mutate();
  };

  // "No me gusta" (toggle de TU dislike): si ya está puesto, lo quita; desde neutro, si te toca,
  // marca tu dislike (rechaza el nivel actual). Con tu LIKE puesto ya NO lo deshace (cada botón
  // togglea solo su propia reacción): un toast te manda al "Me gusta" (con la acción directa de
  // quitarlo, simétrica al "Dar OK" del camino inverso). Dos dislikes de dos personas rechazan
  // la pieza (lo decide el backend). Marcar dislike NO depende de comentarios sin resolver (ese
  // gate es para publicar, no para objetar). El dislike DECISIVO (el que rechaza y resetea la
  // cadena: los OK dados se pierden) pide confirmación —es irreversible con un clic, igual que
  // "Forzar"—; el primer dislike va directo (cero fricción en el caso común).
  const onDislike = async () => {
    if (miReaccion === "dislike") {
      deshacer.mutate(undefined); // toggle off: quita tu dislike
      return;
    }
    if (miReaccion === "like") {
      toast("Tu OK está puesto; vuelve a pulsar «Me gusta» para quitarlo.", {
        action: { label: "Quitar mi OK", onClick: () => deshacer.mutate("ok") },
      });
      return;
    }
    if (puedeDar) {
      if (cadena && esDislikeDecisivo(cadena)) {
        const ok = await confirmar({
          titulo: "Rechazar la pieza",
          mensaje:
            "Tu dislike es el decisivo: la pieza se rechaza y vuelve a redacción, y los OK dados se pierden. ¿Continuar?",
          textoConfirmar: "Rechazar",
        });
        if (!ok) return;
      }
      rechazar.mutate(); // "se marca con dislike"
      return;
    }
    toast(motivoBloqueo);
  };

  // Abre el editor. Si la pieza ya tiene aprobaciones, AVISA primero: editarla las pierde (vuelve a
  // borrador y habrá que aprobarla de nuevo). Igual que reescribir un PR ya aprobado. En piezas
  // YA PUBLICADAS el aviso es otro: lo que salió a la red no cambia desde aquí.
  const abrirEditor = async () => {
    if (tieneAprobaciones) {
      const ok = await confirmar({
        titulo: "Se perderán las aprobaciones",
        mensaje:
          etapa === "publicada"
            ? "Esta pieza ya salió a la red. Editarla aquí solo cambia la copia interna y la devuelve a borrador. ¿Continuar?"
            : "Esta pieza ya tiene el visto bueno del equipo. Si la editas, volverá a borrador y tendrá que aprobarse otra vez desde cero. ¿Quieres continuar?",
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
    <article
      aria-label={publicacion.titulo}
      className="rounded-xl border border-border bg-card text-left text-card-foreground shadow-sm"
    >
      {/* Cabecera EN UNA SOLA LÍNEA (orden del rediseño aprobado): distintivo de FORMATO + RED
          (iconos pelados, sin nombre ni dos burbujas) → quién posteó (IA/autor) · tiempo. El
          distintivo va en la cabecera, no sobre la imagen, para no taparla. */}
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 pb-2 pt-3 text-xs text-muted-foreground">
        <DistintivoRed red={publicacion.red} formato={publicacion.formato} />
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
        <span className="ml-auto inline-flex items-center gap-2">
          {/* Antigüedad de la pieza: cuándo entró a revisión o, si aún no (en preparación),
              cuándo se creó. El `title` aclara QUÉ fecha es al hover; el `sr-only` lleva la
              misma aclaración a lectores de pantalla (patrón de `DistintivoRed`). */}
          {publicacion.enviado_a_revision_en ? (
            <span
              className="tabular-nums"
              title={`Enviada a revisión: ${formatearFechaHoraCorta(publicacion.enviado_a_revision_en)}`}
            >
              {tiempoRelativo(publicacion.enviado_a_revision_en)}
              <span className="sr-only">
                {` (enviada a revisión el ${formatearFechaHoraCorta(publicacion.enviado_a_revision_en)})`}
              </span>
            </span>
          ) : publicacion.fecha_creacion ? (
            <span
              className="tabular-nums"
              title={`Creada: ${formatearFechaHoraCorta(publicacion.fecha_creacion)}`}
            >
              {tiempoRelativo(publicacion.fecha_creacion)}
              <span className="sr-only">
                {` (creada el ${formatearFechaHoraCorta(publicacion.fecha_creacion)})`}
              </span>
            </span>
          ) : null}
          {/* Trazabilidad del PROCESO IA (su run del pipeline): consulta rara → icono discreto
              en la cabecera. GitBranch es el icono canónico del destino (pestaña Pipelines);
              Sparkles ya significa "usa IA" en esta misma tarjeta. La caja h-8/w-8 con márgenes
              negativos da target táctil sin mover el layout. */}
          {publicacion.pipeline_id && (
            <Tooltip label="Ver el proceso de IA que produjo esta pieza (dedup, jerarquización, criba)">
              <Link
                to={`/datos/actividad/pipelines/${encodeURIComponent(publicacion.pipeline_id)}`}
                onClick={(e) => e.stopPropagation()}
                className="-my-2 -mr-2 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
                aria-label="Ver proceso IA"
              >
                <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </Tooltip>
          )}
        </span>
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
        titulo={publicacion.titulo}
        onAbrir={() => void abrirEditor()}
        variante="limpia"
      />

      {/* Acciones: badge de ETAPA (izq) + iconos me gusta / no me gusta / comentar (der). Esta
          zona NO abre el editor (para la propagación). Like y dislike son un TOGGLE de tu
          reacción; marcar OK / marcar dislike solo cuando te toca, quitar tu reacción siempre. */}
      <div
        className="flex flex-wrap items-center gap-2 gap-y-1 px-4 pb-2 pt-1"
        onClick={(e) => e.stopPropagation()}
      >
        <BadgeEtapa etapa={etapa} formato={publicacion.formato} />
        {/* Cuándo sale/salió: la fecha de salida con CalendarClock, SIEMPRE en gris neutro (el
            ámbar semántico de "programada" ya lo porta el badge de etapa: dos señales cromáticas
            idénticas del mismo dato eran doble codificación). El hover (`title`/tooltip) da la
            fecha COMPLETA con año. En piezas programadas la fecha es el PUENTE a Programación
            (mismo tratamiento discreto que el enlace del proceso IA de la cabecera). */}
        {(etapa === "programada" || etapa === "publicada") &&
          publicacion.fecha_programada &&
          (etapa === "programada" ? (
            <Tooltip label="Ver en Programación">
              <Link
                to="/operacion/programacion"
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1 rounded-md text-xs tabular-nums text-muted-foreground hover:text-foreground"
                aria-label={`Programada para ${formatearFechaHora(publicacion.fecha_programada)} — ver en Programación`}
              >
                <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
                {formatearFechaHoraCorta(publicacion.fecha_programada)}
              </Link>
            </Tooltip>
          ) : (
            <span
              className="inline-flex items-center gap-1 text-xs tabular-nums text-muted-foreground"
              title={`Publicada el ${formatearFechaHora(publicacion.fecha_programada)}`}
            >
              <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
              <span aria-hidden="true">
                {formatearFechaHoraCorta(publicacion.fecha_programada)}
              </span>
              <span className="sr-only">
                {`Publicada el ${formatearFechaHora(publicacion.fecha_programada)}`}
              </span>
            </span>
          ))}
        {/* En estados cerrados el botón de like NO se pinta (sería un falso affordance): el
            dato del último OK se conserva aquí, como metadato legible (truncado: en celdas
            estrechas un nombre largo no debe desbordar la tarjeta). */}
        {yaAprobada && publicacion.revisor_nombre && (
          <span
            className="min-w-0 max-w-[12rem] truncate text-xs text-muted-foreground"
            title="Último OK"
          >
            OK: {publicacion.revisor_nombre}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          {!yaAprobada && (
            <Tooltip
              label={
                miReaccion === "like"
                  ? "Ya diste tu OK · vuelve a pulsar para quitarlo"
                  : miReaccion === "dislike"
                    ? "Tu dislike está puesto; púlsalo para retirarlo y poder dar el OK"
                    : puedeDar && sinResolver > 0
                      ? `Resuelve ${plural(sinResolver, "comentario")} antes de aprobar`
                      : tituloLike
              }
            >
              <Button
                variant="ghost"
                size="icon"
                // VERDE solo cuando TÚ ya diste tu OK; gris de reposo en el resto. (El acento
                // keni para "te toca decidir" se leía como ROJO en un botón sin pulsar y
                // confundía: el color queda reservado al estado pulsado.)
                className={cn(
                  "h-10 w-10 text-muted-foreground hover:text-foreground sm:h-8 sm:w-8",
                  miReaccion === "like" &&
                    cn(TEXTO_OK, "hover:text-emerald-700 dark:hover:text-emerald-300"),
                )}
                onClick={onLike}
                disabled={ocupado}
                // Nombre accesible derivado del ESTADO REAL del toggle (fuente única:
                // `motivoBloqueo` cuando no puedes; nada de "pulsa para forzar" aquí).
                aria-label={
                  miReaccion === "like"
                    ? "Quitar tu OK"
                    : miReaccion === "dislike"
                      ? "Retirar tu dislike"
                      : puedeDar
                        ? "Dale tu OK"
                        : "Me gusta: no disponible"
                }
                aria-pressed={miReaccion === "like"}
              >
                {aprobar.isPending || (deshacer.isPending && deshacer.variables !== undefined) ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ThumbsUp className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
          )}
          {/* Dislike: SIEMPRE visible en piezas en revisión (fila estable, no baila entre
              tarjetas); cuando no te toca, onDislike explica con un toast, igual que el like.
              Dos dislikes de dos personas rechazan la pieza. */}
          {enRevision && (
            <Tooltip
              label={
                miReaccion === "like"
                  ? "Tu OK está puesto; quítalo con «Me gusta»"
                  : miReaccion === "dislike"
                    ? "Quitar tu dislike"
                    : "No me gusta"
              }
            >
              <Button
                variant="ghost"
                size="icon"
                // Igual que el OK pero en ROJO: solo cuando TÚ ya marcaste tu dislike; si no, reposo.
                className={cn(
                  "h-10 w-10 text-muted-foreground hover:text-foreground sm:h-8 sm:w-8",
                  miReaccion === "dislike" &&
                    cn(TEXTO_ERROR, "hover:text-red-700 dark:hover:text-red-300"),
                )}
                onClick={() => void onDislike()}
                disabled={ocupado}
                aria-label={miReaccion === "dislike" ? "Quitar tu dislike" : "No me gusta"}
                aria-pressed={miReaccion === "dislike"}
              >
                {rechazar.isPending || (deshacer.isPending && deshacer.variables === undefined) ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ThumbsDown className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
          )}
          {/* El OVERRIDE de forzar (admin/coordinador) vive como botón discreto al pie del panel
              de estado (`CadenaAprobacion`), no aquí ni escondido en un toast. */}
          {/* Comentar: SIEMPRE el mismo icono (identidad estable del botón). Con hilos SIN
              RESOLVER se tiñe de ámbar y muestra la burbuja con el conteo: conversación
              pendiente que bloquea publicar (como en un PR). Abierto, queda marcado con
              `bg-accent` (el hilo puede abrirse fuera del viewport en tarjetas altas). Sin
              `contenido_id` no hay hilo donde escribir: visible pero DESHABILITADO (la fila
              se mantiene estable, mismo criterio que el dislike) y el rótulo lo explica. */}
          <Tooltip
            label={
              !publicacion.contenido_id
                ? "Esta pieza no tiene hilo de comentarios"
                : sinResolver > 0
                  ? `Comentar (${plural(sinResolver, "comentario")} sin resolver)`
                  : comentariosAbierto
                    ? "Ocultar comentarios"
                    : "Comentar"
            }
          >
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "relative h-10 w-10 text-muted-foreground hover:text-foreground sm:h-8 sm:w-8",
                sinResolver > 0 && TEXTO_AVISO,
                comentariosAbierto && "bg-accent text-foreground",
              )}
              onClick={() => setComentariosAbierto((v) => !v)}
              disabled={!publicacion.contenido_id}
              aria-expanded={comentariosAbierto}
              aria-label={
                !publicacion.contenido_id
                  ? "Esta pieza no tiene hilo de comentarios"
                  : sinResolver > 0
                    ? `Comentar (${plural(sinResolver, "comentario")} sin resolver)`
                    : "Comentar"
              }
            >
              <MessageSquare className="h-4 w-4" />
              {sinResolver > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold leading-none tabular-nums text-amber-950">
                  {sinResolver}
                </span>
              )}
            </Button>
          </Tooltip>
          {/* Clonar a OTRA RED de la misma idea (copy + copy-in + foto): abre el diálogo con
              el selector de red destino. Sin `contenido_id` no hay idea padre de la que
              colgar la copia: deshabilitado (fila estable, mismo criterio que Comentar). */}
          <Tooltip
            label={
              !publicacion.contenido_id
                ? "Esta pieza no tiene idea padre: no se puede clonar entre redes"
                : "Clonar a otra red (copy, texto en imagen y foto)"
            }
          >
            <Button
              variant="ghost"
              size="icon"
              className="h-10 w-10 text-muted-foreground hover:text-foreground sm:h-8 sm:w-8"
              onClick={() => setClonando(true)}
              disabled={!publicacion.contenido_id}
              aria-label="Clonar a otra red"
            >
              <Copy className="h-4 w-4" />
            </Button>
          </Tooltip>
          {/* Quitar de ESTA red: borra solo la pieza de esta red (con confirmación); la idea
              y sus demás redes se conservan. Así una idea sale solo en las redes que quieras. */}
          <Tooltip label={`Quitar de ${publicacion.red_nombre}`}>
            <Button
              variant="ghost"
              size="icon"
              className="h-10 w-10 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 sm:h-8 sm:w-8"
              onClick={() => void onBorrar()}
              disabled={borrar.isPending}
              aria-label={`Quitar de ${publicacion.red_nombre}`}
            >
              {borrar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          </Tooltip>
        </div>
      </div>

      {/* Editor rico (reusa el de Publicaciones): copy + imagen (placa con titular inline). Se MONTA
          solo al editar. Es un modal (portal): los clics dentro no abren otra vez la tarjeta. */}
      {editando && <DialogoEditar publicacion={publicacion} onCerrar={() => setEditando(false)} />}

      {/* Clonado entre redes (copy + copy-in + foto, misma idea). Modal: se monta al pedirlo. */}
      {clonando && (
        <DialogoClonar publicacion={publicacion} onCerrar={() => setClonando(false)} />
      )}

      {/* Panel de ESTADO (solo en revisión y con cadena): veredicto de IA + OK del equipo
          (cuántos y de quién) + lo que falta (comentarios sin resolver). El override de
          forzar ya NO es un botón de la tarjeta: se ofrece en el toast del primer OK
          (admin/coordinación), con su misma confirmación. Para piezas aprobadas sin panel,
          la burbuja del botón Comentar sigue siendo la señal de hilos abiertos. */}
      {enRevision && tieneCadena && cadena && (
        <CadenaAprobacion
          cadena={cadena}
          veredictoIA={publicacion.veredicto}
          sinResolver={sinResolver}
        />
      )}

      {/* La cadena NO cargó (red/500): se dice y se ofrece reintentar, en vez de dejar el panel
          mudo y el like contando una historia falsa. */}
      {enRevision && cadenaQuery.isError && (
        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-2 text-xs text-muted-foreground">
          <span>No se pudo cargar el estado de aprobación.</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              void cadenaQuery.refetch();
            }}
          >
            {cadenaQuery.isFetching && <Loader2 className="h-3 w-3 animate-spin" />}
            Reintentar
          </Button>
        </div>
      )}

      {/* Hilo de comentarios del equipo. No abre el editor (para la propagación: tiene inputs).
          Los comentarios cuelgan del CONTENIDO padre: el mismo hilo aparece en las tarjetas
          hermanas (otras redes de la misma idea); la línea de contexto lo aclara. */}
      {comentariosAbierto && publicacion.contenido_id && (
        <div
          ref={comentariosRef}
          className="border-t border-border px-4 py-3"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="mb-2 text-xs text-muted-foreground">
            Conversación de la idea (común a todas sus redes)
          </p>
          <Comentarios contenidoId={publicacion.contenido_id} />
        </div>
      )}
    </article>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { BadgeResponsable } from "@/components/comunes/BadgeResponsable";
import { confirmar } from "@/components/comunes/confirmar";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { HerramientasHashtags } from "@/components/hashtags/HerramientasHashtags";
import { EditorCarrusel } from "@/components/media/EditorCarrusel";
import { EditorImagen } from "@/components/media/EditorImagen";
import { EditorPlacaInline } from "@/components/media/EditorPlacaInline";
import { EditorVideo } from "@/components/media/EditorVideo";
import type { Documento } from "@/editor/documento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { parsearCarrusel, serializarCarrusel, type SlideCarrusel } from "@/lib/carrusel";
import { capasFotoDoc, type FotoCollage } from "@/lib/placa/docPieza";
import {
  parsearEncuadre,
  parsearFotos,
  serializarEncuadre,
  serializarFotos,
} from "@/lib/placa/encuadre";
import type { CuerpoActualizarPublicacion, Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { GestionHashtags } from "./GestionHashtags";
import { metaRed } from "./meta";
import { etapaDePublicacion } from "@/pages/feed/etapa";

/** Diálogo de edición de una publicación, MÍNIMO: solo contenido (copy) + hashtags + imagen. Los
 *  posts no llevan título; el formato es texto plano (sin barra de formato ni UTM). Comentarios y
 *  versiones viven en el feed, no aquí. El estado/programación/aprobación los gestiona el flujo. */
export function DialogoEditar({
  publicacion,
  onCerrar,
}: {
  publicacion: Publicacion | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [contenido, setContenido] = React.useState("");
  // Texto que va DENTRO de la imagen (copy-in), distinto del contenido que la acompaña.
  const [copyIn, setCopyIn] = React.useState("");
  // Imagen: nombre del archivo + url para previsualizar.
  const [imagen, setImagen] = React.useState("");
  const [imagenUrl, setImagenUrl] = React.useState("");
  // "Quitar plantilla": publicar solo la foto, sin placa. Se persiste en la pieza (`placa_oculta`).
  const [placaOculta, setPlacaOculta] = React.useState(false);
  // Plantilla del estudio elegida ("" = placa de marca por defecto / editor en vivo). La pieza la
  // recuerda (`plantilla_diseno_id`); en modo plantilla el editor muestra el resultado renderizado.
  const [plantillaId, setPlantillaId] = React.useState("");
  // COLLAGE: una foto por HUECO (media id + reencuadre), en orden de `capas`. El hueco único legado
  // es `[{objeto: foto, foco/zoom de foto_encuadre}]`. La pieza lo persiste como JSON en `fotos`.
  const [fotos, setFotos] = React.useState<FotoCollage[]>([]);
  const [galeriaPlantillas, setGaleriaPlantillas] = React.useState(false);
  // ESPEJO entre redes (default ON): lo que se edita aquí se aplica también a las demás redes
  // de la idea (el backend propaga copy/copy-in/foto al guardar). Vive en la idea (padre):
  // togglearlo desde cualquier red afecta a todas. OFF = cada red se edita por separado.
  const [espejo, setEspejo] = React.useState(true);
  // Formato de la pieza ("foto"|"video"|"carrusel") + estado del video.
  const [formato, setFormato] = React.useState("foto");
  const [videoKey, setVideoKey] = React.useState("");
  const [videoUrl, setVideoUrl] = React.useState("");
  // CARRUSEL: slides EXTRA en crudo detrás de la portada (la portada es la placa de arriba).
  const [slides, setSlides] = React.useState<SlideCarrusel[]>([]);
  // --- Autoguardado --- //
  // La pieza se guarda SOLA al editar (debounced); no hay botón ni indicador de guardado.
  const cargandoRef = React.useRef(true); // true mientras se cargan los valores al abrir (no autoguarda)
  const guardandoRef = React.useRef(false); // hay un guardado en curso
  const pendienteRef = React.useRef(false); // hubo cambios durante el guardado en curso
  const [gestionHashtags, setGestionHashtags] = React.useState(false);

  // Catálogo de marcas para la gestión de grupos de hashtags.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: publicacion !== null,
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  // Plantillas del estudio por MARCA: como todo es 4:5 y se postea lo mismo a todas las redes, la
  // plantilla la dicta la marca (no la red). Distintas plantillas cubren los tipos de post
  // (breaking, infografía con logo, cita textual, logo del mundial, sin nada…). Se cargan siempre
  // (con marca) porque el editor renderiza la plantilla EN VIVO y necesita su documento.
  const plantillasQuery = useQuery({
    queryKey: ["plantillas-diseno", publicacion?.marca],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: publicacion?.marca }, signal),
    enabled: !!publicacion?.marca,
  });
  // Tipo de plantilla según el formato de la pieza: video → miniaturas (portada); foto → fotos.
  const tipoPlantilla = formato === "video" ? "miniatura" : "foto";
  const plantillas = React.useMemo(
    () => (plantillasQuery.data?.plantillas ?? []).filter((p) => (p.tipo ?? "foto") === tipoPlantilla),
    [plantillasQuery.data, tipoPlantilla],
  );
  // Plantilla por defecto de la marca: la "Placa de marca" migrada (o la primera que haya).
  const idPlacaDeMarca =
    plantillas.find((p) => p.nombre === "Placa de marca")?.id ?? plantillas[0]?.id ?? "";
  // Plantilla efectiva = la elegida por la pieza, o la de marca por defecto si no eligió ninguna.
  const idEfectivo = plantillaId || idPlacaDeMarca;
  // Documento a renderizar en vivo: null en modo "solo foto" (placaOculta) o si no hay plantilla.
  const documentoSel = React.useMemo(() => {
    if (placaOculta) return null;
    const p = plantillas.find((x) => x.id === idEfectivo);
    return (p?.documento as Documento | undefined) ?? null;
  }, [placaOculta, plantillas, idEfectivo]);

  // Elegir una plantilla de la galería: previa EN VIVO (sin round-trip); se hornea al guardar.
  const elegirPlantilla = (idPlantilla: string) => {
    setPlantillaId(idPlantilla);
    setPlacaOculta(false);
    setGaleriaPlantillas(false);
  };

  // Flip de formato (foto/video/carrusel). PATCH /api/contenido/{contenido_id} con {formato}.
  // El backend ajusta las redes (3/5/2) y puede devolver un `aviso` si había redes con contenido.
  const flipFormato = useMutation({
    mutationFn: (nuevoFormato: string) => {
      if (!publicacion) throw new Error("Sin publicación");
      return api.actualizarContenido(publicacion.contenido_id, { formato: nuevoFormato });
    },
    onSuccess: (data) => {
      const nuevoFmt = data.contenido.formato || "foto";
      setFormato(nuevoFmt);
      // Al salir de carrusel el backend limpia sus slides: el estado local los suelta también
      // (si no, el autoguardado los re-escribiría).
      if (nuevoFmt !== "carrusel") setSlides([]);
      if (data.aviso) toast(data.aviso);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Cambia el formato PIDIENDO CONFIRMACIÓN: el cambio puede ser destructivo —el backend borra
  // el asset del formato anterior (la parte visual al pasar a vídeo, el vídeo al pasar a un
  // formato de imagen, los slides al salir de carrusel), quita la plantilla y devuelve la pieza
  // a borrador (pierde el «listo para revisar»)—. Confirmamos siempre porque el asset a perder
  // puede estar en otras redes de la pieza (no solo en la que se edita aquí), así que no se
  // puede detectar de forma fiable desde una sola fila.
  const cambiarFormato = async (nuevo: string) => {
    if (!publicacion || nuevo === formato) return;
    const etiqueta = nuevo === "video" ? "video" : nuevo === "carrusel" ? "carrusel" : "foto";
    const pierde =
      nuevo === "video"
        ? "la foto (y los slides, si los hay)"
        : formato === "video"
          ? "el video"
          : formato === "carrusel"
            ? "los slides del carrusel"
            : "nada de la foto (se conserva)";
    const ok = await confirmar({
      titulo: "Cambiar formato",
      mensaje:
        `Al cambiar a ${etiqueta} se borrará ${pierde} y la plantilla actual, y la ` +
        `pieza volverá a borrador (perderá el «listo para revisar»). ¿Continuar?`,
      destructivo: true,
      textoConfirmar: "Cambiar formato",
    });
    if (!ok) return;
    flipFormato.mutate(nuevo);
  };

  // Toggle del espejo: PUT inmediato (no espera al autoguardado debounced; es un ajuste de la
  // idea, no una edición de contenido). Optimista: el switch responde al instante.
  const cambiarEspejo = useMutation({
    mutationFn: (v: boolean) => {
      if (!publicacion) throw new Error("Sin publicación");
      return api.actualizarPublicacion(publicacion.id, { espejo: v });
    },
    onSuccess: (data) => {
      setEspejo(data.publicacion.espejo ?? true);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    },
    onError: (e, v) => {
      setEspejo(!v); // revierte el optimismo: el backend no lo aplicó
      toast.error(mensajeError(e));
    },
  });

  // Ola F: guardar video (PATCH plataforma con {video}).
  const guardarVideo = useMutation({
    mutationFn: ({ clave }: { clave: string; url: string }) => {
      if (!publicacion) throw new Error("Sin publicación");
      return api.actualizarPlataforma(publicacion.contenido_id, publicacion.id, { video: clave });
    },
    onSuccess: (_data, { clave, url }) => {
      setVideoKey(clave);
      setVideoUrl(url);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Cargamos los valores cada vez que se abre con una publicación nueva.
  React.useEffect(() => {
    if (!publicacion) return;
    cargandoRef.current = true; // no autoguardar por los cambios de estado que provoca esta carga
    setContenido(publicacion.contenido);
    setCopyIn(publicacion.copy_in ?? "");
    setImagen(publicacion.imagen ?? "");
    setImagenUrl(publicacion.imagen_url ?? "");
    setPlacaOculta(publicacion.placa_oculta ?? false);
    setPlantillaId(publicacion.plantilla_diseno_id ?? "");
    setEspejo(publicacion.espejo ?? true);
    // Formato, video y slides del carrusel.
    setFormato(publicacion.formato || "foto");
    setVideoKey(publicacion.video ?? "");
    setVideoUrl("");
    setSlides(parsearCarrusel(publicacion.carrusel));
    // Carga del collage: si la pieza trae `fotos` (JSON), úsalo; si no, deriva el hueco único del
    // par legado `foto`/`foto_encuadre`.
    const fotosGuardadas = parsearFotos(publicacion.fotos);
    if (fotosGuardadas.length) {
      setFotos(fotosGuardadas);
    } else {
      const enc = parsearEncuadre(publicacion.foto_encuadre);
      setFotos([{ objeto: publicacion.foto ?? "", foco: enc?.foco ?? null, zoom: enc?.zoom ?? 0 }]);
    }
    // Reabrimos el autoguardado tras aplicar la carga (en un tick: así el render que dispara esta
    // carga ve `cargandoRef=true` y no guarda; solo los cambios del usuario posteriores guardan).
    const t = setTimeout(() => {
      cargandoRef.current = false;
    }, 0);
    return () => clearTimeout(t);
  }, [publicacion]);

  const limite = publicacion ? metaRed(publicacion.red).limite : null;
  // Pieza ya `publicado`: SOLO LECTURA. Lo que salió a redes no puede diferir de lo mostrado, así
  // que el back la congela (409). En vez de dejar editar y fallar, el editor abre inerte: no se
  // autoguarda nada y los controles quedan deshabilitados (no hay PATCH que rechazar).
  const publicada = publicacion?.estado === "publicado";

  // Persiste la pieza. NO cierra el diálogo: lo comparten el autoguardado y el cierre.
  const persistir = React.useCallback(async () => {
    if (!publicacion) return;
    const imagenFinal = publicacion.marca ? "" : imagen;
    // COLLAGE: persistimos `fotos` (una foto por hueco). Por RETROCOMPAT sincronizamos el hueco 0 al
    // par legado `foto`/`foto_encuadre`, que el backend (y consumidores viejos) siguen leyendo.
    const hueco0 = fotos[0];
    const foco0 = hueco0?.foco ?? null;
    const zoom0 = hueco0?.zoom && hueco0.zoom > 0 ? hueco0.zoom : 1;
    // NO se envía `titulo`: los posts no llevan título; PATCH parcial deja intacto lo no enviado.
    const cuerpo: CuerpoActualizarPublicacion = {
      contenido,
      copy_in: copyIn,
      imagen: imagenFinal,
      // Hueco 0 derivado del collage (retrocompat con `foto`/`foto_encuadre`).
      foto: hueco0?.objeto ?? "",
      placa_oculta: placaOculta,
      // Recuerda (o limpia) la plantilla del estudio elegida.
      plantilla_diseno_id: plantillaId,
      // Reencuadre manual del hueco 0 ("" si está centrado sin zoom).
      foto_encuadre: foco0 ? serializarEncuadre({ foco: foco0, zoom: zoom0 }) : "",
      // Collage completo (todas las fotos por hueco) como JSON.
      fotos: serializarFotos(fotos),
    };
    // CARRUSEL: solo se envían los slides cuando la pieza ES carrusel (en otros formatos el
    // backend ya los limpió en el flip; reenviar el estado local viejo los resucitaría).
    if (formato === "carrusel") {
      cuerpo.carrusel = serializarCarrusel(slides);
    }
    // El estado, la fecha y evergreen NO se tocan aquí: el flujo los gestiona solo (autogen → verificación →
    // me gusta → auto-programar). PATCH parcial: lo no enviado queda intacto.
    const { publicacion: actualizada } = await api.actualizarPublicacion(publicacion.id, cuerpo);
    // AUTO-AVANCE: una pieza autogenerada/editada que YA tiene todo el contenido entra sola a
    // revisión (abre los "me gusta" del equipo). Sustituye al botón manual "Enviar a revisión".
    // GATE COLLAGE: solo auto-avanza si TODOS los huecos del diseño están llenos (no faltan fotos).
    // El hueco 0 cuenta como lleno también si la pieza trae imagen original de RSS (`imagen_fuente`),
    // que es el respaldo que pinta el editor (igual que su contador): sin esto, una pieza de marca
    // cuya única imagen es la original ya no auto-avanzaría al editar el copy.
    const huecosDoc = documentoSel ? capasFotoDoc(documentoSel).length : 1;
    const llenos = fotos.filter((f, i) => f.objeto || (i === 0 && !!publicacion.imagen_fuente)).length;
    const fotosCompletas = llenos >= Math.max(1, huecosDoc);
    if (
      fotosCompletas &&
      actualizada.estado === "borrador" &&
      etapaDePublicacion(actualizada) === "lista_para_revisar"
    ) {
      try {
        await api.enviarARevision(publicacion.id);
      } catch {
        /* carrera / ya en revisión: lo ignoramos (el feed reflejará el estado real) */
      }
    }
  }, [publicacion, fotos, copyIn, placaOculta, plantillaId, imagen, contenido, documentoSel, formato, slides]);

  // Solo se autoguarda cuando hay contenido (el copy del post) y la pieza NO está publicada
  // (publicada = inmutable: nada que persistir). Sin título: ya no lo exige.
  const datosValidos = !!publicacion && contenido.trim().length > 0 && !publicada;

  // Autoguardado: persiste sin cerrar; coalesciona los cambios ocurridos durante un guardado en curso.
  const autoguardar = React.useCallback(async () => {
    if (!datosValidos) return;
    if (guardandoRef.current) {
      pendienteRef.current = true;
      return;
    }
    guardandoRef.current = true;
    try {
      await persistir();
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      // Editar puede RESETEAR las aprobaciones (vuelve a borrador): refresca la cadena para que la
      // tarjeta no siga mostrando los OK viejos.
      if (publicacion) {
        void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", publicacion.id] });
      }
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      guardandoRef.current = false;
      if (pendienteRef.current) {
        pendienteRef.current = false;
        void autoguardar();
      }
    }
  }, [datosValidos, persistir, queryClient, publicacion]);

  const autoguardarRef = React.useRef(autoguardar);
  autoguardarRef.current = autoguardar;

  // Cerrar = salir. No hay botón "Guardar": los cambios se guardan solos. Al cerrar forzamos un
  // último guardado por si quedaba algo sin volcar (el autoguardado es debounced); es best-effort y
  // no bloquea el cierre (la promesa sigue aunque el diálogo se desmonte).
  const cerrar = React.useCallback(() => {
    void autoguardarRef.current();
    onCerrar();
  }, [onCerrar]);

  // Dispara el autoguardado (debounced 1.2 s) cuando el usuario cambia algo. La `imagen` NO entra
  // en la firma: es resultado del horneado, no una edición del usuario (evita un bucle de guardado).
  const firmaAutoguardado = JSON.stringify({
    contenido, copyIn, placaOculta, plantillaId,
    fotos: serializarFotos(fotos),
    carrusel: formato === "carrusel" ? serializarCarrusel(slides) : "",
  });
  React.useEffect(() => {
    if (cargandoRef.current || !publicacion) return;
    const t = setTimeout(() => void autoguardarRef.current(), 1200);
    return () => clearTimeout(t);
  }, [firmaAutoguardado, publicacion]);

  return (
    <Dialog open={publicacion !== null} onOpenChange={(o) => !o && cerrar()}>
      {/* En móvil el editor ocupa toda la pantalla (h-dvh, ancho completo, sin
          radios) para que el revisor edite cómodo en el feed; en escritorio
          mantiene el modal centrado de 2xl. */}
      <DialogContent className="max-h-dvh h-dvh max-w-full overflow-y-auto rounded-none sm:h-auto sm:max-h-[90vh] sm:max-w-2xl sm:rounded-lg">
        <DialogHeader>
          <DialogTitle>Editar publicación</DialogTitle>
          {publicacion && (
            <DialogDescription>
              {publicacion.red_nombre} · {publicacion.marca_nombre}
            </DialogDescription>
          )}
          {/* "La lista" (ClaroSports): quién lleva la pieza, SOLO LECTURA. Aquí avisa a quien edita
              que la pieza ya está cogida por otra persona (antes era invisible en el editor). */}
          {publicacion && (
            <BadgeResponsable
              marca={publicacion.marca}
              responsableId={publicacion.responsable_id}
              responsableNombre={publicacion.responsable_nombre}
              className="self-start"
            />
          )}
          {/* Pieza ya publicada: aviso de SOLO LECTURA. Lo que salió a redes no se edita; el
              editor abre para verla, con todos los controles inertes. */}
          {publicada && (
            <p className="self-start rounded-md bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">
              Ya publicada · solo lectura
            </p>
          )}
        </DialogHeader>

        {/* Orden de edición: primero la IMAGEN/VIDEO, luego el CONTENIDO (copy) y al final los HASHTAGS.
            Publicada = inerte: `pointer-events-none` neutraliza todos los controles (galería de
            plantillas, formato, espejo, subir foto…) sin tener que cablear `disabled` en cada hijo;
            el autoguardado ya está cortado aguas arriba, así que nada puede persistir. */}
        <div
          className={cn("space-y-4", publicada && "pointer-events-none opacity-70")}
          aria-disabled={publicada || undefined}
        >
          {/* Formato de la pieza (foto/video/carrusel): selector segmentado. */}
          {publicacion && (
            <div className="flex flex-wrap items-center gap-3">
              <div
                className="inline-flex items-center gap-1 rounded-md border p-0.5"
                role="group"
                aria-label="Formato de la pieza"
              >
                {(
                  [
                    ["foto", "Foto"],
                    ["video", "Video"],
                    ["carrusel", "Carrusel"],
                  ] as const
                ).map(([valor, etiqueta]) => (
                  <Button
                    key={valor}
                    type="button"
                    size="sm"
                    variant={formato === valor ? "secondary" : "ghost"}
                    className="h-7 px-2.5 text-xs"
                    onClick={() => cambiarFormato(valor)}
                    disabled={flipFormato.isPending}
                    aria-pressed={formato === valor}
                  >
                    {etiqueta}
                  </Button>
                ))}
              </div>
              {/* ESPEJO entre redes: con él puesto, lo editado aquí se aplica también a las
                  demás redes de la idea (las ya publicadas no se tocan). Apágalo para que
                  cada red lleve su propio copy/foto. */}
              <div className="ml-auto flex items-center gap-2">
                <Switch
                  id="editar-espejo-toggle"
                  checked={espejo}
                  onCheckedChange={(v) => {
                    setEspejo(v);
                    cambiarEspejo.mutate(v);
                  }}
                  disabled={cambiarEspejo.isPending}
                />
                <Label
                  htmlFor="editar-espejo-toggle"
                  title="Aplica cambios a todas las redes de la idea"
                >
                  Espejo entre redes
                </Label>
              </div>
            </div>
          )}

          {publicacion && formato === "video" ? (
            // Pieza de VIDEO: editor de clip (Ola F) + puente al Estudio de video.
            <div className="space-y-2">
              <EditorVideo
                video={videoKey}
                videoUrl={videoUrl}
                onCambio={(clave, url) => guardarVideo.mutate({ clave, url })}
                disabled={guardarVideo.isPending}
                idPrefijo="editar"
                red={publicacion.red}
              />
              {/* Puente: abre el Estudio de video con esta pieza (find-or-create por contenido).
                  Allí se hace el "toque RRSS" (reencuadre, overlay, subtítulos) y el render server. */}
              <button
                type="button"
                onClick={() =>
                  navigate(
                    `/contenido/video?contenido=${encodeURIComponent(publicacion.contenido_id)}`,
                  )
                }
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent/60"
              >
                <Clapperboard className="h-4 w-4" />
                Estudio de video
              </button>
            </div>
          ) : publicacion?.marca ? (
              // SISTEMA ÚNICO: la plantilla del estudio se renderiza EN VIVO en el lienzo (con tu
              // foto + reencuadre + titular in-place). El selector (galería por marca) y "solo foto"
              // son nativos en la cabecera del editor.
              <EditorPlacaInline
                marca={publicacion.marca}
                publicacionId={publicacion.id}
                documento={documentoSel}
                copyIn={copyIn}
                onCopyInCambio={setCopyIn}
                copy={contenido}
                fotos={fotos}
                onFotosCambio={setFotos}
                imagenFuente={publicacion.imagen_fuente}
                sinPlantilla={placaOculta}
                onAlternarSinPlantilla={() => setPlacaOculta((v) => !v)}
                onAbrirGaleria={() => setGaleriaPlantillas(true)}
              />
            ) : publicacion ? (
              // Pieza sin marca: foto cruda (sin placa) con el editor de imagen clásico.
              <EditorImagen
                imagen={imagen}
                imagenUrl={imagenUrl}
                onCambio={(nombre, url) => {
                  setImagen(nombre);
                  setImagenUrl(url);
                }}
                idPrefijo="editar"
                publicacionId={publicacion.id}
                red={publicacion.red}
                copy={contenido}
              />
            ) : null}

          {/* CARRUSEL: los slides extra EN CRUDO detrás de la portada (la portada se edita
              arriba con la placa de siempre). Subir/quitar/reordenar y "Hacer portada"
              (intercambia la foto de la placa con ese slide); autoguardado normal. */}
          {publicacion && formato === "carrusel" && (
            <EditorCarrusel
              slides={slides}
              onCambio={setSlides}
              idPrefijo="editar"
              onPortada={(i) => {
                // SWAP portada <-> slide: la imagen del slide pasa al hueco 0 de la placa
                // (sin reencuadre: se reencuadra en el editor de arriba) y la foto que era
                // portada baja a ocupar ese mismo slot del carrusel (no se pierde nada).
                const slide = slides[i];
                if (!slide || slide.tipo !== "imagen") return;
                const fotoActual = fotos[0]?.objeto ?? "";
                const nuevasFotos = [...fotos];
                nuevasFotos[0] = { objeto: slide.objeto, foco: null, zoom: 0 };
                setFotos(nuevasFotos);
                const nuevos = [...slides];
                if (fotoActual) {
                  nuevos[i] = { tipo: "imagen", objeto: fotoActual };
                } else {
                  nuevos.splice(i, 1);
                }
                setSlides(nuevos);
              }}
            />
          )}

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="editar-contenido">Contenido</Label>
              <ContadorCaracteres caracteres={contenido.length} limite={limite} />
            </div>
            <AutoTextarea
              id="editar-contenido"
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              readOnly={publicada}
              maxHeight={420}
              className="min-h-[10rem] font-mono text-sm"
            />
          </div>

          {publicacion && (
            <HerramientasHashtags
              contenido={contenido}
              onContenido={setContenido}
              marca={publicacion.marca}
              onGestionar={() => setGestionHashtags(true)}
            />
          )}
        </div>

        {/* Sin footer: los cambios se guardan solos. Para salir: la "X" o clic fuera (ambos
            fuerzan un último guardado vía `cerrar`). */}

        <GestionHashtags
          abierto={gestionHashtags}
          onCerrar={() => setGestionHashtags(false)}
          marcas={marcas}
        />

        {/* Selector de plantilla del estudio (miniaturas) por MARCA. Al elegir, la previa se
            actualiza EN VIVO en el lienzo (sin round-trip); se hornea al guardar. */}
        {galeriaPlantillas && (
          <GaleriaPlantillas
            plantillas={plantillas}
            onCargar={(p) => elegirPlantilla(p.id)}
            onCerrar={() => setGaleriaPlantillas(false)}
            tipoFijo={tipoPlantilla}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

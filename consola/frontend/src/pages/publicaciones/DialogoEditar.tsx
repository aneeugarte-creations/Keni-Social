import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { HerramientasHashtags } from "@/components/hashtags/HerramientasHashtags";
import { EditorImagen } from "@/components/media/EditorImagen";
import { EditorPlacaInline } from "@/components/media/EditorPlacaInline";
import { EditorVideo } from "@/components/media/EditorVideo";
import type { Documento } from "@/editor/documento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { AutoTextarea } from "@/components/ui/auto-textarea";
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
  // Ola F: formato de la pieza ("foto"|"video") + estado del video.
  const [formato, setFormato] = React.useState("foto");
  const [videoKey, setVideoKey] = React.useState("");
  const [videoUrl, setVideoUrl] = React.useState("");
  // --- Autoguardado --- //
  // La pieza se guarda SOLA al editar (debounced); no hay botón ni indicador de guardado.
  const cargandoRef = React.useRef(true); // true mientras se cargan los valores al abrir (no autoguarda)
  const guardandoRef = React.useRef(false); // hay un guardado en vuelo
  const pendienteRef = React.useRef(false); // hubo cambios durante el guardado en vuelo
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

  // Ola F: flip de formato (foto↔video). PATCH /api/contenido/{contenido_id} con {formato}.
  // El backend ajusta las redes (3↔5) y puede devolver un `aviso` si había redes con contenido.
  const flipFormato = useMutation({
    mutationFn: (nuevoFormato: string) => {
      if (!publicacion) throw new Error("Sin publicación");
      return api.actualizarContenido(publicacion.contenido_id, { formato: nuevoFormato });
    },
    onSuccess: (data) => {
      const nuevoFmt = data.contenido.formato || "foto";
      setFormato(nuevoFmt);
      if (data.aviso) toast(data.aviso);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Cambia el formato (foto↔video) PIDIENDO CONFIRMACIÓN: el cambio es SIEMPRE destructivo —el
  // backend borra el asset del formato anterior (la foto al pasar a vídeo, el vídeo al pasar a
  // foto), quita la plantilla (foto→miniatura y viceversa) y devuelve la pieza a borrador (pierde
  // el «listo para revisar»)—. Confirmamos siempre porque el asset a perder puede estar en otras
  // redes de la pieza (no solo en la que se edita aquí), así que no se puede detectar de forma
  // fiable desde una sola fila.
  const cambiarFormato = (aVideo: boolean) => {
    if (!publicacion) return;
    const que = aVideo ? "la foto" : "el video";
    const ok = window.confirm(
      `Al cambiar a ${aVideo ? "video" : "foto"} se borrará ${que} y la plantilla actual, y la ` +
        `pieza volverá a borrador (perderá el «listo para revisar»). ¿Continuar?`,
    );
    if (!ok) return;
    flipFormato.mutate(aVideo ? "video" : "foto");
  };

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
    // Ola F: formato y video.
    setFormato(publicacion.formato || "foto");
    setVideoKey(publicacion.video ?? "");
    setVideoUrl("");
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

  // Persiste la pieza. NO cierra el diálogo: lo comparten el autoguardado y el cierre.
  const persistir = React.useCallback(async () => {
    if (!publicacion) return;
    // RENDER ON-DEMAND: las piezas de MARCA ya no hornean un PNG al guardar. Persistimos su
    // RECETA (foto + copy_in + placa_oculta + plantilla + encuadre) y dejamos `imagen` vacío; la
    // imagen publicable se renderiza on-demand en el servidor (/api/publicaciones/{id}/compuesta).
    // Así no se duplica un PNG por cada edición de texto. Las piezas SIN marca conservan su
    // `imagen` (imagen subida/generada, sin receta de placa).
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
    // El estado, la fecha y evergreen NO se tocan aquí: el flujo los gestiona solo (autogen → QA →
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
  }, [publicacion, fotos, copyIn, placaOculta, plantillaId, imagen, contenido, documentoSel]);

  // Solo se autoguarda cuando hay contenido (el copy del post). Sin título: ya no lo exige.
  const datosValidos = !!publicacion && contenido.trim().length > 0;

  // Autoguardado: persiste sin cerrar; coalesciona los cambios ocurridos durante un guardado en vuelo.
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
        </DialogHeader>

        {/* Orden de edición: primero la IMAGEN/VIDEO, luego el CONTENIDO (copy) y al final los HASHTAGS. */}
        <div className="space-y-4">
          {/* Ola F: toggle Foto/Video. Solo disponible cuando la pieza tiene contenido_id (no vacío). */}
          {publicacion && (
            <div className="flex items-center gap-3">
              <Label htmlFor="editar-formato-toggle">Foto</Label>
              <Switch
                id="editar-formato-toggle"
                checked={formato === "video"}
                onCheckedChange={(v) => cambiarFormato(v)}
                disabled={flipFormato.isPending}
              />
              <Label htmlFor="editar-formato-toggle">Video</Label>
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
                Editar en Estudio de video
              </button>
            </div>
          ) : publicacion?.marca ? (
              // SISTEMA ÚNICO: la plantilla del estudio se renderiza EN VIVO en el lienzo (con tu
              // foto + reencuadre + titular in-place). El selector (galería por marca) y "solo foto"
              // son nativos en la cabecera del editor.
              <EditorPlacaInline
                marca={publicacion.marca}
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
                copyIn={copyIn}
              />
            ) : null}

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="editar-contenido">Contenido</Label>
              <ContadorCaracteres caracteres={contenido.length} limite={limite} />
            </div>
            <AutoTextarea
              id="editar-contenido"
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
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

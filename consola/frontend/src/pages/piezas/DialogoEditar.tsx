import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard, Loader2, Sparkles } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { BadgeResponsable } from "@/components/comunes/BadgeResponsable";
import { confirmar, elegir } from "@/components/comunes/confirmar";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { SugerenciaHashtags } from "@/components/hashtags/SugerenciaHashtags";
import { agregarHashtags } from "./hashtags";
import { EditorCarrusel } from "@/components/media/EditorCarrusel";
import { EditorCarruselLateral } from "@/components/media/EditorCarruselLateral";
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
import { useGeneracion } from "@/hooks/use-generacion";
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
import {
  type DatosStock,
  mensajeBloqueoStock,
  stockNoAutorizado,
} from "@/lib/stock";
import type { CuerpoActualizarPieza, PlataformaStock, Pieza } from "@/types";

import { CLAVE_PIEZAS } from "./claves";
import { etiquetaCategoriaPieza } from "./categoria";
import { metaRed } from "./meta";
import { etapaDePieza } from "@/pages/feed/etapa";

/** Diálogo de edición de una publicación, MÍNIMO: solo contenido (copy) + hashtags + imagen. Los
 *  posts no llevan título; el formato es texto plano (sin barra de formato ni UTM). Comentarios y
 *  versiones viven en el feed, no aquí. El estado/programación/aprobación los gestiona el flujo. */
function DialogoEditarInterno({
  pieza,
  onCerrar,
  irAVariante,
}: {
  pieza: Pieza | null;
  onCerrar: () => void;
  /** Salta a la pieza HERMANA de la otra variante (foto/carrusel) si existe; devuelve si saltó. */
  irAVariante: (variante: "foto" | "carrusel") => boolean;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // Catálogo de opciones (query cacheada del feed): da las `lineas` para nombrar la categoría de
  // la pieza, cuyo `categoria` suele ser el ID de la vertical (un hash), no un slug legible.
  const opcionesQuery = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: pieza !== null,
  });
  const nombreCategoria = pieza
    ? etiquetaCategoriaPieza(pieza.categoria, opcionesQuery.data?.lineas)
    : "";
  const [contenido, setPublicacion] = React.useState("");
  // Texto que va DENTRO de la imagen (copy-in), distinto del contenido que la acompaña.
  const [copyIn, setCopyIn] = React.useState("");
  // Imagen: nombre del archivo + url para previsualizar.
  const [imagen, setImagen] = React.useState("");
  const [imagenUrl, setImagenUrl] = React.useState("");
  // Origen PROPIO declarado al REEMPLAZAR la imagen en esta sesión (galeria/subida/ia): se manda al
  // guardar para que el back LIMPIE el metadato de licencia heredado (p. ej. de una foto de stock).
  // "" = sin reemplazo en esta sesión (no se envía: una COMPOSICIÓN conserva su crédito).
  const [imagenOrigen, setImagenOrigen] = React.useState("");
  // Estado de imagen de STOCK (origen/proveedor/autorización): condiciona el tratamiento
  // "SIN LICENCIA" y el bloqueo de publicar mientras no esté autorizada.
  const [stock, setStock] = React.useState<DatosStock>({});
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
  // CARRUSEL: slides EXTRA detrás de la portada (la portada es la placa de arriba).
  const [slides, setSlides] = React.useState<SlideCarrusel[]>([]);
  // --- Autoguardado --- //
  // La pieza se guarda SOLA al editar (debounced); no hay botón ni indicador de guardado.
  const cargandoRef = React.useRef(true); // true mientras se cargan los valores al abrir (no autoguarda)
  const guardandoRef = React.useRef(false); // hay un guardado en curso
  const pendienteRef = React.useRef(false); // hubo cambios durante el guardado en curso

  // Plantillas del estudio por MARCA: como todo es 4:5 y se postea lo mismo a todas las redes, la
  // plantilla la dicta la marca (no la red). Distintas plantillas cubren los tipos de post
  // (breaking, infografía con logo, cita textual, logo del mundial, sin nada…). Se cargan siempre
  // (con marca) porque el editor renderiza la plantilla EN VIVO y necesita su documento.
  const plantillasQuery = useQuery({
    queryKey: ["plantillas-diseno", pieza?.marca],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: pieza?.marca }, signal),
    enabled: !!pieza?.marca,
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

  // Generación de CARRUSEL desde el copy: al pasar un post a carrusel sin slides (o al pulsar
  // «Generar carrusel»), se ENCOLA un `claude -p` que parte el copy en titulares y los hornea como
  // placas de la marca; el worker los escribe en las piezas gemelas. Lo seguimos con el mismo hook
  // de sondeo (SSE+fallback) que el resto de trabajos de IA y recargamos la pieza al terminar.
  const genCarrusel = useGeneracion();
  const {
    generacion: genCarruselReg,
    ejecutando: generandoCarrusel,
    cancelando: cancelandoCarrusel,
    iniciar: iniciarGenCarrusel,
    limpiar: limpiarGenCarrusel,
    cancelar: cancelarGenCarrusel,
  } = genCarrusel;
  // El autoguardado NO debe escribir un `carrusel` vacío mientras el worker lo está rellenando
  // (pisaría los slides que hornea). `persistir` lee este ref para omitir los slides durante la gen.
  const generandoCarruselRef = React.useRef(false);
  generandoCarruselRef.current = generandoCarrusel;
  // Longitud elegida en el diálogo «Cambiar a carrusel»: el flip la consume al completar para
  // GENERAR ya con ella (corto/largo). null = el flip no debe auto-generar (otro formato, o slides
  // ya presentes).
  const longitudPendienteRef = React.useRef<"corto" | "largo" | null>(null);

  const lanzarCarrusel = React.useCallback(
    async (longitud: "corto" | "largo") => {
      if (!pieza) return;
      try {
        const r = await api.generarCarrusel(pieza.id, longitud);
        iniciarGenCarrusel(r.generacion);
      } catch (e) {
        toast.error(mensajeError(e));
      }
    },
    [pieza, iniciarGenCarrusel],
  );

  // Conversión NO DESTRUCTIVA a carrusel: crea una VARIANTE hermana (no toca la foto). Reusa el
  // mismo polling que `lanzarCarrusel`; `conversionVarianteRef` marca la gen para que el efecto de
  // completado tome la rama "no recargues esta pieza, refresca el feed" (los slides están en la
  // pieza carrusel NUEVA, no en esta —que sigue siendo foto—).
  const conversionVarianteRef = React.useRef(false);
  const convertirAVarianteCarrusel = React.useCallback(
    async (longitud: "corto" | "largo") => {
      if (!pieza) return;
      try {
        const r = await api.convertirCarrusel(pieza.id, longitud);
        conversionVarianteRef.current = true;
        iniciarGenCarrusel(r.generacion);
      } catch (e) {
        toast.error(mensajeError(e));
      }
    },
    [pieza, iniciarGenCarrusel],
  );

  // Botón de la barra (post YA en carrusel): pregunta la longitud en el MISMO diálogo y (re)genera.
  // `regenerar` solo cambia el texto (ya hay slides que se reemplazan).
  const pedirLongitudYGenerar = React.useCallback(
    async (regenerar: boolean) => {
      const longitud = (await elegir({
        titulo: regenerar ? "Regenerar carrusel" : "Generar carrusel",
        mensaje: regenerar
          ? "Se reemplazan los slides actuales por unos nuevos a partir del copy. Elige la longitud:"
          : "Se generará el carrusel a partir del copy del post. Elige la longitud:",
        opciones: [
          { valor: "corto", etiqueta: "Corto", descripcion: "4–5 tarjetas" },
          { valor: "largo", etiqueta: "Largo", descripcion: "8–9 tarjetas" },
        ],
      })) as "corto" | "largo" | null;
      if (longitud) void lanzarCarrusel(longitud);
    },
    [lanzarCarrusel],
  );

  // Al terminar la generación: recarga la pieza para traer los slides que horneó el worker (su
  // fuente de verdad es la BD, no el `resultado` del registro). Procesa cada generación UNA vez.
  const idGenCarrusel = genCarruselReg?.id;
  const estadoGenCarrusel = genCarruselReg?.estado;
  const procesadoGenRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!pieza || !idGenCarrusel) return;
    if (estadoGenCarrusel !== "completado" && estadoGenCarrusel !== "error") return;
    if (procesadoGenRef.current === idGenCarrusel) return;
    procesadoGenRef.current = idGenCarrusel;
    if (estadoGenCarrusel === "error") {
      toast.error("No se pudo generar el carrusel.");
      conversionVarianteRef.current = false;
      limpiarGenCarrusel();
      return;
    }
    // Conversión a VARIANTE: los slides están en la pieza carrusel NUEVA, no en esta (sigue foto).
    // No recargamos esta pieza; refrescamos el feed para que aparezca la tarjeta carrusel hermana.
    if (conversionVarianteRef.current) {
      conversionVarianteRef.current = false;
      toast("Variante carrusel creada: revísala en el feed, junto a la foto.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      limpiarGenCarrusel();
      return;
    }
    void api
      .pieza(pieza.id)
      .then((r) => {
        const nuevos = parsearCarrusel(r.pieza.carrusel);
        setSlides(nuevos);
        setFormato(r.pieza.formato || "carrusel");
        if (nuevos.length === 0) {
          toast("La IA no vio material para un carrusel; añade los slides a mano.");
        }
      })
      .catch(() => {
        // La recarga falló: avisa y deja que el refetch de la lista traiga los slides horneados.
        toast.error("No se pudieron recargar los slides; refrescando la lista.");
        void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      })
      .finally(() => limpiarGenCarrusel());
    void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
  }, [idGenCarrusel, estadoGenCarrusel, pieza, queryClient, limpiarGenCarrusel]);

  // Flip de formato (foto/video/carrusel). PATCH /api/publicaciones/{publicacion_id} con {formato}.
  // El backend ajusta las redes (3/5/2) y puede devolver un `aviso` si había redes con contenido.
  const flipFormato = useMutation({
    mutationFn: (nuevoFormato: string) => {
      if (!pieza) throw new Error("Sin publicación");
      return api.actualizarPublicacion(pieza.publicacion_id, { formato: nuevoFormato });
    },
    onSuccess: (data) => {
      const nuevoFmt = data.contenido.formato || "foto";
      setFormato(nuevoFmt);
      // Al salir de carrusel el backend limpia sus slides: el estado local los suelta también
      // (si no, el autoguardado los re-escribiría).
      if (nuevoFmt !== "carrusel") setSlides([]);
      if (data.aviso) toast(data.aviso);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      // Si el flip a carrusel vino del diálogo de «Cambiar a carrusel» (donde se eligió la
      // longitud), genera ya con ella. La barra del editor sirve además para regenerar después.
      const longitud = longitudPendienteRef.current;
      longitudPendienteRef.current = null;
      if (nuevoFmt === "carrusel" && longitud) void lanzarCarrusel(longitud);
    },
    onError: (e) => {
      longitudPendienteRef.current = null;
      toast.error(mensajeError(e));
    },
  });

  // Cambia el formato PIDIENDO CONFIRMACIÓN: el cambio puede ser destructivo —el backend borra
  // el asset del formato anterior (la parte visual al pasar a vídeo, el vídeo al pasar a un
  // formato de imagen, los slides al salir de carrusel), quita la plantilla y devuelve la pieza
  // a borrador (pierde el «listo para revisar»)—. Confirmamos siempre porque el asset a perder
  // puede estar en otras redes de la pieza (no solo en la que se edita aquí), así que no se
  // puede detectar de forma fiable desde una sola fila.
  const cambiarFormato = async (nuevo: string) => {
    if (!pieza || nuevo === formato) return;
    // VARIANTES foto<->carrusel: son piezas HERMANAS que conviven. Si la variante destino YA
    // existe, SALTAMOS a ella (la mostramos) en vez de regenerar/flipear: «verla», no rehacerla.
    if (
      (nuevo === "foto" || nuevo === "carrusel") &&
      (formato === "foto" || formato === "carrusel") &&
      irAVariante(nuevo)
    ) {
      return;
    }
    // No existe la variante FOTO hermana (raro: el carrusel nace de una foto): no flipeamos de
    // forma destructiva sin querer; avisamos y dejamos abrirla desde el feed.
    if (nuevo === "foto" && formato === "carrusel") {
      toast("No encuentro la versión foto de esta red; ábrela desde el feed.");
      return;
    }
    // Pasar a CARRUSEL sin slides: el mismo diálogo confirma el cambio Y pregunta la longitud
    // (corto 4-5 / largo 8-9). Al elegir, flipea y genera ya con ella; Cancelar no hace nada.
    if (nuevo === "carrusel" && slides.length === 0) {
      // NO DESTRUCTIVO: crea una VARIANTE carrusel junto a la foto (no la pisa ni la manda a
      // borrador). El feed muestra ambas como tarjetas hermanas y el equipo elige cuál publica.
      const longitud = (await elegir({
        titulo: "Crear carrusel",
        mensaje:
          "Se creará una VARIANTE carrusel a partir del copy del post, junto a la foto (la foto se " +
          "conserva intacta; el feed mostrará ambas y eliges cuál publicar). Elige la longitud:",
        opciones: [
          { valor: "corto", etiqueta: "Corto", descripcion: "4–5 tarjetas" },
          { valor: "largo", etiqueta: "Largo", descripcion: "8–9 tarjetas" },
        ],
      })) as "corto" | "largo" | null;
      if (!longitud) return;
      void convertirAVarianteCarrusel(longitud);
      return;
    }
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
      if (!pieza) throw new Error("Sin publicación");
      return api.actualizarPieza(pieza.id, { espejo: v });
    },
    onSuccess: (data) => {
      setEspejo(data.pieza.espejo ?? true);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
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
      if (!pieza) throw new Error("Sin publicación");
      return api.actualizarPlataforma(pieza.publicacion_id, pieza.id, { video: clave });
    },
    onSuccess: (_data, { clave, url }) => {
      setVideoKey(clave);
      setVideoUrl(url);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Cargamos los valores cada vez que se abre con una publicación nueva.
  React.useEffect(() => {
    if (!pieza) return;
    cargandoRef.current = true; // no autoguardar por los cambios de estado que provoca esta carga
    setPublicacion(pieza.contenido);
    setCopyIn(pieza.copy_in ?? "");
    setImagen(pieza.imagen ?? "");
    setImagenUrl(pieza.imagen_url ?? "");
    // Sin reemplazo aún: no declaramos origen al cargar (la pieza conserva su metadato de licencia).
    setImagenOrigen("");
    setStock({
      imagen_origen: pieza.imagen_origen,
      imagen_proveedor: pieza.imagen_proveedor,
      imagen_autor: pieza.imagen_autor,
      imagen_licencia: pieza.imagen_licencia,
      imagen_credito_url: pieza.imagen_credito_url,
      imagen_autorizada: pieza.imagen_autorizada,
    });
    setPlacaOculta(pieza.placa_oculta ?? false);
    setPlantillaId(pieza.plantilla_diseno_id ?? "");
    setEspejo(pieza.espejo ?? true);
    // Formato, video y slides del carrusel.
    setFormato(pieza.formato || "foto");
    setVideoKey(pieza.video ?? "");
    setVideoUrl("");
    setSlides(parsearCarrusel(pieza.carrusel));
    // Carga del collage: si la pieza trae `fotos` (JSON), úsalo; si no, deriva el hueco único del
    // par legado `foto`/`foto_encuadre`.
    const fotosGuardadas = parsearFotos(pieza.fotos);
    if (fotosGuardadas.length) {
      // RECONCILIA el hueco 0 con el `foto` legado: un collage cuyo hueco 0 llegó VACÍO no debe
      // tapar una foto legada real. Si lo hiciera, el autoguardado (que deriva `foto` del hueco 0)
      // borraría la portada y el espejo propagaría el vacío a las redes hermanas.
      if (!fotosGuardadas[0].objeto && (pieza.foto ?? "")) {
        const enc = parsearEncuadre(pieza.foto_encuadre);
        fotosGuardadas[0] = { objeto: pieza.foto ?? "", foco: enc?.foco ?? null, zoom: enc?.zoom ?? 0 };
      }
      setFotos(fotosGuardadas);
    } else {
      const enc = parsearEncuadre(pieza.foto_encuadre);
      setFotos([{ objeto: pieza.foto ?? "", foco: enc?.foco ?? null, zoom: enc?.zoom ?? 0 }]);
    }
    // Reabrimos el autoguardado tras aplicar la carga (en un tick: así el render que dispara esta
    // carga ve `cargandoRef=true` y no guarda; solo los cambios del usuario posteriores guardan).
    const t = setTimeout(() => {
      cargandoRef.current = false;
    }, 0);
    return () => clearTimeout(t);
  }, [pieza]);

  const limite = pieza ? metaRed(pieza.red).limite : null;
  // Pieza ya `publicado`: SOLO LECTURA. Lo que salió a redes no puede diferir de lo mostrado, así
  // que el back la congela (409). En vez de dejar editar y fallar, el editor abre inerte: no se
  // autoguarda nada y los controles quedan deshabilitados (no hay PATCH que rechazar).
  const publicada = pieza?.estado === "publicado";

  // STOCK SIN LICENCIA: una foto de stock no autorizada bloquea publicar. El auto-envío a revisión
  // se inhibe mientras esté así (defensa en UI; el back también lo bloquea con 409).
  const bloqueoStock = stockNoAutorizado(stock);

  // Foto de stock adjuntada/autorizada: refresca la imagen y su estado de licencia EN VIVO
  // (la preview y el bloqueo responden al instante) y propaga el cambio a los listados.
  const onStockCambio = React.useCallback(
    (plataforma: PlataformaStock) => {
      setImagenUrl(plataforma.imagen_url ?? "");
      setStock({
        imagen_origen: plataforma.imagen_origen,
        imagen_proveedor: plataforma.imagen_proveedor,
        imagen_autor: plataforma.imagen_autor,
        imagen_licencia: plataforma.imagen_licencia,
        imagen_credito_url: plataforma.imagen_credito_url,
        imagen_autorizada: plataforma.imagen_autorizada,
      });
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    },
    [queryClient],
  );

  // Persiste la pieza. NO cierra el diálogo: lo comparten el autoguardado y el cierre.
  const persistir = React.useCallback(async () => {
    if (!pieza) return;
    const imagenFinal = pieza.marca ? "" : imagen;
    // COLLAGE: persistimos `fotos` (una foto por hueco). Por RETROCOMPAT sincronizamos el hueco 0 al
    // par legado `foto`/`foto_encuadre`, que el backend (y consumidores viejos) siguen leyendo.
    const hueco0 = fotos[0];
    const foco0 = hueco0?.foco ?? null;
    const zoom0 = hueco0?.zoom && hueco0.zoom > 0 ? hueco0.zoom : 1;
    // NO se envía `titulo`: los posts no llevan título; PATCH parcial deja intacto lo no enviado.
    const cuerpo: CuerpoActualizarPieza = {
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
    // REEMPLAZO de imagen (galería/IA/subida en el editor sin marca): declara el origen PROPIO para
    // que el back limpie el metadato de licencia heredado. Se OMITE si no hubo reemplazo en la
    // sesión: una COMPOSICIÓN (placa/reframe/render sobre la misma foto) conserva su crédito.
    if (imagenOrigen) cuerpo.imagen_origen = imagenOrigen;
    // CARRUSEL: solo se envían los slides cuando la pieza ES carrusel (en otros formatos el
    // backend ya los limpió en el flip; reenviar el estado local viejo los resucitaría). MIENTRAS
    // se genera el carrusel los OMITIMOS: el worker está rellenando ese campo y un PUT con la lista
    // local (aún vacía) pisaría sus slides.
    if (formato === "carrusel" && !generandoCarruselRef.current) {
      cuerpo.carrusel = serializarCarrusel(slides);
    }
    // El estado, la fecha y evergreen NO se tocan aquí: el flujo los gestiona solo (autogen → verificación →
    // me gusta → auto-programar). PATCH parcial: lo no enviado queda intacto.
    const { pieza: actualizada } = await api.actualizarPieza(pieza.id, cuerpo);
    // AUTO-AVANCE: una pieza autogenerada/editada que YA tiene todo el contenido entra sola a
    // revisión (abre los "me gusta" del equipo). Sustituye al botón manual "Enviar a revisión".
    // GATE COLLAGE: solo auto-avanza si TODOS los huecos del diseño están llenos (no faltan fotos).
    // El hueco 0 cuenta como lleno también si la pieza trae imagen original de RSS (`imagen_fuente`),
    // que es el respaldo que pinta el editor (igual que su contador): sin esto, una pieza de marca
    // cuya única imagen es la original ya no auto-avanzaría al editar el copy.
    const huecosDoc = documentoSel ? capasFotoDoc(documentoSel).length : 1;
    const llenos = fotos.filter((f, i) => f.objeto || (i === 0 && !!pieza.imagen_fuente)).length;
    const fotosCompletas = llenos >= Math.max(1, huecosDoc);
    // STOCK SIN LICENCIA: no auto-avanza (no se puede publicar sin autorizar). `etapaDePieza`
    // ya lo refleja con los datos del back; el flag local cubre el adjuntar recién hecho.
    if (
      fotosCompletas &&
      !bloqueoStock &&
      actualizada.estado === "borrador" &&
      etapaDePieza(actualizada) === "lista_para_revisar"
    ) {
      try {
        await api.enviarARevision(pieza.id);
      } catch {
        /* carrera / ya en revisión: lo ignoramos (el feed reflejará el estado real) */
      }
    }
  }, [pieza, fotos, copyIn, placaOculta, plantillaId, imagen, imagenOrigen, contenido, documentoSel, formato, slides, bloqueoStock]);

  // Solo se autoguarda cuando hay contenido (el copy del post) y la pieza NO está publicada
  // (publicada = inmutable: nada que persistir). Sin título: ya no lo exige.
  const datosValidos = !!pieza && contenido.trim().length > 0 && !publicada;

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
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      // Editar puede RESETEAR las aprobaciones (vuelve a borrador): refresca la cadena para que la
      // tarjeta no siga mostrando los OK viejos.
      if (pieza) {
        void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", pieza.id] });
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
  }, [datosValidos, persistir, queryClient, pieza]);

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
    if (cargandoRef.current || !pieza) return;
    const t = setTimeout(() => void autoguardarRef.current(), 1200);
    return () => clearTimeout(t);
  }, [firmaAutoguardado, pieza]);

  return (
    <Dialog open={pieza !== null} onOpenChange={(o) => !o && cerrar()}>
      {/* En móvil el editor ocupa toda la pantalla (h-dvh, ancho completo, sin
          radios) para que el revisor edite cómodo en el feed; en escritorio
          mantiene el modal centrado de 2xl. */}
      <DialogContent className="max-h-dvh h-dvh max-w-full overflow-y-auto rounded-none sm:h-auto sm:max-h-[90vh] sm:max-w-2xl sm:rounded-lg">
        <DialogHeader>
          <DialogTitle>Editar publicación</DialogTitle>
          {pieza && (
            <DialogDescription>
              {pieza.red_nombre} · {pieza.marca_nombre}
              {nombreCategoria && (
                <span className="ml-1.5 inline-flex items-center gap-1.5 align-middle">
                  <span
                    aria-hidden
                    className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60"
                  />
                  <span className="text-xs text-foreground/70">{nombreCategoria}</span>
                </span>
              )}
            </DialogDescription>
          )}
          {/* «La lista» (todas las marcas): quién lleva la pieza, SOLO LECTURA. Aquí avisa a quien
              edita que la pieza ya está cogida por otra persona (antes era invisible en el editor). */}
          {pieza && (
            <BadgeResponsable
              responsableId={pieza.responsable_id}
              responsableNombre={pieza.responsable_nombre}
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
          {/* Stock SIN LICENCIA: aviso del bloqueo de publicar (vale para todo formato; el control
              para autorizar vive junto a la imagen en el editor sin marca). */}
          {bloqueoStock && !publicada && (
            <Aviso className="self-start">
              {mensajeBloqueoStock({
                licencia: stock.imagen_licencia,
                proveedor: stock.imagen_proveedor,
              })}
            </Aviso>
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
          {pieza && (
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
                    disabled={flipFormato.isPending || generandoCarrusel}
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

          {pieza && formato === "video" ? (
            // Pieza de VIDEO: editor de clip (Ola F) + puente al Estudio de video.
            <div className="space-y-2">
              <EditorVideo
                video={videoKey}
                videoUrl={videoUrl}
                onCambio={(clave, url) => guardarVideo.mutate({ clave, url })}
                disabled={guardarVideo.isPending}
                idPrefijo="editar"
                red={pieza.red}
              />
              {/* Puente: abre el Estudio de video con esta pieza (find-or-create por contenido).
                  Allí se hace el "toque RRSS" (reencuadre, overlay, subtítulos) y el render server. */}
              <button
                type="button"
                onClick={() =>
                  navigate(
                    `/publicaciones/video?contenido=${encodeURIComponent(pieza.publicacion_id)}`,
                  )
                }
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent/60"
              >
                <Clapperboard className="h-4 w-4" />
                Estudio de video
              </button>
            </div>
          ) : pieza?.marca && formato === "carrusel" ? (
              // CARRUSEL: el MISMO editor de placa pero PAGINADO de lado (portada + slides), como
              // el slideshow del feed pero editable. Cada slide edita foto/titular/plantilla. Arriba,
              // la barra de generación desde el copy (crear/regenerar los slides con IA).
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-sm">
                  {generandoCarrusel ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      <span className="text-muted-foreground">Creando el carrusel desde el copy…</span>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7 px-2.5 text-xs"
                        onClick={() => void cancelarGenCarrusel()}
                        disabled={cancelandoCarrusel}
                      >
                        Cancelar
                      </Button>
                    </>
                  ) : slides.length === 0 ? (
                    <>
                      <Sparkles className="h-4 w-4 text-muted-foreground" />
                      <span className="text-muted-foreground">
                        Aún no hay slides. Genera el carrusel a partir del copy del post.
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="ml-auto h-7 px-2.5 text-xs"
                        onClick={() => void pedirLongitudYGenerar(false)}
                      >
                        Generar carrusel
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="text-muted-foreground">
                        Carrusel generado. Edita cada slide o vuelve a generarlo.
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7 px-2.5 text-xs"
                        onClick={() => void pedirLongitudYGenerar(true)}
                      >
                        Regenerar
                      </Button>
                    </>
                  )}
                </div>
                <EditorCarruselLateral
                  marca={pieza.marca}
                  piezaId={pieza.id}
                  plantillas={plantillas}
                  copy={contenido}
                  titulo={pieza.titulo}
                  imagenClave={pieza.imagen_clave}
                  imagenFuente={pieza.imagen_fuente}
                  portadaFotos={fotos}
                  onPortadaFotos={setFotos}
                  portadaCopyIn={copyIn}
                  onPortadaCopyIn={setCopyIn}
                  portadaPlantillaId={plantillaId}
                  onPortadaPlantillaId={(id) => {
                    setPlantillaId(id);
                    setPlacaOculta(false);
                  }}
                  portadaPlacaOculta={placaOculta}
                  onPortadaPlacaOculta={setPlacaOculta}
                  slides={slides}
                  onSlides={setSlides}
                  // Antes de descargar, fuerza el guardado: la portada se sirve del estado guardado
                  // (`/compuesta`), así el archivo refleja la última edición y no la previa al autosave.
                  onGuardarPortada={persistir}
                />
              </div>
            ) : pieza?.marca ? (
              // SISTEMA ÚNICO: la plantilla del estudio se renderiza EN VIVO en el lienzo (con tu
              // foto + reencuadre + titular in-place). El selector (galería por marca) y "solo foto"
              // son nativos en la cabecera del editor.
              <EditorPlacaInline
                marca={pieza.marca}
                piezaId={pieza.id}
                documento={documentoSel}
                copyIn={copyIn}
                onCopyInCambio={setCopyIn}
                copy={contenido}
                titulo={pieza.titulo}
                imagenClave={pieza.imagen_clave}
                fotos={fotos}
                onFotosCambio={setFotos}
                // REEMPLAZO del FONDO (hueco 0) por una propia (subir/galería/IA): declara el origen
                // para mandarlo al guardar y limpiar el metadato de licencia heredado. El buscador de
                // stock/agencias y editar solo texto/diseño NO lo declaran (preservan la metadata).
                onOrigenPropio={setImagenOrigen}
                imagenFuente={pieza.imagen_fuente}
                sinPlantilla={placaOculta}
                onAlternarSinPlantilla={() => setPlacaOculta((v) => !v)}
                onAbrirGaleria={() => setGaleriaPlantillas(true)}
                stock={stock}
                onStockCambio={onStockCambio}
              />
            ) : pieza ? (
              // Pieza sin marca: foto cruda (sin placa) con el editor de imagen clásico.
              <EditorImagen
                imagen={imagen}
                imagenUrl={imagenUrl}
                onCambio={(nombre, url, origen) => {
                  setImagen(nombre);
                  setImagenUrl(url);
                  // REEMPLAZO (galería/IA/subida): recuerda el origen propio para declararlo al
                  // guardar (limpia el metadato de licencia heredado). Quitar la imagen no trae
                  // origen y deja intacto el último declarado.
                  if (origen) setImagenOrigen(origen);
                }}
                idPrefijo="editar"
                piezaId={pieza.id}
                marca={pieza.marca}
                red={pieza.red}
                copy={contenido}
                titulo={pieza.titulo}
                imagenClave={pieza.imagen_clave}
                imagenFuente={pieza.imagen_fuente}
                stock={stock}
                onStockCambio={onStockCambio}
              />
            ) : null}

          {/* CARRUSEL SIN MARCA: sin placa que editar, los slides extra van EN CRUDO detrás de la
              portada (lista de subir/quitar/reordenar). Las piezas CON marca usan el carrusel
              lateral editable de arriba. */}
          {pieza && formato === "carrusel" && !pieza.marca && (
            <EditorCarrusel slides={slides} onCambio={setSlides} idPrefijo="editar" />
          )}

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="editar-contenido">Publicacion</Label>
              <ContadorCaracteres caracteres={contenido.length} limite={limite} />
            </div>
            <AutoTextarea
              id="editar-contenido"
              value={contenido}
              onChange={(e) => setPublicacion(e.target.value)}
              readOnly={publicada}
              maxHeight={420}
              className="min-h-[10rem] font-mono text-sm"
            />
          </div>

          {pieza && (
            <SugerenciaHashtags
              contenido={contenido}
              pieza={pieza}
              onAceptar={(tags) => setPublicacion(agregarHashtags(contenido, tags))}
            />
          )}
        </div>

        {/* Sin footer: los cambios se guardan solos. Para salir: la "X" o clic fuera (ambos
            fuerzan un último guardado vía `cerrar`). */}

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

/** Pieza HERMANA de la otra variante (misma idea + misma red) buscada en la caché del feed/lista
 *  (CLAVE_PIEZAS), sin pedir red: el editor se abre desde superficies que ya la tienen cargada. */
function buscarHermana(
  queryClient: ReturnType<typeof useQueryClient>,
  base: Pieza,
  variante: "foto" | "carrusel",
): Pieza | null {
  let hallada: Pieza | null = null;
  const escanear = (lista: unknown) => {
    if (hallada || !Array.isArray(lista)) return;
    for (const p of lista as Pieza[]) {
      if (
        p &&
        p.id !== base.id &&
        (p.publicacion_id || "") === (base.publicacion_id || "") &&
        p.red === base.red &&
        (p.variante === "carrusel" ? "carrusel" : "foto") === variante
      ) {
        hallada = p;
        return;
      }
    }
  };
  for (const [, datos] of queryClient.getQueriesData({ queryKey: CLAVE_PIEZAS })) {
    if (!datos || typeof datos !== "object") continue;
    const d = datos as { piezas?: unknown; pages?: unknown[] };
    escanear(d.piezas);
    if (Array.isArray(d.pages)) {
      for (const pg of d.pages) {
        if (pg && typeof pg === "object") escanear((pg as { piezas?: unknown }).piezas);
      }
    }
    if (hallada) break;
  }
  return hallada;
}

/**
 * Editor de pieza. Envuelve al editor real para poder SALTAR entre variantes hermanas (foto ↔
 * carrusel de la misma red) sin cerrar: el selector de formato, si la variante destino ya existe,
 * cambia la pieza activa en vez de regenerarla. Al cambiar el `key` el editor interno se remonta
 * y recarga limpio la pieza nueva (su efecto de desmontaje guarda la anterior).
 */
export function DialogoEditar({
  pieza,
  onCerrar,
}: {
  pieza: Pieza | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [activa, setActiva] = React.useState<Pieza | null>(pieza);
  // Abrir con una pieza distinta (cambia el prop) reinicia la pieza activa.
  React.useEffect(() => setActiva(pieza), [pieza]);
  const irAVariante = React.useCallback(
    (variante: "foto" | "carrusel") => {
      if (!activa) return false;
      const hermana = buscarHermana(queryClient, activa, variante);
      if (hermana) {
        setActiva(hermana);
        return true;
      }
      return false;
    },
    [activa, queryClient],
  );
  return (
    <DialogoEditarInterno
      key={activa?.id ?? "vacio"}
      pieza={activa}
      onCerrar={onCerrar}
      irAVariante={irAVariante}
    />
  );
}

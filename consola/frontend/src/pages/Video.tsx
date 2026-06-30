/**
 * Estudio de Video — editor del "toque RRSS" sobre video YA editado (la edición cruda es
 * Premiere). Produce/edita el `documento` de COMPOSICIÓN del contrato (G-video-engine.md) y lo
 * manda a renderizar server-side con FFmpeg.
 *
 * Secciones (sub-navegación dentro de la página):
 *   - Base    : formato/aspecto + clip base + reencuadre (cover/contain, foco).
 *   - Overlay : editor de capas reutilizado (logos/marcos/image-in-video/textos).
 *   - PiP     : segundo video posicionado como Picture-in-Picture.
 *   - Subtítulos : transcribir (ASR) + corrección humana es-MX + marcar listo.
 *   - Render  : encola el render y muestra el mp4 resultante.
 *
 * Honestidad: el preview del navegador es APROXIMADO; el render fiel lo produce el servidor.
 * Nada se quema/publica sin criterio humano. La composición se persiste como BORRADOR en el
 * backend al PRIMER cambio significativo (o con el botón "Guardar borrador"), sin esperar al clip
 * base, y luego se autoguarda. El estado "listo" es organización, NO publicación.
 */
import { useMutation } from "@tanstack/react-query";
import { Captions, Check, CheckCircle2, Film, FolderOpen, Layers, Music, PictureInPicture2, Save, Undo2, Video as VideoIcon } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { AccionesPaginaFin, TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { EditorSubtitulos } from "@/components/video/EditorSubtitulos";
import { GestorComposiciones } from "@/components/video/GestorComposiciones";
// El editor de capas (Konva) se carga PEREZOSAMENTE: pesa y solo se necesita en la sección
// Overlay. Así el bundle inicial es menor y los tests/SSR no importan Konva salvo que entren ahí.
const PanelOverlay = React.lazy(() =>
  import("@/components/video/PanelOverlay").then((m) => ({ default: m.PanelOverlay })),
);
import { PanelPip } from "@/components/video/PanelPip";
import { PanelRender } from "@/components/video/PanelRender";
import { PistaBase } from "@/components/video/PistaBase";
import { PreviewComposicion, type PreviewPlayerHandle } from "@/components/video/PreviewComposicion";
import { SelectorFormato } from "@/components/video/SelectorFormato";
import { TimelineMultipista } from "@/components/video/TimelineMultipista";
import { PanelAudio } from "@/components/video/PanelAudio";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError, urlMedia } from "@/lib/api";
import {
  cambiarAspecto,
  composicionVacia,
  dividirClipBase,
  moverSegmentoBase,
  pistaAudio,
  pistaBase,
  pistaPip,
  pistaSubtitulos,
  quitarMusica,
  quitarPip,
  quitarSegmentoBase,
  setAudioBase,
  setCajaPip,
  setCapasOverlay,
  setClipBase,
  setClipPip,
  setMusica,
  setRecorteBase,
  setReencuadreBase,
  setVolumenMusica,
  tituloBorradorPorDefecto,
  type AspectoVideo,
  type ComposicionVideo,
  type EstadoComposicion,
  type SegmentoSub,
} from "@/lib/video";

type Seccion = "gestor" | "base" | "overlay" | "pip" | "audio" | "subs" | "render";

const SECCIONES: { clave: Seccion; etiqueta: string; Icono: typeof VideoIcon }[] = [
  { clave: "gestor", etiqueta: "Mis composiciones", Icono: FolderOpen },
  { clave: "base", etiqueta: "Base", Icono: VideoIcon },
  { clave: "overlay", etiqueta: "Overlay", Icono: Layers },
  { clave: "pip", etiqueta: "PiP", Icono: PictureInPicture2 },
  { clave: "audio", etiqueta: "Audio", Icono: Music },
  { clave: "subs", etiqueta: "Subtítulos", Icono: Captions },
  { clave: "render", etiqueta: "Render", Icono: Film },
];

export default function Video() {
  const { marcaActiva, marcaPrimaria } = useMarcaActiva();
  const marca = marcaActiva ?? marcaPrimaria ?? "";

  const [searchParams, setSearchParams] = useSearchParams();
  // Deep-links: `?composicion=<id>` reabre una composición; `?contenido=<id>` viene de una pieza
  // (find-or-create por contenido). Se procesan en un efecto y luego se limpian de la URL.
  const composicionParam = searchParams.get("composicion");
  const contenidoParam = searchParams.get("contenido");

  const [seccion, setSeccion] = React.useState<Seccion>("gestor");
  const [aspecto, setAspecto] = React.useState<AspectoVideo>("9:16");
  const [doc, setDoc] = React.useState<ComposicionVideo>(() => composicionVacia("9:16", marca));

  // Media servible para el preview (la composición guarda claves; aquí guardamos las urls).
  const [baseKey, setBaseKey] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [pipKey, setPipKey] = React.useState("");
  const [pipUrl, setPipUrl] = React.useState("");
  const [musicaUrl, setMusicaUrl] = React.useState("");

  // Identidad backend de la composición.
  const [composicionId, setComposicionId] = React.useState<string | null>(null);
  // Pieza ligada (si la composición nació desde una pieza de video). Se pasa a `crearComposicion`.
  const [publicacionId, setPublicacionId] = React.useState<string | null>(null);
  const [segmentos, setSegmentos] = React.useState<SegmentoSub[]>([]);

  // Metadatos del borrador: título (nombre humano) y estado (borrador/listo, organización ≠ publicar).
  const [titulo, setTitulo] = React.useState("");
  const [estado, setEstado] = React.useState<EstadoComposicion>("borrador");

  // Doc VIGENTE (para el flush post-creación de `crear`: su onSuccess corre fuera del render).
  const docRef = React.useRef(doc);
  React.useEffect(() => {
    docRef.current = doc;
  });

  // `id` explícito para el flush post-creación (el estado `composicionId` aún no está aplicado
  // cuando corre el onSuccess de `crear`); el resto de llamadas usan el id del estado.
  const guardar = useMutation({
    mutationFn: ({ id, doc: d }: { id?: string; doc: ComposicionVideo }) =>
      api.video.guardarComposicion(id ?? composicionId!, d),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Crea la composición en el backend en cuanto hay una edición significativa (NO espera al clip
  // base): así el borrador no se pierde si el usuario se va antes de subir el clip. `marca` es
  // obligatoria en la API: sin marca activa no se puede crear. Si la composición nació desde una
  // pieza de video, se ENVÍA su `publicacion_id` para ligarla. Persiste título (derivando uno por
  // defecto si está vacío) y estado.
  const crear = useMutation({
    mutationFn: (d: ComposicionVideo) => {
      const tit = titulo.trim() || tituloBorradorPorDefecto(d.formato?.preset ?? aspecto);
      return api.video.crearComposicion({
        marca: d.marca || marca,
        documento: d,
        titulo: tit,
        estado,
        ...(publicacionId ? { publicacion_id: publicacionId } : {}),
      });
    },
    onSuccess: (r, d) => {
      setComposicionId(r.id);
      // Refleja en UI el título que realmente se guardó (el derivado por defecto si estaba vacío).
      if (!titulo.trim()) setTitulo(tituloBorradorPorDefecto(d.formato?.preset ?? aspecto));
      // Lo editado MIENTRAS se creaba (p. ej. un trim rápido tras subir el clip) quedó solo en
      // local: sin id aún no se podía autoguardar. Flushea el doc vigente para no perderlo (y el
      // indicador "Guardando…" sigue siendo honesto: usa la misma mutación de guardado).
      if (docRef.current !== d) {
        void guardar.mutateAsync({ id: r.id, doc: docRef.current }).catch(() => {});
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  /** Hidrata el estado local (doc, aspecto, claves/urls de media, título/estado) desde una carga. */
  const hidratar = React.useCallback(
    (cargado: ComposicionVideo, id: string, meta?: { titulo?: string; estado?: EstadoComposicion }) => {
      setDoc(cargado);
      setComposicionId(id);
      setAspecto((cargado.formato?.preset as AspectoVideo) ?? "9:16");
      setTitulo(meta?.titulo ?? "");
      setEstado(meta?.estado ?? "borrador");
      const base = pistaBase(cargado)?.clips[0]?.media_id ?? "";
      setBaseKey(base);
      setBaseUrl(base ? urlMedia(base) : "");
      const pip = pistaPip(cargado)?.clips[0]?.media_id ?? "";
      setPipKey(pip);
      setPipUrl(pip ? urlMedia(pip) : "");
      const mus = pistaAudio(cargado)?.clips[0]?.media_id ?? "";
      setMusicaUrl(mus ? urlMedia(mus) : "");
      setSegmentos([]);
      setSeccion("base");
    },
    [],
  );

  // Carga por deep-link. `?composicion=<id>` reabre; `?contenido=<id>` busca-o-crea por pieza.
  // Tras resolver, limpia el query param para no recargar en cada render. Idempotente: no recarga
  // si ya estamos en esa composición.
  const cargando = React.useRef(false);
  React.useEffect(() => {
    if (cargando.current) return;

    async function cargarComposicion(id: string) {
      cargando.current = true;
      try {
        const { composicion } = await api.video.composicion(id);
        hidratar(composicion.documento, composicion.id, {
          titulo: composicion.titulo,
          estado: composicion.estado,
        });
      } catch (e) {
        toast.error(mensajeError(e));
      } finally {
        setSearchParams({}, { replace: true });
        cargando.current = false;
      }
    }

    async function abrirPorPublicacion(cid: string) {
      if (!marca) return; // sin marca no se puede crear; espera a que cargue la marca activa.
      cargando.current = true;
      try {
        const { composiciones } = await api.video.listarComposiciones({
          marca,
          publicacion_id: cid,
        });
        if (composiciones.length > 0) {
          // Reabre la composición ya existente de esta pieza (la más reciente).
          const existente = composiciones[0];
          hidratar(existente.documento, existente.id, {
            titulo: existente.titulo,
            estado: existente.estado,
          });
        } else {
          // No hay: crea una nueva VACÍA ligada a la pieza y la deja abierta para subir el clip.
          const nueva = composicionVacia(aspecto, marca);
          const tit = tituloBorradorPorDefecto(nueva.formato?.preset ?? aspecto);
          const { id } = await api.video.crearComposicion({
            marca,
            documento: nueva,
            publicacion_id: cid,
            titulo: tit,
            estado: "borrador",
          });
          setPublicacionId(cid);
          hidratar(nueva, id, { titulo: tit, estado: "borrador" });
        }
      } catch (e) {
        toast.error(mensajeError(e));
      } finally {
        setSearchParams({}, { replace: true });
        cargando.current = false;
      }
    }

    if (composicionParam && composicionParam !== composicionId) {
      void cargarComposicion(composicionParam);
    } else if (contenidoParam && contenidoParam !== publicacionId) {
      setPublicacionId(contenidoParam);
      void abrirPorPublicacion(contenidoParam);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [composicionParam, contenidoParam, marca]);

  // Actualiza SOLO metadatos del borrador (titulo/estado) sin reenviar el documento (PUT parcial).
  const actualizarMeta = useMutation({
    mutationFn: (cambios: { titulo?: string; estado?: EstadoComposicion }) =>
      api.video.actualizarComposicion(composicionId!, cambios),
    onError: (e) => toast.error(mensajeError(e)),
  });

  /**
   * Aplica una mutación pura al documento y la PERSISTE. Si aún no hay composición en backend, la
   * CREA al primer cambio real (persistencia temprana: el borrador no se pierde aunque no haya
   * clip base). Si ya existe, autoguarda. Sin cambio real (misma referencia) no hace nada.
   */
  const mutar = React.useCallback(
    (fn: (d: ComposicionVideo) => ComposicionVideo) => {
      setDoc((prev) => {
        const siguiente = fn(prev);
        if (siguiente === prev) return prev; // sin cambio real: no reguardar (evita bucles).
        if (composicionId) {
          void guardar.mutateAsync({ doc: siguiente }).catch(() => {});
        } else if (!crear.isPending) {
          // Primer cambio significativo sin composición todavía: crearla (necesita marca).
          const conMarca = { ...siguiente, marca: siguiente.marca || marca };
          if (!conMarca.marca) {
            toast.error("Selecciona una marca antes de editar el video.");
            return conMarca;
          }
          crear.mutate(conMarca);
          return conMarca;
        }
        return siguiente;
      });
    },
    [composicionId, guardar, crear, marca],
  );

  /** Crea explícitamente el borrador (botón "Guardar borrador") si aún no existe. */
  const guardarBorrador = React.useCallback(() => {
    if (composicionId || crear.isPending) return;
    const conMarca = { ...doc, marca: doc.marca || marca };
    if (!conMarca.marca) {
      toast.error("Selecciona una marca antes de guardar el borrador.");
      return;
    }
    setDoc(conMarca);
    crear.mutate(conMarca);
  }, [composicionId, crear, doc, marca]);

  /** Renombra el borrador (si ya existe en backend; si no, sólo guarda el título local). */
  const onCambiarTitulo = React.useCallback(
    (nuevo: string) => {
      setTitulo(nuevo);
      if (composicionId) actualizarMeta.mutate({ titulo: nuevo.trim() });
    },
    [composicionId, actualizarMeta],
  );

  /** Cambia el estado borrador↔listo ("listo" NO publica; es organización). */
  const cambiarEstado = React.useCallback(
    (nuevo: EstadoComposicion) => {
      setEstado(nuevo);
      if (composicionId) actualizarMeta.mutate({ estado: nuevo });
    },
    [composicionId, actualizarMeta],
  );

  // Indicador de guardado: "Guardando…" mientras hay alguna escritura en curso; "Guardado" tras crear.
  const guardando = crear.isPending || guardar.isPending || actualizarMeta.isPending;

  // Reabre una composición desde el gestor: navega a `?composicion=<id>` (el efecto la carga).
  const abrirComposicion = React.useCallback(
    (id: string) => setSearchParams({ composicion: id }),
    [setSearchParams],
  );

  // Empieza una composición en BLANCO (descarta la pieza ligada y el estado actual).
  const nuevaComposicion = React.useCallback(() => {
    setComposicionId(null);
    setPublicacionId(null);
    setBaseKey("");
    setBaseUrl("");
    setPipKey("");
    setPipUrl("");
    setMusicaUrl("");
    setSegmentos([]);
    setTitulo("");
    setEstado("borrador");
    setDoc(composicionVacia(aspecto, marca));
    setSeccion("base");
  }, [aspecto, marca]);

  function onCambioFormato(a: AspectoVideo) {
    setAspecto(a);
    mutar((d) => cambiarAspecto(d, a));
  }

  function onCambioBase(clave: string, url: string) {
    setBaseKey(clave);
    setBaseUrl(url);
    if (!clave) {
      mutar((d) => setClipBase(d, "", 0));
      return;
    }
    // Lee la duración real del clip para fijar duracion_ms; si falla, usa 0 (el render la recalcula).
    leerDuracion(url)
      .then((ms) => fijarBase(clave, ms))
      .catch(() => fijarBase(clave, 0));
  }

  function fijarBase(clave: string, ms: number) {
    setDoc((prev) => {
      // Asegura que la composición lleve la marca activa (la API la exige al crear).
      const siguiente = setClipBase({ ...prev, marca: prev.marca || marca }, clave, ms);
      // La composición se CREA al tener el primer clip base; luego se autoguarda.
      if (!composicionId) {
        if (!siguiente.marca) {
          toast.error("Selecciona una marca antes de editar el video.");
          return siguiente;
        }
        crear.mutate(siguiente);
      } else {
        void guardar.mutateAsync({ doc: siguiente }).catch(() => {});
      }
      return siguiente;
    });
  }

  function onCambioPip(clave: string, url: string) {
    setPipKey(clave);
    setPipUrl(url);
    if (!clave) {
      mutar((d) => quitarPip(d));
      return;
    }
    leerDuracion(url)
      .then((ms) => mutar((d) => setClipPip(d, clave, ms)))
      .catch(() => mutar((d) => setClipPip(d, clave, 0)));
  }

  // ── MÚSICA (pista de audio independiente) ───────────────────────────────────────────────────
  function onCambioMusica(clave: string, url: string) {
    setMusicaUrl(url);
    if (!clave) {
      mutar((d) => quitarMusica(d));
      return;
    }
    leerDuracion(url)
      .then((ms) => mutar((d) => setMusica(d, clave, ms)))
      .catch(() => mutar((d) => setMusica(d, clave, 0)));
  }

  const quitarMusicaLocal = React.useCallback(() => {
    setMusicaUrl("");
    mutar((d) => quitarMusica(d));
  }, [mutar]);

  // Subir un archivo de música y ligarlo (lo dispara «+ Música» del timeline o del panel Audio).
  const inputMusicaRef = React.useRef<HTMLInputElement>(null);
  const subirMusica = useMutation({
    mutationFn: (archivo: File) => api.subirVideo(archivo),
    onSuccess: (r) => onCambioMusica(r.id, r.url),
    onError: (e) => toast.error(mensajeError(e)),
  });
  const pedirMusica = React.useCallback(() => inputMusicaRef.current?.click(), []);
  function onArchivoMusica(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subirMusica.mutate(archivo);
    if (inputMusicaRef.current) inputMusicaRef.current.value = "";
  }

  // Escribe el id de subtítulo en la pista subs de la composición (idempotente: si ya coincide,
  // no muta ni reguarda, para no entrar en bucle de autoguardado).
  function onSubtituloLigado(id: string) {
    mutar((d) => {
      if (pistaSubtitulos(d)?.subtitulo_id === id) return d;
      return {
        ...d,
        pistas: d.pistas.map((p) => (p.tipo === "subtitulos" ? { ...p, subtitulo_id: id } : p)),
      };
    });
  }

  // Caja del PiP: el MISMO commit sirve a los inputs numéricos del panel y al arrastre/
  // redimensionado directo sobre el preview (sincronía bidireccional vía el doc compartido).
  const onCajaPip = React.useCallback(
    (caja: { x?: number; y?: number; w?: number; h?: number }) =>
      mutar((d) => setCajaPip(d, caja)),
    [mutar],
  );

  const tieneBase = !!baseKey;
  // Sin marca activa no se puede crear/guardar la composición: en vez de fallar con un toast al
  // primer cambio, se muestra un aviso claro y se desactiva la edición hasta elegir marca.
  const sinMarca = !marca;

  return (
    // FULL-BLEED (mismo patrón que Imagen.tsx): anula el padding del `<main>` del shell para
    // ocupar exactamente el alto bajo la cabecera (h-12 = 3rem). `overflow-hidden` aquí: la
    // página NUNCA scrollea; el scroll vive DENTRO de cada panel (estilo Canva).
    <div className="-mx-4 -mt-2 -mb-4 flex h-[calc(100dvh-3rem)] flex-col overflow-hidden sm:-mx-6 sm:-mb-6 lg:-mx-8">
      {/* Título de sección (portaliza a la barra de cabecera unificada del shell). */}
      <TituloPagina titulo="Video" icono={VideoIcon} />

      {/* Estado de guardado en la CABECERA unificada (mismo patrón que Imagen): se portaliza al
          flanco DERECHO vía `AccionesPaginaFin` (bajo `md` cae a la fila de acciones móvil).
          Honesto con el estado real: lee los isPending de crear/guardar/actualizar. En el gestor
          no hay borrador en edición. */}
      {seccion !== "gestor" && (
        <AccionesPaginaFin>
          {/* «Sin guardar» en ámbar vía `--aviso-texto-plano`: amber-600/400 de siempre fuera
              del editor, ámbar-100 claro sobre la barra naranja (mismo criterio que Imagen). */}
          <span
            aria-live="polite"
            className={`whitespace-nowrap text-xs ${
              !guardando && !composicionId
                ? "text-[hsl(var(--aviso-texto-plano))]"
                : "text-muted-foreground"
            }`}
          >
            {guardando ? "Guardando…" : composicionId ? "Guardado" : "Sin guardar"}
          </span>
        </AccionesPaginaFin>
      )}

      {/* Sin marca activa no hay dónde guardar: aviso claro + edición desactivada (mejor que un
          toast seco al primer cambio). El selector de marca vive en la cabecera del shell. */}
      {seccion !== "gestor" && sinMarca && (
        <div
          role="alert"
          className="shrink-0 border-b border-amber-300/60 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:border-amber-700/50 dark:bg-amber-950/40 dark:text-amber-300"
        >
          Selecciona una marca arriba para empezar a editar.
        </div>
      )}

      {/* Barra del BORRADOR: título, estado (borrador/listo) y acciones. El indicador de
          guardado vive en la cabecera unificada (AccionesPaginaFin, arriba). Fuera del gestor
          (en el gestor no se edita un borrador concreto). */}
      {seccion !== "gestor" && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <input
            type="text"
            value={titulo}
            onChange={(e) => onCambiarTitulo(e.target.value)}
            placeholder={tituloBorradorPorDefecto(aspecto)}
            aria-label="Título del borrador"
            disabled={sinMarca}
            className="min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
          />

          {/* Badge de estado. */}
          <Badge variant={estado === "listo" ? "ok" : "aviso"} className="shrink-0 gap-1">
            {estado === "listo" ? <CheckCircle2 className="h-3 w-3" /> : null}
            {estado === "listo" ? "Listo" : "Borrador"}
          </Badge>

          {/* El indicador de guardado vive en la cabecera unificada (arriba), no aquí:
              un solo sitio para ese dato, igual que en Imagen. */}

          {/* Acciones: guardar borrador (si aún no existe) o marcar listo/volver a borrador. */}
          {!composicionId ? (
            <button
              type="button"
              onClick={guardarBorrador}
              disabled={crear.isPending || sinMarca}
              title={sinMarca ? "Selecciona una marca arriba" : undefined}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent/60 disabled:opacity-40"
            >
              <Save className="h-3.5 w-3.5" />
              Guardar borrador
            </button>
          ) : estado === "borrador" ? (
            <button
              type="button"
              onClick={() => cambiarEstado("listo")}
              title="Marca el borrador como listo (organización; NO publica)"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent/60"
            >
              <Check className="h-3.5 w-3.5" />
              Marcar listo
            </button>
          ) : (
            <button
              type="button"
              onClick={() => cambiarEstado("borrador")}
              title="Vuelve a borrador para seguir editando"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent/60"
            >
              <Undo2 className="h-3.5 w-3.5" />
              Volver a borrador
            </button>
          )}
        </div>
      )}

      {/* Cuerpo: RAIL de herramientas (izq, estilo Canva como el Estudio de imagen) + contenido.
          El padre NO scrollea (overflow-hidden); cada panel scrollea por dentro. */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Rail vertical de secciones. */}
        <nav
          aria-label="Secciones del editor de video"
          className="flex w-16 shrink-0 flex-col items-stretch gap-0.5 overflow-y-auto border-r border-border bg-muted/30 py-2"
        >
          {SECCIONES.map(({ clave, etiqueta, Icono }) => {
            const activo = seccion === clave;
            // Las secciones que componen sobre el clip requieren un clip base; "Mis composiciones"
            // (gestor) y "Base" están siempre disponibles.
            const requiereBase = clave !== "base" && clave !== "gestor";
            const off = requiereBase && !tieneBase;
            return (
              <button
                key={clave}
                type="button"
                disabled={off}
                title={off ? "Requiere un clip base" : undefined}
                onClick={() => setSeccion(clave)}
                className={`flex flex-col items-center gap-1 px-1 py-2 text-[10px] font-medium leading-tight transition-colors disabled:opacity-40 ${
                  activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60"
                }`}
              >
                <Icono className="h-5 w-5" />
                <span className="text-center">{etiqueta}</span>
              </button>
            );
          })}
        </nav>

        {/* Contenido según la sección. */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {seccion === "gestor" ? (
            <div className="h-full overflow-y-auto">
              <div className="space-y-3 p-4 sm:p-6">
                <button
                  type="button"
                  onClick={nuevaComposicion}
                  className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent/60"
                >
                  Nueva composición
                </button>
                <GestorComposiciones marca={marca} onAbrir={abrirComposicion} />
              </div>
            </div>
          ) : seccion === "overlay" ? (
            // Overlay: editor de capas a pantalla completa, con el clip base DETRÁS del lienzo
            // (las capas se editan directamente sobre el vídeo, no en un área aparte).
            <React.Suspense
              fallback={
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  Cargando editor de capas…
                </div>
              }
            >
              <PanelOverlay
                doc={doc}
                marca={marca}
                capas={pistaOverlayCapas(doc)}
                videoBaseUrl={baseUrl}
                onCapas={(capas) => mutar((d) => setCapasOverlay(d, capas))}
              />
            </React.Suspense>
          ) : (
            // Resto de secciones: panel contextual (controles inline) + LIENZO ÚNICO centrado
            // (formato in-place arriba) + timeline multipista debajo.
            <div className="flex h-full min-h-0">
              <aside className="w-[300px] shrink-0 overflow-y-auto border-r border-border p-4">
                {seccion === "base" && (
                  <PistaBase
                    doc={doc}
                    videoKey={baseKey}
                    videoUrl={baseUrl}
                    onCambioVideo={onCambioBase}
                    onReencuadre={(c) => mutar((d) => setReencuadreBase(d, c))}
                    disabled={sinMarca}
                  />
                )}
                {seccion === "pip" && (
                  <PanelPip
                    doc={doc}
                    videoKey={pipKey}
                    videoUrl={pipUrl}
                    onCambioVideo={onCambioPip}
                    onQuitar={() => {
                      setPipKey("");
                      setPipUrl("");
                      mutar((d) => quitarPip(d));
                    }}
                    disabled={sinMarca}
                  />
                )}
                {seccion === "audio" && (
                  <PanelAudio
                    doc={doc}
                    musicaUrl={musicaUrl}
                    onAudioBase={(c) => mutar((d) => setAudioBase(d, c))}
                    onCambioMusica={onCambioMusica}
                    onVolumenMusica={(c) => mutar((d) => setVolumenMusica(d, c))}
                    onQuitarMusica={quitarMusicaLocal}
                    disabled={sinMarca}
                  />
                )}
                {seccion === "subs" && (
                  <EditorSubtitulos
                    composicionId={composicionId}
                    baseMediaId={baseKey}
                    onSubtituloLigado={onSubtituloLigado}
                    onSegmentos={setSegmentos}
                  />
                )}
                {seccion === "render" && (
                  <PanelRender
                    composicionId={composicionId}
                    onAntesDeRenderizar={async () => {
                      if (composicionId) await guardar.mutateAsync({ doc });
                    }}
                  />
                )}
              </aside>

              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                {/* Formato IN-PLACE sobre el lienzo (un solo selector). */}
                <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-1.5">
                  <span className="text-xs font-medium text-muted-foreground">Formato</span>
                  <SelectorFormato aspecto={aspecto} onCambio={onCambioFormato} disabled={sinMarca} />
                  {seccion === "base" && tieneBase && (
                    <span className="ml-auto hidden text-[11px] text-muted-foreground sm:inline">
                      Arrastra sobre el vídeo para mover el foco
                    </span>
                  )}
                  {seccion === "pip" && (
                    <span className="ml-auto hidden text-[11px] text-muted-foreground sm:inline">
                      Arrastra y redimensiona el PiP en el lienzo
                    </span>
                  )}
                </div>
                <div className="flex min-h-0 flex-1 flex-col bg-muted/30 p-4">
                  <PreviewConTimeline
                    doc={doc}
                    baseUrl={baseUrl}
                    pipUrl={pipUrl}
                    segmentos={segmentos}
                    edicionDeshabilitada={sinMarca}
                    onTrim={(idx, inMs, outMs) =>
                      mutar((d) => setRecorteBase(d, inMs, outMs, undefined, idx))
                    }
                    onDividir={(idx, msLocal) => mutar((d) => dividirClipBase(d, idx, msLocal))}
                    onQuitarSegmento={(idx) => mutar((d) => quitarSegmentoBase(d, idx))}
                    onMoverSegmento={(idx, dest) => mutar((d) => moverSegmentoBase(d, idx, dest))}
                    onAudioBase={(c) => mutar((d) => setAudioBase(d, c))}
                    onAnadirMusica={pedirMusica}
                    onVolumenMusica={(c) => mutar((d) => setVolumenMusica(d, c))}
                    onQuitarMusica={quitarMusicaLocal}
                    pipEditable={seccion === "pip" && !sinMarca}
                    onCajaPip={onCajaPip}
                    reframeEditable={seccion === "base" && !sinMarca}
                    onFoco={(foco) => mutar((d) => setReencuadreBase(d, { foco }))}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input oculto para subir música (lo dispara «+ Música» del timeline / panel de audio). */}
      <input
        ref={inputMusicaRef}
        type="file"
        accept="audio/*,video/*"
        onChange={onArchivoMusica}
        className="hidden"
        aria-label="Subir música"
      />
    </div>
  );
}

/**
 * Vista previa + LÍNEA DE TIEMPO con el reloj del player COMPARTIDO. Vive como componente
 * propio para que el tick de reproducción (60 fps vía `onTiempo`) re-renderice SOLO esta
 * columna y no toda la página (el editor de capas Konva de Overlay es caro). El playhead es
 * bidireccional: el player alimenta `tiempoSeg` y el timeline busca vía `playerRef.buscarA`.
 */
function PreviewConTimeline({
  doc,
  baseUrl,
  pipUrl,
  segmentos,
  edicionDeshabilitada,
  onTrim,
  onDividir,
  onQuitarSegmento,
  onMoverSegmento,
  onAudioBase,
  onAnadirMusica,
  onVolumenMusica,
  onQuitarMusica,
  pipEditable,
  onCajaPip,
  reframeEditable,
  onFoco,
}: {
  doc: ComposicionVideo;
  baseUrl: string;
  pipUrl: string;
  segmentos: SegmentoSub[];
  edicionDeshabilitada: boolean;
  onTrim: (idx: number, inMs: number, outMs: number) => void;
  onDividir: (idx: number, msLocal: number) => void;
  onQuitarSegmento: (idx: number) => void;
  onMoverSegmento: (idx: number, destino: number) => void;
  onAudioBase: (cambios: { volumen?: number; silenciar?: boolean }) => void;
  onAnadirMusica: () => void;
  onVolumenMusica: (cambios: { volumen?: number; silenciar?: boolean }) => void;
  onQuitarMusica: () => void;
  pipEditable: boolean;
  onCajaPip: (caja: { x?: number; y?: number; w?: number; h?: number }) => void;
  reframeEditable: boolean;
  onFoco: (foco: [number, number]) => void;
}) {
  const playerRef = React.useRef<PreviewPlayerHandle>(null);
  const [tiempoSeg, setTiempoSeg] = React.useState(0);
  return (
    <div className="flex min-h-0 w-full flex-1 flex-col gap-3">
      <PreviewComposicion
        doc={doc}
        baseUrl={baseUrl}
        pipUrl={pipUrl}
        segmentos={segmentos}
        playerRef={playerRef}
        onTiempo={setTiempoSeg}
        pipEditable={pipEditable}
        onCajaPip={onCajaPip}
        reframeEditable={reframeEditable}
        onFoco={onFoco}
        conEncuadre
      />
      {baseUrl ? (
        <div className="mx-auto w-full max-w-3xl shrink-0">
          <TimelineMultipista
            doc={doc}
            tiempoSeg={tiempoSeg}
            onSeek={(s) => playerRef.current?.buscarA(s)}
            onTrimSegmento={onTrim}
            onDividirSegmento={onDividir}
            onQuitarSegmento={onQuitarSegmento}
            onMoverSegmento={onMoverSegmento}
            onAudioBase={onAudioBase}
            onAnadirMusica={onAnadirMusica}
            onVolumenMusica={onVolumenMusica}
            onQuitarMusica={onQuitarMusica}
            segmentos={segmentos}
            disabled={edicionDeshabilitada}
          />
        </div>
      ) : null}
    </div>
  );
}

/** Lee la duración (ms) de un video desde su URL, cargando metadatos en un <video> efímero. */
function leerDuracion(url: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      const ms = Number.isFinite(v.duration) ? Math.round(v.duration * 1000) : 0;
      resolve(ms);
    };
    v.onerror = () => reject(new Error("No se pudo leer la duración del video."));
    v.src = url;
  });
}

/** Capas de la pista overlay (vacío si no hay pista). */
function pistaOverlayCapas(doc: ComposicionVideo) {
  const p = doc.pistas.find((x) => x.tipo === "overlay");
  return p && "capas" in p ? p.capas : [];
}

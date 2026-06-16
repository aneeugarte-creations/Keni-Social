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
import { Captions, Check, CheckCircle2, Film, FolderOpen, Layers, PictureInPicture2, Save, Undo2, Video as VideoIcon } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { AccionesPaginaFin, TituloPagina } from "@/components/layout/encabezado";
import { EditorSubtitulos } from "@/components/video/EditorSubtitulos";
import { GestorComposiciones } from "@/components/video/GestorComposiciones";
// El editor de capas (Konva) se carga PEREZOSAMENTE: pesa y solo se necesita en la sección
// Overlay. Así el bundle inicial es menor y los tests/SSR no importan Konva salvo que entren ahí.
const PanelOverlay = React.lazy(() =>
  import("@/components/video/PanelOverlay").then((m) => ({ default: m.PanelOverlay })),
);
import { LineaTiempo } from "@/components/video/LineaTiempo";
import { PanelPip } from "@/components/video/PanelPip";
import { PanelRender } from "@/components/video/PanelRender";
import { PistaBase } from "@/components/video/PistaBase";
import { PreviewComposicion, type PreviewPlayerHandle } from "@/components/video/PreviewComposicion";
import { SelectorFormato } from "@/components/video/SelectorFormato";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError, urlMedia } from "@/lib/api";
import {
  cambiarAspecto,
  composicionVacia,
  pistaBase,
  pistaPip,
  pistaSubtitulos,
  quitarPip,
  setCajaPip,
  setCapasOverlay,
  setClipBase,
  setClipPip,
  setRecorteBase,
  setReencuadreBase,
  tituloBorradorPorDefecto,
  type AspectoVideo,
  type ComposicionVideo,
  type EstadoComposicion,
  type SegmentoSub,
} from "@/lib/video";

type Seccion = "gestor" | "base" | "overlay" | "pip" | "subs" | "render";

const SECCIONES: { clave: Seccion; etiqueta: string; Icono: typeof VideoIcon }[] = [
  { clave: "gestor", etiqueta: "Mis composiciones", Icono: FolderOpen },
  { clave: "base", etiqueta: "Base", Icono: VideoIcon },
  { clave: "overlay", etiqueta: "Overlay", Icono: Layers },
  { clave: "pip", etiqueta: "PiP", Icono: PictureInPicture2 },
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

      {/* Sub-navegación de secciones */}
      <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-border px-3 py-1.5" aria-label="Secciones del editor de video">
        {SECCIONES.map(({ clave, etiqueta, Icono }) => {
          const activo = seccion === clave;
          // Overlay/PiP/Subs/Render requieren un clip base; se deshabilitan hasta tenerlo.
          // "Mis composiciones" (gestor) y "Base" están siempre disponibles.
          const requiereBase = clave !== "base" && clave !== "gestor";
          const off = requiereBase && !tieneBase;
          return (
            <button
              key={clave}
              type="button"
              disabled={off}
              // Explica POR QUÉ está deshabilitada (el disabled sin razón desorienta).
              title={off ? "Requiere un clip base" : undefined}
              onClick={() => setSeccion(clave)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40 ${
                activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60"
              }`}
            >
              <Icono className="h-4 w-4" />
              {etiqueta}
            </button>
          );
        })}
      </nav>

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
          <span
            className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
              estado === "listo"
                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
                : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
            }`}
          >
            {estado === "listo" ? <CheckCircle2 className="h-3 w-3" /> : null}
            {estado === "listo" ? "Listo" : "Borrador"}
          </span>

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

      {/* Cuerpo: controles (izq) + preview (der). El GESTOR ocupa todo el ancho (sin preview).
          El padre NO scrollea (overflow-hidden); cada panel scrollea por dentro. */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {seccion === "gestor" ? (
          <div className="h-full overflow-y-auto">
            {/* Ocupa TODO el ancho (sin `max-w` centrado: los lados ya no quedan vacíos), mismo
                criterio que la galería de Imagen.tsx. */}
            <div className="space-y-3 p-4 sm:p-6">
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={nuevaComposicion}
                  className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent/60"
                >
                  Nueva composición
                </button>
              </div>
              <p className="text-xs text-muted-foreground">
                El estado de subtítulos y el video adjunto se muestran por fila.
              </p>
              <GestorComposiciones marca={marca} onAbrir={abrirComposicion} />
            </div>
          </div>
        ) : (
        // En lg+ el grid llena el alto disponible y CADA columna scrollea por separado (Canva:
        // paneles con scroll interno, página quieta). Por debajo de lg las columnas se apilan y
        // scrollea este contenedor (un solo scroll interno, nunca el de la página).
        <div className="mx-auto grid h-full w-full max-w-6xl gap-6 overflow-y-auto p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)] lg:overflow-hidden">
          {/* Columna de controles según la sección */}
          <section className="flex min-w-0 flex-col gap-4 lg:min-h-0 lg:overflow-y-auto">
            {seccion === "base" && (
              <>
                <div>
                  <h2 className="mb-2 text-sm font-semibold text-foreground">Formato</h2>
                  <SelectorFormato aspecto={aspecto} onCambio={onCambioFormato} disabled={sinMarca} />
                </div>
                <div>
                  <h2 className="mb-2 text-sm font-semibold text-foreground">Pista base</h2>
                  <PistaBase
                    doc={doc}
                    videoKey={baseKey}
                    videoUrl={baseUrl}
                    onCambioVideo={onCambioBase}
                    onReencuadre={(c) => mutar((d) => setReencuadreBase(d, c))}
                    disabled={sinMarca}
                  />
                </div>
              </>
            )}

            {seccion === "overlay" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Capas de overlay</h2>
                <p className="text-xs text-muted-foreground">
                  Logos, marcos de marca, imagen-in-video y textos.
                </p>
                {/* En lg+ el editor LLENA el alto restante de la columna (flex-1); por debajo
                    conserva un alto fijo (la columna apilada scrollea). */}
                <div className="min-h-0 lg:flex-1">
                  <React.Suspense
                    fallback={
                      <div className="flex h-[60vh] min-h-[420px] items-center justify-center rounded-md border border-border text-sm text-muted-foreground lg:h-full">
                        Cargando editor de capas…
                      </div>
                    }
                  >
                    <PanelOverlay
                      doc={doc}
                      marca={marca}
                      capas={pistaOverlayCapas(doc)}
                      onCapas={(capas) => mutar((d) => setCapasOverlay(d, capas))}
                    />
                  </React.Suspense>
                </div>
              </>
            )}

            {seccion === "pip" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Picture-in-Picture</h2>
                <PanelPip
                  doc={doc}
                  videoKey={pipKey}
                  videoUrl={pipUrl}
                  onCambioVideo={onCambioPip}
                  onCaja={onCajaPip}
                  onQuitar={() => {
                    setPipKey("");
                    setPipUrl("");
                    mutar((d) => quitarPip(d));
                  }}
                />
              </>
            )}

            {seccion === "subs" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Subtítulos (es-MX)</h2>
                <EditorSubtitulos
                  composicionId={composicionId}
                  baseMediaId={baseKey}
                  onSubtituloLigado={onSubtituloLigado}
                  onSegmentos={setSegmentos}
                />
              </>
            )}

            {seccion === "render" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Renderizar</h2>
                <p className="text-xs text-muted-foreground">
                  El preview de la derecha es solo una aproximación.
                </p>
                <PanelRender
                  composicionId={composicionId}
                  onAntesDeRenderizar={async () => {
                    if (composicionId) await guardar.mutateAsync({ doc });
                  }}
                />
              </>
            )}
          </section>

          {/* Columna de preview (persistente). Scrollea por dentro si no cabe; el preview se
              clampa al ancho de la columna (no desborda en horizontal). */}
          <aside className="min-w-0 space-y-2 lg:min-h-0 lg:overflow-y-auto">
            <h2 className="text-sm font-semibold text-foreground">Vista previa</h2>
            {/* `atajoEspacio` se apaga en Overlay: el Lienzo (Konva) ya usa la barra espaciadora
                para el pan del lienzo y los dos atajos chocarían. */}
            {/* El PiP solo es manipulable sobre el preview EN su sección (no sorprende al
                editar base/overlay/subtítulos); sin marca la edición está desactivada. */}
            <PreviewConTimeline
              doc={doc}
              baseUrl={baseUrl}
              pipUrl={pipUrl}
              segmentos={segmentos}
              atajoEspacio={seccion !== "overlay"}
              trimDeshabilitado={sinMarca}
              onTrim={(inMs, outMs, durMs) =>
                mutar((d) => setRecorteBase(d, inMs, outMs, durMs > 0 ? durMs : undefined))
              }
              pipEditable={seccion === "pip" && !sinMarca}
              onCajaPip={onCajaPip}
            />
          </aside>
        </div>
        )}
      </div>
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
  atajoEspacio,
  trimDeshabilitado,
  onTrim,
  pipEditable,
  onCajaPip,
}: {
  doc: ComposicionVideo;
  baseUrl: string;
  pipUrl: string;
  segmentos: SegmentoSub[];
  atajoEspacio: boolean;
  trimDeshabilitado: boolean;
  /** Commit del trim del clip base; `durMs` = duración real del clip (0 si aún no se conoce). */
  onTrim: (inMs: number, outMs: number, durMs: number) => void;
  /** Habilita arrastrar/redimensionar la ventana PiP directamente sobre el preview. */
  pipEditable: boolean;
  /** Commit de la caja PiP (compartido con los inputs numéricos del panel). */
  onCajaPip: (caja: { x?: number; y?: number; w?: number; h?: number }) => void;
}) {
  const playerRef = React.useRef<PreviewPlayerHandle>(null);
  const [tiempoSeg, setTiempoSeg] = React.useState(0);
  const [durSeg, setDurSeg] = React.useState(0);
  const durMs = Math.round(durSeg * 1000);
  return (
    <>
      <PreviewComposicion
        doc={doc}
        baseUrl={baseUrl}
        pipUrl={pipUrl}
        segmentos={segmentos}
        atajoEspacio={atajoEspacio}
        playerRef={playerRef}
        onTiempo={setTiempoSeg}
        onDuracion={setDurSeg}
        pipEditable={pipEditable}
        onCajaPip={onCajaPip}
      />
      {baseUrl ? (
        <LineaTiempo
          doc={doc}
          duracionClipMs={durMs}
          tiempoSeg={tiempoSeg}
          onSeek={(s) => playerRef.current?.buscarA(s)}
          onTrim={(inMs, outMs) => onTrim(inMs, outMs, durMs)}
          segmentos={segmentos}
          disabled={trimDeshabilitado}
        />
      ) : null}
    </>
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

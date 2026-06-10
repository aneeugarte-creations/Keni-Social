// Página del Editor profesional — WORKSPACE multi-marca.
//
// Cada PESTAÑA es un documento independiente (por MARCA) con su PROPIO store Zustand e historial;
// los stores persisten en un ref por id de pestaña. Todo post es 4:5 y una misma plantilla sirve
// para todas las redes (no hay dimensión ni filtro por red).
//
// PLANTILLAS por marca: «Guardar» actualiza la plantilla a la que está atada la pestaña (sin pedir
// nombre); «Guardar como» crea una nueva. Un indicador estilo Word muestra si hay cambios sin
// guardar. Sin pestañas se ve la GALERÍA de plantillas de la marca (o lienzo en blanco si no hay).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, FileUp, Image, Loader2, Maximize2, Minimize2, Plus, Repeat, Save, SaveAll, Video, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { TituloPagina } from "@/components/layout/encabezado";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { documentoVacio, type Documento } from "@/editor/documento";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, urlMedia, type PlantillaDiseno } from "@/lib/api";
import { prepararDocumento } from "@/lib/placa/docPieza";

type TipoPlantilla = "foto" | "miniatura";

// Todo post es 4:5 (1080×1350). El tamaño se puede ajustar en «Ajustes del lienzo».
const DIMS_DEFECTO: Documento["formato"] = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

interface Pestana {
  id: string;
  marca: string;
  nombre?: string; // nombre de la plantilla atada (si la hay)
  plantillaId?: string; // plantilla de diseño a la que «Guardar» sobrescribe
  // Si la pestaña está anclada a una publicación (historial/versionado).
  contenido?: string;
  plataforma?: string;
  // Bindings reales de la pieza (titular/pleca): se inyectan al renderizar/guardar para que las
  // capas con `binding` muestren el copy REAL, no el texto de muestra. Solo en pestañas de pieza.
  bindings?: Record<string, string>;
}

let _seq = 0;

// Clave de autoguardado local (crash-safety): por pieza, por plantilla, o por marca.
function claveAuto(p: Pestana): string {
  if (p.contenido && p.plataforma) return `keni:editor:pieza:${p.contenido}:${p.plataforma}`;
  if (p.plantillaId) return `keni:editor:plantilla:${p.plantillaId}`;
  return `keni:editor:doc:${p.marca}`;
}

function leerAuto(clave: string): Documento | null {
  try {
    const s = sessionStorage.getItem(clave);
    return s ? (JSON.parse(s) as Documento) : null;
  } catch {
    return null;
  }
}

export default function Imagen() {
  const opciones = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opciones.data?.marcas ?? [];

  // La marca la manda el SELECTOR GLOBAL del workspace (topbar, `useMarcaActiva`); el editor ya no
  // tiene selector propio. `marcaActiva` = null cuando el selector está en «Todas» (solo admin).
  const { marcaActiva } = useMarcaActiva();
  // Marca CONCRETA de respaldo para crear lienzos/abrir piezas (siempre una marca real): la global
  // si es válida, si no la primera del catálogo.
  const marcaInicial = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : marcas[0]?.id;

  const [searchParams] = useSearchParams();

  const [pestanas, setPestanas] = useState<Pestana[]>([]);
  const [activa, setActiva] = useState<string | null>(null);
  const stores = useRef<Map<string, StoreEditor>>(new Map());
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [galeria, setGaleria] = useState(false);
  // Diálogo de «Guardar como» (nombre de plantilla nueva + tipo).
  const [dialogo, setDialogo] = useState<{ nombre: string; tipo: TipoPlantilla } | null>(null);
  // Edición inline del nombre de una pestaña (doble-clic en su título).
  const [editTab, setEditTab] = useState<{ id: string; valor: string } | null>(null);
  // Cambios sin guardar en la plantilla, por pestaña (indicador estilo Word).
  const [dirty, setDirty] = useState<Record<string, boolean>>({});

  // PANTALLA COMPLETA: foco en el editor (pestañas + lienzo), ocultando el resto del shell. El
  // objetivo es la región editor (`editorRef`), así sus propias pestañas —y el botón para salir—
  // siguen visibles en pantalla completa.
  const editorRef = useRef<HTMLDivElement | null>(null);
  const [pantallaCompleta, setPantallaCompleta] = useState(false);
  useEffect(() => {
    const onCambio = () => setPantallaCompleta(document.fullscreenElement === editorRef.current);
    document.addEventListener("fullscreenchange", onCambio);
    return () => document.removeEventListener("fullscreenchange", onCambio);
  }, []);
  const alternarPantallaCompleta = () => {
    const el = editorRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen?.();
    else void el.requestFullscreen?.().catch(() => toast.error("Tu navegador no permitió la pantalla completa."));
  };

  // Marca que filtra la GALERÍA y la TEXTO del estado vacío: la del selector global. «Todas»
  // (marcaActiva null) => "" => se muestra TODO (plantillas/logos de todas las marcas).
  const marcaEfectiva = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : "";

  const pestanaActiva = pestanas.find((t) => t.id === activa) ?? null;
  const storeActivo = activa ? stores.current.get(activa) ?? null : null;
  // Con una pestaña abierta manda su marca (fija por pestaña); sin pestaña, la del selector global.
  const marcaPanel = pestanaActiva?.marca || marcaEfectiva;
  const sucia = activa ? dirty[activa] : false;

  const marcarLimpia = (id: string) => setDirty((d) => ({ ...d, [id]: false }));
  const bindPlantilla = (id: string, plantillaId: string, nombre: string) =>
    setPestanas((p) => p.map((t) => (t.id === id ? { ...t, plantillaId, nombre } : t)));

  const nuevaPestana = (marca: string, doc?: Documento, extra?: Partial<Pestana>): { id: string; store: StoreEditor } => {
    _seq += 1;
    const id = `tab-${_seq}`;
    const store = crearStoreEditor(doc ?? documentoVacio(DIMS_DEFECTO, marca));
    stores.current.set(id, store);
    setPestanas((p) => [...p, { id, marca, ...extra }]);
    setActiva(id);
    setDirty((d) => ({ ...d, [id]: false }));
    return { id, store };
  };

  // Lienzo EN BLANCO de verdad: SIEMPRE limpio y vacío. No restaura borradores previos de la marca
  // (antes reaparecían "elementos de otros diseños"); los borradores de plantilla/pieza sí se
  // recuperan en sus propios flujos (abrirPlantilla / abrirPiezaTab).
  const abrirPestana = (marcaArg?: string) => {
    // Un lienzo nuevo necesita una marca CONCRETA: si el global está en «Todas», cae a `marcaInicial`.
    const marca = marcaArg || marcaEfectiva || marcaInicial;
    if (!marca) return;
    nuevaPestana(marca);
  };

  // Abre una plantilla guardada EN UNA PESTAÑA NUEVA, atada a esa plantilla.
  const abrirPlantilla = (p: PlantillaDiseno) => {
    nuevaPestana(p.marca, p.documento as Documento, { nombre: p.nombre, plantillaId: p.id });
    setGaleria(false);
    toast.success(`Plantilla «${p.nombre}» abierta.`);
  };

  // Fija los bindings (titular/pleca real) de una pestaña ya abierta.
  const setBindings = (id: string, bindings: Record<string, string>) =>
    setPestanas((p) => p.map((t) => (t.id === id ? { ...t, bindings } : t)));

  // Abre una pestaña ANCLADA a una publicación.
  const abrirPiezaTab = async (cid: string, pid: string, marca: string) => {
    const { id, store } = nuevaPestana(marca, undefined, { contenido: cid, plataforma: pid });
    // Aunque restauremos un borrador local, pedimos los bindings reales (copy/pleca) para el render.
    const guardado = leerAuto(claveAuto({ id: "", marca, contenido: cid, plataforma: pid }));
    try {
      const pieza = await api.imagenPieza(cid, pid);
      setBindings(id, pieza.bindings ?? {});
      if (guardado) {
        store.getState().cargar(guardado);
        return;
      }
      if (pieza.documento) {
        // Versión ya guardada en el editor: es la verdad (su foto va horneada en los huecos).
        store.getState().cargar(pieza.documento as Documento);
      } else {
        // Sin versión: arranca de la plantilla EFECTIVA (la misma que compone el feed) e inyecta
        // la foto de la pieza en sus huecos, para que el lienzo muestre el marco y la foto REALES
        // (no la plantilla genérica de la marca ni una foto de muestra). Cae a la plantilla de
        // marca por defecto si la pieza no tiene plantilla efectiva.
        const base = (pieza.plantilla ??
          (await api.imagenPlantilla(marca, "feed")).documento) as Documento;
        const fotos = pieza.fotos ?? [];
        store.getState().cargar(fotos.length ? prepararDocumento(base, { fotos }) : base);
      }
    } catch (e) {
      if (guardado) {
        store.getState().cargar(guardado);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo abrir la pieza.");
    }
  };

  const qc = useQueryClient();

  const plantillasQ = useQuery({
    queryKey: ["plantillas-diseno", marcaPanel],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: marcaPanel || undefined }, signal),
    // En «Todas» (marcaPanel vacío) se listan las plantillas de todas las marcas.
    enabled: marcas.length > 0,
  });

  // Apertura inicial (una vez): pieza por URL → ancla; si no, con plantillas deja la GALERÍA; sin
  // ninguna abre un lienzo en blanco.
  const abiertoInicial = useRef(false);
  useEffect(() => {
    if (abiertoInicial.current) return;
    const cid = searchParams.get("contenido");
    const pid = searchParams.get("plataforma");
    if (cid && pid) {
      abiertoInicial.current = true;
      void abrirPiezaTab(cid, pid, searchParams.get("marca") || marcaInicial || "");
      return;
    }
    if (marcas.length === 0 || !plantillasQ.isSuccess) return;
    abiertoInicial.current = true;
    if ((plantillasQ.data?.plantillas.length ?? 0) === 0) {
      void abrirPestana(marcaInicial ?? marcas[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, marcas, plantillasQ.isSuccess, plantillasQ.data]);

  const cerrarPestana = (id: string) => {
    // Si hay cambios sin guardar, confirmar. Las piezas/plantillas atadas autoguardan a servidor,
    // pero un lienzo suelto (sin plantilla ni pieza) solo tiene el borrador local: avisamos siempre.
    const t = pestanas.find((x) => x.id === id);
    const sinDestino = t && !t.plantillaId && !t.contenido;
    if (dirty[id]) {
      const msg = sinDestino
        ? "Esta pestaña tiene cambios sin guardar y no está atada a ninguna plantilla. ¿Cerrar y perder el trabajo?"
        : "Esta pestaña tiene cambios sin guardar. ¿Cerrar de todos modos?";
      if (!window.confirm(msg)) return;
    }
    stores.current.delete(id);
    setDirty((d) => {
      const { [id]: _omit, ...resto } = d;
      return resto;
    });
    setPestanas((p) => {
      const resto = p.filter((x) => x.id !== id);
      if (activa === id) setActiva(resto.length ? resto[resto.length - 1].id : null);
      return resto;
    });
  };

  const exportar = useMutation({
    mutationFn: () => {
      const store = activa ? stores.current.get(activa) : null;
      if (!store) throw new Error("No hay pestaña activa.");
      // Pieza: inyecta el titular/pleca REAL (binding). Plantilla suelta: sin bindings → texto de muestra.
      const bindings = pestanaActiva?.contenido ? pestanaActiva.bindings : undefined;
      return api.imagenRender(store.getState().documento, bindings);
    },
    onSuccess: (res) => {
      const url = `/api/media/${res.id}`;
      setExportUrl(url);
      // Abre el PNG en una pestaña nueva (lo más simple/robusto): el usuario ve el resultado ya.
      window.open(url, "_blank", "noopener,noreferrer");
      toast.success("PNG generado.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo exportar."),
  });

  // Al editar: marca "sin guardar", autoguarda local (crash-safety, ~0.8 s) y, si la pestaña está
  // atada a una plantilla, AUTOGUARDA en la plantilla tras 3 s de inactividad (estilo Word).
  useEffect(() => {
    if (!activa) return;
    const store = stores.current.get(activa);
    const p = pestanas.find((t) => t.id === activa);
    if (!store || !p) return;
    const clave = claveAuto(p);
    let tSession: number | undefined;
    let tAuto: number | undefined;
    const unsub = store.subscribe((estado, previo) => {
      if (estado.documento === previo.documento) return;
      setDirty((d) => ({ ...d, [p.id]: true }));
      // Borrador local.
      window.clearTimeout(tSession);
      tSession = window.setTimeout(() => {
        try {
          sessionStorage.setItem(clave, JSON.stringify(estado.documento));
        } catch {
          /* cuota llena: el trabajo sigue en memoria */
        }
      }, 800);
      // Autoguardado a la plantilla tras 3 s sin tocar nada.
      window.clearTimeout(tAuto);
      tAuto = window.setTimeout(async () => {
        if (!p.plantillaId) return; // sin plantilla atada no hay dónde guardar (usa «Guardar como»)
        const st = stores.current.get(p.id);
        if (!st) return;
        const doc = st.getState().documento;
        // Sin hueco de foto explícito el server rechaza; no spameamos 400s (el Guardar manual avisa).
        if (!doc.capas.some((c) => c.tipo === "imagen" && c.es_foto)) return;
        try {
          // Solo el documento (sin re-render de miniatura, para no cargar el server cada 3 s; la
          // miniatura se refresca al Guardar manual).
          await api.actualizarPlantillaDiseno(p.plantillaId, { documento: doc });
          // Solo marcar limpio si no se editó MIENTRAS guardaba (igualdad por referencia).
          if (stores.current.get(p.id)?.getState().documento === doc) {
            setDirty((d) => ({ ...d, [p.id]: false }));
          }
          qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
        } catch {
          /* falló el autoguardado: el punto rojo permanece */
        }
      }, 3000);
    });
    return () => {
      window.clearTimeout(tSession);
      window.clearTimeout(tAuto);
      unsub();
    };
  }, [activa, pestanas, qc]);

  // Genera la miniatura (render best-effort) del documento actual. Inyecta un titular de muestra:
  // las capas con `binding:"copy_in"` renderizan ese texto en vez de quedar vacías (sin esto, la
  // miniatura de la galería sale SIN titular, porque su texto sale del binding, no del literal).
  const miniaturaDe = async (documento: Documento): Promise<string> => {
    try {
      return (await api.imagenRender(documento, { copy_in: "TITULAR", etiqueta_default: "" })).id;
    } catch {
      return "";
    }
  };

  // GUARDAR: si la pestaña ya está atada a una plantilla, la sobrescribe (sin pedir nombre);
  // si no, abre «Guardar como».
  const guardar = useMutation({
    mutationFn: async () => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      if (!pestanaActiva.plantillaId) throw new Error("__sin_plantilla__");
      const documento = storeActivo.getState().documento;
      if (!documento.capas.some((c) => c.tipo === "imagen" && c.es_foto)) throw new Error("__sin_hueco__");
      const miniatura = await miniaturaDe(documento);
      return api.actualizarPlantillaDiseno(pestanaActiva.plantillaId, { documento, miniatura });
    },
    onSuccess: () => {
      if (activa) marcarLimpia(activa);
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Guardado.");
    },
    onError: (e: unknown) => {
      if (e instanceof Error && e.message === "__sin_plantilla__") {
        setDialogo({ nombre: pestanaActiva?.nombre ?? "", tipo: "foto" });
        return;
      }
      if (e instanceof Error && e.message === "__sin_hueco__") {
        toast.error("Marca una imagen como «hueco de foto» antes de guardar.");
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo guardar.");
    },
  });

  // GUARDAR COMO: crea una plantilla nueva con el nombre y tipo dados; ata la pestaña a ella.
  const guardarComo = useMutation({
    mutationFn: async ({ nombre, tipo }: { nombre: string; tipo: TipoPlantilla }) => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      const documento = storeActivo.getState().documento;
      if (!documento.capas.some((c) => c.tipo === "imagen" && c.es_foto)) throw new Error("__sin_hueco__");
      const miniatura = await miniaturaDe(documento);
      return api.crearPlantillaDiseno({ marca: pestanaActiva.marca, nombre, categoria: "post", tipo, documento, miniatura });
    },
    onSuccess: (res, { nombre }) => {
      if (activa) {
        bindPlantilla(activa, res.plantilla.id, nombre);
        marcarLimpia(activa);
      }
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla guardada.");
    },
    onError: (e: unknown) => {
      if (e instanceof Error && e.message === "__sin_hueco__") {
        toast.error("Marca una imagen como «hueco de foto» antes de guardar.");
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo guardar.");
    },
  });

  const confirmarNombre = () => {
    const nombre = dialogo?.nombre.trim();
    if (!nombre) return;
    guardarComo.mutate({ nombre, tipo: dialogo?.tipo ?? "foto" });
    setDialogo(null);
  };

  // Carga una plantilla en la pestaña ACTIVA (la ata a ella). REEMPLAZA el documento y resetea el
  // historial: si hay cambios sin guardar, confirmar antes para no perder el trabajo.
  const cargarPlantillaEnActiva = (p: PlantillaDiseno) => {
    if (storeActivo && activa) {
      if (dirty[activa] && !window.confirm(`Esto reemplaza el contenido actual (con cambios sin guardar) por «${p.nombre}». ¿Continuar?`)) {
        return;
      }
      storeActivo.getState().cargar(p.documento as Documento);
      bindPlantilla(activa, p.id, p.nombre);
      marcarLimpia(activa);
      toast.success(`Plantilla «${p.nombre}» cargada.`);
    }
  };

  const borrarPlantilla = useMutation({
    mutationFn: (id: string) => api.borrarPlantillaDiseno(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla borrada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo borrar."),
  });

  // DUPLICAR: crea una copia de la plantilla ya guardada en la galería (para «remixes» sin empezar
  // de cero). Aparece al instante al invalidar la query.
  const duplicarPlantilla = useMutation({
    mutationFn: (p: PlantillaDiseno) =>
      api.crearPlantillaDiseno({
        marca: p.marca,
        nombre: `Copia de ${p.nombre || "plantilla"}`,
        categoria: p.categoria || "post",
        tipo: p.tipo ?? "foto",
        documento: p.documento,
        miniatura: p.miniatura || undefined,
        lineas: p.lineas,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla duplicada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo duplicar."),
  });

  // ROTACIÓN: marca/desmarca una plantilla para el grupo en rotación de la marca. Con ≥2 marcadas,
  // cada post nuevo de la marca se lleva automáticamente la siguiente del grupo (mismo color en
  // todas las redes). Persiste al instante (PATCH) y refresca la galería.
  const rotarPlantilla = useMutation({
    mutationFn: ({ id, rotar }: { id: string; rotar: boolean }) =>
      api.actualizarPlantillaDiseno(id, { rotar }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success(res.plantilla.rotar ? "Añadida a la rotación." : "Quitada de la rotación.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo cambiar la rotación."),
  });

  // RENOMBRAR una plantilla ya guardada (desde la galería). Persiste y refleja el nombre en
  // cualquier pestaña atada a ella.
  const renombrarPlantilla = useMutation({
    mutationFn: ({ id, nombre }: { id: string; nombre: string }) =>
      api.actualizarPlantillaDiseno(id, { nombre }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      setPestanas((p) => p.map((t) => (t.plantillaId === res.plantilla.id ? { ...t, nombre: res.plantilla.nombre } : t)));
      toast.success("Nombre actualizado.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo renombrar."),
  });

  // Confirma la edición inline del nombre de una pestaña: actualiza el título local y, si la
  // pestaña está atada a una plantilla, persiste el nuevo nombre en la galería.
  const confirmarRenombrarTab = () => {
    if (!editTab) return;
    const nombre = editTab.valor.trim();
    const t = pestanas.find((x) => x.id === editTab.id);
    if (nombre && t) {
      setPestanas((p) => p.map((x) => (x.id === editTab.id ? { ...x, nombre } : x)));
      if (t.plantillaId) renombrarPlantilla.mutate({ id: t.plantillaId, nombre });
    }
    setEditTab(null);
  };

  // Guarda el documento en la PUBLICACIÓN anclada (render + versión + fija su imagen).
  const guardarEnPieza = useMutation({
    mutationFn: () => {
      if (!storeActivo || !pestanaActiva?.contenido || !pestanaActiva?.plataforma) {
        throw new Error("Esta pestaña no está anclada a una publicación.");
      }
      return api.imagenPiezaGuardar(
        pestanaActiva.contenido,
        pestanaActiva.plataforma,
        storeActivo.getState().documento,
        pestanaActiva.bindings,
      );
    },
    onSuccess: (res) => {
      if (activa) marcarLimpia(activa);
      setExportUrl(`/api/media/${res.id}`);
      toast.success(`Guardado en la pieza (v${res.version}).`);
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar en la pieza."),
  });

  const plantillas = plantillasQ.data?.plantillas ?? [];
  const guardando = guardar.isPending || guardarComo.isPending;

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] flex-col">
      {/* Título de sección (portaliza a la barra de cabecera unificada del shell). */}
      <TituloPagina titulo="Imagen" icono={Image} />
      {/* Región EDITOR (pestañas + lienzo): objetivo de PANTALLA COMPLETA, para que sus pestañas
          —y el botón para salir— sigan visibles. `bg-background` evita un fondo transparente en
          pantalla completa. */}
      <div ref={editorRef} className="flex min-h-0 flex-1 flex-col bg-background">
      {/* Pestañas (scroll horizontal) + acciones de guardado a la DERECHA, al final de la misma
          barra: guardar / guardar como / pantalla completa. El «+» (lienzo nuevo) solo aparece
          cuando ya hay alguna pestaña. */}
      {pestanas.length > 0 && (
        <div className="flex items-center border-b border-border bg-muted/30">
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-2">
            {pestanas.map((t) => {
              const marca = marcas.find((m) => m.id === t.marca)?.nombre ?? t.marca;
              return (
                <div
                  key={t.id}
                  className={`flex shrink-0 items-center gap-1 border-b-2 px-3 py-1.5 text-sm ${
                    t.id === activa ? "border-primary font-medium" : "border-transparent text-muted-foreground"
                  }`}
                >
                  {editTab?.id === t.id ? (
                    <input
                      autoFocus
                      value={editTab.valor}
                      onChange={(e) => setEditTab({ id: t.id, valor: e.target.value })}
                      onBlur={confirmarRenombrarTab}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") confirmarRenombrarTab();
                        else if (e.key === "Escape") setEditTab(null);
                      }}
                      className="max-w-[200px] rounded border border-input bg-background px-1 py-0.5 text-sm"
                    />
                  ) : (
                    <button
                      onClick={() => setActiva(t.id)}
                      onDoubleClick={() => setEditTab({ id: t.id, valor: t.nombre || "" })}
                      title="Doble-clic para renombrar"
                      className="max-w-[200px] truncate"
                    >
                      {t.nombre || marca}
                      {dirty[t.id] && <span className="ml-1 text-red-500">•</span>}
                    </button>
                  )}
                  <button onClick={() => cerrarPestana(t.id)} className="opacity-60 hover:opacity-100" title="Cerrar">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
            <button
              onClick={() => abrirPestana()}
              disabled={!marcaInicial}
              title="Nuevo lienzo en blanco"
              className="ml-1 shrink-0 rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
          {/* Acciones, al final del todo a la derecha: guardar · guardar como · pantalla completa. */}
          <div className="flex shrink-0 items-center gap-1 border-l border-border px-1.5">
            {exportUrl && (
              <a href={exportUrl} target="_blank" rel="noreferrer" className="mr-1 hidden text-sm text-primary underline sm:inline">
                Ver PNG
              </a>
            )}
            {pestanaActiva && (
              <>
                {pestanaActiva.contenido && (
                  <Button size="icon" variant="ghost" disabled={guardarEnPieza.isPending} onClick={() => guardarEnPieza.mutate()} title="Guardar en la publicación">
                    <FileUp className="h-4 w-4" />
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  disabled={guardando}
                  onClick={() => guardar.mutate()}
                  title={sucia ? "Guardar (cambios sin guardar)" : "Guardado — se autoguarda a los 3 s"}
                >
                  <span className="relative mr-1 inline-flex">
                    <Save className="h-4 w-4" />
                    {/* Estado EN el icono: punto rojo si hay cambios; check verde si está guardado. */}
                    {guardando ? (
                      <Loader2 className="absolute -right-1.5 -top-1.5 h-2.5 w-2.5 animate-spin text-muted-foreground" />
                    ) : sucia ? (
                      <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-red-500 ring-1 ring-background" />
                    ) : (
                      <Check className="absolute -right-1.5 -top-1.5 h-3 w-3 rounded-full bg-background text-emerald-500" />
                    )}
                  </span>
                  Guardar
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  disabled={guardando}
                  // En pantalla completa el diálogo (portal a body) quedaría oculto: salimos antes de abrirlo.
                  onClick={() => { if (document.fullscreenElement) void document.exitFullscreen?.(); setDialogo({ nombre: "", tipo: "foto" }); }}
                  title="Guardar como… (plantilla nueva)"
                >
                  <SaveAll className="h-4 w-4" />
                </Button>
              </>
            )}
            <Button
              size="icon"
              variant="ghost"
              onClick={alternarPantallaCompleta}
              aria-pressed={pantallaCompleta}
              title={pantallaCompleta ? "Salir de pantalla completa (Esc)" : "Pantalla completa — centrarse en la imagen"}
            >
              {pantallaCompleta ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1">
        {pestanaActiva && storeActivo ? (
          <EditorDocumento
            key={pestanaActiva.id}
            store={storeActivo}
            marca={pestanaActiva.marca}
            onExportar={() => exportar.mutate()}
            exportando={exportar.isPending}
            onPlantillas={() => setGaleria(true)}
            // «Adaptar a…»: abre el documento reencuadrado en una PESTAÑA NUEVA (no machaca la actual).
            onAbrirAdaptado={(docAdaptado, nombre) =>
              nuevaPestana(pestanaActiva.marca, docAdaptado, { nombre })
            }
            // Aviso de hueco de foto: solo relevante cuando la pestaña está atada a una plantilla
            // (sin hueco no autoguarda a servidor ni deja Guardar).
            avisaHueco={!!pestanaActiva.plantillaId}
          />
        ) : (
          <GaleriaInline
            plantillas={plantillas}
            agruparPorMarca={marcaActiva === null}
            cargando={plantillasQ.isLoading}
            onAbrir={abrirPlantilla}
            onBorrar={(p) => borrarPlantilla.mutate(p.id)}
            onDuplicar={(p) => duplicarPlantilla.mutate(p)}
            onRenombrar={(p, nombre) => renombrarPlantilla.mutate({ id: p.id, nombre })}
            onRotar={(p, rotar) => rotarPlantilla.mutate({ id: p.id, rotar })}
            onBlanco={() => abrirPestana()}
          />
        )}
      </div>
      </div>

      {/* Galería modal: aplicar una plantilla a la pestaña ACTIVA (desde el rail). */}
      {galeria && (
        <GaleriaPlantillas
          plantillas={plantillas}
          onCargar={(p) => { cargarPlantillaEnActiva(p); setGaleria(false); }}
          onBorrar={(p) => borrarPlantilla.mutate(p.id)}
          onDuplicar={(p) => duplicarPlantilla.mutate(p)}
          onRenombrar={(p, nombre) => renombrarPlantilla.mutate({ id: p.id, nombre })}
          onRotar={(p, rotar) => rotarPlantilla.mutate({ id: p.id, rotar })}
          onCerrar={() => setGaleria(false)}
        />
      )}

      {/* Diálogo «Guardar como» (nombre de plantilla nueva). */}
      <Dialog open={!!dialogo} onOpenChange={(o) => !o && setDialogo(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Guardar como plantilla</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="Nombre de la plantilla"
            value={dialogo?.nombre ?? ""}
            onChange={(e) => setDialogo((d) => (d ? { ...d, nombre: e.target.value } : d))}
            onKeyDown={(e) => { if (e.key === "Enter") confirmarNombre(); }}
          />
          {/* Selector de tipo: foto (post de imagen) o miniatura (portada de video) */}
          <div className="flex gap-2">
            {(["foto", "miniatura"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setDialogo((d) => (d ? { ...d, tipo: t } : d))}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded border px-3 py-2 text-sm transition-colors ${
                  (dialogo?.tipo ?? "foto") === t
                    ? "border-primary bg-primary/10 font-medium text-primary"
                    : "border-border text-muted-foreground hover:border-muted-foreground"
                }`}
              >
                {t === "foto" ? <Image className="h-3.5 w-3.5" /> : <Video className="h-3.5 w-3.5" />}
                {t === "foto" ? "Foto" : "Miniatura"}
              </button>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogo(null)}>Cancelar</Button>
            <Button onClick={confirmarNombre} disabled={!dialogo?.nombre.trim()}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Agrupa plantillas por marca (orden alfabético por nombre de marca). Para la vista «Todas»,
// donde conviven varias marcas: amontonarlas en una sola rejilla no aporta nada, así que se
// dividen en secciones por marca.
function agruparPlantillasPorMarca(plantillas: PlantillaDiseno[]): PlantillaDiseno[][] {
  const porMarca = new Map<string, PlantillaDiseno[]>();
  for (const p of plantillas) {
    const arr = porMarca.get(p.marca);
    if (arr) arr.push(p);
    else porMarca.set(p.marca, [p]);
  }
  return [...porMarca.values()].sort((a, b) =>
    (a[0].marca_nombre || a[0].marca).localeCompare(b[0].marca_nombre || b[0].marca),
  );
}

// Galería del estado vacío: rejilla de plantillas + tarjeta de «lienzo en blanco». Con una marca
// concreta es una sola rejilla; en «Todas» (`agruparPorMarca`) se parte en secciones por marca.
// La marca y «Plantillas» no se rotulan en el toolbar: aquí lo dicen las cabeceras de sección.
function GaleriaInline({
  plantillas,
  agruparPorMarca,
  cargando,
  onAbrir,
  onBorrar,
  onDuplicar,
  onRenombrar,
  onRotar,
  onBlanco,
}: {
  plantillas: PlantillaDiseno[];
  agruparPorMarca: boolean;
  cargando: boolean;
  onAbrir: (p: PlantillaDiseno) => void;
  onBorrar: (p: PlantillaDiseno) => void;
  onDuplicar: (p: PlantillaDiseno) => void;
  onRenombrar: (p: PlantillaDiseno, nombre: string) => void;
  onRotar: (p: PlantillaDiseno, rotar: boolean) => void;
  onBlanco: () => void;
}) {
  const [editId, setEditId] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const commit = (p: PlantillaDiseno) => {
    const n = editVal.trim();
    if (n && n !== p.nombre) onRenombrar(p, n);
    setEditId(null);
  };
  const REJILLA = "grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4";
  const tarjetaBlanco = (
    <button
      onClick={onBlanco}
      className="flex aspect-[4/5] flex-col items-center justify-center gap-1 rounded border border-dashed border-border text-xs text-muted-foreground hover:border-primary hover:text-foreground"
    >
      <Plus className="h-6 w-6" />
      Lienzo en blanco
    </button>
  );
  const tarjeta = (p: PlantillaDiseno) => (
            <div key={p.id} className="group relative">
              <button
                onClick={() => onAbrir(p)}
                title={`Abrir «${p.nombre}»`}
                className="block w-full overflow-hidden rounded border border-border bg-muted/40 hover:ring-2 hover:ring-primary"
              >
                <div className="aspect-[4/5] w-full">
                  {p.miniatura ? (
                    <img src={urlMedia(p.miniatura)} alt={p.nombre} draggable={false} className="pointer-events-none h-full w-full object-contain" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">Sin vista previa</div>
                  )}
                </div>
              </button>
              {/* Título: clic para renombrar inline (la miniatura de arriba abre la plantilla). El
                  TIPO (foto/miniatura) va en la misma fila del título, a la izquierda, como un
                  chip — ya no flota sobre la imagen. */}
              {editId === p.id ? (
                <input
                  autoFocus
                  value={editVal}
                  onChange={(e) => setEditVal(e.target.value)}
                  onBlur={() => commit(p)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commit(p);
                    else if (e.key === "Escape") setEditId(null);
                  }}
                  className="block w-full rounded border border-primary bg-background px-1.5 py-1 text-xs"
                />
              ) : (
                <div className="flex items-center gap-1.5 px-1.5 py-1">
                  {(p.tipo ?? "foto") === "miniatura" ? (
                    <span
                      title="Miniatura (portada de vídeo)"
                      className="inline-flex shrink-0 items-center gap-0.5 rounded bg-violet-100 px-1 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
                    >
                      <Video className="h-2.5 w-2.5" />Miniatura
                    </span>
                  ) : (
                    <span
                      title="Foto (post de imagen)"
                      className="inline-flex shrink-0 items-center gap-0.5 rounded bg-sky-100 px-1 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
                    >
                      <Image className="h-2.5 w-2.5" />Foto
                    </span>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditId(p.id); setEditVal(p.nombre || ""); }}
                    title="Clic para renombrar"
                    className="min-w-0 flex-1 truncate text-left text-xs text-muted-foreground hover:text-foreground"
                  >
                    {p.nombre || "(sin nombre)"}
                  </button>
                </div>
              )}
              {/* Rotación: incluir la plantilla en el grupo que rota automáticamente por la marca
                  (cada post nuevo se lleva la siguiente; necesita ≥2 marcadas). */}
              <button
                onClick={(e) => { e.stopPropagation(); onRotar(p, !p.rotar); }}
                title={p.rotar ? "En rotación: clic para sacarla del grupo" : "Clic para incluirla en la rotación de la marca"}
                className={`flex w-full items-center justify-center gap-1 px-1.5 pb-1 text-[11px] font-medium transition-colors ${
                  p.rotar ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Repeat className="h-3 w-3" />
                {p.rotar ? "En rotación" : "Rotación"}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onDuplicar(p); }}
                title="Duplicar plantilla"
                className="absolute right-8 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 hover:text-foreground group-hover:opacity-100"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onBorrar(p); }}
                title="Borrar plantilla"
                className="absolute right-1 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
  );
  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6">
      {cargando ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Cargando plantillas…</p>
      ) : agruparPorMarca ? (
        <div className="space-y-8">
          {agruparPlantillasPorMarca(plantillas).map((grupo) => (
            <section key={grupo[0].marca}>
              <h3 className="mb-2 border-b border-border pb-1 text-sm font-medium text-foreground">
                {grupo[0].marca_nombre || grupo[0].marca}
              </h3>
              <div className={REJILLA}>{grupo.map(tarjeta)}</div>
            </section>
          ))}
          {/* «Lienzo en blanco» va al FINAL de la galería (no el primero). */}
          <div className={REJILLA}>{tarjetaBlanco}</div>
        </div>
      ) : (
        <div className={REJILLA}>
          {plantillas.map(tarjeta)}
          {/* «Lienzo en blanco» va al FINAL de la lista (no el primero). */}
          {tarjetaBlanco}
        </div>
      )}
    </div>
  );
}

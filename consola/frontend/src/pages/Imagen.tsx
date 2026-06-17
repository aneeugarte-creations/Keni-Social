// Página del Editor profesional — WORKSPACE multi-marca.
//
// Cada PESTAÑA es un documento independiente (por MARCA) con su PROPIO store Zustand e historial;
// los stores persisten en un ref por id de pestaña. Todo post es 4:5 y una misma plantilla sirve
// para todas las redes (no hay dimensión ni filtro por red).
//
// SHELL (patrón Canva): el lienzo es el protagonista. TODAS las acciones del editor (estado de
// guardado, guardar, deshacer/rehacer, vista con muestra, «Más», Exportar / Guardar en pieza)
// viven ARRIBA, en la barra de cabecera unificada del shell (las portaliza EditorDocumento vía
// `AccionesPagina`). Bajo la cabecera queda UNA sola franja fina: la tira de pestañas del
// workspace. El resto del cromo va a los lados (rail/flyout izquierda, inspector derecha).
//
// PLANTILLAS por marca: «Guardar» actualiza la plantilla a la que está atada la pestaña (sin pedir
// nombre); «Guardar como…» (menú Más) crea una nueva. El estado de guardado se lee como TEXTO
// («Guardado / Guardando… / Sin guardar») en la cabecera. Sin pestañas se ve la GALERÍA de
// plantillas de la marca (o lienzo en blanco si no hay).
//
// El workspace SOBREVIVE a un reload: la lista de pestañas (marca/nombre/plantillaId/pieza +
// activa) se persiste en sessionStorage y se reabre al montar; el contenido sale de los borradores
// de autoguardado local (claveAuto) o del servidor.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Image, Plus, Save, SaveAll, Video, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { TituloPagina } from "@/components/layout/encabezado";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { PublicacionPlantillas } from "@/editor/GaleriaPlantillas";
import { DialogoFotoMuestra } from "@/editor/DialogoFotoMuestra";
import { dataUrlAArchivo } from "@/editor/dataUrl";
import { conFotoEnHuecosVacios, conTextosHorneados, documentoVacio, type Documento } from "@/editor/documento";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, urlMedia, type PlantillaDiseno } from "@/lib/api";
import {
  categoriasPresentes,
  construirCatalogosEtiquetas,
  normalizarCategoria,
  opcionesCategoria,
} from "@/lib/categoriasPlantilla";
import { prepararDocumento } from "@/lib/placa/docPieza";

type TipoPlantilla = "foto" | "miniatura";

// Muestra de una plantilla para el OVERVIEW de la galería (no entra al documento): foto + texto.
type MuestraVals = { foto?: string; titular?: string; etiqueta?: string };

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

// Momento (epoch ms) en que se escribió el borrador local, o 0 si no hay registro. Se escribe
// junto al borrador (clave hermana `:ts`) para poder compararlo con `actualizado` del servidor.
function leerAutoTs(clave: string): number {
  try {
    return Number(sessionStorage.getItem(`${clave}:ts`)) || 0;
  } catch {
    return 0;
  }
}

function borrarAuto(clave: string) {
  try {
    sessionStorage.removeItem(clave);
    sessionStorage.removeItem(`${clave}:ts`);
  } catch {
    /* almacenamiento no disponible */
  }
}

// ── Persistencia del WORKSPACE (qué pestañas hay abiertas) ──────────────────────────────────────
// Solo la FORMA del workspace (no el contenido: ese vive en los borradores por claveAuto y en el
// servidor). sessionStorage: sobrevive al reload, muere al cerrar la pestaña del navegador.

const CLAVE_WORKSPACE = "keni:editor:workspace";

interface WorkspaceGuardado {
  pestanas: Pick<Pestana, "marca" | "nombre" | "plantillaId" | "contenido" | "plataforma">[];
  activa: number; // índice de la pestaña activa
}

function leerWorkspace(): WorkspaceGuardado | null {
  try {
    const s = sessionStorage.getItem(CLAVE_WORKSPACE);
    if (!s) return null;
    const ws = JSON.parse(s) as WorkspaceGuardado;
    return Array.isArray(ws.pestanas) ? ws : null;
  } catch {
    return null;
  }
}

export default function Imagen() {
  const opciones = useQuery({
    queryKey: ["piezas", "opciones"],
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
  // Diálogo de «Guardar como» (nombre de plantilla nueva + tipo + categoría).
  const [dialogo, setDialogo] = useState<{ nombre: string; tipo: TipoPlantilla; categoria: string } | null>(null);
  // Edición inline del nombre de una pestaña (doble-clic en su título).
  const [editTab, setEditTab] = useState<{ id: string; valor: string } | null>(null);
  // Cambios sin guardar en la plantilla, por pestaña (estado «Guardado/Sin guardar» en cabecera).
  const [dirty, setDirty] = useState<Record<string, boolean>>({});

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

  // Lienzo EN BLANCO de verdad: SIEMPRE limpio y vacío. No restaura borradores previos de la marca;
  // los borradores de plantilla/pieza sí se recuperan en sus propios flujos (abrirPlantilla / abrirPiezaTab / restaurarWorkspace).
  const abrirPestana = (marcaArg?: string) => {
    // Un lienzo nuevo necesita una marca CONCRETA: si el global está en «Todas», cae a `marcaInicial`.
    const marca = marcaArg || marcaEfectiva || marcaInicial;
    if (!marca) return;
    nuevaPestana(marca);
  };

  // Abre una plantilla guardada EN UNA PESTAÑA NUEVA, atada a esa plantilla. Si hay un BORRADOR
  // LOCAL más reciente que lo guardado en servidor (p. ej. el autoguardado a la plantilla falló o
  // se cerró antes de los 3 s), recupera el borrador y deja la pestaña en «Sin guardar».
  const abrirPlantilla = (p: PlantillaDiseno) => {
    const clave = claveAuto({ id: "", marca: p.marca, plantillaId: p.id });
    const borrador = leerAuto(clave);
    const tsGuardado = p.actualizado ? Date.parse(p.actualizado) : 0;
    const usarBorrador = !!borrador && leerAutoTs(clave) > tsGuardado;
    const { id } = nuevaPestana(p.marca, usarBorrador && borrador ? borrador : (p.documento as Documento), {
      nombre: p.nombre,
      plantillaId: p.id,
    });
    if (usarBorrador) {
      setDirty((d) => ({ ...d, [id]: true }));
      toast.info(`Plantilla «${p.nombre}»: se recuperó un borrador local más reciente que lo guardado.`);
    } else {
      toast.success(`Plantilla «${p.nombre}» abierta.`);
    }
  };

  // Fija los bindings (titular/pleca real) de una pestaña ya abierta.
  const setBindings = (id: string, bindings: Record<string, string>) =>
    setPestanas((p) => p.map((t) => (t.id === id ? { ...t, bindings } : t)));

  // Abre una pestaña ANCLADA a una publicación. Devuelve el id de la pestaña creada.
  const abrirPiezaTab = async (cid: string, pid: string, marca: string): Promise<string> => {
    const { id, store } = nuevaPestana(marca, undefined, { contenido: cid, plataforma: pid });
    // Aunque restauremos un borrador local, pedimos los bindings reales (copy/pleca) para el render.
    const guardado = leerAuto(claveAuto({ id: "", marca, contenido: cid, plataforma: pid }));
    try {
      const pieza = await api.imagenPieza(cid, pid);
      setBindings(id, pieza.bindings ?? {});
      if (guardado) {
        store.getState().cargar(guardado);
        return id;
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
        return id;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo abrir la pieza.");
    }
    return id;
  };

  const qc = useQueryClient();

  const plantillasQ = useQuery({
    queryKey: ["plantillas-diseno", marcaPanel],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: marcaPanel || undefined }, signal),
    // En «Todas» (marcaPanel vacío) se listan las plantillas de todas las marcas.
    enabled: marcas.length > 0,
  });

  // Catálogo de ETIQUETAS por marca (rótulos personalizados de las categorías): rige cómo se rotulan
  // las categorías en la galería y qué etiquetas ofrece cada selector. Misma clave de marca que las
  // plantillas (en «Todas» trae las de todas las marcas).
  const etiquetasQ = useQuery({
    queryKey: ["etiquetas-plantilla", marcaPanel],
    queryFn: ({ signal }) => api.etiquetasPlantilla({ marca: marcaPanel || undefined }, signal),
    enabled: marcas.length > 0,
  });
  const catalogosEtiquetas = useMemo(() => {
    const cats = construirCatalogosEtiquetas(etiquetasQ.data?.etiquetas ?? []);
    // Garantiza una entrada por marca con AL MENOS sus categorías PRESENTES (sin depender de filas
    // guardadas): así cada marca ve solo sus etiquetas —no la lista global de deportes/noticias—
    // desde el primer renombrado. Los rótulos personalizados (de las filas) se conservan encima.
    for (const p of plantillasQ.data?.plantillas ?? []) {
      let cat = cats.get(p.marca);
      if (!cat) {
        cat = { rotulos: new Map(), slugs: new Set() };
        cats.set(p.marca, cat);
      }
      cat.slugs.add(normalizarCategoria(p.categoria));
    }
    return cats;
  }, [etiquetasQ.data, plantillasQ.data]);

  // RESTAURA el workspace guardado (tras un reload). El contenido de cada pestaña sale del
  // borrador local (claveAuto) si existe, o del servidor (plantilla/pieza). Las pestañas de
  // plantilla comparan borrador vs `actualizado`; si la plantilla ya no existe, el borrador se
  // abre como lienzo suelto (y si tampoco hay borrador, la pestaña se descarta).
  const restaurarWorkspace = async (ws: WorkspaceGuardado, piezaURL?: { cid: string; pid: string; marca: string }) => {
    const ids: (string | null)[] = [];
    const cachePlantillas = new Map<string, PlantillaDiseno[]>();
    const plantillasDe = async (marca: string): Promise<PlantillaDiseno[]> => {
      if (!cachePlantillas.has(marca)) {
        try {
          cachePlantillas.set(marca, (await api.plantillasDiseno({ marca: marca || undefined })).plantillas);
        } catch {
          cachePlantillas.set(marca, []);
        }
      }
      return cachePlantillas.get(marca) ?? [];
    };
    for (const t of ws.pestanas) {
      if (t.contenido && t.plataforma) {
        ids.push(await abrirPiezaTab(t.contenido, t.plataforma, t.marca));
        continue;
      }
      if (t.plantillaId) {
        const clave = claveAuto({ id: "", marca: t.marca, plantillaId: t.plantillaId });
        const borrador = leerAuto(clave);
        const p = (await plantillasDe(t.marca)).find((x) => x.id === t.plantillaId);
        if (p) {
          const usarBorrador = !!borrador && leerAutoTs(clave) > (p.actualizado ? Date.parse(p.actualizado) : 0);
          const { id } = nuevaPestana(t.marca, usarBorrador && borrador ? borrador : (p.documento as Documento), {
            nombre: p.nombre,
            plantillaId: p.id,
          });
          if (usarBorrador) setDirty((d) => ({ ...d, [id]: true }));
          ids.push(id);
        } else if (borrador) {
          const { id } = nuevaPestana(t.marca, borrador, { nombre: t.nombre });
          setDirty((d) => ({ ...d, [id]: true }));
          ids.push(id);
        } else {
          ids.push(null);
        }
        continue;
      }
      // Lienzo suelto: restaura su borrador local (si lo hay; si no, en blanco).
      const borrador = leerAuto(claveAuto({ id: "", marca: t.marca }));
      const { id } = nuevaPestana(t.marca, borrador ?? undefined, { nombre: t.nombre });
      if (borrador) setDirty((d) => ({ ...d, [id]: true }));
      ids.push(id);
    }
    // Pieza pedida por URL: si ya se restauró su pestaña, actívala; si no, ábrela además.
    if (piezaURL) {
      const ya = ws.pestanas.findIndex((t) => t.contenido === piezaURL.cid && t.plataforma === piezaURL.pid);
      if (ya >= 0 && ids[ya]) setActiva(ids[ya]);
      else await abrirPiezaTab(piezaURL.cid, piezaURL.pid, piezaURL.marca);
      return;
    }
    const objetivo = ids[ws.activa] ?? ids.filter(Boolean).pop() ?? null;
    if (objetivo) setActiva(objetivo);
  };

  // Apertura inicial (una vez): workspace guardado → restáuralo (sumando la pieza de la URL si
  // la hay); sin workspace, pieza por URL → ancla; si no, con plantillas deja la GALERÍA; sin
  // ninguna abre un lienzo en blanco.
  const abiertoInicial = useRef(false);
  useEffect(() => {
    if (abiertoInicial.current) return;
    const cid = searchParams.get("contenido");
    const pid = searchParams.get("plataforma");
    const marcaURL = searchParams.get("marca") || marcaInicial || "";
    const ws = leerWorkspace();
    if (ws && ws.pestanas.length > 0) {
      abiertoInicial.current = true;
      void restaurarWorkspace(ws, cid && pid ? { cid, pid, marca: marcaURL } : undefined);
      return;
    }
    if (cid && pid) {
      abiertoInicial.current = true;
      void abrirPiezaTab(cid, pid, marcaURL);
      return;
    }
    if (marcas.length === 0 || !plantillasQ.isSuccess) return;
    abiertoInicial.current = true;
    if ((plantillasQ.data?.plantillas.length ?? 0) === 0) {
      void abrirPestana(marcaInicial ?? marcas[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, marcas, plantillasQ.isSuccess, plantillasQ.data]);

  // PERSISTE la forma del workspace en cada cambio (solo tras la apertura inicial, para no
  // machacar el guardado con el estado vacío del primer render).
  useEffect(() => {
    if (!abiertoInicial.current) return;
    try {
      const ws: WorkspaceGuardado = {
        pestanas: pestanas.map(({ marca, nombre, plantillaId, contenido, plataforma }) => ({
          marca,
          nombre,
          plantillaId,
          contenido,
          plataforma,
        })),
        activa: pestanas.findIndex((t) => t.id === activa),
      };
      sessionStorage.setItem(CLAVE_WORKSPACE, JSON.stringify(ws));
    } catch {
      /* cuota llena: el workspace no se persiste, sin romper */
    }
  }, [pestanas, activa]);

  // GUARD de cierre: con CUALQUIER pestaña sucia, avisa antes de cerrar/recargar la ventana.
  const hayDirty = pestanas.some((t) => dirty[t.id]);
  useEffect(() => {
    if (!hayDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Chrome requiere returnValue para mostrar el diálogo nativo.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [hayDirty]);

  const cerrarPestana = async (id: string) => {
    // Si hay cambios sin guardar, confirmar. Las piezas/plantillas atadas autoguardan a servidor,
    // pero un lienzo suelto (sin plantilla ni pieza) solo tiene el borrador local: avisamos siempre.
    const t = pestanas.find((x) => x.id === id);
    if (!t) return;
    const sinDestino = !t.plantillaId && !t.contenido;
    if (dirty[id]) {
      const ok = await confirmar({
        titulo: "Cerrar pestaña",
        mensaje: sinDestino
          ? "Esta pestaña tiene cambios sin guardar y no está atada a ninguna plantilla. ¿Cerrar y perder el trabajo?"
          : "Esta pestaña tiene cambios sin guardar. ¿Cerrar de todos modos?",
        destructivo: true,
        textoConfirmar: "Cerrar",
      });
      if (!ok) return;
    }
    // El borrador local es crash-safety; un cierre DELIBERADO termina la sesión de edición (si se
    // dejara, reaparecería al reabrir la plantilla/pieza, incluso pisando ediciones de otros).
    borrarAuto(claveAuto(t));
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

  // Al editar: marca "sin guardar", autoguarda local (crash-safety, ~0.8 s) y, si la pestaña está
  // atada a una plantilla, AUTOGUARDA en la plantilla tras 3 s de inactividad (estilo Word).
  //
  // La suscripción depende SOLO de `activa`: renombrar una pestaña o fijar bindings (cambios de
  // `pestanas`) ya NO re-suscriben ni cancelan los timers pendientes (antes la última edición
  // podía quedarse sin autoguardar). La pestaña vigente se lee de un ref EN EL MOMENTO de guardar
  // (así un «Guardar como» que ata la plantilla a mitad de sesión usa la clave/plantilla nuevas).
  // Al limpiar (cambio de pestaña o desmontaje) se hace FLUSH de lo pendiente.
  const pestanasRef = useRef(pestanas);
  pestanasRef.current = pestanas;
  useEffect(() => {
    if (!activa) return;
    const id = activa;
    const store = stores.current.get(id);
    if (!store) return;
    let tSession: number | undefined;
    let tAuto: number | undefined;
    let docPendiente: Documento | null = null; // último documento aún no volcado al borrador local
    let autoPendiente = false; // hay un autoguardado a plantilla programado y sin ejecutar

    const volcarLocal = () => {
      if (!docPendiente) return;
      const p = pestanasRef.current.find((t) => t.id === id);
      if (!p) return;
      const clave = claveAuto(p);
      try {
        sessionStorage.setItem(clave, JSON.stringify(docPendiente));
        sessionStorage.setItem(`${clave}:ts`, String(Date.now()));
      } catch {
        /* cuota llena: el trabajo sigue en memoria */
      }
      docPendiente = null;
    };

    const guardarEnPlantilla = async () => {
      autoPendiente = false;
      const p = pestanasRef.current.find((t) => t.id === id);
      if (!p?.plantillaId) return; // sin plantilla atada no hay dónde guardar (usa «Guardar como»)
      const st = stores.current.get(id);
      if (!st) return;
      const doc = st.getState().documento;
      // Sin hueco de foto explícito el server rechaza; no spameamos 400s (el Guardar manual avisa).
      if (!doc.capas.some((c) => c.tipo === "imagen" && c.es_foto)) return;
      try {
        // Solo el documento (sin re-render de miniatura, para no cargar el server cada 3 s; la
        // miniatura se refresca al Guardar manual).
        await api.actualizarPlantillaDiseno(p.plantillaId, { documento: doc });
        // Solo marcar limpio si no se editó MIENTRAS guardaba (igualdad por referencia).
        if (stores.current.get(id)?.getState().documento === doc) {
          setDirty((d) => ({ ...d, [id]: false }));
        }
        qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      } catch {
        /* falló el autoguardado: el estado «Sin guardar» permanece */
      }
    };

    const unsub = store.subscribe((estado, previo) => {
      if (estado.documento === previo.documento) return;
      setDirty((d) => ({ ...d, [id]: true }));
      // Borrador local.
      docPendiente = estado.documento;
      window.clearTimeout(tSession);
      tSession = window.setTimeout(volcarLocal, 800);
      // Autoguardado a la plantilla tras 3 s sin tocar nada.
      window.clearTimeout(tAuto);
      autoPendiente = true;
      tAuto = window.setTimeout(() => void guardarEnPlantilla(), 3000);
    });
    return () => {
      unsub();
      window.clearTimeout(tSession);
      window.clearTimeout(tAuto);
      // FLUSH: lo pendiente se guarda YA (borrador local síncrono; plantilla en segundo plano).
      volcarLocal();
      if (autoPendiente) void guardarEnPlantilla();
    };
  }, [activa, qc]);

  // Genera la miniatura (render best-effort) del documento con la MUESTRA de la galería horneada:
  //  - foto: la `foto_muestra` en los huecos `es_foto` vacíos (sin ella, grises).
  //  - titular (`copy_in`): el texto de muestra o "TITULAR" (sin esto saldría vacío: sale del binding).
  //  - subtítulo/pleca (`etiqueta_default`): el texto de muestra si lo hay; si no, se REVELA el literal
  //    de la capa (el binding llega vacío en el overview y el render omitiría la capa).
  // El documento editable NO se toca (solo esta copia).
  const miniaturaDe = async (documento: Documento, m: MuestraVals = {}): Promise<string> => {
    let doc = m.foto ? conFotoEnHuecosVacios(documento, m.foto) : documento;
    if (!m.etiqueta) doc = conTextosHorneados(doc, (c) => (c.binding === "etiqueta_default" ? c.texto : null));
    try {
      return (await api.imagenRender(doc, { copy_in: m.titular || "TITULAR", etiqueta_default: m.etiqueta || "" })).id;
    } catch {
      return "";
    }
  };

  // Muestra ACTUAL de una plantilla (de la caché de la query): foto + titular + subtítulo.
  const muestraActualDe = (plantillaId: string): MuestraVals => {
    const p = plantillasQ.data?.plantillas.find((x) => x.id === plantillaId);
    return { foto: p?.foto_muestra || "", titular: p?.titular_muestra || "", etiqueta: p?.etiqueta_muestra || "" };
  };

  // GUARDAR: si la pestaña ya está atada a una plantilla, la sobrescribe (sin pedir nombre);
  // si no, abre «Guardar como».
  const guardar = useMutation({
    mutationFn: async () => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      if (!pestanaActiva.plantillaId) throw new Error("__sin_plantilla__");
      const documento = storeActivo.getState().documento;
      if (!documento.capas.some((c) => c.tipo === "imagen" && c.es_foto)) throw new Error("__sin_hueco__");
      // Hornea la muestra ya asignada a la plantilla (foto + texto) para que la miniatura no la pierda
      // al re-guardar el diseño.
      const miniatura = await miniaturaDe(documento, muestraActualDe(pestanaActiva.plantillaId));
      return api.actualizarPlantillaDiseno(pestanaActiva.plantillaId, { documento, miniatura });
    },
    onSuccess: () => {
      if (activa) marcarLimpia(activa);
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla guardada.");
    },
    onError: (e: unknown) => {
      if (e instanceof Error && e.message === "__sin_plantilla__") {
        setDialogo({ nombre: pestanaActiva?.nombre ?? "", tipo: "foto", categoria: "" });
        return;
      }
      if (e instanceof Error && e.message === "__sin_hueco__") {
        toast.error("Marca una imagen como «hueco de foto» antes de guardar.");
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo guardar.");
    },
  });

  // GUARDAR COMO: crea una plantilla nueva con nombre, tipo y categoría; ata la pestaña a ella.
  // La categoría es texto libre (el backend la normaliza a slug); vacía cae a "general".
  const guardarComo = useMutation({
    mutationFn: async ({ nombre, tipo, categoria }: { nombre: string; tipo: TipoPlantilla; categoria: string }) => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      const documento = storeActivo.getState().documento;
      if (!documento.capas.some((c) => c.tipo === "imagen" && c.es_foto)) throw new Error("__sin_hueco__");
      const miniatura = await miniaturaDe(documento);
      return api.crearPlantillaDiseno({
        marca: pestanaActiva.marca,
        nombre,
        categoria: categoria.trim() || undefined,
        tipo,
        documento,
        miniatura,
      });
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
    guardarComo.mutate({ nombre, tipo: dialogo?.tipo ?? "foto", categoria: dialogo?.categoria ?? "" });
    setDialogo(null);
  };

  // ── FOTO DE MUESTRA por plantilla (galería «tal cual quedaría») ──────────────────────────────────
  // Plantilla cuyo diálogo de muestra está abierto (puerta de GALERÍA), o null.
  const [muestraDe, setMuestraDe] = useState<PlantillaDiseno | null>(null);

  // Sube la foto elegida (dataURL subida o URL pegada) al almacén y devuelve su objeto; "" la limpia.
  // La foto subida llega como dataURL: se decodifica a File SIN `fetch` (la CSP `connect-src 'self'`
  // bloquea `fetch('data:…')` → "Failed to fetch"). La URL externa la descarga el back (`mediaDesdeUrl`).
  const subirMuestra = async (src: string): Promise<string> => {
    if (!src) return "";
    if (src.startsWith("data:")) {
      return (await api.subirMedia(dataUrlAArchivo(src, "muestra"), "plantillas")).id;
    }
    return (await api.mediaDesdeUrl(src)).id;
  };

  // PUERTA COMPARTIDA (galería + fotón del editor): fija la MUESTRA de una plantilla (foto + texto) y
  // regenera su miniatura horneada. `foto`: null = no se tocó (conserva la actual); string = nueva
  // ("" la quita). `titular`/`etiqueta`: texto de muestra ("" = fallback). `documento` es el que se
  // hornea (el de la plantilla en galería; el del lienzo en el editor). El documento editable NO se toca.
  const fijarMuestra = useMutation({
    mutationFn: async ({ plantillaId, documento, foto, titular, etiqueta }: {
      plantillaId: string;
      documento: Documento;
      foto: string | null;
      titular: string;
      etiqueta: string;
    }) => {
      const objeto = foto === null ? muestraActualDe(plantillaId).foto || "" : await subirMuestra(foto);
      const miniatura = await miniaturaDe(documento, { foto: objeto, titular, etiqueta });
      return api.actualizarPlantillaDiseno(plantillaId, {
        foto_muestra: objeto,
        titular_muestra: titular,
        etiqueta_muestra: etiqueta,
        // Si el render falla ("") conservamos la miniatura anterior en vez de borrarla.
        ...(miniatura ? { miniatura } : {}),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      setMuestraDe(null);
      toast.success("Muestra actualizada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo fijar la muestra."),
  });

  // Carga una plantilla en la pestaña ACTIVA (la ata a ella). REEMPLAZA el documento y resetea el
  // historial: si hay cambios sin guardar, confirmar antes para no perder el trabajo.
  const cargarPlantillaEnActiva = async (p: PlantillaDiseno) => {
    if (!storeActivo || !activa) return;
    if (dirty[activa]) {
      const ok = await confirmar({
        titulo: "Reemplazar contenido",
        mensaje: `Esto reemplaza el contenido actual (con cambios sin guardar) por «${p.nombre}». ¿Continuar?`,
        destructivo: true,
        textoConfirmar: "Reemplazar",
      });
      if (!ok) return;
    }
    storeActivo.getState().cargar(p.documento as Documento);
    bindPlantilla(activa, p.id, p.nombre);
    marcarLimpia(activa);
    toast.success(`Plantilla «${p.nombre}» cargada.`);
  };

  const borrarPlantilla = useMutation({
    mutationFn: (id: string) => api.borrarPlantillaDiseno(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla borrada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo borrar."),
  });

  // Borrado SIEMPRE con confirmación (mismo patrón que el resto de la app: `confirmar()` propio,
  // destructivo, texto «Borrar»). Vale para la galería inline y para la modal.
  const pedirBorrarPlantilla = async (p: PlantillaDiseno) => {
    const ok = await confirmar({
      titulo: "Borrar plantilla",
      mensaje: `¿Borrar la plantilla «${p.nombre || "sin nombre"}»? Esta acción no se puede deshacer.`,
      destructivo: true,
      textoConfirmar: "Borrar",
    });
    if (ok) borrarPlantilla.mutate(p.id);
  };

  // DUPLICAR: crea una copia de la plantilla ya guardada en la galería (para «remixes» sin empezar
  // de cero). Aparece al instante al invalidar la query.
  const duplicarPlantilla = useMutation({
    mutationFn: (p: PlantillaDiseno) =>
      api.crearPlantillaDiseno({
        marca: p.marca,
        nombre: `Copia de ${p.nombre || "plantilla"}`,
        categoria: p.categoria || undefined,
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

  // REORDENAR: orden MANUAL de la galería (drag-and-drop). Update OPTIMISTA (la rejilla se recoloca
  // al instante) + persistencia (POST) + invalidación. `ids` es la lista COMPLETA de la marca en su
  // nuevo orden. En error, revierte al orden previo.
  const reordenarPlantillas = useMutation({
    mutationFn: (ids: string[]) => api.reordenarPlantillasDiseno(ids),
    onMutate: async (ids: string[]) => {
      await qc.cancelQueries({ queryKey: ["plantillas-diseno"] });
      const clave = ["plantillas-diseno", marcaPanel];
      const previo = qc.getQueryData<{ plantillas: PlantillaDiseno[] }>(clave);
      if (previo) {
        const pos = new Map(ids.map((id, i) => [id, i]));
        const reordenadas = [...previo.plantillas].sort(
          (a, b) => (pos.get(a.id) ?? Infinity) - (pos.get(b.id) ?? Infinity),
        );
        qc.setQueryData(clave, { ...previo, plantillas: reordenadas });
      }
      return { clave, previo };
    },
    onError: (e: unknown, _ids, ctx) => {
      if (ctx?.previo) qc.setQueryData(ctx.clave, ctx.previo);
      toast.error(e instanceof Error ? e.message : "No se pudo reordenar.");
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ["plantillas-diseno"] }),
  });

  // CATEGORIZAR: cambia la categoría de una plantilla ya guardada (badge-selector de la galería).
  const categorizarPlantilla = useMutation({
    mutationFn: ({ id, categoria }: { id: string; categoria: string }) =>
      api.actualizarPlantillaDiseno(id, { categoria }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Categoría actualizada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo cambiar la categoría."),
  });

  // RENOMBRAR el RÓTULO de una etiqueta de la marca (catálogo editable): cambia solo el texto visible
  // (no mueve plantillas: el slug es la identidad). Persiste el override por `(marca, slug)`.
  const renombrarEtiqueta = useMutation({
    mutationFn: ({ marca, slug, etiqueta }: { marca: string; slug: string; etiqueta: string }) =>
      api.guardarEtiquetaPlantilla(marca, slug, etiqueta),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["etiquetas-plantilla"] });
      toast.success("Etiqueta renombrada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo renombrar la etiqueta."),
  });

  // CREAR una etiqueta: persiste su rótulo (preserva acentos/mayúsculas) Y la asigna a la plantilla
  // desde cuyo selector se creó. El slug se deriva del texto igual que en el backend.
  const crearEtiqueta = useMutation({
    mutationFn: async ({ p, etiqueta }: { p: PlantillaDiseno; etiqueta: string }) => {
      const slug = normalizarCategoria(etiqueta);
      await api.guardarEtiquetaPlantilla(p.marca, slug, etiqueta);
      await api.actualizarPlantillaDiseno(p.id, { categoria: slug });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["etiquetas-plantilla"] });
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Etiqueta creada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo crear la etiqueta."),
  });

  // BORRAR el rótulo personalizado de una etiqueta (no toca plantillas). El backend devuelve 409 si
  // alguna plantilla aún usa esa categoría (el mensaje, con el conteo, va al toast).
  const borrarEtiqueta = useMutation({
    mutationFn: ({ marca, slug }: { marca: string; slug: string }) =>
      api.borrarEtiquetaPlantilla(marca, slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["etiquetas-plantilla"] });
      toast.success("Etiqueta eliminada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo eliminar la etiqueta."),
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

  // Guarda el documento en la PUBLICACIÓN anclada (render + versión + fija su imagen). El PNG
  // resultante se ofrece en el toast (acción «Ver PNG»).
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
      toast.success(`Guardado en la pieza (v${res.version}).`, {
        action: { label: "Ver PNG", onClick: () => window.open(urlMedia(res.id), "_blank", "noopener") },
      });
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar en la pieza."),
  });

  const plantillas = useMemo(() => plantillasQ.data?.plantillas ?? [], [plantillasQ.data]);
  const guardando = guardar.isPending || guardarComo.isPending || guardarEnPieza.isPending;

  // Sugerencias de categoría del diálogo «Guardar como»: las etiquetas de la marca de la pieza (su
  // catálogo + las presentes), no la lista global, para que cada marca vea solo las suyas.
  const opcionesEtiquetaDialogo = useMemo(
    () =>
      opcionesCategoria(
        categoriasPresentes(plantillas),
        null,
        catalogosEtiquetas.get(pestanaActiva?.marca || marcaPanel || marcaInicial),
      ),
    [plantillas, catalogosEtiquetas, pestanaActiva?.marca, marcaPanel, marcaInicial],
  );

  return (
    // FULL-BLEED: anula el padding del `<main>` del shell para que el lienzo aproveche todo el
    // alto/ancho bajo la cabecera (h-12 = 3rem). Entre cabecera y lienzo solo queda la tira de
    // pestañas (única franja fina).
    <div className="-mx-4 -mt-2 -mb-4 flex h-[calc(100dvh-3rem)] flex-col overflow-hidden sm:-mx-6 sm:-mb-6 lg:-mx-8">
      {/* Título de sección (portaliza a la barra de cabecera unificada del shell). */}
      <TituloPagina titulo="Imagen" icono={Image} />

      {/* TIRA DE PESTAÑAS: única franja entre cabecera y lienzo. Solo pestañas + «+»; las
          acciones del editor viven arriba, en la cabecera (las portaliza EditorDocumento). */}
      {pestanas.length > 0 && (
        <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-muted px-2 py-1">
          {pestanas.map((t) => {
            const marca = marcas.find((m) => m.id === t.marca)?.nombre ?? t.marca;
            return (
              // Pestañas estilo navegador (Chrome): la activa se distingue por una superficie
              // CLARA que flota sobre el gris de la barra (fondo `--card` + sombra + esquinas
              // redondeadas), no por un subrayado. Las inactivas se funden con la barra y solo
              // toman fondo al pasar el ratón.
              <div
                key={t.id}
                className={`flex shrink-0 items-center gap-1 rounded-md px-3 py-1 text-sm transition-colors ${
                  t.id === activa
                    ? "bg-card font-medium text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
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
                <button onClick={() => void cerrarPestana(t.id)} className="opacity-60 hover:opacity-100" title="Cerrar">
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
      )}

      <div className="min-h-0 flex-1">
        {pestanaActiva && storeActivo ? (
          <EditorDocumento
            key={pestanaActiva.id}
            store={storeActivo}
            marca={pestanaActiva.marca}
            // EXPORTAR: el diálogo lee el documento del store y descarga con formato/calidad/escala.
            // Pieza anclada → titular/pleca REAL (bindings) y el botón pasa a secundario (la acción
            // primaria es «Guardar en pieza»); plantilla suelta → texto de muestra y Exportar primario.
            exportar={{
              bindings: pestanaActiva.contenido ? pestanaActiva.bindings : undefined,
              nombre: pestanaActiva.nombre,
              primario: !pestanaActiva.contenido,
            }}
            // TODA la barra del editor se portaliza a la cabecera unificada del shell.
            accionesEnCabecera
            accionesInicio={
              <>
                {/* Estado de guardado LEGIBLE (texto, no glifos montados sobre un icono).
                    «Sin guardar» avisa en ámbar vía `--aviso-texto-plano`: amber-600/400 de
                    siempre fuera del editor, y ámbar-100 claro dentro de la barra naranja
                    (el amber-600 sobre el degradado era casi invisible). */}
                <span
                  aria-live="polite"
                  className={`hidden whitespace-nowrap text-sm md:inline ${
                    !guardando && sucia ? "text-[hsl(var(--aviso-texto-plano))]" : "text-muted-foreground"
                  }`}
                >
                  {guardando ? "Guardando…" : sucia ? "Sin guardar" : "Guardado"}
                </span>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  disabled={guardando}
                  onClick={() => guardar.mutate()}
                  title={
                    pestanaActiva.plantillaId
                      ? sucia
                        ? "Guardar la plantilla (hay cambios sin guardar)"
                        : "Guardado"
                      : "Guardar como plantilla…"
                  }
                >
                  <Save className="h-4 w-4" />
                </Button>
              </>
            }
            accionesFin={
              pestanaActiva.contenido ? (
                <Button
                  size="sm"
                  // Misma caja que las píldoras etiquetadas de la barra (marca, Adaptar):
                  // h-8 px-2.5 text-sm, gap interno icono-texto 1.5 único (sin mr-* en el icono).
                  className="h-8 gap-1.5 px-2.5 text-sm"
                  disabled={guardarEnPieza.isPending}
                  onClick={() => guardarEnPieza.mutate()}
                  title="Guardar en la publicación (render + nueva versión)"
                >
                  <FileUp className="h-4 w-4" />
                  <span className="hidden sm:inline">Guardar en pieza</span>
                </Button>
              ) : undefined
            }
            menuExtra={
              <button
                onClick={() => setDialogo({ nombre: "", tipo: "foto", categoria: "" })}
                disabled={guardando}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-40"
              >
                <SaveAll className="h-4 w-4 text-muted-foreground" /> Guardar como plantilla…
              </button>
            }
            // Panel «Diseño» del rail (galería de plantillas como COLUMNA estilo Canva, no modal):
            // aplicar una plantilla a la pestaña activa + gestión (renombrar/duplicar/borrar/rotar).
            panelDiseno={
              <PublicacionPlantillas
                compacto
                plantillas={plantillas}
                onCargar={(p) => void cargarPlantillaEnActiva(p)}
                onBorrar={(p) => void pedirBorrarPlantilla(p)}
                onDuplicar={(p) => duplicarPlantilla.mutate(p)}
                onRenombrar={(p, nombre) => renombrarPlantilla.mutate({ id: p.id, nombre })}
                onRotar={(p, rotar) => rotarPlantilla.mutate({ id: p.id, rotar })}
                onCategorizar={(p, categoria) => categorizarPlantilla.mutate({ id: p.id, categoria })}
                catalogos={catalogosEtiquetas}
                onRenombrarEtiqueta={(p, slug, etiqueta) => renombrarEtiqueta.mutate({ marca: p.marca, slug, etiqueta })}
                onCrearEtiqueta={(p, etiqueta) => crearEtiqueta.mutate({ p, etiqueta })}
                onBorrarEtiqueta={(p, slug) => borrarEtiqueta.mutate({ marca: p.marca, slug })}
                onFotoMuestra={(p) => setMuestraDe(p)}
                onReordenar={(ids) => reordenarPlantillas.mutate(ids)}
              />
            }
            // «Adaptar a…»: abre el documento reencuadrado en una PESTAÑA NUEVA (no machaca la actual).
            onAbrirAdaptado={(docAdaptado, nombre) =>
              nuevaPestana(pestanaActiva.marca, docAdaptado, { nombre })
            }
            // Aviso de hueco de foto: solo relevante cuando la pestaña está atada a una plantilla
            // (sin hueco no autoguarda a servidor ni deja Guardar).
            avisaHueco={!!pestanaActiva.plantillaId}
            // PUERTA EDITOR de la foto de muestra: solo si la pestaña edita una plantilla. El fotón
            // de «Vista con muestra» persiste la FOTO que se sube/pega como muestra de ESA plantilla
            // (el texto de muestra se conserva: se edita desde el ⋮ de la galería).
            onFotoMuestra={
              pestanaActiva.plantillaId
                ? (src) => {
                    const plantillaId = pestanaActiva.plantillaId;
                    if (plantillaId) {
                      const cur = muestraActualDe(plantillaId);
                      fijarMuestra.mutate({
                        plantillaId,
                        documento: storeActivo.getState().documento,
                        foto: src,
                        titular: cur.titular || "",
                        etiqueta: cur.etiqueta || "",
                      });
                    }
                  }
                : undefined
            }
          />
        ) : (
          // GALERÍA del estado vacío (sin pestañas): el MISMO `PublicacionPlantillas` del rail y de
          // la modal, a página completa (una sola fuente de verdad): ocupa TODO el ancho (sin
          // `max-w` centrado: los lados ya no quedan vacíos), con más columnas en pantallas grandes,
          // gestión completa, agrupación por marca en «Todas» y «Lienzo en blanco» al final.
          <div className="h-full">
            {plantillasQ.isLoading ? (
              <p className="py-8 text-center text-sm text-muted-foreground">Cargando plantillas…</p>
            ) : (
              <PublicacionPlantillas
                plantillas={plantillas}
                agruparPorMarca={marcaActiva === null}
                onCargar={abrirPlantilla}
                onBorrar={(p) => void pedirBorrarPlantilla(p)}
                onDuplicar={(p) => duplicarPlantilla.mutate(p)}
                onRenombrar={(p, nombre) => renombrarPlantilla.mutate({ id: p.id, nombre })}
                onRotar={(p, rotar) => rotarPlantilla.mutate({ id: p.id, rotar })}
                onCategorizar={(p, categoria) => categorizarPlantilla.mutate({ id: p.id, categoria })}
                catalogos={catalogosEtiquetas}
                onRenombrarEtiqueta={(p, slug, etiqueta) => renombrarEtiqueta.mutate({ marca: p.marca, slug, etiqueta })}
                onCrearEtiqueta={(p, etiqueta) => crearEtiqueta.mutate({ p, etiqueta })}
                onBorrarEtiqueta={(p, slug) => borrarEtiqueta.mutate({ marca: p.marca, slug })}
                onFotoMuestra={(p) => setMuestraDe(p)}
                onReordenar={(ids) => reordenarPlantillas.mutate(ids)}
                onLienzoBlanco={() => abrirPestana()}
              />
            )}
          </div>
        )}
      </div>

      {/* Diálogo de MUESTRA (puerta de galería): foto + texto de la plantilla, sin abrir el editor.
          `key` reinicia el estado al cambiar de plantilla. */}
      {muestraDe && (
        <DialogoFotoMuestra
          key={muestraDe.id}
          plantilla={muestraDe}
          aplicando={fijarMuestra.isPending}
          onCerrar={() => setMuestraDe(null)}
          onAplicar={({ foto, titular, etiqueta }) =>
            fijarMuestra.mutate({
              plantillaId: muestraDe.id,
              documento: muestraDe.documento as Documento,
              foto,
              titular,
              etiqueta,
            })
          }
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
          {/* Categoría: combobox del catálogo (datalist) + texto libre. Vacía cae a «General». */}
          <div className="space-y-1">
            <label htmlFor="plantilla-categoria" className="text-xs text-muted-foreground">
              Categoría (opcional)
            </label>
            <Input
              id="plantilla-categoria"
              list="categorias-plantilla"
              placeholder="Última hora, Marcador…"
              value={dialogo?.categoria ?? ""}
              onChange={(e) => setDialogo((d) => (d ? { ...d, categoria: e.target.value } : d))}
              onKeyDown={(e) => { if (e.key === "Enter") confirmarNombre(); }}
            />
            <datalist id="categorias-plantilla">
              {opcionesEtiquetaDialogo.map((c) => (
                <option key={c.slug} value={c.etiqueta} />
              ))}
            </datalist>
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

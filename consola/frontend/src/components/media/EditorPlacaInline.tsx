/**
 * Editor de imagen INLINE: un `<canvas>` que compone la PLANTILLA DEL ESTUDIO de la pieza EN EL
 * NAVEGADOR, con el MISMO motor que el servidor (`dibujarDocumento`), en vivo. Sistema ÚNICO de
 * plantillas (la placa de marca legacy se migró a una plantilla del estudio más).
 *
 *  - La plantilla (documento de capas) se renderiza con UNA foto por HUECO DE FOTO (`es_foto`): un
 *    COLLAGE puede tener N huecos. Cada hueco lleva su propia foto (media id) y su reencuadre.
 *  - Cabecera: quitar plantilla (publicar solo la foto cruda) · elegir plantilla del estudio.
 *  - Interacción POR HUECO: clic en un hueco lo selecciona y abre su origen de foto; arrastrar
 *    dentro de un hueco reencuadra ESE hueco; el zoom y "Centrar" actúan sobre el hueco activo.
 *  - Titular: clic para reescribir in place. Contador "Faltan X de N fotos" bajo el lienzo.
 *  - Origen de la FOTO (por hueco): Subir · Texto · IA · Usar imagen original.
 *  - El canvas es SOLO previa en vivo: al guardar NO se hornea ningún PNG. La pieza guarda su
 *    RECETA (fotos + copy_in + plantilla) y la imagen publicable se renderiza on-demand en el
 *    servidor (`/api/publicaciones/{id}/compuesta`).
 */
import { useMutation } from "@tanstack/react-query";
import { Crop, ImagePlus, LayoutTemplate, Library, Loader2, Move, Slash, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorArtes } from "@/components/media/SelectorArtes";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { CapaImagen, CapaTexto, Documento } from "@/editor/documento";
import { useGeneracion } from "@/hooks/use-generacion";
import { ApiError, api, mensajeError, urlMedia } from "@/lib/api";
import { dibujarDocumento } from "@/lib/placa/dibujar.mjs";
import {
  capasFotoDoc,
  capaTitularDoc,
  type FotoCollage,
  mediaIdsDe,
  prepararDocumento,
} from "@/lib/placa/docPieza";
import { ENCUADRE_DEFECTO, normalizarEncuadre } from "@/lib/placa/encuadre";
import { cargarFuentesPlaca } from "@/lib/placa/fuentes";
import { familiaRealDe } from "@/lib/placa/render";
import type { Arte } from "@/types";

/** Lienzo por defecto del post de foto (4:5) cuando no hay plantilla (foto cruda). */
const LIENZO_4_5 = { w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 };

/**
 * Caja (en px de lienzo) que ocupa la capa del titular, para situar el editor in place encima.
 * Modo CAJA (la capa trae `h>0`): la caja es ESA, fija e inamovible (`[y, y+h]`); el render
 * encoge el texto para caber. Modo LEGADO (`h<=0`, plantillas antiguas sin alto): se estima por
 * nº de líneas × interlineado, y con `ancla:"abajo"` el bloque crece hacia arriba desde `y`.
 */
function cajaTitularLienzo(c: CapaTexto): { x: number; y: number; w: number; h: number } {
  if (c.h > 0) return { x: c.x, y: c.y, w: c.w, h: c.h };
  const interlineado = c.interlineado || 1.14;
  const maxLineas = Math.max(1, c.auto_ajuste?.max_lineas ?? 2);
  const h = Math.round(c.tamano * interlineado * maxLineas);
  return { x: c.x, y: c.ancla === "abajo" ? c.y - h : c.y, w: c.w, h };
}

/** Familias (reales) que usa un documento, para precargar solo esas fuentes. */
function familiasDeDocumento(doc: Documento): string[] {
  const fr = familiaRealDe(doc.fuentes);
  const reales = new Set<string>([doc.fuentes.sans, doc.fuentes.condensada]);
  for (const c of doc.capas) {
    if (c.tipo === "texto") reales.add(fr(c.familia));
    else if (c.tipo === "logo" && c.tipo_logo === "wordmark") reales.add(fr(c.wordmark.familia));
  }
  return [...reales].filter(Boolean);
}

/** Carga una URL como `HTMLImageElement` (o null si falla/está vacía). */
function cargarImagen(url: string | null): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

export interface EditorPlacaInlineProps {
  marca: string;
  /** Plantilla del estudio elegida (documento de capas). `null` = sin plantilla = foto cruda. */
  documento: Documento | null;
  /** Titular en vivo (texto DENTRO de la imagen / copy-in de la pieza). */
  copyIn: string;
  /** Edita el titular: el copy-in es clicable y reescribible IN PLACE sobre la plantilla. */
  onCopyInCambio?: (valor: string) => void;
  /** Copy de la pieza (contenido del post): se usa como SUGERENCIA del prompt al generar con IA. */
  copy?: string;
  /** Una foto por HUECO (collage), en orden de `capas`. `fotos[i]` va al hueco `es_foto` i. */
  fotos: FotoCollage[];
  /** Notifica un cambio en el array de fotos (foto/reencuadre de algún hueco). */
  onFotosCambio: (fotos: FotoCollage[]) => void;
  /** URL de la imagen original (RSS de marca propia), si la pieza la trae. */
  imagenFuente?: string;
  /** "Sin plantilla": publicar solo la foto cruda (sin la plantilla encima). */
  sinPlantilla: boolean;
  /** Alterna "sin plantilla" (icono de plantilla tachada). */
  onAlternarSinPlantilla: () => void;
  /** Abre la galería de plantillas del estudio (selector nativo en la cabecera). */
  onAbrirGaleria?: () => void;
}

export function EditorPlacaInline({
  marca,
  documento,
  copyIn,
  onCopyInCambio,
  copy = "",
  fotos,
  onFotosCambio,
  imagenFuente,
  sinPlantilla,
  onAlternarSinPlantilla,
  onAbrirGaleria,
}: EditorPlacaInlineProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [galeriaAbierta, setGaleriaAbierta] = React.useState(false);
  // Opciones de ORIGEN de la foto (Texto / Subir / Generar con IA): se abren al TOCAR un hueco
  // (fuera del titular), no como bloque permanente en el panel de edición. El origen elegido se
  // escribe en el HUECO ACTIVO (`slotActivo`).
  const [fuenteAbierta, setFuenteAbierta] = React.useState(false);
  const [prompt, setPrompt] = React.useState("");
  const [avisoGenerar, setAvisoGenerar] = React.useState("");
  const [fuentesListas, setFuentesListas] = React.useState(false);
  // Hueco seleccionado del collage (índice en `capasFotoDoc`/`fotos`). Default 0 (el único, legado).
  const [slotActivo, setSlotActivo] = React.useState(0);

  // ¿Hay plantilla activa? (documento presente y NO en modo "solo foto").
  const activo = !sinPlantilla && !!documento;
  const lienzo = activo && documento ? documento.formato : LIENZO_4_5;

  // Huecos de foto del diseño (en orden). Sin plantilla: un único hueco virtual (la foto cruda).
  const huecos = React.useMemo<CapaImagen[]>(
    () => (activo && documento ? capasFotoDoc(documento) : []),
    [activo, documento],
  );
  const nHuecos = Math.max(1, huecos.length);

  // El hueco activo nunca debe quedar fuera de rango (cambio de plantilla con menos huecos).
  React.useEffect(() => {
    if (slotActivo > nHuecos - 1) setSlotActivo(0);
  }, [slotActivo, nHuecos]);

  // Foto del hueco activo (o un hueco vacío por defecto si aún no existe en el array).
  const fotoActiva = fotos[slotActivo] ?? { objeto: "", foco: null, zoom: 0 };
  // Reencuadre vigente del hueco activo. `foco:null` = el humano no lo tocó (se respeta el diseño):
  // para DIBUJAR/ARRASTRAR usamos el por defecto, pero solo persistimos foco cuando hay arrastre.
  const encActivo = {
    foco: fotoActiva.foco ?? ENCUADRE_DEFECTO.foco,
    zoom: fotoActiva.zoom && fotoActiva.zoom > 0 ? fotoActiva.zoom : ENCUADRE_DEFECTO.zoom,
  };
  const encRef = React.useRef(encActivo);
  encRef.current = encActivo;

  // Escribe (parcheando) el hueco `i` del array de fotos y notifica al padre. Rellena huecos
  // intermedios vacíos si el array es más corto que el índice (no debería pasar, pero es seguro).
  const fotosRef = React.useRef(fotos);
  fotosRef.current = fotos;
  const cambiarHueco = React.useCallback(
    (i: number, parche: Partial<FotoCollage>) => {
      const base = fotosRef.current.slice();
      while (base.length <= i) base.push({ objeto: "", foco: null, zoom: 0 });
      base[i] = { ...base[i], ...parche };
      onFotosCambio(base);
    },
    [onFotosCambio],
  );
  // Cambia la FOTO (media id) del hueco activo. Al cambiar la imagen, reseteamos su reencuadre.
  const cambiarFotoActiva = React.useCallback(
    (id: string) => {
      cambiarHueco(slotActivo, { objeto: id, foco: null, zoom: 0 });
      setFuenteAbierta(false);
    },
    [cambiarHueco, slotActivo],
  );

  // Edición IN PLACE del titular: la capa de texto del copy-in (si la plantilla la tiene).
  const capaTitular = activo && documento ? capaTitularDoc(documento) : null;
  const [editandoTitular, setEditandoTitular] = React.useState(false);
  const [cajaTitular, setCajaTitular] = React.useState<
    { left: number; top: number; width: number; height: number } | null
  >(null);
  const titularEditable = !!capaTitular && !!onCopyInCambio;

  // Precarga de fuentes del documento (sin ellas el ajuste de líneas no cuadra). Sin plantilla,
  // no hay texto que dibujar: listo de inmediato.
  React.useEffect(() => {
    if (!activo || !documento) {
      setFuentesListas(true);
      return;
    }
    let vivo = true;
    setFuentesListas(false);
    void cargarFuentesPlaca(familiasDeDocumento(documento)).then(() => {
      if (vivo) setFuentesListas(true);
    });
    return () => {
      vivo = false;
    };
  }, [activo, documento]);

  // Imágenes del documento (logos, fondos, fotos de muestra de otras capas) por media id.
  const [assets, setAssets] = React.useState<Record<string, HTMLImageElement | null>>({});
  React.useEffect(() => {
    if (!activo || !documento) {
      setAssets({});
      return;
    }
    let vivo = true;
    const ids = mediaIdsDe(documento);
    void Promise.all(
      ids.map((id) => cargarImagen(urlMedia(id)).then((img) => [id, img] as const)),
    ).then((pares) => {
      if (vivo) setAssets(Object.fromEntries(pares));
    });
    return () => {
      vivo = false;
    };
  }, [activo, documento]);

  // Fotos de la pieza POR HUECO (mapa media_id -> imagen). Cargamos cada `objeto` no vacío. El
  // hueco 0 sin foto cae a la imagen original (respaldo legado) si la pieza la trae.
  const respaldoHueco0 = !fotos[0]?.objeto && imagenFuente ? imagenFuente : "";
  const idsFotos = React.useMemo(() => {
    const set = new Set<string>();
    for (const f of fotos) if (f.objeto) set.add(f.objeto);
    return [...set];
  }, [fotos]);
  // Clave estable por CONTENIDO del set de ids: el reencuadre crea un `fotos` nuevo en cada tick de
  // arrastre, pero el SET de ids no cambia; así no recargamos las imágenes en cada `pointermove`,
  // solo cuando se asigna/quita una foto (el set cambia).
  const claveFotos = idsFotos.join("|");
  const [mapaFotos, setMapaFotos] = React.useState<Record<string, HTMLImageElement | null>>({});
  React.useEffect(() => {
    let vivo = true;
    const ids = claveFotos ? claveFotos.split("|") : [];
    void Promise.all(
      ids.map((id) => cargarImagen(urlMedia(id)).then((img) => [id, img] as const)),
    ).then((pares) => {
      if (vivo) setMapaFotos(Object.fromEntries(pares));
    });
    return () => {
      vivo = false;
    };
  }, [claveFotos]);
  // Imagen del respaldo (original) para el hueco 0 cuando aún no tiene foto propia.
  const [imgRespaldo, setImgRespaldo] = React.useState<HTMLImageElement | null>(null);
  React.useEffect(() => {
    let vivo = true;
    void cargarImagen(respaldoHueco0 || null).then((img) => {
      if (vivo) setImgRespaldo(img);
    });
    return () => {
      vivo = false;
    };
  }, [respaldoHueco0]);

  // Imagen efectiva de un hueco i (su foto cargada, o el respaldo si es el hueco 0 sin foto).
  const imagenDeHueco = React.useCallback(
    (i: number): HTMLImageElement | null => {
      const obj = fotosRef.current[i]?.objeto;
      if (obj) return mapaFotos[obj] ?? null;
      if (i === 0) return imgRespaldo;
      return null;
    },
    [mapaFotos, imgRespaldo],
  );

  // --- Render en vivo (debounced) --- //
  const render = React.useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { w, h } = lienzo;
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    if (activo && documento) {
      const doc = prepararDocumento(documento, { fotos });
      // Mapa de imágenes para el motor: assets del doc + una entrada por foto de hueco + respaldo
      // del hueco 0 (su `objeto` real va vacío, así que el motor lo pintaría vacío; lo inyectamos
      // bajo la clave que `prepararDocumento` dejó en el hueco 0).
      const imgs: Record<string, HTMLImageElement | null> = { ...assets, ...mapaFotos };
      if (respaldoHueco0 && imgRespaldo) {
        const hueco0 = capasFotoDoc(doc)[0];
        if (hueco0) {
          hueco0.objeto = "__respaldo0__";
          imgs["__respaldo0__"] = imgRespaldo;
        }
      }
      dibujarDocumento(ctx, {
        documento: doc,
        imgs,
        // Mientras se edita el titular in place, el canvas NO lo dibuja: lo muestra el overlay.
        bindings: { copy_in: editandoTitular ? "" : copyIn, etiqueta_default: "" },
        familiaReal: familiaRealDe(documento.fuentes),
      });
    } else {
      // Sin plantilla: solo la foto cruda del hueco 0 (cover con su reencuadre) o un fondo neutro.
      ctx.fillStyle = "#111315";
      ctx.fillRect(0, 0, w, h);
      const img = imagenDeHueco(0);
      const enc0 = {
        foco: fotos[0]?.foco ?? ENCUADRE_DEFECTO.foco,
        zoom: fotos[0]?.zoom && fotos[0].zoom > 0 ? fotos[0].zoom : 1,
      };
      if (img) {
        const esc = Math.max(w / img.width, h / img.height) * enc0.zoom;
        const dw = img.width * esc;
        const dh = img.height * esc;
        ctx.drawImage(img, (w - dw) * enc0.foco[0], (h - dh) * enc0.foco[1], dw, dh);
      }
    }
  }, [
    activo,
    documento,
    lienzo,
    assets,
    mapaFotos,
    respaldoHueco0,
    imgRespaldo,
    imagenDeHueco,
    fotos,
    copyIn,
    editandoTitular,
  ]);

  React.useEffect(() => {
    if (!fuentesListas) return;
    const t = setTimeout(render, 120);
    return () => clearTimeout(t);
  }, [render, fuentesListas]);

  // --- Origen de la FOTO (escribe en el hueco activo) --- //
  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (d) => cambiarFotoActiva(d.id),
    onError: (e) => toast.error(mensajeError(e)),
  });
  const usarOriginal = useMutation({
    mutationFn: () => {
      if (!imagenFuente) throw new Error("Sin imagen original.");
      return api.mediaDesdeUrl(imagenFuente);
    },
    onSuccess: (d) => {
      cambiarFotoActiva(d.id);
      toast.success("Imagen original cargada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const { generacion: genIA, ejecutando: generandoIA, iniciar: iniciarIA } = useGeneracion();
  const generar = useMutation({
    mutationFn: () => api.generarMedia({ prompt: prompt.trim() }),
    onSuccess: (d) => {
      setAvisoGenerar("");
      iniciarIA(d.generacion);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        setAvisoGenerar(e.message);
        return;
      }
      toast.error(mensajeError(e));
    },
  });
  const iaTerminal = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!genIA || genIA.id === iaTerminal.current) return;
    if (genIA.estado === "completado") {
      iaTerminal.current = genIA.id;
      const r = genIA.resultado;
      if (r?.id) {
        setPrompt("");
        cambiarFotoActiva(r.id);
      }
    } else if (genIA.estado === "error") {
      iaTerminal.current = genIA.id;
      toast.error(genIA.error || "No se pudo generar la imagen.");
    }
  }, [genIA, cambiarFotoActiva]);

  // --- Reencuadre manual: arrastrar para encuadrar + zoom dentro del HUECO activo --- //
  // Caja (en px de lienzo) de un hueco i: su rect en el diseño, o el lienzo entero sin plantilla.
  const cajaDelHueco = React.useCallback(
    (i: number): { x: number; y: number; w: number; h: number } => {
      const hueco = huecos[i];
      if (hueco) return { x: hueco.x, y: hueco.y, w: hueco.w, h: hueco.h };
      return { x: 0, y: 0, w: lienzo.w, h: lienzo.h };
    },
    [huecos, lienzo],
  );
  // ¿Qué hueco contiene el punto (cx,cy) en coords de lienzo? Si varios solapan, gana el de MENOR
  // área (el más específico para el clic). Devuelve su índice, o -1 si ninguno lo contiene.
  const huecoEnPunto = React.useCallback(
    (cx: number, cy: number): number => {
      let mejor = -1;
      let mejorArea = Infinity;
      huecos.forEach((c, i) => {
        if (cx >= c.x && cx <= c.x + c.w && cy >= c.y && cy <= c.y + c.h) {
          const area = c.w * c.h;
          if (area < mejorArea) {
            mejorArea = area;
            mejor = i;
          }
        }
      });
      return mejor;
    },
    [huecos],
  );

  const arrastre = React.useRef<{ x: number; y: number } | null>(null);
  const slotArrastre = React.useRef(0); // hueco que se está reencuadrando con el arrastre en curso
  const inicioPunt = React.useRef<{ x: number; y: number } | null>(null);
  const arrastrado = React.useRef(false); // ¿hubo movimiento real? (distingue arrastre de clic)

  // Punto del puntero en coords de lienzo.
  function puntoLienzo(e: React.PointerEvent<HTMLCanvasElement>): { cx: number; cy: number } | null {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    return {
      cx: ((e.clientX - rect.left) / rect.width) * lienzo.w,
      cy: ((e.clientY - rect.top) / rect.height) * lienzo.h,
    };
  }

  function onPointerDownFoto(e: React.PointerEvent<HTMLCanvasElement>) {
    if (editandoTitular) return;
    inicioPunt.current = { x: e.clientX, y: e.clientY };
    arrastrado.current = false;
    // Determina QUÉ hueco contiene el punto y lo selecciona; el arrastre reencuadra ESE hueco.
    const p = puntoLienzo(e);
    const i = p ? (activo ? huecoEnPunto(p.cx, p.cy) : 0) : -1;
    const slot = i >= 0 ? i : -1;
    // Sin plantilla siempre hay hueco 0; con plantilla solo si el clic cayó en un hueco.
    const idx = activo ? slot : 0;
    if (idx >= 0) {
      setSlotActivo(idx);
      slotArrastre.current = idx;
      if (imagenDeHueco(idx)) {
        arrastre.current = { x: e.clientX, y: e.clientY };
        e.currentTarget.setPointerCapture(e.pointerId);
      }
    }
  }
  function onPointerMoveFoto(e: React.PointerEvent<HTMLCanvasElement>) {
    const inicio = inicioPunt.current;
    if (inicio && Math.hypot(e.clientX - inicio.x, e.clientY - inicio.y) > 4) {
      arrastrado.current = true;
    }
    const ancla = arrastre.current;
    const canvas = canvasRef.current;
    const slot = slotArrastre.current;
    const img = imagenDeHueco(slot);
    if (!ancla || !img || !canvas) return;
    const caja = cajaDelHueco(slot);
    if (!caja.w) return;
    const rect = canvas.getBoundingClientRect();
    const escalaCss = rect.width ? canvas.width / rect.width : 1; // px de lienzo por px de pantalla
    // Reencuadre actual del HUECO que se arrastra (no necesariamente el activo si cambió el render).
    const fotoSlot = fotosRef.current[slot];
    const actual = {
      foco: fotoSlot?.foco ?? ENCUADRE_DEFECTO.foco,
      zoom: fotoSlot?.zoom && fotoSlot.zoom > 0 ? fotoSlot.zoom : 1,
    };
    const esc = Math.max(caja.w / img.width, caja.h / img.height) * actual.zoom;
    const sobranteX = img.width * esc - caja.w;
    const sobranteY = img.height * esc - caja.h;
    const dxLienzo = (e.clientX - ancla.x) * escalaCss;
    const dyLienzo = (e.clientY - ancla.y) * escalaCss;
    // Arrastrar la foto a la derecha muestra su parte izquierda → el foco DISMINUYE.
    const dFx = sobranteX > 0 ? -dxLienzo / sobranteX : 0;
    const dFy = sobranteY > 0 ? -dyLienzo / sobranteY : 0;
    arrastre.current = { x: e.clientX, y: e.clientY };
    const n = normalizarEncuadre({
      foco: [actual.foco[0] + dFx, actual.foco[1] + dFy],
      zoom: actual.zoom,
    });
    cambiarHueco(slot, { foco: n.foco, zoom: n.zoom });
  }
  function onPointerUpFoto(e: React.PointerEvent<HTMLCanvasElement>) {
    const fueArrastre = arrastrado.current;
    arrastre.current = null;
    inicioPunt.current = null;
    arrastrado.current = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* el puntero pudo soltarse fuera del canvas */
    }
    // Solo nos interesa un CLIC (sin arrastre): el arrastre era reencuadre.
    if (editandoTitular || fueArrastre) return;
    const p = puntoLienzo(e);
    if (!p) return;
    // Clic sobre la caja del TITULAR -> reescribir el copy-in in place.
    if (titularEditable && capaTitular) {
      const box = cajaTitularLienzo(capaTitular);
      if (p.cx >= box.x && p.cx <= box.x + box.w && p.cy >= box.y && p.cy <= box.y + box.h) {
        setEditandoTitular(true);
        return;
      }
    }
    // Clic en un HUECO -> seleccionarlo y abrir su origen de foto (Texto/Subir/IA). Sin
    // plantilla siempre es el hueco 0; con plantilla, solo si el clic cayó dentro de un hueco.
    const i = activo ? huecoEnPunto(p.cx, p.cy) : 0;
    if (i >= 0) {
      setSlotActivo(i);
      abrirFuente();
    }
  }
  function onZoom(valor: number) {
    const n = normalizarEncuadre({ foco: encRef.current.foco, zoom: valor });
    cambiarHueco(slotActivo, { foco: n.foco, zoom: n.zoom });
  }

  // Caja en pantalla (px CSS) de la capa del titular, para posicionar el editor in place encima.
  const recalcularCajaTitular = React.useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !capaTitular) {
      setCajaTitular(null);
      return;
    }
    const sx = canvas.clientWidth / lienzo.w;
    const sy = canvas.clientHeight / lienzo.h;
    const box = cajaTitularLienzo(capaTitular);
    setCajaTitular({ left: box.x * sx, top: box.y * sy, width: box.w * sx, height: box.h * sy });
  }, [capaTitular, lienzo]);

  React.useEffect(() => {
    if (!editandoTitular) return;
    recalcularCajaTitular();
    window.addEventListener("resize", recalcularCajaTitular);
    return () => window.removeEventListener("resize", recalcularCajaTitular);
  }, [editandoTitular, recalcularCajaTitular]);

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subir.mutate(archivo);
    if (inputRef.current) inputRef.current.value = "";
  }
  function elegirArte(arte: Arte) {
    cambiarFotoActiva(arte.objeto);
  }

  // Abre las opciones de origen de la foto y SIEMBRA el prompt de IA con el copy del post (o el
  // titular), como sugerencia editable, si el prompt está vacío.
  function abrirFuente() {
    setPrompt((p) => (p.trim() ? p : (copy || copyIn || "").trim()));
    setFuenteAbierta(true);
  }

  const ocupado = subir.isPending || generar.isPending || generandoIA || usarOriginal.isPending;
  // ¿El hueco activo tiene foto cargada? (controla la barra de reencuadre).
  const hayFotoActiva = !!imagenDeHueco(slotActivo);
  // Contador de huecos sin foto (sobre el nº de huecos del diseño).
  const huecosLlenos = React.useMemo(
    () =>
      Array.from({ length: nHuecos }, (_, i) => i).filter((i) => !!fotos[i]?.objeto || (i === 0 && !!respaldoHueco0))
        .length,
    [nHuecos, fotos, respaldoHueco0],
  );
  const faltan = nHuecos - huecosLlenos;
  const esCollage = nHuecos > 1;

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <ImagePlus className="h-4 w-4 text-muted-foreground" />
          Imagen
          {sinPlantilla && <span className="font-normal text-muted-foreground">· solo foto</span>}
        </span>
        {/* Selector nativo de plantilla: quitar plantilla (publicar solo la foto) · elegir plantilla
            del estudio (galería por marca). Todo es 4:5, así que la plantilla la dicta la MARCA. */}
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant={sinPlantilla ? "secondary" : "outline"}
            size="icon"
            className="h-7 w-7"
            onClick={onAlternarSinPlantilla}
            title={
              sinPlantilla
                ? "Solo foto (sin plantilla). Toca para volver a aplicar la plantilla"
                : "Quitar la plantilla: publicar solo la foto, sin nada encima"
            }
            aria-pressed={sinPlantilla}
          >
            <span className="relative inline-flex">
              <LayoutTemplate className="h-3.5 w-3.5" />
              <Slash className="absolute inset-0 h-3.5 w-3.5 text-destructive" />
            </span>
          </Button>
          {onAbrirGaleria && (
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={onAbrirGaleria}
              title="Elegir una plantilla del estudio (por marca)"
            >
              <LayoutTemplate className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Lienzo en vivo: resolución real, escalado por CSS. Arrastrable para reencuadrar el hueco
          tocado; el titular es clicable y reescribible in place. */}
      <div className="flex justify-center rounded-md border border-border bg-muted/20 p-2">
        {!fuentesListas ? (
          <div className="flex h-56 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="relative">
            <canvas
              ref={canvasRef}
              className="max-h-[22rem] w-auto rounded-md"
              style={{
                aspectRatio: `${lienzo.w} / ${lienzo.h}`,
                cursor: hayFotoActiva ? "move" : "pointer",
                touchAction: "none",
              }}
              onPointerDown={onPointerDownFoto}
              onPointerMove={onPointerMoveFoto}
              onPointerUp={onPointerUpFoto}
              onPointerCancel={onPointerUpFoto}
            />
            {editandoTitular && cajaTitular && (
              <textarea
                autoFocus
                value={copyIn}
                onChange={(e) => onCopyInCambio?.(e.target.value)}
                onBlur={() => setEditandoTitular(false)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault();
                    setEditandoTitular(false);
                  }
                }}
                placeholder="Escribe el titular…"
                className="absolute resize-none overflow-hidden rounded-sm bg-black/55 p-1 text-center font-bold uppercase leading-tight text-white shadow-lg outline-none ring-2 ring-primary placeholder:text-white/60"
                style={{
                  left: cajaTitular.left,
                  top: cajaTitular.top,
                  width: cajaTitular.width,
                  height: cajaTitular.height,
                  fontSize: Math.max(11, cajaTitular.height * 0.16),
                }}
              />
            )}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {esCollage
            ? "Toca un hueco para elegir su foto · arrástralo para encuadrarlo."
            : titularEditable
              ? "Toca el titular para reescribirlo · toca la imagen para cambiar la foto."
              : "Toca la imagen para añadir o cambiar la foto (texto, subir o generar con IA)."}
        </p>
        {/* Contador "Faltan X de N fotos" (solo útil en collage de varios huecos). */}
        {esCollage && (
          <span
            className={
              faltan > 0
                ? "shrink-0 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-300"
                : "shrink-0 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300"
            }
          >
            {faltan > 0 ? `Faltan ${faltan} de ${nHuecos} fotos` : `${nHuecos} de ${nHuecos} fotos`}
          </span>
        )}
      </div>

      {/* Reencuadre: arrastra la foto del hueco activo + zoom. Solo si ese hueco tiene foto. */}
      {hayFotoActiva && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          {esCollage && (
            <span className="font-medium text-foreground">
              Hueco {slotActivo + 1} de {nHuecos}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <Move className="h-3.5 w-3.5" />
            Arrastra la foto para encuadrarla
          </span>
          <span className="flex flex-1 items-center gap-2">
            <Crop className="h-3.5 w-3.5 shrink-0" />
            <input
              type="range"
              min={1}
              max={3}
              step={0.02}
              value={encActivo.zoom}
              onChange={(e) => onZoom(Number(e.target.value))}
              aria-label="Zoom de la foto"
              className="h-1.5 w-full min-w-[6rem] max-w-[16rem] cursor-pointer accent-primary"
            />
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            disabled={
              encActivo.foco[0] === 0.5 && encActivo.foco[1] === 0.5 && encActivo.zoom === 1
            }
            onClick={() => cambiarHueco(slotActivo, { foco: [0.5, 0.5], zoom: 1 })}
          >
            Centrar
          </Button>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={onArchivo}
        className="hidden"
        aria-label="Adjuntar imagen"
      />

      {/* Origen de la foto: se abre al TOCAR un hueco (no es un bloque fijo del panel). Escribe en
          el HUECO ACTIVO. */}
      <Dialog open={fuenteAbierta} onOpenChange={setFuenteAbierta}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {esCollage ? `Foto del hueco ${slotActivo + 1} de ${nHuecos}` : "Imagen de la pieza"}
            </DialogTitle>
            <DialogDescription>
              Elígela de la galería, súbela o genérala con IA.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {imagenFuente && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => usarOriginal.mutate()}
                  disabled={ocupado}
                >
                  {usarOriginal.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ImagePlus className="h-4 w-4" />
                  )}
                  Usar imagen original
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setFuenteAbierta(false);
                  setGaleriaAbierta(true);
                }}
                disabled={ocupado}
              >
                <Library className="h-4 w-4" />
                Texto
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => inputRef.current?.click()}
                disabled={ocupado}
              >
                {subir.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                Subir
              </Button>
            </div>
            <div className="space-y-1.5">
              <span className="text-xs text-muted-foreground">
                o genera con IA (sugerencia: el copy del post):
              </span>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Describe la imagen: p. ej. estadio iluminado al atardecer…"
                  disabled={ocupado}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && prompt.trim() && !ocupado) {
                      e.preventDefault();
                      generar.mutate();
                    }
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  onClick={() => generar.mutate()}
                  disabled={ocupado || prompt.trim().length === 0}
                  className="shrink-0"
                >
                  {generandoIA ? <Loader2 className="h-4 w-4 animate-spin" /> : <MarcaIA costo />}
                  {generandoIA ? "Generando…" : "Generar con IA"}
                </Button>
              </div>
            </div>
            {avisoGenerar && (
              <p className="rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-300">
                {avisoGenerar}
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <SelectorArtes
        open={galeriaAbierta}
        onCerrar={() => setGaleriaAbierta(false)}
        onSeleccionar={elegirArte}
        marca={marca}
      />
    </div>
  );
}

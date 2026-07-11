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
 *    servidor (`/api/piezas/{id}/compuesta`).
 *
 * Composición: la cabecera (`CabeceraPlaca`), la barra de reencuadre (`BarraReencuadre`) y el
 * diálogo de origen de la foto (`DialogoFuenteFoto`) viven en `components/media/placa/`; los
 * helpers puros y los tipos en `placa/lib.ts` y `placa/tipos.ts`.
 */
import { useMutation } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { AvisoAutorizarStock } from "@/components/media/AvisoAutorizarStock";
import { BuscadorStock } from "@/components/media/BuscadorStock";
import { BuscadorBiblioteca } from "@/components/media/biblioteca/BuscadorBiblioteca";
import { BadgeStock } from "@/components/media/OverlaySinLicencia";
import { SelectorArtes } from "@/components/media/SelectorArtes";
import { BarraReencuadre } from "@/components/media/placa/BarraReencuadre";
import { CabeceraPlaca } from "@/components/media/placa/CabeceraPlaca";
import { DialogoFuenteFoto } from "@/components/media/placa/DialogoFuenteFoto";
import { LienzoPlaca } from "@/components/media/placa/LienzoPlaca";
import type { OrigenImagenPropio } from "@/components/media/EditorImagen";
import {
  cajaTitularLienzo,
  familiasDeDocumento,
  origenFondoPropio,
} from "@/components/media/placa/lib";
import { LIENZO_4_5, type EditorPlacaInlineProps } from "@/components/media/placa/tipos";
import { useImagenesPlaca } from "@/components/media/placa/useImagenesPlaca";
import type { CapaImagen } from "@/editor/documento";
import { useGeneracion } from "@/hooks/use-generacion";
import { ApiError, api, mensajeError } from "@/lib/api";
import { descargarBlob, ofrecerCopiarCopy, slugNombre } from "@/lib/descargas";
import { dibujarDocumento } from "@/lib/placa/dibujar.mjs";
import {
  capasFotoDoc,
  capaTitularDoc,
  type FotoCollage,
  prepararDocumento,
} from "@/lib/placa/docPieza";
import { ENCUADRE_DEFECTO, normalizarEncuadre } from "@/lib/placa/encuadre";
import { cargarFuentesPlaca } from "@/lib/placa/fuentes";
import { familiaRealDe } from "@/lib/placa/render";
import {
  etiquetaOverlayStock,
  keywordBusqueda,
  mensajeBloqueoStock,
  nombreProveedor,
  stockAutorizado,
  stockNoAutorizado,
  tituloAutorizarStock,
} from "@/lib/stock";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { Arte } from "@/types";

export type { EditorPlacaInlineProps } from "@/components/media/placa/tipos";

export function EditorPlacaInline({
  marca,
  piezaId,
  documento,
  copyIn,
  onCopyInCambio,
  copy = "",
  titulo,
  imagenClave,
  fotos,
  onFotosCambio,
  onOrigenPropio,
  imagenFuente,
  sinPlantilla,
  onAlternarSinPlantilla,
  onAbrirGaleria,
  stock,
  onStockCambio,
}: EditorPlacaInlineProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [galeriaAbierta, setGaleriaAbierta] = React.useState(false);
  // Buscador de fotos de stock (4ª vía de imagen del hueco activo).
  const [buscadorStock, setBuscadorStock] = React.useState(false);
  // Buscador de fotos LICENCIADAS de agencia (AFP) para el hueco activo: publicables con crédito.
  const [buscadorAgencias, setBuscadorAgencias] = React.useState(false);
  // Buscador de fotos PROPIAS (galería local del equipo vía el túnel keni-fotos), por marca.
  const [buscadorPropio, setBuscadorPropio] = React.useState(false);
  // Buscador de la BIBLIOTECA (catálogo de medios del equipo: portal/subidas/fotografías).
  const [buscadorBiblioteca, setBuscadorBiblioteca] = React.useState(false);
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
  // Slot objetivo para trabajos en progreso (subida, IA). Capturado en el momento de iniciar
  // el trabajo para evitar condiciones de carrera si el usuario cambia de hueco mientras genera.
  const slotEnProgreso = React.useRef(slotActivo);

  // Cambia la FOTO (media id) del hueco activo. Al cambiar la imagen, reseteamos su reencuadre.
  const cambiarFotoActiva = React.useCallback(
    (id: string) => {
      cambiarHueco(slotActivo, { objeto: id, foco: null, zoom: 0 });
      setFuenteAbierta(false);
    },
    [cambiarHueco, slotActivo],
  );

  // Declara hacia el padre el origen PROPIO de un REEMPLAZO del FONDO (hueco 0): subir/galería/IA
  // limpian el metadato de licencia heredado. Un hueco secundario del collage no porta esa metadata
  // (`origenFondoPropio` devuelve null), así que no declara nada (preserva un fondo de stock).
  const declararFondoPropio = React.useCallback(
    (slot: number, origen: OrigenImagenPropio) => {
      const declarar = origenFondoPropio(slot, origen);
      if (declarar) onOrigenPropio?.(declarar);
    },
    [onOrigenPropio],
  );

  // Estado de stock de la pieza: condiciona el tratamiento "SIN LICENCIA" y el bloqueo de publicar.
  const sinLicencia = !!stock && stockNoAutorizado(stock);
  const autorizada = !!stock && stockAutorizado(stock);
  const proveedor = nombreProveedor(stock?.imagen_proveedor);

  // Autorizar / revocar la foto de stock (decisión HUMANA de derechos). Autorizar limpia
  // `falta_imagen` en el back y retira el overlay; revocar vuelve a bloquearla.
  const autorizarStock = useMutation({
    mutationFn: (autorizar: boolean) => {
      if (!piezaId) throw new Error("Sin pieza");
      return api.autorizarStock({ pieza_id: piezaId, autorizar });
    },
    onSuccess: (res, autorizar) => {
      onStockCambio?.(res.plataforma);
      toast.success(autorizar ? "Imagen autorizada para publicar." : "Autorización retirada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const onAutorizar = async () => {
    if (autorizada) {
      autorizarStock.mutate(false);
      return;
    }
    const ok = await confirmar({
      titulo: tituloAutorizarStock({
        licencia: stock?.imagen_licencia,
        proveedor: stock?.imagen_proveedor,
      }),
      mensaje: (
        <AvisoAutorizarStock
          proveedor={stock?.imagen_proveedor}
          licencia={stock?.imagen_licencia}
          autor={stock?.imagen_autor}
        />
      ),
      textoConfirmar: "Autorizar",
    });
    if (ok) autorizarStock.mutate(true);
  };

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

  // El hueco 0 sin foto cae a la imagen original (respaldo legado) si la pieza la trae.
  const respaldoHueco0 = !fotos[0]?.objeto && imagenFuente ? imagenFuente : "";
  // Bitmaps que necesita el render: assets del documento + foto por hueco + respaldo del hueco 0.
  const { assets, mapaFotos, imgRespaldo } = useImagenesPlaca(
    activo,
    documento,
    fotos,
    respaldoHueco0,
  );

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
          hueco0.visible = true; // hueco relleno: visible aunque la plantilla lo traiga oculto
          imgs["__respaldo0__"] = imgRespaldo;
        }
      }
      dibujarDocumento(ctx, {
        documento: doc,
        imgs,
        // Mientras se edita el titular in place, el canvas NO lo dibuja: lo muestra el overlay.
        bindings: { copy_in: editandoTitular ? "" : copyIn, etiqueta_default: "" },
        familiaReal: familiaRealDe(documento.fuentes),
        final: true,
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
    let rafId: number | null = null;
    const scheduleRender = () => {
      if (rafId === null) {
        rafId = requestAnimationFrame(() => {
          render();
          rafId = null;
        });
      }
    };
    scheduleRender();
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [render, fuentesListas]);

  // --- Origen de la FOTO (escribe en el hueco activo) --- //
  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (d) => {
      cambiarHueco(slotEnProgreso.current, { objeto: d.id, foco: null, zoom: 0 });
      declararFondoPropio(slotEnProgreso.current, "subida");
      setFuenteAbierta(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const { generacion: genIA, ejecutando: generandoIA, iniciar: iniciarIA } = useGeneracion();
  // Handler para iniciar generación con IA: captura el slot activo en este momento.
  const iniciarGeneracion = React.useCallback(() => {
    slotEnProgreso.current = slotActivo;
    generar.mutate();
  }, [slotActivo]);

  const generar = useMutation({
    mutationFn: () => api.generarMedia({ prompt: prompt.trim(), pieza_id: piezaId }),
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
        cambiarHueco(slotEnProgreso.current, { objeto: r.id, foco: null, zoom: 0 });
        declararFondoPropio(slotEnProgreso.current, "ia");
        setFuenteAbierta(false);
      }
    } else if (genIA.estado === "error") {
      iaTerminal.current = genIA.id;
      toast.error(genIA.error || "No se pudo generar la imagen.");
    }
  }, [genIA, cambiarHueco, declararFondoPropio]);

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
    if (archivo) {
      slotEnProgreso.current = slotActivo;
      subir.mutate(archivo);
    }
    if (inputRef.current) inputRef.current.value = "";
  }
  function elegirArte(arte: Arte) {
    // `cambiarFotoActiva` escribe en el hueco activo; un arte de la galería es foto PROPIA.
    cambiarFotoActiva(arte.objeto);
    declararFondoPropio(slotActivo, "galeria");
  }

  // Abre las opciones de origen de la foto y SIEMBRA el prompt de IA con el copy del post (o el
  // titular), como sugerencia editable, si el prompt está vacío.
  function abrirFuente() {
    setPrompt((p) => (p.trim() ? p : (copy || copyIn || "").trim()));
    setFuenteAbierta(true);
  }

  const ocupado = subir.isPending || generar.isPending || generandoIA;
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

  // Descarga del render COMPLETO tal cual se ve en el lienzo (foto + plantilla + texto horneado):
  // exporta el `<canvas>` a PNG (WYSIWYG, sin round-trip al servidor) y dispara la descarga. Luego
  // ofrece copiar el copy del post al portapapeles, para pegarlo donde se publique a mano (p. ej. X,
  // que Metricool no cubre). El lienzo se compone con imágenes `crossOrigin`, así que no se contamina.
  const descargar = React.useCallback(async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let blob: Blob | null = null;
    try {
      blob = await new Promise<Blob | null>((res) => canvas.toBlob((b) => res(b), "image/png"));
    } catch {
      blob = null;
    }
    if (!blob) {
      toast.error("No se pudo generar la imagen. Inténtalo de nuevo.");
      return;
    }
    descargarBlob(blob, `${slugNombre(marca)}.png`);
    toast.success("Imagen descargada.");
    await ofrecerCopiarCopy(copy);
  }, [copy, marca]);

  return (
    <div className="space-y-2.5">
      <CabeceraPlaca
        sinPlantilla={sinPlantilla}
        onAlternarSinPlantilla={onAlternarSinPlantilla}
        onAbrirGaleria={onAbrirGaleria}
        onDescargar={() => void descargar()}
      />

      {/* Stock SIN LICENCIA: bloqueo de publicar + control de autorizar (decisión humana de
          derechos). Va en el chrome del editor, NO sobre el canvas. */}
      {sinLicencia && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          <span className="flex-1 font-medium">
            {mensajeBloqueoStock({
              licencia: stock?.imagen_licencia,
              proveedor: stock?.imagen_proveedor,
            })}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="shrink-0"
            onClick={() => void onAutorizar()}
            disabled={autorizarStock.isPending}
          >
            {autorizarStock.isPending ? (
              <Spinner className="h-3.5 w-3.5" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5" />
            )}
            Autorizar
          </Button>
        </div>
      )}

      {/* Lienzo + tratamiento de stock superpuesto. El overlay "SIN LICENCIA" y el badge son DOM
          absolutos sobre el área EXACTA del canvas (NO se dibujan en el canvas), así al autorizar
          desaparecen limpio. `pointer-events-none` para no robar clics al lienzo. */}
      <LienzoPlaca
        canvasRef={canvasRef}
        lienzo={lienzo}
        fuentesListas={fuentesListas}
        hayFotoActiva={hayFotoActiva}
        onPointerDown={onPointerDownFoto}
        onPointerMove={onPointerMoveFoto}
        onPointerUp={onPointerUpFoto}
        copyIn={copyIn}
        onCopyInCambio={onCopyInCambio}
        editandoTitular={editandoTitular}
        onTerminarTitular={() => setEditandoTitular(false)}
        cajaTitular={cajaTitular}
        esCollage={esCollage}
        titularEditable={titularEditable}
        faltan={faltan}
        nHuecos={nHuecos}
        superpuesto={
          <>
            {sinLicencia && (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 flex items-center justify-center"
              >
                <span className="select-none rounded-sm bg-black/35 px-2.5 py-1 text-xs font-semibold uppercase tracking-widest text-white/90 backdrop-blur-[1px]">
                  {etiquetaOverlayStock({
                    licencia: stock?.imagen_licencia,
                    proveedor: stock?.imagen_proveedor,
                  })}
                </span>
              </div>
            )}
            {(sinLicencia || autorizada) && (
              <BadgeStock
                proveedor={proveedor}
                autorizada={autorizada}
                className="pointer-events-none absolute bottom-2 right-2"
              />
            )}
          </>
        }
      />

      {autorizada && piezaId && (
        <div className="flex items-center justify-end">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="px-2 text-muted-foreground"
            onClick={() => void onAutorizar()}
            disabled={autorizarStock.isPending}
          >
            {autorizarStock.isPending ? <Spinner className="h-3.5 w-3.5" /> : null}
            Revocar autorización
          </Button>
        </div>
      )}

      {/* Reencuadre: arrastra la foto del hueco activo + zoom. Solo si ese hueco tiene foto. */}
      {hayFotoActiva && (
        <BarraReencuadre
          esCollage={esCollage}
          slotActivo={slotActivo}
          nHuecos={nHuecos}
          encActivo={encActivo}
          onZoom={onZoom}
          onCentrar={() => cambiarHueco(slotActivo, { foco: [0.5, 0.5], zoom: 1 })}
        />
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
      <DialogoFuenteFoto
        open={fuenteAbierta}
        onOpenChange={setFuenteAbierta}
        esCollage={esCollage}
        slotActivo={slotActivo}
        nHuecos={nHuecos}
        ocupado={ocupado}
        subiendo={subir.isPending}
        generandoIA={generandoIA}
        prompt={prompt}
        onPromptCambio={setPrompt}
        avisoGenerar={avisoGenerar}
        onAbrirGaleria={() => {
          setFuenteAbierta(false);
          setGaleriaAbierta(true);
        }}
        onSubir={() => inputRef.current?.click()}
        onBuscarStock={piezaId ? () => setBuscadorStock(true) : undefined}
        onBuscarAgencias={piezaId ? () => setBuscadorAgencias(true) : undefined}
        onBuscarPropio={piezaId && marca ? () => setBuscadorPropio(true) : undefined}
        onBuscarBiblioteca={piezaId ? () => setBuscadorBiblioteca(true) : undefined}
        piezaId={piezaId}
        onAdjuntarSugerida={
          piezaId
            ? (plataforma) => {
                cambiarFotoActiva(plataforma.foto);
                onStockCambio?.(plataforma);
                setFuenteAbierta(false);
              }
            : undefined
        }
        onGenerar={iniciarGeneracion}
      />

      <SelectorArtes
        open={galeriaAbierta}
        onCerrar={() => setGaleriaAbierta(false)}
        onSeleccionar={elegirArte}
        marca={marca}
      />

      {/* Buscador de fotos de stock: al adjuntar una candidata, el back deja la pieza en stock no
          autorizado y devuelve la plataforma con la foto (media id) ya colocada en el hueco; la
          fijamos en el hueco activo del lienzo y notificamos al padre para refrescar la pieza. */}
      {piezaId && (
        <BuscadorStock
          open={buscadorStock}
          onCerrar={() => setBuscadorStock(false)}
          piezaId={piezaId}
          imagenFuente={imagenFuente}
          consultaInicial={keywordBusqueda({ imagen_clave: imagenClave, titulo })}
          onAdjuntada={(plataforma) => {
            cambiarFotoActiva(plataforma.foto);
            onStockCambio?.(plataforma);
            setBuscadorStock(false);
          }}
        />
      )}

      {/* Foto LICENCIADA de agencia (AFP): al adjuntarla el back deja la pieza publicable con su
          crédito y devuelve la plataforma con la foto colocada; la fijamos en el hueco activo. */}
      {piezaId && (
        <BuscadorStock
          open={buscadorAgencias}
          onCerrar={() => setBuscadorAgencias(false)}
          piezaId={piezaId}
          fuente="agencias"
          consultaInicial={keywordBusqueda({ imagen_clave: imagenClave, titulo })}
          onAdjuntada={(plataforma) => {
            cambiarFotoActiva(plataforma.foto);
            onStockCambio?.(plataforma);
            setBuscadorAgencias(false);
          }}
        />
      )}

      {/* Foto PROPIA de la galería local (túnel keni-fotos) que comparte a la marca de la pieza: el
          back trae el original por el túnel, deja la pieza publicable y la fijamos en el hueco activo. */}
      {piezaId && marca && (
        <BuscadorStock
          open={buscadorPropio}
          onCerrar={() => setBuscadorPropio(false)}
          piezaId={piezaId}
          fuente="propio"
          marca={marca}
          consultaInicial={keywordBusqueda({ imagen_clave: imagenClave, titulo })}
          onAdjuntada={(plataforma) => {
            cambiarFotoActiva(plataforma.foto);
            onStockCambio?.(plataforma);
            setBuscadorPropio(false);
          }}
        />
      )}

      {/* Biblioteca del equipo (catálogo de medios: portal/originales/fotografías): al adjuntar un
          item el back deja la pieza publicable y devuelve la plataforma; la fijamos en el hueco. */}
      {piezaId && (
        <BuscadorBiblioteca
          open={buscadorBiblioteca}
          onCerrar={() => setBuscadorBiblioteca(false)}
          piezaId={piezaId}
          marca={marca}
          consultaInicial={keywordBusqueda({ imagen_clave: imagenClave, titulo })}
          onAdjuntada={(plataforma) => {
            cambiarFotoActiva(plataforma.foto);
            onStockCambio?.(plataforma);
            setBuscadorBiblioteca(false);
          }}
        />
      )}
    </div>
  );
}

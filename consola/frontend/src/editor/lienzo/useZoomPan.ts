// Zoom y PAN del lienzo (estilo Canva), extraídos como hook. Owns la medida del espacio disponible
// (ResizeObserver), el nivel de zoom y la escala efectiva, el ancla de zoom-al-cursor/centro, y el
// pan con barra espaciadora / botón central. El componente le pasa el formato y el contenedor de
// scroll, y recibe `escala`/`baseFit` + los manejadores.

import type Konva from "konva";
import {
  type MouseEvent as ReactMouseEvent,
  type RefObject,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { clampZoom } from "./lib";

export function useZoomPan({
  w,
  h,
  maxAncho,
  maxAlto,
  scrollRef,
}: {
  w: number;
  h: number;
  maxAncho: number;
  maxAlto: number;
  scrollRef: RefObject<HTMLDivElement | null>;
}) {
  // Mide el espacio disponible para AJUSTAR el lienzo (responsive: llena el ancho en móvil y el
  // centro en escritorio). Cae a las props si aún no se ha medido.
  const medirRef = useRef<HTMLDivElement | null>(null);
  const [disp, setDisp] = useState<{ w: number; h: number }>({ w: maxAncho, h: maxAlto });
  useEffect(() => {
    const el = medirRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setDisp({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const baseFit = Math.min(disp.w / w, disp.h / h, 1);

  const [zoom, setZoom] = useState(1);
  const escala = baseFit * zoom;

  // Ancla de zoom-al-cursor: tras re-renderizar con la nueva escala, ajusta el scroll para que el
  // punto del documento bajo el cursor permanezca bajo el cursor.
  const anclaZoom = useRef<{ docX: number; docY: number; sx: number; sy: number } | null>(null);

  // ── Zoom (estilo Canva) ──────────────────────────────────────────────────
  // Todos los cambios de zoom SIN gesto de puntero (botones, menú de %, atajos) se anclan al
  // CENTRO del viewport: el punto del documento que estaba en el centro sigue en el centro tras
  // el cambio de escala. (El zoom con rueda se ancla al cursor en `onWheel`.)
  const anclarCentro = () => {
    const cont = scrollRef.current;
    if (!cont) return;
    const sx = cont.clientWidth / 2;
    const sy = cont.clientHeight / 2;
    anclaZoom.current = { docX: (cont.scrollLeft + sx) / escala, docY: (cont.scrollTop + sy) / escala, sx, sy };
  };
  const acercar = () => { anclarCentro(); setZoom((z) => clampZoom(z * 1.1, baseFit)); };
  const alejar = () => { anclarCentro(); setZoom((z) => clampZoom(z * 0.9, baseFit)); };
  // "Ajustar a pantalla" = el lienzo entero cabe en el espacio disponible. Como `escala = baseFit *
  // zoom` y `baseFit` ya encaja el documento, ajustar a pantalla equivale a zoom=1.
  const ajustarPantalla = () => setZoom(1);
  // "100%" = un píxel del documento ocupa un píxel de pantalla, i.e. escala efectiva 1 => zoom =
  // 1/baseFit (acotado al rango permitido).
  const zoomReal = () => { anclarCentro(); setZoom(clampZoom(1 / baseFit, baseFit)); };
  // Nivel ABSOLUTO del menú de zoom (0.1 => escala efectiva 10 %).
  const fijarEscala = (esc: number) => { anclarCentro(); setZoom(clampZoom(esc / baseFit, baseFit)); };

  // Zoom con ctrl/cmd + rueda, CENTRADO EN EL CURSOR: calcula el punto del documento bajo el puntero
  // y deja anotada un ancla; tras re-renderizar con la nueva escala, el efecto de abajo ajusta el
  // scroll para que ese mismo punto quede bajo el cursor (como Figma/Canva).
  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    if (!(e.evt.ctrlKey || e.evt.metaKey)) return;
    e.evt.preventDefault();
    const cont = scrollRef.current;
    const factor = e.evt.deltaY < 0 ? 1.1 : 0.9;
    if (cont) {
      const rect = cont.getBoundingClientRect();
      const sx = e.evt.clientX - rect.left; // offset del cursor dentro del contenedor (px pantalla)
      const sy = e.evt.clientY - rect.top;
      anclaZoom.current = {
        docX: (sx + cont.scrollLeft) / escala,
        docY: (sy + cont.scrollTop) / escala,
        sx,
        sy,
      };
    }
    setZoom((z) => clampZoom(z * factor, baseFit));
  };

  // Aplica el ancla de zoom-al-cursor tras commit (la nueva escala ya está en el DOM, así el scroll
  // no se recorta contra el tamaño viejo del contenido).
  useLayoutEffect(() => {
    const a = anclaZoom.current;
    if (!a) return;
    anclaZoom.current = null;
    const cont = scrollRef.current;
    if (!cont) return;
    cont.scrollLeft = a.docX * escala - a.sx;
    cont.scrollTop = a.docY * escala - a.sy;
    // `scrollRef` es un ref ESTABLE (identidad constante): incluirlo no cambia cuándo corre el
    // efecto (solo al cambiar `escala`), pero satisface a exhaustive-deps al ser ahora un parámetro.
  }, [escala, scrollRef]);

  // ── Pan (estilo Canva) ─────────────────────────────────────────────────────
  // Pan con barra espaciadora / botón central: `espacio` controla el cursor y desactiva la
  // interacción con las capas (Stage `listening` off) para que el arrastre haga PAN, no mueva capas.
  const [espacio, setEspacio] = useState(false);
  const espacioRef = useRef(false);
  const [paneando, setPaneando] = useState(false);

  // Pan con barra ESPACIADORA: mientras está pulsada, cursor grab/grabbing y `listening` del Stage
  // off (los arrastres mueven el lienzo, no las capas). Ignora el espacio si el foco está en un campo
  // editable (evita romper la escritura). `blur` de ventana lo resetea (no quedarse "pegado").
  useEffect(() => {
    const esEditable = (t: EventTarget | null) => {
      const el = t as HTMLElement | null;
      return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || esEditable(e.target)) return;
      e.preventDefault(); // evita el scroll de página al mantener espacio
      if (!espacioRef.current) {
        espacioRef.current = true;
        setEspacio(true);
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      espacioRef.current = false;
      setEspacio(false);
    };
    const reset = () => {
      espacioRef.current = false;
      setEspacio(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", reset);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", reset);
    };
  }, []);

  // PAN del contenedor de scroll: con espacio pulsado (botón izq) o con el botón CENTRAL del ratón.
  // Arrastra cambiando scrollLeft/scrollTop. Funciona aunque el puntero salga del lienzo (listeners
  // en window).
  const onMouseDownContenedor = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (!(espacioRef.current || e.button === 1)) return;
    const cont = scrollRef.current;
    if (!cont) return;
    e.preventDefault();
    setPaneando(true);
    const sx = e.clientX;
    const sy = e.clientY;
    const sl = cont.scrollLeft;
    const stp = cont.scrollTop;
    const onMove = (ev: MouseEvent) => {
      cont.scrollLeft = sl - (ev.clientX - sx);
      cont.scrollTop = stp - (ev.clientY - sy);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setPaneando(false);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return {
    medirRef,
    baseFit,
    escala,
    zoom,
    acercar,
    alejar,
    ajustarPantalla,
    zoomReal,
    fijarEscala,
    onWheel,
    espacio,
    espacioRef,
    paneando,
    onMouseDownContenedor,
  };
}

// Render interactivo de UNA capa como nodo Konva. Es el "proxy" editable del lienzo: el archivo
// final lo hornea el servidor con `dibujarDocumento` (fidelidad exacta de fuentes/cover/degradados).
// Aquí priorizamos manipulación directa (seleccionar, arrastrar, escalar, rotar).

import Konva from "konva";
import { useEffect, useRef } from "react";
import { Ellipse, Group, Image as KonvaImage, Line, Rect, Text } from "react-konva";

import type { Capa, CapaGrupo, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto } from "../documento";
import { useImagen } from "../useImagen";

export interface CapaNodoProps {
  capa: Capa;
  seleccionada: boolean;
  onSelect: (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => void;
  onChange: (cambios: Partial<Capa>) => void;
  onGesto: () => void;
  // Hijas de un grupo: no son arrastrables ni transformables por separado (el grupo manda).
  interactivo?: boolean;
}

const ALIN: Record<string, string> = {
  izquierda: "left",
  centro: "center",
  derecha: "right",
  justificado: "justify",
};

// Puntos inicial/final de un degradado lineal sobre una caja w×h según `angulo` (grados), con la
// MISMA convención que `gradienteLineal` de dibujar.mjs: 0°=↑, 90°=→, 180°=↓ (vertical), 270°=←.
// Konva usa puntos relativos al nodo (origen 0,0), así que el centro de la caja es (w/2,h/2).
export function puntosGradiente(w: number, h: number, angulo = 180) {
  const a = (angulo * Math.PI) / 180;
  const ux = Math.sin(a), uy = -Math.cos(a);
  const cx = w / 2, cy = h / 2;
  const semi = (Math.abs(w * ux) + Math.abs(h * uy)) / 2;
  return {
    start: { x: cx - ux * semi, y: cy - uy * semi },
    end: { x: cx + ux * semi, y: cy + uy * semi },
  };
}

// Resuelve las familias LÓGICAS del documento ("sans"/"condensada") a fuentes reales, para que
// el editor (Konva) pinte con la MISMA tipografía que el export del servidor (Barlow / Barlow
// Condensed por defecto). Cualquier otra familia (nombre real) se pasa tal cual.
function familiaReal(familia: string | undefined): string {
  if (familia === "sans") return "Barlow";
  if (familia === "condensada") return "Barlow Condensed";
  return familia || "Barlow";
}

type Filtros = CapaImagen["filtros"];

// Imagen AJUSTADA a una caja SIN deformar: la caja (`Group`) recorta y la imagen se escala
// preservando su proporción — `cover` la llena (desborde recortado), `contain` la encaja. El
// `Group` es el nodo interactivo (drag/transform); la imagen interior aplica los filtros Konva
// (WYSIWYG; el export del servidor usa los mismos, exactos).
function NodoImagenAjustada({
  img,
  w,
  h,
  ajuste,
  foco,
  zoom = 1,
  filtros,
  forma,
  radio,
  props,
}: {
  img: HTMLImageElement;
  w: number;
  h: number;
  ajuste: "cover" | "contain";
  foco: [number, number];
  zoom?: number;
  filtros: Filtros;
  forma?: "rect" | "elipse";
  radio?: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  props: any;
}) {
  const ref = useRef<Konva.Image | null>(null);
  const iw = img.width || 1;
  const ih = img.height || 1;
  const base = ajuste === "contain" ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const escala = base * (zoom > 0 ? zoom : 1);
  const dw = iw * escala;
  const dh = ih * escala;
  const ix = (w - dw) * (foco[0] ?? 0.5);
  const iy = (h - dh) * (foco[1] ?? 0.5);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (!filtros) {
      node.filters([]);
      node.clearCache();
      node.getLayer()?.batchDraw();
      return;
    }
    const lista: (typeof Konva.Filters.Brighten)[] = [];
    if (filtros.brillo != null && filtros.brillo !== 1) lista.push(Konva.Filters.Brighten);
    if (filtros.contraste != null && filtros.contraste !== 1) lista.push(Konva.Filters.Contrast);
    if (filtros.saturacion != null && filtros.saturacion !== 1) lista.push(Konva.Filters.HSL);
    if (filtros.desenfoque) lista.push(Konva.Filters.Blur);
    node.filters(lista);
    node.brightness((filtros.brillo ?? 1) - 1);
    node.contrast(((filtros.contraste ?? 1) - 1) * 100);
    node.saturation((filtros.saturacion ?? 1) - 1);
    node.blurRadius(filtros.desenfoque ?? 0);
    try {
      node.cache();
    } catch {
      /* imagen aún sin dimensiones: se reintenta en el próximo render */
    }
    node.getLayer()?.batchDraw();
  }, [filtros, dw, dh, img]);

  // Recorte de la caja según la forma (espejo del clip de `dibujarImagenEnCaja`): elipse/círculo,
  // rect de esquinas redondeadas (radio>0), o rect simple (default => clipX/Y/W/H como antes).
  const r = radio ?? 0;
  const recorte =
    forma === "elipse"
      ? {
          clipFunc: (ctx: Konva.Context) => {
            ctx.beginPath();
            ctx.ellipse(w / 2, h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
            ctx.closePath();
          },
        }
      : r > 0
        ? {
            clipFunc: (ctx: Konva.Context) => {
              const rr = Math.min(r, w / 2, h / 2);
              ctx.beginPath();
              ctx.moveTo(rr, 0);
              ctx.arcTo(w, 0, w, h, rr);
              ctx.arcTo(w, h, 0, h, rr);
              ctx.arcTo(0, h, 0, 0, rr);
              ctx.arcTo(0, 0, w, 0, rr);
              ctx.closePath();
            },
          }
        : { clipX: 0, clipY: 0, clipWidth: w, clipHeight: h };
  return (
    <Group {...props} {...recorte}>
      {/* Zona sensible al puntero del tamaño de la caja: la imagen interior va con listening=false,
          así que sin este Rect el Group no recibiría clic/arrastre (no se podían mover las fotos).
          opacity 0 = invisible en escena pero presente en el hit graph de Konva. */}
      <Rect x={0} y={0} width={w} height={h} fill="#000000" opacity={0} />
      <KonvaImage ref={ref} image={img} x={ix} y={iy} width={dw} height={dh} listening={false} />
    </Group>
  );
}

function textoMuestra(c: CapaTexto): string {
  const base = c.binding === "copy_in"
    ? c.texto || "Titular de ejemplo"
    : c.binding === "etiqueta_default"
      ? c.texto || "PLECA"
      : c.texto;
  return c.mayusculas ? base.toUpperCase() : base;
}

export function CapaNodo({ capa, seleccionada, onSelect, onChange, onGesto, interactivo = true }: CapaNodoProps) {
  // Hook SIEMPRE llamado (regla de hooks); null para capas sin imagen.
  const objetoImg = capa.tipo === "imagen" ? capa.objeto : capa.tipo === "logo" ? capa.media_id : null;
  const img = useImagen(objetoImg);

  const comun = {
    id: capa.id,
    x: capa.x,
    y: capa.y,
    rotation: capa.rotacion,
    opacity: capa.opacidad,
    draggable: interactivo && !capa.bloqueada,
    onMouseDown: onSelect,
    onTap: onSelect,
    listening: interactivo,
    ...(interactivo
      ? {
          onDragStart: onGesto,
          onDragEnd: (e: Konva.KonvaEventObject<DragEvent>) => {
            onChange({ x: e.target.x(), y: e.target.y() });
          },
        }
      : {}),
  };

  // Transform genérico: convierte escala -> w/h (y tamaño de fuente en textos), resetea escala.
  const onTransformEnd = (e: Konva.KonvaEventObject<Event>) => {
    const nodo = e.target;
    const sx = nodo.scaleX();
    const sy = nodo.scaleY();
    nodo.scaleX(1);
    nodo.scaleY(1);
    const base: Partial<Capa> = {
      x: nodo.x(),
      y: nodo.y(),
      rotacion: nodo.rotation(),
    } as Partial<Capa>;
    if (capa.tipo === "texto") {
      // "La caja es inamovible, que encoja el texto": al redimensionar una capa de texto
      // dibujamos la CAJA (ancho Y alto). El texto se auto-encoge en el render para caber; NO
      // crecemos el tamaño de fuente con la escala vertical. Persistimos `h` (no solo `w`), lo que
      // activa el modo caja (h>0) para esta capa.
      onChange({
        ...base,
        w: Math.max(16, capa.w * sx),
        h: Math.max(16, capa.h > 0 ? capa.h * sy : (capa as CapaTexto).tamano * (capa as CapaTexto).interlineado * sy),
      } as Partial<Capa>);
    } else {
      onChange({
        ...base,
        w: Math.max(8, capa.w * sx),
        h: Math.max(8, capa.h * sy),
      } as Partial<Capa>);
    }
  };

  const props = { ...comun, onTransformEnd };

  switch (capa.tipo) {
    case "imagen": {
      const c = capa as CapaImagen;
      if (!img) {
        return <Rect {...props} width={c.w} height={c.h} fill="#2a2d31" stroke="#4b5158" dash={[8, 8]} />;
      }
      const nodoImg = <NodoImagenAjustada img={img} w={c.w} h={c.h} ajuste={c.ajuste} foco={c.foco} zoom={c.zoom} filtros={c.filtros} forma={c.forma} radio={c.radio} props={props} />;
      // cornerRadius de la silueta de sombra, aproximando la forma: círculo (elipse) o esquinas.
      const sombraRadio = c.forma === "elipse" ? Math.min(c.w, c.h) / 2 : c.radio && c.radio > 0 ? c.radio : 0;
      // Realce de selección que SIGUE LA FORMA: el Transformer de Konva usa su bbox rect (sus
      // tiradores definen la caja), pero cuando la imagen es elipse o tiene esquinas redondeadas el
      // contorno azul punteado debe cuadrar con la forma redonda. Solo visual (listening=false).
      const formaRedonda = c.forma === "elipse" || (c.radio ?? 0) > 0;
      const realceSel =
        seleccionada && interactivo && formaRedonda ? (
          c.forma === "elipse" ? (
            <Ellipse
              x={c.x + c.w / 2}
              y={c.y + c.h / 2}
              radiusX={c.w / 2}
              radiusY={c.h / 2}
              rotation={c.rotacion}
              stroke="#3b82f6"
              strokeWidth={2}
              dash={[6, 4]}
              listening={false}
            />
          ) : (
            <Rect
              x={c.x}
              y={c.y}
              width={c.w}
              height={c.h}
              cornerRadius={c.radio}
              rotation={c.rotacion}
              stroke="#3b82f6"
              strokeWidth={2}
              dash={[6, 4]}
              listening={false}
            />
          )
        ) : null;
      // Sombra de la imagen: el Group de la imagen se recorta a su caja (la sombra no escaparía del
      // clip), así que la proyecta una silueta SIN listening dibujada detrás (igual que el render).
      if (c.sombra) {
        return (
          <>
            <Rect
              x={c.x}
              y={c.y}
              width={c.w}
              height={c.h}
              cornerRadius={sombraRadio}
              rotation={c.rotacion}
              opacity={c.opacidad}
              fill="#000000"
              listening={false}
              shadowColor={c.sombra.color}
              shadowOffsetX={c.sombra.dx}
              shadowOffsetY={c.sombra.dy}
              shadowBlur={c.sombra.desenfoque ?? 0}
              shadowOpacity={c.sombra.opacidad ?? 1}
              shadowEnabled
            />
            {nodoImg}
            {realceSel}
          </>
        );
      }
      if (realceSel) {
        return (
          <>
            {nodoImg}
            {realceSel}
          </>
        );
      }
      return nodoImg;
    }
    case "logo": {
      const c = capa as CapaLogo;
      if (c.tipo_logo === "imagen" && img) {
        // Logo: SIEMPRE encajar (contain) — nunca deformar.
        return <NodoImagenAjustada img={img} w={c.w} h={c.h} ajuste="contain" foco={[0.5, 0.5]} filtros={null} props={props} />;
      }
      return (
        <Group {...props}>
          <Rect width={c.w} height={c.h} fill={c.wordmark.fondo} cornerRadius={6} />
          <Text
            text={c.wordmark.texto || "LOGO"}
            width={c.w}
            height={c.h}
            align="center"
            verticalAlign="middle"
            fontFamily={familiaReal(c.wordmark.familia)}
            fontSize={Math.round(c.h * 0.42)}
            fontStyle={c.wordmark.peso >= 600 ? "bold" : "normal"}
            fill={c.wordmark.color}
          />
        </Group>
      );
    }
    case "texto": {
      const c = capa as CapaTexto;
      // En modo CAJA (h>0) respetamos el alto y la alineación vertical dentro de ella. El
      // auto-encogido de fuente NO se replica en Konva (la "vista real" la rinde el servidor con
      // dibujar.mjs); aquí basta con honrar caja + valign.
      const enCaja = c.h > 0;
      // Relleno: degradado lineal (mismos puntos que el render) o color sólido.
      const grad = c.relleno_degradado
        ? puntosGradiente(c.w, enCaja ? c.h : c.tamano * c.interlineado, c.relleno_degradado.angulo)
        : null;
      const nodoTexto = (
        <Text
          {...(c.chip ? {} : props)}
          text={textoMuestra(c)}
          width={c.w}
          height={enCaja ? c.h : undefined}
          verticalAlign={enCaja ? (c.valign === "centro" ? "middle" : c.valign === "abajo" ? "bottom" : "top") : undefined}
          fontFamily={familiaReal(c.familia)}
          fontSize={c.tamano}
          fontStyle={c.peso >= 600 ? "bold" : "normal"}
          fill={grad ? undefined : c.color}
          fillLinearGradientStartPoint={grad ? grad.start : undefined}
          fillLinearGradientEndPoint={grad ? grad.end : undefined}
          fillLinearGradientColorStops={
            grad && c.relleno_degradado ? [0, c.relleno_degradado.desde, 1, c.relleno_degradado.hasta] : undefined
          }
          align={ALIN[c.alineacion] ?? "left"}
          lineHeight={c.interlineado}
          letterSpacing={c.interletra || 0}
          stroke={c.contorno?.color}
          strokeWidth={c.contorno?.grosor ?? 0}
          fillAfterStrokeEnabled
          shadowColor={c.sombra?.color}
          shadowOffsetX={c.sombra?.dx}
          shadowOffsetY={c.sombra?.dy}
          shadowBlur={c.sombra?.desenfoque ?? 0}
          shadowOpacity={c.sombra?.opacidad ?? 1}
          shadowEnabled={!!c.sombra}
        />
      );
      if (!c.chip) return nodoTexto;
      // CHIP/pleca: el servidor pinta un fondo por línea detrás del texto (`dibujarChipLinea`).
      // Aquí lo aproximamos a nivel de CAJA: un Rect detrás del texto con el padding (pad_x/pad_y)
      // y el radio del chip. Aproximación; el export del servidor manda en la pieza final.
      const padX = c.chip.pad_x ?? 24;
      const padY = c.chip.pad_y ?? 14;
      const altoTexto = enCaja ? c.h : c.tamano * c.interlineado;
      // Posición del chip dentro del Group (coordenadas relativas a la capa). Aproxima el ancho con
      // la caja de texto; el render real lo ajusta al ancho de cada línea.
      return (
        <Group {...props}>
          <Rect
            x={-padX}
            y={-padY}
            width={c.w + padX * 2}
            height={altoTexto + padY * 2}
            fill={c.chip.color}
            cornerRadius={c.chip.radio || 0}
            listening={false}
          />
          {nodoTexto}
        </Group>
      );
    }
    case "marco": {
      const c = capa as CapaMarco;
      if (c.forma === "linea") {
        return (
          <Line
            {...props}
            points={[0, 0, c.w, c.h]}
            stroke={c.borde?.color ?? "#FFFFFF"}
            strokeWidth={c.borde?.grosor ?? 4}
          />
        );
      }
      // Relleno: degradado lineal (mismos puntos que el render) o color sólido. La sombra de la
      // forma usa los shadow* de Konva según `c.sombra`.
      const gradM = c.relleno_degradado ? puntosGradiente(c.w, c.h, c.relleno_degradado.angulo) : null;
      const rellenoMarco = gradM
        ? {
            fillLinearGradientStartPoint: gradM.start,
            fillLinearGradientEndPoint: gradM.end,
            fillLinearGradientColorStops: [0, c.relleno_degradado!.desde, 1, c.relleno_degradado!.hasta],
          }
        : { fill: c.relleno ?? undefined };
      const sombraMarco = c.sombra
        ? {
            shadowColor: c.sombra.color,
            shadowOffsetX: c.sombra.dx,
            shadowOffsetY: c.sombra.dy,
            shadowBlur: c.sombra.desenfoque ?? 0,
            shadowOpacity: c.sombra.opacidad ?? 1,
            shadowEnabled: true,
          }
        : {};
      if (c.forma === "elipse") {
        return (
          <Ellipse
            {...props}
            x={c.x + c.w / 2}
            y={c.y + c.h / 2}
            radiusX={c.w / 2}
            radiusY={c.h / 2}
            {...rellenoMarco}
            {...sombraMarco}
            stroke={c.borde?.color}
            strokeWidth={c.borde?.grosor}
          />
        );
      }
      return (
        <Rect
          {...props}
          width={c.w}
          height={c.h}
          cornerRadius={c.radio}
          {...rellenoMarco}
          {...sombraMarco}
          stroke={c.borde?.color}
          strokeWidth={c.borde?.grosor}
        />
      );
    }
    case "overlay": {
      const c = capa as CapaOverlay;
      const band = Math.max(1, c.h * c.alto_frac);
      // Rampa de legibilidad FIEL al servidor (`dibujarOverlayInferior`): ~11 paradas con la curva
      // t^1.5 sobre el alfa máximo (def 238/255). Separamos el RGB del posible alfa de 8 dígitos de
      // `c.color` (un `${c.color}00` lo corrompería) para componer cada parada como rgba(...).
      const m = /^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$/.exec(c.color || "#111315");
      const rgb = m ? m[1] : "111315";
      const aHex = m && m[2] ? parseInt(m[2], 16) / 255 : 1;
      const r = parseInt(rgb.slice(0, 2), 16);
      const g = parseInt(rgb.slice(2, 4), 16);
      const b = parseInt(rgb.slice(4, 6), 16);
      const aMax = ((c.alpha ?? 238) / 255) * aHex;
      const stops: (number | string)[] = [];
      for (let i = 0; i <= 10; i++) {
        const t = i / 10;
        stops.push(t, `rgba(${r},${g},${b},${aMax * Math.pow(t, 1.5)})`);
      }
      return (
        <Rect
          {...props}
          y={c.y + c.h - band}
          width={c.w}
          height={band}
          listening={!capa.bloqueada}
          fillLinearGradientStartPoint={{ x: 0, y: 0 }}
          fillLinearGradientEndPoint={{ x: 0, y: band }}
          fillLinearGradientColorStops={stops}
        />
      );
    }
    case "grupo": {
      // El grupo se arrastra como bloque: las hijas se pintan en coordenadas ABSOLUTAS (igual que
      // en el servidor) y el nodo Group vive en (0,0). Al soltar, se hornea el desplazamiento en
      // las coordenadas absolutas de cada hija (y en la bbox del grupo) y se resetea el nodo.
      const c = capa as CapaGrupo;
      const onDragEndGrupo = (e: Konva.KonvaEventObject<DragEvent>) => {
        const node = e.target;
        const dx = node.x();
        const dy = node.y();
        node.position({ x: 0, y: 0 });
        onChange({
          x: c.x + dx,
          y: c.y + dy,
          capas: c.capas.map((s) => ({ ...s, x: s.x + dx, y: s.y + dy })),
        } as Partial<Capa>);
      };
      return (
        <Group
          id={c.id}
          x={0}
          y={0}
          opacity={c.opacidad}
          draggable={!c.bloqueada}
          onMouseDown={onSelect}
          onTap={onSelect}
          onDragStart={onGesto}
          onDragEnd={onDragEndGrupo}
        >
          {c.capas.map((sub) => (
            <CapaNodo key={sub.id} capa={sub} seleccionada={false} onSelect={onSelect} onChange={() => {}} onGesto={onGesto} interactivo={false} />
          ))}
        </Group>
      );
    }
    default:
      return null;
  }
}

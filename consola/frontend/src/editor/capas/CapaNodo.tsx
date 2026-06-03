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
  props,
}: {
  img: HTMLImageElement;
  w: number;
  h: number;
  ajuste: "cover" | "contain";
  foco: [number, number];
  zoom?: number;
  filtros: Filtros;
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

  return (
    <Group {...props} clipX={0} clipY={0} clipWidth={w} clipHeight={h}>
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

export function CapaNodo({ capa, onSelect, onChange, onGesto, interactivo = true }: CapaNodoProps) {
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
      onChange({
        ...base,
        w: Math.max(16, capa.w * sx),
        tamano: Math.max(8, Math.round((capa as CapaTexto).tamano * sy)),
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
      return <NodoImagenAjustada img={img} w={c.w} h={c.h} ajuste={c.ajuste} foco={c.foco} zoom={c.zoom} filtros={c.filtros} props={props} />;
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
            fontFamily={c.wordmark.familia}
            fontSize={Math.round(c.h * 0.42)}
            fontStyle={c.wordmark.peso >= 600 ? "bold" : "normal"}
            fill={c.wordmark.color}
          />
        </Group>
      );
    }
    case "texto": {
      const c = capa as CapaTexto;
      return (
        <Text
          {...props}
          text={textoMuestra(c)}
          width={c.w}
          fontFamily={c.familia}
          fontSize={c.tamano}
          fontStyle={c.peso >= 600 ? "bold" : "normal"}
          fill={c.color}
          align={ALIN[c.alineacion] ?? "left"}
          lineHeight={c.interlineado}
          letterSpacing={c.interletra || 0}
          stroke={c.contorno?.color}
          strokeWidth={c.contorno?.grosor ?? 0}
          fillAfterStrokeEnabled
          shadowColor={c.sombra?.color}
          shadowOffsetX={c.sombra?.dx}
          shadowOffsetY={c.sombra?.dy}
          shadowEnabled={!!c.sombra}
        />
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
      if (c.forma === "elipse") {
        return (
          <Ellipse
            {...props}
            x={c.x + c.w / 2}
            y={c.y + c.h / 2}
            radiusX={c.w / 2}
            radiusY={c.h / 2}
            fill={c.relleno ?? undefined}
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
          fill={c.relleno ?? undefined}
          stroke={c.borde?.color}
          strokeWidth={c.borde?.grosor}
        />
      );
    }
    case "overlay": {
      const c = capa as CapaOverlay;
      const band = Math.max(1, c.h * c.alto_frac);
      return (
        <Rect
          {...props}
          y={c.y + c.h - band}
          width={c.w}
          height={band}
          listening={!capa.bloqueada}
          fillLinearGradientStartPoint={{ x: 0, y: 0 }}
          fillLinearGradientEndPoint={{ x: 0, y: band }}
          fillLinearGradientColorStops={[0, `${c.color}00`, 1, c.color]}
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

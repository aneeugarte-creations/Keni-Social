// Panel «Elementos» del rail (patrón Canva): inserta capas listas para usar — textos con estilo,
// formas (con vista previa real), bloques compuestos típicos de noticias/deportes (pleca inferior),
// imagen y degradado. Cada inserción queda seleccionada para editarla al instante.

import { Image as ImageIcon, PanelBottom, PanelTop } from "lucide-react";

import type { Capa, CapaMarco, CapaTexto } from "./documento";
import { nuevaCapaImagen, nuevaCapaMarco, nuevaCapaOverlay, nuevaCapaTexto, zTope } from "./documento";
import { crearElipse, crearLinea, crearRectangulo, crearTextoCuerpo } from "./elementos";
import { useStoreEditor } from "./usarEditor";

// Presets de texto. Titular y Pleca quedan ENLAZADOS al copy de la pieza (binding): al aplicar la
// plantilla a una publicación se rellenan solos. Subtítulo y Cuerpo son texto fijo. «Cuerpo» es el
// MISMO elemento que crea el atajo T del lienzo (fábrica compartida en `elementos.ts`).
const TEXTOS: { etiqueta: string; vista: string; clase: string; chip?: boolean; atajo?: string; crear: () => CapaTexto }[] = [
  { etiqueta: "Titular", vista: "Titular", clase: "text-xl font-extrabold tracking-tight", crear: () => nuevaCapaTexto({ w: 760, texto: "TITULAR", tamano: 96, peso: 800, mayusculas: true, ancla: "abajo", binding: "copy_in" }) },
  { etiqueta: "Subtítulo", vista: "Subtítulo", clase: "text-base font-bold", crear: () => nuevaCapaTexto({ w: 760, texto: "Subtítulo", tamano: 56, peso: 700 }) },
  { etiqueta: "Cuerpo", vista: "Texto de cuerpo", clase: "text-xs", atajo: "T", crear: crearTextoCuerpo },
  { etiqueta: "Pleca", vista: "EN VIVO", clase: "text-[10px] font-bold", chip: true, crear: () => nuevaCapaTexto({ w: 760, texto: "EN VIVO", tamano: 38, peso: 700, mayusculas: true, binding: "etiqueta_default", chip: { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 } }) },
];

// Vista previa de una forma como SVG: silueta FIEL a `pathFormaLocal` (CapaNodo) y a `dibujar.mjs`,
// no un icono genérico. `points` en un lienzo 24×24 (o el viewBox que se pase).
const poli = (points: string, vb = "0 0 24 24", cls = "h-7 w-7") => (
  <svg viewBox={vb} className={`${cls} text-foreground/80`} fill="currentColor"><polygon points={points} /></svg>
);

// Formas, con una vista previa real (no solo un icono). Rectángulo, Elipse y Línea son los MISMOS
// elementos que crean los atajos R/C/L del lienzo (fábricas compartidas en `elementos.ts`). El resto
// (triángulo, rombo, polígonos, estrella, flecha) son marcos con su `forma` del catálogo compartido.
const FORMAS: { etiqueta: string; vista: React.ReactNode; atajo?: string; crear: () => CapaMarco }[] = [
  { etiqueta: "Rectángulo", vista: <span className="h-6 w-9 rounded-sm bg-foreground/80" />, atajo: "R", crear: crearRectangulo },
  { etiqueta: "Redondeado", vista: <span className="h-6 w-9 rounded-lg bg-foreground/80" />, crear: () => nuevaCapaMarco({ w: 360, h: 240, forma: "rect", relleno: "#E30613", borde: null, radio: 32 }) },
  { etiqueta: "Elipse", vista: <span className="h-7 w-7 rounded-full bg-foreground/80" />, atajo: "C", crear: crearElipse },
  { etiqueta: "Triángulo", vista: poli("12,1 23,23 1,23"), crear: () => nuevaCapaMarco({ w: 320, h: 280, forma: "triangulo", relleno: "#E30613", borde: null }) },
  { etiqueta: "Rombo", vista: poli("12,1 23,12 12,23 1,12"), crear: () => nuevaCapaMarco({ w: 300, h: 300, forma: "rombo", relleno: "#E30613", borde: null }) },
  { etiqueta: "Pentágono", vista: poli("12,1 22.5,8.6 18.5,20.9 5.5,20.9 1.5,8.6"), crear: () => nuevaCapaMarco({ w: 300, h: 300, forma: "pentagono", relleno: "#E30613", borde: null }) },
  { etiqueta: "Hexágono", vista: poli("12,1 21.5,6.5 21.5,17.5 12,23 2.5,17.5 2.5,6.5"), crear: () => nuevaCapaMarco({ w: 320, h: 300, forma: "hexagono", relleno: "#E30613", borde: null }) },
  { etiqueta: "Estrella", vista: poli("12,1 15.2,7.6 22.5,8.6 17.2,13.7 18.5,20.9 12,17.5 5.5,20.9 6.8,13.7 1.5,8.6 8.8,7.6"), crear: () => nuevaCapaMarco({ w: 300, h: 300, forma: "estrella", relleno: "#E30613", borde: null }) },
  { etiqueta: "Flecha", vista: poli("0,7 22,7 22,0 36,12 22,24 22,17 0,17", "0 0 36 24", "h-6 w-9"), crear: () => nuevaCapaMarco({ w: 360, h: 240, forma: "flecha", relleno: "#E30613", borde: null }) },
  { etiqueta: "Línea", vista: <span className="h-0.5 w-9 bg-foreground/80" />, atajo: "L", crear: crearLinea },
  { etiqueta: "Marco", vista: <span className="h-6 w-9 rounded-sm border-2 border-foreground/80" />, crear: () => nuevaCapaMarco({ w: 360, h: 240, forma: "rect", relleno: null, borde: { color: "#FFFFFF", grosor: 8 } }) },
];

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{titulo}</div>
      {children}
    </div>
  );
}

export function PanelElementos() {
  const store = useStoreEditor();

  const insertar = (capa: Capa) => {
    const st = store.getState();
    const doc = st.documento;
    const x = Math.round((doc.formato.w - capa.w) / 2);
    const y = capa.tipo === "texto" && capa.ancla === "abajo"
      ? doc.formato.h - doc.formato.safe_bottom
      : Math.max(doc.formato.safe_top, Math.round(doc.formato.h * 0.12));
    st.agregar({ ...capa, x, y, z: zTope(doc) } as Capa);
    st.seleccionar(st.documento.capas[st.documento.capas.length - 1]?.id ?? null);
  };

  const seleccionarUltima = () => {
    const st = store.getState();
    st.seleccionar(st.documento.capas[st.documento.capas.length - 1]?.id ?? null);
  };

  // Degradado de legibilidad a sangre: banda pegada ABAJO (def) o ARRIBA. Cubre todo el lienzo y la
  // banda vive en el borde elegido; el alto/color/opacidad se ajustan luego en el inspector.
  const agregarDegradado = (lado?: "arriba") => {
    const st = store.getState();
    const doc = st.documento;
    st.agregar(
      nuevaCapaOverlay({ w: doc.formato.w, h: doc.formato.h, z: zTope(doc), ...(lado ? { lado } : {}) }),
    );
    seleccionarUltima();
  };

  // Bloque compuesto: PLECA INFERIOR de noticia (degradado + etiqueta roja + titular ligado al copy).
  const insertarPleca = () => {
    const st = store.getState();
    const { w, h, safe_bottom } = st.documento.formato;
    st.insertarBloque([
      nuevaCapaOverlay({ x: 0, y: 0, w, h, color: "#000000", alto_frac: 0.5, alpha: 210 }),
      nuevaCapaTexto({
        texto: "EN VIVO", binding: "etiqueta_default", mayusculas: true, tamano: 38, peso: 700,
        x: 80, y: Math.round(h - safe_bottom - h * 0.18), w: 420,
        chip: { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 },
      }),
      nuevaCapaTexto({
        texto: "Titular de la noticia", binding: "copy_in", mayusculas: true, tamano: 92, peso: 800,
        ancla: "abajo", x: 80, y: h - safe_bottom, w: w - 160, contorno: null,
      }),
    ]);
    seleccionarUltima();
  };

  return (
    <div className="flex h-full flex-col overflow-auto p-3">
      <Seccion titulo="Texto">
        <div className="flex flex-col gap-1.5">
          {TEXTOS.map((t) => (
            <button
              key={t.etiqueta}
              onClick={() => insertar(t.crear())}
              title={t.atajo ? `${t.etiqueta} (${t.atajo})` : t.etiqueta}
              className="flex items-center gap-3 overflow-hidden rounded-xl border bg-card px-3 py-2.5 text-left transition-colors hover:border-primary hover:bg-accent/40"
            >
              <span className="w-16 shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">{t.etiqueta}</span>
              <span className={`truncate text-foreground ${t.clase}`}>
                {t.chip ? <span className="rounded-sm bg-[#E30613] px-1.5 py-0.5 text-white">{t.vista}</span> : t.vista}
              </span>
            </button>
          ))}
        </div>
      </Seccion>

      <Seccion titulo="Bloques">
        <button
          onClick={insertarPleca}
          className="w-full overflow-hidden rounded-xl border bg-card p-1.5 text-left transition-colors hover:border-primary hover:bg-accent/40"
        >
          {/* Mini-maqueta: foto (placeholder gris) con la pleca SOLO en la franja inferior
              (degradado + etiqueta + titular). La tarjeta es clara; lo oscuro es la pleca real. */}
          <div className="relative h-20 w-full overflow-hidden rounded bg-gradient-to-br from-zinc-300 to-zinc-500">
            <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-black via-black/55 to-transparent" />
            <div className="absolute bottom-2 left-2 flex flex-col gap-1">
              <span className="w-fit rounded-sm bg-[#E30613] px-1.5 py-0.5 text-[8px] font-bold text-white">EN VIVO</span>
              <span className="text-[11px] font-extrabold uppercase leading-tight text-white">Titular de la noticia</span>
            </div>
          </div>
        </button>
        <p className="mt-1 px-1 text-[10px] text-muted-foreground">Pleca inferior: degradado + etiqueta + titular (se rellena con el copy).</p>
      </Seccion>

      <Seccion titulo="Formas">
        <div className="grid grid-cols-3 gap-1.5">
          {FORMAS.map((f) => (
            <button
              key={f.etiqueta}
              onClick={() => insertar(f.crear())}
              title={f.atajo ? `${f.etiqueta} (${f.atajo})` : f.etiqueta}
              className="flex aspect-square flex-col items-center justify-center gap-1.5 rounded-xl border bg-card text-[9px] text-muted-foreground hover:border-primary hover:bg-accent/50"
            >
              {f.vista}
              {f.etiqueta}
            </button>
          ))}
        </div>
      </Seccion>

      <Seccion titulo="Otros">
        <div className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() => insertar(nuevaCapaImagen("", { w: 540, h: 540 }))}
            className="flex flex-col items-center gap-1 rounded-xl border bg-card px-2 py-3 text-xs text-muted-foreground hover:border-primary hover:bg-accent/50"
          >
            <ImageIcon className="h-5 w-5" />
            Imagen
          </button>
          <button
            onClick={() => agregarDegradado()}
            title="Degradado pegado abajo"
            className="flex flex-col items-center gap-1 rounded-xl border bg-card px-2 py-3 text-xs text-muted-foreground hover:border-primary hover:bg-accent/50"
          >
            <PanelBottom className="h-5 w-5" />
            Degradado ↓
          </button>
          <button
            onClick={() => agregarDegradado("arriba")}
            title="Degradado pegado arriba"
            className="flex flex-col items-center gap-1 rounded-xl border bg-card px-2 py-3 text-xs text-muted-foreground hover:border-primary hover:bg-accent/50"
          >
            <PanelTop className="h-5 w-5" />
            Degradado ↑
          </button>
        </div>
      </Seccion>
    </div>
  );
}

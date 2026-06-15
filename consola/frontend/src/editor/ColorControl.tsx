// Control de color reutilizable estilo CANVA: muestra el color actual y, al abrirlo, ofrece un
// selector COMPLETO de espectro (cuadro de saturación/brillo + tira de tono: cualquier color
// posible, no solo muestras), entrada hexadecimal, cuentagotas (si el navegador trae la API
// EyeDropper) y MUESTRAS de un clic: colores de la marca activa, los ya usados en el diseño
// («paleta del documento»), los recientes y la rejilla de sólidos predeterminados de Canva.
//
// Soporta TRANSPARENCIA: el color se guarda como `#RRGGBB` (opaco) o `#RRGGBBAA` (con alfa). Un
// deslizador de opacidad + botón «Transparente» permiten, p. ej., un degradado de negro a
// transparente (#000000 → #00000000). Las muestras se pintan sobre un tablero de ajedrez para que
// se vea la transparencia.
//
// El popover se renderiza en un PORTAL a `body` con posición fija: así NO lo recorta el
// `overflow` del panel inspector.

import { useQuery } from "@tanstack/react-query";
import { Pipette } from "lucide-react";
import { type CSSProperties, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { MarcaActivaContexto } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

import { COLORES_PREDETERMINADOS, hexARgb, hsvARgb, normalizaHex, rgbAHex, rgbAHsv, type Hsv } from "./color";
import type { CapaMarco, CapaOverlay, CapaTexto } from "./documento";
import { useEditor } from "./usarEditor";

// Fondo de tablero de ajedrez (GIMP/Adobe) para visualizar transparencia detrás de una muestra.
const TABLERO: CSSProperties = {
  backgroundImage:
    "linear-gradient(45deg,#bbb 25%,transparent 25%),linear-gradient(-45deg,#bbb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#bbb 75%),linear-gradient(-45deg,transparent 75%,#bbb 75%)",
  backgroundSize: "8px 8px",
  backgroundPosition: "0 0,0 4px,4px -4px,-4px 0",
  backgroundColor: "#fff",
};

const RE_HEX = /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

const ANCHO_POPOVER = 240;

// Separa un color en su parte RGB (#RRGGBB) y su alfa 0..255.
function partes(v: string): { rgb: string; alfa: number } {
  if (/^#[0-9a-fA-F]{8}$/.test(v)) return { rgb: v.slice(0, 7), alfa: parseInt(v.slice(7, 9), 16) };
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return { rgb: v, alfa: 255 };
  return { rgb: "#000000", alfa: 255 };
}

// Combina RGB + alfa en un color canónico: `#RRGGBB` si es opaco (no ensucia el JSON), `#RRGGBBAA` si no.
function combina(rgb: string, alfa: number): string {
  const a = Math.max(0, Math.min(255, Math.round(alfa)));
  if (a >= 255) return rgb.toUpperCase();
  return (rgb + a.toString(16).padStart(2, "0")).toUpperCase();
}

// Colores recientes a nivel de módulo (persisten entre selecciones y pestañas durante la sesión).
const recientes: string[] = [];
function recordar(color: string) {
  const c = color.toUpperCase();
  const i = recientes.indexOf(c);
  if (i >= 0) recientes.splice(i, 1);
  recientes.unshift(c);
  if (recientes.length > 10) recientes.length = 10;
}

// Recolecta los colores DISTINTOS presentes en el documento (texto, marcos, chips, overlays, fondo).
function coloresDelDocumento(
  capas: unknown[],
  fondo: { color?: string; degradado?: { desde: string; hasta: string } },
): string[] {
  const set = new Set<string>();
  const add = (c?: string | null) => { if (c && RE_HEX.test(c)) set.add(c.toUpperCase()); };
  for (const capa of capas as { tipo: string }[]) {
    if (capa.tipo === "texto") { add((capa as CapaTexto).color); add((capa as CapaTexto).chip?.color); add((capa as CapaTexto).contorno?.color); }
    if (capa.tipo === "marco") { add((capa as CapaMarco).relleno); add((capa as CapaMarco).borde?.color); }
    if (capa.tipo === "overlay") add((capa as CapaOverlay).color);
  }
  add(fondo.color);
  add(fondo.degradado?.desde);
  add(fondo.degradado?.hasta);
  return [...set];
}

// Colores de la MARCA ACTIVA (identidad de `plantillaMarca`: rojo/tinta/blanco), como lista de hex
// para ofrecerlos en el ColorControl con un clic. El contexto de marca es OPCIONAL (mismo trato
// que PanelMarca): fuera del provider —p. ej. en los tests del editor— simplemente no hay colores
// de marca, sin romper.
function useColoresMarca(): string[] {
  const contexto = useContext(MarcaActivaContexto);
  const marcaActiva = contexto?.marcaActiva ?? null;
  const { data } = useQuery({
    queryKey: ["plantilla-marca", marcaActiva],
    queryFn: ({ signal }) => api.plantillaMarca(marcaActiva!, signal),
    enabled: !!marcaActiva,
    staleTime: 5 * 60_000,
  });
  const p = data?.plantilla;
  if (!p) return [];
  // Dedup preservando orden (rojo, tinta, blanco), filtrando hex válidos.
  const vistos = new Set<string>();
  const out: string[] = [];
  for (const c of [p.rojo, p.tinta, p.blanco]) {
    if (c && RE_HEX.test(c)) {
      const up = c.toUpperCase();
      if (!vistos.has(up)) { vistos.add(up); out.push(up); }
    }
  }
  return out;
}

// API EyeDropper (solo Chromium): cuentagotas REAL sobre toda la pantalla. El botón solo aparece
// si el navegador la trae (Safari/Firefox aún no).
type ConstructorGotero = new () => { open: () => Promise<{ sRGBHex: string }> };
function constructorGotero(): ConstructorGotero | undefined {
  return (window as unknown as { EyeDropper?: ConstructorGotero }).EyeDropper;
}

// Gesto de ARRASTRE con puntero sobre un área: llama a `alPunto(fx, fy)` (fracciones 0..1
// recortadas al área) al pulsar y mientras se arrastra, y a `alSoltar` al terminar.
function arrastrar(
  e: React.PointerEvent<HTMLDivElement>,
  alPunto: (fx: number, fy: number) => void,
  alSoltar?: () => void,
) {
  const r = e.currentTarget.getBoundingClientRect();
  const punto = (ev: { clientX: number; clientY: number }) => {
    alPunto(
      Math.max(0, Math.min(1, (ev.clientX - r.left) / (r.width || 1))),
      Math.max(0, Math.min(1, (ev.clientY - r.top) / (r.height || 1))),
    );
  };
  punto(e);
  const mover = (ev: PointerEvent) => punto(ev);
  const soltar = () => {
    window.removeEventListener("pointermove", mover);
    window.removeEventListener("pointerup", soltar);
    alSoltar?.();
  };
  window.addEventListener("pointermove", mover);
  window.addEventListener("pointerup", soltar);
}

// Selector de ESPECTRO (cualquier color, patrón Canva/Photoshop), sin dependencias: cuadro 2D de
// saturación (x) y brillo (y) pintado con degradados CSS sobre el matiz puro + tira de TONO
// (arcoíris). Mantiene el HSV en estado local: el hex no conserva el matiz cuando s=0 o v=0
// (blancos/negros/grises) y sin esta memoria el cursor «saltaría» al pasar por ellos.
function SelectorEspectro({ rgb, onChange, onFin }: {
  rgb: string; // #RRGGBB del color actual (el alfa lo gestiona ColorControl)
  onChange: (rgb: string) => void;
  onFin?: () => void; // fin del gesto (para registrar «recientes» una sola vez por arrastre)
}) {
  const [hsv, setHsv] = useState<Hsv>(() => rgbAHsv(hexARgb(rgb) ?? { r: 0, g: 0, b: 0 }));
  // Re-deriva el HSV SOLO cuando `rgb` cambia desde fuera (muestra, hex, gotero, undo), nunca
  // cuando es el eco de lo que este selector acaba de emitir (mismo patrón que el Stepper de la
  // barra contextual: estado local + comparación con el valor previo durante el render).
  const [previo, setPrevio] = useState(rgb);
  if (rgb !== previo) {
    setPrevio(rgb);
    if (rgb.toUpperCase() !== rgbAHex(hsvARgb(hsv))) {
      const c = hexARgb(rgb);
      if (c) setHsv(rgbAHsv(c));
    }
  }

  const fija = (n: Hsv) => {
    setHsv(n);
    onChange(rgbAHex(hsvARgb(n)));
  };

  // Durante el gesto las callbacks capturan el `hsv` del pointerdown: vale porque cada área solo
  // mueve SU(S) eje(s) y el resto queda congelado mientras dura el arrastre.
  return (
    <div className="flex flex-col gap-2">
      <div
        aria-label="Espectro de color (saturación y brillo)"
        onPointerDown={(e) => {
          e.preventDefault();
          arrastrar(e, (fx, fy) => fija({ h: hsv.h, s: fx, v: 1 - fy }), onFin);
        }}
        className="relative h-32 w-full cursor-crosshair touch-none rounded-md border border-border"
        style={{
          background: `linear-gradient(to top,#000,rgba(0,0,0,0)),linear-gradient(to right,#fff,rgba(255,255,255,0)),hsl(${Math.round(hsv.h)} 100% 50%)`,
        }}
      >
        <span
          className="pointer-events-none absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_1px_rgba(0,0,0,.4)]"
          style={{ left: `${hsv.s * 100}%`, top: `${(1 - hsv.v) * 100}%`, background: rgbAHex(hsvARgb(hsv)) }}
        />
      </div>
      <div
        aria-label="Tono"
        onPointerDown={(e) => {
          e.preventDefault();
          arrastrar(e, (fx) => fija({ h: fx * 360, s: hsv.s, v: hsv.v }), onFin);
        }}
        className="relative h-3 w-full cursor-ew-resize touch-none rounded-full"
        style={{ background: "linear-gradient(to right,#f00 0%,#ff0 17%,#0f0 33%,#0ff 50%,#00f 67%,#f0f 83%,#f00 100%)" }}
      >
        <span
          className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_1px_rgba(0,0,0,.4)]"
          style={{ left: `${(hsv.h / 360) * 100}%`, background: `hsl(${Math.round(hsv.h)} 100% 50%)` }}
        />
      </div>
    </div>
  );
}

function Muestras({ colores, valor, onPick }: { colores: string[]; valor: string; onPick: (c: string) => void }) {
  if (colores.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {colores.map((c) => (
        <button
          key={c}
          onClick={() => onPick(c)}
          title={c}
          style={TABLERO}
          className={`h-5 w-5 overflow-hidden rounded border ${c.toUpperCase() === valor.toUpperCase() ? "border-primary ring-1 ring-primary" : "border-border"}`}
        >
          <span className="block h-full w-full" style={{ background: c }} />
        </button>
      ))}
    </div>
  );
}

export function ColorControl({ valor, onChange, titulo = "Color" }: {
  valor: string;
  onChange: (c: string) => void;
  titulo?: string; // tooltip y nombre accesible del botón (p. ej. «Color del texto»)
}) {
  const [abierto, setAbierto] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  // Texto en edición de la entrada hexadecimal (`null` = sin edición: muestra el color actual).
  const [hexEdicion, setHexEdicion] = useState<string | null>(null);
  const botonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const capas = useEditor((s) => s.documento.capas);
  const fondo = useEditor((s) => s.documento.fondo);
  const delDoc = coloresDelDocumento(capas, fondo);
  const deMarca = useColoresMarca();
  const { rgb, alfa } = partes(valor);
  // Último valor aplicado, para registrar «recientes» UNA vez al soltar el arrastre del espectro
  // (registrar en cada tick del arrastre inundaría la lista con intermedios casi iguales).
  const valorRef = useRef(valor);
  valorRef.current = valor;

  useEffect(() => {
    if (!abierto) return;
    const cerrar = () => setAbierto(false);
    // Cierra al scrollear FUERA del popover (capture: true) o cambiar tamaño de ventana. El scroll
    // interno del propio popover (su contenido es alto y scrollea) no debe cerrarlo.
    const cerrarEnScroll = (e: Event) => {
      if (popoverRef.current && e.target instanceof Node && popoverRef.current.contains(e.target)) return;
      cerrar();
    };
    const cerrarEnResize = () => cerrar();
    const conTecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cerrar();
        botonRef.current?.focus();
      }
    };
    // Enfoca la entrada hexadecimal al abrir.
    setTimeout(() => inputRef.current?.focus(), 0);
    window.addEventListener("click", cerrar);
    window.addEventListener("scroll", cerrarEnScroll, { capture: true });
    window.addEventListener("resize", cerrarEnResize);
    window.addEventListener("keydown", conTecla);
    return () => {
      window.removeEventListener("click", cerrar);
      window.removeEventListener("scroll", cerrarEnScroll, { capture: true });
      window.removeEventListener("resize", cerrarEnResize);
      window.removeEventListener("keydown", conTecla);
    };
  }, [abierto]);


  const abrir = () => {
    const r = botonRef.current?.getBoundingClientRect();
    if (r) {
      const left = Math.max(8, Math.min(window.innerWidth - ANCHO_POPOVER - 8, r.right - ANCHO_POPOVER));
      // El popover es alto (espectro + muestras): si abajo no queda sitio, se sube y su contenido
      // scrollea por dentro (maxHeight en el render).
      const top = window.innerHeight - (r.bottom + 4) < 320
        ? Math.max(8, window.innerHeight - 328)
        : r.bottom + 4;
      setPos({ top, left });
    }
    setHexEdicion(null);
    setAbierto((v) => !v);
  };

  const elegir = (c: string) => { recordar(c); onChange(c); };
  const setRgb = (nuevoRgb: string) => elegir(combina(nuevoRgb, alfa));
  const setAlfa = (nuevoAlfa: number) => elegir(combina(rgb, nuevoAlfa));

  const commitHex = () => {
    if (hexEdicion !== null) {
      const n = normalizaHex(hexEdicion);
      if (n) setRgb(n);
    }
    setHexEdicion(null);
  };

  const Gotero = constructorGotero();
  const abrirGotero = async () => {
    if (!Gotero) return;
    try {
      const res = await new Gotero().open();
      if (res?.sRGBHex) setRgb(res.sRGBHex.toUpperCase());
    } catch {
      // Gesto cancelado (Esc): sin cambios.
    }
  };

  return (
    <div className="relative shrink-0" onClick={(e) => e.stopPropagation()}>
      <button
        ref={botonRef}
        onClick={abrir}
        style={TABLERO}
        className="relative h-6 w-10 overflow-hidden rounded border border-input"
        title={titulo}
        aria-label={titulo}
      >
        <span className="absolute inset-0" style={{ background: valor }} />
      </button>
      {abierto && pos &&
        createPortal(
          <div
            ref={popoverRef}
            role="dialog"
            aria-label={titulo}
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              top: pos.top,
              left: pos.left,
              width: ANCHO_POPOVER,
              maxHeight: `calc(100vh - ${pos.top + 8}px)`,
            }}
            className="z-[100] overflow-y-auto rounded-md border border-border bg-popover p-2 shadow-lg"
          >
            {/* ESPECTRO completo: el arrastre emite #RRGGBB (se conserva el alfa actual) y los
                «recientes» se registran una sola vez al soltar, no en cada tick. */}
            <SelectorEspectro
              rgb={rgb}
              onChange={(nuevo) => onChange(combina(nuevo, alfa))}
              onFin={() => recordar(valorRef.current)}
            />
            <div className="mb-2 mt-2 flex items-center gap-1">
              <input
                ref={inputRef}
                type="text"
                aria-label="Color en hexadecimal"
                spellCheck={false}
                value={hexEdicion ?? rgb.toUpperCase()}
                onChange={(e) => setHexEdicion(e.target.value)}
                onBlur={commitHex}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitHex();
                  if (e.key === "Escape") setHexEdicion(null);
                }}
                className="h-7 w-0 flex-1 rounded border border-input bg-background px-1.5 font-mono text-[11px] uppercase outline-none focus:border-primary"
              />
              {Gotero && (
                <button
                  onClick={abrirGotero}
                  title="Cuentagotas (toma un color de la pantalla)"
                  aria-label="Cuentagotas"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-input text-muted-foreground hover:border-primary hover:text-foreground"
                >
                  <Pipette className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            {/* Opacidad (alfa). 0 = transparente. */}
            <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              <span>Opacidad</span>
              <span>{Math.round((alfa / 255) * 100)}%</span>
            </div>
            <input
              type="range"
              aria-label="Opacidad"
              min={0}
              max={255}
              value={alfa}
              onChange={(e) => setAlfa(Number(e.target.value))}
              className="mb-2 w-full"
            />
            <button
              onClick={() => setAlfa(0)}
              style={TABLERO}
              className="mb-2 w-full overflow-hidden rounded border border-border py-1 text-[11px] text-foreground hover:border-primary"
            >
              <span className="rounded bg-background/70 px-1">Transparente</span>
            </button>
            {deMarca.length > 0 && (
              <>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Marca</div>
                <Muestras colores={deMarca} valor={valor} onPick={elegir} />
              </>
            )}
            {delDoc.length > 0 && (
              <>
                <div className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">En el diseño</div>
                <Muestras colores={delDoc} valor={valor} onPick={elegir} />
              </>
            )}
            {recientes.length > 0 && (
              <>
                <div className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Recientes</div>
                <Muestras colores={recientes} valor={valor} onPick={elegir} />
              </>
            )}
            <div className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Colores predeterminados</div>
            <Muestras colores={COLORES_PREDETERMINADOS} valor={valor} onPick={elegir} />
          </div>,
          document.body,
        )}
    </div>
  );
}

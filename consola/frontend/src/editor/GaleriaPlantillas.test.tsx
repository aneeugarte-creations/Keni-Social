/**
 * Tests de GaleriaPlantillas:
 *  - Diferenciación foto / miniatura: filtro por tipo, badge de tipo, `tipoFijo`.
 *  - Organización estilo Canva: búsqueda (nombre/categoría), chips de categoría, agrupación por
 *    categoría y badge-selector de categoría (modo gestión vs selector).
 *  - Vacío de búsqueda con salida de un clic («Borrar búsqueda»).
 *  - `ContenidoPlantillas` reutilizable como panel «Diseño» del rail (sin envoltorio modal).
 *  - Masonry (2 columnas en compacto, aspecto real del documento) + carga perezosa por lotes
 *    (sentinel + IntersectionObserver falso controlable).
 */
import { act, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContenidoPlantillas, GaleriaPlantillas } from "./GaleriaPlantillas";
import { ratioPlantilla, repartirMasonry } from "@/components/plantillas/FiltroPlantillas";
import type { PlantillaDiseno } from "@/lib/api";

// IntersectionObserver controlable: jsdom no lo trae; capturamos el callback de cada instancia
// para disparar la intersección a mano (mismo patrón que FeedIdeacion.test).
const disparadoresIO: (() => void)[] = [];
class IOFalso {
  cb: IntersectionObserverCallback;
  constructor(cb: IntersectionObserverCallback) {
    this.cb = cb;
    disparadoresIO.push(() =>
      this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver),
    );
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}
beforeEach(() => {
  disparadoresIO.length = 0;
  vi.stubGlobal("IntersectionObserver", IOFalso as unknown as typeof IntersectionObserver);
});
afterEach(() => {
  vi.unstubAllGlobals();
});
/** Dispara la intersección del ÚLTIMO observador vivo (el del sentinel actual). */
const dispararIO = () =>
  act(() => {
    disparadoresIO[disparadoresIO.length - 1]?.();
  });

// Plantillas de prueba
const FOTO: PlantillaDiseno = {
  id: "foto-1",
  marca: "m1",
  nombre: "Placa de marca",
  categoria: "post",
  tipo: "foto",
  documento: {},
  miniatura: "",
  miniatura_url: "",
  foto_muestra: "",
  foto_muestra_url: "",
  titular_muestra: "",
  etiqueta_muestra: "",
  lineas: [],
  activo: true,
  rotar: false,
  orden: 0,
  marca_nombre: "UnoTV",
  autor_id: "u1",
  autor_nombre: "Ana",
  creado: "2026-01-01T00:00:00",
  actualizado: "2026-01-01T00:00:00",
};

const MINIATURA: PlantillaDiseno = {
  ...FOTO,
  id: "min-1",
  nombre: "Portada video",
  tipo: "miniatura",
};

const AMBAS = [FOTO, MINIATURA];

describe("GaleriaPlantillas — filtro de tipo", () => {
  it("por defecto muestra solo plantillas de tipo 'foto'", () => {
    render(
      <GaleriaPlantillas plantillas={AMBAS} onCargar={vi.fn()} onCerrar={vi.fn()} />,
    );
    // La plantilla de foto aparece; la de miniatura no.
    expect(screen.getByTitle(`Cargar «${FOTO.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${MINIATURA.nombre}»`)).not.toBeInTheDocument();
  });

  it("al pulsar 'Miniaturas' muestra solo las de tipo miniatura", () => {
    render(
      <GaleriaPlantillas plantillas={AMBAS} onCargar={vi.fn()} onCerrar={vi.fn()} />,
    );
    // Cambiar al filtro de miniaturas
    fireEvent.click(screen.getByText("Miniaturas"));
    expect(screen.getByTitle(`Cargar «${MINIATURA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${FOTO.nombre}»`)).not.toBeInTheDocument();
  });

  it("muestra la etiqueta de tipo 'Foto' junto al nombre, fuera de la miniatura", () => {
    render(
      <GaleriaPlantillas plantillas={[FOTO]} onCargar={vi.fn()} onCerrar={vi.fn()} />,
    );
    expect(screen.getByText("Foto")).toBeInTheDocument();
  });

  it("muestra la etiqueta de tipo 'Miniatura' junto al nombre (con tipoFijo)", () => {
    render(
      <GaleriaPlantillas
        plantillas={[MINIATURA]}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    expect(screen.getByText("Miniatura")).toBeInTheDocument();
    // El selector de tipo NO aparece (tipoFijo lo oculta)
    expect(screen.queryByText("Fotos")).not.toBeInTheDocument();
  });

  it("tipoFijo='miniatura' filtra directamente y oculta el selector", () => {
    render(
      <GaleriaPlantillas
        plantillas={AMBAS}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    // Solo la miniatura aparece
    expect(screen.getByTitle(`Cargar «${MINIATURA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${FOTO.nombre}»`)).not.toBeInTheDocument();
    // No hay botón de cambio de filtro
    expect(screen.queryByText("Fotos")).not.toBeInTheDocument();
  });

  it("mensaje vacío contextualizado cuando no hay plantillas del tipo activo", () => {
    render(
      <GaleriaPlantillas
        plantillas={[FOTO]}
        onCargar={vi.fn()}
        onCerrar={vi.fn()}
        tipoFijo="miniatura"
      />,
    );
    expect(screen.getByText(/miniaturas para esta marca/i)).toBeInTheDocument();
  });

  it("con onRotar: refleja el estado de rotación y lo alterna al pulsar", () => {
    const onRotar = vi.fn();
    const EN_ROTACION: PlantillaDiseno = { ...FOTO, id: "rot-1", nombre: "Azul", rotar: true };
    render(
      <GaleriaPlantillas
        plantillas={[FOTO, EN_ROTACION]}
        onCargar={vi.fn()}
        onRotar={onRotar}
        onCerrar={vi.fn()}
      />,
    );
    // FOTO no está en rotación -> "Rotación"; la otra sí -> "En rotación".
    expect(screen.getByText("Rotación")).toBeInTheDocument();
    expect(screen.getByText("En rotación")).toBeInTheDocument();
    // Pulsar la de FOTO la AÑADE a la rotación (rotar -> true).
    fireEvent.click(screen.getByText("Rotación"));
    expect(onRotar).toHaveBeenCalledWith(expect.objectContaining({ id: "foto-1" }), true);
  });

  it("sin onRotar (modo selector) no muestra el control de rotación", () => {
    render(<GaleriaPlantillas plantillas={[FOTO]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    expect(screen.queryByText("Rotación")).not.toBeInTheDocument();
  });
});

// ── Búsqueda + chips + agrupación por categoría (estilo Canva) ─────────────────────────────────

const ULTIMA: PlantillaDiseno = { ...FOTO, id: "cat-1", nombre: "Roja breaking", categoria: "ultima-hora" };
const MARCADOR: PlantillaDiseno = { ...FOTO, id: "cat-2", nombre: "Final del partido", categoria: "marcador" };

describe("GaleriaPlantillas — búsqueda y categorías", () => {
  it("la búsqueda filtra por nombre", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA, MARCADOR]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "breaking" } });
    expect(screen.getByTitle(`Cargar «${ULTIMA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${MARCADOR.nombre}»`)).not.toBeInTheDocument();
  });

  it("la búsqueda encuentra por categoría, acento-insensible", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA, MARCADOR]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "última hora" } });
    expect(screen.getByTitle(`Cargar «${ULTIMA.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${MARCADOR.nombre}»`)).not.toBeInTheDocument();
  });

  it("sin coincidencias muestra el mensaje de vacío de búsqueda", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzz-nada" } });
    expect(screen.getByText(/sin resultados/i)).toBeInTheDocument();
  });

  it("el vacío de búsqueda ofrece «Borrar búsqueda», que restaura la rejilla", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA, MARCADOR]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    // Búsqueda sin resultados + chip activo: el botón limpia AMBOS filtros.
    fireEvent.click(screen.getByRole("button", { name: "Marcador" }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzz-nada" } });
    expect(screen.getByText(/sin resultados/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Borrar búsqueda" }));
    expect(screen.queryByText(/sin resultados/i)).not.toBeInTheDocument();
    expect(screen.getByTitle(`Cargar «${ULTIMA.nombre}»`)).toBeInTheDocument();
    expect(screen.getByTitle(`Cargar «${MARCADOR.nombre}»`)).toBeInTheDocument();
    expect((screen.getByRole("searchbox") as HTMLInputElement).value).toBe("");
  });

  it("chips: «Todas» + las categorías presentes; un chip filtra la rejilla", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA, MARCADOR]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Todas" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Marcador" }));
    expect(screen.getByTitle(`Cargar «${MARCADOR.nombre}»`)).toBeInTheDocument();
    expect(screen.queryByTitle(`Cargar «${ULTIMA.nombre}»`)).not.toBeInTheDocument();
  });

  it("con una sola categoría no hay chips ni cabeceras de grupo", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Todas" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Última hora" })).not.toBeInTheDocument();
  });

  it("con varias categorías agrupa con cabeceras de sección", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA, MARCADOR]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Última hora" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Marcador" })).toBeInTheDocument();
  });

  it("el legado 'post' se muestra como badge «General»", () => {
    render(<GaleriaPlantillas plantillas={[FOTO]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    expect(screen.getByText("General")).toBeInTheDocument();
  });

  it("sin onCategorizar (modo selector) el badge no abre selector", () => {
    render(<GaleriaPlantillas plantillas={[ULTIMA]} onCargar={vi.fn()} onCerrar={vi.fn()} />);
    expect(screen.queryByTitle("Cambiar categoría")).not.toBeInTheDocument();
  });

  it("con onCategorizar el badge abre el selector y permite cambiar la categoría", () => {
    const onCategorizar = vi.fn();
    render(
      <GaleriaPlantillas
        plantillas={[ULTIMA]}
        onCargar={vi.fn()}
        onCategorizar={onCategorizar}
        onCerrar={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Cambiar categoría"));
    fireEvent.click(screen.getByRole("option", { name: "Marcador" }));
    expect(onCategorizar).toHaveBeenCalledWith(expect.objectContaining({ id: "cat-1" }), "marcador");
  });

  it("el selector de categoría filtra el catálogo (acento-insensible)", () => {
    render(
      <GaleriaPlantillas
        plantillas={[ULTIMA]}
        onCargar={vi.fn()}
        onCategorizar={vi.fn()}
        onCerrar={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Cambiar categoría"));
    fireEvent.change(screen.getByPlaceholderText("Buscar etiqueta…"), {
      target: { value: "marc" },
    });
    expect(screen.getByRole("option", { name: "Marcador" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Efemérides" })).not.toBeInTheDocument();
  });

  it("el buscador NO crea: el botón «Crear etiqueta» abre un campo aparte y crea", () => {
    const onCategorizar = vi.fn();
    render(
      <GaleriaPlantillas
        plantillas={[ULTIMA]}
        onCargar={vi.fn()}
        onCategorizar={onCategorizar}
        onCerrar={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Cambiar categoría"));
    // Escribir en el buscador NO ofrece crear (solo filtra).
    fireEvent.change(screen.getByPlaceholderText("Buscar etiqueta…"), {
      target: { value: "Promo especial" },
    });
    expect(screen.getByText("Sin coincidencias")).toBeInTheDocument();
    // La creación va por su propio botón → campo aparte.
    fireEvent.click(screen.getByRole("button", { name: "Crear etiqueta" }));
    const campo = screen.getByPlaceholderText("Nombre de la etiqueta…");
    fireEvent.change(campo, { target: { value: "Promo especial" } });
    fireEvent.keyDown(campo, { key: "Enter" });
    expect(onCategorizar).toHaveBeenCalledWith(
      expect.objectContaining({ id: "cat-1" }),
      "Promo especial",
    );
  });

  it("con onRenombrar el mini-editor edita el NOMBRE ahí mismo (Enter)", () => {
    const onRenombrar = vi.fn();
    render(
      <GaleriaPlantillas
        plantillas={[ULTIMA]}
        onCargar={vi.fn()}
        onCategorizar={vi.fn()}
        onRenombrar={onRenombrar}
        onCerrar={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Editar nombre y etiqueta"));
    const nombre = screen.getByLabelText("Nombre");
    fireEvent.change(nombre, { target: { value: "Roja portada" } });
    fireEvent.keyDown(nombre, { key: "Enter" });
    expect(onRenombrar).toHaveBeenCalledWith(expect.objectContaining({ id: "cat-1" }), "Roja portada");
  });

  it("el mini-editor cambia nombre Y etiqueta en una sola interacción", () => {
    const onRenombrar = vi.fn();
    const onCategorizar = vi.fn();
    render(
      <GaleriaPlantillas
        plantillas={[ULTIMA]}
        onCargar={vi.fn()}
        onCategorizar={onCategorizar}
        onRenombrar={onRenombrar}
        onCerrar={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Editar nombre y etiqueta"));
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nuevo nombre" } });
    fireEvent.click(screen.getByRole("option", { name: "Marcador" }));
    expect(onCategorizar).toHaveBeenCalledWith(expect.objectContaining({ id: "cat-1" }), "marcador");
    expect(onRenombrar).toHaveBeenCalledWith(expect.objectContaining({ id: "cat-1" }), "Nuevo nombre");
  });

  it("sin cambiar el nombre, cerrar el mini-editor no dispara renombrado", () => {
    const onRenombrar = vi.fn();
    render(
      <GaleriaPlantillas
        plantillas={[ULTIMA]}
        onCargar={vi.fn()}
        onCategorizar={vi.fn()}
        onRenombrar={onRenombrar}
        onCerrar={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Editar nombre y etiqueta"));
    fireEvent.click(screen.getByRole("option", { name: "Marcador" }));
    expect(onRenombrar).not.toHaveBeenCalled();
  });

  it("teclear el nombre y clicar FUERA lo persiste (sin closure obsoleto)", () => {
    const onRenombrar = vi.fn();
    render(
      <GaleriaPlantillas
        plantillas={[ULTIMA]}
        onCargar={vi.fn()}
        onCategorizar={vi.fn()}
        onRenombrar={onRenombrar}
        onCerrar={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Editar nombre y etiqueta"));
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Editado fuera" } });
    fireEvent.mouseDown(document.body);
    expect(onRenombrar).toHaveBeenCalledWith(expect.objectContaining({ id: "cat-1" }), "Editado fuera");
  });
});

// ── ContenidoPlantillas como panel «Diseño» del rail (sin modal) ────────────────────────────────

describe("ContenidoPlantillas — modo panel del rail", () => {
  it("renderiza búsqueda + tarjetas SIN envoltorio de diálogo y cargar funciona", () => {
    const onCargar = vi.fn();
    render(<ContenidoPlantillas compacto plantillas={[ULTIMA, MARCADOR]} onCargar={onCargar} />);
    // No hay modal: ni role dialog ni backdrop de cierre.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Cerrar galería de plantillas")).not.toBeInTheDocument();
    // Búsqueda y chips presentes (fijos arriba del scroll, estilo Canva).
    expect(screen.getByRole("searchbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Todas" })).toBeInTheDocument();
    // Un clic en la tarjeta aplica la plantilla.
    fireEvent.click(screen.getByTitle(`Cargar «${ULTIMA.nombre}»`));
    expect(onCargar).toHaveBeenCalledWith(expect.objectContaining({ id: "cat-1" }));
  });

  it("en modo compacto el masonry es fijo de 2 columnas", () => {
    const { container } = render(
      <ContenidoPlantillas compacto plantillas={[ULTIMA]} onCargar={vi.fn()} />,
    );
    const masonry = container.querySelector("[data-masonry]");
    expect(masonry).toHaveAttribute("data-masonry", "2");
    expect(masonry?.querySelectorAll("[data-col]")).toHaveLength(2);
  });
});

// ── Masonry (aspecto real + reparto) y carga perezosa por lotes ─────────────────────────────────

const MUCHAS: PlantillaDiseno[] = Array.from({ length: 30 }, (_, i) => ({
  ...FOTO,
  id: `lote-${i}`,
  nombre: `Plantilla ${i}`,
}));

describe("ContenidoPlantillas — masonry y carga perezosa", () => {
  it("reparte las tarjetas entre las 2 columnas del panel compacto", () => {
    const { container } = render(
      <ContenidoPlantillas compacto plantillas={MUCHAS.slice(0, 4)} onCargar={vi.fn()} />,
    );
    const cols = container.querySelectorAll("[data-col]");
    expect(cols).toHaveLength(2);
    // Mismo aspecto en las 4 => reparto equilibrado 2/2 (greedy a la columna más corta).
    expect(cols[0].querySelectorAll("img")).toHaveLength(2);
    expect(cols[1].querySelectorAll("img")).toHaveLength(2);
  });

  it("la miniatura reserva la relación de aspecto REAL del documento (sin layout shift)", () => {
    const VERTICAL: PlantillaDiseno = {
      ...FOTO,
      id: "vert-1",
      nombre: "Story vertical",
      documento: { formato: { w: 1080, h: 1920 } },
    };
    render(<ContenidoPlantillas compacto plantillas={[VERTICAL]} onCargar={vi.fn()} />);
    const caja = screen.getByTitle("Cargar «Story vertical»").firstElementChild as HTMLElement;
    expect(caja.style.aspectRatio).toBe(String(1080 / 1920));
  });

  it("sin formato en el documento cae al 4/5 histórico", () => {
    render(<ContenidoPlantillas compacto plantillas={[FOTO]} onCargar={vi.fn()} />);
    const caja = screen.getByTitle(`Cargar «${FOTO.nombre}»`).firstElementChild as HTMLElement;
    expect(caja.style.aspectRatio).toBe(String(4 / 5));
    expect(ratioPlantilla(FOTO)).toBeCloseTo(0.8);
  });

  it("repartirMasonry es estable por prefijo: cargar un lote no recoloca lo ya pintado", () => {
    const antes = repartirMasonry(MUCHAS.slice(0, 24), 2);
    const despues = repartirMasonry(MUCHAS, 2);
    expect(despues[0].slice(0, antes[0].length)).toEqual(antes[0]);
    expect(despues[1].slice(0, antes[1].length)).toEqual(antes[1]);
  });

  it("renderiza el primer lote (24) con sentinel; la intersección suelta el resto", () => {
    const { container } = render(
      <ContenidoPlantillas compacto plantillas={MUCHAS} onCargar={vi.fn()} />,
    );
    expect(screen.getAllByTitle(/^Cargar «/)).toHaveLength(24);
    expect(container.querySelector("[data-sentinela]")).toBeInTheDocument();
    dispararIO();
    expect(screen.getAllByTitle(/^Cargar «/)).toHaveLength(30);
    // Sin más pendientes, el sentinel desaparece (y con él el observador).
    expect(container.querySelector("[data-sentinela]")).not.toBeInTheDocument();
  });

  it("buscar reinicia el lote: una plantilla más allá del primer lote aparece al filtrar", () => {
    render(<ContenidoPlantillas compacto plantillas={MUCHAS} onCargar={vi.fn()} />);
    expect(screen.queryByTitle("Cargar «Plantilla 29»")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Plantilla 29" } });
    expect(screen.getByTitle("Cargar «Plantilla 29»")).toBeInTheDocument();
  });

  it("hover de tarjeta: elevación + escala sutil en ~150ms y foco visible por teclado", () => {
    render(<ContenidoPlantillas compacto plantillas={[FOTO]} onCargar={vi.fn()} />);
    const tarjeta = screen.getByTitle(`Cargar «${FOTO.nombre}»`);
    expect(tarjeta.className).toContain("duration-150");
    expect(tarjeta.className).toContain("hover:shadow-lg");
    expect(tarjeta.className).toContain("motion-safe:hover:scale-[1.02]");
    expect(tarjeta.className).toContain("focus-visible:ring-2");
  });
});

// ── Galería a página completa (estado vacío de pages/Imagen): marca + lienzo en blanco ─────────

const CLARO: PlantillaDiseno = {
  ...FOTO,
  id: "m2-1",
  marca: "m2",
  marca_nombre: "Claro Sports",
  nombre: "Placa Claro",
};

describe("ContenidoPlantillas — agrupación por marca y «Lienzo en blanco»", () => {
  it("agruparPorMarca divide en secciones por marca, en orden alfabético", () => {
    render(
      <ContenidoPlantillas agruparPorMarca plantillas={[FOTO, CLARO]} onCargar={vi.fn()} />,
    );
    const cabeceras = screen.getAllByRole("heading").map((h) => h.textContent);
    expect(cabeceras).toEqual(["Claro Sports", "UnoTV"]);
    expect(screen.getByTitle(`Cargar «${FOTO.nombre}»`)).toBeInTheDocument();
    expect(screen.getByTitle(`Cargar «${CLARO.nombre}»`)).toBeInTheDocument();
  });

  it("dentro de una sección de marca, las categorías llevan cabecera propia solo si hay varias", () => {
    render(
      <ContenidoPlantillas
        agruparPorMarca
        plantillas={[ULTIMA, MARCADOR, CLARO]}
        onCargar={vi.fn()}
      />,
    );
    // m1 (UnoTV) tiene dos categorías -> cabeceras; m2 (Claro) una sola -> sin cabecera extra.
    expect(screen.getByRole("heading", { name: "Última hora" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Marcador" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "General" })).not.toBeInTheDocument();
  });

  it("onLienzoBlanco añade la tarjeta «Lienzo en blanco» al final y dispara el handler", () => {
    const onLienzoBlanco = vi.fn();
    render(
      <ContenidoPlantillas plantillas={[FOTO]} onCargar={vi.fn()} onLienzoBlanco={onLienzoBlanco} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /lienzo en blanco/i }));
    expect(onLienzoBlanco).toHaveBeenCalledTimes(1);
  });

  it("sin onLienzoBlanco no aparece la tarjeta (modo selector/panel)", () => {
    render(<ContenidoPlantillas plantillas={[FOTO]} onCargar={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /lienzo en blanco/i })).not.toBeInTheDocument();
  });

  it("galería vacía: copy unificado + la tarjeta «Lienzo en blanco» como CTA", () => {
    const onLienzoBlanco = vi.fn();
    render(<ContenidoPlantillas plantillas={[]} onCargar={vi.fn()} onLienzoBlanco={onLienzoBlanco} />);
    expect(screen.getByText(/aún no hay plantillas para esta marca/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /lienzo en blanco/i }));
    expect(onLienzoBlanco).toHaveBeenCalledTimes(1);
  });

  // ── REORDENAR (drag-and-drop) ────────────────────────────────────────────────────────────────
  const dtFalso = () => ({ effectAllowed: "", dropEffect: "", setData: vi.fn(), getData: () => "" });

  it("con onReordenar, arrastrar una tarjeta sobre otra de la misma sección avisa con la lista COMPLETA de ids en el nuevo orden", () => {
    const onReordenar = vi.fn();
    const f1 = { ...FOTO, id: "f1", nombre: "Uno" };
    const f2 = { ...FOTO, id: "f2", nombre: "Dos" };
    const f3 = { ...FOTO, id: "f3", nombre: "Tres" };
    const { container } = render(
      <ContenidoPlantillas plantillas={[f1, f2, f3]} onCargar={vi.fn()} onReordenar={onReordenar} />,
    );
    const card = (id: string) => container.querySelector(`[data-plantilla-id="${id}"]`)!;
    expect(card("f1")).toHaveAttribute("draggable", "true"); // modo reordenable
    const dt = dtFalso();
    fireEvent.dragStart(card("f3"), { dataTransfer: dt });
    fireEvent.dragEnter(card("f1"), { dataTransfer: dt });
    fireEvent.dragOver(card("f1"), { dataTransfer: dt });
    fireEvent.drop(card("f1"), { dataTransfer: dt });
    // f3 se inserta ANTES de f1: [f3, f1, f2].
    expect(onReordenar).toHaveBeenCalledWith(["f3", "f1", "f2"]);
  });

  it("no reordena entre secciones distintas (otra categoría): arrastrar de una a otra no hace nada", () => {
    const onReordenar = vi.fn();
    const general = { ...FOTO, id: "g1", categoria: "post" };
    const deportes = { ...FOTO, id: "d1", categoria: "deportes" };
    const { container } = render(
      <ContenidoPlantillas plantillas={[general, deportes]} onCargar={vi.fn()} onReordenar={onReordenar} />,
    );
    const card = (id: string) => container.querySelector(`[data-plantilla-id="${id}"]`)!;
    const dt = dtFalso();
    fireEvent.dragStart(card("g1"), { dataTransfer: dt });
    fireEvent.drop(card("d1"), { dataTransfer: dt });
    expect(onReordenar).not.toHaveBeenCalled();
  });

  it("sin onReordenar (modo selector) las tarjetas no son arrastrables", () => {
    const { container } = render(<ContenidoPlantillas plantillas={[FOTO]} onCargar={vi.fn()} />);
    expect(container.querySelector(`[data-plantilla-id="${FOTO.id}"]`)).not.toHaveAttribute("draggable");
  });
});

// ── Foto de muestra (puerta de galería) ──────────────────────────────────────────────────────────
// En modo GESTIÓN la tarjeta lleva varias acciones (Foto de muestra…, Duplicar, Borrar) en el
// kebab «⋮» (aria-label «Más acciones»); en modo SELECTOR no hay acciones, así que no aparece.
describe("ContenidoPlantillas — foto de muestra", () => {
  const gestion = { onDuplicar: vi.fn(), onBorrar: vi.fn() };

  it("ofrece «Foto y texto de muestra…» en el kebab de la tarjeta y lo invoca con la plantilla", async () => {
    const onFotoMuestra = vi.fn();
    render(<ContenidoPlantillas plantillas={[FOTO]} onCargar={vi.fn()} onFotoMuestra={onFotoMuestra} {...gestion} />);
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Foto y texto de muestra/ }));
    expect(onFotoMuestra).toHaveBeenCalledWith(FOTO);
  });

  it("con muestra ya asignada la entrada dice «Editar muestra…»", async () => {
    const conMuestra: PlantillaDiseno = { ...FOTO, foto_muestra: "plantillas/m.jpg", foto_muestra_url: "/api/media/plantillas/m.jpg" };
    render(<ContenidoPlantillas plantillas={[conMuestra]} onCargar={vi.fn()} onFotoMuestra={vi.fn()} {...gestion} />);
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(await screen.findByRole("menuitem", { name: /Editar muestra/ })).toBeInTheDocument();
  });

  it("con solo titular_muestra (sin foto) también dice «Editar muestra…»", async () => {
    const conTitular: PlantillaDiseno = { ...FOTO, titular_muestra: "LEO MESSI" };
    render(<ContenidoPlantillas plantillas={[conTitular]} onCargar={vi.fn()} onFotoMuestra={vi.fn()} {...gestion} />);
    fireEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(await screen.findByRole("menuitem", { name: /Editar muestra/ })).toBeInTheDocument();
  });

  it("en modo selector (sin acciones de gestión) no hay kebab ni «muestra»", () => {
    render(<ContenidoPlantillas plantillas={[FOTO]} onCargar={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Más acciones" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /muestra/i })).toBeNull();
  });
});

/**
 * Tests de la barra CONTEXTUAL de texto (patrón Canva):
 *  - Popover de ESPACIADO: un icono que agrupa Interletrado (px) e Interlineado (factor) como
 *    sliders con caja numérica editable, más el ANCLAJE vertical de la caja (`valign`).
 *  - aA MAYÚSCULAS: toggle de `mayusculas` (transforma en render, no destruye lo escrito).
 *  - TRANSPARENCIA: popover con slider de `opacidad` (0–100, 100 = opaco) para todas las capas.
 *  - COLOR: toda capa con color (texto, marco, overlay, logo wordmark) expone su ColorControl
 *    completo (espectro + hex + muestras) en la barra; elegir un sólido limpia el degradado.
 *  Todos los campos viajan en el documento y los respeta el export del servidor (`dibujar.mjs`):
 *  nada de propiedades que el editor muestre y el export ignore.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BarraContextual } from "./BarraContextual";
import { ProveedorEditor } from "./contexto";
import {
  documentoVacio,
  nuevaCapaImagen,
  nuevaCapaLogo,
  nuevaCapaMarco,
  nuevaCapaOverlay,
  nuevaCapaTexto,
  type Capa,
  type CapaMarco,
  type CapaTexto,
} from "./documento";
import { crearStoreEditor } from "./store";

const FORMATO = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

function montarCon(capa: Capa) {
  const doc = documentoVacio(FORMATO, "m1");
  doc.capas.push(capa);
  const store = crearStoreEditor(doc);
  store.getState().seleccionar(capa.id);
  render(
    // El ColorControl de la barra consulta la plantilla de marca vía react-query: hace falta el
    // QueryClient. El contexto de marca es opcional y aquí no se monta (sin colores de marca).
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ProveedorEditor store={store}>
        <BarraContextual onAbrirAjustes={vi.fn()} onReencuadrar={vi.fn()} onReemplazar={vi.fn()} />
      </ProveedorEditor>
    </QueryClientProvider>,
  );
  return store;
}

function montarConTexto(parcial: Partial<CapaTexto> = {}) {
  return montarCon(nuevaCapaTexto({ id: "t1", ...parcial }));
}

function capaTexto(store: ReturnType<typeof crearStoreEditor>): CapaTexto {
  return store.getState().documento.capas.find((c) => c.id === "t1") as CapaTexto;
}

// Abre el popover de espaciado (icono único, patrón Canva).
function abrirEspaciado() {
  fireEvent.click(screen.getByRole("button", { name: "Espaciado" }));
}

describe("BarraContextual — popover de espaciado: interlineado", () => {
  it("el slider actualiza `interlineado` (rango 1.0–2.5, paso 0.05)", () => {
    const store = montarConTexto({ interlineado: 1.15 });
    abrirEspaciado();
    const slider = screen.getByRole("slider", { name: "Interlineado" });
    expect(slider).toHaveAttribute("min", "1");
    expect(slider).toHaveAttribute("max", "2.5");
    expect(slider).toHaveAttribute("step", "0.05");
    fireEvent.change(slider, { target: { value: "1.5" } });
    expect(capaTexto(store).interlineado).toBe(1.5);
  });

  it("compatibilidad: un valor fuera del paso (1.14 por defecto) se muestra tal cual en la caja", () => {
    montarConTexto(); // default de fábrica: 1.14
    abrirEspaciado();
    const caja = screen.getByRole("spinbutton", { name: "Interlineado" }) as HTMLInputElement;
    expect(caja.value).toBe("1.14");
  });

  it("la caja numérica admite teclear un valor exacto (con decimales)", () => {
    const store = montarConTexto({ interlineado: 1.15 });
    abrirEspaciado();
    const caja = screen.getByRole("spinbutton", { name: "Interlineado" });
    fireEvent.change(caja, { target: { value: "1.85" } });
    fireEvent.blur(caja);
    expect(capaTexto(store).interlineado).toBe(1.85);
  });
});

describe("BarraContextual — popover de espaciado: interletrado (tracking)", () => {
  it("el slider actualiza `interletra` en px", () => {
    const store = montarConTexto({ interletra: 0 });
    abrirEspaciado();
    fireEvent.change(screen.getByRole("slider", { name: "Interletrado" }), { target: { value: "8" } });
    expect(capaTexto(store).interletra).toBe(8);
  });

  it("la caja numérica recorta al rango: tracking negativo hasta el mínimo (−20)", () => {
    const store = montarConTexto({ interletra: 0 });
    abrirEspaciado();
    const caja = screen.getByRole("spinbutton", { name: "Interletrado" });
    fireEvent.change(caja, { target: { value: "-99" } });
    fireEvent.blur(caja);
    expect(capaTexto(store).interletra).toBe(-20);
  });
});

describe("BarraContextual — popover de espaciado: anclar la caja (valign)", () => {
  it("con caja (h>0) los tres anclajes están activos y cambian `valign`", () => {
    const store = montarConTexto({ h: 400, valign: "arriba" });
    abrirEspaciado();
    const abajo = screen.getByRole("button", { name: "Anclar abajo" });
    expect(abajo).not.toBeDisabled();
    fireEvent.click(abajo);
    expect(capaTexto(store).valign).toBe("abajo");
    expect(screen.getByRole("button", { name: "Anclar abajo" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Anclar al centro" }));
    expect(capaTexto(store).valign).toBe("centro");
  });

  it("sin caja (h<=0, modo legado por `ancla`) los anclajes se apagan con tooltip", () => {
    const store = montarConTexto({ valign: "centro" }); // h de fábrica: 0
    abrirEspaciado();
    const arriba = screen.getByRole("button", { name: "Anclar arriba" });
    expect(arriba).toBeDisabled();
    expect(arriba).toHaveAttribute("title", "El anclaje vertical aplica al texto con caja (estira primero el alto de la caja)");
    fireEvent.click(arriba);
    expect(capaTexto(store).valign).toBe("centro"); // el clic no hace nada
  });
});

describe("BarraContextual — aA mayúsculas", () => {
  it("aA conmuta `mayusculas` (transformación en render; el texto crudo no se toca)", () => {
    const store = montarConTexto({ texto: "Hola ñandú" });
    const btn = screen.getByRole("button", { name: "Mayúsculas" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(btn);
    expect(capaTexto(store).mayusculas).toBe(true);
    expect(capaTexto(store).texto).toBe("Hola ñandú"); // lo escrito queda intacto
    expect(screen.getByRole("button", { name: "Mayúsculas" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(btn);
    expect(capaTexto(store).mayusculas).toBe(false);
  });
});

describe("BarraContextual — transparencia (todas las capas)", () => {
  it("el slider del popover edita `opacidad` (100 = opaco) en una capa de texto", () => {
    const store = montarConTexto();
    fireEvent.click(screen.getByRole("button", { name: "Transparencia" }));
    fireEvent.change(screen.getByRole("slider", { name: "Transparencia" }), { target: { value: "40" } });
    expect(capaTexto(store).opacidad).toBeCloseTo(0.4);
  });

  it("también existe para capas NO de texto (imagen) y edita su `opacidad`", () => {
    const store = montarCon(nuevaCapaImagen("m-1", { id: "i1" }));
    fireEvent.click(screen.getByRole("button", { name: "Transparencia" }));
    fireEvent.change(screen.getByRole("slider", { name: "Transparencia" }), { target: { value: "75" } });
    const capa = store.getState().documento.capas.find((c) => c.id === "i1")!;
    expect(capa.opacidad).toBeCloseTo(0.75);
  });
});

describe("BarraContextual — tamaño de letra (regresión)", () => {
  it("el stepper de tamaño sigue editando `tamano`", () => {
    const store = montarConTexto({ tamano: 64 });
    const input = screen.getByLabelText("Tamaño de letra");
    fireEvent.change(input, { target: { value: "72" } });
    fireEvent.blur(input);
    expect(capaTexto(store).tamano).toBe(72);
  });
});

describe("BarraContextual — cursiva (I) y subrayado (U)", () => {
  it("I conmuta `cursiva` en una familia CON itálica (Barlow)", () => {
    const store = montarConTexto(); // familia por defecto: Barlow
    const btn = screen.getByRole("button", { name: "Cursiva" });
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute("title", "Cursiva");
    fireEvent.click(btn);
    expect(capaTexto(store).cursiva).toBe(true);
    fireEvent.click(btn);
    expect(capaTexto(store).cursiva).toBe(false);
  });

  it("I queda DESHABILITADO (con tooltip) si la familia no tiene itálica (Anton)", () => {
    const store = montarConTexto({ familia: "Anton" });
    const btn = screen.getByRole("button", { name: "Cursiva" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "Esta fuente no tiene cursiva");
    fireEvent.click(btn);
    expect(capaTexto(store).cursiva).toBeUndefined(); // el clic no hace nada
  });

  it("las familias lógicas legadas ('sans'/'condensada') resuelven a Barlow: I habilitado", () => {
    montarConTexto({ familia: "condensada" });
    expect(screen.getByRole("button", { name: "Cursiva" })).not.toBeDisabled();
  });

  it("U conmuta `subrayado`", () => {
    const store = montarConTexto();
    const btn = screen.getByRole("button", { name: "Subrayado" });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(capaTexto(store).subrayado).toBe(true);
    fireEvent.click(btn);
    expect(capaTexto(store).subrayado).toBe(false);
  });

  it("U queda DESHABILITADO para el texto en arco (curva), con tooltip", () => {
    const store = montarConTexto({ curva: { radio: 600 } });
    const btn = screen.getByRole("button", { name: "Subrayado" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "El texto en arco no admite subrayado");
    fireEvent.click(btn);
    expect(capaTexto(store).subrayado).toBeUndefined();
  });
});

describe("BarraContextual — color (selector completo en la barra)", () => {
  it("texto: la entrada hexadecimal edita `color` y LIMPIA el degradado del relleno", () => {
    const store = montarConTexto({ relleno_degradado: { desde: "#000000", hasta: "#FFFFFF" } });
    fireEvent.click(screen.getByRole("button", { name: "Color del texto" }));
    const hex = screen.getByRole("textbox", { name: "Color en hexadecimal" });
    fireEvent.change(hex, { target: { value: "0057b7" } }); // sin '#' y en minúsculas: se normaliza
    fireEvent.keyDown(hex, { key: "Enter" });
    expect(capaTexto(store).color).toBe("#0057B7");
    expect(capaTexto(store).relleno_degradado).toBeNull();
  });

  it("texto: la paleta de sólidos predeterminados aplica con un clic", () => {
    const store = montarConTexto();
    fireEvent.click(screen.getByRole("button", { name: "Color del texto" }));
    fireEvent.click(screen.getByTitle("#FFDE59"));
    expect(capaTexto(store).color).toBe("#FFDE59");
  });

  it("marco: el relleno se edita desde la barra (y limpia el degradado)", () => {
    const store = montarCon(nuevaCapaMarco({ id: "m1", relleno: "#111111", relleno_degradado: { desde: "#000000", hasta: "#FFFFFF" } }));
    fireEvent.click(screen.getByRole("button", { name: "Color de relleno" }));
    fireEvent.click(screen.getByTitle("#FF5757"));
    const marco = store.getState().documento.capas.find((c) => c.id === "m1") as CapaMarco;
    expect(marco.relleno).toBe("#FF5757");
    expect(marco.relleno_degradado).toBeNull();
  });

  it("marco: el color del borde se edita desde la barra; la forma «línea» no ofrece relleno", () => {
    const store = montarCon(nuevaCapaMarco({ id: "m1", forma: "linea" }));
    expect(screen.queryByRole("button", { name: "Color de relleno" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Color del borde" }));
    fireEvent.click(screen.getByTitle("#5271FF"));
    const marco = store.getState().documento.capas.find((c) => c.id === "m1") as CapaMarco;
    expect(marco.borde).toEqual({ color: "#5271FF", grosor: 6 }); // el grosor de fábrica no se pisa
  });

  it("overlay: su color se edita desde la barra", () => {
    const store = montarCon(nuevaCapaOverlay({ id: "o1" }));
    fireEvent.click(screen.getByRole("button", { name: "Color del overlay" }));
    fireEvent.click(screen.getByTitle("#38B6FF"));
    const overlay = store.getState().documento.capas.find((c) => c.id === "o1")!;
    expect((overlay as { color: string }).color).toBe("#38B6FF");
  });

  it("logo wordmark: expone color y fondo; el logo de imagen, ninguno", () => {
    const store = montarCon(nuevaCapaLogo("", { id: "l1" })); // sin media => wordmark
    fireEvent.click(screen.getByRole("button", { name: "Fondo del wordmark" }));
    fireEvent.click(screen.getByTitle("#00BF63"));
    const logo = store.getState().documento.capas.find((c) => c.id === "l1")!;
    expect((logo as { wordmark: { fondo: string } }).wordmark.fondo).toBe("#00BF63");
  });

  it("logo de IMAGEN: sin controles de color en la barra", () => {
    montarCon(nuevaCapaLogo("media/logo.png", { id: "l2" }));
    expect(screen.queryByRole("button", { name: "Color del wordmark" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Fondo del wordmark" })).toBeNull();
  });
});

describe("BarraContextual — tachado (S)", () => {
  it("S conmuta `tachado` (combinable con el subrayado)", () => {
    const store = montarConTexto({ subrayado: true });
    const btn = screen.getByRole("button", { name: "Tachado" });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(capaTexto(store).tachado).toBe(true);
    expect(capaTexto(store).subrayado).toBe(true); // no se pisan
    fireEvent.click(btn);
    expect(capaTexto(store).tachado).toBe(false);
  });

  it("S queda DESHABILITADO para el texto en arco (curva), con tooltip (mismo trato que U)", () => {
    const store = montarConTexto({ curva: { radio: 600 } });
    const btn = screen.getByRole("button", { name: "Tachado" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "El texto en arco no admite tachado");
    fireEvent.click(btn);
    expect(capaTexto(store).tachado).toBeUndefined();
  });
});

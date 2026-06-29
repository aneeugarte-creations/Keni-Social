import { render, screen } from "@testing-library/react";
import { Newspaper, Rss, Sparkles } from "lucide-react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SelectorSeccion } from "@/components/layout/SelectorSeccion";
import type { ItemTabHub } from "@/components/layout/hub-tabs";

const PESTANAS: ItemTabHub[] = [
  { ruta: "/operacion/investigacion", etiqueta: "Noticias", icono: Newspaper, end: true },
  { ruta: "/operacion/investigacion/contenidos", etiqueta: "Publicaciones", icono: Sparkles },
  { ruta: "/operacion/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
];

function renderEn(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <SelectorSeccion pestanas={PESTANAS} pathname={pathname} />
    </MemoryRouter>,
  );
}

describe("SelectorSeccion · sección activa", () => {
  it("el trigger muestra la pestaña de coincidencia exacta (tab raíz con `end`)", () => {
    renderEn("/operacion/investigacion");
    expect(screen.getByRole("combobox", { name: /sección/i })).toHaveTextContent("Noticias");
  });

  it("matchea sub-rutas de una pestaña no-`end`", () => {
    renderEn("/operacion/investigacion/contenidos/algo");
    expect(screen.getByRole("combobox", { name: /sección/i })).toHaveTextContent("Publicaciones");
  });

  it("elige la coincidencia más específica (ruta más larga), no el tab raíz", () => {
    renderEn("/operacion/investigacion/fuentes");
    expect(screen.getByRole("combobox", { name: /sección/i })).toHaveTextContent("Fuentes");
  });
});

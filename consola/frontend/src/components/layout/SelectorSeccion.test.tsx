import { render, screen } from "@testing-library/react";
import { Newspaper, Rss, Sparkles } from "lucide-react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SelectorSeccion } from "@/components/layout/SelectorSeccion";
import type { ItemTabHub } from "@/components/layout/hub-tabs";

const PESTANAS: ItemTabHub[] = [
  { ruta: "/datos/investigacion", etiqueta: "Noticias", icono: Newspaper, end: true },
  { ruta: "/datos/investigacion/contenidos", etiqueta: "Publicaciones", icono: Sparkles },
  { ruta: "/datos/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
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
    renderEn("/datos/investigacion");
    expect(screen.getByRole("combobox", { name: /sección/i })).toHaveTextContent("Noticias");
  });

  it("matchea sub-rutas de una pestaña no-`end`", () => {
    renderEn("/datos/investigacion/contenidos/algo");
    expect(screen.getByRole("combobox", { name: /sección/i })).toHaveTextContent("Publicaciones");
  });

  it("elige la coincidencia más específica (ruta más larga), no el tab raíz", () => {
    renderEn("/datos/investigacion/fuentes");
    expect(screen.getByRole("combobox", { name: /sección/i })).toHaveTextContent("Fuentes");
  });
});

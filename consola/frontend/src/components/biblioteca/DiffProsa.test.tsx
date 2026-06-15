/**
 * DiffProsa: diff de prosa legible (verde = añadido, rojo tachado = borrado), con las
 * `{{VARIABLES}}` como tokens atómicos (el diff nunca parte una variable) y modo
 * "solo cambios" que colapsa los párrafos sin tocar.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DiffProsa } from "./DiffProsa";

describe("DiffProsa", () => {
  it("marca lo añadido con <ins> y lo borrado con <del>", () => {
    const { container } = render(
      <DiffProsa antes="El copy debe ser corto." despues="El copy debe ser largo." />,
    );
    expect(container.querySelector("del")?.textContent).toBe("corto.");
    expect(container.querySelector("ins")?.textContent).toBe("largo.");
  });

  it("trata {{VAR}} como token atómico (no la parte por la mitad)", () => {
    const { container } = render(
      <DiffProsa antes="Habla de {{MARCA}} hoy" despues="Habla de {{TEMA}} hoy" />,
    );
    // La variable entera cambia: el chip viejo en <del> y el nuevo en <ins>.
    expect(container.querySelector("del")?.textContent).toBe("MARCA");
    expect(container.querySelector("ins")?.textContent).toBe("TEMA");
  });

  it("sin diferencias avisa 'Sin cambios'", () => {
    render(<DiffProsa antes="Igual." despues="Igual." />);
    expect(screen.getByText(/Sin cambios/)).toBeInTheDocument();
  });

  it("'solo cambios' colapsa los párrafos sin tocar y se despliegan al clic", () => {
    const antes = "Uno.\n\nDos.\n\nTres.\n\nViejo.";
    const despues = "Uno.\n\nDos.\n\nTres.\n\nNuevo.";
    render(<DiffProsa antes={antes} despues={despues} soloCambios />);
    const separador = screen.getByText(/3 párrafos sin cambios/);
    expect(screen.queryByText("Dos.")).not.toBeInTheDocument();
    fireEvent.click(separador);
    expect(screen.getByText("Dos.")).toBeInTheDocument();
  });

  it("un cambio de SOLO whitespace no produce ningún resaltado", () => {
    // Mismo contenido, distinto whitespace (espacios extra y un salto): jamás se resalta.
    const { container } = render(
      <DiffProsa antes={"Hola    mundo cruel."} despues={"Hola mundo\ncruel."} />,
    );
    expect(container.querySelector("ins")).toBeNull();
    expect(container.querySelector("del")).toBeNull();
  });

  it("espacios sobrantes idénticos por lo demás dan 'Sin cambios'", () => {
    // Tras normalizar, ambos lados colapsan a lo mismo: ni bloque de cambio.
    render(<DiffProsa antes={"Hola   mundo."} despues={"Hola mundo."} />);
    expect(screen.getByText(/Sin cambios/)).toBeInTheDocument();
  });

  it("no muestra el frontmatter como contenido ni como cambio", () => {
    const antes = "---\nslug: viejo\n---\nEl cuerpo no cambia.";
    const despues = "---\nslug: nuevo\n---\nEl cuerpo no cambia.";
    const { container } = render(<DiffProsa antes={antes} despues={despues} />);
    expect(container.textContent).not.toContain("slug");
    expect(container.textContent).not.toContain("---");
    expect(screen.getByText(/Sin cambios/)).toBeInTheDocument();
  });

  it("no escupe markdown crudo: encabezados, negrita y viñetas se limpian", () => {
    const { container } = render(
      <DiffProsa
        antes={"## Titular\n\n- punto"}
        despues={"## Titular nuevo\n\n- punto"}
      />,
    );
    expect(container.textContent).not.toContain("##");
    expect(container.textContent).not.toContain("- punto");
    expect(container.textContent).toContain("Titular");
    // El cambio real de palabra sí se resalta.
    expect(container.querySelector("ins")?.textContent?.trim()).toBe("nuevo");
  });

  it("la viñeta `*` vs `-` no genera un diff fantasma de formato", () => {
    const { container } = render(
      <DiffProsa antes={"* uno\n* dos"} despues={"- uno\n- dos"} />,
    );
    expect(container.querySelector("ins")).toBeNull();
    expect(container.querySelector("del")).toBeNull();
  });

  it("avisa de cambio de SOLO formato cuando el texto plano es el mismo", () => {
    render(<DiffProsa antes={"Esto importa."} despues={"**Esto** importa."} />);
    expect(screen.getByText(/Solo cambios de formato/)).toBeInTheDocument();
    expect(screen.queryByText(/^Sin cambios\.$/)).not.toBeInTheDocument();
  });

  it("un cambio de solo frontmatter sigue siendo 'Sin cambios' (no formato)", () => {
    render(
      <DiffProsa
        antes={"---\nslug: viejo\n---\nEl cuerpo no cambia."}
        despues={"---\nslug: nuevo\n---\nEl cuerpo no cambia."}
      />,
    );
    expect(screen.getByText(/^Sin cambios\.$/)).toBeInTheDocument();
    expect(screen.queryByText(/Solo cambios de formato/)).not.toBeInTheDocument();
  });

  it("no escupe caracteres crudos de fence, tabla, backslash ni autolink", () => {
    const antes = [
      "Intro vieja.",
      "",
      "```ts\nconst x = 1\n```",
      "",
      "| A | B |\n| --- | --- |\n| 1 | 2 |",
      "",
      "Línea con break\\",
      "Ver <https://keni.io/x> y <br> fin.",
    ].join("\n");
    const despues = antes.replace("Intro vieja.", "Intro nueva.");
    const { container } = render(<DiffProsa antes={antes} despues={despues} />);
    const txt = container.textContent ?? "";
    expect(txt).not.toContain("```");
    expect(txt).not.toContain("|");
    expect(txt).not.toContain("\\");
    expect(txt).not.toContain("<br>");
    expect(txt).not.toContain("<https://keni.io/x>");
    expect(txt).toContain("https://keni.io/x");
    // El cambio real de palabra sí se resalta.
    expect(container.querySelector("ins")?.textContent?.trim()).toBe("nueva.");
  });

  it("una variable `{{VAR}}` se pinta como pastilla (sin las llaves crudas)", () => {
    const { container } = render(
      <DiffProsa antes="Sobre {{MARCA}} hoy." despues="Sobre {{MARCA}} ahora." />,
    );
    // El chip muestra el nombre sin `{{ }}`.
    expect(container.textContent).toContain("MARCA");
    expect(container.textContent).not.toContain("{{MARCA}}");
    // Y el cambio real de palabra sí se resalta.
    expect(container.querySelector("ins")?.textContent).toBe("ahora.");
    expect(container.querySelector("del")?.textContent).toBe("hoy.");
  });
});

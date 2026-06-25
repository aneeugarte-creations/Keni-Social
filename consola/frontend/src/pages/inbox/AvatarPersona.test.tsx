import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AvatarPersona } from "./AvatarPersona";

describe("AvatarPersona", () => {
  it("muestra la inicial del nombre cuando no hay avatar", () => {
    render(<AvatarPersona nombre="Ana Audiencia" avatar={null} />);
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("pinta la foto cuando hay avatar", () => {
    render(<AvatarPersona nombre="Ana" avatar="http://img/a.jpg" />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "http://img/a.jpg");
  });

  it("cae a la inicial si la imagen del avatar falla al cargar (URL caducada)", () => {
    render(<AvatarPersona nombre="Ana" avatar="http://img/expirada.jpg" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });
});

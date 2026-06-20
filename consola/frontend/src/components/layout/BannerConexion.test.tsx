import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BannerConexion } from "@/components/layout/BannerConexion";
import { registrarExitoRed, registrarFalloRed } from "@/lib/estado-red";

afterEach(() => {
  // El store es un singleton de módulo: un éxito reinicia el contador y apaga el banner,
  // dejándolo limpio para el siguiente caso.
  act(() => {
    registrarExitoRed();
  });
});

describe("BannerConexion · conexión degradada", () => {
  it("no aparece sin fallos", () => {
    render(<BannerConexion />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("aparece al cruzar el umbral de fallos consecutivos y se va al primer éxito", () => {
    render(<BannerConexion />);

    // Un solo fallo no basta (umbral anti-parpadeo ante un blip puntual).
    act(() => {
      registrarFalloRed();
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    // Al segundo fallo seguido, aparece.
    act(() => {
      registrarFalloRed();
    });
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/Problemas de conexión con la consola/i)).toBeInTheDocument();

    // El primer éxito lo retira.
    act(() => {
      registrarExitoRed();
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

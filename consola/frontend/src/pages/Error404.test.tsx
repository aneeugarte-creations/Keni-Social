/**
 * Tests de la página 404 dedicada y de su cableado en el catch-all del router.
 *
 * Verifica que:
 *  - El componente Error404 muestra el mensaje "Página no encontrada (404)",
 *    el path que no existía y los botones "Volver al feed" / "Atrás".
 *  - Una URL desconocida renderiza la 404 (NO rebota en silencio al feed): el
 *    catch-all `path: "*"` usa <Error404/>, no <Navigate to="/operacion/feed"/>.
 *  - Desde la 404 se puede navegar a otra sección (el enlace "Volver al feed").
 */
import { fireEvent, render, screen } from "@testing-library/react";
import {
  createMemoryRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
import { describe, expect, it } from "vitest";

import Error404 from "./Error404";

/** Router mínimo que ESPEJA el cableado de router.tsx: el catch-all es la 404. */
function construirRouter(rutaInicial: string) {
  return createMemoryRouter(
    [
      // Una ruta-índice real (la home del equipo) y una sección cualquiera.
      { path: "/", element: <Navigate to="/operacion/feed" replace /> },
      { path: "/operacion/feed", element: <p>Feed del equipo</p> },
      // Catch-all: 404 dedicada, igual que en router.tsx.
      { path: "*", element: <Error404 /> },
    ],
    { initialEntries: [rutaInicial] },
  );
}

describe("Error404", () => {
  it("una URL desconocida renderiza la 404 (no redirige al feed)", () => {
    render(<RouterProvider router={construirRouter("/ruta/que/no/existe")} />);
    expect(screen.getByText("Página no encontrada (404)")).toBeInTheDocument();
    // Muestra el path que no se encontró.
    expect(screen.getByText("/ruta/que/no/existe")).toBeInTheDocument();
    // NO rebotó al feed.
    expect(screen.queryByText("Feed del equipo")).not.toBeInTheDocument();
  });

  it("ofrece volver al feed y atrás", () => {
    render(<RouterProvider router={construirRouter("/nope")} />);
    const volver = screen.getByRole("link", { name: /volver al feed/i });
    expect(volver).toHaveAttribute("href", "/operacion/feed");
    expect(screen.getByRole("button", { name: /atrás/i })).toBeInTheDocument();
  });

  it("desde la 404 se navega al feed al pulsar 'Volver al feed'", () => {
    render(<RouterProvider router={construirRouter("/nope")} />);
    fireEvent.click(screen.getByRole("link", { name: /volver al feed/i }));
    expect(screen.getByText("Feed del equipo")).toBeInTheDocument();
    expect(screen.queryByText("Página no encontrada (404)")).not.toBeInTheDocument();
  });
});

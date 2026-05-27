import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Sidebar } from "@/components/layout/Sidebar";
import { navegacionParaRol } from "@/components/layout/navegacion";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { RolUsuario } from "@/types";

/** Render del sidebar con un usuario de sesión simulado del rol indicado. */
function renderSidebar(rol: RolUsuario) {
  const valor: ValorSesion = {
    usuario: { id: "u1", usuario: "x", rol, debe_cambiar_password: false },
    cargando: false,
    iniciarSesion: async () => {},
    cerrarSesion: async () => {},
    refrescar: async () => {},
  };
  return render(
    <SesionContexto.Provider value={valor}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </SesionContexto.Provider>,
  );
}

describe("Sidebar · visibilidad por rol", () => {
  it("muestra 'Usuarios' en el nav cuando el rol es admin", () => {
    renderSidebar("admin");
    expect(screen.getByRole("link", { name: /usuarios/i })).toBeInTheDocument();
  });

  it("oculta 'Usuarios' del nav cuando el rol es editor", () => {
    renderSidebar("editor");
    expect(screen.queryByRole("link", { name: /usuarios/i })).not.toBeInTheDocument();
    // Las páginas de trabajo siguen visibles para el editor.
    expect(screen.getByRole("link", { name: /generar copy/i })).toBeInTheDocument();
  });
});

describe("navegacionParaRol", () => {
  it("incluye el ítem soloAdmin únicamente para admin", () => {
    const conAdmin = navegacionParaRol(true)
      .flatMap((g) => g.items)
      .map((i) => i.ruta);
    const sinAdmin = navegacionParaRol(false)
      .flatMap((g) => g.items)
      .map((i) => i.ruta);

    expect(conAdmin).toContain("/usuarios");
    expect(sinAdmin).not.toContain("/usuarios");
  });
});

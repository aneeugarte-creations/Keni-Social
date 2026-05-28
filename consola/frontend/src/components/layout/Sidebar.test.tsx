import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { Sidebar } from "@/components/layout/Sidebar";
import { navegacionParaRol } from "@/components/layout/navegacion";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { RolUsuario } from "@/types";

function valorSesion(rol: RolUsuario): ValorSesion {
  return {
    usuario: { id: "u1", usuario: "x", rol, debe_cambiar_password: false },
    cargando: false,
    iniciarSesion: async () => {},
    cerrarSesion: async () => {},
    refrescar: async () => {},
  };
}

/** Render del sidebar con un usuario de sesión simulado del rol indicado. */
function renderSidebar(rol: RolUsuario) {
  return render(
    <SesionContexto.Provider value={valorSesion(rol)}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </SesionContexto.Provider>,
  );
}

/** Render del menú del avatar (donde ahora viven los ajustes). */
function renderAvatarMenu(rol: RolUsuario) {
  return render(
    <SesionContexto.Provider value={valorSesion(rol)}>
      <MemoryRouter>
        <CuentaUsuario />
      </MemoryRouter>
    </SesionContexto.Provider>,
  );
}

describe("Sidebar · estructura", () => {
  it("muestra las páginas del día a día para cualquier rol", () => {
    renderSidebar("editor");
    expect(screen.getByRole("link", { name: /panel/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /generación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /investigación/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /publicaciones/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /agentes/i })).toBeInTheDocument();
  });

  it("no muestra los ajustes en el sidebar (ahora cuelgan del avatar)", () => {
    renderSidebar("admin");
    expect(screen.queryByRole("link", { name: /^configuración$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^usuarios$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^mi cuenta$/i })).not.toBeInTheDocument();
  });
});

describe("Avatar · visibilidad de Usuarios por rol", () => {
  it("muestra 'Usuarios' al abrir el menú cuando el rol es admin", () => {
    renderAvatarMenu("admin");
    fireEvent.click(screen.getByRole("button", { name: /x.*administrador/i }));
    expect(screen.getByRole("menuitem", { name: /usuarios/i })).toBeInTheDocument();
  });

  it("oculta 'Usuarios' del menú cuando el rol es editor", () => {
    renderAvatarMenu("editor");
    fireEvent.click(screen.getByRole("button", { name: /x.*editor/i }));
    expect(screen.queryByRole("menuitem", { name: /usuarios/i })).not.toBeInTheDocument();
    // Las demás opciones siguen visibles.
    expect(screen.getByRole("menuitem", { name: /mi cuenta/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /configuración/i })).toBeInTheDocument();
  });
});

describe("navegacionParaRol", () => {
  it("no expone rutas admin-only en el sidebar (ya no las hay)", () => {
    const conAdmin = navegacionParaRol(true).flatMap((g) => g.items);
    const sinAdmin = navegacionParaRol(false).flatMap((g) => g.items);
    expect(conAdmin.some((i) => i.soloAdmin)).toBe(false);
    expect(conAdmin.map((i) => i.ruta)).toEqual(sinAdmin.map((i) => i.ruta));
  });
});

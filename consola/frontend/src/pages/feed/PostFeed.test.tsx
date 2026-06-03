import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { Publicacion, UsuarioSesion } from "@/types";

import { PostFeed } from "./PostFeed";

/** Una `Publicacion` completa con valores por defecto (sobreescribibles). */
function pub(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "p1",
    contenido_id: "c1",
    titulo: "Tema",
    marca: "piso-15",
    marca_nombre: "Piso 15",
    red: "x",
    red_nombre: "X",
    contenido: "Copy ya redactado por la IA.",
    copy_in: "",
    estado: "pendiente",
    veredicto: "",
    autor_id: "",
    autor_nombre: "",
    enviado_a_revision_en: "",
    revisor_id: "",
    revisor_nombre: "",
    revisado_en: "",
    preparado_en: "",
    id_post_metricool: "",
    tipo_contenido: "ia",
    imagen_fuente: "",
    foto: "",
    falta_copy: false,
    falta_imagen: true,
    falta_revision: true,
    falta_publicar: true,
    fecha_creacion: "",
    fecha_actualizacion: "",
    fecha_programada: "",
    fecha_fuente: "",
    origen: "pipeline",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    etapa_ia: "generando_arte",
    ...over,
  } as Publicacion;
}

function renderPost(publicacion: Publicacion, usuario: Partial<UsuarioSesion> = {}) {
  const valor: ValorSesion = {
    usuario: { id: "u1", usuario: "revisor", rol: "editor", debe_cambiar_password: false, ...usuario } as UsuarioSesion,
    cargando: false,
    iniciarSesion: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={valor}>
        <PostFeed publicacion={publicacion} />
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("PostFeed · firma IA y aviso de bloqueo", () => {
  it("pieza autogenerada (sin autor) firma como «IA», no «desconocido»", () => {
    renderPost(pub({ autor_nombre: "" }));
    expect(screen.getByText("IA")).toBeInTheDocument();
    expect(screen.queryByText(/desconocido/i)).not.toBeInTheDocument();
  });

  it("pieza posteada por una persona muestra su nombre, no «IA»", () => {
    renderPost(pub({ autor_nombre: "Ana" }));
    expect(screen.getByText(/Ana/)).toBeInTheDocument();
    expect(screen.queryByText(/^IA$/)).not.toBeInTheDocument();
  });

  it("el «Me gusta» está deshabilitado y avisa de qué falta cuando la IA aún la prepara", () => {
    renderPost(pub({ etapa_ia: "generando_arte" }));
    expect(screen.getByRole("button", { name: /me gusta/i })).toBeDisabled();
    // Aviso VISIBLE (no solo tooltip) de qué falta.
    expect(screen.getByText(/Falta el arte/i)).toBeInTheDocument();
  });
});

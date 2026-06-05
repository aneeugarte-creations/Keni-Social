import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { Publicacion, UsuarioSesion } from "@/types";

import { PostFeed } from "./PostFeed";

// Los avisos de bloqueo del "me gusta" son toasts (no texto fijo): mockeamos sonner para asertarlos.
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

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
    verificarMfa: vi.fn(),
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
  beforeEach(() => {
    vi.clearAllMocks();
  });

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

  it("ofrece me gusta y comentar (iconos), NO un botón Editar; la tarjeta abre el editor", () => {
    renderPost(pub());
    expect(screen.getByRole("button", { name: "Me gusta" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comentar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^editar/i })).not.toBeInTheDocument();
    // La tarjeta completa es clicable (abre el editor).
    expect(screen.getByRole("button", { name: /abrir para editar/i })).toBeInTheDocument();
  });

  it("«Me gusta» cuando NO toca no aprueba: avisa con un toast (falta la imagen)", () => {
    renderPost(pub({ etapa_ia: "generando_arte" }));
    fireEvent.click(screen.getByRole("button", { name: "Me gusta" }));
    expect(toast).toHaveBeenCalledWith(expect.stringMatching(/Falta la imagen/i));
  });

  it("pieza lista pero aún en borrador: el badge dice 'Lista para revisar' y like avisa que entra sola", () => {
    renderPost(pub({ etapa_ia: "lista_para_revisar" }));
    expect(screen.getByText(/Lista para revisar/i)).toBeInTheDocument();
    expect(screen.queryByText(/Falta el copy/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Me gusta" }));
    expect(toast).toHaveBeenCalledWith(expect.stringMatching(/no está en revisión|entra sola/i));
  });
});

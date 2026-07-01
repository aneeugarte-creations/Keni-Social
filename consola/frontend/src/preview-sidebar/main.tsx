/**
 * Vista previa del Sidebar/AppShell REALES en localhost, sin backend: siembra el QueryClient
 * con la MISMA forma que devuelve la API (`/api/catalogo`, `/api/sistema/uso`, `/api/limites`) y
 * pone contextos de sesión/marca a mano, así que lo que se ve aquí es el componente de producción
 * de verdad (mismas clases Tailwind, mismo AppShell), no una aproximación. Contenido en blanco
 * (sin rutas hijas) a propósito: solo importa la barra. NO entra en el build de producción; se
 * abre navegando a `/preview-sidebar.html` con `npm run dev`.
 */
/* eslint-disable react-refresh/only-export-components */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import "@/index.css";

import { AppShell } from "@/components/layout/AppShell";
import { FiltrosPublicacionProvider } from "@/hooks/use-filtros-contenido";
import { MarcaActivaContexto, type ValorMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { TemaProvider } from "@/hooks/use-tema";
import type { UsuarioSesion } from "@/types/auth";
import { CATALOGO_MUESTRA, USO_MUESTRA } from "./datos";

const queryClient = new QueryClient();
queryClient.setQueryData(["catalogo"], CATALOGO_MUESTRA);
queryClient.setQueryData(["uso-cuenta"], { cuentas: USO_MUESTRA });
queryClient.setQueryData(["limites"], { limites: [] });

const USUARIO_MUESTRA: UsuarioSesion = {
  id: "1",
  usuario: "ane",
  rol: "admin",
  nombre: "Ane Ugarte",
  debe_cambiar_password: false,
};

const SESION_MUESTRA: ValorSesion = {
  usuario: USUARIO_MUESTRA,
  cargando: false,
  errorConexion: false,
  motivoCaida: null,
  iniciarSesion: async () => ({ mfaRequerido: false }),
  verificarConPasskey: async () => {},
  entrarConPasskey: async () => {},
  cerrarSesion: async () => {},
  refrescar: async () => {},
};

const MARCA_MUESTRA: ValorMarcaActiva = {
  marcaActiva: null,
  marcaPrimaria: null,
  enMarcaPrimaria: true,
  fueraDeCasa: false,
  esMultiMarca: true,
  puedeTodas: true,
  marcaActivaEsNoticias: true,
  etiquetaInvestigacion: "Noticias",
  marcasParaSwitch: [],
  nombreActiva: null,
  cambiarMarca: () => {},
  volverAPrimaria: () => {},
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TemaProvider>
        <SesionContexto.Provider value={SESION_MUESTRA}>
          <MarcaActivaContexto.Provider value={MARCA_MUESTRA}>
            <FiltrosPublicacionProvider>
              <MemoryRouter initialEntries={["/operacion/investigacion"]}>
                <Routes>
                  <Route path="*" element={<AppShell />} />
                </Routes>
              </MemoryRouter>
            </FiltrosPublicacionProvider>
          </MarcaActivaContexto.Provider>
        </SesionContexto.Provider>
      </TemaProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);

import { createRoot } from "react-dom/client";

import "../index.css";

import { ShellCongelado } from "./ShellCongelado";

// Página de mantenimiento: monta el cascarón congelado. Sin StrictMode (no hay efectos que
// validar) ni providers de red. La recarga automática la dispara el <script> de la página.
const raiz = document.getElementById("mantenimiento");
if (raiz) {
  createRoot(raiz).render(<ShellCongelado />);
}

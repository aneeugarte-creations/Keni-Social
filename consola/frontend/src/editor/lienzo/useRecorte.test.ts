// El modo recorte ya no es solo de imágenes: un objeto sin píxeles (forma/línea/logo) entra al modo
// vía el botón "Recortar" (prop `recorteId`) y se recorta su RECUADRO. Cancelar restaura el recuadro
// de entrada (igual que el recorte de foto restaura el `crop`). El doble clic sigue siendo de imagen.

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { documentoVacio, nuevaCapaMarco } from "../documento";
import { crearStoreEditor } from "../store";
import { useRecorte } from "./useRecorte";

const sinRotacion = () => true;

function montar(recorteId: string | null) {
  const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
  const marco = nuevaCapaMarco({ id: "marco-1", x: 100, y: 100, w: 200, h: 100 });
  store.getState().agregar(marco);
  const onSalirRecorte = vi.fn();
  const hook = renderHook(({ id }) =>
    useRecorte({
      store,
      documento: store.getState().documento,
      recorteId: id,
      onSalirRecorte,
      capaReencuadre: null,
      sinRotacion,
    }),
    { initialProps: { id: recorteId } },
  );
  return { store, onSalirRecorte, hook };
}

describe("useRecorte — recorte de RECUADRO para objetos no-imagen", () => {
  it("reconoce un marco (no-imagen) como capa en recorte vía recorteId", () => {
    const { hook } = montar("marco-1");
    expect(hook.result.current.capaRecorte?.id).toBe("marco-1");
    expect(hook.result.current.capaRecorte?.tipo).toBe("marco");
  });

  it("cancelar RESTAURA el recuadro de entrada y sale del modo", () => {
    const { store, onSalirRecorte, hook } = montar("marco-1");
    // Recorta el recuadro (como haría el overlay arrastrando un tirador).
    act(() => store.getState().actualizar("marco-1", { x: 150, y: 100, w: 150, h: 100 }));
    expect(store.getState().documento.capas.find((c) => c.id === "marco-1")?.w).toBe(150);
    // Cancelar vuelve al recuadro de entrada (200×100 en 100,100) y avisa al padre para cerrar.
    act(() => hook.result.current.cancelarRecorte());
    const m = store.getState().documento.capas.find((c) => c.id === "marco-1");
    expect(m).toMatchObject({ x: 100, y: 100, w: 200, h: 100 });
    expect(onSalirRecorte).toHaveBeenCalledTimes(1);
  });
});

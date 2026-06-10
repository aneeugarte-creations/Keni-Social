// Contrato de los atajos del MODO RECORTE estilo Canva: Enter CONFIRMA (Hecho) y Escape CANCELA
// (restaura), respetando la CASCADA de Escape existente (recorte → reencuadre → deseleccionar).

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { documentoVacio, nuevaCapaTexto } from "../documento";
import { crearStoreEditor } from "../store";
import { type ZoomApi, useAtajosTeclado } from "./useAtajosTeclado";

function montar(opts: { recorteId?: string | null; reencuadreId?: string | null; conSeleccion?: boolean } = {}) {
  const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
  const texto = nuevaCapaTexto({ id: "texto-1", nombre: "Texto", z: 1 });
  store.getState().agregar(texto);
  if (opts.conSeleccion) store.getState().seleccionar(texto.id);
  const zoom = {
    current: { acercar: vi.fn(), alejar: vi.fn(), ajustar: vi.fn(), real: vi.fn() } as ZoomApi,
  };
  const onSalirReencuadre = vi.fn();
  const onCancelarRecorte = vi.fn();
  const onConfirmarRecorte = vi.fn();
  const hook = renderHook(() =>
    useAtajosTeclado({
      store,
      zoom,
      reencuadreId: opts.reencuadreId ?? null,
      onSalirReencuadre,
      recorteId: opts.recorteId ?? null,
      onCancelarRecorte,
      onConfirmarRecorte,
    }),
  );
  return { store, hook, onSalirReencuadre, onCancelarRecorte, onConfirmarRecorte };
}

// Como en un navegador real, el keydown se origina en el elemento enfocado (body) y BURBUJEA
// hasta window, donde escucha el hook.
const tecla = (key: string) => document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));

describe("useAtajosTeclado — modo recorte (Canva)", () => {
  it("Enter con el recorte activo CONFIRMA (Hecho)", () => {
    const { onConfirmarRecorte, onCancelarRecorte, hook } = montar({ recorteId: "img-1" });
    tecla("Enter");
    expect(onConfirmarRecorte).toHaveBeenCalledTimes(1);
    expect(onCancelarRecorte).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("Enter sin recorte activo no dispara nada", () => {
    const { onConfirmarRecorte, hook } = montar({ conSeleccion: true });
    tecla("Enter");
    expect(onConfirmarRecorte).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("Escape con el recorte activo CANCELA y no toca la selección (cascada)", () => {
    const { store, onCancelarRecorte, hook } = montar({ recorteId: "img-1", conSeleccion: true });
    tecla("Escape");
    expect(onCancelarRecorte).toHaveBeenCalledTimes(1);
    expect(store.getState().seleccion).toBe("texto-1");
    hook.unmount();
  });

  it("la cascada de Escape sigue intacta: reencuadre → deseleccionar", () => {
    const conReencuadre = montar({ reencuadreId: "img-1", conSeleccion: true });
    tecla("Escape");
    expect(conReencuadre.onSalirReencuadre).toHaveBeenCalledTimes(1);
    expect(conReencuadre.store.getState().seleccion).toBe("texto-1");
    conReencuadre.hook.unmount();

    const sinModos = montar({ conSeleccion: true });
    tecla("Escape");
    expect(sinModos.store.getState().seleccion).toBeNull();
    sinModos.hook.unmount();
  });
});

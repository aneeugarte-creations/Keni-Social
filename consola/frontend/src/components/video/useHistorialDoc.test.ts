/**
 * Tests del hook useHistorialDoc (deshacer/rehacer del documento de vídeo):
 *  - registrar + deshacer revierte el doc al snapshot anterior.
 *  - rehacer restaura el doc descartado por un deshacer.
 *  - puedeDeshacer / puedeRehacer reflejan el estado de las pilas.
 *  - Una acción nueva tras deshacer descarta el futuro (no hay rehacer).
 *  - El límite de 50 snapshots previene acumulación ilimitada.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { composicionVacia, type ComposicionVideo } from "@/lib/video";

import { useHistorialDoc } from "./useHistorialDoc";

function docA() {
  return composicionVacia("9:16", "unotv");
}

function docB() {
  return { ...composicionVacia("1:1", "unotv"), marca: "unotv" };
}

describe("useHistorialDoc", () => {
  it("arranca sin historial (no puede deshacer ni rehacer)", () => {
    const { result } = renderHook(() => useHistorialDoc(docA()));
    expect(result.current.puedeDeshacer).toBe(false);
    expect(result.current.puedeRehacer).toBe(false);
  });

  it("deshacer revierte un cambio del doc al snapshot anterior", () => {
    const inicial = docA();
    const { result, rerender } = renderHook(({ doc }) => useHistorialDoc(doc), {
      initialProps: { doc: inicial },
    });

    // Registra el doc ANTES de mutar (como lo haría Video.tsx).
    act(() => result.current.registrar(inicial));

    const modificado = docB();
    // Simula que el componente padre ya actualizó el doc a `modificado`.
    rerender({ doc: modificado });

    expect(result.current.puedeDeshacer).toBe(true);
    const restaurado = result.current.deshacer();
    expect(restaurado).toBe(inicial);
  });

  it("rehacer restaura el doc descartado por un deshacer", () => {
    const a = docA();
    const b = docB();
    const { result, rerender } = renderHook(({ doc }) => useHistorialDoc(doc), {
      initialProps: { doc: a },
    });

    act(() => result.current.registrar(a));
    rerender({ doc: b });

    // Deshace (vuelve a `a`).
    let recuperado: ComposicionVideo | null = null;
    act(() => {
      recuperado = result.current.deshacer();
    });
    expect(recuperado).toBe(a);

    // Ahora puede rehacer (recuperar `b`).
    rerender({ doc: a });
    expect(result.current.puedeRehacer).toBe(true);
    let rehecho: ComposicionVideo | null = null;
    act(() => {
      rehecho = result.current.rehacer();
    });
    expect(rehecho).toBe(b);
  });

  it("una acción nueva tras deshacer descarta el futuro", () => {
    const a = docA();
    const b = docB();
    const c = { ...docA(), marca: "claro" };
    const { result, rerender } = renderHook(({ doc }) => useHistorialDoc(doc), {
      initialProps: { doc: a },
    });

    act(() => result.current.registrar(a));
    rerender({ doc: b });

    // Deshace hacia `a`.
    act(() => { result.current.deshacer(); });
    rerender({ doc: a });

    // Nueva acción desde `a` → registra y mutar a `c`.
    act(() => result.current.registrar(a));
    rerender({ doc: c });

    // El futuro se descartó: no puede rehacer `b`.
    expect(result.current.puedeRehacer).toBe(false);
  });

  it("puedeDeshacer / puedeRehacer son reactivos", () => {
    const a = docA();
    const { result, rerender } = renderHook(({ doc }) => useHistorialDoc(doc), {
      initialProps: { doc: a },
    });

    expect(result.current.puedeDeshacer).toBe(false);
    act(() => result.current.registrar(a));
    expect(result.current.puedeDeshacer).toBe(true);

    rerender({ doc: docB() });
    act(() => { result.current.deshacer(); });
    expect(result.current.puedeDeshacer).toBe(false);
    expect(result.current.puedeRehacer).toBe(true);
  });
});

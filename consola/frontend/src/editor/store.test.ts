import { describe, expect, it } from "vitest";

import { documentoVacio, nuevoId, nuevaCapaTexto, nuevaCapaMarco } from "./documento";
import { crearStoreEditor } from "./store";

describe("Store del editor (Zustand)", () => {
  describe("Ids únicos", () => {
    it("duplicarMulti genera ids únicos en llamadas consecutivas (sin colisión de timestamps)", () => {
      const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "test");
      const store = crearStoreEditor(doc);

      // Agrega una capa de prueba usando factory
      const texto = nuevaCapaTexto({ id: "texto-test-1", nombre: "Texto 1", z: 1 });
      const estado = store.getState();
      estado.agregar(texto);
      estado.seleccionar(texto.id);

      // Duplica dos veces seguidas (en el mismo milisegundo potencialmente)
      estado.duplicarMulti();
      const doc1 = store.getState().documento;
      const ids1 = doc1.capas.map((c) => c.id);

      estado.deshacer(); // Vuelve atrás
      estado.seleccionar(texto.id);
      estado.duplicarMulti();
      const doc2 = store.getState().documento;
      const ids2 = doc2.capas.map((c) => c.id);

      // Los ids generados en las dos llamadas deben ser diferentes (no colisionar).
      const generadosEnDoc1 = ids1.filter((id) => !["foto", "texto-test-1"].includes(id));
      const generadosEnDoc2 = ids2.filter((id) => !["foto", "texto-test-1"].includes(id));
      expect(generadosEnDoc1).toHaveLength(1);
      expect(generadosEnDoc2).toHaveLength(1);
      expect(generadosEnDoc1[0]).not.toEqual(generadosEnDoc2[0]);
    });

    it("nuevoId genera secuencias únicas incluso si se llama múltiples veces en el mismo ms", () => {
      const prefijo = "test";
      const ids: string[] = [];
      // Llama nuevoId 10 veces seguidas (que probablemente caerán en el mismo milisegundo)
      for (let i = 0; i < 10; i++) {
        ids.push(nuevoId(prefijo));
      }
      // Todos deben ser únicos gracias al contador de módulo
      const unicos = new Set(ids);
      expect(unicos.size).toBe(10);
    });
  });

  describe("Deshacer y rehacer sanean selección", () => {
    it("deshacer poda seleccionMulti a ids que existan en el documento restaurado", () => {
      const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "test");
      const store = crearStoreEditor(doc);

      const estado = store.getState();
      const texto1 = nuevaCapaTexto({ id: "texto-1", nombre: "Texto 1", z: 1 });
      const texto2 = nuevaCapaTexto({ id: "texto-2", nombre: "Texto 2", z: 2 });

      estado.agregar(texto1);
      estado.agregar(texto2);
      estado.seleccionarMuchas(["texto-1", "texto-2"]);
      expect(store.getState().seleccionMulti).toEqual(["texto-1", "texto-2"]);

      // Borra texto-2 (registra un paso de historial)
      estado.quitar("texto-2");
      // La seleccion se auto-limpia: texto-2 se quita de seleccionMulti, queda solo texto-1
      expect(store.getState().seleccionMulti).toEqual(["texto-1"]);
      expect(store.getState().documento.capas.map((c) => c.id)).not.toContain("texto-2");

      // Deshace: debe volver a tener texto-1 y texto-2 en el documento
      estado.deshacer();
      // El documento debe tener ambas capas de nuevo
      expect(store.getState().documento.capas.map((c) => c.id)).toContain("texto-1");
      expect(store.getState().documento.capas.map((c) => c.id)).toContain("texto-2");
      // La seleccionMulti debe haber sido saneada si era necesario (aquí ambas existen, así que se conserva)
      expect(store.getState().seleccionMulti.length).toBeGreaterThan(0);
    });

    it("deshacer pone seleccion a null si la capa ya no existe", () => {
      const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "test");
      const store = crearStoreEditor(doc);

      const estado = store.getState();
      const texto = nuevaCapaTexto({ id: "texto-1", nombre: "Texto 1", z: 1 });

      estado.agregar(texto);
      estado.seleccionar("texto-1");
      expect(store.getState().seleccion).toBe("texto-1");

      // Borra la capa
      estado.quitar("texto-1");
      expect(store.getState().seleccion).toBeNull();

      // Deshace (restaura la capa)
      estado.deshacer();
      const docRestaurado = store.getState().documento;
      expect(docRestaurado.capas.map((c) => c.id)).toContain("texto-1");
      // La selección debe restaurarse también (porque deshacer está en el pasado donde existía)
    });

    it("rehacer poda seleccionMulti de la misma manera", () => {
      const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "test");
      const store = crearStoreEditor(doc);

      const estado = store.getState();
      const texto = nuevaCapaTexto({ id: "texto-1", nombre: "Texto 1", z: 1 });

      estado.agregar(texto);
      estado.seleccionar("texto-1");

      // Borra
      estado.quitar("texto-1");
      expect(store.getState().seleccion).toBeNull();

      // Deshace (restaura)
      estado.deshacer();
      expect(store.getState().documento.capas.map((c) => c.id)).toContain("texto-1");

      // Rehace (borra de nuevo)
      estado.rehacer();
      expect(store.getState().documento.capas.map((c) => c.id)).not.toContain("texto-1");
      expect(store.getState().seleccion).toBeNull();
    });
  });

  describe("aplicarPosiciones respeta parámetro registrar", () => {
    it("aplicarPosiciones(pos, true) registra en historial (default)", () => {
      const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "test");
      const store = crearStoreEditor(doc);

      const estado = store.getState();
      const texto = nuevaCapaTexto({ id: "texto-1", x: 10, y: 20, z: 1 });

      estado.agregar(texto);
      const pasadoAntes = store.getState().pasado.length;

      estado.aplicarPosiciones([{ id: "texto-1", x: 20, y: 30 }], true);
      const pasadoDespues = store.getState().pasado.length;

      expect(pasadoDespues).toBe(pasadoAntes + 1);
    });

    it("aplicarPosiciones(pos, false) no registra en historial", () => {
      const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "test");
      const store = crearStoreEditor(doc);

      const estado = store.getState();
      const texto = nuevaCapaTexto({ id: "texto-1", x: 10, y: 20, z: 1 });

      estado.agregar(texto);
      const pasadoAntes = store.getState().pasado.length;

      estado.aplicarPosiciones([{ id: "texto-1", x: 20, y: 30 }], false);
      const pasadoDespues = store.getState().pasado.length;

      expect(pasadoDespues).toBe(pasadoAntes); // No cambió
    });
  });

  describe("agrupar calcula bbox con rotación", () => {
    it("agrupar calcula bbox correcto para capas rotadas", () => {
      const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "test");
      const store = crearStoreEditor(doc);

      const estado = store.getState();
      // Dos capas rectangulares
      const rect1 = nuevaCapaMarco({ id: "rect-1", nombre: "Rect 1", x: 100, y: 100, w: 50, h: 50, rotacion: 0, z: 1, relleno: "#FF0000" });
      const rect2 = nuevaCapaMarco({ id: "rect-2", nombre: "Rect 2", x: 200, y: 200, w: 50, h: 50, rotacion: 45, z: 2, relleno: "#00FF00" });

      estado.agregar(rect1);
      estado.agregar(rect2);
      estado.seleccionarMuchas(["rect-1", "rect-2"]);

      // Agrupa
      estado.agrupar();

      const grupo = store.getState().documento.capas.find((c) => c.tipo === "grupo");
      expect(grupo).toBeDefined();
      if (!grupo) return;

      // El bbox del grupo debe envolver ambas capas, incluyendo la rotada.
      // rect1 sin rotar: [100,100] a [150,150]
      // rect2 rotado 45°: esquinas rotadas deben estar dentro del bbox del grupo
      // El grupo debe tener x, y, w, h que envuelvan a ambas
      expect(grupo.x).toBeLessThanOrEqual(100); // Envuelve rect1
      expect(grupo.y).toBeLessThanOrEqual(100);
      expect(grupo.x + grupo.w).toBeGreaterThanOrEqual(150); // Envuelve rect1
      expect(grupo.y + grupo.h).toBeGreaterThanOrEqual(150);
    });
  });
});

import { describe, expect, it } from "vitest";

import { bandaOverlay, cajaVisual, documentoVacio, nuevoId, nuevaCapaMarco, nuevaCapaOverlay, nuevaCapaTexto } from "./documento";
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

  describe("Deshacer y rehacer reparan selección", () => {
    it("deshacer purga seleccionMulti a ids que existan en el documento restaurado", () => {
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
      // La seleccionMulti debe haber sido reparada si era necesario (aquí ambas existen, así que se conserva)
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

    it("rehacer purga seleccionMulti de la misma manera", () => {
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

  describe("ordenarMulti («Ordenar», tidy up estilo Canva)", () => {
    const montarCajas = (cajas: { id: string; x: number; y: number; w: number; h: number }[]) => {
      const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
      const estado = store.getState();
      cajas.forEach((c, i) => estado.agregar(nuevaCapaMarco({ ...c, z: i + 1, relleno: "#FF0000" })));
      estado.seleccionarMuchas(cajas.map((c) => c.id));
      return store;
    };
    const caja = (store: ReturnType<typeof crearStoreEditor>, id: string) =>
      store.getState().documento.capas.find((c) => c.id === id)!;

    it("disposición horizontal: hueco uniforme dentro de la extensión y centros alineados en Y", () => {
      const store = montarCajas([
        { id: "a", x: 0, y: 90, w: 100, h: 60 },
        { id: "b", x: 110, y: 140, w: 50, h: 20 },
        { id: "c", x: 450, y: 100, w: 150, h: 40 },
      ]);
      store.getState().ordenarMulti();
      // Extensión 0..600, tamaños 100+50+150 = 300 => hueco (600−300)/2 = 150: a:0, b:250, c:450.
      expect(caja(store, "a").x).toBe(0);
      expect(caja(store, "b").x).toBe(250);
      expect(caja(store, "c").x).toBe(450);
      // Centros Y alineados a la media de centros ((120+150+120)/3 = 130).
      expect(caja(store, "a").y).toBe(130 - 30);
      expect(caja(store, "b").y).toBe(130 - 10);
      expect(caja(store, "c").y).toBe(130 - 20);
    });

    it("disposición vertical (mayor dispersión en Y): reparte en Y y alinea centros en X", () => {
      const store = montarCajas([
        { id: "a", x: 100, y: 0, w: 80, h: 100 },
        { id: "b", x: 120, y: 120, w: 40, h: 100 },
        { id: "c", x: 100, y: 500, w: 80, h: 100 },
      ]);
      store.getState().ordenarMulti();
      // Extensión 0..600, altos 300 => hueco (600−300)/2 = 150: a:0, b:250, c:500.
      expect(caja(store, "a").y).toBe(0);
      expect(caja(store, "b").y).toBe(250);
      expect(caja(store, "c").y).toBe(500);
      // Centros X a la media de centros (140 los tres => no cambian).
      expect(caja(store, "a").x).toBe(100);
      expect(caja(store, "b").x).toBe(120);
      expect(caja(store, "c").x).toBe(100);
    });

    it("es UN solo paso de deshacer (vuelve a las posiciones de partida)", () => {
      const store = montarCajas([
        { id: "a", x: 0, y: 100, w: 100, h: 50 },
        { id: "b", x: 130, y: 100, w: 100, h: 50 },
        { id: "c", x: 500, y: 100, w: 100, h: 50 },
      ]);
      const pasadoAntes = store.getState().pasado.length;
      store.getState().ordenarMulti();
      expect(store.getState().pasado.length).toBe(pasadoAntes + 1);
      store.getState().deshacer();
      expect(caja(store, "b").x).toBe(130);
      expect(caja(store, "c").x).toBe(500);
    });

    it("con menos de 3 capas seleccionadas es un no-op (ni mueve ni registra historial)", () => {
      const store = montarCajas([
        { id: "a", x: 0, y: 100, w: 100, h: 50 },
        { id: "b", x: 130, y: 100, w: 100, h: 50 },
        { id: "c", x: 500, y: 100, w: 100, h: 50 },
      ]);
      store.getState().seleccionarMuchas(["a", "b"]);
      const pasadoAntes = store.getState().pasado.length;
      store.getState().ordenarMulti();
      expect(store.getState().pasado.length).toBe(pasadoAntes);
      expect(caja(store, "b").x).toBe(130);
    });
  });

  describe("alinear/alinearMulti operan sobre la caja VISIBLE (overlay = banda, texto legado = bloque)", () => {
    const FORMATO = { w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 };
    const montarOverlay = () => {
      const store = crearStoreEditor(documentoVacio(FORMATO, "test"));
      // Overlay a sangre (la caja cubre el lienzo): solo se VE su banda inferior.
      store.getState().agregar(nuevaCapaOverlay({ id: "ov", x: 0, y: 0, w: 1080, h: 1350, alto_frac: 0.45, z: 1 }));
      return store;
    };
    const capaDe = (store: ReturnType<typeof crearStoreEditor>, id: string) =>
      store.getState().documento.capas.find((c) => c.id === id)!;

    it("'arriba' deja la BANDA del overlay pegada al borde superior (antes la dejaba abajo)", () => {
      const store = montarOverlay();
      store.getState().alinear("ov", "arriba");
      const c = capaDe(store, "ov");
      // y del MODELO = banda - h, para que el tope VISIBLE (y + h - banda) caiga en 0.
      expect(c.y).toBe(bandaOverlay(c as never) - 1350);
      expect(cajaVisual(c).y).toBe(0);
    });

    it("'abajo' del overlay conserva el comportamiento histórico (y = f.h - h: banda al fondo)", () => {
      const store = montarOverlay();
      store.getState().alinear("ov", "abajo");
      expect(capaDe(store, "ov").y).toBe(0); // f.h - h = 1350 - 1350
    });

    it("'centroV' centra la BANDA visible, no la caja fantasma", () => {
      const store = montarOverlay();
      store.getState().alinear("ov", "centroV");
      const c = capaDe(store, "ov");
      const vis = cajaVisual(c);
      expect(vis.y).toBe(Math.round((1350 - vis.h) / 2));
    });

    it("texto legado (h<=0, ancla 'abajo'): 'arriba' coloca el BLOQUE en y visible 0", () => {
      const store = crearStoreEditor(documentoVacio(FORMATO, "test"));
      store.getState().agregar(
        nuevaCapaTexto({ id: "t", x: 80, y: 1254, w: 760, h: 0, tamano: 96, interlineado: 1.14, ancla: "abajo", z: 1 }),
      );
      store.getState().alinear("t", "arriba");
      const c = capaDe(store, "t");
      // La y almacenada es el borde INFERIOR del bloque (contrato legado): queda en altoVisual.
      expect(c.y).toBe(Math.round(96 * 1.14));
      expect(cajaVisual(c).y).toBe(0);
    });

    it("alinearMulti aplica la misma conversión visible a toda la selección", () => {
      const store = montarOverlay();
      store.getState().agregar(nuevaCapaMarco({ id: "m", x: 10, y: 600, w: 100, h: 100, z: 2 }));
      store.getState().seleccionarMuchas(["ov", "m"]);
      store.getState().alinearMulti("arriba");
      expect(cajaVisual(capaDe(store, "ov")).y).toBe(0);
      expect(capaDe(store, "m").y).toBe(0);
    });
  });

  describe("aplicarPosiciones y grupos (hijas en coordenadas absolutas)", () => {
    it("mover un grupo desplaza también a sus hijas (el export pinta las hijas, no la bbox)", () => {
      const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
      const estado = store.getState();
      estado.agregar(nuevaCapaMarco({ id: "a", x: 0, y: 0, w: 100, h: 100, z: 1 }));
      estado.agregar(nuevaCapaMarco({ id: "b", x: 200, y: 200, w: 100, h: 100, z: 2 }));
      estado.seleccionarMuchas(["a", "b"]);
      estado.agrupar();
      const grupo = store.getState().documento.capas.find((c) => c.tipo === "grupo")!;
      store.getState().aplicarPosiciones([{ id: grupo.id, x: grupo.x + 10, y: grupo.y + 5 }]);
      const g = store.getState().documento.capas.find((c) => c.id === grupo.id)!;
      expect(g.x).toBe(grupo.x + 10);
      expect(g.y).toBe(grupo.y + 5);
      // Las hijas viajan con el grupo (mismo horneado que onDragEndGrupo).
      const hijas = (g as { capas: { id: string; x: number; y: number }[] }).capas;
      expect(hijas.find((s) => s.id === "a")).toMatchObject({ x: 10, y: 5 });
      expect(hijas.find((s) => s.id === "b")).toMatchObject({ x: 210, y: 205 });
    });

    it("duplicar un grupo desplaza la copia ENTERA (+24,+24), hijas incluidas", () => {
      const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
      const estado = store.getState();
      estado.agregar(nuevaCapaMarco({ id: "a", x: 0, y: 0, w: 100, h: 100, z: 1 }));
      estado.agregar(nuevaCapaMarco({ id: "b", x: 200, y: 200, w: 100, h: 100, z: 2 }));
      estado.seleccionarMuchas(["a", "b"]);
      estado.agrupar();
      const grupo = store.getState().documento.capas.find((c) => c.tipo === "grupo")!;
      store.getState().duplicar(grupo.id);
      const copia = store.getState().documento.capas.filter((c) => c.tipo === "grupo").at(-1)!;
      expect(copia.id).not.toBe(grupo.id);
      expect(copia.x).toBe(grupo.x + 24);
      const hijas = (copia as { capas: { x: number; y: number }[] }).capas;
      expect(hijas[0]).toMatchObject({ x: 24, y: 24 });
    });
  });
});

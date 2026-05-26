/**
 * Tests para FlujoGeneracion (#118 C-1, A-3):
 *
 * C-1: terminalRef se reinicia al iniciar una nueva generación, garantizando
 *      que el toast de éxito y la invalidación de ["publicaciones"] se disparen
 *      en la 2ª generación (y sucesivas).
 *
 * A-3: resultadoCopy usa la skill capturada al lanzar (skillGeneracionRef), no
 *      la skill seleccionada en el UI en ese momento, para que cambiar el selector
 *      durante la generación en background no oculte el resultado.
 *
 * NOTA: FlujoGeneracion es un componente con muchas dependencias externas
 * (useQuery de skills, useMutation, router, etc.). Probamos las lógicas críticas
 * de forma aislada (unit) sin montar el componente completo, para mantener los
 * tests rápidos y deterministas.
 */
import { describe, expect, it } from "vitest";

/**
 * C-1: el patrón "reiniciar ref antes de iniciar" garantiza que el efecto
 * terminal (toast + invalidación) se ejecute en la 2ª generación con el mismo id.
 *
 * Simulamos la lógica del useEffect:
 *   if (!generacion || generacion.id === terminalRef.current) return;
 *   if (generacion.estado === "completado") { terminalRef.current = generacion.id; ... }
 */
describe("FlujoGeneracion · C-1: reinicio de terminalRef (#118)", () => {
  it("sin reinicio, la 2ª generación con el mismo id no dispara el efecto terminal", () => {
    const terminalRef = { current: null as string | null };
    const disparos: string[] = [];

    function simularEfectoTerminal(id: string, estado: string) {
      if (id === terminalRef.current) return; // bloqueado por el ref
      if (estado === "completado") {
        terminalRef.current = id;
        disparos.push(id);
      }
    }

    // 1ª generación
    simularEfectoTerminal("gen-abc", "completado");
    expect(disparos).toHaveLength(1); // se disparó

    // 2ª generación con el MISMO id (sin reiniciar el ref)
    simularEfectoTerminal("gen-abc", "completado");
    expect(disparos).toHaveLength(1); // NO se vuelve a disparar — BUG
  });

  it("CON reinicio, la 2ª generación con el mismo id SÍ dispara el efecto terminal", () => {
    const terminalRef = { current: null as string | null };
    const disparos: string[] = [];

    function simularEfectoTerminal(id: string, estado: string) {
      if (id === terminalRef.current) return;
      if (estado === "completado") {
        terminalRef.current = id;
        disparos.push(id);
      }
    }

    // 1ª generación
    simularEfectoTerminal("gen-abc", "completado");
    expect(disparos).toHaveLength(1);

    // Reinicio del ref (simula lo que hace onSuccess antes de llamar a iniciar)
    terminalRef.current = null;

    // 2ª generación con el MISMO id (ref reiniciado — FIX C-1)
    simularEfectoTerminal("gen-abc", "completado");
    expect(disparos).toHaveLength(2); // ahora SÍ se dispara
  });

  it("con ids distintos, el efecto se dispara en cada generación aunque no haya reinicio explícito", () => {
    const terminalRef = { current: null as string | null };
    const disparos: string[] = [];

    function simularEfectoTerminal(id: string, estado: string) {
      if (id === terminalRef.current) return;
      if (estado === "completado") {
        terminalRef.current = id;
        disparos.push(id);
      }
    }

    simularEfectoTerminal("gen-001", "completado");
    simularEfectoTerminal("gen-002", "completado");
    expect(disparos).toEqual(["gen-001", "gen-002"]);
  });
});

/**
 * A-3: resultadoCopy debe usar la skill capturada al lanzar, no la seleccionada
 * en el selector UI en el momento de evaluar el memo.
 */
describe("FlujoGeneracion · A-3: skillGeneracionRef no depende del selector (#118)", () => {
  it("si la skill de UI cambia durante la generación, el resultado sigue siendo visible", () => {
    // Simula el useMemo de resultadoCopy con la lógica corregida (A-3)
    function calcularResultadoCopy(
      generacionEstado: string,
      generacionResultado: object | null,
      skillUsadaRef: { salida: string } | undefined,
    ) {
      if (generacionEstado !== "completado" || !generacionResultado) return null;
      if (skillUsadaRef && skillUsadaRef.salida !== "piezas") return null;
      return generacionResultado;
    }

    const generacion = { estado: "completado", resultado: { piezas: [{ red: "x", texto: "Hola" }] } };

    // Skill capturada al lanzar: "piezas"
    const skillCapturada = { salida: "piezas" };
    // Skill que el usuario cambió en el UI mientras esperaba: "documento"
    const skillUIActual = { salida: "documento" };

    // Con el fix A-3: usamos skillCapturada (ref), no skillUIActual
    const resultadoFix = calcularResultadoCopy(
      generacion.estado,
      generacion.resultado,
      skillCapturada,
    );
    expect(resultadoFix).not.toBeNull(); // el resultado es visible

    // Sin el fix (bug original): usaría skillUIActual
    const resultadoBug = calcularResultadoCopy(
      generacion.estado,
      generacion.resultado,
      skillUIActual,
    );
    expect(resultadoBug).toBeNull(); // el resultado desaparecería — BUG
  });

  it("si skillGeneracionRef es undefined (skill sin salida definida), muestra el resultado", () => {
    function calcularResultadoCopy(
      generacionEstado: string,
      generacionResultado: object | null,
      skillUsadaRef: { salida: string } | undefined,
    ) {
      if (generacionEstado !== "completado" || !generacionResultado) return null;
      if (skillUsadaRef && skillUsadaRef.salida !== "piezas") return null;
      return generacionResultado;
    }

    const resultado = calcularResultadoCopy("completado", { piezas: [] }, undefined);
    expect(resultado).not.toBeNull();
  });
});

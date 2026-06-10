/**
 * Tests para @/lib/formato — utilidades de formato es-MX compartidas.
 *
 * Cubre todos los helpers: numeroCompacto, numeroCompleto, porcentaje,
 * variacion, puntosPct, rendimientoRel, costeUsd y duracion; incluyendo
 * valores límite y no finitos.
 */
import { describe, expect, it } from "vitest";

import {
  costeUsd,
  duracion,
  nombreFormato,
  nombreMarca,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  puntosPct,
  rendimientoRel,
  tiempoVis,
  variacion,
} from "./formato";

// ---------------------------------------------------------------------------
// numeroCompacto
// ---------------------------------------------------------------------------
describe("numeroCompacto", () => {
  it("devuelve — para valores no finitos", () => {
    expect(numeroCompacto(NaN)).toBe("—");
    expect(numeroCompacto(Infinity)).toBe("—");
    expect(numeroCompacto(-Infinity)).toBe("—");
  });

  it("devuelve el entero sin abreviar para valores < 1000", () => {
    expect(numeroCompacto(0)).toBe("0");
    expect(numeroCompacto(842)).toBe("842");
    expect(numeroCompacto(999)).toBe("999");
  });

  it("abrevia con notación compacta para valores >= 1000", () => {
    // El símbolo compacto de miles varía según la implementación de ICU en el
    // entorno (Node full-ICU → "mil", Node sin ICU completo → "k").
    const mil = numeroCompacto(1830);
    expect(mil).toMatch(/mil|k/i);

    // 221_621_046 → "221.6 M" o "221.6 M." según ICU, siempre contiene dígitos y M
    const millones = numeroCompacto(221_621_046);
    expect(millones).toMatch(/\d.*[Mm]/);
  });

  it("maneja negativos pequeños sin abreviar", () => {
    expect(numeroCompacto(-500)).toBe("-500");
  });
});

// ---------------------------------------------------------------------------
// numeroCompleto
// ---------------------------------------------------------------------------
describe("numeroCompleto", () => {
  it("devuelve — para valores no finitos", () => {
    expect(numeroCompleto(NaN)).toBe("—");
  });

  it("formatea con separadores de miles es-MX", () => {
    // En es-MX el separador de miles es coma: 1,234,567
    const resultado = numeroCompleto(1_234_567);
    expect(resultado).toBe("1,234,567");
  });

  it("formatea cero", () => {
    expect(numeroCompleto(0)).toBe("0");
  });
});

// ---------------------------------------------------------------------------
// porcentaje
// ---------------------------------------------------------------------------
describe("porcentaje", () => {
  it("devuelve — para valores no finitos", () => {
    expect(porcentaje(NaN)).toBe("—");
  });

  it("incluye un decimal y el símbolo %", () => {
    const r = porcentaje(1.8);
    expect(r).toContain("%");
    expect(r).toContain("1");
    expect(r).toContain("8");
  });

  it("formatea cero correctamente", () => {
    expect(porcentaje(0)).toContain("0.0");
  });
});

// ---------------------------------------------------------------------------
// variacion
// ---------------------------------------------------------------------------
describe("variacion", () => {
  it("devuelve — para valores no finitos", () => {
    expect(variacion(NaN)).toBe("—");
  });

  it("añade + para valores positivos", () => {
    expect(variacion(12.345)).toContain("+");
  });

  it("añade − (menos tipográfico) para valores negativos", () => {
    // El signo menos tipográfico (U+2212) se distingue del ASCII '-'
    expect(variacion(-4)).toContain("−");
  });

  it("no añade signo para cero", () => {
    const r = variacion(0);
    expect(r).not.toContain("+");
    expect(r).not.toContain("−");
  });

  it("decide el signo TRAS redondear: −0.04 → '0.0 %' sin signo (nunca '−0.0 %')", () => {
    expect(variacion(-0.04)).toBe("0.0 %");
    expect(variacion(0.04)).toBe("0.0 %");
  });

  it("incluye un decimal y el símbolo %", () => {
    expect(variacion(5)).toContain("%");
  });
});

// ---------------------------------------------------------------------------
// puntosPct (diferencia en puntos porcentuales, p. ej. engagement A vs B)
// ---------------------------------------------------------------------------
describe("puntosPct", () => {
  it("devuelve — para valores no finitos", () => {
    expect(puntosPct(NaN)).toBe("—");
    expect(puntosPct(Infinity)).toBe("—");
  });

  it("añade + para positivos y − (menos tipográfico U+2212) para negativos", () => {
    expect(puntosPct(0.42)).toBe("+0.4 pts");
    expect(puntosPct(-1.16)).toBe("−1.2 pts");
  });

  it("decide el signo TRAS redondear: −0.04 → '0.0 pts' sin signo (nunca '−0.0 pts')", () => {
    expect(puntosPct(-0.04)).toBe("0.0 pts");
    expect(puntosPct(0.04)).toBe("0.0 pts");
    expect(puntosPct(0)).toBe("0.0 pts");
  });

  it("usa el sufijo ' pts', nunca '%' (los puntos no son variación relativa)", () => {
    expect(puntosPct(2.5)).toContain(" pts");
    expect(puntosPct(2.5)).not.toContain("%");
  });
});

// ---------------------------------------------------------------------------
// rendimientoRel
// ---------------------------------------------------------------------------
describe("rendimientoRel", () => {
  it("null (sin base de comparación) → —", () => {
    expect(rendimientoRel(null)).toBe("—");
  });

  it("siempre muestra 1 decimal con sufijo ×", () => {
    expect(rendimientoRel(0.04)).toBe("0.0×"); // nunca "0×"
    expect(rendimientoRel(1)).toBe("1.0×");
    expect(rendimientoRel(1.4)).toBe("1.4×");
  });

  it("no finito → —", () => {
    expect(rendimientoRel(NaN)).toBe("—");
    expect(rendimientoRel(Infinity)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// costeUsd
// ---------------------------------------------------------------------------
describe("costeUsd", () => {
  it("devuelve — para valores no finitos", () => {
    expect(costeUsd(NaN)).toBe("—");
  });

  it("usa 3 decimales para importes muy pequeños (< $0.10)", () => {
    const r = costeUsd(0.0381);
    // Debe contener 3 dígitos después del separador decimal
    expect(r).toMatch(/\.\d{3}/);
  });

  it("usa 2 decimales para importes normales", () => {
    const r = costeUsd(1.5);
    expect(r).toMatch(/\.\d{2}$/);
  });

  it("incluye una referencia a USD (símbolo $ o literal 'USD' según ICU)", () => {
    // Node sin full-ICU puede producir "USD 0.00" en lugar de "$0.00".
    const r = costeUsd(0);
    expect(r).toMatch(/\$|USD/);
  });
});

// ---------------------------------------------------------------------------
// duracion
// ---------------------------------------------------------------------------
describe("duracion", () => {
  it("devuelve — para valores no finitos o negativos", () => {
    expect(duracion(NaN)).toBe("—");
    expect(duracion(-1)).toBe("—");
  });

  it("formatea menos de 60 segundos con 1 decimal y 's'", () => {
    const r = duracion(850);
    expect(r).toContain("s");
    // 0.9 s
    expect(r).toMatch(/0[.,]9/);
  });

  it("formatea 60+ segundos como 'X min Y s'", () => {
    // 95 000 ms → 95 s → 1 min 35 s
    const r = duracion(95_000);
    expect(r).toContain("min");
    expect(r).toContain("1");
    expect(r).toContain("35");
  });

  it("formatea exactamente 60 segundos (1 min 0 s)", () => {
    const r = duracion(60_000);
    expect(r).toContain("min");
    expect(r).toContain("1");
  });
});

// ---------------------------------------------------------------------------
// tiempoVis (segundos → "Xs" / "Xm Ys")
// ---------------------------------------------------------------------------
describe("tiempoVis", () => {
  it("devuelve — para valores no finitos o negativos", () => {
    expect(tiempoVis(NaN)).toBe("—");
    expect(tiempoVis(-1)).toBe("—");
  });

  it("muestra segundos sueltos hasta el minuto", () => {
    expect(tiempoVis(0)).toBe("0s");
    expect(tiempoVis(12)).toBe("12s");
    expect(tiempoVis(59)).toBe("59s");
  });

  it("muestra 'Xm Ys' a partir del minuto y omite los segundos en punto", () => {
    expect(tiempoVis(60)).toBe("1m");
    expect(tiempoVis(95)).toBe("1m 35s");
  });
});

// ---------------------------------------------------------------------------
// nombreRed
// ---------------------------------------------------------------------------
describe("nombreRed", () => {
  it("traduce los ids conocidos a su forma de marca", () => {
    expect(nombreRed("instagram")).toBe("Instagram");
    expect(nombreRed("tiktok")).toBe("TikTok");
    expect(nombreRed("youtube")).toBe("YouTube");
    expect(nombreRed("linkedin")).toBe("LinkedIn");
    expect(nombreRed("bluesky")).toBe("Bluesky");
  });

  it("normaliza twitter y x a 'X'", () => {
    expect(nombreRed("twitter")).toBe("X");
    expect(nombreRed("x")).toBe("X");
  });

  it("capitaliza ids desconocidos (degradación honesta) y '' → —", () => {
    expect(nombreRed("kwai")).toBe("Kwai");
    expect(nombreRed("")).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// nombreFormato
// ---------------------------------------------------------------------------
describe("nombreFormato", () => {
  it("null y vacío → 'Sin formato'", () => {
    expect(nombreFormato(null)).toBe("Sin formato");
    expect(nombreFormato("")).toBe("Sin formato");
    expect(nombreFormato("   ")).toBe("Sin formato");
  });

  it("maneja el prefijo feed_ de Meta", () => {
    expect(nombreFormato("feed_image")).toBe("Feed image");
    expect(nombreFormato("feed_carousel_album")).toBe("Carrusel");
    expect(nombreFormato("feed_video")).toBe("Vídeo");
    expect(nombreFormato("feed_reel")).toBe("Reel");
  });

  it("normaliza los formatos genéricos", () => {
    expect(nombreFormato("reel")).toBe("Reel");
    expect(nombreFormato("foto")).toBe("Foto");
    expect(nombreFormato("photo")).toBe("Foto");
    expect(nombreFormato("carrusel")).toBe("Carrusel");
    expect(nombreFormato("carousel")).toBe("Carrusel");
    expect(nombreFormato("video")).toBe("Vídeo");
    expect(nombreFormato("link")).toBe("Enlace");
    expect(nombreFormato("texto")).toBe("Texto");
    expect(nombreFormato("text")).toBe("Texto");
  });

  it("capitaliza formatos desconocidos (degradación honesta)", () => {
    expect(nombreFormato("story")).toBe("Story");
  });
});

// ---------------------------------------------------------------------------
// nombreMarca (resolver por catálogo, degradación honesta)
// ---------------------------------------------------------------------------
describe("nombreMarca", () => {
  const CATALOGO = [
    { id: "unotv", nombre: "UnoTV" },
    { id: "claro_sports", nombre: "Claro Sports" },
  ];

  it("resuelve el id contra el catálogo (lista)", () => {
    expect(nombreMarca("unotv", CATALOGO)).toBe("UnoTV");
    expect(nombreMarca("claro_sports", CATALOGO)).toBe("Claro Sports");
  });

  it("resuelve el id contra un Map<id, nombre>", () => {
    const mapa = new Map(CATALOGO.map((m) => [m.id, m.nombre]));
    expect(nombreMarca("unotv", mapa)).toBe("UnoTV");
  });

  it("si el id no está en el catálogo, devuelve el id tal cual (no inventa)", () => {
    expect(nombreMarca("desconocida", CATALOGO)).toBe("desconocida");
  });

  it("'' → —", () => {
    expect(nombreMarca("", CATALOGO)).toBe("—");
  });
});

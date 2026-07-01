// Rejilla de TERCIOS (regla de los tercios) dentro del marco de recorte: 2 líneas verticales y 2
// horizontales a 1/3 y 2/3. Solo guía visual (sin eventos), pensada para pintarse DURANTE el gesto
// de recorte. Se estira al contenedor (`inset-0`), así que el llamador la mete dentro del marco.

export function RejillaTercios({ visible = true }: { visible?: boolean }) {
  if (!visible) return null;
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {[1 / 3, 2 / 3].map((f) => (
        <div
          key={`v${f}`}
          className="absolute top-0 bottom-0 w-px bg-white/50 mix-blend-difference"
          style={{ left: `${f * 100}%` }}
        />
      ))}
      {[1 / 3, 2 / 3].map((f) => (
        <div
          key={`h${f}`}
          className="absolute left-0 right-0 h-px bg-white/50 mix-blend-difference"
          style={{ top: `${f * 100}%` }}
        />
      ))}
    </div>
  );
}

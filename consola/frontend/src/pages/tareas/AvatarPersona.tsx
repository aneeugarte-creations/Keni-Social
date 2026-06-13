import { cn } from "@/lib/utils";

// Colores fijos por persona: con 5 personas el color se vuelve reconocible de un vistazo
// (patrón de los calendarios editoriales: identidad por color, no solo por nombre).
const PALETA_PERSONA = [
  "bg-sky-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-cyan-500",
] as const;

/** Color estable de una persona por hash de su id (mismo id → mismo color siempre). */
function colorPersona(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return PALETA_PERSONA[h % PALETA_PERSONA.length];
}

/** Avatar redondo con la inicial y el color propio de la persona. */
export function AvatarPersona({
  id,
  nombre,
  size = "md",
}: {
  id: string;
  nombre: string;
  size?: "sm" | "md";
}) {
  return (
    <span
      title={nombre}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-medium text-white",
        colorPersona(id),
        size === "sm" ? "h-5 w-5 text-[10px]" : "h-6 w-6 text-xs",
      )}
    >
      {(nombre || "?").slice(0, 1).toUpperCase()}
    </span>
  );
}

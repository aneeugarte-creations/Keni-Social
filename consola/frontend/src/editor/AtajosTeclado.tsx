// Modal «Atajos de teclado» del editor: chuleta de referencia agrupada por función (crear, editar,
// mover, ordenar capas, zoom). Se abre desde el menú «Más» y desde el botón «?» del rail. Solo
// muestra los atajos; no los ejecuta (el motor vive en `lienzo/useAtajosTeclado.ts` y en el Lienzo).

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// Un atajo: teclas (una o varias combinaciones separadas por «·» dentro de `teclas`) + su acción.
type Atajo = { teclas: string[]; accion: string };
type Grupo = { titulo: string; atajos: Atajo[] };

// SET INTENCIONADO de atajos (coordinado con el bundle «canvas»): z-order de UN paso en ⌘] / ⌘[ y
// frente/fondo en ⌘⇧] / ⌘⇧[; Shift bloquea proporción y Alt escala desde el centro al redimensionar.
const GRUPOS: Grupo[] = [
  {
    titulo: "Crear",
    atajos: [
      { teclas: ["T"], accion: "Texto" },
      { teclas: ["R"], accion: "Rectángulo" },
      { teclas: ["C"], accion: "Círculo" },
      { teclas: ["L"], accion: "Línea" },
    ],
  },
  {
    titulo: "Edición",
    atajos: [
      { teclas: ["⌘Z"], accion: "Deshacer" },
      { teclas: ["⌘⇧Z"], accion: "Rehacer" },
      { teclas: ["⌘D"], accion: "Duplicar" },
      { teclas: ["⌘C", "⌘V"], accion: "Copiar y pegar" },
      { teclas: ["⌘⌥C", "⌘⌥V"], accion: "Copiar y pegar estilo" },
      { teclas: ["⌘A"], accion: "Seleccionar todo" },
      { teclas: ["⌫"], accion: "Borrar" },
    ],
  },
  {
    titulo: "Mover y transformar",
    atajos: [
      { teclas: ["←", "↑", "→", "↓"], accion: "Mover 1 px" },
      { teclas: ["⇧ + flechas"], accion: "Mover 10 px" },
      { teclas: ["⇧ al redimensionar"], accion: "Bloquear proporción" },
      { teclas: ["⌥ al redimensionar"], accion: "Escalar desde el centro" },
    ],
  },
  {
    titulo: "Ordenar capas",
    atajos: [
      { teclas: ["⌘G"], accion: "Agrupar" },
      { teclas: ["⌘⇧G"], accion: "Desagrupar" },
      { teclas: ["⌘]", "⌘["], accion: "Subir / bajar un paso" },
      { teclas: ["⌘⇧]", "⌘⇧["], accion: "Traer al frente / enviar al fondo" },
      { teclas: ["⌥⇧T"], accion: "Ordenar (espaciado uniforme, 3+ capas)" },
    ],
  },
  {
    titulo: "Zoom",
    atajos: [
      { teclas: ["⌘0"], accion: "Ajustar a la pantalla" },
      { teclas: ["⇧0"], accion: "Tamaño real (100 %)" },
      { teclas: ["⌘+", "⌘−"], accion: "Acercar / alejar" },
    ],
  },
];

function Tecla({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded border border-border bg-muted px-1.5 text-[11px] font-medium text-foreground">
      {children}
    </kbd>
  );
}

export function AtajosTeclado({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Atajos de teclado</DialogTitle>
          <DialogDescription>
            En Windows/Linux usa Ctrl en lugar de ⌘ y Alt en lugar de ⌥.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
          {GRUPOS.map((g) => (
            <section key={g.titulo}>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {g.titulo}
              </h3>
              <dl className="flex flex-col gap-1.5">
                {g.atajos.map((a) => (
                  <div key={a.accion} className="flex items-center justify-between gap-3">
                    <dt className="text-sm text-foreground">{a.accion}</dt>
                    <dd className="flex shrink-0 items-center gap-1">
                      {a.teclas.map((t) => (
                        <Tecla key={t}>{t}</Tecla>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

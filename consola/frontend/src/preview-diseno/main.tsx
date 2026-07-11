/**
 * Página de decisión de variantes de diseño: muestra lado a lado, con los componentes
 * REALES de la consola (mismas clases Tailwind, mismos tokens), las alternativas de cada
 * decisión de unificación visual pendiente. Cada sección corresponde a una pregunta de la
 * ronda de decisiones. NO entra en el build de producción; se abre navegando a
 * `/preview-diseno.html` con `npm run dev`. Incluye interruptor claro/oscuro propio porque
 * varias variantes solo divergen en tema oscuro.
 */
/* eslint-disable react-refresh/only-export-components */
import { Moon, MoreHorizontal, Pencil, Sun, Trash2 } from "lucide-react";
import * as React from "react";
import ReactDOM from "react-dom/client";
import { toast } from "sonner";

import "@/index.css";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import { type ContextoTema, TemaContext } from "@/hooks/tema-contexto";
import { cn } from "@/lib/utils";

/* ---------- armazón de la página ---------- */

function Seccion({
  id,
  titulo,
  pregunta,
  columnas = 3,
  children,
}: {
  id: string;
  titulo: string;
  pregunta: string;
  columnas?: 1 | 2 | 3;
  children: React.ReactNode;
}) {
  const grid =
    columnas === 1 ? "grid-cols-1" : columnas === 2 ? "md:grid-cols-2" : "md:grid-cols-3";
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">
          {id} · {titulo}
        </h2>
        <p className="text-sm text-muted-foreground">{pregunta}</p>
      </div>
      <div className={cn("grid gap-4", grid)}>{children}</div>
    </section>
  );
}

function Opcion({
  letra,
  nombre,
  recomendada,
  nota,
  children,
}: {
  letra: string;
  nombre: string;
  recomendada?: boolean;
  nota?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">
          {letra} — {nombre}
        </span>
        {recomendada && (
          <Badge variant="secondary" className="text-[10px]">
            recomendada
          </Badge>
        )}
      </div>
      <div className="flex-1">{children}</div>
      {nota && <p className="text-xs text-muted-foreground">{nota}</p>}
    </div>
  );
}

/* ---------- piezas de maqueta reutilizadas ---------- */

const BTN = "h-7 px-2.5 text-xs"; // compacto de facto de la consola

function PieDialogo({ primario, cancelar }: { primario: React.ReactNode; cancelar: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-background p-4">
      <p className="text-sm font-semibold">Nueva campaña</p>
      <div className="mt-3 space-y-1.5">
        <Label className="text-xs">Nombre</Label>
        <Input className="h-8" placeholder="Verano Claro Sports" />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        {cancelar}
        {primario}
      </div>
    </div>
  );
}

function ConfirmarBorrado({ boton }: { boton: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-background p-4">
      <p className="text-sm font-semibold">¿Eliminar la pieza?</p>
      <p className="mt-1 text-xs text-muted-foreground">Esta acción no se puede deshacer.</p>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" className={BTN}>
          Cancelar
        </Button>
        {boton}
      </div>
    </div>
  );
}

function ItemPieza({ pad }: { pad: string }) {
  return (
    <div className={cn("flex items-center justify-between gap-3 rounded-xl border bg-card", pad)}>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">Resumen del partido América vs Chivas</p>
        <p className="truncate text-xs text-muted-foreground">Claro Sports · Instagram · hace 2 h</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge variant="ok">Completado</Badge>
        <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
      </div>
    </div>
  );
}

function Swatch({ hex, nombre }: { hex: string; nombre: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="inline-flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold text-white"
        style={{ backgroundColor: hex }}
      >
        {nombre.charAt(0)}
      </span>
      <div className="text-xs">
        <div className="font-medium">{nombre}</div>
        <div className="text-muted-foreground">{hex}</div>
      </div>
    </div>
  );
}

/* ---------- recetas de badge de estado que hoy conviven ---------- */

const CHIP_BASE = "inline-flex items-center rounded-md px-2.5 py-0.5 text-xs font-medium";

const RECETAS_ESTADO: { letra: string; nombre: string; nota: string; recomendada?: boolean; chips: { texto: string; clase: string }[] }[] = [
  {
    letra: "A",
    nombre: "Tinte suave 700/300 (Badge canónico)",
    nota: "La receta de badge.tsx (variantes ok/info/aviso/error). Legible en claro y oscuro.",
    recomendada: true,
    chips: [
      { texto: "Completado", clase: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" },
      { texto: "En curso", clase: "bg-sky-500/15 text-sky-700 dark:text-sky-300" },
      { texto: "Revisar", clase: "bg-amber-500/15 text-amber-700 dark:text-amber-300" },
      { texto: "Error", clase: "bg-red-500/15 text-red-700 dark:text-red-300" },
    ],
  },
  {
    letra: "B",
    nombre: "Tinte suave 600 + borde (ChipEstado actual)",
    nota: "La usa ChipEstado y Pipelines. Sin par oscuro: en tema oscuro el texto 600 queda apagado.",
    chips: [
      { texto: "Completado", clase: "border border-emerald-500/30 bg-emerald-500/15 text-emerald-600" },
      { texto: "En curso", clase: "border border-sky-500/30 bg-sky-500/15 text-sky-600" },
      { texto: "Revisar", clase: "border border-amber-500/30 bg-amber-500/15 text-amber-600" },
      { texto: "Error", clase: "border border-red-500/30 bg-red-500/15 text-red-600" },
    ],
  },
  {
    letra: "C",
    nombre: "Relleno claro 50/800 (estado-color.ts)",
    nota: "La usan CalendarioPreview y rota-calendario. Más saturada; requiere 4 clases dark por color.",
    chips: [
      {
        texto: "Completado",
        clase:
          "border border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
      },
      {
        texto: "En curso",
        clase:
          "border border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300",
      },
      {
        texto: "Revisar",
        clase:
          "border border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
      },
      {
        texto: "Error",
        clase:
          "border border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300",
      },
    ],
  },
  {
    letra: "D",
    nombre: "Outline (semáforo de estado-color.ts)",
    nota: "Solo borde y texto, sin fondo. La usa el semáforo de cobertura.",
    chips: [
      { texto: "Completado", clase: "border border-emerald-500/50 text-emerald-700 dark:text-emerald-300" },
      { texto: "En curso", clase: "border border-sky-500/50 text-sky-700 dark:text-sky-300" },
      { texto: "Revisar", clase: "border border-amber-500/50 text-amber-700 dark:text-amber-300" },
      { texto: "Error", clase: "border border-red-500/50 text-red-700 dark:text-red-300" },
    ],
  },
];

/* ---------- app ---------- */

function App() {
  const [oscuro, setOscuro] = React.useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );
  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", oscuro);
  }, [oscuro]);
  const tema: ContextoTema = React.useMemo(
    () => ({
      tema: oscuro ? "dark" : "light",
      esOscuro: oscuro,
      alternar: () => setOscuro((v) => !v),
      fijar: (t) => setOscuro(t === "oscuro"),
    }),
    [oscuro],
  );

  return (
    <TemaContext.Provider value={tema}>
      {/* index.css bloquea el scroll del documento (overflow:hidden en body); el scroll vive aquí. */}
      <div className="h-screen overflow-y-auto bg-background font-sans text-foreground antialiased">
        <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3">
            <div>
              <h1 className="text-base font-semibold">Sistema de diseño · Consola — decisiones cerradas</h1>
              <p className="text-xs text-muted-foreground">
                Componentes reales de la app mostrando el estándar único decidido (11-jul-2026).
                La especificación completa vive en docs/sistema-diseno.md.
              </p>
            </div>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => setOscuro(!oscuro)}
              aria-label="Alternar tema"
            >
              {oscuro ? <Sun /> : <Moon />}
            </Button>
          </div>
        </header>

        <main className="mx-auto max-w-5xl space-y-12 px-6 py-8">
          <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Ronda 1 · Botones</span> — cómo se señala
            el primario, el destructivo, la altura estándar y el Cancelar.
          </p>

          <Seccion
            id="1.1"
            titulo="Botón primario — DECIDIDO"
            pregunta="Elegido el relleno oscuro (variante primary): negro en claro, blanco en oscuro, plano y sin sombra. Cancelar ghost. Todas las secciones siguientes ya lo usan."
            columnas={2}
          >
            <Opcion
              letra="✓"
              nombre="Relleno oscuro (elegida)"
              nota="El primario de toda la app. Se identifica al instante, monocromo, estilo Vercel."
            >
              <PieDialogo
                cancelar={
                  <Button variant="ghost" className={BTN}>
                    Cancelar
                  </Button>
                }
                primario={
                  <Button variant="default" className={BTN}>
                    Guardar
                  </Button>
                }
              />
            </Opcion>
          </Seccion>

          <Seccion
            id="1.2"
            titulo="Acción destructiva — DECIDIDO"
            pregunta="Elegida A: ghost rojo siempre; el botón de confirmar del diálogo va neutro con el primario oscuro."
            columnas={2}
          >
            <Opcion
              letra="✓"
              nombre="Ghost rojo (elegida)"
              nota="Discreto; la protección real la da el diálogo confirmar()."
            >
              <div className="space-y-3">
                <Button variant="ghost" className={cn(BTN, "text-destructive hover:text-destructive")}>
                  <Trash2 /> Eliminar
                </Button>
                <ConfirmarBorrado
                  boton={
                    <Button variant="default" className={BTN}>
                      Sí, eliminar
                    </Button>
                  }
                />
              </div>
            </Opcion>
          </Seccion>

          <Seccion
            id="1.3"
            titulo="Altura y Cancelar — DECIDIDOS"
            pregunta="Altura estándar h-7 compacta (se formaliza en el componente, cero cambio visual) y Cancelar ghost, plano."
            columnas={2}
          >
            <Opcion
              letra="✓"
              nombre="h-7 + Cancelar ghost (elegidas)"
              nota="El trío estándar de la app: acción normal outline, primario oscuro, Cancelar ghost — todos a h-7."
            >
              <div className="flex flex-wrap items-center gap-2">
                <Button className="h-7 px-2.5 text-xs">
                  <Pencil /> Editar
                </Button>
                <Button variant="ghost" className="h-7 px-2.5 text-xs">
                  Cancelar
                </Button>
                <Button variant="default" className="h-7 px-2.5 text-xs">
                  Guardar
                </Button>
              </div>
            </Opcion>
          </Seccion>

          <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Ronda 2 · Color y badges</span> — la
            receta única de estado, el rojo de error, la forma de los chips y la paleta de marca.
          </p>

          <Seccion
            id="2.1"
            titulo="Badge de estado — DECIDIDO"
            pregunta="Elegida A: tinte suave 700/300 (la receta del Badge canónico), única en toda la app. El error usa el token destructive (decisión 2.2)."
            columnas={2}
          >
            <Opcion
              letra="✓"
              nombre="Tinte suave 700/300 (elegida)"
              nota="ChipEstado, Pipelines, calendarios y semáforos migran a esta receta."
            >
              <div className="flex flex-wrap gap-2">
                {RECETAS_ESTADO[0].chips.map((c) => (
                  <span key={c.texto} className={cn(CHIP_BASE, c.clase)}>
                    {c.texto}
                  </span>
                ))}
                <span className={cn(CHIP_BASE, "bg-destructive/10 text-destructive")}>Error (token)</span>
                <span className={cn(CHIP_BASE, "border text-muted-foreground")}>Pendiente</span>
              </div>
            </Opcion>
          </Seccion>

          <Seccion
            id="2.2 + 2.3"
            titulo="Rojo de error y forma de chip — DECIDIDOS"
            pregunta="Error siempre con el token destructive (un solo rojo en la app). Chips rectangulares rounded-md; las píldoras quedan solo para contadores."
            columnas={2}
          >
            <Opcion letra="✓" nombre="Token destructive (elegida)" nota="Badges, textos y botones de error beben del mismo rojo del tema.">
              <div className="flex flex-wrap items-center gap-2">
                <span className={cn(CHIP_BASE, "bg-destructive/10 text-destructive")}>Error</span>
                <span className="text-xs text-destructive">No se pudo publicar la pieza.</span>
              </div>
            </Opcion>
            <Opcion letra="✓" nombre="Chips rectangulares (elegida)" nota="La forma del componente Badge en toda la app.">
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">Deportes</Badge>
                <Badge variant="secondary">Tendencia</Badge>
                <Badge variant="outline">Evergreen</Badge>
              </div>
            </Opcion>
          </Seccion>

          <Seccion
            id="2.4"
            titulo="Paleta de marca — DECIDIDA"
            pregunta="UnoTV toma el azul navy de la portada de los informes; Claro Sports su rojo corporativo. Un solo módulo de paleta para organigrama, informes y avatares."
            columnas={2}
          >
            <Opcion letra="✓" nombre="UnoTV navy + Claro Sports rojo (elegida)" nota="Se elimina el azul #2563eb del organigrama y el rojo #E4002B queda solo como acento del wordmark en informes si hace falta.">
              <div className="flex flex-wrap gap-6">
                <Swatch hex="#16273F" nombre="UnoTV" />
                <Swatch hex="#DA291C" nombre="Claro Sports" />
              </div>
            </Opcion>
          </Seccion>

          <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Ronda 3 · Componentes</span> — título de
            tarjeta, densidad de los ítems de lista, pestañas de sección y tooltips.
          </p>

          <Seccion
            id="3.1 + 3.2"
            titulo="Título de tarjeta y densidad — DECIDIDOS"
            pregunta="Título de tarjeta: text-sm font-semibold (CardTitle se alinea). Ítems repetidos de lista: p-3; tarjetas sueltas: p-4/p-6."
            columnas={2}
          >
            <Opcion letra="✓" nombre="Título text-sm font-semibold (elegida)" nota="El estándar de facto pasa a ser el único.">
              <Card>
                <CardHeader className="p-4 pb-2">
                  <CardTitle className="text-sm font-semibold">Rendimiento semanal</CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0 text-sm text-muted-foreground">
                  128 piezas publicadas · +12 % vs semana anterior
                </CardContent>
              </Card>
            </Opcion>
            <Opcion letra="✓" nombre="Ítem de lista p-3 (elegida)" nota="Ritmo de lista y proporción con la tipografía compacta.">
              <div className="space-y-2">
                <ItemPieza pad="p-3" />
                <ItemPieza pad="p-3" />
              </div>
            </Opcion>
          </Seccion>

          <Seccion
            id="3.3 + 3.4"
            titulo="Pestañas de sección y tooltips — DECIDIDOS"
            pregunta="Las secciones de página navegan SIEMPRE en la barra superior (migran Inbox, Fuentes y Programa). Tooltips siempre con el componente; title= queda prohibido."
            columnas={2}
          >
            <Opcion
              letra="✓"
              nombre="Secciones en la barra superior (elegida)"
              nota="El cuerpo queda limpio para el contenido; las Tabs segmentadas quedan solo para conmutar vistas dentro del contenido."
            >
              <div className="rounded-xl border bg-background">
                <div className="flex items-center gap-4 border-b px-4">
                  <span className="border-b-2 border-foreground py-2 text-sm font-medium">Entrantes</span>
                  <span className="py-2 text-sm text-muted-foreground">Aprobadas</span>
                  <span className="py-2 text-sm text-muted-foreground">Archivo</span>
                </div>
                <div className="p-4 text-xs text-muted-foreground">…contenido de la sección…</div>
              </div>
            </Opcion>
            <Opcion
              letra="✓"
              nombre="Componente Tooltip (elegida)"
              nota="Instantáneo, estilado y accesible. Pasa el ratón para verlo."
            >
              <div className="flex items-center gap-2">
                <Tooltip label="Editar pieza">
                  <Button variant="ghost" size="icon" className="h-7 w-7">
                    <Pencil />
                  </Button>
                </Tooltip>
                <Tooltip label="Eliminar pieza">
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive">
                    <Trash2 />
                  </Button>
                </Tooltip>
              </div>
            </Opcion>
          </Seccion>

          <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Ronda 4 · Feedback y formularios</span> —
            estados de carga, confirmación de éxito, espaciado de campos y texto secundario.
          </p>

          <Seccion
            id="4.1 + 4.2"
            titulo="Carga y confirmación de éxito — DECIDIDOS"
            pregunta="Skeleton con forma para listados/dashboards y spinner para diálogos/acciones; el texto pelado desaparece. Toast de éxito SIEMPRE tras acción del usuario (el silencio queda para autoguardados)."
            columnas={2}
          >
            <Opcion letra="✓" nombre="Skeleton (listados) + spinner (acciones)" nota="La página no salta al llegar los datos; la espera puntual gira.">
              <div className="space-y-2">
                <Skeleton className="h-10 rounded-xl" />
                <Skeleton className="h-10 rounded-xl" />
                <div className="flex h-10 items-center justify-center gap-2 rounded-xl border border-dashed">
                  <Spinner className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">Guardando…</span>
                </div>
              </div>
            </Opcion>
            <Opcion letra="✓" nombre="Toast de éxito siempre (pruébalo)" nota="Toda acción del usuario confirma.">
              <Button
                variant="default"
                className={BTN}
                onClick={() => toast.success("Cambios guardados")}
              >
                Guardar cambios
              </Button>
            </Opcion>
          </Seccion>

          <Seccion
            id="4.3 + 4.4"
            titulo="Formularios y texto secundario — DECIDIDOS"
            pregunta="Separación entre campos space-y-4 (label y control prietos con space-y-1.5). Metadata de tarjetas/listas/tablas en text-xs; text-sm reservado para párrafos y descripciones."
            columnas={2}
          >
            <Opcion letra="✓" nombre="space-y-4 entre campos (elegida)" nota="Aire estándar shadcn; formularios que respiran.">
              <div className="space-y-4 rounded-xl border bg-background p-4">
                <div className="space-y-1.5">
                  <Label className="text-xs">Nombre</Label>
                  <Input className="h-8" placeholder="Campaña de verano" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Marca</Label>
                  <Input className="h-8" placeholder="Claro Sports" />
                </div>
              </div>
            </Opcion>
            <Opcion letra="✓" nombre="Metadata en text-xs (elegida)" nota="Coherente con la densidad compacta del sistema.">
              <div className="rounded-xl border bg-card p-3">
                <p className="text-sm font-medium">Resumen del partido América vs Chivas</p>
                <p className="text-xs text-muted-foreground">Claro Sports · Instagram · hace 2 h · 1.2k interacciones</p>
              </div>
            </Opcion>
          </Seccion>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Correcciones sin decisión (violaciones del canon existente)</h2>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              <li>El único window.confirm de la app (Fotos) pasa al diálogo confirmar() canónico.</li>
              <li>Las 2 páginas de detalle con cabecera en el cuerpo migran a TituloPagina con flecha atrás.</li>
              <li>El grid de Economía sin breakpoints (no colapsa en móvil) se corrige.</li>
              <li>La pantalla de login usa colores neutral fijos que ignoran el tema: pasa a tokens.</li>
              <li>Las 2 tablas reconstruidas a mano (Marcas, ReparteMes) migran a ui/table.</li>
              <li>Los callouts ámbar pintados a mano migran al componente Aviso.</li>
              <li>Los iconos dentro de botones se normalizan al tamaño que fuerza el componente.</li>
            </ul>
          </section>
        </main>
        <Toaster />
      </div>
    </TemaContext.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

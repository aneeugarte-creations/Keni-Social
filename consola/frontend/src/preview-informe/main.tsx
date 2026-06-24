/**
 * Vista previa del Informe (deck PDF de Métricas) en localhost. Monta el componente REAL
 * `<Informe>` a través del adaptador REAL `desdeEntradas`, alimentado por datos de muestra con
 * la forma cruda del backend — de modo que cualquier insight nuevo del adaptador aparece aquí
 * igual que en producción. Un selector cambia entre marcas / "todas". Solo para iterar diseño;
 * NO entra en el build de producción (no es un input del rollup; lo sirve `servir.sh`).
 */
/* eslint-disable react-refresh/only-export-components */
import * as React from "react";
import ReactDOM from "react-dom/client";

import "@/index.css";

import { Informe } from "@/pages/metricas/informe/Informe";
import { desdeEntradas } from "@/pages/metricas/informe/desdeEntradas";
import { descargarPresentacion } from "@/pages/metricas/exportarPdf";
import { MUESTRAS } from "./datos";

const CLAVES = Object.keys(MUESTRAS);

function Vista() {
  const params = new URLSearchParams(location.search);
  const inicial = params.get("marca") ?? "unotv";
  const [clave, setClave] = React.useState(CLAVES.includes(inicial) ? inicial : "unotv");
  const [breve, setBreve] = React.useState(params.get("breve") === "1");
  const muestra = MUESTRAS[clave];
  const data = React.useMemo(() => desdeEntradas(muestra.entradas, muestra.ctx), [muestra]);

  return (
    <div style={{ background: "#e9e9ec", height: "100vh", overflowY: "auto", padding: "32px 0 64px" }}>
      <div
        data-preview-toolbar
        style={{
          position: "fixed",
          top: 16,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 50,
          display: "flex",
          gap: 8,
          padding: "8px 10px",
          background: "rgba(255,255,255,0.92)",
          borderRadius: 12,
          boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
          backdropFilter: "blur(8px)",
        }}
      >
        {CLAVES.map((k) => (
          <button
            key={k}
            onClick={() => setClave(k)}
            style={{
              fontFamily: "Geist, sans-serif",
              fontSize: 13,
              padding: "6px 12px",
              borderRadius: 8,
              border: "1px solid " + (k === clave ? "#111827" : "#e5e7eb"),
              background: k === clave ? "#111827" : "#fff",
              color: k === clave ? "#fff" : "#374151",
              cursor: "pointer",
            }}
          >
            {MUESTRAS[k].ctx.marca}
          </button>
        ))}
        <button
          data-genpdf
          onClick={() => void descargarPresentacion(muestra.entradas, muestra.ctx, clave, { breve })}
          style={{
            fontFamily: "Geist, sans-serif",
            fontSize: 13,
            padding: "6px 12px",
            borderRadius: 8,
            border: "1px solid #e5e7eb",
            background: "#fff",
            color: "#374151",
            cursor: "pointer",
            marginLeft: 8,
          }}
        >
          PDF
        </button>
        <button
          onClick={() => setBreve((b) => !b)}
          style={{
            fontFamily: "Geist, sans-serif",
            fontSize: 13,
            padding: "6px 12px",
            borderRadius: 8,
            border: "1px solid " + (breve ? "#ea580c" : "#e5e7eb"),
            background: breve ? "#ea580c" : "#fff",
            color: breve ? "#fff" : "#374151",
            cursor: "pointer",
            marginLeft: 8,
          }}
        >
          {breve ? "Breve ✓" : "Breve"}
        </button>
      </div>

      {/* Cada diapositiva del deck es 1280×720; las apilamos centradas con una sombra suave
          para distinguirlas, igual que se verían como páginas del PDF. */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 28 }}>
        {React.Children.map(<Informe data={data} breve={breve} />, (n) => n)}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Vista />
  </React.StrictMode>,
);

import React from "react";
import ReactDOM from "react-dom/client";

import "@/index.css";
import "./presentacion.css";
import { Presentacion } from "./Presentacion";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Presentacion />
  </React.StrictMode>,
);

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./index.css";
import { PhoenixProvider } from "./store";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PhoenixProvider>
      <App />
    </PhoenixProvider>
  </React.StrictMode>,
);

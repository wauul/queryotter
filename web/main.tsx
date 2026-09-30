import React from "react";
import { createRoot } from "react-dom/client";
import Studio from "./Studio";
import { ThemeProvider } from "./Theme";
import { LanguageProvider } from "./Language";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./style.css";
import "./studio.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LanguageProvider>
      <ThemeProvider>
        <Studio />
      </ThemeProvider>
    </LanguageProvider>
  </React.StrictMode>,
);

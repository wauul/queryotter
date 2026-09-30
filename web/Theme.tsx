import React, {
  createContext,
  useContext,
  useLayoutEffect,
  useState,
} from "react";
import { Monitor, Moon, Sun } from "lucide-react";

type ThemeMode = "system" | "light" | "dark";
const ThemeContext = createContext<{
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}>({ mode: "system", setMode: () => {} });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const initial = document.documentElement.dataset.themeMode;
    return initial === "light" || initial === "dark" ? initial : "system";
  });
  useLayoutEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    function apply() {
      const theme =
        mode === "system" ? (media.matches ? "dark" : "light") : mode;
      document.documentElement.dataset.theme = theme;
      document.documentElement.dataset.themeMode = mode;
      document.documentElement.style.colorScheme = theme;
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute("content", theme === "dark" ? "#101c24" : "#f3f6f8");
    }
    apply();
    try {
      localStorage.setItem("queryotter-theme", mode);
    } catch {
      /* Session preference still works when storage is unavailable. */
    }
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode]);
  return (
    <ThemeContext.Provider value={{ mode, setMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function ThemeControl() {
  const { mode, setMode } = useContext(ThemeContext);
  const Icon = mode === "system" ? Monitor : mode === "dark" ? Moon : Sun;
  return (
    <label className="q-theme-control">
      <Icon size={16} aria-hidden="true" />
      <span className="q-sr-only">Color theme</span>
      <select
        value={mode}
        onChange={(e) => setMode(e.target.value as ThemeMode)}
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}

import React, {
  createContext,
  useContext,
  useLayoutEffect,
  useState,
} from "react";
import { Moon, Sun } from "lucide-react";
import { useLanguage, LanguageControl } from "./Language";

type ThemeMode = "system" | "light" | "dark";
const ThemeContext = createContext<{
  mode: ThemeMode;
  theme: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
}>({ mode: "system", theme: "light", setMode: () => {} });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
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
      setResolvedTheme(theme);
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
    <ThemeContext.Provider value={{ mode, theme: resolvedTheme, setMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function ThemeControl() {
  const { theme, setMode } = useContext(ThemeContext);
  const { t } = useLanguage();
  const Icon = theme === "dark" ? Moon : Sun;
  return (
    <button
      className="q-theme-toggle"
      aria-label={t("Dark mode")}
      aria-pressed={theme === "dark"}
      title={t(
        theme === "dark" ? "Switch to light mode" : "Switch to dark mode",
      )}
      onClick={() => setMode(theme === "dark" ? "light" : "dark")}
    >
      <Icon size={19} aria-hidden="true" />
    </button>
  );
}
export function Preferences() {
  return (
    <div className="q-preferences">
      <LanguageControl />
      <ThemeControl />
    </div>
  );
}

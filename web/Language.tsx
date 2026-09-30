import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Check, ChevronDown, Globe2 } from "lucide-react";
import french from "./locales/fr.json";

export type Language = "en" | "fr";
type Values = Record<string, string | number>;
type Translator = (text: string, values?: Values) => string;
const frenchCopy: Record<string, string> = french;
export function translate(
  text: string,
  language: Language,
  values: Values = {},
) {
  if (!text.trim()) return text;
  const prefix = text.match(/^\s*/)?.[0] || "";
  const suffix = text.match(/\s*$/)?.[0] || "";
  const key = text.trim().replace(/\s+/g, " ");
  const translated = language === "fr" ? frenchCopy[key] : undefined;
  return (
    translated === undefined ? text : prefix + translated + suffix
  ).replace(/\{(\w+)\}/g, (all, name) =>
    values[name] === undefined ? all : String(values[name]),
  );
}
const LanguageContext = createContext<{
  language: Language;
  setLanguage: (language: Language) => void;
  t: Translator;
}>({ language: "en", setLanguage: () => {}, t: (text) => text });
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, updateLanguage] = useState<Language>(() =>
    document.documentElement.lang === "fr" ? "fr" : "en",
  );
  function setLanguage(next: Language) {
    document.documentElement.lang = next;
    try {
      localStorage.setItem("queryotter-language", next);
    } catch {
      /* The current session still works. */
    }
    updateLanguage(next);
  }
  const t: Translator = (text, values) => translate(text, language, values);
  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}
export const useLanguage = () => useContext(LanguageContext);
export function LanguageControl() {
  const { language, setLanguage, t } = useLanguage();
  const languages: { value: Language; name: string }[] = [
    { value: "en", name: "English" },
    { value: "fr", name: "Français" },
  ];
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(0);
  const control = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const options = useRef<(HTMLButtonElement | null)[]>([]);
  const listId = useId();
  const current = languages.findIndex((item) => item.value === language);
  useEffect(() => {
    if (!open) return;
    setFocused(current);
    options.current[current]?.focus();
    const outside = (event: PointerEvent) => {
      if (!control.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open, current]);
  function close() {
    setOpen(false);
    trigger.current?.focus();
  }
  return (
    <div
      ref={control}
      className="q-language-control"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <button
        ref={trigger}
        className="q-language-trigger"
        aria-label={`${t("Language")}: ${languages[current].name}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <Globe2 className="q-language-icon" size={16} aria-hidden="true" />
        <span lang={language}>{languages[current].name}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div
          id={listId}
          role="listbox"
          aria-label={t("Language")}
          className="q-language-menu"
          onKeyDown={(event) => {
            let next = focused;
            if (event.key === "Escape") {
              event.preventDefault();
              event.stopPropagation();
              close();
              return;
            }
            if (event.key === "ArrowDown")
              next = (focused + 1) % languages.length;
            else if (event.key === "ArrowUp")
              next = (focused + languages.length - 1) % languages.length;
            else if (event.key === "Home" || event.key.toLowerCase() === "e")
              next = 0;
            else if (event.key === "End" || event.key.toLowerCase() === "f")
              next = 1;
            else return;
            event.preventDefault();
            setFocused(next);
            options.current[next]?.focus();
          }}
        >
          {languages.map((item, index) => (
            <button
              key={item.value}
              ref={(element) => {
                options.current[index] = element;
              }}
              role="option"
              lang={item.value}
              aria-selected={language === item.value}
              tabIndex={focused === index ? 0 : -1}
              onFocus={() => setFocused(index)}
              onClick={() => {
                setLanguage(item.value);
                close();
              }}
            >
              {item.name}
              {language === item.value && (
                <Check size={16} aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

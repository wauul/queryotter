(function () {
  var mode = "system";
  try {
    var saved = localStorage.getItem("queryotter-theme");
    if (saved === "light" || saved === "dark") mode = saved;
  } catch (_) {}
  var theme =
    mode === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : mode;
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.style.colorScheme = theme;
  var language =
    typeof navigator !== "undefined" && /^fr\b/i.test(navigator.language)
      ? "fr"
      : "en";
  try {
    var savedLanguage = localStorage.getItem("queryotter-language");
    if (savedLanguage === "en" || savedLanguage === "fr")
      language = savedLanguage;
  } catch (_) {}
  document.documentElement.lang = language;
})();

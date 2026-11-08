import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { vi } from "./vi";
import { en } from "./en";
import type { Lang } from "../api/types";

const LANG_KEY = "mentor.lang";

export function storedLang(): Lang {
  try {
    return localStorage.getItem(LANG_KEY) === "en" ? "en" : "vi";
  } catch {
    return "vi";
  }
}

/** Switch UI language and remember it (so the login screen opens in the last used language). */
export function setLang(lang: Lang) {
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* ignore */
  }
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
}

void i18n.use(initReactI18next).init({
  resources: { vi: { translation: vi }, en: { translation: en } },
  lng: storedLang(),
  fallbackLng: "vi",
  interpolation: { escapeValue: false },
  returnNull: false,
});
document.documentElement.lang = storedLang();

export default i18n;

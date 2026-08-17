import { en } from "/static/locale_en.js";
import { zhTW } from "/static/locale_zh_tw.js";

const LOCALES = { en, "zh-TW": zhTW };
const STORAGE_KEY = "scopes-tool-webui-locale";
let currentLocale = localStorage.getItem(STORAGE_KEY) || "en";

export function locale() {
  return currentLocale;
}

export function setLocale(value) {
  currentLocale = LOCALES[value] ? value : "en";
  localStorage.setItem(STORAGE_KEY, currentLocale);
  document.documentElement.lang = currentLocale === "zh-TW" ? "zh-Hant-TW" : "en";
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = translate(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = translate(element.dataset.i18nPlaceholder);
  });
  document.dispatchEvent(new CustomEvent("localechange", { detail: currentLocale }));
}

export function translate(key) {
  return LOCALES[currentLocale][key] || LOCALES.en[key] || key;
}

export function initializeI18n() {
  setLocale(currentLocale);
}

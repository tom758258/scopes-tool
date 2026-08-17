import { en } from "/static/locale_en.js";
import { zhTW } from "/static/locale_zh_tw.js";

const LOCALES = { en, "zh-TW": zhTW };
const STORAGE_KEY = "scopes-tool-webui-locale";
let currentLocale = localStorage.getItem(STORAGE_KEY) || "en";
const JOB_STATUS_KEYS = {
  queued: "status.queued",
  running: "status.running",
  completed: "status.completed",
  failed: "status.failedJob",
  cancelled: "status.cancelled",
};

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
  document.querySelectorAll("[data-i18n-title]").forEach((element) => {
    element.title = translate(element.dataset.i18nTitle);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", translate(element.dataset.i18nAriaLabel));
  });
  const title = document.querySelector("title[data-i18n]");
  if (title) document.title = translate(title.dataset.i18n);
  document.dispatchEvent(new CustomEvent("localechange", { detail: currentLocale }));
}

export function translate(key, values = {}) {
  let text = LOCALES[currentLocale][key] || LOCALES.en[key] || key;
  Object.entries(values).forEach(([name, value]) => {
    text = text.replaceAll(`{{${name}}}`, String(value));
  });
  return text;
}

export function translateJobStatus(status) {
  return translate(JOB_STATUS_KEYS[status] || status);
}

export function initializeI18n() {
  setLocale(currentLocale);
}

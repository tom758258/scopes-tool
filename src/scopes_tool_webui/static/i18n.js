import { en } from "/static/locale_en.js";
import { zhTW } from "/static/locale_zh_tw.js";

const LOCALES = { en, "zh-TW": zhTW };
const STORAGE_KEY = "scopes-tool-webui-locale";
let currentLocale = readSavedLocale() || detectBrowserLocale();
const JOB_STATUS_KEYS = {
  queued: "status.queued",
  running: "status.running",
  completed: "status.completed",
  failed: "status.failedJob",
  cancelled: "status.cancelled",
};

function isSupportedLocale(value) {
  return value === "en" || value === "zh-TW";
}

function readSavedLocale() {
  try {
    const saved = globalThis.localStorage?.getItem(STORAGE_KEY);
    return isSupportedLocale(saved) ? saved : null;
  } catch (_error) {
    return null;
  }
}

function detectBrowserLocale() {
  let navigatorLike;
  try {
    navigatorLike = globalThis.navigator;
  } catch (_error) {
    return "en";
  }
  let language;
  try {
    if (Array.isArray(navigatorLike?.languages)) {
      language = navigatorLike.languages.find((value) => typeof value === "string" && value.trim());
    }
  } catch (_error) {
    // Fall back to navigator.language when languages is unavailable.
  }
  if (!language) {
    try {
      language = navigatorLike?.language;
    } catch (_error) {
      // Browser locale access must not prevent WebUI initialization.
    }
  }
  const normalized = typeof language === "string" ? language.trim().replaceAll("_", "-").toLowerCase() : "";
  return normalized === "zh-tw" || normalized.startsWith("zh-tw-")
    || normalized === "zh-hant" || normalized.startsWith("zh-hant-") ? "zh-TW" : "en";
}

export function locale() {
  return currentLocale;
}

export function setLocale(value) {
  currentLocale = isSupportedLocale(value) ? value : "en";
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, currentLocale);
  } catch (_error) {
    // Keep language switching available when browser storage is unavailable.
  }
  applyLocale();
}

function applyLocale() {
  document.documentElement.lang = currentLocale;
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

export function hasTranslation(key) {
  return Boolean(LOCALES[currentLocale][key] || LOCALES.en[key]);
}

export function translateJobStatus(status) {
  return translate(JOB_STATUS_KEYS[status] || status);
}

export function initializeI18n() {
  applyLocale();
}

// Tema: sistem / açık / koyu (tercih bu cihazda saklanır).
import { $$, store } from './util.js';
import { icon } from './icons.js';

const KEY = 'theme';
const darkMq = window.matchMedia('(prefers-color-scheme: dark)');

export function themePref() {
  const v = store.get(KEY, 'system');
  return v === 'light' || v === 'dark' ? v : 'system';
}

export function effectiveTheme() {
  const pref = themePref();
  return pref === 'system' ? (darkMq.matches ? 'dark' : 'light') : pref;
}

export function applyTheme() {
  const eff = effectiveTheme();
  document.documentElement.dataset.theme = eff;
  document.documentElement.dataset.themePref = themePref();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', eff === 'dark' ? '#0f1115' : '#f4f5f8');
  for (const b of $$('[data-theme-toggle]')) {
    const next = eff === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç';
    b.setAttribute('aria-label', next);
    b.setAttribute('title', next);
    const ic = b.querySelector('.theme-ic');
    if (ic) ic.innerHTML = icon(eff === 'dark' ? 'sun' : 'moon', { size: b.classList.contains('side-link') ? 20 : 22 }).s;
    const lb = b.querySelector('.theme-label');
    if (lb) lb.textContent = eff === 'dark' ? 'Açık tema' : 'Koyu tema';
  }
}

export function setThemePref(pref) {
  store.set(KEY, pref);
  applyTheme();
  document.dispatchEvent(new CustomEvent('autosell:theme'));
}

export function toggleTheme() {
  setThemePref(effectiveTheme() === 'dark' ? 'light' : 'dark');
}

darkMq.addEventListener('change', () => {
  if (themePref() === 'system') applyTheme();
});

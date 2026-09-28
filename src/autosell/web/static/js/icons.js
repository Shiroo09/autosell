// Satır içi SVG simge seti (24×24, çizgi tabanlı). Dış kaynak kullanılmaz.
import { raw, esc } from './util.js';

// Dişli (ayarlar) simgesi: düzgün bir çokgen olarak hesaplanır.
function gearPath() {
  const teeth = 8, rOut = 9.6, rIn = 7.3, cx = 12, cy = 12;
  const step = (Math.PI * 2) / teeth;
  const pts = [];
  for (let i = 0; i < teeth; i++) {
    const a = i * step - Math.PI / 2;
    const half = step * 0.2;
    const slope = step * 0.1;
    pts.push([a - half - slope, rIn], [a - half, rOut], [a + half, rOut], [a + half + slope, rIn]);
  }
  const xy = pts.map(([a, r]) => `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`);
  return `<path d="M${xy.join('L')}Z"/><circle cx="12" cy="12" r="3"/>`;
}

const P = {
  home: '<path d="M3.5 10.2 12 3.5l8.5 6.7"/><path d="M5.5 8.8V19a1.5 1.5 0 0 0 1.5 1.5h3.2v-5.2h3.6v5.2H17a1.5 1.5 0 0 0 1.5-1.5V8.8"/>',
  tag: '<path d="M3.5 12.1V4.9c0-.8.6-1.4 1.4-1.4h7.2c.4 0 .7.1 1 .4l7.4 7.4c.6.6.6 1.4 0 2l-7.2 7.2c-.6.6-1.4.6-2 0l-7.4-7.4c-.3-.3-.4-.6-.4-1Z"/><circle cx="8.2" cy="8.2" r="1.6"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.6"/>',
  list: '<path d="M8.5 6h12M8.5 12h12M8.5 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01" stroke-width="2.6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.8"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>',
  settings: gearPath(),
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/>',
  eyeOff: '<path d="M10.2 5.7c.6-.1 1.2-.2 1.8-.2 6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.4 3.2M6.6 6.9C4 8.6 2.5 12 2.5 12s3.5 6.5 9.5 6.5c1.8 0 3.3-.5 4.6-1.3"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="m3.5 3.5 17 17"/>',
  chart: '<path d="M3.5 20.5h17"/><rect x="5" y="11" width="3.2" height="6.5" rx="1"/><rect x="10.4" y="5.5" width="3.2" height="12" rx="1"/><rect x="15.8" y="13.5" width="3.2" height="4" rx="1"/>',
  search: '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m20 20-4.3-4.3"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>',
  moon: '<path d="M20 14.6A8.3 8.3 0 0 1 9.4 4a8.3 8.3 0 1 0 10.6 10.6Z"/>',
  monitor: '<rect x="2.5" y="4" width="19" height="12.5" rx="2"/><path d="M8.5 20.5h7M12 16.5v4"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m4.5 12.5 5 5 10-10.5"/>',
  chevronLeft: '<path d="m14.5 5.5-6.5 6.5 6.5 6.5"/>',
  chevronRight: '<path d="m9.5 5.5 6.5 6.5-6.5 6.5"/>',
  chevronDown: '<path d="m5.5 9.5 6.5 6.5 6.5-6.5"/>',
  chevronUp: '<path d="m5.5 14.5 6.5-6.5 6.5 6.5"/>',
  arrowLeft: '<path d="M19.5 12h-15M10.5 6 4.5 12l6 6"/>',
  arrowRight: '<path d="M4.5 12h15M13.5 6l6 6-6 6"/>',
  arrowUp: '<path d="M12 19.5v-15M6 10.5l6-6 6 6"/>',
  arrowDown: '<path d="M12 4.5v15M6 13.5l6 6 6-6"/>',
  trash: '<path d="M4 6.8h16M9.8 11v5.5M14.2 11v5.5"/><path d="m5.8 6.8.9 11.7a2 2 0 0 0 2 1.9h6.6a2 2 0 0 0 2-1.9l.9-11.7"/><path d="M9 6.8V4.9c0-.8.6-1.4 1.4-1.4h3.2c.8 0 1.4.6 1.4 1.4v1.9"/>',
  pencil: '<path d="M4 20h4.2L19 9.2a2.9 2.9 0 0 0-4.2-4.2L4 15.8V20Z"/><path d="m13.5 6.5 4 4"/>',
  external: '<path d="M14 3.5h6.5V10M20.5 3.5 11 13"/><path d="M18.5 14v4.5a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2H10"/>',
  star: '<path d="m12 3.3 2.7 5.4 6 .9-4.4 4.2 1.1 6-5.4-2.8-5.4 2.8 1.1-6-4.4-4.2 6-.9Z"/>',
  starFill: '<path d="m12 3.3 2.7 5.4 6 .9-4.4 4.2 1.1 6-5.4-2.8-5.4 2.8 1.1-6-4.4-4.2 6-.9Z" fill="currentColor"/>',
  refresh: '<path d="M19.8 10.5A8 8 0 0 0 5.6 7.2L4 9"/><path d="M4 4.5V9h4.5"/><path d="M4.2 13.5a8 8 0 0 0 14.2 3.3L20 15"/><path d="M20 19.5V15h-4.5"/>',
  sparkles: '<path d="M10 3.5 11.7 8a2 2 0 0 0 1.3 1.3l4.5 1.7-4.5 1.7a2 2 0 0 0-1.3 1.3L10 18.5 8.3 14a2 2 0 0 0-1.3-1.3L2.5 11 7 9.3A2 2 0 0 0 8.3 8Z"/><path d="M18.5 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8Z"/><path d="M18 3.5l.6 1.4 1.4.6-1.4.6L18 7.5l-.6-1.4L16 5.5l1.4-.6Z"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.2"/><circle cx="9" cy="10" r="1.8"/><path d="m20.5 15.5-4.8-4.8L6.5 19.5"/>',
  camera: '<path d="M4 8.5c0-1.1.9-2 2-2h1.6l1.6-2.2h5.6l1.6 2.2H18c1.1 0 2 .9 2 2v9c0 1.1-.9 2-2 2H6c-1.1 0-2-.9-2-2Z"/><circle cx="12" cy="12.8" r="3.4"/>',
  upload: '<path d="M12 15.5v-11M7.5 9 12 4.5 16.5 9"/><path d="M4.5 15.5v2.5c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2v-2.5"/>',
  grip: '<g fill="currentColor" stroke="none"><circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/></g>',
  play: '<path d="M7.5 5.3v13.4c0 .8.9 1.3 1.5.8l10.2-6.7c.6-.4.6-1.2 0-1.6L9 4.5c-.6-.5-1.5 0-1.5.8Z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2.2"/>',
  alert: '<path d="M10.4 4.3 2.9 17.4c-.7 1.2.2 2.6 1.6 2.6h15c1.4 0 2.3-1.4 1.6-2.6L13.6 4.3c-.7-1.2-2.5-1.2-3.2 0Z"/><path d="M12 9.5v4"/><path d="M12 16.8h.01" stroke-width="2.4"/>',
  info: '<circle cx="12" cy="12" r="8.8"/><path d="M12 11v5.2"/><path d="M12 7.8h.01" stroke-width="2.4"/>',
  checkCircle: '<circle cx="12" cy="12" r="8.8"/><path d="m8.2 12.4 2.6 2.6 5-5.3"/>',
  xCircle: '<circle cx="12" cy="12" r="8.8"/><path d="m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6"/>',
  clock: '<circle cx="12" cy="12" r="8.8"/><path d="M12 7v5.2l3.2 2"/>',
  pin: '<path d="M12 21s-6.8-5.9-6.8-11.3a6.8 6.8 0 0 1 13.6 0C18.8 15.1 12 21 12 21Z"/><circle cx="12" cy="9.7" r="2.4"/>',
  bot: '<rect x="4" y="8" width="16" height="11.5" rx="3"/><path d="M12 4.5V8"/><circle cx="12" cy="3.8" r="1"/><path d="M9 13v1.5M15 13v1.5M2 12.5v3M22 12.5v3"/>',
  key: '<circle cx="8" cy="15" r="4.2"/><path d="m11 12 8.5-8.5M16 7l2.6 2.6M18.5 4.5l2 2"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/><path d="M12 14.5v2"/>',
  browser: '<rect x="3" y="4" width="18" height="16" rx="2.2"/><path d="M3 8.8h18"/><path d="M6.3 6.4h.01M8.8 6.4h.01" stroke-width="2.2"/>',
  send: '<path d="M20.5 3.5 10.2 13.8"/><path d="m20.5 3.5-6.4 17-3.9-6.7-6.7-3.9Z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
  type: '<path d="M5 7V4.5h14V7M12 4.5v15M9 19.5h6"/>',
  store: '<path d="M4 9.2 5.4 4.5h13.2L20 9.2"/><path d="M4 9.2c0 1.5 1.2 2.6 2.7 2.6s2.6-1.1 2.6-2.6c0 1.5 1.2 2.6 2.7 2.6s2.7-1.1 2.7-2.6c0 1.5 1.1 2.6 2.6 2.6S20 10.7 20 9.2"/><path d="M5.5 11.6v8.9h13v-8.9M10 20.5v-5h4v5"/>',
  bell: '<path d="M6 9.5a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15.5 6 9.5Z"/><path d="M10.2 20.5a2 2 0 0 0 3.6 0"/>',
  trendUp: '<path d="m3.5 16.5 5.5-5.5 4 4 7.5-7.5"/><path d="M15 7.5h5.5V13"/>',
  trendDown: '<path d="m3.5 7.5 5.5 5.5 4-4 7.5 7.5"/><path d="M15 16.5h5.5V11"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2.2"/><path d="M15.5 8.5V5.7c0-1.2-1-2.2-2.2-2.2H5.7c-1.2 0-2.2 1-2.2 2.2v7.6c0 1.2 1 2.2 2.2 2.2h2.8"/>',
  more: '<path d="M5.5 12h.01M12 12h.01M18.5 12h.01" stroke-width="3"/>',
  logout: '<path d="M14.5 4H18c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2h-3.5"/><path d="M9.5 16.5 5 12l4.5-4.5M5 12h11"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  link: '<path d="M10 13.8a4.3 4.3 0 0 0 6.1 0l3-3a4.3 4.3 0 0 0-6.1-6.1l-1.1 1.1"/><path d="M14 10.2a4.3 4.3 0 0 0-6.1 0l-3 3a4.3 4.3 0 0 0 6.1 6.1l1.1-1.1"/>',
  activity: '<path d="M3 12h3.8l2.7-7.5 5 15 2.7-7.5H21"/>',
  wifiOff: '<path d="m3.5 3.5 17 17"/><path d="M8.6 15.6a4.8 4.8 0 0 1 6.2-.6M5.3 12.2a9.5 9.5 0 0 1 4.3-2.3M2.5 8.8a14 14 0 0 1 3.4-2.2M13.5 9.6a9.6 9.6 0 0 1 5.2 2.6M10.4 5.1A14 14 0 0 1 21.5 8.8"/><path d="M12 19h.01" stroke-width="2.6"/>',
  box: '<path d="m12 3.2 8.3 4.3v9L12 20.8l-8.3-4.3v-9Z"/><path d="m3.7 7.5 8.3 4.4 8.3-4.4M12 11.9v8.9"/>',
  percent: '<path d="M18.5 5.5l-13 13"/><circle cx="7.3" cy="7.3" r="2.3"/><circle cx="16.7" cy="16.7" r="2.3"/>',
  coins: '<rect x="2.5" y="6" width="19" height="12" rx="2.2"/><circle cx="12" cy="12" r="2.6"/><path d="M6 9.5v5M18 9.5v5"/>',
  zap: '<path d="M13 2.8 4.8 13.2h6.4l-1 8 8.2-10.4H12Z"/>',
  bulb: '<path d="M9.2 17.5h5.6M10 20.5h4"/><path d="M12 3.5a5.8 5.8 0 0 0-3.4 10.5c.6.4.9 1.1.9 1.8v.7h5v-.7c0-.7.3-1.4.9-1.8A5.8 5.8 0 0 0 12 3.5Z"/>',
  history: '<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3.5 4v4.5H8"/><path d="M12 8v4.2l2.8 1.8"/>',
  hand: '<path d="M8.5 12.5V6a1.5 1.5 0 0 1 3 0v5.5M11.5 11V4.8a1.5 1.5 0 0 1 3 0V11M14.5 11V6.5a1.5 1.5 0 0 1 3 0v6.8c0 4.3-2.7 7.2-6.3 7.2-2.3 0-3.7-.9-5-2.8l-2.6-4a1.5 1.5 0 0 1 2.4-1.8l2.5 2.6"/>',
  shield: '<path d="M12 3.2 4.8 6v5.6c0 4.3 3 7.8 7.2 9.2 4.2-1.4 7.2-4.9 7.2-9.2V6Z"/><path d="m8.8 12.2 2.3 2.3 4.2-4.4"/>',
  dot: '<circle cx="12" cy="12" r="3" fill="currentColor"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  scale: '<path d="M12 4v16M7.5 20.5h9M5 7.5h14"/><path d="m5 7.5-2.5 6a3 3 0 0 0 5 0Zm14 0-2.5 6a3 3 0 0 0 5 0Z"/>',
  receipt: '<path d="M6 3.5h12v17l-2.4-1.5-2.4 1.5-1.2-.8-1.2.8-2.4-1.5L6 20.5Z"/><path d="M9 8h6M9 11.5h6M9 15h3.5"/>',
  folder: '<path d="M3.5 7c0-1.1.9-2 2-2h4l2 2.5h7c1.1 0 2 .9 2 2V17c0 1.1-.9 2-2 2h-13c-1.1 0-2-.9-2-2Z"/>',
  wand: '<path d="m4 20 11-11"/><path d="m13.5 7.5 3 3"/><path d="M17 3.5v3M15.5 5h3M20 8.5v2M19 9.5h2M8.5 3.5v2M7.5 4.5h2"/>',
};

export const ICON_NAMES = Object.keys(P);

export function icon(name, opts = {}) {
  const { size = 20, cls = '', label = '', strokeWidth = 1.8 } = opts;
  const body = P[name] || P.dot;
  const a11y = label ? `role="img" aria-label="${esc(label)}"` : 'aria-hidden="true" focusable="false"';
  return raw(
    `<svg class="icon${cls ? ' ' + cls : ''}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" ${a11y}>${body}</svg>`,
  );
}

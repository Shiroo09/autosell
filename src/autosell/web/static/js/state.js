// Paylaşılan küçük önbellek: sunucu durumu (/api/status).
import { api } from './api.js';

let status = null;
let statusAt = 0;
let inflight = null;
const listeners = new Set();

/** Sunucu durumunu döndürür (10 sn önbellekli). */
export async function getStatus({ force = false } = {}) {
  if (!force && status && Date.now() - statusAt < 10000) return status;
  if (inflight) return inflight;
  inflight = api('/api/status')
    .then((s) => {
      setStatus(s);
      return s;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export function setStatus(s) {
  status = s;
  statusAt = Date.now();
  listeners.forEach((fn) => {
    try {
      fn(s);
    } catch (e) {
      console.error(e);
    }
  });
}

export const cachedStatus = () => status;

export function onStatus(fn) {
  listeners.add(fn);
  if (status) fn(status);
  return () => listeners.delete(fn);
}

export function invalidateStatus() {
  statusAt = 0;
}

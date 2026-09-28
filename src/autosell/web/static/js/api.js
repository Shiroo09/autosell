// Sunucu API'si için merkezi istemci.
// Değişiklik yapan her istek (POST/PUT/DELETE) CSRF koruması için "X-AutoSell: 1" başlığı taşır.

const CSRF = { name: 'X-AutoSell', value: '1' };
const listeners = { auth: new Set(), blocked: new Set(), online: new Set() };

export class ApiError extends Error {
  constructor(status, message, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
  get isNetwork() {
    return this.status === 0;
  }
}

/** Oturum gerektiğinde (401) çağrılır. */
export const onAuthRequired = (fn) => (listeners.auth.add(fn), () => listeners.auth.delete(fn));
/** Ağdan şifresiz erişim engellendiğinde (403) çağrılır. */
export const onBlocked = (fn) => (listeners.blocked.add(fn), () => listeners.blocked.delete(fn));
/** Sunucuya erişilebilirlik değişince çağrılır (true/false). */
export const onConnection = (fn) => (listeners.online.add(fn), () => listeners.online.delete(fn));

let lastOnline = true;
function setOnline(ok) {
  if (ok === lastOnline) return;
  lastOnline = ok;
  listeners.online.forEach((fn) => fn(ok));
}

function detailMessage(data, status) {
  const d = data && typeof data === 'object' ? data.detail : null;
  if (typeof d === 'string' && d.trim()) return d.trim();
  if (Array.isArray(d) && d.length) {
    const f = d[0] || {};
    const loc = (f.loc || []).filter((x) => x !== 'body' && x !== 'query').join('.');
    return `Geçersiz değer${loc ? ` (${loc})` : ''}${f.msg ? `: ${f.msg}` : ''}`;
  }
  if (status === 404) return 'Aranan kayıt bulunamadı.';
  if (status === 413) return 'Dosya çok büyük (en fazla 25 MB).';
  if (status === 401) return 'Oturum açmanız gerekiyor.';
  if (status === 403) return 'Bu işlem için izniniz yok.';
  if (status >= 500) return 'Sunucuda beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.';
  return `İstek başarısız oldu (${status}).`;
}

function handleFailure(path, status, data) {
  const err = new ApiError(status, detailMessage(data, status), data);
  if (status === 401 && path !== '/api/login') listeners.auth.forEach((fn) => fn(err));
  if (status === 403 && /ağdan|şifre belirleyin/i.test(err.message)) listeners.blocked.forEach((fn) => fn(err));
  return err;
}

const NETWORK_MSG = 'Sunucuya ulaşılamadı. AutoSell çalışıyor mu? Bağlantınızı kontrol edin.';

/**
 * JSON API çağrısı.
 * @param {string} path
 * @param {{method?: string, body?: any, form?: FormData, signal?: AbortSignal, headers?: object}} opts
 */
export async function api(path, opts = {}) {
  const { method = 'GET', body, form, signal, headers = {} } = opts;
  const init = {
    method,
    headers: { Accept: 'application/json', ...headers },
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
  };
  if (method !== 'GET' && method !== 'HEAD') init.headers[CSRF.name] = CSRF.value;
  if (form) init.body = form;
  else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch (e) {
    if (e && e.name === 'AbortError') throw e;
    setOnline(false);
    throw new ApiError(0, NETWORK_MSG);
  }
  setOnline(true);
  let data = null;
  const type = res.headers.get('content-type') || '';
  try {
    data = type.includes('json') ? await res.json() : await res.text();
  } catch {
    data = null;
  }
  if (!res.ok) throw handleFailure(path, res.status, data);
  return data;
}

api.get = (path, opts) => api(path, { ...opts, method: 'GET' });
api.post = (path, body, opts) => api(path, { ...opts, method: 'POST', body });
api.put = (path, body, opts) => api(path, { ...opts, method: 'PUT', body });
api.del = (path, opts) => api(path, { ...opts, method: 'DELETE' });

/**
 * Yükleme ilerlemesi gösterebilmek için XHR ile çok parçalı gönderim.
 * @param {string} path
 * @param {FormData} form
 * @param {{onProgress?: (fraction: number) => void, method?: string}} opts
 */
export function upload(path, form, { onProgress, method = 'POST' } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, path);
    xhr.withCredentials = true;
    xhr.setRequestHeader(CSRF.name, CSRF.value);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.responseType = 'text';
    if (onProgress && xhr.upload) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.min(1, e.loaded / Math.max(1, e.total)));
      };
    }
    xhr.onerror = () => {
      setOnline(false);
      reject(new ApiError(0, NETWORK_MSG));
    };
    xhr.onload = () => {
      setOnline(true);
      let data = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        data = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(handleFailure(path, xhr.status, data));
    };
    xhr.send(form);
  });
}

export const enc = encodeURIComponent;

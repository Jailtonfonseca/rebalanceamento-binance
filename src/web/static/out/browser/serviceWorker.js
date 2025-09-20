/**
 * Minimal service worker used to satisfy frontend lookups.
 *
 * The frontend periodically requests `/_static/out/browser/serviceWorker.js`. The
 * FastAPI application previously returned a 404, polluting the logs. By serving
 * this stub we avoid unnecessary errors while still allowing future
 * enhancements.
 */
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', () => {
  // No offline caching for now; this handler merely keeps the service worker valid.
});

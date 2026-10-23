// Registers the offline worker (sw.js): with no connection, pages show the site's own
// offline page instead of the browser's error. Identifying still needs the network.
//
// Usage, from a page that loads install-button.js:
//   import { registerOfflinePage } from './offline.js';
//   registerOfflinePage();
export function registerOfflinePage(nav = navigator) {
  if (!('serviceWorker' in nav)) return;
  nav.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch(() => {});
}

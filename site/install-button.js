// "Install app" button, shared by every page that links the web app manifest.
//
// Behaviour by platform (as of late 2026):
//   Chrome / Edge / Samsung Internet / Android   -> real install: the browser fires
//       `beforeinstallprompt`; we keep it and call prompt() on tap.
//   iPhone / iPad Safari                          -> no install API exists; the button
//       opens a short "Share -> Add to Home Screen" guide instead.
//   Already installed (running standalone)        -> hidden.
//   Anything else (e.g. Firefox desktop)          -> hidden.
// Needs a valid manifest (Chrome's install criteria), otherwise `beforeinstallprompt` never
// fires and only the iOS guide can appear. Styles live in install-button.css.
//
// Usage: <button id="install-app" class="install-app" type="button" hidden>Install app</button>
//        <script type="module">
//          import { mountInstallButton } from './install-button.js';
//          mountInstallButton(document.getElementById('install-app'), { appName: 'twelveswaras' });
//        </script>

export function isStandalone(win = window) {
  return win.matchMedia?.('(display-mode: standalone)').matches || win.navigator.standalone === true;
}

// iPadOS 13+ reports itself as Mac; tell it apart by touch support.
export function isIosSafari(nav = navigator) {
  const ua = nav.userAgent || '';
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && (nav.maxTouchPoints || 0) > 1);
  const otherEngineShell = /CriOS|FxiOS|EdgiOS|OPiOS/.test(ua); // these can't add to home screen the same way
  return ios && !otherEngineShell;
}

export function mountInstallButton(button, { appName = 'this app', win = window } = {}) {
  if (!button || isStandalone(win)) return () => {};
  let deferred = null;

  const onPrompt = (e) => {
    e.preventDefault(); // keep the browser's mini-infobar from showing; we offer the button instead
    deferred = e;
    button.hidden = false;
  };
  const onInstalled = () => { deferred = null; button.hidden = true; };
  win.addEventListener('beforeinstallprompt', onPrompt);
  win.addEventListener('appinstalled', onInstalled);

  if (isIosSafari(win.navigator)) button.hidden = false;

  button.addEventListener('click', async () => {
    if (deferred) {
      const ev = deferred;
      deferred = null;
      ev.prompt();
      const { outcome } = await ev.userChoice;
      if (outcome === 'accepted') button.hidden = true;
      return;
    }
    if (isIosSafari(win.navigator)) showIosGuide(appName, win.document);
  });

  return () => {
    win.removeEventListener('beforeinstallprompt', onPrompt);
    win.removeEventListener('appinstalled', onInstalled);
  };
}

// A minimal accessible dialog, styled by install-button.css.
export function showIosGuide(appName, doc = document) {
  const dlg = doc.createElement('dialog');
  dlg.className = 'install-guide';
  dlg.setAttribute('aria-labelledby', 'install-guide-title');
  dlg.innerHTML = `
    <h2 id="install-guide-title">Add ${escapeHtml(appName)} to your Home Screen</h2>
    <ol>
      <li>Tap the <strong>Share</strong> button <span aria-hidden="true">(the square with an arrow)</span> in Safari's toolbar.</li>
      <li>Scroll down and tap <strong>Add to Home Screen</strong>.</li>
      <li>Tap <strong>Add</strong>.</li>
    </ol>
    <form method="dialog"><button>OK</button></form>`;
  dlg.addEventListener('close', () => dlg.remove());
  doc.body.append(dlg);
  dlg.showModal();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

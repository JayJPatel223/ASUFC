const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const { createWriteStream, mkdirSync } = require('node:fs');
const path = require('node:path');
const { createInterface } = require('node:readline');
let window;
let runtime;
let staffOrigin;
let stopping = false;
let selectedBackup;

app.commandLine.appendSwitch('disable-background-networking');

function stopWithError(message) {
  if (stopping) return;
  dialog.showErrorBox('ASUFC Finance could not open', message);
  app.quit();
}

async function showStaffWindow() {
  const testData = !app.isPackaged && process.env.ASUFC_DESKTOP_TEST_DATA;
  if (testData) {
    const testDirectory = path.resolve(testData);
    mkdirSync(testDirectory, { recursive: true, mode: 0o700 });
    app.setPath('userData', testDirectory);
  }
  const state = path.join(app.getPath('userData'), 'staff-data');
  mkdirSync(state, { recursive: true, mode: 0o700 });
  const launchKey = randomBytes(32).toString('hex');
  const bundle = path.join(app.isPackaged ? process.resourcesPath : __dirname, 'runtime');
  const executable = process.platform === 'win32' ? 'asufc-backend.exe' : 'asufc-backend';
  window = new BrowserWindow({
    width: 1260,
    height: 850,
    minWidth: 380,
    minHeight: 520,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      partition: 'asufc-staff',
    },
  });
  const { webContents } = window;
  await webContents.session.setProxy({ mode: 'direct' });
  const canNavigate = url => staffOrigin && new URL(url).origin === staffOrigin;
  webContents.on('will-navigate', (event, url) => { if (!canNavigate(url)) event.preventDefault(); });
  webContents.on('will-redirect', (event, url) => { if (!canNavigate(url)) event.preventDefault(); });
  webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  webContents.session.setPermissionRequestHandler((_page, _permission, callback) => callback(false));
  webContents.session.webRequest.onBeforeRequest(
    { urls: ['http://*/*', 'https://*/*'] },
    (request, callback) => callback({ cancel: new URL(request.url).origin !== staffOrigin }),
  );
  webContents.session.on('will-download', (event, item, initiator) => {
    const url = new URL(item.getURL());
    if (initiator !== webContents || url.origin !== staffOrigin) {
      event.preventDefault();
      return;
    }
    item.setSaveDialogOptions({ title: 'Save ASUFC Finance file', defaultPath: path.join(app.getPath('downloads'), item.getFilename()) });
  });

  const child = spawn(path.join(bundle, 'asufc-backend', executable), [
    '--state-dir', state,
    '--postgres-bin', path.join(bundle, 'postgres', 'bin'),
    '--frontend', path.join(bundle, 'frontend'),
  ], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  runtime = child;
  child.stderr.pipe(createWriteStream(path.join(state, 'desktop.log'), { flags: 'w', mode: 0o600 }));
  child.stdin.on('error', () => {
    if (!stopping) stopWithError('The local ledger could not connect to the desktop app.');
  });
  child.on('error', () => stopWithError('The bundled staff runtime could not start. Reinstall the app or contact support.'));
  child.on('close', () => {
    runtime = undefined;
    if (!stopping) stopWithError('The local ledger stopped. Its log is in the ASUFC Finance application data folder.');
  });

  const fromLedger = event => {
    const frame = event.senderFrame;
    return staffOrigin && event.sender === webContents && frame && !frame.parent && frame.url.startsWith(staffOrigin + '/');
  };
  ipcMain.handle('asufc:choose-backup', async event => {
    if (!fromLedger(event)) return '';
    const selection = await dialog.showOpenDialog(window, {
      title: 'Choose an ASUFC Finance backup',
      properties: ['openFile'],
      filters: [{ name: 'ASUFC Finance backup', extensions: ['asufcbak'] }],
    });
    if (!fromLedger(event)) return '';
    selectedBackup = selection.filePaths[0];
    return selectedBackup ? path.basename(selectedBackup) : '';
  });
  ipcMain.handle('asufc:restore-backup', async (event, passphrase) => {
    if (!fromLedger(event) || !selectedBackup || typeof passphrase !== 'string' ||
        passphrase.length < 16 || passphrase.length > 1024) {
      return {ok: false, message: 'Choose a backup file and enter its passphrase.'};
    }
    try {
      const response = await webContents.session.fetch(staffOrigin + '/api/desktop/restore', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-ASUFC-Request': '1', 'X-ASUFC-Launcher': launchKey},
        body: JSON.stringify({path: selectedBackup, passphrase}),
        redirect: 'error',
      });
      if (response.ok) {
        selectedBackup = undefined;
        return {ok: true};
      }
      const failure = await response.json().catch(() => null);
      if (typeof failure?.detail === 'string') return {ok: false, message: failure.detail};
    } catch {
      return {ok: false, message: 'Could not reach the local ledger. Close and reopen the app.'};
    }
    return {ok: false, message: 'The backup could not be restored.'};
  });

  createInterface({ input: child.stdout }).on('line', async line => {
    if (stopping) return;
    try {
      const event = JSON.parse(line);
      if (event.status === 'ready' && Number.isInteger(event.port) && event.port > 0 && event.port < 65536) {
        staffOrigin = 'http://127.0.0.1:' + event.port;
        // This partition lives for one app launch. The renderer cannot read the credential.
        await webContents.session.cookies.set({
          url: staffOrigin, name: 'asufc_desktop_session', value: launchKey,
          path: '/api', httpOnly: true, sameSite: 'strict',
        });
        await window.loadURL(staffOrigin);
        window.show();
      } else if (event.status === 'error') {
        stopWithError(event.message);
      }
    } catch {
      stopWithError('The staff runtime could not load the application window.');
    }
  });
  child.stdin.write(launchKey + '\n');
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {
    if (!window?.isVisible()) return;
    if (window.isMinimized()) window.restore();
    window.focus();
  });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', event => {
    if (!runtime || stopping) return;
    event.preventDefault();
    stopping = true;
    runtime.once('close', () => app.quit());
    runtime.stdin.end();
  });
  app.whenReady().then(showStaffWindow).catch(() => stopWithError('The desktop window could not be started.'));
}

const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const { createWriteStream, mkdirSync } = require('node:fs');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { pathToFileURL } = require('node:url');

const setupPath = path.join(__dirname, 'setup.html');
const setupUrl = pathToFileURL(setupPath).href;
let window;
let runtime;
let staffOrigin;
let canSetPassword = false;
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
  const canNavigate = url => url === setupUrl || (staffOrigin && new URL(url).origin === staffOrigin);
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
    if (!stopping) stopWithError('The local ledger stopped during sign-in setup.');
  });
  child.on('error', () => stopWithError('The bundled staff runtime could not start. Reinstall the app or contact support.'));
  child.on('close', () => {
    runtime = undefined;
    if (!stopping) stopWithError('The local ledger stopped. Its log is in the ASUFC Finance application data folder.');
  });

  const fromSetup = event => canSetPassword && event.sender === webContents && event.senderFrame?.url === setupUrl;
  const submitSetup = (event, password, restorePath) => {
    if (!fromSetup(event)) return false;
    if (typeof password !== 'string' || password.length < 16 || password.length > 1024) return false;
    canSetPassword = false;
    runtime.stdin.write(JSON.stringify({ password, restore_path: restorePath }) + '\n');
    return true;
  };
  ipcMain.handle('asufc:initial-password', (event, password) => submitSetup(event, password));
  ipcMain.handle('asufc:choose-backup', async event => {
    if (!fromSetup(event)) return '';
    const selection = await dialog.showOpenDialog(window, {
      title: 'Choose an ASUFC Finance backup',
      properties: ['openFile'],
      filters: [{ name: 'ASUFC Finance backup', extensions: ['asufcbak'] }],
    });
    if (!fromSetup(event)) return '';
    selectedBackup = selection.filePaths[0];
    return selectedBackup ? path.basename(selectedBackup) : '';
  });
  ipcMain.handle('asufc:restore-backup', (event, password) => {
    return Boolean(selectedBackup && submitSetup(event, password, selectedBackup));
  });

  createInterface({ input: child.stdout }).on('line', async line => {
    if (stopping) return;
    try {
      const event = JSON.parse(line);
      if (event.status === 'setup_required') {
        canSetPassword = true;
        await window.loadFile(setupPath);
        window.show();
      } else if (event.status === 'setup_error') {
        canSetPassword = true;
        webContents.send('asufc:password-error', event.message);
      } else if (event.status === 'ready' && Number.isInteger(event.port) && event.port > 0 && event.port < 65536) {
        canSetPassword = false;
        selectedBackup = undefined;
        staffOrigin = 'http://127.0.0.1:' + event.port;
        await window.loadURL(staffOrigin);
        window.show();
      } else if (event.status === 'error') {
        stopWithError(event.message);
      }
    } catch {
      stopWithError('The staff runtime could not load the application window.');
    }
  });
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

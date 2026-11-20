const { contextBridge, ipcRenderer } = require('electron');

if (location.protocol === 'file:' && location.pathname.endsWith('/setup.html')) {
  contextBridge.exposeInMainWorld('asufcSetup', {
    setPassword: password => ipcRenderer.invoke('asufc:initial-password', password),
    chooseBackup: () => ipcRenderer.invoke('asufc:choose-backup'),
    restoreBackup: passphrase => ipcRenderer.invoke('asufc:restore-backup', passphrase),
    onPasswordError: callback => ipcRenderer.on('asufc:password-error', (_event, message) => callback(message)),
  });
} else if (location.protocol === 'http:' && location.hostname === '127.0.0.1') {
  contextBridge.exposeInMainWorld('asufcDesktop', true);
}

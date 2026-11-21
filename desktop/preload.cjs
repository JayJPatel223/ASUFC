const { contextBridge, ipcRenderer } = require('electron');

if (location.protocol === 'http:' && location.hostname === '127.0.0.1') {
  contextBridge.exposeInMainWorld('asufcDesktop', true);
  contextBridge.exposeInMainWorld('asufcRecovery', {
    chooseBackup: () => ipcRenderer.invoke('asufc:choose-backup'),
    restoreBackup: passphrase => ipcRenderer.invoke('asufc:restore-backup', passphrase),
  });
}

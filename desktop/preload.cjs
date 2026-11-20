const { contextBridge, ipcRenderer } = require('electron');

if (location.protocol === 'file:' && location.pathname.endsWith('/setup.html')) {
  contextBridge.exposeInMainWorld('asufcSetup', {
    setPassword: password => ipcRenderer.invoke('asufc:initial-password', password),
    onPasswordError: callback => ipcRenderer.on('asufc:password-error', (_event, message) => callback(message)),
  });
}

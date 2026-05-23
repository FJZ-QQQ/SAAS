const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  onUpdateStatus: (callback) => {
    // 每次注册新监听器时，先移除旧的，防止重复触发
    ipcRenderer.removeAllListeners('update-status')
    ipcRenderer.on('update-status', (_event, value) => callback(value))
  },
  onBackendStatus: (callback) => {
    ipcRenderer.removeAllListeners('backend-status')
    ipcRenderer.on('backend-status', (_event, value) => callback(value))
  }
})

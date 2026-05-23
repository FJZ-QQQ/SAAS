const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron')
const path = require('path')
const { spawn } = require('child_process')

// 开发模式检测
const isDev = !app.isPackaged

let mainWindow = null
let tray = null
let pythonProcess = null

// 启动后台 RPA 引擎
function startPythonServer() {
  let exePath
  let exeCwd
  
  if (isDev) {
    // 开发模式：直接用 Python
    const pythonExecutable = process.platform === 'win32' ? 'py' : 'python'
    const scriptPath = path.join(__dirname, '../../douyin-rpa/rpa_server.py')
    exeCwd = path.join(__dirname, '../../douyin-rpa')
    
    console.log(`[Electron] 开发模式启动: ${pythonExecutable} "${scriptPath}"`)
    pythonProcess = spawn(pythonExecutable, [scriptPath], {
      cwd: exeCwd,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
      shell: false
    })
  } else {
    // 生产模式：优先用 Python 运行脚本（便于更新），fallback 到编译的 exe
    const scriptPath = path.join(process.resourcesPath, 'rpa_engine', '_internal', 'rpa_server.py')
    const exeCandidate = path.join(process.resourcesPath, 'rpa_engine', 'rpa_engine.exe')
    exeCwd = path.join(process.resourcesPath, 'rpa_engine', '_internal')
    
    const fs = require('fs')
    const hasPython = (() => { try { require('child_process').execSync('py --version', { stdio: 'ignore' }); return true } catch { return false } })()
    
    if (hasPython && fs.existsSync(scriptPath)) {
      console.log(`[Electron] 生产模式(Python): py "${scriptPath}"`)
      pythonProcess = spawn('py', [scriptPath], {
        cwd: exeCwd,
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
        shell: false
      })
    } else {
      console.log(`[Electron] 生产模式(EXE): "${exeCandidate}"`)
      pythonProcess = spawn(exeCandidate, [], {
        cwd: path.join(process.resourcesPath, 'rpa_engine'),
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
        shell: false
      })
    }
  }

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[RPA Engine] ${data.toString().trim()}`)
    // 未来可以通过 webContents.send 发送给前台
  })

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[RPA Error] ${data.toString().trim()}`)
  })

  pythonProcess.on('close', (code) => {
    console.log(`[Electron] RPA 引擎已退出，退出码: ${code}`)
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: '光宸智能客服 - 抖音智能客服助手',
    icon: path.join(__dirname, '../build/icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    // 窗口外观
    backgroundColor: '#f5f0e8',
    show: false,
    titleBarStyle: 'default',
  })

  // 加载页面
  if (isDev) {
    // 开发模式：加载 Vite 开发服务器
    mainWindow.loadURL('http://localhost:5173')
    // mainWindow.webContents.openDevTools() // 需要时取消注释
  } else {
    // 生产模式：加载打包后的文件
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  // 窗口准备好后再显示（避免白屏闪烁）
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // 点击关闭按钮时直接退出整个应用，不再最小化到托盘
  mainWindow.on('close', (event) => {
    app.isQuitting = true
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

function createTray() {
  // 创建一个简单的托盘图标（16x16 橙色圆形）
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示主窗口',
      click: () => {
        if (mainWindow) {
          mainWindow.show()
          mainWindow.focus()
        }
      }
    },
    { type: 'separator' },
    {
      label: '退出 光宸智能客服',
      click: () => {
        app.isQuitting = true
        app.quit()
      }
    }
  ])

  tray.setToolTip('光宸智能客服 - 抖音智能客服助手')
  tray.setContextMenu(contextMenu)

  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// 单实例锁定（防止重复打开）
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// ★ 启动时先清理上次的残留锁文件
function cleanupLockFiles() {
  try {
    const fs = require('fs')
    let sessionsDir
    if (isDev) {
      sessionsDir = path.join(__dirname, '../../douyin-rpa/sessions')
    } else {
      sessionsDir = path.join(process.resourcesPath, 'douyin-rpa/sessions')
    }
    if (!fs.existsSync(sessionsDir)) return
    
    const lockFileNames = ['SingletonLock', 'SingletonCookie', 'SingletonSocket']
    const walkDir = (dir) => {
      try {
        const entries = fs.readdirSync(dir, { withFileTypes: true })
        for (const entry of entries) {
          const fullPath = path.join(dir, entry.name)
          if (entry.isDirectory()) {
            walkDir(fullPath)
          } else if (lockFileNames.includes(entry.name)) {
            try {
              fs.unlinkSync(fullPath)
              console.log(`[Electron] 启动清理: 删除锁文件 ${fullPath}`)
            } catch (e) { /* 文件可能被占用 */ }
          }
        }
      } catch (e) { /* ignore */ }
    }
    walkDir(sessionsDir)
  } catch (e) {
    console.log('[Electron] 启动清理跳过:', e.message)
  }
}

// ★ 彻底清理退出：先优雅关闭（保存 cookies），再强制清理残留
function cleanupOnExit() {
  console.log('[Electron] 正在清理所有后台进程...')
  const { execSync } = require('child_process')
  
  // 1. ★ 关键：同步调用 /shutdown 并等待完成（让 Playwright 正常关闭浏览器，保存 cookies）
  try {
    console.log('[Electron] 等待 Playwright 优雅关闭浏览器...')
    execSync(
      'powershell -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:8100/shutdown -Method POST -TimeoutSec 5 -ErrorAction SilentlyContinue | Out-Null } catch {}"',
      { stdio: 'ignore', timeout: 8000 }
    )
    // 等待浏览器关闭完成
    console.log('[Electron] ✅ 浏览器已优雅关闭（cookies 已保存）')
  } catch (e) {
    console.log('[Electron] 优雅关闭超时，将强制清理')
  }
  
  // 2. 杀掉 Python 进程树
  if (pythonProcess && pythonProcess.pid) {
    try {
      execSync(`taskkill /F /T /PID ${pythonProcess.pid} 2>nul`, { stdio: 'ignore', timeout: 5000 })
      console.log(`[Electron] 已杀掉 Python 进程树 PID=${pythonProcess.pid}`)
    } catch (e) {
      try { pythonProcess.kill('SIGKILL') } catch (e2) { /* ignore */ }
    }
    pythonProcess = null
  }
  
  // 3. 清理残留 Chrome 进程（仅清理我们的 sessions 目录下的）
  try {
    let sessionsDir
    if (isDev) {
      sessionsDir = path.join(__dirname, '../../douyin-rpa/sessions')
    } else {
      sessionsDir = path.join(process.resourcesPath, 'douyin-rpa/sessions')
    }
    try {
      const result = execSync(
        `wmic process where "Name='chrome.exe' and CommandLine like '%${sessionsDir.replace(/\\/g, '\\\\')}%'" get ProcessId /format:list 2>nul`,
        { encoding: 'utf-8', timeout: 5000 }
      )
      const pids = result.match(/ProcessId=(\d+)/g)
      if (pids && pids.length > 0) {
        pids.forEach(p => {
          const pid = p.split('=')[1]
          try {
            execSync(`taskkill /F /PID ${pid} 2>nul`, { stdio: 'ignore', timeout: 3000 })
          } catch (e) { /* ignore */ }
        })
        console.log(`[Electron] 已清理 ${pids.length} 个残留 Chrome 进程`)
      }
    } catch (e) { /* 没有残留 chrome 也正常 */ }
  } catch (e) { /* ignore */ }
  
  // 4. 兜底：杀掉残留 python.exe
  try {
    execSync('taskkill /F /IM python.exe 2>nul', { stdio: 'ignore', timeout: 3000 })
  } catch (e) { /* ignore */ }
  
  // 5. 清理锁文件
  cleanupLockFiles()
  
  console.log('[Electron] ✅ 所有后台进程已清理完毕')
}

// ★ OTA 热更新：启动时从云端拉取最新的 Python 后端文件
const CLOUD_API = 'http://124.223.99.238:8100'

async function checkForUpdates() {
  if (isDev) return  // 开发模式不自动更新
  
  const sendStatus = (msg, type='info', progress=null) => {
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('update-status', { msg, type, progress })
    }
  }
  
  let hasUpdated = false
  
  const fs = require('fs')
  const https = require('http')
  const crypto = require('crypto')
  
  const localDir = path.join(process.resourcesPath, 'rpa_engine', '_internal')
  if (!fs.existsSync(localDir)) return
  const appDir = path.join(process.resourcesPath, 'app')
  const distDir = path.join(appDir, 'dist')
  const distHashFile = path.join(distDir, '.dist_hash')
  const updateStateFile = path.join(appDir, '.last_update_signature.json')

  const fileHash = (filepath) => {
    try {
      return crypto.createHash('md5').update(fs.readFileSync(filepath)).digest('hex')
    } catch {
      return ''
    }
  }

  const readUpdateState = () => {
    try {
      if (!fs.existsSync(updateStateFile)) return null
      return JSON.parse(fs.readFileSync(updateStateFile, 'utf-8'))
    } catch {
      return null
    }
  }

  const writeUpdateState = (state) => {
    try {
      fs.writeFileSync(updateStateFile, JSON.stringify(state, null, 2), 'utf-8')
    } catch (e) {
      console.log(`[Update] 记录更新状态失败: ${e.message}`)
    }
  }
  
  console.log('[Update] 检查云端更新...')
  // sendStatus('正在检查更新...', 'info') // 暂时不发，免得每次打开都闪一下
  
  try {
    // 1. 获取云端版本信息
    const versionData = await new Promise((resolve, reject) => {
      const req = https.get(`${CLOUD_API}/api/version`, { timeout: 5000 }, (res) => {
        let data = ''
        res.on('data', chunk => data += chunk)
        res.on('end', () => {
          try { resolve(JSON.parse(data)) } catch (e) { reject(e) }
        })
      })
      req.on('error', reject)
      req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
    })
    
    console.log(`[Update] 云端版本: ${versionData.version} (build ${versionData.build})`)

    const remoteSignature = crypto.createHash('sha256').update(JSON.stringify({
      version: versionData.version,
      build: versionData.build,
      files: Object.fromEntries(
        Object.entries(versionData.files || {})
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([fname, info]) => [fname, info.hash])
      ),
      dist_zip: versionData.dist_zip?.hash || '',
    })).digest('hex')
    
    // 2. 比对本地文件 MD5，找出需要更新的文件
    const filesToUpdate = []
    for (const [fname, info] of Object.entries(versionData.files || {})) {
      const localPath = path.join(localDir, fname)
      if (!fs.existsSync(localPath)) {
        filesToUpdate.push(fname)
        continue
      }
      const localHash = fileHash(localPath)
      if (localHash !== info.hash) {
        filesToUpdate.push(fname)
      }
    }

    const localDistHash = fs.existsSync(distHashFile) ? fs.readFileSync(distHashFile, 'utf-8').trim() : ''
    const needsDistUpdate = Boolean(versionData.dist_zip && localDistHash !== versionData.dist_zip.hash)
    
    if (filesToUpdate.length === 0 && !needsDistUpdate) {
      console.log('[Update] ✅ 已是最新版本，无需更新')
      return
    }

    const updateState = readUpdateState()
    if (updateState?.signature === remoteSignature && updateState?.updateFailed) {
      console.log('[Update] ⚠ 同一版本上次更新校验失败，暂停自动更新避免反复闪退')
      sendStatus('更新校验未通过，已暂停自动重启，可继续使用', 'error')
      return
    }
    if (
      updateState?.signature === remoteSignature &&
      updateState?.restartRequested &&
      !updateState?.remainingFiles?.length &&
      !updateState?.remainingDist
    ) {
      console.log('[Update] ⚠ 同一版本已触发过重启，仍检测到差异，跳过重复重启避免循环')
      sendStatus('更新已应用，正在等待软件稳定启动...', 'info')
      return
    }
    
    if (filesToUpdate.length > 0) {
      console.log(`[Update] 发现 ${filesToUpdate.length} 个文件需要更新: ${filesToUpdate.join(', ')}`)
      sendStatus(`发现新版本，正在更新后台组件... (共 ${filesToUpdate.length} 个文件)`, 'info')
    }
    
    // 3. 下载并替换文件
    for (const fname of filesToUpdate) {
      try {
        const content = await new Promise((resolve, reject) => {
          const req = https.get(`${CLOUD_API}/api/update/file/${fname}`, { timeout: 10000 }, (res) => {
            const chunks = []
            res.on('data', chunk => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)))
            res.on('end', () => resolve(Buffer.concat(chunks)))
          })
          req.on('error', reject)
          req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
        })
        
        const localPath = path.join(localDir, fname)
        // 备份旧文件
        if (fs.existsSync(localPath)) {
          fs.copyFileSync(localPath, localPath + '.bak')
        }
        fs.writeFileSync(localPath, content)
        const localHashAfterWrite = fileHash(localPath)
        if (localHashAfterWrite === info.hash) {
          console.log(`[Update] ✅ ${fname} 已更新`)
          hasUpdated = true
        } else {
          console.log(`[Update] ✗ ${fname} 更新后校验失败: local=${localHashAfterWrite}, remote=${info.hash}`)
        }
      } catch (e) {
        console.log(`[Update] ✗ ${fname} 更新失败: ${e.message}`)
      }
    }
    
    // ★ 检查前端 dist.zip 更新
    if (needsDistUpdate) {
        console.log('[Update] 前端界面有更新，正在下载...')
        sendStatus('正在下载最新界面，请稍候...', 'info')
        try {
          const zipData = await new Promise((resolve, reject) => {
            const req = https.get(`${CLOUD_API}/api/update/dist`, { timeout: 30000 }, (res) => {
              const chunks = []
              res.on('data', chunk => chunks.push(chunk))
              res.on('end', () => resolve(Buffer.concat(chunks)))
            })
            req.on('error', reject)
            req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
          })
          
          // 解压 zip 到 dist 目录
          const AdmZip = (() => {
            try { return require('adm-zip') } catch { return null }
          })()
          
          if (AdmZip) {
            const zip = new AdmZip(zipData)
            zip.extractAllTo(distDir, true)
          } else {
            // 没有 adm-zip，用简易方法：保存 zip 然后用 PowerShell 解压
            const tmpZip = path.join(process.resourcesPath, 'app', '_dist_update.zip')
            fs.writeFileSync(tmpZip, zipData)
            require('child_process').execSync(
              `powershell -Command "Expand-Archive -Path '${tmpZip}' -DestinationPath '${distDir}' -Force"`,
              { timeout: 15000 }
            )
            try { fs.unlinkSync(tmpZip) } catch {}
          }
          
          // 记录哈希
          fs.writeFileSync(distHashFile, versionData.dist_zip.hash, 'utf-8')
          console.log('[Update] ✅ 前端界面已更新')
          hasUpdated = true
        } catch (e) {
          console.log(`[Update] ✗ 前端更新失败: ${e.message}`)
        }
    }

    const remainingFiles = []
    for (const [fname, info] of Object.entries(versionData.files || {})) {
      const localPath = path.join(localDir, fname)
      if (fileHash(localPath) !== info.hash) {
        remainingFiles.push(fname)
      }
    }
    const remainingDist = Boolean(
      versionData.dist_zip &&
      (!fs.existsSync(distHashFile) || fs.readFileSync(distHashFile, 'utf-8').trim() !== versionData.dist_zip.hash)
    )
    
    console.log('[Update] ★ 更新完成！')
    
    if (hasUpdated) {
      if (remainingFiles.length > 0 || remainingDist) {
        writeUpdateState({
          signature: remoteSignature,
          version: versionData.version,
          build: versionData.build,
          restartRequested: false,
          updateFailed: true,
          updatedAt: new Date().toISOString(),
          remainingFiles,
          remainingDist,
        })
        console.log(`[Update] ⚠ 更新后校验未完全通过，跳过自动重启: files=${remainingFiles.join(',')} dist=${remainingDist}`)
        sendStatus('更新校验未通过，已暂停自动重启，可继续使用', 'error')
        return
      }
      writeUpdateState({
        signature: remoteSignature,
        version: versionData.version,
        build: versionData.build,
        restartRequested: true,
        updateFailed: false,
        updatedAt: new Date().toISOString(),
        remainingFiles,
        remainingDist,
      })
      sendStatus('更新完成，正在重启软件以应用新版本...', 'success')
      setTimeout(() => {
        app.relaunch()
        app.quit()
      }, 3000)
    }
  } catch (e) {
    console.log(`[Update] 检查更新失败（不影响使用）: ${e.message}`)
    // sendStatus('更新检查失败', 'error')
  }
}

app.whenReady().then(async () => {
  // ★ 优化启动速度：先显示窗口，再后台处理

  // 1. 先清理残留（极快，<10ms）
  cleanupLockFiles()
  
  // 2. 立即显示窗口（用户先看到界面）
  createWindow()
  createTray()
  
  // 3. 立即启动后端（不等 OTA）
  startPythonServer()
  
  // 4. OTA 更新放后台（不阻塞界面和后端启动）
  checkForUpdates().catch(e => {
    console.log(`[Update] 后台更新检查失败（不影响使用）: ${e.message}`)
  })
})

// 退出清理 —— 用多个钩子确保一定执行
app.on('before-quit', () => {
  cleanupOnExit()
})

app.on('will-quit', () => {
  // 二次保险：如果 before-quit 没来得及清理
  if (pythonProcess) {
    cleanupOnExit()
  }
})

// 所有窗口关闭时强制退出（不要留后台）
app.on('window-all-closed', () => {
  app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

import { useState, useEffect } from 'react'
import { HashRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Accounts from './pages/Accounts'
import Messages from './pages/Messages'
import Leads from './pages/Leads'
import Scripts from './pages/Scripts'
import MyAccount from './pages/MyAccount'
import Login from './pages/Login'
import AdminLogin from './pages/AdminLogin'
import AdminPanel from './pages/AdminPanel'
import appIcon from './assets/app-icon.png'
import './index.css'

// ★ 会话管理 — 基于服务端 token（30天有效）
const API_BASE = 'http://localhost:8100'

function getStoredSession() {
  try {
    const raw = localStorage.getItem('gc_session')
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function saveSession(authMode, merchantData, token) {
  const session = {
    authMode,
    merchantData,
    token: token || '',
    login_at: new Date().toISOString(),
  }
  localStorage.setItem('gc_session', JSON.stringify(session))
}

function clearSession() {
  localStorage.removeItem('gc_session')
}

export default function App() {
  // 三种状态：null=未登录, 'merchant'=商家端, 'admin'=管理员端
  const [authMode, setAuthMode] = useState(null)
  const [merchantData, setMerchantData] = useState(null)
  const [adminData, setAdminData] = useState(null)
  const [showAdminLogin, setShowAdminLogin] = useState(false)
  const [checking, setChecking] = useState(true) // ★ 启动时检查 token
  const [updateStatus, setUpdateStatus] = useState(null) // ★ OTA 更新状态

  useEffect(() => {
    // 监听 Electron 传来的更新状态
    if (window.electronAPI && window.electronAPI.onUpdateStatus) {
      window.electronAPI.onUpdateStatus((data) => {
        setUpdateStatus(data)
      })
    }
  }, [])

  // ★ 启动时向服务端验证 token，决定是否自动登录
  useEffect(() => {
    const checkToken = async (retries = 5) => {
      const session = getStoredSession()
      if (!session || !session.token) {
        setChecking(false)
        return
      }

      // 管理员会话不需要 token 验证（本地判断）
      if (session.authMode === 'admin') {
        setAdminData(session.merchantData)
        setAuthMode('admin')
        setChecking(false)
        return
      }

      try {
        const res = await fetch(`${API_BASE}/api/auth/check`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: session.token })
        })
        
        if (res.ok) {
          const data = await res.json()
          // ★ token 有效 → 自动登录
          setMerchantData({
            merchant_id: data.merchant_id,
            phone: data.phone,
            balance: data.balance,
            token: session.token,
          })
          setAuthMode('merchant')
        } else {
          // ★ token 无效/过期 → 清除，重新登录
          clearSession()
        }
      } catch {
        if (retries > 0) {
          setTimeout(() => checkToken(retries - 1), 1000)
          return
        }
        clearSession()
      }
      setChecking(false)
    }

    checkToken()
  }, [])

  // 商家登录成功
  const handleMerchantLogin = (data) => {
    setMerchantData(data)
    setAuthMode('merchant')
    saveSession('merchant', data, data.token)
  }

  // 管理员登录成功
  const handleAdminLogin = (data) => {
    setAdminData(data)
    setAuthMode('admin')
    setShowAdminLogin(false)
    saveSession('admin', data, data.admin_token)
  }

  // ★ 退出登录：通知服务端删除 token + 清除本地
  const handleLogout = async () => {
    const session = getStoredSession()
    if (session?.token) {
      try {
        if (session.authMode === 'admin') {
          await fetch(`${API_BASE}/api/admin/logout`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${session.token}` }
          })
        } else {
          await fetch(`${API_BASE}/api/auth/logout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: session.token })
          })
        }
      } catch {
        // 忽略退出时的后端连接失败，本地会话仍会清除
      }
    }
    setAuthMode(null)
    setMerchantData(null)
    setAdminData(null)
    setShowAdminLogin(false)
    clearSession()
  }

  const renderUpdateToast = () => {
    if (!updateStatus) return null

    const colors = {
      info: { bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' },
      success: { bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
      error: { bg: '#fef2f2', text: '#b91c1c', border: '#fecaca' },
    }
    const theme = colors[updateStatus.type] || colors.info

    return (
      <div style={{
        position: 'fixed',
        top: 16,
        right: 16,
        zIndex: 9999,
        maxWidth: 360,
        padding: '12px 16px',
        borderRadius: 12,
        background: theme.bg,
        color: theme.text,
        border: `1px solid ${theme.border}`,
        boxShadow: '0 10px 30px rgba(15, 23, 42, 0.12)',
        fontSize: 13,
        fontWeight: 600,
      }}>
        {updateStatus.msg || '正在更新...'}
        {updateStatus.progress != null && (
          <div style={{
            height: 4,
            marginTop: 8,
            borderRadius: 999,
            overflow: 'hidden',
            background: 'rgba(15, 23, 42, 0.12)',
          }}>
            <div style={{
              width: `${Math.max(0, Math.min(100, updateStatus.progress))}%`,
              height: '100%',
              background: theme.text,
            }} />
          </div>
        )}
      </div>
    )
  }

  // ★ 启动时显示加载中
  if (checking) {
    return (
      <>
        {renderUpdateToast()}
        <div style={{
          minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%)',
          fontFamily: 'Inter, system-ui, sans-serif'
        }}>
          <div style={{ textAlign: 'center' }}>
            <img
              src={appIcon}
              alt="光宸智能客服"
              style={{
                width: 52, height: 52, borderRadius: 16,
                display: 'block', margin: '0 auto 16px',
                animation: 'pulse 1.5s infinite',
              }}
            />
            <p style={{ color: '#64748b', fontSize: 14 }}>正在检查登录状态...</p>
          </div>
        </div>
      </>
    )
  }

  // 未登录 → 显示登录页
  if (!authMode) {
    if (showAdminLogin) {
      return (
        <>
          {renderUpdateToast()}
          <AdminLogin
            onLogin={handleAdminLogin}
            onBack={() => setShowAdminLogin(false)}
          />
        </>
      )
    }
    return (
      <>
        {renderUpdateToast()}
        <Login
          onLogin={handleMerchantLogin}
          onAdminLogin={() => setShowAdminLogin(true)}
        />
      </>
    )
  }

  // 管理员模式 → 管理员面板
  if (authMode === 'admin') {
    return (
      <>
        {renderUpdateToast()}
        <AdminPanel
          adminData={adminData}
          onLogout={handleLogout}
        />
      </>
    )
  }

  // 商家模式 → 主应用
  return (
    <>
      {renderUpdateToast()}
      <HashRouter>
        <div className="app-layout">
          <Sidebar
            merchantData={merchantData}
            onLogout={handleLogout}
          />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Dashboard merchantData={merchantData} />} />
              <Route path="/accounts" element={<Accounts merchantData={merchantData} />} />
              <Route path="/messages" element={<Messages merchantData={merchantData} />} />
              <Route path="/leads" element={<Leads merchantData={merchantData} />} />
              <Route path="/scripts" element={<Scripts merchantData={merchantData} />} />
              <Route path="/my-account" element={<MyAccount merchantData={merchantData} />} />
            </Routes>
          </main>
        </div>
      </HashRouter>
    </>
  )
}

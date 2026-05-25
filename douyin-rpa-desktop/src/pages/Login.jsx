import { useState } from 'react'
import { Phone, Lock, ArrowRight, KeyRound } from 'lucide-react'
import appIcon from '../assets/app-icon.png'

export default function Login({ onLogin, onAdminLogin }) {
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!phone) { setError('请输入手机号'); return }
    if (!/^1[3-9]\d{9}$/.test(phone)) { setError('请输入正确的11位手机号'); return }
    if (!password) { setError('请输入密码'); return }
    setLoading(true)

    try {
      const res = await fetch('http://localhost:8100/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, password })
      })
      const data = await res.json()
      if (res.ok && data.status === 'ok') {
        onLogin(data)
      } else {
        setError(data.error || '登录失败')
      }
    } catch (e) {
      setError('无法连接后端服务。请检查：① 杀毒软件是否拦截了程序 ② 尝试右键以管理员身份运行')
    }
    setLoading(false)
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%)',
      fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      <div style={{
        background: 'rgba(255, 255, 255, 0.8)',
        backdropFilter: 'blur(20px)',
        borderRadius: 24,
        padding: '48px',
        width: '100%',
        maxWidth: 420,
        boxShadow: '0 20px 40px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.05)',
        border: '1px solid rgba(255,255,255,0.6)'
      }}>
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <img
            src={appIcon}
            alt="光宸智能客服"
            style={{
              width: 72, height: 72, borderRadius: 20,
              display: 'block', margin: '0 auto 20px',
              boxShadow: '0 10px 20px rgba(87, 100, 242, 0.24)'
            }}
          />
          <h1 style={{ fontSize: 28, fontWeight: 800, color: '#1e293b', marginBottom: 8 }}>光宸智能客服</h1>
          <p style={{ color: '#64748b', fontSize: 14 }}>智能抖音获客系统 · 手机号和密码登录</p>
        </div>

        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{
              background: '#fef2f2', color: '#ef4444', padding: '12px 16px',
              borderRadius: 12, fontSize: 13, marginBottom: 20, textAlign: 'center',
              fontWeight: 500, border: '1px solid #fee2e2'
            }}>
              {error}
            </div>
          )}

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 8 }}>手机号</label>
            <div style={{ position: 'relative' }}>
              <Phone size={18} color="#94a3b8" style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 11))}
                placeholder="输入手机号"
                maxLength={11}
                style={{
                  width: '100%', padding: '14px 16px 14px 44px',
                  background: '#f8fafc', border: '1px solid #e2e8f0',
                  borderRadius: 12, fontSize: 15, color: '#1e293b',
                  outline: 'none', transition: 'all 0.2s',
                  boxSizing: 'border-box'
                }}
                onFocus={(e) => { e.target.style.borderColor = '#f97316'; e.target.style.boxShadow = '0 0 0 3px rgba(249, 115, 22, 0.1)' }}
                onBlur={(e) => { e.target.style.borderColor = '#e2e8f0'; e.target.style.boxShadow = 'none' }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 32 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#475569', marginBottom: 8 }}>密码</label>
            <div style={{ position: 'relative' }}>
              <Lock size={18} color="#94a3b8" style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="输入密码"
                autoComplete="current-password"
                style={{
                  width: '100%', padding: '14px 16px 14px 44px',
                  background: '#f8fafc', border: '1px solid #e2e8f0',
                  borderRadius: 12, fontSize: 15, color: '#1e293b',
                  outline: 'none', transition: 'all 0.2s',
                  boxSizing: 'border-box'
                }}
                onFocus={(e) => { e.target.style.borderColor = '#f97316'; e.target.style.boxShadow = '0 0 0 3px rgba(249, 115, 22, 0.1)' }}
                onBlur={(e) => { e.target.style.borderColor = '#e2e8f0'; e.target.style.boxShadow = 'none' }}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%', padding: '14px',
              background: loading ? '#fdba74' : '#f97316',
              color: 'white', border: 'none', borderRadius: 12,
              fontSize: 16, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 8, transition: 'all 0.2s',
              boxShadow: '0 4px 12px rgba(249, 115, 22, 0.2)'
            }}
            onMouseOver={(e) => !loading && (e.currentTarget.style.transform = 'translateY(-1px)')}
            onMouseOut={(e) => !loading && (e.currentTarget.style.transform = 'translateY(0)')}
          >
            {loading ? '正在登录...' : '登录'}
            {!loading && <ArrowRight size={18} />}
          </button>
        </form>

        {onAdminLogin && (
          <div style={{ textAlign: 'center', marginTop: 24, paddingTop: 20, borderTop: '1px solid #e2e8f0' }}>
            <button
              type="button"
              onClick={onAdminLogin}
              style={{
                background: 'none', border: 'none', color: '#94a3b8',
                fontSize: 13, cursor: 'pointer', display: 'inline-flex',
                alignItems: 'center', gap: 6, transition: 'color 0.2s',
              }}
              onMouseOver={(e) => e.currentTarget.style.color = '#475569'}
              onMouseOut={(e) => e.currentTarget.style.color = '#94a3b8'}
            >
              <KeyRound size={14} />
              管理员后台入口
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

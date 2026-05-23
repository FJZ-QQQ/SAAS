import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Users, Bot, Target, Wallet, Link2, Unlink, ChevronRight, ArrowUpRight, Loader, AlertTriangle, TrendingUp, MessageCircle, UserCheck, Zap, Clock } from 'lucide-react'

export default function Dashboard({ merchantData }) {
  const navigate = useNavigate()
  const [accountInfo, setAccountInfo] = useState(null)
  const [liveAccounts, setLiveAccounts] = useState({})
  const [stats, setStats] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const mid = merchantData?.merchant_id || 0
        const [accRes, statusRes, statsRes] = await Promise.all([
          fetch(`http://localhost:8100/api/account?merchant_id=${mid}`),
          fetch(`http://localhost:8100/status?owner_merchant_id=${mid}`),
          fetch(`http://localhost:8100/api/stats?merchant_id=${mid}`),
        ])
        const accData = await accRes.json()
        const statusData = await statusRes.json()
        const statsData = await statsRes.json()
        setAccountInfo(accData)
        setLiveAccounts(statusData)
        setStats(statsData)
      } catch (e) {
        console.error(e)
      }
      setLoading(false)
    }
    fetchData()
    const timer = setInterval(fetchData, 5000)
    return () => clearInterval(timer)
  }, [merchantData])

  const balance = accountInfo?.balance ?? merchantData?.balance ?? 0
  const totalLeads = accountInfo?.total_leads ?? 0
  const slotCount = Object.keys(liveAccounts).length
  const onlineCount = Object.values(liveAccounts).filter(s => s.status === 'running').length
  const hasBoundAccount = slotCount > 0

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">首页</h1>
      </header>

      <div className="page-body">
        {/* 余额不足警告 */}
        {balance <= 0 && (
          <div style={{
            background: 'linear-gradient(135deg, rgba(220,53,69,0.08) 0%, rgba(220,53,69,0.03) 100%)',
            border: '1px solid rgba(220,53,69,0.2)',
            borderRadius: 14, padding: '16px 22px', marginBottom: 20,
            display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <AlertTriangle size={22} color="var(--accent-red)" />
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--accent-red)' }}>
                余额不足 — AI已停止回复
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                请联系管理员充值后，AI客服才会继续自动回复私信
              </div>
            </div>
          </div>
        )}

        {/* ★ 今日实时数据看板 */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <TrendingUp size={16} />
            今日实时数据
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
              {stats.date || new Date().toISOString().slice(0,10)}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
            {/* 今日接待 */}
            <div className="stat-card blue" style={{ textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--accent-blue-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <MessageCircle size={18} color="var(--accent-blue)" />
                </div>
              </div>
              <div className="stat-value" style={{ fontSize: 24 }}>{stats.today_messages || 0}</div>
              <div className="stat-label">今日接待</div>
            </div>
            {/* 今日留资 */}
            <div className="stat-card green" style={{ textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--accent-green-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <UserCheck size={18} color="var(--accent-green)" />
                </div>
              </div>
              <div className="stat-value" style={{ fontSize: 24 }}>{stats.today_leads || 0}</div>
              <div className="stat-label">今日留资</div>
            </div>
            {/* 留资率 */}
            <div className="stat-card orange" style={{ textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--accent-orange-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Target size={18} color="var(--accent-orange)" />
                </div>
              </div>
              <div className="stat-value" style={{ fontSize: 24 }}>{stats.lead_rate || 0}%</div>
              <div className="stat-label">留资率</div>
            </div>
            {/* AI成功率 */}
            <div className="stat-card" style={{ textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(139,92,246,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Zap size={18} color="#8b5cf6" />
                </div>
              </div>
              <div className="stat-value" style={{ fontSize: 24, color: (stats.ai_success_rate || 100) >= 90 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                {stats.ai_success_rate || 100}%
              </div>
              <div className="stat-label">AI成功率</div>
            </div>
            {/* 平均响应 */}
            <div className="stat-card" style={{ textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(6,182,212,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Clock size={18} color="#06b6d4" />
                </div>
              </div>
              <div className="stat-value" style={{ fontSize: 24 }}>{stats.avg_response_time || 0}s</div>
              <div className="stat-label">平均响应</div>
            </div>
          </div>
        </div>

        {/* 余额 & 统计 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
          <div className="stat-card orange" style={{ textAlign: 'center' }}>
            <div className="stat-label">当前余额</div>
            <div className="stat-value" style={{
              color: balance > 0 ? 'var(--accent-orange)' : 'var(--accent-red)',
            }}>¥{balance.toFixed(2)}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              每收集1条客资扣费¥1.00
            </div>
          </div>
          <div className="stat-card green" style={{ textAlign: 'center' }}>
            <div className="stat-label">累计客资</div>
            <div className="stat-value">{totalLeads}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              手机号 + 微信号
            </div>
          </div>
          <div className="stat-card blue" style={{ textAlign: 'center' }}>
            <div className="stat-label">抖音账号</div>
            <div className="stat-value">{onlineCount}/{slotCount}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              {hasBoundAccount ? '在线 / 已绑定' : '尚未绑定'}
            </div>
          </div>
        </div>

        {/* 核心功能入口卡片 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* 抖音账号绑定 */}
          <div
            className="panel"
            style={{ cursor: 'pointer', transition: 'all 0.2s' }}
            onClick={() => navigate('/accounts')}
            onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-glow-blue)' }}
            onMouseOut={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none' }}
          >
            <div className="panel-body" style={{ padding: '28px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: hasBoundAccount ? 'var(--accent-green-glow)' : 'var(--accent-orange-glow)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {hasBoundAccount ? <Link2 size={24} color="var(--accent-green)" /> : <Unlink size={24} color="var(--accent-orange)" />}
                </div>
                <ChevronRight size={20} color="var(--text-muted)" />
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>
                抖音账号绑定
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {hasBoundAccount
                  ? `已绑定 ${slotCount} 个账号，${onlineCount} 个在线运行中`
                  : '点击绑定你的抖音账号，开始自动回复私信'}
              </div>
              <div style={{
                marginTop: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                background: hasBoundAccount ? 'var(--accent-green-glow)' : 'var(--accent-orange-glow)',
                color: hasBoundAccount ? 'var(--accent-green)' : 'var(--accent-orange)',
              }}>
                {hasBoundAccount ? '● 已绑定' : '○ 未绑定'}
              </div>
            </div>
          </div>

          {/* AI智能体配置 */}
          <div
            className="panel"
            style={{ cursor: 'pointer', transition: 'all 0.2s' }}
            onClick={() => navigate('/scripts')}
            onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-glow-orange)' }}
            onMouseOut={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none' }}
          >
            <div className="panel-body" style={{ padding: '28px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: 'var(--accent-purple-glow)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Bot size={24} color="var(--accent-purple)" />
                </div>
                <ChevronRight size={20} color="var(--text-muted)" />
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>
                AI 智能体配置
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                设置AI客服的昵称、人设描述和知识库内容
              </div>
              <div style={{
                marginTop: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                background: 'var(--accent-purple-glow)', color: 'var(--accent-purple)',
              }}>
                前往配置 →
              </div>
            </div>
          </div>

          {/* 我的客资 */}
          <div
            className="panel"
            style={{ cursor: 'pointer', transition: 'all 0.2s' }}
            onClick={() => navigate('/leads')}
            onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-glow-orange)' }}
            onMouseOut={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none' }}
          >
            <div className="panel-body" style={{ padding: '28px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: 'var(--accent-orange-glow)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Target size={24} color="var(--accent-orange)" />
                </div>
                <ChevronRight size={20} color="var(--text-muted)" />
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>
                我的客资
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                查看AI收集到的客户联系方式（手机号/微信号）
              </div>
              <div style={{
                marginTop: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                background: 'var(--accent-orange-glow)', color: 'var(--accent-orange)',
              }}>
                共 {totalLeads} 条客资
              </div>
            </div>
          </div>

          {/* 消息监控 */}
          <div
            className="panel"
            style={{ cursor: 'pointer', transition: 'all 0.2s' }}
            onClick={() => navigate('/messages')}
            onMouseOver={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-glow-blue)' }}
            onMouseOut={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none' }}
          >
            <div className="panel-body" style={{ padding: '28px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: 'var(--accent-blue-glow)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Users size={24} color="var(--accent-blue)" />
                </div>
                <ChevronRight size={20} color="var(--text-muted)" />
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>
                消息监控
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                查看AI与客户的所有对话记录
              </div>
              <div style={{
                marginTop: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                background: 'var(--accent-blue-glow)', color: 'var(--accent-blue)',
              }}>
                实时更新中
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

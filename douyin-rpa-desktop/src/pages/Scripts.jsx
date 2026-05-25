import { useState, useEffect, useRef } from 'react'
import { Save, RotateCcw, Plus, Trash2, Sparkles, Loader, Bot, BookOpen, UserCircle, Send, MessageSquare, Eraser, Store, ShieldAlert, X } from 'lucide-react'

const formatStoreName = (id) => `${id}号店铺`

export default function Scripts({ merchantData }) {
  const currentMid = merchantData?.merchant_id || 0
  const [nickname, setNickname] = useState('')
  const [persona, setPersona] = useState('')
  const [knowledgeBase, setKnowledgeBase] = useState('')
  const [keywords, setKeywords] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

  // ★ 店铺选择
  const [stores, setStores] = useState([])
  const [selectedStore, setSelectedStore] = useState('')

  // Chat state
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef(null)
  const chatInputRef = useRef(null)
  const chatSessionId = useRef(`test_${Date.now()}`)
  const configRequestRef = useRef(0)

  // ★ 敏感词管理
  const [sensitiveWords, setSensitiveWords] = useState([])
  const [newWord, setNewWord] = useState('')
  const [swSaving, setSwSaving] = useState(false)

  // 获取已绑定的店铺列表
  useEffect(() => {
    if (!currentMid) return
    fetch(`http://localhost:8100/status?owner_merchant_id=${currentMid}`)
      .then(r => r.json())
      .then(data => {
        // /status 返回 { "1": { status, nickname, ... }, "2": { ... } }
        const storeList = Object.entries(data)
          .map(([id, info]) => ({
            id: parseInt(id),
            name: formatStoreName(id),
            status: info.status
          }))
        setStores(storeList)
        setSelectedStore(prev => {
          if (prev && storeList.some(store => store.id === Number(prev))) return prev
          return storeList[0]?.id || ''
        })
      })
      .catch(() => {})
  }, [currentMid])

  // 加载敏感词
  useEffect(() => {
    fetch(`http://localhost:8100/api/sensitive-words?merchant_id=${currentMid}`)
      .then(r => r.json())
      .then(data => setSensitiveWords(data.words || []))
      .catch(() => {})
  }, [currentMid])

  // 加载选中店铺的配置
  const loadConfig = (storeId) => {
    const requestId = ++configRequestRef.current
    if (!storeId || !currentMid) {
      setNickname('')
      setPersona('')
      setKnowledgeBase('')
      setKeywords([])
      setLoading(false)
      return
    }
    setLoading(true)
    setSaveMsg('')
    fetch(`http://localhost:8100/api/scripts?merchant_id=${currentMid}&slot_id=${storeId}`)
      .then(r => r.json())
      .then(data => {
        if (requestId !== configRequestRef.current) return
        setNickname(data.nickname || '')
        setPersona(data.persona || '')
        setKnowledgeBase(data.knowledge_base || '')
        setKeywords(data.keywords || [])
        setLoading(false)
      })
      .catch(e => {
        if (requestId !== configRequestRef.current) return
        console.error(e)
        setLoading(false)
      })
  }

  useEffect(() => {
    loadConfig(selectedStore)
    setChatMessages([])
    chatSessionId.current = `test_${Date.now()}_store${selectedStore}`
  }, [selectedStore, currentMid])

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  const handleSave = async () => {
    if (!selectedStore) {
      setSaveMsg('请先选择店铺')
      return
    }
    setSaving(true)
    setSaveMsg('')
    try {
      const res = await fetch('http://localhost:8100/api/scripts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nickname,
          persona,
          knowledge_base: knowledgeBase,
          merchant_id: currentMid,
          slot_id: selectedStore,
        })
      })
      const data = await res.json()
      if (data.status === 'ok') {
        setSaveMsg('✅ 配置已保存')
      } else {
        setSaveMsg('❌ 保存失败: ' + (data.error || '未知错误'))
      }
    } catch (e) {
      setSaveMsg('❌ 网络错误: ' + e.message)
    }
    setSaving(false)
    setTimeout(() => setSaveMsg(''), 3000)
  }

  const handleReset = async () => {
    if (!selectedStore) {
      setSaveMsg('请先选择店铺')
      return
    }
    if (!confirm('确定要重置为已保存的配置吗？')) return
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:8100/api/scripts?merchant_id=${currentMid}&slot_id=${selectedStore}`)
      const data = await res.json()
      setNickname(data.nickname || '')
      setPersona(data.persona || '')
      setKnowledgeBase(data.knowledge_base || '')
      setKeywords(data.keywords || [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const handleSendMessage = async () => {
    const text = chatInput.trim()
    if (!text || chatLoading) return

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: text,
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    setChatMessages(prev => [...prev, userMsg])
    setChatInput('')
    setChatLoading(true)

    try {
      const res = await fetch('http://localhost:8100/api/test-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          user_id: chatSessionId.current,
          agent_config: { nickname: nickname || '小橙', persona, knowledge_base: knowledgeBase }
        })
      })
      const data = await res.json()
      const aiMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.reply || '抱歉，我没有理解您的问题',
        source: data.source || 'unknown',
        time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      }
      setChatMessages(prev => [...prev, aiMsg])
    } catch (e) {
      setChatMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        content: `网络错误: ${e.message}`,
        source: 'error',
        time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      }])
    }
    setChatLoading(false)
    setTimeout(() => chatInputRef.current?.focus(), 100)
  }

  const handleClearChat = () => {
    setChatMessages([])
    chatSessionId.current = `test_${Date.now()}`
  }

  const aiName = nickname || '小橙'

  return (
    <>
      <header className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <h1 className="page-title" style={{ margin: 0 }}>AI 智能体配置</h1>
          {stores.length > 0 && (
            <div style={{ display: 'flex', gap: 6, background: 'var(--bg-secondary)', borderRadius: 8, padding: '3px 4px' }}>
              {stores.map(s => (
                <button
                  key={s.id}
                  onClick={() => setSelectedStore(s.id)}
                  style={{
                    padding: '5px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                    fontSize: 13, fontWeight: selectedStore === s.id ? 600 : 400,
                    background: selectedStore === s.id ? 'var(--accent-orange)' : 'transparent',
                    color: selectedStore === s.id ? '#fff' : 'var(--text-secondary)',
                    transition: 'all 0.2s'
                  }}
                >{s.name}</button>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          {saveMsg && <span style={{ fontSize: 13 }}>{saveMsg}</span>}
          <button className="btn btn-ghost" onClick={handleReset}>
            <RotateCcw size={16} />
            重置
          </button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? <Loader size={16} className="spin" /> : <Save size={16} />}
            {saving ? '保存中...' : '保存配置'}
          </button>
        </div>
      </header>

      <div className="page-body">
        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-muted)' }}>
            <Loader size={24} className="spin" />
            <div style={{ marginTop: 12 }}>加载配置中...</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 420px', gap: '20px', height: 'calc(100vh - 140px)' }}>
            {/* 左侧：三段式配置 */}
            <div style={{ overflowY: 'auto', paddingRight: 4 }}>
              {/* AI 昵称 */}
              <div className="panel" style={{ marginBottom: 20 }}>
                <div className="panel-header">
                  <span className="panel-title">
                    <Bot size={18} style={{ marginRight: 8, verticalAlign: 'middle', color: 'var(--accent-orange)' }} />
                    AI 客服昵称
                  </span>
                </div>
                <div className="panel-body">
                  <div className="form-group">
                    <label className="form-label" style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 8, display: 'block' }}>
                      给你的AI客服起一个名字，客户会看到这个名字
                    </label>
                    <input
                      className="form-input"
                      value={nickname}
                      onChange={e => setNickname(e.target.value)}
                      placeholder="例如：小橙、小美、专属顾问"
                      maxLength={20}
                      style={{ fontSize: 16, fontWeight: 600 }}
                    />
                  </div>
                </div>
              </div>

              {/* AI 人设描述 */}
              <div className="panel" style={{ marginBottom: 20 }}>
                <div className="panel-header">
                  <span className="panel-title">
                    <UserCircle size={18} style={{ marginRight: 8, verticalAlign: 'middle', color: 'var(--accent-purple)' }} />
                    AI 人设描述
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>定义AI的性格和角色</span>
                </div>
                <div className="panel-body">
                  <div className="form-group">
                    <label className="form-label" style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 8, display: 'block' }}>
                      描述AI客服的人设特征，例如专业领域、性格特点、沟通风格等
                    </label>
                    <textarea
                      className="form-textarea"
                      value={persona}
                      onChange={e => setPersona(e.target.value)}
                      style={{ minHeight: 120 }}
                      placeholder="例如：专业、耐心，熟悉公司注册流程和费用，善于用简洁明了的语言解答客户疑问，态度热情友好"
                    />
                  </div>
                </div>
              </div>

              {/* 知识库内容 */}
              <div className="panel" style={{ marginBottom: 20 }}>
                <div className="panel-header">
                  <span className="panel-title">
                    <BookOpen size={18} style={{ marginRight: 8, verticalAlign: 'middle', color: 'var(--accent-green)' }} />
                    知识库内容
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>AI回复的核心参考资料</span>
                </div>
                <div className="panel-body">
                  <div className="form-group">
                    <label className="form-label" style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 8, display: 'block' }}>
                      输入你的产品/服务介绍、价格、优势、常见问答等内容，AI会基于这些信息回复客户
                    </label>
                    <textarea
                      className="form-textarea"
                      value={knowledgeBase}
                      onChange={e => setKnowledgeBase(e.target.value)}
                      style={{ minHeight: 180 }}
                      placeholder={`例如：\n公司注册800元起，包含营业执照和刻章\n代理记账200元/月起\n工商变更500元起\n\n常见问题：\nQ: 注册公司需要多长时间？\nA: 一般3-5个工作日即可完成`}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* 右侧：Gemini 风格对话测试 */}
            <div style={{
              display: 'flex', flexDirection: 'column',
              background: 'var(--bg-panel)',
              borderRadius: 16,
              border: '1px solid var(--border-color)',
              overflow: 'hidden',
              height: '100%',
            }}>
              {/* Chat Header */}
              <div style={{
                padding: '16px 20px',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                background: 'linear-gradient(135deg, rgba(249,115,22,0.06), rgba(234,88,12,0.03))',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: '50%',
                    background: 'linear-gradient(135deg, #f97316, #ea580c)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'white', fontSize: 14, fontWeight: 700,
                  }}>
                    {aiName.charAt(0)}
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{aiName}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>AI 智能体测试</div>
                  </div>
                </div>
                <button
                  className="btn btn-ghost"
                  onClick={handleClearChat}
                  style={{ padding: '6px 10px', fontSize: 11, gap: 4 }}
                  title="清空对话"
                >
                  <Eraser size={14} />
                  清空
                </button>
              </div>

              {/* Chat Messages Area */}
              <div style={{
                flex: 1, overflowY: 'auto', padding: '20px 16px',
                display: 'flex', flexDirection: 'column', gap: 16,
              }}>
                {chatMessages.length === 0 && (
                  <div style={{
                    flex: 1, display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center',
                    color: 'var(--text-muted)', gap: 12, padding: 40,
                  }}>
                    <div style={{
                      width: 56, height: 56, borderRadius: '50%',
                      background: 'linear-gradient(135deg, rgba(249,115,22,0.15), rgba(234,88,12,0.08))',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <MessageSquare size={24} style={{ color: 'var(--accent-orange)' }} />
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)' }}>
                      与 {aiName} 对话
                    </div>
                    <div style={{ fontSize: 12, textAlign: 'center', lineHeight: 1.7, maxWidth: 260 }}>
                      发送消息测试 AI 的回复效果<br />
                      支持多轮对话，调用真实 AI 接口
                    </div>
                    {/* Quick prompts */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8, justifyContent: 'center' }}>
                      {['你好', '价格多少？', '怎么合作？', '有什么优惠吗'].map(q => (
                        <button
                          key={q}
                          onClick={() => { setChatInput(q); setTimeout(() => chatInputRef.current?.focus(), 50) }}
                          style={{
                            padding: '6px 14px', borderRadius: 20,
                            border: '1px solid var(--border-color)',
                            background: 'var(--bg-input)',
                            color: 'var(--text-secondary)',
                            fontSize: 12, cursor: 'pointer',
                            transition: 'all 0.2s',
                          }}
                          onMouseEnter={e => { e.target.style.borderColor = 'var(--accent-orange)'; e.target.style.color = 'var(--accent-orange)' }}
                          onMouseLeave={e => { e.target.style.borderColor = 'var(--border-color)'; e.target.style.color = 'var(--text-secondary)' }}
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {chatMessages.map(msg => (
                  <div
                    key={msg.id}
                    style={{
                      display: 'flex',
                      flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                      gap: 10, alignItems: 'flex-start',
                    }}
                  >
                    {/* Avatar */}
                    <div style={{
                      width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                      background: msg.role === 'user'
                        ? 'linear-gradient(135deg, #3b82f6, #2563eb)'
                        : 'linear-gradient(135deg, #f97316, #ea580c)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: 'white', fontSize: 12, fontWeight: 700,
                    }}>
                      {msg.role === 'user' ? '我' : aiName.charAt(0)}
                    </div>

                    {/* Bubble */}
                    <div style={{
                      maxWidth: '80%', display: 'flex', flexDirection: 'column',
                      alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    }}>
                      <div style={{
                        padding: '10px 14px',
                        borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                        background: msg.role === 'user'
                          ? 'linear-gradient(135deg, #3b82f6, #2563eb)'
                          : 'var(--bg-input)',
                        color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                        fontSize: 13, lineHeight: 1.7,
                        boxShadow: msg.role === 'user'
                          ? '0 2px 8px rgba(59,130,246,0.2)'
                          : '0 1px 4px rgba(0,0,0,0.04)',
                        wordBreak: 'break-word',
                      }}>
                        {msg.content}
                      </div>
                      <div style={{
                        fontSize: 10, color: 'var(--text-muted)',
                        marginTop: 4, padding: '0 4px',
                        display: 'flex', gap: 6, alignItems: 'center',
                      }}>
                        <span>{msg.time}</span>
                        {msg.source === 'ai' && <span style={{ color: 'var(--accent-green)' }}>● AI</span>}
                        {msg.source === 'mock' && <span style={{ color: 'var(--accent-orange)' }}>● 模拟</span>}
                        {msg.source === 'error' && <span style={{ color: 'var(--accent-red)' }}>● 错误</span>}
                      </div>
                    </div>
                  </div>
                ))}

                {/* AI Typing indicator */}
                {chatLoading && (
                  <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                      background: 'linear-gradient(135deg, #f97316, #ea580c)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: 'white', fontSize: 12, fontWeight: 700,
                    }}>
                      {aiName.charAt(0)}
                    </div>
                    <div style={{
                      padding: '12px 18px', borderRadius: '16px 16px 16px 4px',
                      background: 'var(--bg-input)',
                      display: 'flex', gap: 5, alignItems: 'center',
                    }}>
                      <span className="typing-dot" style={{ '--i': 0 }} />
                      <span className="typing-dot" style={{ '--i': 1 }} />
                      <span className="typing-dot" style={{ '--i': 2 }} />
                    </div>
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* Chat Input */}
              <div style={{
                padding: '12px 16px',
                borderTop: '1px solid var(--border-color)',
                background: 'var(--bg-panel)',
              }}>
                <div style={{
                  display: 'flex', gap: 8, alignItems: 'center',
                  background: 'var(--bg-input)',
                  borderRadius: 24, padding: '4px 4px 4px 16px',
                  border: '1px solid var(--border-color)',
                  transition: 'border-color 0.2s',
                }}>
                  <input
                    ref={chatInputRef}
                    className="form-input"
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                    placeholder={`给 ${aiName} 发送消息...`}
                    disabled={chatLoading}
                    style={{
                      flex: 1, border: 'none', background: 'transparent',
                      padding: '8px 0', fontSize: 13, outline: 'none',
                      boxShadow: 'none',
                    }}
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={chatLoading || !chatInput.trim()}
                    style={{
                      width: 36, height: 36, borderRadius: '50%',
                      border: 'none', cursor: 'pointer',
                      background: chatInput.trim() && !chatLoading
                        ? 'linear-gradient(135deg, #f97316, #ea580c)'
                        : 'var(--border-color)',
                      color: 'white',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'all 0.2s',
                      flexShrink: 0,
                    }}
                  >
                    {chatLoading ? <Loader size={16} className="spin" /> : <Send size={16} />}
                  </button>
                </div>
                <div style={{
                  textAlign: 'center', fontSize: 10, color: 'var(--text-muted)',
                  marginTop: 6, opacity: 0.6,
                }}>
                  Enter 发送 · 调用通义千问 AI 真实接口
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ★ 敏感词管理 */}
      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-body" style={{ padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <ShieldAlert size={20} color="var(--accent-red)" />
            <span style={{ fontWeight: 700, fontSize: 16 }}>敏感词过滤</span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>AI回复中包含这些词时会自动拦截</span>
          </div>
          
          {/* 添加敏感词 */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              className="form-input"
              placeholder="输入敏感词..."
              value={newWord}
              onChange={e => setNewWord(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && newWord.trim()) {
                  const updated = [...sensitiveWords, newWord.trim()]
                  setSensitiveWords(updated)
                  setNewWord('')
                  // 自动保存
                  fetch('http://localhost:8100/api/sensitive-words', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ words: updated, merchant_id: currentMid })
                  })
                }
              }}
              style={{ flex: 1 }}
            />
            <button
              onClick={() => {
                if (!newWord.trim()) return
                const updated = [...sensitiveWords, newWord.trim()]
                setSensitiveWords(updated)
                setNewWord('')
                fetch('http://localhost:8100/api/sensitive-words', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ words: updated, merchant_id: currentMid })
                })
              }}
              style={{
                padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                background: 'var(--accent-orange)', color: '#fff', border: 'none', cursor: 'pointer'
              }}
            >
              <Plus size={14} />
            </button>
          </div>
          
          {/* 敏感词列表 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {sensitiveWords.length === 0 ? (
              <div style={{ fontSize: 13, color: 'var(--text-muted)', padding: '8px 0' }}>
                暂无敏感词，添加后 AI 回复中包含这些词时会自动替换为安全回复
              </div>
            ) : sensitiveWords.map((word, idx) => (
              <span key={idx} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 10px 4px 12px', borderRadius: 20,
                background: 'rgba(220,53,69,0.08)', color: 'var(--accent-red)',
                fontSize: 13, fontWeight: 500,
              }}>
                {word}
                <X
                  size={14}
                  style={{ cursor: 'pointer', opacity: 0.6 }}
                  onClick={() => {
                    const updated = sensitiveWords.filter((_, i) => i !== idx)
                    setSensitiveWords(updated)
                    fetch('http://localhost:8100/api/sensitive-words', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ words: updated, merchant_id: currentMid })
                    })
                  }}
                />
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Typing animation styles */}
      <style>{`
        .typing-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: var(--text-muted);
          animation: typingBounce 1.4s ease-in-out infinite;
          animation-delay: calc(var(--i) * 0.2s);
        }
        @keyframes typingBounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
    </>
  )
}

import { useState, useRef, useEffect } from 'react'
import ChatWindow from './components/ChatWindow'
import ToolTracePanel from './components/ToolTracePanel'
import { Bot, Zap, Activity } from 'lucide-react'

const SUGGESTED_QUERIES = [
  "How's our pipeline looking for energy this quarter?",
  "Compare sector performance for Q1 2025",
  "What's our revenue forecast for technology deals?",
  "Show me our deal win-rate and conversion metrics",
  "Which sector has the highest pipeline value?",
  "Give me a full BI overview for the current quarter",
]

const API_BASE = import.meta.env.VITE_API_BASE || ''

export default function App() {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        "👋 Hi! I'm **Monday BI**, your AI-powered business intelligence agent.\n\n" +
        "I can analyse your Monday.com pipeline data in real-time — ask me about sector performance, " +
        "revenue forecasts, conversion rates, and more.\n\n" +
        "Try one of the suggestions below or type your own question.",
      trace: [],
      timestamp: new Date(),
    },
  ])
  const [traceSteps, setTraceSteps] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [connected, setConnected] = useState(null) // null=checking, true/false
  const inputRef = useRef(null)

  // Health check on mount
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.ok ? setConnected(true) : setConnected(false))
      .catch(() => setConnected(false))
  }, [])

  const sendQuery = async (query) => {
    if (!query.trim() || loading) return

    const userMsg = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)
    setError(null)
    setTraceSteps([])

    try {
      // Build conversation history from all prior real user/assistant turns
      // (exclude welcome/error messages, cap at last 10 turns to stay within token limits)
      const historyTurns = messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .filter((m) => m.id !== 'welcome')
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content }))

      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, history: historyTurns }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || 'Server error')
      }

      const data = await res.json()

      const assistantMsg = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.answer,
        trace: data.trace || [],
        model: data.model,
        iterations: data.iterations,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, assistantMsg])
      setTraceSteps(data.trace || [])
    } catch (err) {
      setError(err.message)
      const errMsg = {
        id: (Date.now() + 2).toString(),
        role: 'error',
        content: `⚠️ **Error:** ${err.message}`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }

  const handleSuggestion = (q) => {
    sendQuery(q)
  }

  const handleClearChat = () => {
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content:
          "👋 Chat cleared! Ready for your next question.\n\nAsk me anything about your Monday.com pipeline data.",
        trace: [],
        timestamp: new Date(),
      },
    ])
    setTraceSteps([])
    setError(null)
  }

  return (
    <div className="app-shell">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-brand">
          <div className="brand-icon">
            <Bot size={22} />
          </div>
          <div className="brand-text">
            <span className="brand-name">Monday BI Agent</span>
            <span className="brand-sub">Powered by xAI Grok + Monday.com</span>
          </div>
        </div>

        <div className="header-status">
          <div className={`status-dot ${connected === true ? 'online' : connected === false ? 'offline' : 'checking'}`} />
          <span className="status-label">
            {connected === true ? 'API Connected' : connected === false ? 'API Offline' : 'Checking…'}
          </span>
        </div>

        <div className="header-badges">
          <span className="badge badge-purple"><Zap size={11} /> Grok LLM</span>
          <span className="badge badge-blue"><Activity size={11} /> Live API</span>
        </div>
      </header>

      {/* ── Main layout ── */}
      <main className="app-body">
        {/* Left: Chat */}
        <section className="chat-section">
          <ChatWindow
            messages={messages}
            loading={loading}
            onSend={sendQuery}
            onClear={handleClearChat}
            inputRef={inputRef}
          />

          {/* Suggested queries (shown when only welcome message) */}
          {messages.length === 1 && (
            <div className="suggestions">
              <p className="suggestions-label">💡 Try asking:</p>
              <div className="suggestions-grid">
                {SUGGESTED_QUERIES.map((q) => (
                  <button
                    key={q}
                    className="suggestion-chip"
                    onClick={() => handleSuggestion(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Right: Tool trace */}
        <aside className="trace-section">
          <ToolTracePanel steps={traceSteps} loading={loading} />
        </aside>
      </main>
    </div>
  )
}

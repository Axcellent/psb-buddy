import { useMemo, useRef, useState } from "react"
import { Plus, MessageCircle, Search, PanelRightClose, PanelRightOpen, FileText, ShieldCheck, Sparkles, Send, Paperclip, ChevronDown, MoreHorizontal, Copy, ThumbsUp, ThumbsDown, Check, Clock3, X, Command, Menu, ArrowUpRight, BookOpen } from "lucide-react"

const initialChats = [
  { 
    id: "contract", 
    title: "Проверка договора", 
    date: "10 нояб." 
  },
  { 
    id: "vacation", 
    title: "Оформление отпуска", 
    date: "10 нояб." 
  },
  { 
    id: "nda", 
    title: "Соглашение о конфиденциальности", 
    date: "8 нояб." 
  }
]

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  time: "19:42",
  sources: [],
  text: "Здравствуйте! Я помогу найти ответы в документах и покажу, на какие положения опирается каждый вывод.\n\nЗадайте вопрос — например: «Какие документы нужны для оформления отпуска?»"
}

const demoAnswer = {
  text: "Для оформления ежегодного отпуска обычно нужно проверить график отпусков и подать заявление, если требуется согласование или изменение запланированных дат. Работодатель должен уведомить сотрудника о начале отпуска не позднее чем за две недели.\n\nПроверьте локальный порядок согласования в вашей организации: он может предусматривать дополнительные шаги.",
  sources: [
    {
      title: "Правила внутреннего трудового распорядка.pdf",
      section: "Раздел 6. Время отдыха",
      page: "стр. 12",
    },
    {
      title: "График отпусков 2026.xlsx",
      section: "Лист «Сотрудники»",
      page: "строка 48",
    }
  ]
}

const LogoMark = ({ small = false }) => (
  <span className={`logo-mark${small ? " logo-mark-small" : ""}`} aria-hidden="true">
    <i />
    <b />
  </span>
)

function MessageBubble({ message, onSelectSource })
{
  const [copied, setCopied] = useState(false)
  const [reaction, setReaction] = useState("")
  const isAssistant = message.role === "assistant"

  const copyText = async () => {
    try
    {
      await navigator.clipboard.writeText(message.text)
    }
    catch { }

    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  return (
    <article className={`message-row ${isAssistant ? "message-assistant" : "message-user"}`}>
      { isAssistant && (
        <div className="avatar assistant-avatar">
          <LogoMark small />
        </div>
      ) }
      <div className="message-content">
        <div className="message-meta">
          <strong>{ isAssistant ? "Docwise AI" : "Вы"}</strong>
          <span>{ message.time }</span>
          { isAssistant && ( 
            <button 
              className="source-count"
              onClick={() => message.sources?.[0] && onSelectSource(message.sources[0])}
            >
              <FileText size={13} />
              Источники - { message.sources?.length ?? 0 }
            </button>
          ) }
        </div>
        <div className={`bubble ${isAssistant ? "assistant-bubble" : "user-bubble"}`}>
          {isAssistant && (
            <span className="answer-status">
              <Check size={12} />
              ответ готов
            </span>
          )}
          <p>{message.text}</p>
          {isAssistant && message.sources?.length > 0 && (
            <div className="inline-sources">
              {message.sources.map((source) => (
                <button
                  key={source.title}
                  className="inline-source"
                  onClick={() => onSelectSource(source)}
                >
                  <FileText size={13} />
                  {source.title}
                  <ArrowUpRight size={12} />
                </button>
              ))}
            </div>
          )}
        </div>
        {isAssistant && message.id !== "welcome" && (
          <div className="message-actions" aria-label="Действия с ответом">
            <button onClick={copyText} title="Скопировать">
              <Copy size={14} />
              {copied && <span>Скопировано</span>}
            </button>
            <button
              className={reaction === "up" ? "selected" : ""}
              onClick={() => setReaction(reaction === "up" ? "" : "up")}
              title="Полезный ответ"
            >
              <ThumbsUp size={14} />
            </button>
            <button
              className={reaction === "down" ? "selected" : ""}
              onClick={() => setReaction(reaction === "down" ? "" : "down")}
              title="Неполезный ответ"
            >
              <ThumbsDown size={14} />
            </button>
          </div>
        )}
      </div>
      {!isAssistant && <div className="avatar user-avatar">ВЫ</div>}
    </article>
  )
}

export default function App()
{
  const [chats, setChats] = useState(initialChats)
  const [activeChat, setActiveChat] = useState("vacation")
  const [conversations, setConversations] = useState({ vacation: [welcomeMessage] })
  const [input, setInput] = useState("")
  const [search, setSearch] = useState("")
  const [selectedSource, setSelectedSource] = useState(null)
  const [sourcesOpen, setSourcesOpen] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [demoMode, setDemoMode] = useState(true)
  const [isTyping, setIsTyping] = useState(false)

  const inputRef = useRef(null)
  const scrollRef = useRef(null)

  const messages = conversations[activeChat] ?? [welcomeMessage]
  const currentChat = chats.find((chat) => chat.id === activeChat)
  const sources = useMemo(() => messages.flatMap((messages) => messages.sources ?? []), [messages])
  const filteredChats = chats.filter((chat) => chat.title.toLowerCase().includes(search.toLowerCase()))
  
  const createChat = () => {
    const id = `chat-${Date.now()}`

    setChats((prev) => [
      { id, title: "Новый диалог", date: "сейчас" },
      ...prev
    ])

    setConversations((prev) => ({
      ...prev,
      [id]: [welcomeMessage]
    }))

    setActiveChat(id)
    setInput("")
    setSidebarOpen(false)

    window.setTimeout(() => inputRef.current?.focus(), 60)
  }

  const sendMessage = (event) => {
    event?.preventDefault()

    const text = input.trim()
    if (!text || isTyping)
      return

    const time = new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit", 
      minute: "2-digit"
    }).format(new Date())

    const userMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      time, 
      text
    }

    setConversations((prev) => ({
      ...prev,
      [activeChat]: [...(prev[activeChat] ?? [welcomeMessage]), userMessage]
    }))

    setChats((prev) =>
      prev.map((chat) =>
        chat.id === activeChat && chat.title === "Новый диалог"
          ? {
              ...chat,
              title: text.length > 30 ? `${text.slice(0, 30)}...` : text,
              date: "сейчас",
            }
          : chat
      )
    )

    setInput("")
    setIsTyping(true)

    window.setTimeout(() => {
      const reply = {
        id: `reply-${Date.now()}`,
        role: "assistant",
        time,
        ...demoAnswer
      }

      setConversations((prev) => ({
        ...prev,
        [activeChat]: [...(prev[activeChat] ?? [welcomeMessage]), reply],
      }))

      setIsTyping(false)

      window.setTimeout(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: "smooth"
        })
      }, 60)
    }, 900)
  }

  const activateChat = (id) => {
    setActiveChat(id)
    setSidebarOpen(false)
    setSelectedSource(null)
  
    if (!conversations[id]) 
    {
      setConversations((prev) => ({
        ...prev,
        [id]: [welcomeMessage],
      }))
    }
  }

  return (
    <main className="workspace">
      { sidebarOpen && (
        <button
          className="mobile-scrim"
          aria-label="Закрыть меню"
          onClick={() => setSidebarOpen(false)}
        />
      ) }
      <aside className={`sidebar panel ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <LogoMark />
          <div>
            <strong>DOCWISE</strong>
            <span>AI ASSISTANT</span>
          </div>
          <button
            className="icon-button mobile-close"
            aria-label="Закрыть меню"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <button className="new-chat-button" onClick={createChat}>
          <Plus size={18} strokeWidth={2.2} />
          <span>Новый чат</span>
          <kbd><Command size={10} /> K</kbd>
        </button>
        <div className="history-heading">
          <span>История диалогов</span>
          <span className="count-pill">{ chats.length }</span>
        </div>
        <label className="chat-search">
          <Search size={14} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Найти диалог"
          />
        </label>
        <nav className="chat-list" aria-label="История диалогов">
          { filteredChats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => activateChat(chat.id)}
              className={`chat-item ${activeChat === chat.id ? "active" : ""}`}
            >
              <MessageCircle size={16} />
              <span className="chat-title">{chat.title}</span>
              <time>{chat.date}</time>
            </button>
          )) }
          { filteredChats.length === 0 && (
            <p className="empty-search">Диалоги не найдены</p>
          ) }
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-user">
            <div className="user-avatar user-avatar-small">М</div>
            <div>
              <strong>Моя команда</strong>
              <span>Рабочее пространство</span>
            </div>
            <MoreHorizontal size={18} />
          </div>
          <button className="help-link">
            <BookOpen size={15} />
            Как это работает?
            <ArrowUpRight size={13} />
          </button>
        </div>
      </aside>
      <section className="main-column">
      <header className="topbar panel">
        <button
          className="icon-button mobile-menu"
          aria-label="Открыть меню"
          onClick={() => setSidebarOpen(true)}
        >
          <Menu size={19} />
        </button>
        <div className="page-title">
          <span className="eyebrow">
            Интеллектуальный поиск по документам
          </span>
          <h1>
            Юридический ассистент <span className="beta-tag">BETA</span>
          </h1>
        </div>
        <div className="topbar-actions">
          <button
            className={`demo-toggle ${demoMode ? "is-on" : ""}`}
            onClick={() => setDemoMode((prev) => !prev)}
          >
            <span className="status-dot" />
            {demoMode ? "Демо-режим" : "Рабочий режим"}
            <ChevronDown size={13} />
          </button>
          <div className="top-brand">
            <LogoMark small />
            <span>DW</span>
          </div>
        </div>
      </header>
        <section className="chat-panel panel">
          <div className="chat-header">
            <div className="chat-header-icon"><Sparkles size={18} /></div>
            <div className="chat-header-copy">
              <strong>{ currentChat?.title ?? "Диалог с ассистентом" }</strong>
              <span>Ответы с опорой на базу знаний</span>
            </div>
            <div className="secure-session">
              <ShieldCheck size={15} />
              <span>Защищённая сессия</span>
            </div>
            <button
              className="icon-button source-toggle"
              onClick={() => setSourcesOpen(!sourcesOpen)}
              title={sourcesOpen ? "Скрыть источники" : "Показать источники"}
            >
              {sourcesOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
            </button>
          </div>
          <div className="conversation" ref={scrollRef}>
            { messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onSelectSource={setSelectedSource}
              />
            )) }
            { isTyping && (
              <div className="typing-row">
                <div className="avatar assistant-avatar"><LogoMark small /></div>
                <div className="typing-bubble">
                  <span />
                  <span />
                  <span />
                  <small>Ассистент готовит ответ</small>
                </div>
              </div>
            ) }
          </div>
          <div className="composer-area">
            { messages.length === 1 && (
              <div className="suggestions">
                <span>Попробуйте спросить</span>
                <button onClick={() => setInput("Какие документы нужны для оформления отпуска?")}>
                  Оформление отпуска
                </button>
                <button onClick={() => setInput("На что обратить внимание в договоре?")}>
                  Проверка договора
                </button>  
              </div>
            ) }
            <form className="composer" onSubmit={sendMessage}>
              <button
                type="button"
                className="attach-button"
                title="ПРикрепить документ"
                onClick={() => alert("Загрузка документов будет доступна в рабочем режиме")}
              >
                <Paperclip size={17} />
              </button>
              <textarea
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) 
                  {
                    event.preventDefault()
                    sendMessage()
                  }
                }}
                placeholder="Задайте вопрос по документам…"
                rows={1}
              />
              <button
                className={`send-button ${input.trim() ? "ready" : ""}`}
                type="submit"
                disabled={!input.trim() || isTyping}
                aria-label="Отправить сообщение"
              >
                <Send size={16} />
              </button>
            </form>
            <div className="composer-note">
              <ShieldCheck size={12} />
              Ответы формируются по вашим документам. Проверяйте важные выводы.
            </div>
          </div>
        </section>
      </section>
      { sourcesOpen && (
        <aside className="sources-panel panel">
          <div className="sources-heading">
            <div>
              <span className="eyebrow">Проверяемость</span>
              <h2>Источники ответа</h2>
            </div>
            <span className="source-total">{String(sources.length).padStart(2, "0")}</span>
          </div>
          <div className="source-info">
            <div className="source-info-icon"><ShieldCheck size={17} /></div>
            <p>Каждый фрагмент связан с конкретным документом и пунктом.</p>
          </div>
          { selectedSource ? (
            <div className="source-detail">
              <button className="source-back" onClick={() => setSelectedSource(null)}>
                Все источники
              </button>
              <div className="source-file-icon"><FileText size={23} /></div>
              <span className="source-type">Источник ответа</span>
              <h3>{selectedSource.title}</h3>
              <div className="source-detail-row">
                <span>Раздел</span>
                <strong>{selectedSource.section}</strong>
              </div>
              <div className="source-detail-row">
                <span>Расположение</span>
                <strong>{selectedSource.page}</strong>
              </div>
              <button
                className="open-document"
                onClick={() => alert("Просмотр документа появится после подключения хранилища.")}
              >
                Открыть документ
                <ArrowUpRight size={14} />
              </button>
            </div>
          ) : sources.length ? (
            <div className="source-list">
              { sources.map((source, index) => (
                <button
                key={`${source.title}-${index}`}
                className="source-card"
                onClick={() => setSelectedSource(source)}
              >
                <div className="source-card-icon"><FileText size={17} /></div>
                <div>
                  <strong>{source.title}</strong>
                  <span>{source.section} * {source.page}</span>
                </div>
                <ArrowUpRight size={14} />
              </button>
              )) }
            </div>
          ) : (
            <div className="sources-empty">
              <div className="empty-file-icon"><FileText size={24} /></div>
              <strong>Пока нет источников</strong>
              <p>
                После ответа ассистента здесь появятся документы, пункты и цитаты,
                на которых основан вывод.
              </p>
            </div>
          ) }
          <div className="trust-note">
            <div className="trust-icon"><Sparkles size={16} /></div>
            <div>
              <strong>Контроль достоверности</strong>
              <p>Ассистент не додумывает документы и подтверждает выводы фрагментами.</p>
            </div>
          </div>
        </aside>
      ) }
    </main>
  )
}
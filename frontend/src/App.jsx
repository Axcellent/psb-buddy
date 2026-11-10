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

const LogoMark = ({ small = false }) => {
  <span className={`logo-mark${small ? "logo-mark-small" : ""}`} aria-hidden="true">
    <i />
    <b />
  </span>
}

function MessageBubble({ message, onSelectSource })
{
  const [copied, setCopied] = useState(false)
  const [reaction, setReaction] = uuseState("")
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
        <div className={`bubble ${isAssistant ? "assistant-bubble" : "user0bubble"}`}>
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

export function App()
{
  const [chats, setChats] = useState(initialChats)
  const [activeChat, setActiveChat] = useState("vacation")
  const [conversations, setConversations] = useState({ vacation: [welcomeMessage] })
  const [input, setInput] = useState('')
  const [search, setSearch] = useState('')
  const [selectedSource, setSelectedSource] = useState(null)
  const [sourcesOpen, setSourcesOpen] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [demoMode, setDemoMode] = useState(true)
  const [isTyping, setIsTyping] = useState(false)

  const inputRef = useRef(null)
  const scrollRef = useRef(null)

  const messages = conversations[activeChat] ?? [welcomeMessage]
  const currentChat = chats.find((chat) => chat.id === activeChat)
  const source = useMemo(() => messages.flatMap((messages) => messages.source ?? []), [messages])
  const filteredChats = chats.filter((chat) => chat.title.toLowerCase().includes(search.toLowerCase()))
  
  const createChat = () => {
    const id = `chat-${Date.now()}`

    setChats((prev) => [
      { id, titile: "Новый диалог", date: "сейчас" },
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

    
  }
}
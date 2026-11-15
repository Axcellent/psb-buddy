import { useMemo, useRef, useEffect, useState } from "react"
import { Document, Page, pdfjs} from "react-pdf"
import { MessageCircle, Search, ChevronLeft, ChevronRight, Minus, Plus, X, FileText, Send, Copy, ThumbsUp, ThumbsDown, Check, Command, ArrowUpRight } from "lucide-react"

import "react-pdf/dist/Page/AnnotationLayer.css"
import "react-pdf/dist/Page/TextLayer.css"

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString()

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
    id: "rules-vacation",
    title: "Правила внутреннего трудового распорядка.pdf",
    section: "Раздел 6. Время отдыха",
    page: 12,
    pdfUrl: "/document/rules.pdf",
    quote:
      "Ежегодный оплачиваемый отпуск предоставляется в соответствии " +
      "с утверждённым графиком отпусков. При изменении запланированных " +
      "дат сотрудник направляет заявление на согласование.",
    chunks: [
      {
        id: "rules-1",
        page: 12,
        text:
          "Ежегодный оплачиваемый отпуск предоставляется в соответствии " +
          "с утверждённым графиком отпусков. При изменении запланированных " +
          "дат сотрудник направляет заявление на согласование."
      },
      {
        id: "rules-2",
        page: 12,
        text:
          "В заявлении сотрудник указывает предполагаемые даты " +
          "и продолжительность отпуска. Заявление передаётся " +
          "на согласование в установленном порядке."
      },
      {
        id: "rules-3",
        page: 13,
        text:
          "После согласования заявления ответственное подразделение " +
          "оформляет необходимые документы."
      },
    ],
      chunkId: "rules-1"
    },
    {
      id: "schedule-vacation",
      title: "График отпусков 2026.xlsx",
      section: "Лист «Сотрудники»",
      page: null,
      location: "Строка 48",
      quote:
        "Демонстрационная запись графика: даты отпуска сотрудника " +
        "согласованы с руководителем.",
      chunks: [
        {
          id: "schedule-1",
          page: null,
          text:
            "Демонстрационная запись графика: даты отпуска сотрудника " +
            "согласованы с руководителем."
        },
      ],
      chunkId: "schedule-1"
    }
  ]
}

const LogoMark = ({ small = false }) => (
  <img
    src="/psb.svg"
    alt="ПСБ"
    className={`logo-mark${small ? " logo-mark-small" : ""}`}
    width={small ? 24 : 32}
    height={small ? 24 : 32}
  />
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

function PdfReader({ source, onClose }) 
{
  const [numPages, setNumPages] = useState(0)
  const [pageNumber, setPageNumber] = useState(1)
  const [scale, setScale] = useState(1)
  const [containerWidth, setContainerWidth] = useState(600)
  const [pageError, setPageError] = useState(false)

  const bodyRef = useRef(null)
  const closeRef = useRef(null)

  useEffect(() => {
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow

    document.body.style.overflow = "hidden"
    closeRef.current?.focus()

    const element = bodyRef.current

    const observer = new ResizeObserver(([entry]) => {
      setContainerWidth(Math.max(100, Math.floor(entry.contentRect.width)))
    })

    if (element) 
      observer.observe(element)

    return () => {
      observer.disconnect()
      document.body.style.overflow = previousOverflow
      previousFocus?.focus?.()
    }
  }, [])

  useEffect(() => {
    bodyRef.current?.scrollTo({
      top: 0,
      left: 0,
    })

    setPageError(false)
  }, [pageNumber])

  const handleLoadSuccess = ({ numPages: count }) => {
    setNumPages(count)

    const requestedPage = Number(source.page)
    const initialPage = Number.isInteger(requestedPage) ? requestedPage : 1

    setPageNumber(Math.min(Math.max(initialPage, 1), count))
  }

  const handleKeyDown = (event) => {
    if (event.key === "Escape") 
    {
      onClose()
      return
    }

    if (event.key !== "Tab") return

    const controls = Array.from(
      event.currentTarget.querySelectorAll(
        "button:not(:disabled), input:not(:disabled), a[href]",
      ),
    ).filter((element) => element.getClientRects().length > 0)

    const first = controls[0]
    const last = controls[controls.length - 1]

    if (event.shiftKey && document.activeElement === first) 
    {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) 
    {
      event.preventDefault()
      first?.focus()
    }
  }

  const pageWidth = Math.min(containerWidth, 780)

  return (
    <div
      className="pdf-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget)
          onClose()
      }}
    >
      <section
        className="pdf-reader"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pdf-reader-title"
        onKeyDown={handleKeyDown}
      >
        <header className="pdf-reader-header">
          <div className="pdf-reader-title">
            <span>Просмотр документа</span>
            <h2 id="pdf-reader-title">{source.title}</h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="icon-button"
            aria-label="Закрыть документ"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>
        <div className="pdf-toolbar">
          <div className="pdf-control-group">
            <button
              type="button"
              className="icon-button"
              aria-label="Предыдущая страница"
              disabled={!numPages || pageNumber <= 1}
              onClick={() => setPageNumber((prev) => prev - 1)}
            >
              <ChevronLeft size={18} />
            </button>
            <span className="pdf-page-label" aria-live="polite">
              { numPages ? `${pageNumber} / ${numPages}` : "- / -" }
            </span>
            <button
              type="button"
              className="icon-button"
              aria-label="Следующая страница"
              disabled={!numPages || pageNumber >= numPages}
              onClick={() => setPageNumber((prev) => prev + 1)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
          <div className="pdf-control-group">
            <button
              type="button"
              className="icon-button"
              aria-label="Уменьшить масштаб"
              disabled={scale <= 0.5}
              onClick={() =>
                setScale((prev) =>
                  Math.max(0.5, Number((prev - 0.25).toFixed(2))),
                )
              }
            >
              <Minus size={17} />
            </button>
            <button
              type="button"
              className="pdf-zoom-reset"
              title="Сбросить масштаб"
              onClick={() => setScale(1)}
            >
              { Math.round(scale * 100) }%
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="Увеличить масштаб"
              disabled={scale >= 2}
              onClick={() =>
                setScale((prev) =>
                  Math.min(2, Number((prev + 0.25).toFixed(2))),
                )
              }
            >
              <Plus size={17} />
            </button>
          </div>
        </div>
        <div className="pdf-reader-body" ref={bodyRef}>
          <Document
            file={source.pdfUrl}
            onLoadSuccess={handleLoadSuccess}
            onLoadError={(error) => {
              setNumPages(0)
              console.error("Ошибка загрузки PDF:", error)
            }}
            loading={
              <p className="pdf-status" role="status">
                Загрузка документа…
              </p>
            }
            error={
              <div className="pdf-status" role="alert">
                <strong>Не удалось открыть PDF.</strong>
                <p>
                  Проверьте адрес документа и наличие файла
                  в папке public/documents.
                </p>
              </div>
            }
            noData={
              <p className="pdf-status">
                Адрес документа не указан.
              </p>
            }
          >
            { numPages > 0 && (
              <Page
                key={pageNumber}
                pageNumber={pageNumber}
                width={pageWidth}
                scale={scale}
                renderTextLayer
                renderAnnotationLayer
                onRenderError={() => setPageError(true)}
                loading={
                  <p className="pdf-status" role="status">
                    Загрузка страницы…
                  </p>
                }
                error={
                  <p className="pdf-status" role="alert">
                    Не удалось отобразить страницу.
                  </p>
                }
              />
            ) }
          </Document>
          { pageError && (
            <p className="pdf-status" role="alert">
              Ошибка отрисовки. Попробуйте открыть другую страницу.
            </p>
          ) }
        </div>
        { source.quote && (
          <footer className="pdf-reader-quote">
            <strong>Фрагмент, использованный в ответе</strong>
            <blockquote>{source.quote}</blockquote>
          </footer>
        ) }
      </section>
    </div>
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
  const [readerSource, setReaderSource] = useState(null)
  const [isTyping, setIsTyping] = useState(false)

  const inputRef = useRef(null)
  const scrollRef = useRef(null)

  const messages = conversations[activeChat] ?? [welcomeMessage]
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
      </aside>
      <section className="main-column">
        <section className="chat-panel panel">
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
          </div>
        </section>
      </section>
      { sourcesOpen && (
        <aside className="sources-panel panel">
          <div className="sources-heading">
            <div>
              <h2>Источники ответа</h2>
            </div>
            <span className="source-total">{String(sources.length).padStart(2, "0")}</span>
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
                type="button"
                className="open-document"
                disabled={!selectedSource.pdfUrl}
                title={selectedSource.pdfUrl ? "Открыть PDF внутри приложения" : "PDF-версия документа пока недоступна"}
                onClick={() => setReaderSource(selectedSource)}
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
        </aside>
      ) }
      { readerSource && (
        <PdfReader
          key={`${readerSource.id ?? readerSource.title}:${readerSource.pdfUrl}`}
          source={readerSource}
          onClose={() => setReaderSource(null)}
        />
      ) }
    </main>
  )
}
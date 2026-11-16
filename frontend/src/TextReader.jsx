import { Fragment, useEffect, useMemo, useRef, useState } from "react"
import { X } from "lucide-react"
import { apiUrl } from "./api"

export default function TextReader({ source, onClose }) {
  const [doc, setDoc] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const closeRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError("")
    setDoc(null)
    if (!source.pdfUrl) {
      setLoading(false)
      setError("URL документа не указан")
      return
    }
    fetch(apiUrl(source.pdfUrl))
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const type = r.headers.get("content-type") || ""
        if (!type.includes("application/json")) {
          throw new Error("Документ не является текстовым")
        }
        return r.json()
      })
      .then((data) => {
        if (!cancelled) setDoc(data)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [source.pdfUrl])

  useEffect(() => {
    closeRef.current?.focus()
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    const onKey = (e) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => {
      document.body.style.overflow = prev
      document.removeEventListener("keydown", onKey)
    }
  }, [onClose])

  const content = useMemo(() => {
    if (!doc) return null
    const text = doc.text || ""
    const quote = (source.quote || "").trim()
    if (!quote) return text
    const parts = text.split(quote)
    if (parts.length < 2) return text
    return parts.map((part, i) => (
      <Fragment key={i}>
        {part}
        {i < parts.length - 1 && <mark>{quote}</mark>}
      </Fragment>
    ))
  }, [doc, source.quote])

  return (
    <div
      className="pdf-backdrop"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        className="pdf-reader"
        role="dialog"
        aria-modal="true"
        aria-labelledby="text-reader-title"
      >
        <header className="pdf-reader-header">
          <div className="pdf-reader-title">
            <span>Просмотр документа</span>
            <h2 id="text-reader-title">{source.title}</h2>
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
        <div className="pdf-reader-body">
          {loading && (
            <p className="pdf-status" role="status">
              Загрузка документа…
            </p>
          )}
          {error && (
            <p className="pdf-status" role="alert">
              Не удалось открыть документ: {error}
            </p>
          )}
          {doc && (
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontFamily: "inherit",
                margin: 0,
                lineHeight: 1.55,
              }}
            >
              {content}
            </pre>
          )}
        </div>
        {source.quote && (
          <footer className="pdf-reader-quote">
            <strong>Фрагмент, использованный в ответе</strong>
            <blockquote>{source.quote}</blockquote>
          </footer>
        )}
      </section>
    </div>
  )
}

import { useTranslation } from 'react-i18next'
import { resolveLang, localized, proseParts } from '../../guides.utils'
import type { LocalizedText } from '../../guides.types'

/** Props for ProseBlock. */
interface ProseBlockProps {
  /** The block's text. */
  body: LocalizedText
  /** Whether the next block is not prose, so a short line here heads it. */
  beforeNonProse: boolean
}

/**
 * A prose block as headings, term lists and plain lines.
 * @param props The text and whether a non-prose block follows.
 * @returns The formatted prose.
 */
export function ProseBlock({ body, beforeNonProse }: ProseBlockProps) {
  const { i18n } = useTranslation()
  const lang = resolveLang(i18n.language)

  return (
    <div className="flex flex-col gap-2">
      {proseParts(localized(body, lang), beforeNonProse).map((part, i) => {
        if (part.kind === 'heading') {
          return <h3 key={i} className="text-sm font-bold tracking-wide text-[#c084fc]">{part.text}</h3>
        }
        if (part.kind === 'terms') {
          return (
            <dl key={i} className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 rounded-lg bg-[#151515] px-3 py-2.5 text-sm">
              {part.terms.map((term, ti) => (
                <div key={ti} className="contents">
                  <dt className="font-bold text-[#ffffff]">{term.term}</dt>
                  <dd className="leading-relaxed whitespace-pre-line text-[#cbd5e1]">{term.lines.join('\n')}</dd>
                </div>
              ))}
            </dl>
          )
        }
        return <p key={i} className="text-sm leading-relaxed text-[#cbd5e1]">{part.text}</p>
      })}
    </div>
  )
}

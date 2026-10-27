import { Fragment } from 'react'
import { matcher } from '../encyclopedia-content'
import { linkDescription } from '../encyclopedia.utils'
import { CardLink } from './CardLink'
import { GlossaryTerm, KeywordTerm } from './GlossaryTerm'

/**
 * Text with its glossary terms, game keywords and card names linked.
 * @param props The text and its classes.
 * @param props.text The text to link.
 * @param props.className Classes for the wrapping span.
 * @returns The linked text.
 */
export function RichDescription({ text, className }: { text: string; className?: string }) {
  const segments = linkDescription(text, matcher)
  return (
    <span className={className}>
      {segments.map((seg, i) =>
        seg.kind === 'term' ? (
          <GlossaryTerm key={i} termId={seg.termId}>
            {seg.value}
          </GlossaryTerm>
        ) : seg.kind === 'keyword' ? (
          <KeywordTerm key={i} definition={seg.definition}>
            {seg.value}
          </KeywordTerm>
        ) : seg.kind === 'card' ? (
          <CardLink key={i} cardId={seg.cardId}>
            {seg.value}
          </CardLink>
        ) : (
          <Fragment key={i}>{seg.value}</Fragment>
        ),
      )}
    </span>
  )
}

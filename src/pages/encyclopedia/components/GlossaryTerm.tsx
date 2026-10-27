import type { ReactNode } from 'react'
import { Popover } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { glossaryById } from '../encyclopedia-content'
import { localized, resolveLang } from '../encyclopedia.utils'

/** Props for LinkPopover. */
interface LinkPopoverProps {
  /** The linked text as it reads in the description. */
  label: string
  /** The link's text colour classes, purple for terms and blue for cards. */
  linkClassName: string
  /** Extra classes for the popover box, such as a wider max width. */
  bodyClassName?: string
  /** What the popover shows. */
  children: ReactNode
}

/** Props for TermPopover. */
interface TermPopoverProps {
  /** The linked text as it reads in the description. */
  children: string
  /** The popover's title. */
  title: string
  /** The popover's body. */
  definition: string
}

/**
 * Linked text that opens a small popover, shared by the Encyclopedia's term, keyword and card links.
 * @param props See `LinkPopoverProps`.
 * @returns The link and its popover.
 */
export function LinkPopover({ label, linkClassName, bodyClassName, children }: LinkPopoverProps) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button type="button" className={cn('cursor-pointer border-none bg-transparent p-0 underline decoration-dotted underline-offset-2', linkClassName)}>
          {label}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className={cn('z-50 max-w-[260px] rounded-md border border-[#444] bg-[#1e1e1e] p-3 text-xs text-[#d4d4d4] shadow-xl', bodyClassName)}
          sideOffset={4}
          onOpenAutoFocus={e => e.preventDefault()}
        >
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

/**
 * Linked text that opens a small popover with a definition.
 * @param props See `TermPopoverProps`.
 * @returns The link and its popover.
 */
function TermPopover({ children, title, definition }: TermPopoverProps) {
  return (
    <LinkPopover label={children} linkClassName="text-[#c084fc] hover:text-[#d8b4fe]">
      <p className="mb-1 font-bold text-[#e9d5ff]">{title}</p>
      <p className="leading-relaxed">{definition}</p>
    </LinkPopover>
  )
}

/**
 * A glossary term, linked to its hand-written definition.
 * @param props The term id and the linked text.
 * @param props.termId The glossary entry's id.
 * @param props.children The linked text.
 * @returns The link, or the plain text when the term is unknown.
 */
export function GlossaryTerm({ termId, children }: { termId: string; children: string }) {
  const { i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const entry = glossaryById.get(termId)

  if (!entry) return <>{children}</>
  return <TermPopover title={localized(entry.term, lang)} definition={localized(entry.definition, lang)}>{children}</TermPopover>
}

/**
 * A game keyword, linked to the game's own definition.
 * @param props The keyword's definition and the linked text.
 * @param props.definition The game's definition.
 * @param props.children The linked text, such as "Ignition" or "Incinerate:".
 * @returns The link.
 */
export function KeywordTerm({ definition, children }: { definition: string; children: string }) {
  return <TermPopover title={children.replace(/:$/, '')} definition={definition}>{children}</TermPopover>
}

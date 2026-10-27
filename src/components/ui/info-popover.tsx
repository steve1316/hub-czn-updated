import * as React from 'react'
import { Popover } from 'radix-ui'
import { Info } from 'lucide-react'

interface InfoPopoverProps {
  content: React.ReactNode
  className?: string
  ariaLabel?: string
}

export function InfoPopover({ content, className, ariaLabel = 'More information' }: InfoPopoverProps) {
  return (
    <Popover.Root>
      <Popover.Trigger
        type="button"
        className={`text-[#999] hover:text-[#ffffff] cursor-pointer leading-none bg-transparent border-none p-0.5 rounded inline-flex items-center${className ? ` ${className}` : ''}`}
        aria-label={ariaLabel}
      >
        <Info size={16} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="bg-[#1e1e1e] border border-[#444] rounded-md p-3 text-sm text-[#d4d4d4] shadow-xl max-w-[280px] z-50"
          sideOffset={4}
          onOpenAutoFocus={e => e.preventDefault()}
        >
          {content}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

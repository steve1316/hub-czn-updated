import { useTranslation } from 'react-i18next'
import { assetUrl } from '@/lib/api'
import { AssetImage } from '@/components/ui/asset-image'
import type { SetItem } from '../../guides.types'

/** Props for SetListBlock. */
interface SetListBlockProps {
  /** The parts of the sheet's set line, in order. */
  items: SetItem[]
}

/**
 * A sheet line of sets as set cards, with parts that name no set (such as "Flex") as plain pills.
 * @param props The set line's parts.
 * @returns The set cards.
 */
export function SetListBlock({ items }: SetListBlockProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {items.map((item, index) =>
        item.setId === undefined ? (
          <span
            key={`${item.label}-${index}`}
            className="self-center rounded-full border border-dashed border-[#555] px-3 py-1 text-xs text-[#b3b3b3]"
          >
            {/^flex$/i.test(item.label) ? t('guides.flex') : item.label}
          </span>
        ) : (
          <article
            key={`${item.setId}-${index}`}
            title={t('guides.sheetSays', { label: item.label })}
            className="flex max-w-xs gap-2.5 rounded-lg border border-[#282828] bg-[#181818] p-2.5"
          >
            {item.icon && <AssetImage src={assetUrl(item.icon)} alt="" className="h-9 w-9 shrink-0 object-contain" />}
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <h4 className="truncate text-sm font-bold text-[#ffffff]">{item.name}</h4>
                {item.pieces !== undefined && (
                  <span className="shrink-0 rounded bg-[#c084fc]/20 px-1.5 text-[10px] font-bold text-[#c084fc]">{item.pieces}pc</span>
                )}
                {item.flex && (
                  <span className="shrink-0 rounded-full border border-dashed border-[#555] px-1.5 text-[10px] text-[#b3b3b3]">{t('guides.flex')}</span>
                )}
              </div>
              {item.bonus && <p className="mt-0.5 text-xs leading-relaxed text-[#b3b3b3]">{item.bonus}</p>}
            </div>
          </article>
        ),
      )}
    </div>
  )
}

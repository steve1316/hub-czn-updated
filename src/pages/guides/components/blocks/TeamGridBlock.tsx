import { useTranslation } from 'react-i18next'
import { getCharacterFaceUrl } from '@/lib/deck-builder-assets'
import { cn } from '@/lib/utils'
import { resolveLang, localized } from '../../guides.utils'
import type { LocalizedText, TeamMember } from '../../guides.types'

/** Props for TeamGridBlock. */
interface TeamGridBlockProps {
  /** Untitled groups are example teams, titled ones are the picks for a role. */
  groups: { title?: LocalizedText; members: TeamMember[] }[]
  /** The guide character's res_id, whose face is ringed. */
  selfId: number
}

/**
 * Example teams as numbered cards, and role picks as labelled cards, with each member's face and name.
 * @param props The groups and the guide character's res_id.
 * @returns The team cards.
 */
export function TeamGridBlock({ groups, selfId }: TeamGridBlockProps) {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  // Untitled groups are numbered on their own, so a role card between them does not skip a number.
  let teamNumber = 0

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {groups.map((group, gi) => (
        <div key={gi} className="flex flex-col gap-2 rounded-lg border border-[#282828] bg-[#181818] p-3">
          <h4 className={cn('text-sm font-bold', group.title ? 'text-[#c084fc]' : 'text-[#ffffff]')}>
            {group.title ? localized(group.title, lang) : t('guides.team', { n: ++teamNumber })}
          </h4>
          <div className="flex flex-wrap gap-2">
            {group.members.map((member, mi) => {
              const face = getCharacterFaceUrl(member.charResId)
              const self = member.charResId === selfId
              return (
                <div key={`${member.charResId}-${mi}`} className="flex w-20 flex-col items-center gap-1">
                  {face ? (
                    <img
                      src={face}
                      alt={member.name}
                      className={cn('h-16 w-16 rounded-full object-cover', self && 'ring-2 ring-[#c084fc]')}
                    />
                  ) : (
                    <div className={cn('grid h-16 w-16 place-items-center rounded-full bg-[#222] text-base font-bold text-[#8a8a8a]', self && 'ring-2 ring-[#c084fc]')}>
                      {member.name.charAt(0)}
                    </div>
                  )}
                  <span className="w-full text-center text-xs leading-tight text-[#b3b3b3]">{member.name}</span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

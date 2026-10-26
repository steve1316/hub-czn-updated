// Pictures the sheet shows that no card or portrait matched, such as relic screenshots, keyed by file name.
const guideImages = Object.fromEntries(
  Object.entries(
    import.meta.glob('../../data/images/*.webp', {
      eager: true,
      query: '?url',
      import: 'default',
    }) as Record<string, string>,
  ).map(([path, url]) => [path.split('/').pop(), url]),
) as Record<string, string>

/** Props for ImageBlock. */
interface ImageBlockProps {
  /** The picture's file name under `data/images`. */
  image: string
}

/**
 * One picture from the sheet, shown at its natural width up to the page width.
 * @param props The picture's file name.
 * @returns The picture, or nothing when the file is missing.
 */
export function ImageBlock({ image }: ImageBlockProps) {
  const src = guideImages[image]
  if (!src) return null
  return <img src={src} alt="" loading="lazy" className="max-w-full self-start rounded-lg border border-[#282828]" />
}

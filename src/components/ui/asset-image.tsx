import { useEffect, useRef, useState } from "react"
import type { ImgHTMLAttributes, ReactNode } from "react"
import { ImageOff } from "lucide-react"
import { MAX_IMAGE_RETRIES, imageRetryDelay, imageRetryUrl } from "@/lib/imageRetry"

/** Props for `AssetImage`. Takes the normal `<img>` props plus an optional fallback. */
interface AssetImageProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> {
  /** Full image url, usually from `assetUrl()`. */
  src: string
  /** Shown once all retries have failed. Defaults to a dark neutral placeholder sized by `className`. */
  fallback?: ReactNode
}

/**
 * An `<img>` that loads lazily and retries failed loads with backoff before showing a placeholder.
 * @param props The `<img>` props, plus `fallback` for a custom failure view.
 * @returns The image, or the fallback after the last retry fails.
 */
export function AssetImage({ src, fallback, className, onError, alt = "", ...rest }: AssetImageProps) {
  const [attempt, setAttempt] = useState(0)
  const [failed, setFailed] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // A new src starts over.
  useEffect(() => {
    setAttempt(0)
    setFailed(false)
  }, [src])

  // Cancel a pending retry on unmount or when src changes.
  useEffect(() => () => clearTimeout(timer.current), [src])

  if (failed) {
    return (
      fallback ?? (
        <div className={`${className ?? ""} flex items-center justify-center bg-[#282828] text-[#555]`} role="img" aria-label={alt}>
          <ImageOff className="h-1/2 w-1/2 max-h-4 max-w-4" />
        </div>
      )
    )
  }

  return (
    <img
      {...rest}
      src={imageRetryUrl(src, attempt)}
      alt={alt}
      className={className}
      loading="lazy"
      decoding="async"
      onError={(e) => {
        onError?.(e)
        if (attempt >= MAX_IMAGE_RETRIES) {
          setFailed(true)
          return
        }
        clearTimeout(timer.current)
        timer.current = setTimeout(() => setAttempt(attempt + 1), imageRetryDelay(attempt + 1))
      }}
    />
  )
}

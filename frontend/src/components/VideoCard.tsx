// A preview card for one input video. FFmpeg in the local sidecar extracts a
// small JPEG; never ask WebKitGTK to decode a video inside the editor window.
import { useEffect, useState } from "react"
import { Trash2, Film } from "lucide-react"
import { basename } from "@/lib/files"
import { getVideoInfo, SIDECAR_BASE } from "@/lib/api"

function formatDuration(secs: number): string {
  if (!Number.isFinite(secs) || secs <= 0) return ""
  const total = Math.round(secs)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m)
  return (h > 0 ? h + ":" : "") + mm + ":" + String(s).padStart(2, "0")
}

export function VideoCard({
  path,
  disabled,
  onRemove,
}: {
  path: string
  disabled?: boolean
  onRemove: () => void
}) {
  const [duration, setDuration] = useState(0)
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const posterUrl = SIDECAR_BASE + "/video-poster?path=" + encodeURIComponent(path)

  useEffect(() => {
    let cancelled = false
    setDuration(0)
    setFailed(false)
    setLoaded(false)
    void getVideoInfo(path)
      .then((info) => { if (!cancelled && info.ok) setDuration(info.duration) })
      .catch(() => { /* Missing engine: still allow removing the input. */ })
    return () => { cancelled = true }
  }, [path])

  return (
    <div className="relative overflow-hidden rounded-md border bg-card">
      <div className="relative flex h-28 items-center justify-center bg-muted">
        {!failed && (
          <img
            src={posterUrl}
            alt=""
            className={loaded ? "size-full object-cover" : "hidden"}
            onLoad={() => setLoaded(true)}
            onError={() => setFailed(true)}
          />
        )}
        {!loaded && <Film className="size-6 text-muted-foreground" />}
        {duration > 0 && (
          <span className="absolute right-1 top-1 rounded bg-black/70 px-1 text-[10px] text-white">
            {formatDuration(duration)}
          </span>
        )}
        <button
          aria-label={"Remove " + basename(path)}
          className="absolute left-1 top-1 rounded bg-black/70 p-1 text-white transition-colors hover:bg-destructive disabled:opacity-40"
          disabled={disabled}
          onClick={onRemove}
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
      <p className="line-clamp-2 p-2 text-xs" title={path}>
        {basename(path)}
      </p>
    </div>
  )
}

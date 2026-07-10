/** WAAPI ghost flight: page titles fly between graph nodes and list rows.
 * Ghosts are raw DOM in the dedicated layer, animated with transform/opacity
 * only — nothing here touches React state, so the flight can't trigger a
 * render or a layout pass mid-animation. */

export type FlightRect = { left: number; top: number; width: number; height: number }

export type Flight = {
  text: string
  from: FlightRect
  /** null → no visible destination (node panned offscreen): fade in place */
  to: FlightRect | null
}

export const reducedMotion = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

const DURATION = 300
const STAGGER = 25
const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)'

/** Rects are relative to the ghost layer (which is inset:0 in main). Ghosts
 * are sized at the destination rect and scaled from the source rect, all via
 * a single transform from the layer origin — top/left are never animated. */
export function flyTitles(flights: Flight[], layer: HTMLElement): Promise<void> {
  if (!flights.length || reducedMotion()) return Promise.resolve()
  const ghosts: HTMLElement[] = []
  const anims: Promise<unknown>[] = []
  flights.forEach((f, i) => {
    const el = document.createElement('div')
    el.className = 'wiki-ghost'
    el.textContent = f.text
    const to = f.to ?? f.from
    el.style.width = `${to.width}px`
    el.style.height = `${to.height}px`
    layer.appendChild(el)
    ghosts.push(el)
    const keyframes = f.to
      ? [
          {
            transform: `translate(${f.from.left}px, ${f.from.top}px) scale(${
              f.from.width / Math.max(to.width, 1)
            }, ${f.from.height / Math.max(to.height, 1)})`,
            opacity: 0.95,
          },
          { transform: `translate(${to.left}px, ${to.top}px) scale(1, 1)`, opacity: 1 },
        ]
      : [
          { transform: `translate(${f.from.left}px, ${f.from.top}px)`, opacity: 1 },
          { transform: `translate(${f.from.left}px, ${f.from.top}px)`, opacity: 0 },
        ]
    const anim = el.animate(keyframes, {
      duration: DURATION,
      delay: i * STAGGER,
      easing: EASE,
      fill: 'both',
    })
    anims.push(anim.finished.catch(() => {}))
  })
  return Promise.all(anims).then(() => ghosts.forEach((g) => g.remove()))
}

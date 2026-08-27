export function probe(el: Element) {
  try {
    el.requestFullscreen();
  } catch (e) {
    // Safari throws when not user-initiated; the caller re-prompts.
  }
}

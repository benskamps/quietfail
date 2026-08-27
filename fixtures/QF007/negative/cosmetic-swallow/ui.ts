// Nothing in these try blocks changes any state that outlives the call, so a
// vanished error costs nothing and reporting it is noise.
export function focusFirst(el: HTMLElement) {
  try {
    el.focus();
  } catch (e) {}
}

export function supportsGrid(): boolean {
  let ok = false;
  try {
    ok = CSS.supports("display", "grid");
  } catch (e) {}
  return ok;
}

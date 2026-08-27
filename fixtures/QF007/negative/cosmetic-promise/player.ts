// Autoplay rejection is expected and costs nothing; nothing was written.
export function tryAutoplay(video: HTMLVideoElement) {
  video.play().catch(() => {});
}

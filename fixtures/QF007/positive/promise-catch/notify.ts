export function notify(userId: string) {
  return sendPush(userId).catch(() => {});
}

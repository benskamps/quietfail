export async function save(record: Record<string, unknown>) {
  try {
    await db.insert(record);
  } catch (e) {
    console.error("insert failed", e);
    return false;
  }
  return true;
}

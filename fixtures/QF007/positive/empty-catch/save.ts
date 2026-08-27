export async function save(record: Record<string, unknown>) {
  try {
    await db.insert(record);
  } catch (e) {}
  return true;
}

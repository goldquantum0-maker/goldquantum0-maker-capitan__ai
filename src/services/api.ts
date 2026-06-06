const BASE = "/api";

export async function streamChat(
  messages: { role: string; content: string }[],
  onChunk: (c: string) => void,
  onDone: () => void
) {
  const res = await fetch(BASE + "/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: messages, stream: true }),
  });
  const reader = res.body?.getReader();
  const decoder = new TextDecoder();
  if (!reader) return;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    const lines = text.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        if (data.done) { onDone(); return; }
        if (data.content) onChunk(data.content);
      }
    }
  }
}

export async function fetchPrices() {
  const res = await fetch(BASE + "/market/prices");
  return res.json();
}

export async function generateReport(prompt: string, title: string) {
  const res = await fetch(BASE + "/reports/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: prompt, title: title }),
  });
  return res.json();
}

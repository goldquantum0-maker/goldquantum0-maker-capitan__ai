const API_BASE = "/api";

interface ChatMessage {
  role: string;
  content: string;
}

interface StreamResponse {
  content?: string;
  done?: boolean;
}

export async function streamChat(
  messages: ChatMessage[],
  onChunk: (content: string) => void,
  onDone: () => void,
  onError: (error: string) => void
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, stream: true }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("No response body");
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const jsonStr = line.slice(6);
          try {
            const data: StreamResponse = JSON.parse(jsonStr);
            if (data.done) {
              onDone();
              return;
            }
            if (data.content) {
              onChunk(data.content);
            }
          } catch {
            // Skip malformed JSON chunks
          }
        }
      }
    }
  } catch (error) {
    onError(error instanceof Error ? error.message : "Connection failed");
  }
}

export async function fetchMarketPrices(): Promise<{
  data: Record<string, { price: number; change_pct: number; source: string }>;
  count: number;
}> {
  const response = await fetch(`${API_BASE}/market/prices`);
  if (!response.ok) throw new Error("Failed to fetch prices");
  return response.json();
}

export async function fetchMarketNews(): Promise<{
  data: Array<{ title: string; source: string; url?: string }>;
  count: number;
}> {
  const response = await fetch(`${API_BASE}/market/news`);
  if (!response.ok) throw new Error("Failed to fetch news");
  return response.json();
}

export async function generateReport(
  prompt: string,
  title: string,
  category: string = "general"
): Promise<{
  id?: string;
  title: string;
  content: string;
  category: string;
}> {
  const response = await fetch(`${API_BASE}/reports/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, title, category }),
  });
  if (!response.ok) throw new Error("Report generation failed");
  return response.json();
}

export async function downloadReportPDF(
  prompt: string,
  title: string
): Promise<string> {
  const response = await fetch(`${API_BASE}/reports/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, title }),
  });
  if (!response.ok) throw new Error("PDF generation failed");
  return response.text();
}
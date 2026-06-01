export type ArticleCard = {
  title: string;
  source: string;
  date: string | null;
  snippet: string;
  url: string;
  tags: string[];
};

export type Topic = { slug: string; label: string };

export type ChatResponse = {
  answer: string;
  cards: ArticleCard[];
  status: "ok" | "empty" | "degraded";
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export async function fetchTopics(): Promise<Topic[]> {
  const res = await fetch(`${API_URL}/topics`, { cache: "no-store" });
  if (!res.ok) throw new Error(`topics: ${res.status}`);
  return res.json();
}

export async function postChat(
  question: string,
  topics: string[],
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, topics }),
  });
  if (!res.ok) throw new Error(`chat: ${res.status}`);
  return res.json();
}

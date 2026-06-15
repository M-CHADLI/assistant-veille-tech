"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArticleCard,
  ChatResponse,
  Topic,
  fetchTopics,
  postChat,
} from "../lib/api";
import { HowItWorks } from "./HowItWorks";

const TAG_COLORS = [
  "bg-indigo-500/20 text-indigo-200 border-indigo-400/40",
  "bg-emerald-500/20 text-emerald-200 border-emerald-400/40",
  "bg-amber-500/20 text-amber-200 border-amber-400/40",
  "bg-rose-500/20 text-rose-200 border-rose-400/40",
  "bg-sky-500/20 text-sky-200 border-sky-400/40",
  "bg-fuchsia-500/20 text-fuchsia-200 border-fuchsia-400/40",
];

function tagColor(tag: string): string {
  let h = 0;
  for (const ch of tag) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TAG_COLORS[h % TAG_COLORS.length];
}

export default function Page() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [customTopic, setCustomTopic] = useState("");
  const [question, setQuestion] = useState(
    "Quelles tendances reviennent cette semaine ?",
  );
  const [resp, setResp] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTopics()
      .then(setTopics)
      .catch((e) => setError(String(e)));
  }, []);

  const effectiveTopics = useMemo(() => {
    const arr = Array.from(selected);
    const extra = customTopic.trim();
    if (extra) arr.push(extra);
    return arr;
  }, [selected, customTopic]);

  function toggle(label: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  async function launch() {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResp(null);
    try {
      const r = await postChat(question.trim(), effectiveTopics);
      setResp(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-10">
        <h1 className="text-4xl font-semibold tracking-tight">
          Nauda Palisse — Veille Tech
        </h1>
        <p className="mt-2 text-sm text-neutral-400">
          Assistant interne pour suivre les tendances et les outils de l'écosystème.
        </p>
        <a
          href="#comment-ca-marche"
          className="mt-3 inline-block text-xs text-indigo-300 underline-offset-4 hover:underline"
        >
          ↓ Comment ça marche ?
        </a>
      </header>

      <section className="space-y-5 rounded-2xl border border-white/10 bg-white/5 p-6 backdrop-blur">
        <div>
          <div className="mb-2 text-xs uppercase tracking-wider text-neutral-400">
            Sujets populaires
          </div>
          <div className="flex flex-wrap gap-2">
            {topics.map((t) => {
              const active = selected.has(t.label);
              return (
                <button
                  key={t.slug}
                  type="button"
                  onClick={() => toggle(t.label)}
                  className={`rounded-full border px-3 py-1 text-sm transition ${
                    active
                      ? "border-indigo-400 bg-indigo-500/30 text-white"
                      : "border-white/10 bg-white/5 text-neutral-300 hover:bg-white/10"
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <label className="mb-2 block text-xs uppercase tracking-wider text-neutral-400">
            Ou tapez un sujet
          </label>
          <input
            type="text"
            value={customTopic}
            onChange={(e) => setCustomTopic(e.target.value)}
            placeholder="ex : Rust, edge computing, vector DB…"
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
        </div>

        <div>
          <label className="mb-2 block text-xs uppercase tracking-wider text-neutral-400">
            Question
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="text-xs text-neutral-500">
            {effectiveTopics.length > 0
              ? `Filtres actifs : ${effectiveTopics.join(", ")}`
              : "Aucun filtre — toute la base sera interrogée."}
          </div>
          <button
            type="button"
            onClick={launch}
            disabled={loading || !question.trim()}
            className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Recherche en cours…" : "Lancer la veille"}
          </button>
        </div>
      </section>

      <section className="mt-10">
        {error && (
          <div className="rounded-lg border border-rose-400/40 bg-rose-500/10 p-4 text-sm text-rose-200">
            Erreur : {error}
          </div>
        )}

        {!error && resp && (
          <>
            <div className="mb-6 rounded-2xl border border-white/10 bg-white/5 p-5">
              <div className="text-xs uppercase tracking-wider text-neutral-400">
                Synthèse
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm text-neutral-100">
                {resp.answer}
              </p>
              {resp.status !== "ok" && (
                <p className="mt-2 text-xs text-neutral-500">
                  statut : {resp.status}
                </p>
              )}
            </div>

            {resp.trending.length > 0 && (
              <div className="mb-6 rounded-xl border border-amber-400/30 bg-amber-500/10 p-4">
                <div className="text-xs uppercase tracking-wider text-amber-300">
                  📈 Tendances (3+ articles)
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {resp.trending.map((tag) => (
                    <span
                      key={tag}
                      className={`rounded-full border px-3 py-1 text-sm font-medium ${tagColor(tag)}`}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {resp.cards.length === 0 ? (
              <div className="rounded-lg border border-white/10 bg-white/5 p-6 text-center text-sm text-neutral-400">
                Aucun résultat pour le moment.
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {resp.cards.map((card, i) => (
                  <Card key={i} card={card} />
                ))}
              </div>
            )}
          </>
        )}

        {!error && !resp && !loading && (
          <div className="rounded-lg border border-dashed border-white/10 bg-white/5 p-10 text-center text-sm text-neutral-500">
            Choisissez un sujet, posez une question, lancez la veille.
          </div>
        )}
      </section>

      <HowItWorks />
    </main>
  );
}

function Card({ card }: { card: ArticleCard }) {
  return (
    <article className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/5 p-4 shadow-sm transition hover:bg-white/10">
      <header>
        <h3 className="line-clamp-2 text-base font-semibold leading-snug">
          {card.title}
        </h3>
        <div className="mt-1 text-xs text-neutral-400">
          {card.source}
          {card.date && ` · ${new Date(card.date).toLocaleDateString("fr-FR")}`}
        </div>
      </header>
      <p
        className="text-sm text-neutral-300"
        style={{
          display: "-webkit-box",
          WebkitLineClamp: 3,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {card.snippet}
      </p>
      {card.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {card.tags.map((t) => (
            <span
              key={t}
              className={`rounded-full border px-2 py-0.5 text-[11px] ${tagColor(t)}`}
            >
              {t}
            </span>
          ))}
        </div>
      )}
      {card.url && (
        <a
          href={card.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-auto inline-flex w-fit items-center gap-1 rounded-md border border-indigo-400/50 px-3 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-500/20"
        >
          Lire l'article →
        </a>
      )}
    </article>
  );
}

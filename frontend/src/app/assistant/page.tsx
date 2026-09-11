"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Brain, Loader2, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { aiApi, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { AssistantResponse } from "@/lib/types";
import { formatPrice } from "@/lib/format";

type ChatMessage = { role: "user" | "assistant"; content: string; response?: AssistantResponse };

const SUGGESTIONS = [
  "Find a 2BHK in Hyderabad under 70 lakh near metro",
  "Show a family-friendly apartment in Bangalore under 1 crore",
  "Find an investment property with good rental potential",
];

export default function AssistantPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number>();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!isAuthenticated) return;
    const prompt = new URLSearchParams(window.location.search).get("prompt")?.trim()
      || sessionStorage.getItem("assistant_draft")?.trim();
    if (prompt) {
      queueMicrotask(() => setText(prompt));
      sessionStorage.removeItem("assistant_draft");
    }
  }, [isAuthenticated]);

  const send = async (event?: FormEvent, suggestion?: string) => {
    event?.preventDefault();
    const message = (suggestion ?? text).trim();
    if (!message || sending) return;
    setMessages((current) => [...current, { role: "user", content: message }]);
    setText("");
    setError(undefined);
    setSending(true);
    try {
      const response = await aiApi.assistant({ message, conversation_id: conversationId });
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, { role: "assistant", content: response.answer, response }]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The assistant could not complete that request. Please try again.");
    } finally {
      setSending(false);
    }
  };

  if (isLoading) return <div className="flex justify-center py-24"><Loader2 className="animate-spin" /></div>;
  if (!isAuthenticated) return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center">
      <Brain className="mx-auto mb-4 size-12 text-primary" />
      <h1 className="text-2xl font-bold">Sign in to use your property assistant</h1>
      <p className="mt-2 text-muted-foreground">Conversations are private and saved to your account.</p>
      <Link href="/auth/login?next=%2Fassistant"><Button className="mt-6 gradient-primary text-white">Sign in</Button></Link>
    </div>
  );

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-2xl gradient-primary text-white"><Sparkles className="size-6" /></div>
        <h1 className="text-3xl font-bold tracking-tight">Property decision assistant</h1>
        <p className="mt-2 text-muted-foreground">Search real listings conversationally. Every recommendation is grounded in platform data.</p>
      </div>
      <Card className="min-h-[480px] border-border/60 p-4 sm:p-6">
        {messages.length === 0 ? (
          <div className="flex min-h-[350px] flex-col items-center justify-center text-center">
            <Brain className="mb-4 size-10 text-primary/60" />
            <p className="font-medium">What kind of property are you looking for?</p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((suggestion) => <Button key={suggestion} variant="outline" size="sm" onClick={() => send(undefined, suggestion)}>{suggestion}</Button>)}
            </div>
          </div>
        ) : <div className="space-y-5">
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={message.role === "user" ? "ml-auto max-w-[80%]" : "max-w-[90%]"}>
              <div className={message.role === "user" ? "rounded-2xl rounded-br-md bg-primary px-4 py-3 text-primary-foreground" : "rounded-2xl rounded-bl-md bg-muted px-4 py-3 whitespace-pre-line text-sm leading-relaxed"}>{message.content}</div>
              {message.response?.results.length ? <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {message.response.results.slice(0, 3).map((property) => <Link key={property.property_id} href={`/properties/${property.property_id}`} className="rounded-xl border border-border/60 bg-background p-3 transition-colors hover:border-primary/50">
                  <p className="text-xs font-semibold line-clamp-2">{property.title}</p>
                  <p className="mt-1 text-sm font-bold text-primary">{formatPrice(property.price)}</p>
                  <p className="text-xs text-muted-foreground">{property.overall_score}% match · {property.locality || property.city}</p>
                  {property.positive_factors[0] ? <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">Why: {property.positive_factors[0]}</p> : null}
                </Link>)}
              </div> : null}
              {message.response?.citations.length ? <p className="mt-2 text-xs text-muted-foreground">Verified platform records: {message.response.citations.map((citation) => citation.label).join(" · ")}</p> : null}
            </div>
          ))}
        </div>}
        {sending && <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />Searching verified listings and checking location context…</div>}
        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
        <form onSubmit={(event) => send(event)} className="mt-6 flex gap-2 border-t pt-4">
          <Input value={text} onChange={(event) => setText(event.target.value)} placeholder="Ask for a property, budget, or location…" disabled={sending} />
          <Button type="submit" disabled={!text.trim() || sending} className="gradient-primary text-white"><Send className="size-4" /></Button>
        </form>
      </Card>
    </div>
  );
}

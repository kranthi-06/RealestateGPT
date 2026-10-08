"use client";

import { FormEvent, useEffect, useState, useRef } from "react";
import Link from "next/link";
import { Brain, Loader2, Send, Sparkles, Search, Home, TrendingUp, GitCompare, AlertCircle, MessageSquare, Bot, Zap, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { aiApi, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { AssistantResponse } from "@/lib/types";
import { formatPrice } from "@/lib/format";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  response?: AssistantResponse;
  toolCalls?: string[];
};

const QUICK_ACTIONS = [
  { label: "Find 2BHK under ₹70L", prompt: "Find a 2BHK in Hyderabad under 70 lakh near metro", icon: Home },
  { label: "Family home near metro", prompt: "Show a family-friendly apartment in Bangalore under 1 crore near good schools", icon: Search },
  { label: "Investment rental yield", prompt: "Find an investment property with good rental potential and appreciation", icon: TrendingUp },
  { label: "Compare areas", prompt: "Compare Whitefield vs Koramangala for a 3BHK purchase", icon: GitCompare },
  { label: "Explain price trends", prompt: "Why are prices rising in Gachibowli?", icon: AlertCircle },
];

function ToolCallBadge({ tool }: { tool: string }) {
  const icons: Record<string, React.ComponentType<{ className?: string }>> = {
    search_properties: Search,
    get_price_intelligence: TrendingUp,
    get_nearby: MapPin,
    compare_properties: GitCompare,
    get_area_intelligence: Brain,
    calculate_affordability: Zap,
  };
  const Icon = icons[tool] || MessageSquare;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-full border border-slate-200">
      <Icon className="h-3 w-3" />
      {tool.replace(/_/g, " ")}
    </span>
  );
}

export default function AssistantPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number>();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    scrollAreaRef.current?.scrollTo({ top: scrollAreaRef.current.scrollHeight, behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const prompt = new URLSearchParams(window.location.search).get("prompt")?.trim()
      || sessionStorage.getItem("assistant_draft")?.trim();
    if (prompt) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setText(prompt);
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
      const toolCalls = response.tool_calls?.map((tc) => tc.tool) || [];
      setMessages((current) => [...current, { role: "assistant", content: response.answer, response, toolCalls }]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The assistant could not complete that request. Please try again.");
    } finally {
      setSending(false);
    }
  };

  if (isLoading) return (
    <div className="mx-auto max-w-4xl px-4 py-24">
      <div className="flex justify-center items-center h-64">
        <div className="flex flex-col items-center gap-4">
          <Brain className="h-12 w-12 text-green-600 animate-pulse" />
          <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
          <p className="text-slate-500">Initializing your property assistant…</p>
        </div>
      </div>
    </div>
  );

  if (!isAuthenticated) return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center">
      <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-green-100 text-green-600">
        <Brain className="size-7" />
      </div>
      <h1 className="text-2xl font-bold text-slate-900">Sign in to use your property assistant</h1>
      <p className="mt-2 text-slate-500">Conversations are private and saved to your account.</p>
      <Link href="/auth/login?next=%2Fassistant">
        <Button className="mt-6 bg-green-600 hover:bg-green-700 text-white">
          <MessageSquare className="mr-2 h-4 w-4" /> Sign in
        </Button>
      </Link>
    </div>
  );

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8">
        <div className="flex items-center justify-center gap-3 mb-4">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-green-100 text-green-600">
            <Sparkles className="size-6" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Property decision assistant</h1>
            <p className="mt-1 text-slate-600">Search real listings conversationally. Every recommendation is grounded in platform data.</p>
          </div>
        </div>

        <div className="flex flex-wrap justify-center gap-2">
          {QUICK_ACTIONS.map((action) => (
            <Button
              key={action.label}
              variant="outline"
              size="sm"
              onClick={() => send(undefined, action.prompt)}
              disabled={sending}
              className="gap-1.5"
            >
              <action.icon className="h-3.5 w-3.5" />
              {action.label}
            </Button>
          ))}
        </div>
      </div>

      <Card className="h-[calc(100vh-300px)] min-h-[500px] max-h-[700px] border-border/60 flex flex-col">
        <ScrollArea className="flex-1 overflow-y-auto" ref={scrollAreaRef}>
          <div className="p-4 sm:p-6 space-y-6">
            {messages.length === 0 ? (
              <div className="flex min-h-[300px] flex-col items-center justify-center text-center">
                <Brain className="mb-4 size-10 text-green-600/60" />
                <p className="font-medium text-slate-900">What kind of property are you looking for?</p>
                <p className="mt-1 text-sm text-slate-500">Try one of the quick actions above or type your own question.</p>
              </div>
            ) : (
              <div className="space-y-6">
                {messages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[85%] ${message.role === "user" ? "" : ""}`}>
                      <div className={`rounded-2xl px-4 py-3 ${
                        message.role === "user"
                          ? "rounded-br-md bg-green-600 text-white"
                          : "rounded-bl-md bg-slate-50 border border-slate-200 text-slate-900"
                      } whitespace-pre-line text-sm leading-relaxed`}>
                        {message.content}
                      </div>

                      {message.toolCalls && message.toolCalls.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {message.toolCalls.map((tool) => (
                            <ToolCallBadge key={tool} tool={tool} />
                          ))}
                        </div>
                      )}

                      {message.response?.results && message.response.results.length > 0 && (
                        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                          {message.response.results.slice(0, 3).map((property) => (
                            <Link
                              key={property.property_id}
                              href={`/properties/${property.property_id}`}
                              className="rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-green-300 hover:shadow-sm"
                            >
                              <p className="text-xs font-semibold line-clamp-2 text-slate-900">{property.title}</p>
                              <p className="mt-1 text-sm font-bold text-green-600">{formatPrice(property.price)}</p>
                              <p className="text-xs text-slate-500">{property.overall_score}% match · {property.locality || property.city}</p>
                              {property.positive_factors[0] && (
                                <p className="mt-1 text-xs text-green-700">Why: {property.positive_factors[0]}</p>
                              )}
                            </Link>
                          ))}
                        </div>
                      )}

                      {message.response?.citations && message.response.citations.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {message.response.citations.map((citation, i) => (
                            <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-blue-50 text-blue-700 rounded-full border border-blue-100">
                              <Bot className="h-3 w-3" />
                              {citation.label}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        <div className="border-t border-slate-200 bg-white p-4">
          {sending && (
            <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="size-4 animate-spin text-green-600" />
              <span>Searching verified listings and analyzing location context…</span>
            </div>
          )}
          {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
          <form onSubmit={(event) => send(event)} className="flex gap-2">
            <Input
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Ask for a property, budget, location, or comparison…"
              disabled={sending}
              className="flex-1"
              autoFocus
            />
            <Button type="submit" disabled={!text.trim() || sending} className="bg-green-600 hover:bg-green-700 text-white">
              <Send className="size-4" />
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}

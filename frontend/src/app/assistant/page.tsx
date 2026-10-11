"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Calculator,
  Globe,
  Heart,
  Home,
  Loader2,
  MapPin,
  MessageSquare,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { aiApi, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { AssistantResponse, ScoredProperty } from "@/lib/types";
import { formatPrice } from "@/lib/format";
import { PropertyActions } from "@/components/property-actions";
import { cn } from "@/lib/utils";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  response?: AssistantResponse;
  toolCalls?: string[];
  createdAt: string;
};

const QUICK_ACTIONS = [
  {
    label: "Say Hello",
    prompt: "Hii",
    icon: Sparkles,
  },
  {
    label: "Explain home loans",
    prompt: "Explain home loans.",
    icon: Home,
  },
  {
    label: "What is rental yield?",
    prompt: "What is rental yield?",
    icon: TrendingUp,
  },
  {
    label: "Hyderabad location advice",
    prompt: "What is a good location to buy a house in Hyderabad?",
    icon: MapPin,
  },
  {
    label: "Can I afford ₹60 lakh?",
    prompt: "Can I afford a house worth ₹60 lakh?",
    icon: Calculator,
  },
  {
    label: "Rent in Nandyal",
    prompt: "Find two bedroom houses for rent in Nandyal",
    icon: Search,
  },
];

const TOOL_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  search_properties: Search,
  search_web_properties: Globe,
  get_property: Search,
  get_price_intelligence: TrendingUp,
  get_market_stats: TrendingUp,
  nearby_places: MapPin,
  find_nearby_places_by_location: MapPin,
  get_area_intelligence: Sparkles,
  calculate_affordability: Calculator,
  calculate_emi: Calculator,
  calculate_route: MapPin,
  save_property: Heart,
  unsave_property: Heart,
  list_saved_properties: Heart,
};

const TOOL_LABELS: Record<string, string> = {
  search_properties: "Catalog search",
  search_web_properties: "Web research",
  get_property: "Property details",
  get_price_intelligence: "Price intelligence",
  get_market_stats: "Market data",
  nearby_places: "Near property",
  find_nearby_places_by_location: "Local amenities",
  get_area_intelligence: "Area intelligence",
  calculate_affordability: "Affordability calculator",
  calculate_emi: "EMI calculator",
  calculate_route: "Route calculation",
  save_property: "Saved property",
  unsave_property: "Updated saved list",
  list_saved_properties: "Saved properties",
};

function ToolCallBadge({ tool }: { tool: string }) {
  const Icon = TOOL_ICONS[tool] || MessageSquare;
  const label = TOOL_LABELS[tool] ?? tool.replace(/_/g, " ");
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

/** A real catalogue property the assistant retrieved, with its own actions. */
function RecommendationCard({ property }: { property: ScoredProperty }) {
  const image = property.image_urls?.split(",").map((value) => value.trim()).find(Boolean);
  return (
    <article className="overflow-hidden rounded-2xl border border-emerald-950/10 bg-white shadow-[0_10px_25px_rgb(21_60_49_/_0.08)] transition hover:-translate-y-0.5 hover:shadow-[0_16px_30px_rgb(21_60_49_/_0.13)]">
      {image && (
        <Link href={`/properties/${property.property_id}`} className="block h-24 overflow-hidden bg-emerald-50">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={image} alt="" className="h-full w-full object-cover" loading="lazy" />
        </Link>
      )}
      <div className="p-3">
        <Link href={`/properties/${property.property_id}`} className="block">
          <p className="line-clamp-2 text-xs font-semibold text-slate-900 hover:text-green-700">{property.title}</p>
          <p className="mt-1 font-serif text-base font-bold text-emerald-800">{formatPrice(property.price)}</p>
          <p className="text-xs text-slate-500">
            {property.locality || property.city}
            {property.bedrooms != null && ` · ${property.bedrooms} BHK`}
            {property.area_sqft != null && ` · ${property.area_sqft} sq ft`}
          </p>
        </Link>
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="rounded-full bg-green-50 px-2 py-0.5 text-[11px] font-medium text-green-700">
            {Math.round(property.overall_score)}% match
          </span>
          <div className="flex items-center gap-1">
            <Link
              href={`/properties/${property.property_id}`}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              Details
              <ArrowRight className="h-3 w-3" />
            </Link>
            <PropertyActions
              propertyId={property.property_id}
              title={property.title}
              variant="compact"
            />
          </div>
        </div>
      </div>
    </article>
  );
}

export default function AssistantPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  /** The last user message, so a retry after a failure re-sends it. */
  const lastFailedMessage = useRef<string | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    scrollAreaRef.current?.scrollTo({ top: scrollAreaRef.current.scrollHeight, behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, scrollToBottom]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const params = new URLSearchParams(window.location.search);
    const prompt =
      params.get("prompt")?.trim() || sessionStorage.getItem("assistant_draft")?.trim();
    if (prompt) {
      const id = window.setTimeout(() => setText(prompt), 0);
      sessionStorage.removeItem("assistant_draft");
      return () => window.clearTimeout(id);
    }
  }, [isAuthenticated]);

  const send = useCallback(
    async (event?: FormEvent, suggestion?: string) => {
      event?.preventDefault();
      const message = (suggestion ?? text).trim();
      if (!message || sending) return;

      lastFailedMessage.current = message;
      setMessages((current) => [
        ...current,
        { role: "user", content: message, createdAt: new Date().toISOString() },
      ]);
      setText("");
      setError(undefined);
      setSending(true);
      try {
        const contextualPropertyId = typeof window === "undefined"
          ? undefined
          : Number(new URLSearchParams(window.location.search).get("property_id")) || undefined;
        const response = await aiApi.assistant({ message, conversation_id: conversationId, property_id: contextualPropertyId });
        if (!response.answer?.trim()) throw new ApiError("The assistant returned an empty response. Please retry.", 502);
        setConversationId(response.conversation_id);
        const toolCalls = response.tool_calls?.map((tc) => tc.tool) || [];
        setMessages((current) => [
          ...current,
          { role: "assistant", content: response.answer, response, toolCalls, createdAt: new Date().toISOString() },
        ]);
        lastFailedMessage.current = null;
        setError(undefined);
      } catch (caught) {
        const message_ =
          caught instanceof ApiError
            ? caught.status === 429
              ? "The assistant is currently busy. Please wait a moment and try again."
              : caught.status === 503
                ? "All AI providers are temporarily unavailable. Please try again in a few moments."
                : caught.message || "The assistant could not complete that request."
            : "The assistant could not complete that request. Check your connection and try again.";
        setError(message_);
      } finally {
        setSending(false);
      }
    },
    [conversationId, sending, text]
  );

  const retry = useCallback(() => {
    const message = lastFailedMessage.current;
    if (!message) return;
    void send(undefined, message);
  }, [send]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-24">
        <div className="flex h-64 flex-col items-center justify-center gap-4">
          <Sparkles className="h-10 w-10 animate-pulse text-green-600" />
          <p className="text-slate-500">Initializing your property assistant…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <div className="mx-auto mb-6 flex size-14 items-center justify-center rounded-2xl bg-emerald-950 text-[#d7e9bd] shadow-lg shadow-emerald-950/15">
          <Sparkles className="size-7" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Sign in to use your property assistant</h1>
        <p className="mt-2 text-sm text-slate-500">
          Save your conversations, search real listings conversationally, and get personalized property guidance.
        </p>
        <Link href="/auth/login?next=%2Fassistant">
          <Button className="mt-6 w-full bg-green-600 hover:bg-green-700">
            Sign In to Continue
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        <div className="mb-4 flex items-center justify-center gap-3">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-emerald-950 text-[#d7e9bd] shadow-lg shadow-emerald-950/15">
            <Sparkles className="size-6" />
          </div>
          <div>
            <p className="app-kicker">Conversational Real Estate Intelligence</p>
            <h1 className="app-page-title mt-1 text-3xl">RealEstateGPT Assistant</h1>
            <p className="mt-1 text-slate-600">
              Conversational guidance for property buying, renting, mortgages, affordability, and market insights.
            </p>
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

      <Card className="flex h-[calc(100vh-318px)] max-h-[720px] min-h-[520px] flex-col overflow-hidden border-emerald-950/10 bg-[#fffefa] shadow-[0_18px_50px_rgb(21_60_49_/_0.09)]">
        <ScrollArea className="flex-1 overflow-y-auto" ref={scrollAreaRef}>
          <div className="space-y-6 p-4 sm:p-6">
            {messages.length === 0 ? (
              <div className="flex min-h-[300px] flex-col items-center justify-center text-center">
                <Sparkles className="mb-4 size-10 text-emerald-600" />
                <p className="text-base font-semibold text-slate-900">
                  How can I help with your real estate journey today?
                </p>
                <p className="mt-1 max-w-md text-sm text-slate-500">
                  Ask anything about buying or renting, home loans, EMI calculations, rental yield, or locality comparisons.
                </p>
              </div>
            ) : (
              messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={cn(
                    "flex",
                    message.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  <div className="max-w-[85%]">
                    <div
                      className={cn(
                        "whitespace-pre-line rounded-2xl px-4 py-3 text-sm leading-relaxed",
                        message.role === "user"
                          ? "rounded-br-md bg-green-600 text-white shadow-sm"
                          : "rounded-bl-md border border-slate-200/80 bg-white text-slate-900 shadow-sm"
                      )}
                    >
                      {message.content}
                    </div>
                    <p className={cn("mt-1.5 text-[10px] uppercase tracking-[.12em] text-slate-400", message.role === "user" && "text-right")}>
                      {message.role === "assistant" ? "RealEstateGPT · " : ""}{new Date(message.createdAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                    </p>

                    {message.toolCalls && message.toolCalls.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {message.toolCalls.map((tool) => (
                          <ToolCallBadge key={tool} tool={tool} />
                        ))}
                      </div>
                    )}

                    {message.response?.warnings && message.response.warnings.length > 0 && (
                      <div className="mt-2 rounded-lg border border-amber-200/70 bg-amber-50/60 px-3 py-2 text-xs text-amber-900">
                        {message.response.warnings.map((warning, i) => (
                          <p key={i} className="flex items-start gap-1.5">
                            <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" />
                            {warning}
                          </p>
                        ))}
                      </div>
                    )}

                    {message.response?.results && message.response.results.length > 0 && (
                      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        {message.response.results.slice(0, 6).map((property) => (
                          <RecommendationCard key={property.property_id} property={property} />
                        ))}
                      </div>
                    )}

                    {message.response?.citations && message.response.citations.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {message.response.citations.map((citation, i) => {
                          const citationContent = <><Bot className="h-3 w-3" />{citation.label}</>;
                          return citation.url ? (
                            <a
                              href={citation.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              key={i}
                              className="inline-flex items-center gap-1 rounded-full border border-blue-100 bg-blue-50 px-2 py-0.5 text-xs text-blue-700 hover:underline"
                            >
                              {citationContent}
                            </a>
                          ) : (
                            <span key={i} className="inline-flex items-center gap-1 rounded-full border border-blue-100 bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                              {citationContent}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        <div className="border-t border-emerald-950/10 bg-white/85 p-4 backdrop-blur">
          {sending && (
            <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="size-4 animate-spin text-green-600" />
              <span>RealEstateGPT is thinking…</span>
            </div>
          )}
          {error && !sending && (
            <div role="alert" className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              <div className="flex items-center gap-2">
                <AlertCircle className="size-4 shrink-0 text-red-600" />
                <span>{error}</span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={retry}
                className="h-8 gap-1.5 border-red-200 bg-white text-xs font-medium text-red-700 hover:bg-red-50"
              >
                <RefreshCw className="size-3.5" />
                Retry
              </Button>
            </div>
          )}
          <form onSubmit={(event) => send(event)} className="flex gap-2">
            <Input
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Ask about a property, budget, location, market, or EMI…"
              disabled={sending}
              className="flex-1"
              aria-label="Message the property assistant"
              autoFocus
            />
            <Button
              type="submit"
              disabled={!text.trim() || sending}
              className="bg-green-600 text-white hover:bg-green-700"
              aria-label="Send message"
            >
              <Send className="size-4" />
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}

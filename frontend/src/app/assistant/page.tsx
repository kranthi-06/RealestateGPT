"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Brain,
  Calculator,
  GitCompare,
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
  /** True when the request failed and the user can retry this message. */
  failed?: boolean;
};

const QUICK_ACTIONS = [
  {
    label: "2BHK for rent in Nandyal",
    prompt: "Find two-bedroom houses for rent in Nandyal",
    icon: Home,
  },
  {
    label: "Compare prices in Hyderabad",
    prompt: "Compare apartment prices in Hyderabad",
    icon: GitCompare,
  },
  {
    label: "EMI for ₹40 lakh",
    prompt: "What is the estimated EMI for a ₹40 lakh property?",
    icon: TrendingUp,
  },
  {
    label: "Hospitals & schools near me",
    prompt: "Find hospitals and schools near this location",
    icon: MapPin,
  },
  {
    label: "Websites listing here",
    prompt: "Show real-estate websites listing properties in this area",
    icon: Globe,
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
  compare_properties: GitCompare,
  get_area_intelligence: Brain,
  calculate_affordability: Calculator,
  calculate_emi: Calculator,
  calculate_route: MapPin,
  save_property: Heart,
  unsave_property: Heart,
  list_saved_properties: Heart,
};

const TOOL_LABELS: Record<string, string> = {
  search_properties: "Verified listings",
  search_web_properties: "Web discovery",
  get_property: "Property details",
  get_price_intelligence: "Price intelligence",
  get_market_stats: "Market data",
  nearby_places: "Near a property",
  find_nearby_places_by_location: "Near this location",
  compare_properties: "Comparison",
  get_area_intelligence: "Area intelligence",
  calculate_affordability: "Affordability",
  calculate_emi: "EMI",
  calculate_route: "Route",
  save_property: "Saved for you",
  unsave_property: "Updated saved list",
  list_saved_properties: "Your saved list",
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
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-green-300 hover:shadow-sm">
      <Link href={`/properties/${property.property_id}`} className="block">
        <p className="line-clamp-2 text-xs font-semibold text-slate-900 hover:text-green-700">
          {property.title}
        </p>
        <p className="mt-1 text-sm font-bold text-green-600">{formatPrice(property.price)}</p>
        <p className="text-xs text-slate-500">
          {property.locality || property.city}
          {property.bedrooms != null && ` · ${property.bedrooms} BHK`}
          {property.area_sqft != null && ` · ${property.area_sqft} sq ft`}
        </p>
      </Link>
      <div className="mt-2 flex items-center justify-between gap-2">
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
        ...current.filter((m) => !m.failed),
        { role: "user", content: message },
      ]);
      setText("");
      setError(undefined);
      setSending(true);
      try {
        const response = await aiApi.assistant({ message, conversation_id: conversationId });
        setConversationId(response.conversation_id);
        const toolCalls = response.tool_calls?.map((tc) => tc.tool) || [];
        setMessages((current) => [
          ...current,
          { role: "assistant", content: response.answer, response, toolCalls },
        ]);
        lastFailedMessage.current = null;
      } catch (caught) {
        const message_ =
          caught instanceof ApiError
            ? caught.status === 429
              ? "The assistant is busy right now. Please wait a moment and try again."
              : caught.message || "The assistant could not complete that request."
            : "The assistant could not complete that request. Check your connection and try again.";
        setError(message_);
        // Keep the failed turn visible so the user can retry it in place.
        setMessages((current) => [
          ...current,
          { role: "assistant", content: message_, failed: true },
        ]);
      } finally {
        setSending(false);
      }
    },
    [conversationId, sending, text]
  );

  const retry = useCallback(() => {
    const message = lastFailedMessage.current;
    if (!message) return;
    setMessages((current) => current.slice(0, -1));
    void send(undefined, message);
  }, [send]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-24">
        <div className="flex h-64 flex-col items-center justify-center gap-4">
          <Brain className="h-12 w-12 animate-pulse text-green-600" />
          <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
          <p className="text-slate-500">Initializing your property assistant…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="mx-auto max-w-xl px-4 py-24 text-center">
        <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-green-100 text-green-600">
          <Brain className="size-7" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Sign in to use your property assistant</h1>
        <p className="mt-2 text-slate-500">
          Conversations are private and saved to your account.
        </p>
        <Link href="/auth/login?next=%2Fassistant">
          <Button className="mt-6 bg-green-600 text-white hover:bg-green-700">
            <MessageSquare className="mr-2 h-4 w-4" />
            Sign in
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8">
        <div className="mb-4 flex items-center justify-center gap-3">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-green-100 text-green-600">
            <Sparkles className="size-6" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Property decision assistant</h1>
            <p className="mt-1 text-slate-600">
              Search real listings conversationally. Every recommendation is grounded in platform data.
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

      <Card className="flex h-[calc(100vh-300px)] max-h-[700px] min-h-[500px] flex-col border-border/60">
        <ScrollArea className="flex-1 overflow-y-auto" ref={scrollAreaRef}>
          <div className="space-y-6 p-4 sm:p-6">
            {messages.length === 0 ? (
              <div className="flex min-h-[300px] flex-col items-center justify-center text-center">
                <Brain className="mb-4 size-10 text-green-600/60" />
                <p className="font-medium text-slate-900">
                  What kind of property are you looking for?
                </p>
                <p className="mt-1 max-w-sm text-sm text-slate-500">
                  Ask for listings, a price comparison, or a financing question. Answers come from
                  the stored catalogue, and the assistant says so when nothing matches.
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
                          ? "rounded-br-md bg-green-600 text-white"
                          : message.failed
                            ? "rounded-bl-md border border-red-200 bg-red-50 text-red-900"
                            : "rounded-bl-md border border-slate-200 bg-slate-50 text-slate-900"
                      )}
                    >
                      {message.content}
                    </div>

                    {message.failed && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={retry}
                        className="mt-2 h-8 gap-1.5"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Retry
                      </Button>
                    )}

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
                        {message.response.citations.map((citation, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center gap-1 rounded-full border border-blue-100 bg-blue-50 px-2 py-0.5 text-xs text-blue-700"
                          >
                            <Bot className="h-3 w-3" />
                            {citation.label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
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
          {error && !sending && (
            <p role="alert" className="mb-4 flex items-start gap-2 text-sm text-red-600">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              {error}
            </p>
          )}
          <form onSubmit={(event) => send(event)} className="flex gap-2">
            <Input
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Ask for a property, budget, location, or comparison…"
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

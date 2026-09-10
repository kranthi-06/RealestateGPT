"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Building2,
  Search,
  Heart,
  GitCompareArrows,
  User,
  LogOut,
  Menu,
  X,
  Sparkles,
  Shield,
} from "lucide-react";
import { useState } from "react";

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-[#dedbd1] bg-[#fbfaf7]/90 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-[4.5rem] items-center justify-between">
          {/* Logo */}
          <Link href="/" className="group flex items-center gap-2.5">
            <div className="flex size-9 items-center justify-center rounded-xl bg-[#1d3c31] shadow-sm transition-shadow group-hover:shadow-md">
              <Building2 className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold tracking-tight text-[#1d3028]">
              RealEstate<span className="text-[#6d8677]">GPT</span>
            </span>
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden items-center gap-1 md:flex">
            <Link href="/search">
              <Button variant="ghost" size="sm" className="text-[#5e6d64] hover:bg-[#edf2ed] hover:text-[#1d3c31]">
                Explore homes
              </Button>
            </Link>
            <Link href="/#how-it-works"><Button variant="ghost" size="sm" className="text-[#5e6d64] hover:bg-[#edf2ed] hover:text-[#1d3c31]">How it works</Button></Link>
            {isAuthenticated && (
              <Link href="/assistant">
                <Button variant="ghost" size="sm" className="gap-2 text-[#5e6d64] hover:bg-[#edf2ed] hover:text-[#1d3c31]">
                  <Sparkles className="w-4 h-4" /> AI Assistant
                </Button>
              </Link>
            )}
            {isAuthenticated && (
              <>
                <Link href="/saved">
                  <Button variant="ghost" size="sm" className="gap-2 text-[#5e6d64] hover:bg-[#edf2ed] hover:text-[#1d3c31]">
                    <Heart className="w-4 h-4" />
                    Saved
                  </Button>
                </Link>
                <Link href="/compare">
                  <Button variant="ghost" size="sm" className="gap-2 text-[#5e6d64] hover:bg-[#edf2ed] hover:text-[#1d3c31]">
                    <GitCompareArrows className="w-4 h-4" />
                    Compare
                  </Button>
                </Link>
              </>
            )}
          </nav>

          {/* Auth / User */}
          <div className="hidden md:flex items-center gap-3">
            {isAuthenticated ? (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button variant="outline" size="sm" className="gap-2" />
                  }
                >
                  <div className="w-6 h-6 rounded-full gradient-primary flex items-center justify-center">
                    <span className="text-xs text-white font-semibold">
                      {user?.full_name?.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  {user?.full_name?.split(" ")[0]}
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <div className="px-2 py-1.5 text-xs text-muted-foreground">
                    {user?.email}
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem render={<Link href="/saved" className="w-full" />}>
                    <Heart className="w-4 h-4 mr-2" />
                    Saved Properties
                  </DropdownMenuItem>
                  <DropdownMenuItem render={<Link href="/searches" className="w-full" />}>
                    <Search className="w-4 h-4 mr-2" />
                    Saved Searches
                  </DropdownMenuItem>
                  <DropdownMenuItem render={<Link href="/compare" className="w-full" />}>
                    <GitCompareArrows className="w-4 h-4 mr-2" />
                    Comparisons
                  </DropdownMenuItem>
                  <DropdownMenuItem render={<Link href="/assistant" className="w-full" />}>
                    <Sparkles className="w-4 h-4 mr-2" />
                    AI Assistant
                  </DropdownMenuItem>
                  <DropdownMenuItem render={<Link href="/profile" className="w-full" />}>
                    <User className="w-4 h-4 mr-2" />
                    Profile & Settings
                  </DropdownMenuItem>
                  {user?.role === "admin" && (
                    <DropdownMenuItem render={<Link href="/admin" className="w-full" />}>
                      <Shield className="w-4 h-4 mr-2" />
                      Admin Dashboard
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={logout}
                    className="text-destructive cursor-pointer"
                  >
                    <LogOut className="w-4 h-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <div className="flex items-center gap-2">
                <Link href="/auth/login">
                  <Button variant="ghost" size="sm" className="text-[#385247] hover:bg-[#edf2ed]">
                    Sign In
                  </Button>
                </Link>
                <Link href="/auth/register">
                  <Button size="sm" className="rounded-xl bg-[#1d3c31] text-white hover:bg-[#284f41]">
                    Get Started
                  </Button>
                </Link>
              </div>
            )}
          </div>

          {/* Mobile menu toggle */}
          <button
            className="md:hidden p-2"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Mobile Nav */}
        {mobileOpen && (
          <div className="md:hidden pb-4 border-t border-border/50 mt-2 pt-4 space-y-2">
            <Link
              href="/search"
              onClick={() => setMobileOpen(false)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent text-sm"
            >
              <Search className="w-4 h-4" /> Search Properties
            </Link>
            {isAuthenticated ? (
              <>
                <Link
                  href="/saved"
                  onClick={() => setMobileOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent text-sm"
                >
                  <Heart className="w-4 h-4" /> Saved
                </Link>
                <Link
                  href="/compare"
                  onClick={() => setMobileOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent text-sm"
                >
                  <GitCompareArrows className="w-4 h-4" /> Compare
                </Link>
                <Link href="/assistant" onClick={() => setMobileOpen(false)} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent text-sm">
                  <Sparkles className="w-4 h-4" /> AI Assistant
                </Link>
                <button
                  onClick={() => { logout(); setMobileOpen(false); }}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent text-sm text-destructive w-full text-left"
                >
                  <LogOut className="w-4 h-4" /> Logout
                </button>
              </>
            ) : (
              <div className="flex gap-2 px-3 pt-2">
                <Link href="/auth/login" className="flex-1">
                  <Button variant="outline" size="sm" className="w-full" onClick={() => setMobileOpen(false)}>
                    Sign In
                  </Button>
                </Link>
                <Link href="/auth/register" className="flex-1">
                  <Button size="sm" className="w-full gradient-primary text-white border-0" onClick={() => setMobileOpen(false)}>
                    Get Started
                  </Button>
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

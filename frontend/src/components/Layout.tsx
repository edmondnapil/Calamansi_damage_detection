import { BarChart3, ChevronDown, FileText, Home, Image as ImageIcon, Info, LogOut, Menu, Search, Settings, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import ErrorBoundary from "./ErrorBoundary";
import sprigPhoto from "../assets/calamansi-sprig.webp";
import { useAuth } from "../lib/auth";
import { LeafLogo } from "./ui";

export const FULL_TITLE = "Web-Based Calamansi Leaf Damage Detection Using Image Classification";

type NavItem = { to: string; label: string; icon: typeof Home; end?: boolean };

const NAV: NavItem[] = [
  { to: "/app", label: "Dashboard", icon: Home, end: true },
  { to: "/app/detect", label: "Detect Leaf", icon: ImageIcon },
  { to: "/app/logs", label: "Logs", icon: FileText },
  { to: "/app/reports", label: "Reports", icon: BarChart3 },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

const ADMIN_NAV: NavItem[] = [{ to: "/admin", label: "Admin dashboard", icon: ShieldCheck }];

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const items = user?.role === "admin" ? [...NAV, ...ADMIN_NAV] : NAV;
  return (
    <>
      <div
        className={`fixed inset-0 z-30 bg-forest-950/40 transition-opacity lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
      />
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col overflow-hidden bg-forest-900 text-white transition-transform lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-3 px-6 pb-8 pt-7">
          <LeafLogo size={42} />
          <div className="min-w-0">
            <p className="text-[17px] font-bold leading-tight">Calamansi Leaf Detection</p>
            <p className="text-xs text-white/60">Healthy vs. Damaged Classifier</p>
          </div>
          <button className="ml-auto p-1 text-white/70 lg:hidden" onClick={onClose} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>
        <nav className="relative z-10 flex flex-col gap-1.5 px-4" aria-label="Main">
          {items.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onClose}
              className={({ isActive }) =>
                `group relative flex items-center gap-3.5 rounded-xl px-4 py-3 text-[15px] font-medium transition ${
                  isActive ? "bg-forest-700 text-white" : "text-white/75 hover:bg-white/5 hover:text-white"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute left-0 top-2 bottom-2 w-1 rounded-r bg-leaf-500" />}
                  <Icon size={20} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mx-6 my-6 border-t border-white/10" />
        <img
          src={sprigPhoto}
          alt=""
          aria-hidden="true"
          className="pointer-events-none absolute -left-6 bottom-20 w-[80%] select-none opacity-25"
        />
        <div className="relative z-10 mt-auto flex items-start gap-3 px-6 pb-6">
          <LeafLogo size={30} />
          <p className="text-[11px] leading-snug text-white/70">
            <span className="font-semibold text-white/90">{FULL_TITLE}</span>
            <br />
            Transfer learning · FastAPI · Supabase
          </p>
        </div>
      </aside>
    </>
  );
}

function ProfileMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2.5 rounded-xl px-2 py-1.5 hover:bg-mint-100"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-forest-800 text-sm font-semibold text-white">
          {(user?.full_name || user?.email || "?").charAt(0).toUpperCase()}
        </span>
        <span className="hidden max-w-[160px] truncate text-sm font-semibold text-forest-950 sm:inline">{user?.full_name}</span>
        <ChevronDown size={16} className="text-slate-500" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-20 mt-2 w-60 origin-top-right animate-scale-in rounded-xl border border-leaf-100 bg-white p-1.5 shadow-lift">
          <div className="border-b border-leaf-100 px-3 pb-2 pt-1.5">
            <p className="truncate text-sm font-semibold text-forest-950">{user?.full_name}</p>
            <p className="truncate text-xs text-slate-500">{user?.email}</p>
            {user?.role === "admin" && (
              <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-forest-800 px-2 py-0.5 text-[11px] font-medium text-white">
                <ShieldCheck size={11} /> Administrator
              </span>
            )}
          </div>
          <Link role="menuitem" to="/app/settings" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-mint-50">
            <Settings size={15} /> Settings
          </Link>
          <Link role="menuitem" to="/app/settings#about" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-mint-50">
            <Info size={15} /> About the model
          </Link>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void signOut();
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50"
          >
            <LogOut size={15} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Header({ onMenu }: { onMenu: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/app/logs${q.trim() ? `?search=${encodeURIComponent(q.trim())}` : ""}`);
  };
  return (
    <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-leaf-100 bg-mint-50/95 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
      <button className="rounded-lg p-2 text-forest-800 hover:bg-mint-100 lg:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu size={22} />
      </button>
      <form onSubmit={submit} className="relative max-w-lg flex-1" role="search">
        <Search size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search logs by file name, result or model…"
          aria-label="Search detection logs"
          className="w-full rounded-xl border border-leaf-100 bg-white py-2.5 pl-10 pr-3 text-sm placeholder:text-slate-400 focus:border-leaf-500 focus:outline-none focus:ring-2 focus:ring-leaf-100"
        />
      </form>
      <div className="ml-auto">
        <ProfileMenu />
      </div>
    </header>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollTo(), and an effect
    // must return nothing or a cleanup function (React would call the Promise and crash).
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    <div className="min-h-screen bg-mint-50 font-sans text-forest-950">
      <Sidebar open={open} onClose={() => setOpen(false)} />
      <div className="lg:pl-[264px]">
        <Header onMenu={() => setOpen(true)} />
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
          <ErrorBoundary resetKey={pathname}>
            <div key={pathname} className="animate-page-in">
              <Outlet />
            </div>
          </ErrorBoundary>
        </main>
        <footer className="px-4 pb-6 text-center text-xs text-slate-500 sm:px-6 lg:px-8">
          {FULL_TITLE} · Predictions are limited to the model's learned Healthy and Damaged classes and are not a professional
          plant-health diagnosis.
        </footer>
      </div>
    </div>
  );
}

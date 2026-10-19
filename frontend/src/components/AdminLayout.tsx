import { Activity, ChevronDown, LayoutDashboard, LogOut, Menu, ScanLine, Search, Settings, ShieldCheck, Users, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import sprigPhoto from "../assets/calamansi-sprig.webp";
import { useAuth } from "../lib/auth";
import ErrorBoundary from "./ErrorBoundary";
import { FULL_TITLE } from "./Layout";
import { LeafLogo } from "./ui";

const NAV = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/activity", label: "Activity", icon: Activity },
  { to: "/admin/account", label: "Settings", icon: Settings },
];

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const link = ({ isActive }: { isActive: boolean }) =>
    `group relative flex items-center gap-3.5 rounded-xl px-4 py-3 text-[15px] font-medium transition-colors duration-200 ease-smooth ${
      isActive ? "bg-forest-700 text-white" : "text-white/75 hover:bg-white/5 hover:text-white"
    }`;
  return (
    <>
      <div
        className={`fixed inset-0 z-30 bg-forest-950/40 transition-opacity duration-250 ease-smooth lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
      />
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col overflow-hidden bg-forest-950 text-white transition-transform duration-250 ease-smooth lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Administrator navigation"
      >
        <div className="flex items-center gap-3 px-6 pb-6 pt-7">
          <LeafLogo size={42} />
          <div className="min-w-0">
            <p className="text-[17px] font-bold leading-tight">Admin Console</p>
            <p className="text-xs text-white/60">Calamansi Leaf Detection</p>
          </div>
          <button className="ml-auto p-1 text-white/70 lg:hidden" onClick={onClose} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>
        <nav className="relative z-10 flex flex-col gap-1.5 px-4">
          <p className="px-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-white/45">Administration</p>
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={onClose} className={link}>
              {({ isActive }) => (
                <>
                  <span className={`absolute bottom-2 left-0 top-2 w-1 rounded-r bg-leaf-500 transition-opacity duration-200 ${isActive ? "opacity-100" : "opacity-0"}`} />
                  <Icon size={20} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
          <p className="px-4 pb-1 pt-5 text-[11px] font-semibold uppercase tracking-wider text-white/45">Detection</p>
          <NavLink to="/app" onClick={onClose} className={link}>
            <ScanLine size={20} /> Detection app
          </NavLink>
        </nav>
        <img src={sprigPhoto} alt="" aria-hidden="true" className="pointer-events-none absolute -left-6 bottom-20 w-[80%] select-none opacity-[0.18]" />
        <div className="relative z-10 mt-auto flex items-start gap-3 px-6 pb-6">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-leaf-200" />
          <p className="text-[11px] leading-snug text-white/70">
            Administrator area. Every action is checked on the server and recorded in the activity log.
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
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, []);
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2.5 rounded-xl px-2 py-1.5 transition hover:bg-mint-100" aria-haspopup="menu" aria-expanded={open}>
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-forest-800 text-sm font-semibold text-white">
          {(user?.full_name || "A").charAt(0).toUpperCase()}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block max-w-[180px] truncate text-sm font-semibold leading-tight text-forest-950">{user?.full_name}</span>
          <span className="block text-[11px] leading-tight text-leaf-700">Administrator</span>
        </span>
        <ChevronDown size={16} className={`text-slate-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-20 mt-2 w-60 origin-top-right animate-scale-in rounded-xl border border-leaf-100 bg-white p-1.5 shadow-lift">
          <div className="border-b border-leaf-100 px-3 pb-2 pt-1.5">
            <p className="truncate text-sm font-semibold">{user?.full_name}</p>
            <p className="truncate text-xs text-slate-500">{user?.email}</p>
          </div>
          <Link role="menuitem" to="/admin/account" onClick={() => setOpen(false)} className="mt-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition hover:bg-mint-50">
            <Settings size={15} /> Settings
          </Link>
          <Link role="menuitem" to="/app" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition hover:bg-mint-50">
            <ScanLine size={15} /> Detection app
          </Link>
          <button role="menuitem" onClick={() => { setOpen(false); void signOut(); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-700 transition hover:bg-red-50">
            <LogOut size={15} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export default function AdminLayout() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const { pathname } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  const search = (e: FormEvent) => {
    e.preventDefault();
    navigate(`/admin/users${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`);
  };
  return (
    <div className="min-h-screen bg-mint-50 font-sans text-forest-950">
        <Sidebar open={open} onClose={() => setOpen(false)} />
        <div className="lg:pl-[264px]">
          <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-leaf-100 bg-mint-50/95 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
            <button className="rounded-lg p-2 text-forest-800 transition hover:bg-mint-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
              <Menu size={22} />
            </button>
            <form onSubmit={search} className="relative max-w-md flex-1" role="search">
              <Search size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search users by name, username or email…"
                aria-label="Search users"
                className="w-full rounded-xl border border-leaf-100 bg-white py-2.5 pl-10 pr-3 text-sm transition duration-200 placeholder:text-slate-400 focus:border-leaf-500 focus:outline-none focus:ring-4 focus:ring-leaf-100"
              />
            </form>
            <div className="ml-auto">
              <ProfileMenu />
            </div>
          </header>
          <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
            <ErrorBoundary resetKey={pathname}>
              <div key={pathname} className="animate-page-in">
                <Outlet />
              </div>
            </ErrorBoundary>
          </main>
          <footer className="px-4 pb-6 text-center text-xs text-slate-500">{FULL_TITLE} · Administrator console</footer>
        </div>
    </div>
  );
}

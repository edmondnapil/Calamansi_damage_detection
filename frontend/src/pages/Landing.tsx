import { ArrowRight, BarChart3, CloudUpload, FileText, Leaf, LogIn, Menu, ScanLine, ShieldCheck, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import aboutPhoto from "../assets/landing/about-calamansi-tree.webp";
import credits from "../assets/landing/credits.json";
import ctaPhoto from "../assets/landing/cta-calamansi-fruit.webp";
import heroPhoto from "../assets/landing/hero-calamansi-leaves.webp";
import howPhoto from "../assets/landing/how-calamansi-field.webp";
import { FULL_TITLE } from "../components/Layout";
import { LeafLogo } from "../components/ui";
import { api } from "../lib/api";
import { homeFor, useAuth } from "../lib/auth";
import { pct } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const NAV = [
  { href: "#home", label: "Home" },
  { href: "#about", label: "About" },
  { href: "#how-it-works", label: "How It Works" },
  { href: "#features", label: "Features" },
];

function AuthButtons({ compact = false }: { compact?: boolean }) {
  const { status, user } = useAuth();
  if (status === "signed_in")
    return (
      <Link to={homeFor(user)} className="inline-flex items-center justify-center gap-2 rounded-xl bg-leaf-600 px-4 py-2.5 text-sm font-semibold text-white transition duration-200 ease-smooth hover:bg-leaf-500 active:scale-[0.98]">
        {user?.role === "admin" ? "Admin dashboard" : "Open dashboard"} <ArrowRight size={16} />
      </Link>
    );
  return (
    <div className={`flex gap-2 ${compact ? "flex-col" : "items-center"}`}>
      <Link to="/login" className="inline-flex items-center justify-center gap-2 rounded-xl border border-leaf-200 px-4 py-2 text-sm font-semibold text-forest-800 transition duration-200 ease-smooth hover:border-leaf-500/50 hover:bg-mint-50 active:scale-[0.98]">
        <LogIn size={16} /> Login
      </Link>
      <Link to="/register" className="inline-flex items-center justify-center gap-2 rounded-xl bg-forest-800 px-4 py-2 text-sm font-semibold text-white shadow-sm transition duration-200 ease-smooth hover:bg-forest-700 hover:shadow-md active:scale-[0.98]">
        Register
      </Link>
    </div>
  );
}

/** Which page section is on screen, for the navigation's active state. */
function useActiveSection(ids: string[]) {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const seen = new Map<string, number>();
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => seen.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0));
        const best = [...seen.entries()].sort((a, b) => b[1] - a[1])[0];
        if (best && best[1] > 0) setActive(best[0]);
      },
      { rootMargin: "-64px 0px -40% 0px", threshold: [0, 0.15, 0.4, 0.7] },
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [ids]);
  return active;
}

const SECTION_IDS = ["home", "about", "how-it-works", "features"];

function NavBar() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const active = useActiveSection(SECTION_IDS);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const linkCls = (href: string) =>
    `relative rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-200 ease-smooth ${
      active === href.slice(1) ? "text-forest-900" : "text-slate-600 hover:bg-mint-100 hover:text-forest-900"
    }`;
  return (
    <header className={`sticky top-0 z-30 border-b bg-white/95 backdrop-blur transition-shadow duration-250 ease-smooth ${scrolled ? "border-leaf-100 shadow-card" : "border-transparent"}`}>
      <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 sm:px-6" aria-label="Main">
        <a href="#home" className="flex items-center gap-2.5">
          <LeafLogo size={36} />
          <span className="text-[15px] font-bold leading-tight text-forest-950">Calamansi Leaf Detection</span>
        </a>
        <div className="ml-auto hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className={linkCls(n.href)} aria-current={active === n.href.slice(1) ? "true" : undefined}>
              {n.label}
              <span className={`absolute inset-x-3 -bottom-[13px] h-0.5 rounded-full bg-leaf-600 transition-all duration-250 ease-smooth ${active === n.href.slice(1) ? "opacity-100" : "scale-x-0 opacity-0"}`} />
            </a>
          ))}
          <span className="mx-2 h-6 w-px bg-leaf-100" />
          <AuthButtons />
        </div>
        <button className="ml-auto rounded-lg p-2 text-forest-800 hover:bg-mint-100 md:hidden" onClick={() => setOpen((o) => !o)} aria-label="Toggle menu" aria-expanded={open}>
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </nav>
      {/* Mobile menu: height/opacity transition (no layout jump, no horizontal overflow) */}
      <div className={`grid overflow-hidden transition-all duration-250 ease-smooth md:hidden ${open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`} aria-hidden={!open}>
        <div className="min-h-0">
          <div className="border-t border-leaf-100 px-4 pb-4 pt-2">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} tabIndex={open ? 0 : -1} onClick={() => setOpen(false)}
                className={`block rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${active === n.href.slice(1) ? "bg-mint-100 text-forest-900" : "text-slate-700 hover:bg-mint-100"}`}>
                {n.label}
              </a>
            ))}
            <div className="mt-2">
              <AuthButtons compact />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section id="home" className="relative overflow-hidden bg-forest-900 text-white">
      <img src={heroPhoto} alt="Calamansi (Citrus × microcarpa) leaves and a young green fruit on a tree in Nueva Ecija, Philippines" className="absolute inset-0 h-full w-full object-cover" fetchPriority="high" />
      <div className="absolute inset-0 bg-gradient-to-r from-forest-950/95 via-forest-900/80 to-forest-900/20" />
      <div className="relative mx-auto max-w-6xl animate-fade-up px-4 py-20 sm:px-6 sm:py-28 lg:py-32">
        <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-white/85">
          <Leaf size={14} /> Plant-health image classification
        </p>
        <h1 className="mt-5 max-w-3xl text-3xl font-bold leading-tight sm:text-5xl">{FULL_TITLE}</h1>
        <p className="mt-5 max-w-2xl text-base text-white/85 sm:text-lg">
          Take or upload a photo of a calamansi leaf. A trained machine-learning model checks that it is a calamansi leaf and classifies it as{" "}
          <strong className="text-white">Healthy</strong> or <strong className="text-white">Damaged</strong>.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/register" className="inline-flex items-center gap-2 rounded-xl bg-leaf-600 px-5 py-3 text-sm font-semibold text-white hover:bg-leaf-500">
            Get Started <ArrowRight size={16} />
          </Link>
          <Link to="/login" className="inline-flex items-center gap-2 rounded-xl border border-white/40 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10">
            <LogIn size={16} /> Login
          </Link>
        </div>
      </div>
    </section>
  );
}

function About() {
  const model = useAsync(() => api.model(), []);
  const acc = model.data?.evaluation?.test.accuracy;
  const n = model.data?.evaluation?.test.n;
  return (
    <section id="about" className="scroll-mt-16 bg-white">
      <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:py-20">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-leaf-700">About the project</p>
          <h2 className="mt-2 text-2xl font-bold text-forest-950 sm:text-3xl">Early warning for calamansi leaf damage</h2>
          <p className="mt-4 text-slate-600">
            Calamansi (<em>Citrus × microcarpa</em>) is one of the most widely grown citrus crops in the Philippines. Spots, yellowing and other
            leaf damage are often the first visible sign that a tree needs attention.
          </p>
          <p className="mt-3 text-slate-600">
            This system uses an image-classification model (MobileNetV2, trained with transfer learning on a dataset of real calamansi leaf
            photos) to sort leaves into two classes: <strong>Healthy</strong> and <strong>Damaged</strong>. It does not diagnose specific
            diseases; it is an aid for spotting leaves that need a closer look.
          </p>
          {acc !== undefined && (
            <p className="mt-5 inline-flex items-center gap-2 rounded-xl bg-leaf-50 px-4 py-3 text-sm text-forest-900 ring-1 ring-leaf-100">
              <ShieldCheck size={18} className="text-leaf-600" />
              {pct(acc)} accuracy on {n} held-out test photos of calamansi leaves
            </p>
          )}
        </div>
        <img src={aboutPhoto} alt="A calamansi tree in the Philippines" loading="lazy" className="aspect-[4/3] w-full rounded-2xl object-cover shadow-card" />
      </div>
    </section>
  );
}

const STEPS = [
  { icon: CloudUpload, title: "Upload a leaf photo", text: "Choose a photo or take one with your camera. A single leaf, flat and in good light, gives the best result." },
  { icon: ScanLine, title: "The model analyses it", text: "The system first checks that the photo shows calamansi leaves, then the trained classifier examines the leaf." },
  { icon: FileText, title: "See the result", text: "You get Healthy or Damaged with a confidence score. Every result is saved to your private history." },
];

function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-16 bg-mint-50">
      <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_1.1fr] lg:py-20">
        <img src={howPhoto} alt="Calamansi fruit and leaves in a calamansi field in Nueva Ecija, Philippines" loading="lazy" className="order-2 aspect-[4/3] w-full rounded-2xl object-cover shadow-card lg:order-1" />
        <div className="order-1 lg:order-2">
          <p className="text-sm font-semibold uppercase tracking-wider text-leaf-700">How it works</p>
          <h2 className="mt-2 text-2xl font-bold text-forest-950 sm:text-3xl">Three steps from photo to result</h2>
          <ol className="mt-6 space-y-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className="flex gap-4 rounded-2xl border border-leaf-100 bg-white p-4 shadow-card">
                <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-forest-800 text-white">
                  <s.icon size={20} />
                </span>
                <div>
                  <p className="font-semibold text-forest-950">
                    {i + 1}. {s.title}
                  </p>
                  <p className="mt-1 text-sm text-slate-600">{s.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

const FEATURES = [
  { icon: Sparkles, title: "Healthy / Damaged classification", text: "A MobileNetV2 model trained on real calamansi leaf photos, with the confidence of every prediction." },
  { icon: ShieldCheck, title: "Calamansi-leaf check", text: "Photos of other plants, fruit, people or objects are rejected instead of being given a wrong label." },
  { icon: FileText, title: "Detection history", text: "Every classification is saved with its photo, date and confidence. Search, filter and open any record." },
  { icon: BarChart3, title: "Dashboard & reports", text: "Totals, daily trends and CSV export for the period you choose." },
  { icon: LogIn, title: "Private, secure accounts", text: "Email verification with a one-time code, password reset, and each user sees only their own records." },
  { icon: CloudUpload, title: "Upload or camera", text: "Drag and drop a photo or capture one directly with your device camera." },
];

function Features() {
  return (
    <section id="features" className="scroll-mt-16 bg-white">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
        <p className="text-sm font-semibold uppercase tracking-wider text-leaf-700">Features</p>
        <h2 className="mt-2 text-2xl font-bold text-forest-950 sm:text-3xl">What the system offers</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-leaf-100 bg-mint-50/60 p-5 transition duration-250 ease-smooth hover:-translate-y-0.5 hover:border-leaf-200 hover:bg-white hover:shadow-lift">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-leaf-600 text-white">
                <f.icon size={19} />
              </span>
              <p className="mt-3 font-semibold text-forest-950">{f.title}</p>
              <p className="mt-1 text-sm text-slate-600">{f.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function CallToAction() {
  return (
    <section className="relative overflow-hidden bg-forest-900 text-white">
      <img src={ctaPhoto} alt="Freshly harvested calamansi fruits from the Philippines" loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-forest-950/80" />
      <div className="relative mx-auto flex max-w-6xl flex-col items-start gap-5 px-4 py-14 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-bold sm:text-3xl">Ready to check your calamansi leaves?</h2>
          <p className="mt-2 text-white/80">Create a free account, verify your email, and classify your first leaf in a minute.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/register" className="inline-flex items-center gap-2 rounded-xl bg-leaf-600 px-5 py-3 text-sm font-semibold text-white hover:bg-leaf-500">
            Get Started <ArrowRight size={16} />
          </Link>
          <Link to="/login" className="inline-flex items-center gap-2 rounded-xl border border-white/40 px-5 py-3 text-sm font-semibold hover:bg-white/10">
            Login
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-forest-950 text-white/80">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.2fr_1fr]">
        <div>
          <div className="flex items-center gap-2.5">
            <LeafLogo size={34} />
            <p className="font-semibold text-white">{FULL_TITLE}</p>
          </div>
          <p className="mt-3 max-w-md text-sm">
            An academic machine-learning project. Results are limited to the model's Healthy and Damaged classes and are not a professional
            plant-health diagnosis.
          </p>
          <p className="mt-3 text-xs text-white/60">Built with React, FastAPI, TensorFlow and Supabase.</p>
        </div>
        <div>
          <p className="text-sm font-semibold text-white">Photo credits</p>
          <ul className="mt-2 space-y-1.5 text-xs">
            {credits.map((c) => (
              <li key={c.key}>
                <a href={c.source} target="_blank" rel="noreferrer" className="underline hover:text-white">{c.title}</a> by {c.author},{" "}
                {c.licenseUrl ? (
                  <a href={c.licenseUrl} target="_blank" rel="noreferrer" className="underline hover:text-white">{c.license}</a>
                ) : (
                  c.license
                )}
                , via Wikimedia Commons (resized and cropped).
              </li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen scroll-smooth font-sans text-forest-950">
      <NavBar />
      <main>
        <Hero />
        <About />
        <HowItWorks />
        <Features />
        <CallToAction />
      </main>
      <Footer />
    </div>
  );
}

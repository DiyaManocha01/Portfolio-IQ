import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { useAuth } from '../hooks/useAuth';
import { DisclaimerFooter } from '../components/DisclaimerFooter';

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: DashboardIcon },
  { to: '/portfolio', label: 'My Portfolio', icon: PortfolioIcon },
  { to: '/stocks', label: 'Stocks', icon: StocksIcon },
  { to: '/discover', label: 'Discover', icon: DiscoverIcon },
  { to: '/intelligence', label: 'Portfolio Intelligence', icon: IntelligenceIcon },
];

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  function handleLogout() {
    logout();
    navigate('/login');
  }

  return (
    <div className="flex min-h-screen bg-base-bg text-slate-100">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-64 shrink-0 flex-col border-r border-base-border bg-base-surface">
        <SidebarContent onNavigate={() => {}} onLogout={handleLogout} userLabel={user?.full_name ?? user?.email} />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="relative z-50 flex h-full w-64 flex-col border-r border-base-border bg-base-surface">
            <SidebarContent onNavigate={() => setMobileOpen(false)} onLogout={handleLogout} userLabel={user?.full_name ?? user?.email} />
          </aside>
        </div>
      )}

      <div className="flex min-h-screen flex-1 flex-col">
        {/* Top bar (mobile) */}
        <header className="flex items-center justify-between gap-3 border-b border-base-border bg-base-surface px-4 py-3 lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="rounded-md p-2 text-slate-300 hover:bg-base-surface2"
            aria-label="Open navigation"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <Logo />
          <div className="w-9" />
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
        <DisclaimerFooter />
      </div>
    </div>
  );
}

function SidebarContent({
  onNavigate,
  onLogout,
  userLabel,
}: {
  onNavigate: () => void;
  onLogout: () => void;
  userLabel?: string;
}) {
  return (
    <>
      <div className="flex items-center gap-2 px-5 py-5">
        <Logo />
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition',
                isActive
                  ? 'bg-brand-500/15 text-brand-300 border border-brand-500/30'
                  : 'text-slate-400 hover:bg-base-surface2 hover:text-slate-200 border border-transparent'
              )
            }
          >
            <item.icon className="h-4.5 w-4.5" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-base-border px-3 py-4">
        <div className="mb-3 truncate px-2 text-xs text-slate-500">{userLabel}</div>
        <button
          onClick={onLogout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-400 hover:bg-base-surface2 hover:text-slate-100 transition"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Log out
        </button>
      </div>
    </>
  );
}

function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 font-bold text-white">P</div>
      <div className="leading-tight">
        <div className="text-sm font-bold text-slate-100">PortfolioIQ</div>
        <div className="text-[10px] text-slate-500">AI Portfolio Intelligence</div>
      </div>
    </div>
  );
}

function iconBase(props: React.SVGProps<SVGSVGElement>) {
  return { xmlns: 'http://www.w3.org/2000/svg', fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor', strokeWidth: 1.8, ...props };
}

function DashboardIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconBase(props)}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13h4v8H3v-8zM10 3h4v18h-4V3zM17 8h4v13h-4V8z" />
    </svg>
  );
}
function PortfolioIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconBase(props)}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7h18M3 7v12a2 2 0 002 2h14a2 2 0 002-2V7M3 7l2-4h14l2 4M9 11h6" />
    </svg>
  );
}
function StocksIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconBase(props)}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v18h18M7 15l3-4 3 2 4-6" />
    </svg>
  );
}
function DiscoverIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconBase(props)}>
      <circle cx="11" cy="11" r="7" />
      <path strokeLinecap="round" d="M21 21l-4.3-4.3" />
    </svg>
  );
}
function IntelligenceIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconBase(props)}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3a6 6 0 00-3.6 10.8c.5.4.8 1 .8 1.7v.3h5.6v-.3c0-.7.3-1.3.8-1.7A6 6 0 0012 3z" />
    </svg>
  );
}

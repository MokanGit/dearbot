'use client';

import React from 'react';
import { useEntraAuth } from './EntraAuthProvider';
import { Shield, ArrowRight, Lock } from 'lucide-react';

export function EntraLoginCard() {
  const { login, isLoading } = useEntraAuth();

  return (
    <div className="min-h-[80vh] flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 p-8 shadow-xl relative overflow-hidden text-center">
        {/* Decorative subtle background accents */}
        <div className="absolute -top-16 -right-16 w-36 h-36 bg-sky-100 rounded-full blur-2xl pointer-events-none" />
        <div className="absolute -bottom-16 -left-16 w-36 h-36 bg-slate-100 rounded-full blur-2xl pointer-events-none" />

        <div className="inline-flex p-3 bg-sky-50 border border-sky-100 rounded-2xl mb-4 text-sky-700">
          <Lock className="w-7 h-7" />
        </div>

        <h1 className="text-xl font-bold text-slate-900 tracking-tight">
          Admin Control Plane
        </h1>
        <p className="text-xs text-slate-500 mt-1.5 leading-relaxed max-w-xs mx-auto">
          Sign in with your authorized Microsoft Entra ID account to manage job applications, generate tracked CVs, and monitor recruiter interactions.
        </p>

        <div className="mt-8 space-y-4">
          <button
            onClick={() => login()}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 px-5 py-3.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl transition-all duration-200 disabled:opacity-50 font-semibold text-sm shadow-md hover:shadow-lg group cursor-pointer"
          >
            {/* Microsoft 4-Color Tiles SVG Logo */}
            <svg className="w-4 h-4 shrink-0" viewBox="0 0 23 23">
              <path fill="#f35325" d="M0 0h11v11H0z" />
              <path fill="#81bc06" d="M12 0h11v11H12z" />
              <path fill="#05a6f0" d="M0 12h11v11H0z" />
              <path fill="#ffba08" d="M12 12h11v11H12z" />
            </svg>
            <span>Sign in with Microsoft Entra ID</span>
            <ArrowRight className="w-4 h-4 text-slate-400 group-hover:translate-x-0.5 group-hover:text-white transition-all ml-auto" />
          </button>
        </div>

        <div className="mt-8 pt-6 border-t border-slate-100 flex items-center justify-center gap-2 text-[11px] text-slate-400">
          <Shield className="w-3.5 h-3.5 text-emerald-600" />
          <span>Secured with Microsoft Entra ID</span>
        </div>
      </div>
    </div>
  );
}

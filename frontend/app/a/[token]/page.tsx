"use client";

import { useState, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { collectDeviceTelemetry } from "../../lib/telemetry";
import { PublicFooter } from "../../components/PublicFooter";
import { DemoQrCode } from "../../components/DemoQrCode";
import { 
  Bot, 
  Send, 
  Sparkles, 
  Shield, 
  CheckCircle2, 
  ExternalLink, 
  ChevronDown, 
  ChevronUp, 
  Lock,
  Building,
  Award,
  Terminal,
  Copy,
  Check,
  Globe,
  Layers,
  Cpu,
  Download,
  FileText,
  BookOpen,
  Paperclip,
  Briefcase
} from "lucide-react";
import { registerWebMCPTools } from "../../lib/webmcp";

interface EvidenceItem {
  source_title: string;
  excerpt: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  confidence?: "high" | "medium" | "low" | "unavailable";
  evidence?: EvidenceItem[];
  model_name?: string;
}

interface AdditionalDoc {
  id: string;
  title: string;
  filename: string;
  file_size: number;
  mime_type: string;
  download_url: string;
}

interface CoverLetterSummary {
  summary: string;
  fit_highlights: string[];
}

interface ApplicationPublicInfo {
  token: string;
  company: string;
  role: string;
  candidate: {
    name: string;
    headline: string;
    summary: string;
    last_updated: string;
  };
  cover_letter_summary?: CoverLetterSummary;
  suggested_questions?: string[];
  documents: {
    has_cv: boolean;
    cv_filename: string;
    cv_download_url: string;
    has_cover_letter: boolean;
    cover_letter_filename?: string;
    cover_letter_download_url?: string;
    cover_letter_text?: string;
    additional_documents: AdditionalDoc[];
  };
}

const SUGGESTED_QUESTIONS = [
  "Tell me about the candidate's technology leadership and organizational scale experience.",
  "What experience does the candidate have with financial services, credit and banking regulations?",
  "What concrete evidence supports the candidate's cybersecurity, resilience, and DORA readiness experience?",
  "Give examples of the candidate's practical AI and data governance work."
];

function formatFileSize(bytes: number): string {
  if (!bytes || bytes === 0) return "0 KB";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

export default function PublicProfilePage() {
  const params = useParams();
  const token = params?.token as string;

  const [appInfo, setAppInfo] = useState<ApplicationPublicInfo | null>(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedEvidence, setExpandedEvidence] = useState<{ [key: number]: boolean }>({});
  const [hasLoggedView, setHasLoggedView] = useState(false);
  const [showAiInstructions, setShowAiInstructions] = useState(false);
  const [aiTier, setAiTier] = useState<"get" | "post" | "mcp" | "webmcp">("get");
  const [copiedCurl, setCopiedCurl] = useState(false);
  const [tokenStatus, setTokenStatus] = useState<"checking" | "valid" | "revoked" | "not_found">("checking");
  const [tokenErrorDetail, setTokenErrorDetail] = useState<string>("");
  const [showCoverLetterModal, setShowCoverLetterModal] = useState(false);
  const [profileShareUrl, setProfileShareUrl] = useState("");

  const sampleGetQuestions = [
    {
      label: "Leadership & Scale",
      q: "What executive technology leadership and organizational scale experience does the candidate have?"
    },
    {
      label: "Banking & DORA",
      q: "What experience does the candidate have with banking, credit management, and DORA compliance?"
    },
    {
      label: "Cybersecurity & Cloud",
      q: "Can you provide examples of the candidate's cybersecurity, zero trust, and cloud architecture work?"
    }
  ];

  const candidateDisplayName =
    appInfo?.candidate?.name || process.env.NEXT_PUBLIC_CANDIDATE_NAME || "the candidate";
  const originUrl =
    typeof window !== "undefined"
      ? window.location.origin
      : (process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000");

  const curlExample = `curl -X POST "${originUrl}/a/${token}/ask" \\
  -H "Content-Type: application/json" \\
  -d '{"question": "What is ${candidateDisplayName}\\u0027s experience with engineering, architecture, and technology leadership?"}'`;

  const copyCurl = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(curlExample);
      setCopiedCurl(true);
      setTimeout(() => setCopiedCurl(false), 2500);
    }
  };

  const pageLoadTimeRef = useRef<number>(Date.now());
  const maxScrollRef = useRef<number>(0);

  const apiBase = typeof window !== "undefined" ? "" : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

  useEffect(() => {
    if (!token) return;

    const shareOrigin = window.location.origin;

    setProfileShareUrl(`${shareOrigin.replace(/\/$/, "")}/a/${encodeURIComponent(token)}`);
  }, [token]);

  // Track max scroll depth
  useEffect(() => {
    const onScroll = () => {
      const total = document.documentElement.scrollHeight - window.innerHeight;
      if (total > 0) {
        const pct = Math.round((window.scrollY / total) * 100);
        if (pct > maxScrollRef.current) {
          maxScrollRef.current = Math.min(100, pct);
        }
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Fetch initial profile info and validate token
  useEffect(() => {
    if (!token) return;

    fetch(`${apiBase}/a/${token}/profile.json`)
      .then(async (res) => {
        if (!res.ok) {
          let detail = "";
          try {
            const err = await res.json();
            detail = err.detail || "";
          } catch {}

          if (res.status === 410 || detail.toLowerCase().includes("revoked")) {
            setTokenStatus("revoked");
            setTokenErrorDetail(detail);
          } else if (res.status === 404) {
            setTokenStatus("not_found");
          } else {
            setTokenStatus("not_found");
          }
          return null;
        }
        setTokenStatus("valid");
        return res.json();
      })
      .then((data) => {
        if (data) {
          setAppInfo({
            token,
            company: data.evaluation_context?.company || "",
            role: data.evaluation_context?.role || "",
            candidate: {
              name: data.name || process.env.NEXT_PUBLIC_CANDIDATE_NAME || "Sample Candidate",
              headline: data.headline || "Technology Executive",
              summary: data.description || "",
              last_updated: data.last_updated || new Date().toISOString().split("T")[0],
            },
            cover_letter_summary: data.cover_letter_summary,
            suggested_questions: data.suggested_questions,
            documents: data.documents || {
              has_cv: true,
              cv_filename: `${(data.name || process.env.NEXT_PUBLIC_CANDIDATE_NAME || "Sample Candidate").replace(/\s+/g, "_")}_CV.pdf`,
              cv_download_url: `${apiBase}/a/${token}/cv`,
              has_cover_letter: false,
              additional_documents: [],
            },
          });
        }
      })
      .catch((err) => {
        console.error("Failed to load profile:", err);
        setTokenStatus("not_found");
      });
  }, [token, apiBase]);

  useEffect(() => {
    if (!appInfo?.candidate.name) return;
    document.title = `${appInfo.candidate.name} — Application Profile · DearBot`;
  }, [appInfo?.candidate.name]);

  // Register WebMCP tools
  useEffect(() => {
    if (!token || tokenStatus !== "valid") return;
    registerWebMCPTools(token);
  }, [token, tokenStatus]);

  // Log human view once
  useEffect(() => {
    if (token && !hasLoggedView) {
      setHasLoggedView(true);
      const { fingerprint, metadata } = collectDeviceTelemetry(0, 0);

      fetch(`${apiBase}/a/${token}/view`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_fingerprint: fingerprint,
          device_metadata: metadata,
        }),
      })
        .then((res) => {
          if (!res.ok) console.warn("Failed to log view:", res.status);
        })
        .catch((err) => {
          console.error("Could not log view:", err);
        });
    }
  }, [token, hasLoggedView, apiBase]);

  const handleAsk = async (queryToAsk?: string) => {
    const q = (queryToAsk || question).trim();
    if (!q || isLoading) return;

    const userMsg: Message = { role: "user", content: q };
    const placeholderMsg: Message = {
      role: "assistant",
      content: "",
      model_name: "Genererar svar..."
    };

    setMessages((prev) => [...prev, userMsg, placeholderMsg]);
    setQuestion("");
    setIsLoading(true);

    const dwellSeconds = Math.round((Date.now() - pageLoadTimeRef.current) / 1000);
    const { fingerprint, metadata } = collectDeviceTelemetry(dwellSeconds, maxScrollRef.current);

    try {
      const res = await fetch(`${apiBase}/a/${token}/ask-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          device_fingerprint: fingerprint,
          device_metadata: metadata,
        }),
      });

      if (!res.ok) {
        let errMessage = `Error: HTTP ${res.status}`;
        try {
          const errData = await res.json();
          if (errData?.detail) errMessage = errData.detail;
        } catch {}
        throw new Error(errMessage);
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";
      let modelName = "";
      let confidence: any = undefined;
      let evidence: EvidenceItem[] = [];

      if (reader) {
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const payload = JSON.parse(line.slice(6));
                if (payload.type === "token") {
                  accumulated += payload.content;
                  setMessages((prev) => {
                    const next = [...prev];
                    const last = next[next.length - 1];
                    if (last && last.role === "assistant") {
                      last.content = accumulated;
                    }
                    return next;
                  });
                } else if (payload.type === "metadata") {
                  modelName = payload.model_name || "";
                  confidence = payload.confidence;
                  evidence = payload.evidence || [];
                  setMessages((prev) => {
                    const next = [...prev];
                    const last = next[next.length - 1];
                    if (last && last.role === "assistant") {
                      last.model_name = modelName;
                      last.confidence = confidence;
                      last.evidence = evidence;
                    }
                    return next;
                  });
                }
              } catch (e) {}
            }
          }
        }
      }
    } catch (err: any) {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant") {
          last.content = err?.message || "Sorry, I encountered an issue retrieving that information. Please try again or rephrase your question.";
          last.confidence = "low";
          last.model_name = "Offline / Error";
        } else {
          next.push({
            role: "assistant",
            content: err?.message || "Sorry, I encountered an issue retrieving that information.",
            confidence: "low",
          });
        }
        return next;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const toggleEvidence = (idx: number) => {
    setExpandedEvidence((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  if (tokenStatus === "revoked") {
    return (
      <main className="max-w-xl mx-auto px-4 py-20 text-center space-y-6">
        <div className="p-8 bg-amber-50/80 border border-amber-200 rounded-2xl shadow-xs space-y-4">
          <div className="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center mx-auto text-amber-600">
            <Lock className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            Profile Link Revoked or Expired
          </h1>
          <p className="text-sm text-slate-600 leading-relaxed max-w-md mx-auto">
            {tokenErrorDetail || "This custom profile link is no longer active. To request an updated link or discuss opportunities, please reach out to the candidate."}
          </p>
          <div className="pt-2">
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs transition-colors shadow-xs"
            >
              Return to Home
            </Link>
          </div>
        </div>
        <PublicFooter />
      </main>
    );
  }

  if (tokenStatus === "not_found") {
    return (
      <main className="max-w-xl mx-auto px-4 py-20 text-center space-y-6">
        <div className="p-8 bg-slate-100 border border-slate-200 rounded-2xl shadow-xs space-y-4">
          <div className="w-12 h-12 rounded-full bg-slate-200 flex items-center justify-center mx-auto text-slate-600">
            <Lock className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            Profile Link Not Found
          </h1>
          <p className="text-sm text-slate-600 leading-relaxed max-w-md mx-auto">
            The profile link you followed could not be found or may have been mistyped.
          </p>
          <div className="pt-2">
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs transition-colors shadow-xs"
            >
              Return to Home
            </Link>
          </div>
        </div>
        <PublicFooter />
      </main>
    );
  }

  const cvUrl = `${apiBase}/a/${token}/cv`;
  const clUrl = `${apiBase}/a/${token}/cover-letter`;
  const hasCoverLetter = Boolean(appInfo?.documents.has_cover_letter);
  const additionalDocs = appInfo?.documents.additional_documents || [];
  const candidateName = appInfo?.candidate.name || process.env.NEXT_PUBLIC_CANDIDATE_NAME || "Candidate Profile";
  const candidateHeadline = appInfo?.candidate.headline || process.env.NEXT_PUBLIC_CANDIDATE_HEADLINE || "Professional experience and application materials";
  const candidateFirstName = candidateName.split(" ")[0] || "the candidate";
  const activeSuggestedQuestions = (appInfo?.suggested_questions && appInfo.suggested_questions.length > 0)
    ? appInfo.suggested_questions
    : SUGGESTED_QUESTIONS;

  return (
    <div className="dearbot-profile-page">
      <a className="skip-link" href="#profile-content">Skip to profile</a>
      {/* Machine-readable AI Discovery tags for LLM Scrapers */}
      <link rel="alternate" type="application/json" href={`${apiBase}/a/${token}/profile.json`} />
      <meta name="ai-capability-level1" content={`Level 1 URL/GET: Query directly via GET ${apiBase}/a/${token}/ask?q=<your_question>`} />
      <meta name="ai-capability-level2" content={`Level 2 REST/POST: Query via POST ${apiBase}/a/${token}/ask with JSON {"question": "..."}`} />
      <meta name="ai-capability-level3" content={`Level 3 MCP: Connect via Model Context Protocol at ${apiBase}/mcp/${token}`} />
      <meta name="ai-capability-webmcp" content="Level 4 WebMCP: In-browser AI agents can query via document.modelContext tools: ask_cv, get_cv_summary, get_experience" />

      <header className="dearbot-nav dearbot-profile-nav">
        <Link className="dearbot-brand" href="/" aria-label="DearBot home">
          <span className="dearbot-mark" aria-hidden="true">D<span>B</span></span>
          <span>DearBot</span>
        </Link>
        <nav aria-label="Profile navigation">
          <a href="#documents">Documents</a>
          <a href="#ask">Ask</a>
          <a href="#experience">Experience</a>
        </nav>
        <span className="dearbot-nav-label">Private application profile</span>
      </header>

      <main id="profile-content" className="dearbot-profile max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8 sm:space-y-10">
        
        {/* Candidate & Opportunity Header */}
        <header className="dearbot-profile-hero bg-white rounded-2xl border border-slate-200/80 shadow-xs p-6 sm:p-8 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="space-y-1.5">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200/70 mb-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-sky-600" /> Evidence-linked candidate profile
              </div>
              <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                {candidateName}
              </h1>
              <p className="text-base sm:text-lg font-medium text-sky-800">
                {candidateHeadline}
              </p>
            </div>

            {appInfo?.company && (
              <div className="self-start sm:self-auto px-3.5 py-2 rounded-xl bg-slate-50 border border-slate-200 text-right sm:text-right">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                  Application Context
                </span>
                <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5 justify-end mt-0.5">
                  <Briefcase className="w-3.5 h-3.5 text-sky-600" />
                  {appInfo.role}
                </span>
                <span className="text-[11px] text-slate-500 block">
                  {appInfo.company}
                </span>
              </div>
            )}
          </div>

          <p className="text-sm text-slate-600 leading-relaxed max-w-3xl pt-1">
            Review the tailored application package, role-relevant highlights and source-linked answers about my professional background.
          </p>
        </header>

        {profileShareUrl && (
          <section className="dearbot-profile-share" aria-labelledby="profile-share-title">
            <div>
              <div className="dearbot-section-label">Presentation mode</div>
              <h2 id="profile-share-title">Open this application<br /><em>on your phone.</em></h2>
              <p>
                Scan the code to open this exact application profile. Select the code to
                enlarge it for a presentation screen.
              </p>
              <a href={profileShareUrl} target="_blank" rel="noreferrer">{profileShareUrl}</a>
            </div>
            <DemoQrCode targetUrl={profileShareUrl} />
          </section>
        )}

        {/* SECTION 1: DOWNLOADABLE APPLICATION PACKAGE & ROLE FIT */}
        <section id="documents" className="space-y-4 scroll-mt-24">
          <div className="flex items-center justify-between">
            <h2 className="dearbot-section-heading text-lg sm:text-xl font-bold text-slate-900 flex items-center gap-2">
              <FileText className="w-5 h-5 text-sky-600" /> Application Package &amp; Fit Summary
            </h2>
            <span className="text-xs font-medium text-slate-500">
              Documents and role alignment
            </span>
          </div>

          {/* Primary Cards: CV & Cover Letter */}
          <div className="grid sm:grid-cols-2 gap-4">
            
            {/* CV Download Card */}
            <div className="dearbot-document-primary p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-sky-900 via-slate-900 to-slate-950 text-white shadow-md border border-slate-800 flex flex-col justify-between space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-sky-400/20 text-sky-300 border border-sky-400/30">
                    <CheckCircle2 className="w-3 h-3 text-sky-400" /> Tailored application document
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">PDF Format</span>
                </div>
                <h3 className="text-lg font-bold text-white tracking-tight">
                  Curriculum Vitae (CV)
                </h3>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Career history, leadership track record and documented capabilities tailored to this opportunity.
                </p>
              </div>

              <div className="pt-2">
                <a
                  href={cvUrl}
                  download
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-sky-500 hover:bg-sky-400 active:bg-sky-600 text-slate-950 font-bold text-sm transition-colors shadow-sm cursor-pointer"
                >
                  <Download className="w-4 h-4" /> Download Tailored CV (PDF)
                </a>
              </div>
            </div>

            {/* Cover Letter Card */}
            <div className="dearbot-document-secondary p-5 sm:p-6 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <BookOpen className="w-3 h-3" /> Application Statement
                  </span>
                  <span className="text-[11px] text-slate-500">
                    {hasCoverLetter ? "Available" : "General profile"}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-slate-900 tracking-tight">
                  Cover Letter
                </h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {hasCoverLetter
                    ? "Specific application motivation, strategic alignment, and leadership perspective for this opportunity."
                    : "No separate cover letter was requested for this opportunity. You can query my background directly below."}
                </p>
              </div>

              {hasCoverLetter ? (
                <div className="flex flex-col sm:flex-row gap-2 pt-2">
                  <a
                    href={clUrl}
                    download
                    className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-medium text-xs transition-colors shadow-xs"
                  >
                    <Download className="w-3.5 h-3.5" /> Download Cover Letter
                  </a>
                  {appInfo?.documents.cover_letter_text && (
                    <button
                      type="button"
                      onClick={() => setShowCoverLetterModal(true)}
                      className="inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium text-xs transition-colors cursor-pointer border border-slate-200"
                    >
                      <BookOpen className="w-3.5 h-3.5 text-slate-600" /> Read Inline
                    </button>
                  )}
                </div>
              ) : (
                <div className="pt-2">
                  <span className="inline-block text-xs text-slate-400 italic">
                    Refer to CV and Q&amp;A assistant below for all role-specific details.
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Cover Letter Summary & 3-5 Role Fit Highlights */}
          {appInfo?.cover_letter_summary && (
            <div className="dearbot-fit-summary p-5 sm:p-6 rounded-2xl bg-gradient-to-br from-slate-50 via-sky-50/30 to-white border border-sky-200/80 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-sky-100 pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="p-2 rounded-xl bg-sky-600 text-white shadow-2xs">
                    <Sparkles className="w-4 h-4" />
                  </span>
                  <div>
                    <h3 className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
                      Why {candidateFirstName} Fits the {appInfo?.role || "Target"} Role
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Structured cover letter summary &amp; verified requirement alignment
                    </p>
                  </div>
                </div>
                {hasCoverLetter && appInfo?.documents.cover_letter_text && (
                  <button
                    type="button"
                    onClick={() => setShowCoverLetterModal(true)}
                    className="self-start sm:self-auto inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-sky-800 text-xs font-semibold border border-sky-200 transition-colors shadow-2xs cursor-pointer"
                  >
                    <BookOpen className="w-3.5 h-3.5 text-sky-600" /> View Full Cover Letter
                  </button>
                )}
              </div>

              {/* Summary Statement */}
              {appInfo.cover_letter_summary.summary && (
                <p className="text-xs sm:text-sm text-slate-700 leading-relaxed font-serif italic bg-white p-3.5 rounded-xl border border-slate-200/80">
                  &ldquo;{appInfo.cover_letter_summary.summary}&rdquo;
                </p>
              )}

              {/* 3-5 Fit Bullet Points */}
              {appInfo.cover_letter_summary.fit_highlights && appInfo.cover_letter_summary.fit_highlights.length > 0 && (
                <div className="space-y-2 pt-1">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                    Core Qualifications &amp; Fit ({appInfo.cover_letter_summary.fit_highlights.length} key points):
                  </span>
                  <div className="grid gap-2">
                    {appInfo.cover_letter_summary.fit_highlights.map((bullet, bIdx) => (
                      <div
                        key={bIdx}
                        className="flex items-start gap-3 p-3 rounded-xl bg-white border border-slate-200/80 text-xs sm:text-sm text-slate-800 shadow-2xs hover:border-sky-300 transition-colors"
                      >
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                        <span className="leading-snug">{bullet}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Additional Documents Grid (Certificates, Recommendations, etc.) */}
          {additionalDocs.length > 0 && (
            <div className="space-y-2 pt-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <Paperclip className="w-3.5 h-3.5 text-sky-600" /> Additional Requested Documents ({additionalDocs.length})
              </span>
              <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-3">
                {additionalDocs.map((doc) => (
                  <div
                    key={doc.id}
                    className="p-4 rounded-xl bg-white border border-slate-200 hover:border-sky-300 transition-colors shadow-xs flex flex-col justify-between space-y-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <Award className="w-4 h-4 text-sky-600" />
                        <span className="text-[10px] text-slate-500 font-mono">
                          {formatFileSize(doc.file_size)}
                        </span>
                      </div>
                      <h4 className="text-xs font-bold text-slate-900 leading-tight line-clamp-2">
                        {doc.title}
                      </h4>
                      <p className="text-[11px] text-slate-400 truncate" title={doc.filename}>
                        {doc.filename}
                      </p>
                    </div>

                    <a
                      href={`${apiBase}${doc.download_url}`}
                      download
                      className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-sky-50 hover:text-sky-700 text-slate-700 font-medium text-xs border border-slate-200 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" /> Download
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Inline Cover Letter Modal / Viewer */}
        {showCoverLetterModal && appInfo?.documents.cover_letter_text && (
          <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95">
              <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
                <div className="flex items-center gap-2">
                  <BookOpen className="w-4 h-4 text-sky-600" />
                  <h3 className="font-bold text-sm text-slate-900">Cover Letter</h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowCoverLetterModal(false)}
                  className="text-slate-400 hover:text-slate-600 text-sm font-semibold p-1 rounded-md"
                >
                  ✕ Close
                </button>
              </div>
              <div className="p-6 overflow-y-auto space-y-4 text-sm text-slate-800 whitespace-pre-line leading-relaxed font-serif">
                {appInfo.documents.cover_letter_text}
              </div>
              <div className="p-4 border-t border-slate-100 flex items-center justify-between bg-slate-50">
                <a
                  href={clUrl}
                  download
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs transition-colors"
                >
                  <Download className="w-3.5 h-3.5" /> Download Document
                </a>
                <button
                  type="button"
                  onClick={() => setShowCoverLetterModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-200 hover:bg-slate-300 text-slate-700 font-medium text-xs transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 2: INTERACTIVE RECRUITER Q&A ASSISTANT */}
        <section id="ask" className="dearbot-ask bg-white rounded-2xl border border-slate-200 shadow-md p-6 sm:p-8 space-y-6 scroll-mt-24">
          <div className="border-b border-slate-100 pb-4 space-y-1">
            <h2 className="dearbot-section-heading text-lg sm:text-xl font-bold text-slate-900 flex items-center gap-2">
              <Bot className="w-5 h-5 text-sky-600" /> Ask about {candidateFirstName}&apos;s background
            </h2>
            <p className="text-xs text-slate-500">
              Answers are grounded in {candidateFirstName}&apos;s career documentation and include supporting excerpts when available.
            </p>
          </div>

          {/* Suggested Questions */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Suggested Inquiries:</span>
            <div className="flex flex-wrap gap-2">
              {activeSuggestedQuestions.map((sq, i) => (
                <button
                  key={i}
                  onClick={() => handleAsk(sq)}
                  disabled={isLoading}
                  className="text-xs text-left px-3 py-2 rounded-lg bg-slate-50 hover:bg-sky-50 hover:text-sky-800 text-slate-700 border border-slate-200 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {sq}
                </button>
              ))}
            </div>
          </div>

          {/* Conversation History */}
          {messages.length > 0 && (
            <div className="space-y-4 pt-2">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-xl text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-sky-50 text-sky-950 ml-4 sm:ml-8 border border-sky-100"
                      : "bg-slate-50 text-slate-900 mr-4 sm:mr-8 border border-slate-200 shadow-xs"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-xs text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                        {msg.role === "user" ? "Your Question" : "Professional Profile Answer"}
                      </span>
                      {msg.role === "assistant" && msg.model_name && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-sky-800 bg-sky-50 px-2 py-0.5 rounded-md border border-sky-100">
                          <Cpu className="w-3 h-3 text-sky-600" />
                          <span>{msg.model_name}</span>
                        </span>
                      )}
                    </div>
                    {msg.confidence && (
                      <span
                        className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
                          msg.confidence === "high"
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : msg.confidence === "medium"
                            ? "bg-amber-50 text-amber-700 border-amber-200"
                            : msg.confidence === "unavailable"
                            ? msg.content?.toLowerCase().includes("no verified evidence")
                              ? "bg-slate-100 text-slate-700 border-slate-300"
                              : "bg-rose-50 text-rose-700 border-rose-200"
                            : "bg-slate-100 text-slate-600 border-slate-200"
                        }`}
                      >
                        {msg.confidence === "unavailable"
                          ? msg.content?.toLowerCase().includes("no verified evidence")
                            ? "No Verified Evidence"
                            : "Service Unavailable"
                          : `Confidence: ${msg.confidence}`}
                      </span>
                    )}
                  </div>

                  {msg.role === "assistant" && !msg.content ? (
                    <div className="flex items-center gap-2 text-slate-400 py-1">
                      <span className="inline-block w-2 h-2 rounded-full bg-sky-500 animate-pulse"></span>
                      <span className="inline-block w-2 h-2 rounded-full bg-sky-500 animate-pulse delay-75"></span>
                      <span className="inline-block w-2 h-2 rounded-full bg-sky-500 animate-pulse delay-150"></span>
                    </div>
                  ) : (
                    <p className="whitespace-pre-line text-slate-800">{msg.content}</p>
                  )}

                  {/* Supporting Evidence Cards */}
                  {msg.evidence && msg.evidence.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-200/70">
                      <button
                        onClick={() => toggleEvidence(idx)}
                        className="text-xs font-semibold text-sky-700 hover:text-sky-900 inline-flex items-center gap-1 cursor-pointer"
                      >
                        {expandedEvidence[idx] ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        Supporting Experience &amp; Evidence ({msg.evidence.length})
                      </button>

                      {expandedEvidence[idx] && (
                        <div className="mt-2 space-y-2">
                          {msg.evidence.map((item, eIdx) => (
                            <div
                              key={eIdx}
                              className="p-3 bg-white rounded-lg border border-slate-200 text-xs space-y-1"
                            >
                              <div className="font-bold text-slate-900 flex items-center gap-1">
                                <Award className="w-3.5 h-3.5 text-sky-600" /> {item.source_title}
                              </div>
                              <p className="text-slate-600 italic">&ldquo;{item.excerpt}&rdquo;</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Question Input Box */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAsk();
            }}
            className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-2"
          >
            <input
              type="text"
              aria-label={`Ask a question about ${candidateFirstName}'s professional background`}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about experience, leadership, projects or technologies..."
              disabled={isLoading}
              className="flex-1 px-4 py-3 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 bg-white"
            />
            <button
              type="submit"
              disabled={isLoading || !question.trim()}
              className="dearbot-primary-action px-6 py-3 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-medium text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm cursor-pointer"
            >
              {isLoading ? (
                <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              <span>Ask</span>
            </button>
          </form>
        </section>

        {/* SECTION 3: SELECTED EXECUTIVE TRACK RECORD & THEMES */}
        <section id="experience" className="space-y-4 scroll-mt-24">
          <h2 className="dearbot-section-heading text-lg sm:text-xl font-bold text-slate-900">Selected Experience &amp; Themes</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs space-y-2">
              <h3 className="font-bold text-slate-900 flex items-center gap-2">
                <Building className="w-4 h-4 text-sky-600" /> Technology Leadership &amp; Scale
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Led Nordic technology, product development, operations, and data analytics as CITO at Example Financial Services and Nordic CTO at Example Insurance Group, aligning engineering roadmaps with executive committees and boards.
              </p>
            </div>

            <div className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs space-y-2">
              <h3 className="font-bold text-slate-900 flex items-center gap-2">
                <Shield className="w-4 h-4 text-emerald-600" /> Cybersecurity &amp; Operational Resilience
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Established zero-trust security architectures, CISO governance, business continuity, and regulatory readiness (GDPR, NIS2, DORA, PCI-DSS, Basel II) across mission-critical banking, insurance, and public transport platforms.
              </p>
            </div>

            <div className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs space-y-2">
              <h3 className="font-bold text-slate-900 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-600" /> AI Engineering &amp; Data Platforms
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Hands-on AI engineering (Example University AI studies 2023–2025, PyTorch, RAG, LangSmith, ZEP, Multi-Agent DevOps) combined with enterprise data &amp; AI strategy delivered 6 months ahead of schedule at SL.
              </p>
            </div>

            <div className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs space-y-2">
              <h3 className="font-bold text-slate-900 flex items-center gap-2">
                <Award className="w-4 h-4 text-amber-600" /> Cloud &amp; Financial Transformation
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                Executed cloud-first Azure modernization at Example Financial Services (&gt;30% IT budget reduction while increasing automation and delivery cadence) and built a shared cloud platform across 12 regulated European entities at Example Bank Group.
              </p>
            </div>
          </div>
        </section>

        {/* SECTION 4: TRANSPARENCY & GOVERNANCE NOTICE */}
        <section className="bg-slate-100/80 p-4 rounded-xl border border-slate-200 text-xs text-slate-600 flex items-start gap-3">
          <Shield className="w-4 h-4 text-sky-600 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <p className="leading-relaxed">
              <strong>About the answers:</strong> AI responses are limited to the career material connected to this application and may include source excerpts for review.
            </p>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Questions and basic usage data may be logged for service quality, security and interview preparation.
            </p>
          </div>
        </section>

        {/* SECTION 5: AI AGENT, MCP & WEBMCP DISCOVERY HUB (MOVED TO BOTTOM) */}
        <section className="dearbot-protocol-hub bg-slate-900 rounded-2xl border border-slate-800 p-5 sm:p-6 text-slate-200 space-y-4 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <div className="inline-flex items-center gap-1.5 text-xs font-bold text-sky-400 uppercase tracking-wider mb-1">
                <Cpu className="w-4 h-4" /> AI Agents &amp; Machine Discovery
              </div>
              <h3 className="text-base font-bold text-white">
                Model Context Protocol (MCP) &amp; WebMCP Interfaces
              </h3>
              <p className="text-xs text-slate-400">
                Automated screening agents (ChatGPT, Claude, Perplexity, Cursor) can query this profile directly.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setShowAiInstructions(!showAiInstructions)}
              className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition-colors cursor-pointer border border-slate-700"
            >
              <Layers className="w-3.5 h-3.5 text-sky-400" />
              <span>{showAiInstructions ? "Collapse AI Protocol Hub" : "Expand 4 Protocol Tiers"}</span>
              {showAiInstructions ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>

          {/* Quick summary badges */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-400 text-xs">Supported interfaces:</span>
            <span className="px-2 py-0.5 rounded bg-sky-500/10 text-sky-300 font-medium text-[11px] border border-sky-500/20">
              Tier 1: URL / GET
            </span>
            <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 font-medium text-[11px] border border-emerald-500/20">
              Tier 2: REST POST
            </span>
            <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 font-medium text-[11px] border border-purple-500/20">
              Tier 3: Remote MCP
            </span>
            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 font-medium text-[11px] border border-amber-500/20">
              Tier 4: In-Browser WebMCP
            </span>
          </div>

          {showAiInstructions && (
            <div className="pt-2 space-y-4 border-t border-slate-800">
              {/* 4 Tier Selector Tabs */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setAiTier("get")}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-xs transition-colors cursor-pointer ${
                    aiTier === "get"
                      ? "bg-sky-500 text-slate-950 font-bold shadow-xs"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700"
                  }`}
                >
                  <Globe className="w-3.5 h-3.5" /> Tier 1: URL / GET
                </button>
                <button
                  type="button"
                  onClick={() => setAiTier("post")}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-xs transition-colors cursor-pointer ${
                    aiTier === "post"
                      ? "bg-emerald-500 text-slate-950 font-bold shadow-xs"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700"
                  }`}
                >
                  <Terminal className="w-3.5 h-3.5" /> Tier 2: REST API / POST
                </button>
                <button
                  type="button"
                  onClick={() => setAiTier("mcp")}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-xs transition-colors cursor-pointer ${
                    aiTier === "mcp"
                      ? "bg-purple-500 text-slate-950 font-bold shadow-xs"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700"
                  }`}
                >
                  <Cpu className="w-3.5 h-3.5" /> Tier 3: Remote MCP
                </button>
                <button
                  type="button"
                  onClick={() => setAiTier("webmcp")}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-xs transition-colors cursor-pointer ${
                    aiTier === "webmcp"
                      ? "bg-amber-500 text-slate-950 font-bold shadow-xs"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700"
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" /> Tier 4: WebMCP (In-Browser)
                </button>
              </div>

              {/* Content for Tier 1 */}
              {aiTier === "get" && (
                <div className="space-y-3 bg-slate-950 p-4 rounded-xl border border-slate-800">
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <b className="text-sky-400">Simplest Discovery:</b> Designed for web-browsing AI models (ChatGPT Browsing, Perplexity, Claude Web Fetch) that cannot execute POST requests:
                  </p>
                  <pre className="p-2.5 bg-slate-900 rounded-lg text-[11px] font-mono text-sky-300 overflow-x-auto border border-slate-800">
                    {apiBase}/a/{token}/ask?q=&lt;your_factual_question&gt;
                  </pre>

                  <div className="space-y-1.5 pt-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      Direct test links:
                    </span>
                    <div className="flex flex-col gap-1.5">
                      {sampleGetQuestions.map((item, qIdx) => (
                        <a
                          key={qIdx}
                          href={`${apiBase}/a/${token}/ask?q=${encodeURIComponent(item.q)}`}
                          target="_blank"
                          rel="noreferrer"
                          className="p-2 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-800 text-sky-300 hover:text-sky-200 transition-colors flex items-center justify-between gap-2 text-xs"
                        >
                          <span className="truncate">
                            <b className="text-slate-400 mr-1.5 font-normal">[{item.label}]</b>
                            {item.q}
                          </span>
                          <ExternalLink className="w-3 h-3 shrink-0 text-slate-500" />
                        </a>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 pt-1 text-xs text-slate-400">
                    <a
                      href={`${apiBase}/a/${token}/profile.json`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sky-400 hover:text-sky-300 font-medium inline-flex items-center gap-1"
                    >
                      Inspect profile.json <ExternalLink className="w-3 h-3" />
                    </a>
                    <span>•</span>
                    <a
                      href={`${apiBase}/a/${token}/ask`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sky-400 hover:text-sky-300 font-medium inline-flex items-center gap-1"
                    >
                      Query Catalog <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>
              )}

              {/* Content for Tier 2 */}
              {aiTier === "post" && (
                <div className="space-y-3 bg-slate-950 p-4 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-emerald-400 flex items-center gap-1.5 text-xs">
                      <Terminal className="w-3.5 h-3.5" /> Direct Stateless HTTP POST (cURL / Python / Node):
                    </span>
                    <button
                      type="button"
                      onClick={copyCurl}
                      className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium transition-colors border border-slate-700 cursor-pointer"
                    >
                      {copiedCurl ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3 text-slate-400" />}
                      <span>{copiedCurl ? "Copied" : "Copy cURL"}</span>
                    </button>
                  </div>
                  <pre className="p-2.5 bg-slate-900 rounded-lg text-[11px] font-mono text-emerald-300 overflow-x-auto border border-slate-800">
                    {curlExample}
                  </pre>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    Returns structured JSON with <code className="text-sky-300">{"{ answer, evidence: [{ source_title, excerpt }], confidence, request_id }"}</code>. Strict factual isolation; no hallucinations.
                  </p>
                </div>
              )}

              {/* Content for Tier 3 */}
              {aiTier === "mcp" && (
                <div className="space-y-3 bg-slate-950 p-4 rounded-xl border border-slate-800">
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <b className="text-purple-400">Model Context Protocol (MCP):</b> Stateless JSON-RPC 2.0 endpoint for Claude Desktop, Cursor, and automated recruiting pipelines.
                  </p>
                  <pre className="p-2.5 bg-slate-900 rounded-lg text-[11px] font-mono text-purple-300 overflow-x-auto border border-slate-800">
                    {apiBase}/mcp/{token}
                  </pre>
                  <p className="text-xs text-slate-400">
                    Exposes tools: <code className="text-purple-300 font-mono">get_profile</code>, <code className="text-purple-300 font-mono">ask_about_candidate</code>, and <code className="text-purple-300 font-mono">get_evidence</code>.
                  </p>
                </div>
              )}

              {/* Content for Tier 4: WebMCP */}
              {aiTier === "webmcp" && (
                <div className="space-y-3 bg-slate-950 p-4 rounded-xl border border-slate-800">
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <b className="text-amber-400">W3C Web Model Context Protocol (WebMCP):</b> Browser-native model tool registration on <code className="text-amber-300 font-mono">document.modelContext</code>. When a WebMCP-capable browser or in-page agent visits this page, it discovers and calls structured CV tools directly.
                  </p>
                  <div className="p-3 bg-slate-900 rounded-lg border border-slate-800 space-y-2 text-xs">
                    <div className="flex items-center justify-between text-xs font-semibold text-amber-400">
                      <span>Primary Tool: <code className="text-amber-300 font-mono">ask_cv(question)</code></span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">readOnlyHint: true</span>
                    </div>
                    <pre className="p-2 bg-slate-950 rounded font-mono text-[10px] text-amber-300 overflow-x-auto">
{`// Invoked by browser AI agents natively via document.modelContext:
const tools = await document.modelContext.getTools();
const result = await ask_cv({ question: "Has the candidate worked with DORA and cybersecurity?" });
// Returns: { answer: "...", confidence: "high", evidence: [...], source: "cv-assistant" }`}
                    </pre>
                  </div>
                  <div className="grid sm:grid-cols-2 gap-2 text-xs">
                    <div className="p-2.5 bg-slate-900/80 rounded-lg border border-slate-800 space-y-1">
                      <span className="font-semibold text-slate-300 font-mono">get_cv_summary()</span>
                      <p className="text-slate-500 text-[11px]">Returns concise executive summary, core roles, and domain capabilities.</p>
                    </div>
                    <div className="p-2.5 bg-slate-900/80 rounded-lg border border-slate-800 space-y-1">
                      <span className="font-semibold text-slate-300 font-mono">get_experience(topic)</span>
                      <p className="text-slate-500 text-[11px]">Factual experience query for a specific framework or skill (e.g. &apos;DORA&apos;).</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Visitor Consent & Quality Telemetry Notice */}
        <div className="text-center text-xs text-slate-500 py-2">
          <p>
            By using this service you agree to our operational quality &amp; telemetry tracking. Data is permanently removed when the application is closed.{" "}
            <Link
              href="/privacy"
              className="text-sky-600 hover:text-sky-700 font-medium underline underline-offset-2 transition-colors"
            >
              Read full policy &gt;&gt;
            </Link>
          </p>
        </div>

        <PublicFooter candidateName={candidateName} cvHref={cvUrl} />
      </main>
    </div>
  );
}

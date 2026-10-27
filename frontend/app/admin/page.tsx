"use client";

import { useState, useEffect } from "react";
import { 
  RefreshCw, 
  Plus, 
  FileText, 
  Download, 
  ExternalLink, 
  Eye, 
  HelpCircle, 
  Bot, 
  ShieldAlert, 
  CheckCircle2, 
  Clock, 
  X, 
  FolderSync,
  AlertCircle,
  LogOut,
  UserCheck,
  Building2,
  Globe,
  Monitor,
  Cpu,
  MapPin,
  Navigation,
  Paperclip,
  Trash2,
  Copy,
  Check,
  BookOpen,
  Briefcase,
  Layers,
  Search,
  Activity
} from "lucide-react";
import { EntraAuthProvider, useEntraAuth } from "../auth/EntraAuthProvider";
import { EntraLoginCard } from "../auth/EntraLoginCard";

interface Application {
  id: string;
  token: string;
  company: string;
  role: string;
  cv_version: string;
  created_at: string;
  is_active: boolean;
  profile_url: string;
  pdf_url: string;
  has_cv?: boolean;
  has_cover_letter?: boolean;
  cover_letter_filename?: string;
  documents_count?: number;
  stats: {
    profile_views: number;
    questions: number;
    ai_agent_interactions: number;
  };
}

interface DocumentItem {
  id: string;
  title: string;
  filename: string;
  classification: string;
  classification_source?: string;
  manually_approved_at?: string;
  is_active?: boolean;
  content_hash: string;
  last_synced: string;
  character_count: number;
}

interface ApplicationDetail {
  application: {
    id: string;
    token: string;
    company: string;
    role: string;
    job_description: string;
    notes?: string;
    cv_version: string;
    created_at: string;
    is_active: boolean;
    profile_url: string;
    pdf_url: string;
    has_cv?: boolean;
    cover_letter?: {
      has_file: boolean;
      filename?: string;
      text?: string;
      download_url?: string;
    };
    additional_documents?: Array<{
      id: string;
      title: string;
      filename: string;
      file_size: number;
      mime_type: string;
      created_at: string;
      download_url: string;
    }>;
  };
  metrics: {
    profile_views: number;
    questions_count: number;
    client_breakdown: { [key: string]: number };
    organizations: string[];
  };
  timeline: Array<{
    id: string;
    timestamp: string;
    event_type?: string;
    question?: string;
    answer?: string;
    confidence?: string;
    client_type: string;
    client_name?: string;
    request_id: string;
    ip_address?: string;
    organization?: string;
    geo_country?: string;
    geo_city?: string;
    reverse_dns?: string;
    isp?: string;
    asn?: string;
    referer?: string;
    accept_language?: string;
    device_fingerprint?: string;
    device_metadata?: any;
  }>;
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return "0 KB";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const candidateFileSlug = (process.env.NEXT_PUBLIC_CANDIDATE_NAME || "Sample Candidate")
  .replace(/[^A-Za-z0-9_-]+/g, "_")
  .replace(/^_+|_+$/g, "") || "Candidate";

function AdminDashboardContent() {
  const { authMode, account, isAuthenticated, isLoading, login, logout, getAuthHeaders } = useEntraAuth();
  const [activeTab, setActiveTab] = useState<"applications" | "knowledge">("applications");
  const [applications, setApplications] = useState<Application[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedApp, setSelectedApp] = useState<ApplicationDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Create Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createModalTab, setCreateModalTab] = useState<"url" | "manual">("url");
  const [newCompany, setNewCompany] = useState("");
  const [newRole, setNewRole] = useState("");
  const [newJD, setNewJD] = useState("");
  const [newNotes, setNewNotes] = useState("");

  // From Job Link (AI Auto-Tailor) State
  const [jobUrl, setJobUrl] = useState("");
  const [jobUrlNotes, setJobUrlNotes] = useState("");
  const [isStreamingUrl, setIsStreamingUrl] = useState(false);
  const [streamStep, setStreamStep] = useState<
    "idle" | "fetching_page" | "analyzing_job" | "generating_cv" | "generating_cover_letter" | "finalizing" | "completed" | "error"
  >("idle");
  const [streamProgress, setStreamProgress] = useState(0);
  const [streamMessage, setStreamMessage] = useState("");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [urlScreendump, setUrlScreendump] = useState<{
    url: string;
    domain: string;
    page_title: string;
    site_name: string;
    screenshot_data_url: string;
  } | null>(null);
  const [analyzedJobInfo, setAnalyzedJobInfo] = useState<{
    company: string;
    role: string;
    language: string;
    positioning_angle: string;
    key_requirements: string[];
  } | null>(null);
  const [streamedCvText, setStreamedCvText] = useState("");
  const [streamedCvSection, setStreamedCvSection] = useState("");
  const [streamedClText, setStreamedClText] = useState("");
  const [streamPreviewTab, setStreamPreviewTab] = useState<"cv" | "cl">("cv");
  
  // Custom CV upload
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  
  // Cover Letter
  const [coverLetterMode, setCoverLetterMode] = useState<"none" | "file" | "text">("none");
  const [coverLetterFile, setCoverLetterFile] = useState<File | null>(null);
  const [coverLetterText, setCoverLetterText] = useState("");

  // Additional Supporting Documents
  const [additionalDocs, setAdditionalDocs] = useState<Array<{ id: string; file: File | null; title: string }>>([]);

  const addDocRow = () => {
    setAdditionalDocs((prev) => [
      ...prev,
      { id: Math.random().toString(36).substring(7), file: null, title: "" },
    ]);
  };

  const updateDocRow = (id: string, field: "file" | "title", value: any) => {
    setAdditionalDocs((prev) =>
      prev.map((item) => (item.id === id ? { ...item, [field]: value } : item))
    );
  };

  const removeDocRow = (id: string) => {
    setAdditionalDocs((prev) => prev.filter((item) => item.id !== id));
  };

  const [isGeneratingCV, setIsGeneratingCV] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);
  const [createdResult, setCreatedResult] = useState<{
    id: string;
    token?: string;
    company?: string;
    role?: string;
    language?: string;
    positioning_angle?: string;
    profile_url: string;
    pdf_download_url: string;
    cover_letter_download_url?: string;
    has_cover_letter?: boolean;
    cover_letter_filename?: string;
    additional_documents_count?: number;
    application_log?: string;
  } | null>(null);

  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const apiBase = typeof window !== "undefined" ? "" : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

  const copyToClipboard = (text: string, id: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedToken(id);
      setTimeout(() => setCopiedToken(null), 2500);
    }
  };

  const handleAuthenticatedDownload = async (urlPath: string, fallbackFilename: string) => {
    try {
      const headers = await getAuthHeaders();
      const targetUrl = urlPath.startsWith("http") ? urlPath : `${apiBase}${urlPath}`;
      const res = await fetch(targetUrl, { headers });
      if (!res.ok) {
        alert(`Download failed (status ${res.status}).`);
        return;
      }
      const blob = await res.blob();
      const disp = res.headers.get("content-disposition") || "";
      const fnMatch = disp.match(/filename="?([^"]+)"?/i);
      const filename = fnMatch && fnMatch[1] ? fnMatch[1] : fallbackFilename;
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(objUrl), 5000);
    } catch (err: any) {
      console.error("Authenticated download error:", err);
      window.open(urlPath, "_blank", "noopener,noreferrer");
    }
  };

  const fetchApplications = async () => {
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/applications`, { headers });
      if (res.ok) {
        const data = await res.json();
        setApplications(data);
      }
    } catch (err) {
      console.error("Failed to fetch applications:", err);
    }
  };

  const fetchDocuments = async () => {
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/documents`, { headers });
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (err) {
      console.error("Failed to fetch documents:", err);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchApplications();
      fetchDocuments();
    }
  }, [isAuthenticated]);

  const handleSyncNow = async () => {
    setIsSyncing(true);
    setSyncFeedback(null);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/sync`, {
        method: "POST",
        headers,
      });
      if (res.ok) {
        const data = await res.json();
        setSyncFeedback(`Sync complete! ${data.added} added, ${data.updated} updated, ${data.unchanged} unchanged.`);
        fetchDocuments();
      } else {
        setSyncFeedback("Sync failed. Check backend logs.");
      }
    } catch (err) {
      setSyncFeedback("Sync request failed.");
    } finally {
      setIsSyncing(false);
    }
  };

  const handleToggleClassification = async (docId: string, current: string) => {
    const nextClass = current === "public" ? "internal" : "public";
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/documents/${docId}/classification`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ classification: nextClass }),
      });
      if (res.ok) {
        fetchDocuments();
      } else {
        alert("Could not update document classification.");
      }
    } catch (err) {
      console.error("Failed to toggle classification:", err);
    }
  };

  const handleAddAdditionalDoc = () => {
    if (additionalDocs.length < 5) {
      setAdditionalDocs([...additionalDocs, { id: Math.random().toString(36).substring(7), file: null, title: "" }]);
    }
  };

  const handleRemoveAdditionalDoc = (indexOrId: number | string) => {
    if (typeof indexOrId === "number") {
      setAdditionalDocs(additionalDocs.filter((_, i) => i !== indexOrId));
    } else {
      setAdditionalDocs(additionalDocs.filter((d) => d.id !== indexOrId));
    }
  };

  const handleAdditionalDocChange = (indexOrId: number | string, field: "file" | "title", value: any) => {
    if (typeof indexOrId === "number") {
      const updated = [...additionalDocs];
      updated[indexOrId] = { ...updated[indexOrId], [field]: value };
      setAdditionalDocs(updated);
    } else {
      setAdditionalDocs(additionalDocs.map((d) => (d.id === indexOrId ? { ...d, [field]: value } : d)));
    }
  };

  const resetForm = () => {
    setCreateModalTab("url");
    setNewCompany("");
    setNewRole("");
    setNewJD("");
    setNewNotes("");
    setAttachedFile(null);
    setCoverLetterMode("none");
    setCoverLetterFile(null);
    setCoverLetterText("");
    setAdditionalDocs([]);
    setCreatedResult(null);
    setJobUrl("");
    setJobUrlNotes("");
    setIsStreamingUrl(false);
    setStreamStep("idle");
    setStreamProgress(0);
    setStreamMessage("");
    setStreamError(null);
    setUrlScreendump(null);
    setAnalyzedJobInfo(null);
    setStreamedCvText("");
    setStreamedCvSection("");
    setStreamedClText("");
    setStreamPreviewTab("cv");
  };

  const handleCreateFromUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedUrl = jobUrl.trim();
    if (!trimmedUrl || isStreamingUrl) return;

    setIsStreamingUrl(true);
    setStreamStep("fetching_page");
    setStreamProgress(5);
    setStreamMessage("Connecting to job advertisement URL & capturing webpage snapshot...");
    setStreamError(null);
    setUrlScreendump(null);
    setAnalyzedJobInfo(null);
    setStreamedCvText("");
    setStreamedCvSection("");
    setStreamedClText("");
    setStreamPreviewTab("cv");

    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/applications/from-url-stream`, {
        method: "POST",
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          url: trimmedUrl,
          notes: jobUrlNotes.trim() || undefined,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        if (res.status === 401) {
          alert(`Session expired or unauthorized (${res.status}). Redirecting to log in again...`);
          login();
          return;
        }
        setStreamStep("error");
        setStreamError(`Request failed (${res.status}): ${errText}`);
        return;
      }

      if (!res.body) {
        setStreamStep("error");
        setStreamError("Streaming response body not available.");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const rawEvent of parts) {
          const lines = rawEvent.split("\n");
          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const jsonStr = line.slice(5).trim();
            if (!jsonStr) continue;
            try {
              const evt = JSON.parse(jsonStr);
              if (evt.progress !== undefined) {
                setStreamProgress(evt.progress);
              }
              if (evt.message) {
                setStreamMessage(evt.message);
              }
              if (evt.step) {
                setStreamStep(evt.step);
                if (evt.step === "generating_cover_letter") {
                  setStreamPreviewTab("cl");
                }
              }

              if (evt.type === "screendump") {
                setUrlScreendump({
                  url: evt.url,
                  domain: evt.domain,
                  page_title: evt.page_title,
                  site_name: evt.site_name,
                  screenshot_data_url: evt.screenshot_data_url,
                });
              } else if (evt.type === "job_analyzed") {
                setAnalyzedJobInfo({
                  company: evt.company,
                  role: evt.role,
                  language: evt.language,
                  positioning_angle: evt.positioning_angle,
                  key_requirements: evt.key_requirements || [],
                });
              } else if (evt.type === "cv_stream") {
                setStreamPreviewTab("cv");
                if (evt.section) setStreamedCvSection(evt.section);
                if (evt.delta) {
                  setStreamedCvText((prev) => prev + evt.delta);
                }
              } else if (evt.type === "cv_ready") {
                if (evt.markdown) {
                  setStreamedCvText((prev) => prev || evt.markdown);
                }
              } else if (evt.type === "cl_stream") {
                setStreamPreviewTab("cl");
                if (evt.delta) {
                  setStreamedClText((prev) => prev + evt.delta);
                }
              } else if (evt.type === "cl_ready") {
                setStreamPreviewTab("cl");
                if (evt.markdown) {
                  setStreamedClText((prev) => prev || evt.markdown);
                }
              } else if (evt.type === "completed" && evt.result) {
                setStreamStep("completed");
                setStreamProgress(100);
                if (evt.result.cv_markdown) {
                  setStreamedCvText((prev) => prev || evt.result.cv_markdown);
                }
                if (evt.result.cover_letter_text) {
                  setStreamedClText((prev) => prev || evt.result.cover_letter_text);
                }
                setCreatedResult({
                  id: evt.result.id,
                  token: evt.result.token,
                  company: evt.result.company,
                  role: evt.result.role,
                  language: evt.result.language,
                  positioning_angle: evt.result.positioning_angle,
                  profile_url: evt.result.profile_url,
                  pdf_download_url: evt.result.pdf_download_url,
                  cover_letter_download_url: evt.result.cover_letter_download_url,
                  has_cover_letter: evt.result.has_cover_letter,
                  cover_letter_filename: evt.result.cover_letter_filename,
                  additional_documents_count: evt.result.additional_documents_count,
                  application_log: evt.result.application_log,
                });
                fetchApplications();
              } else if (evt.type === "error") {
                setStreamStep("error");
                setStreamError(evt.message || "An error occurred while generating the application.");
              }
            } catch (parseErr) {
              console.warn("Could not parse SSE event:", parseErr);
            }
          }
        }
      }
    } catch (err: any) {
      console.error("Error streaming application creation from URL:", err);
      setStreamStep("error");
      setStreamError(err?.message || "Network error while streaming application generation.");
    } finally {
      setIsStreamingUrl(false);
    }
  };

  const handleCreateApplication = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCompany.trim() || !newRole.trim() || !newJD.trim()) return;

    setIsGeneratingCV(true);
    try {
      const headers = await getAuthHeaders();

      const formData = new FormData();
      formData.append("company", newCompany.trim());
      formData.append("role", newRole.trim());
      formData.append("job_description", newJD.trim());
      if (newNotes.trim()) formData.append("notes", newNotes.trim());

      // CV upload (gets the tag stamped into it)
      if (attachedFile) {
        formData.append("cv_file", attachedFile);
      }

      // Cover letter
      if (coverLetterMode === "file" && coverLetterFile) {
        formData.append("cover_letter_file", coverLetterFile);
      } else if (coverLetterMode === "text" && coverLetterText.trim()) {
        formData.append("cover_letter_text", coverLetterText.trim());
      }

      // Additional documents
      additionalDocs.forEach((docItem) => {
        if (docItem.file) {
          formData.append("additional_files", docItem.file);
          formData.append("additional_titles", docItem.title.trim() || docItem.file.name);
        }
      });

      const res = await fetch(`${apiBase}/admin/applications`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setCreatedResult({
          id: data.id,
          profile_url: data.profile_url,
          pdf_download_url: data.pdf_download_url,
          has_cover_letter: data.has_cover_letter,
          additional_documents_count: data.additional_documents_count,
          application_log: data.application_log,
        });
        fetchApplications();
      } else {
        const errText = await res.text();
        console.error("Server error response:", res.status, errText);
        try {
          const errJson = JSON.parse(errText);
          if (res.status === 401) {
            alert(`Session expired or unauthorized (${res.status}): ${errJson.detail || errText}\n\nRedirecting to log in again...`);
            login();
            return;
          }
          alert(`Error creating application (${res.status}): ${errJson.detail || errText}`);
        } catch {
          if (res.status === 401) {
            alert(`Session expired (${res.status}). Redirecting to log in again...`);
            login();
            return;
          }
          alert(`Error creating application (${res.status}): ${errText}`);
        }
      }
    } catch (err: any) {
      console.error("Network or execution error creating application:", err);
      alert(`Error creating application: ${err?.message || err}`);
    } finally {
      setIsGeneratingCV(false);
    }
  };

  const loadApplicationDetail = async (id: string) => {
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/applications/${id}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setSelectedApp(data);
      }
    } catch (err) {
      console.error("Failed to load application detail:", err);
    }
  };

  const handleRevoke = async (id: string) => {
    if (!confirm("Are you sure you want to revoke this application token? Visitors will receive a 410 Gone error.")) return;
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/applications/${id}/revoke`, { method: "POST", headers });
      if (res.ok) {
        fetchApplications();
        if (selectedApp?.application.id === id) {
          loadApplicationDetail(id);
        }
      } else {
        alert(`Failed to revoke application (status ${res.status}).`);
      }
    } catch (err: any) {
      alert(`Failed to revoke application: ${err?.message || err}`);
    }
  };

  const handleDeleteApplication = async (id: string, company: string, role: string) => {
    if (!confirm(`Are you sure you want to permanently delete the application for "${company} — ${role}"?\n\nThis will immediately and permanently erase all database records, interaction logs, generated PDFs, and attached files.`)) return;
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/applications/${id}`, { method: "DELETE", headers });
      if (res.ok) {
        fetchApplications();
        if (selectedApp?.application.id === id) {
          setSelectedApp(null);
        }
      } else {
        alert(`Failed to delete application (status ${res.status}).`);
      }
    } catch (err: any) {
      alert(`Failed to delete application: ${err?.message || err}`);
    }
  };

  const handleRunCleanup = async () => {
    if (!confirm("Run 30-day retention cleanup?\n\nThis will permanently purge all applications and associated files that have been revoked for more than 30 days.")) return;
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBase}/admin/cleanup?retention_days=30`, { method: "POST", headers });
      if (res.ok) {
        const data = await res.json();
        alert(`Retention cleanup completed!\nPurged ${data.purged_count} expired application(s).`);
        fetchApplications();
      } else {
        alert(`Failed to run cleanup (status ${res.status}).`);
      }
    } catch (err: any) {
      alert(`Failed to run cleanup: ${err?.message || err}`);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-3 border-sky-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-slate-500 font-medium">Verifying Microsoft Entra credentials...</p>
        </div>
      </div>
    );
  }

  if (authMode === "entra" && !isAuthenticated) {
    return <EntraLoginCard />;
  }

  const filteredApps = applications.filter((app) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return app.company.toLowerCase().includes(q) || app.role.toLowerCase().includes(q);
  });

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      {/* Top Navbar */}
      <header className="bg-slate-900 text-white border-b border-slate-800 px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-sky-500 flex items-center justify-center font-bold text-slate-950 text-sm">
            {(process.env.NEXT_PUBLIC_CANDIDATE_NAME || "DB").slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h1 className="text-sm sm:text-base font-bold tracking-tight">
              {process.env.NEXT_PUBLIC_CANDIDATE_NAME || "DearBot"} — Application Hub
            </h1>
            <p className="text-[11px] text-slate-400">Recruiter Intelligence, CV Stamping &amp; Document Packaging</p>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {account && (
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300">
              <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span className="font-medium text-white">{account.name || account.username}</span>
            </div>
          )}

          <a
            href="https://eu.smith.langchain.com/o/default/projects/p/AI-augumented-CV"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold transition-colors border border-slate-700 shadow-xs cursor-pointer"
            title="Open LangSmith LLM Tracing & Observability Dashboard (EU)"
          >
            <Activity className="w-3.5 h-3.5 text-sky-400" />
            <span className="hidden sm:inline">LangSmith Traces</span>
            <ExternalLink className="w-3 h-3 text-slate-400" />
          </a>

          <button
            onClick={() => {
              resetForm();
              setShowCreateModal(true);
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs transition-colors shadow-sm cursor-pointer"
          >
            <Plus className="w-4 h-4" /> New Application Package
          </button>

          <button
            onClick={() => logout()}
            title="Sign out of Microsoft Entra ID"
            className="inline-flex items-center gap-1.5 px-2.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium transition-colors border border-slate-700 cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-6 flex-1">
        
        {/* Navigation Tabs & Search */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("applications")}
              className={`px-4 py-2 rounded-lg text-xs sm:text-sm font-semibold transition-colors cursor-pointer ${
                activeTab === "applications"
                  ? "bg-white text-slate-900 shadow-sm border border-slate-200"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Applications ({applications.length})
            </button>
            <button
              onClick={() => setActiveTab("knowledge")}
              className={`px-4 py-2 rounded-lg text-xs sm:text-sm font-semibold transition-colors cursor-pointer ${
                activeTab === "knowledge"
                  ? "bg-white text-slate-900 shadow-sm border border-slate-200"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Canonical Knowledge ({documents.length} docs)
            </button>
          </div>

          {activeTab === "applications" && (
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <button
                type="button"
                onClick={handleRunCleanup}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700 cursor-pointer shrink-0"
                title="Permanently purge applications revoked over 30 days ago"
              >
                <Clock className="w-3.5 h-3.5 text-slate-500" /> 30-Day Cleanup
              </button>
              <div className="relative w-full sm:w-64">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter by company or role..."
                  className="w-full pl-9 pr-3 py-1.5 text-xs bg-white rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
            </div>
          )}
        </div>

        {/* Tab 1: Applications */}
        {activeTab === "applications" && (
          <div className="grid lg:grid-cols-3 gap-6">
            
            {/* Applications List */}
            <div className="lg:col-span-2 space-y-4">
              {filteredApps.length === 0 ? (
                <div className="p-10 text-center bg-white rounded-2xl border border-slate-200 space-y-3">
                  <Briefcase className="w-10 h-10 text-slate-300 mx-auto" />
                  <h3 className="font-bold text-slate-700 text-base">
                    {searchQuery ? "No Matching Applications Found" : "No Applications Created Yet"}
                  </h3>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    {searchQuery
                      ? "Try searching for a different keyword or clear the search filter."
                      : "Create your first application package with CV, cover letter, and supporting documents to send to recruiters."}
                  </p>
                  {!searchQuery && (
                    <button
                      onClick={() => {
                        resetForm();
                        setShowCreateModal(true);
                      }}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs transition-colors cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5" /> Create Application
                    </button>
                  )}
                </div>
              ) : (
                filteredApps.map((app) => (
                  <div
                    key={app.id}
                    onClick={() => loadApplicationDetail(app.id)}
                    className={`p-5 bg-white rounded-2xl border transition-all cursor-pointer hover:shadow-md ${
                      selectedApp?.application.id === app.id
                        ? "border-sky-500 ring-2 ring-sky-500/20 shadow-sm"
                        : "border-slate-200"
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-bold text-slate-900 text-base">{app.company}</h3>
                          <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 border border-slate-200">
                            {app.role}
                          </span>
                          {!app.is_active && (
                            <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-600 border border-rose-200">
                              Revoked
                            </span>
                          )}
                        </div>

                        {/* Package Document Indicators */}
                        <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] text-slate-500">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-50 text-sky-700 font-medium">
                            <FileText className="w-3 h-3 text-sky-600" /> Stamped CV
                          </span>
                          {app.has_cover_letter && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-medium">
                              <BookOpen className="w-3 h-3 text-emerald-600" /> Cover Letter
                            </span>
                          )}
                          {(app.documents_count || 0) > 0 && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-50 text-purple-700 font-medium">
                              <Paperclip className="w-3 h-3 text-purple-600" /> {app.documents_count} doc{app.documents_count === 1 ? "" : "s"}
                            </span>
                          )}
                          <span>&bull; Created {new Date(app.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex flex-wrap items-center gap-2 pt-2 sm:pt-0">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            copyToClipboard(app.profile_url, app.id);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700 cursor-pointer"
                          title="Copy Recruiter Link"
                        >
                          {copiedToken === app.id ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                          <span>{copiedToken === app.id ? "Copied" : "Copy Link"}</span>
                        </button>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            const path = app.pdf_url?.startsWith("http")
                              ? new URL(app.pdf_url).pathname
                              : app.pdf_url || `/admin/applications/${app.id}/pdf`;
                            handleAuthenticatedDownload(path, `CV_${candidateFileSlug}_${app.company.replace(/\s+/g, "_")}.pdf`);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700 cursor-pointer"
                          title="Download Tagged CV"
                        >
                          <Download className="w-3.5 h-3.5 text-slate-500" /> PDF CV
                        </button>

                        <a
                          href={app.profile_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-sky-50 hover:bg-sky-100 border border-sky-200 text-xs font-medium text-sky-800"
                        >
                          <ExternalLink className="w-3.5 h-3.5" /> View
                        </a>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteApplication(app.id, app.company, app.role);
                          }}
                          className="inline-flex items-center gap-1 p-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 border border-rose-200 text-xs font-medium text-rose-700 cursor-pointer"
                          title="Permanent Delete (Waste Basket)"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Quick Analytics Bar */}
                    <div className="grid grid-cols-3 gap-3 pt-3.5 mt-3.5 border-t border-slate-100">
                      <div className="flex items-center gap-2">
                        <Eye className="w-4 h-4 text-slate-400" />
                        <div>
                          <span className="text-[11px] text-slate-400 block">Profile Views</span>
                          <span className="text-xs font-bold text-slate-800">{app.stats.profile_views}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <HelpCircle className="w-4 h-4 text-sky-600" />
                        <div>
                          <span className="text-[11px] text-slate-400 block">Questions Asked</span>
                          <span className="text-xs font-bold text-sky-700">{app.stats.questions}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Bot className="w-4 h-4 text-purple-600" />
                        <div>
                          <span className="text-[11px] text-slate-400 block">AI Bot Queries</span>
                          <span className="text-xs font-bold text-purple-700">{app.stats.ai_agent_interactions}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Application Detail & Intelligence Sidebar */}
            <div className="space-y-4">
              {selectedApp ? (
                <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-5 sticky top-6 shadow-xs">
                  <div className="flex items-start justify-between border-b border-slate-100 pb-3 gap-2">
                    <div>
                      <h3 className="font-bold text-slate-900 text-base">{selectedApp.application.company}</h3>
                      <p className="text-xs text-sky-700 font-semibold">{selectedApp.application.role}</p>
                    </div>
                    {selectedApp.application.is_active ? (
                      <button
                        onClick={() => handleRevoke(selectedApp.application.id)}
                        className="text-[11px] text-rose-600 hover:text-rose-800 font-medium px-2 py-1 rounded bg-rose-50 border border-rose-200 cursor-pointer"
                      >
                        Revoke Token
                      </button>
                    ) : (
                      <span className="text-[10px] uppercase font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                        Revoked
                      </span>
                    )}
                  </div>

                  {/* Shareable Link Box */}
                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                      Recruiter Profile Link
                    </span>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        readOnly
                        value={selectedApp.application.profile_url}
                        className="flex-1 text-xs font-mono bg-white border border-slate-200 rounded px-2 py-1 text-sky-800 truncate"
                      />
                      <button
                        type="button"
                        onClick={() => copyToClipboard(selectedApp.application.profile_url, "sidebar")}
                        className="p-1.5 rounded bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 cursor-pointer"
                        title="Copy"
                      >
                        {copiedToken === "sidebar" ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>

                  {/* Document Package in this application */}
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                      Uploaded Document Package
                    </h4>
                    <div className="space-y-1.5">
                      <button
                        type="button"
                        onClick={() =>
                          handleAuthenticatedDownload(
                            selectedApp.application.pdf_url || `/admin/applications/${selectedApp.application.id}/pdf`,
                            `CV_${candidateFileSlug}_${selectedApp.application.company.replace(/\s+/g, "_")}.pdf`
                          )
                        }
                        className="w-full p-2 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs flex items-center justify-between transition-colors cursor-pointer"
                      >
                        <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                          <FileText className="w-3.5 h-3.5 text-sky-600" /> Stamped CV (PDF)
                        </span>
                        <Download className="w-3.5 h-3.5 text-slate-400" />
                      </button>

                      {selectedApp.application.cover_letter?.has_file && (
                        <button
                          type="button"
                          onClick={() =>
                            handleAuthenticatedDownload(
                              `/admin/applications/${selectedApp.application.id}/cover-letter`,
                              selectedApp.application.cover_letter?.filename ||
                                `Personal_Letter_${candidateFileSlug}_${selectedApp.application.company.replace(/\s+/g, "_")}.pdf`
                            )
                          }
                          className="w-full p-2 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs flex items-center justify-between transition-colors cursor-pointer"
                        >
                          <span className="font-semibold text-slate-800 flex items-center gap-1.5 truncate mr-2">
                            <BookOpen className="w-3.5 h-3.5 text-emerald-600 shrink-0" /> Cover Letter ({selectedApp.application.cover_letter.filename || "PDF"})
                          </span>
                          <Download className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        </button>
                      )}

                      {selectedApp.application.cover_letter?.text && !selectedApp.application.cover_letter.has_file && (
                        <div className="p-2 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1">
                          <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                            <BookOpen className="w-3.5 h-3.5 text-emerald-600" /> Cover Letter (Text)
                          </span>
                          <p className="text-[11px] text-slate-600 italic line-clamp-2">
                            {selectedApp.application.cover_letter.text}
                          </p>
                        </div>
                      )}

                      {selectedApp.application.additional_documents && selectedApp.application.additional_documents.map((doc) => (
                        <a
                          key={doc.id}
                          href={doc.download_url}
                          target="_blank"
                          rel="noreferrer"
                          className="p-2 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs flex items-center justify-between transition-colors"
                        >
                          <span className="font-semibold text-slate-800 flex items-center gap-1.5 truncate mr-2">
                            <Paperclip className="w-3.5 h-3.5 text-purple-600 shrink-0" /> {doc.title}
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono shrink-0">
                            {formatBytes(doc.file_size)}
                          </span>
                        </a>
                      ))}
                    </div>
                  </div>

                  {/* Identified Organizations */}
                  {selectedApp.metrics.organizations && selectedApp.metrics.organizations.length > 0 && (
                    <div className="p-3 bg-sky-50 border border-sky-100 rounded-xl space-y-1.5">
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-sky-800 flex items-center gap-1">
                        <Building2 className="w-3.5 h-3.5 text-sky-600" /> Identified Networks
                      </h4>
                      <div className="flex flex-wrap gap-1">
                        {selectedApp.metrics.organizations.map((org) => (
                          <span key={org} className="px-2 py-0.5 rounded bg-white border border-sky-200 text-xs font-semibold text-sky-900 shadow-2xs">
                            {org}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Detected Clients */}
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                      Detected Clients &amp; Bots
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.keys(selectedApp.metrics.client_breakdown).length === 0 ? (
                        <span className="text-xs text-slate-400 italic">No visits recorded yet.</span>
                      ) : (
                        Object.entries(selectedApp.metrics.client_breakdown).map(([name, count]) => (
                          <span
                            key={name}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200"
                          >
                            <Bot className="w-3 h-3 text-slate-500" /> {name}: {count}
                          </span>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Question & Interaction Timeline */}
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                      <span>Timeline Events ({selectedApp.timeline.length})</span>
                      <a
                        href="https://eu.smith.langchain.com/o/default/projects/p/AI-augumented-CV"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-600 hover:text-sky-700 transition-colors normal-case"
                        title="Inspect full LLM prompt & response traces in LangSmith"
                      >
                        <Activity className="w-3 h-3 text-sky-500" />
                        <span>LangSmith Traces</span>
                        <ExternalLink className="w-2.5 h-2.5 text-slate-400" />
                      </a>
                    </h4>

                    {selectedApp.timeline.length === 0 ? (
                      <p className="text-xs text-slate-400 italic">No interactions recorded yet.</p>
                    ) : (
                      <div className="space-y-2 max-h-[22rem] overflow-y-auto pr-1">
                        {selectedApp.timeline.map((item) => (
                          <div key={item.id} className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1.5">
                            <div className="flex items-center justify-between text-[10px] text-slate-400 border-b border-slate-200/60 pb-1">
                              <span>{new Date(item.timestamp).toLocaleString()}</span>
                              <span className={`px-1.5 py-0.2 rounded font-bold uppercase text-[9px] ${
                                item.event_type?.includes("DOWNLOAD") ? "bg-emerald-100 text-emerald-800" :
                                item.event_type === "QUESTION" ? "bg-sky-100 text-sky-800" :
                                item.event_type === "PROFILE_VIEW" ? "bg-purple-100 text-purple-800" :
                                "bg-amber-100 text-amber-800"
                              }`}>
                                {item.event_type || "EVENT"}
                              </span>
                            </div>

                            {item.question ? (
                              <div className="space-y-1">
                                <p className="font-semibold text-slate-900">&ldquo;{item.question}&rdquo;</p>
                                <p className="text-slate-600 text-[11px] line-clamp-2">{item.answer}</p>
                              </div>
                            ) : item.event_type?.includes("DOWNLOAD") ? (
                              <p className="text-emerald-800 font-semibold text-[11px] flex items-center gap-1">
                                <Download className="w-3 h-3" /> Recruiter downloaded: {item.event_type.replace("_DOWNLOAD", "")}
                              </p>
                            ) : item.event_type === "PROFILE_VIEW" ? (
                              <p className="text-purple-800 font-medium text-[11px] flex items-center gap-1">
                                <Eye className="w-3 h-3" /> Recruiter opened web profile
                              </p>
                            ) : (
                              <p className="text-slate-600 text-[11px]">Machine discovery query</p>
                            )}

                            {item.organization && (
                              <div className="text-[10px] text-sky-800 font-medium flex items-center gap-1">
                                <Building2 className="w-3 h-3" /> {item.organization}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="p-8 bg-white rounded-2xl border border-slate-200 text-center text-slate-400 text-xs">
                  Select an application from the left to inspect its complete package, downloads, and question timeline.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Canonical Knowledge Base */}
        {activeTab === "knowledge" && (() => {
          const publicDocs = documents.filter((d) => d.classification === "public" && d.is_active !== false);
          const internalDocs = documents.filter((d) => d.classification === "internal" || d.is_active === false);
          const totalPublicChars = publicDocs.reduce((acc, d) => acc + d.character_count, 0);
          const estimatedTokens = Math.round(totalPublicChars / 4);

          return (
            <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-6 shadow-xs">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-base sm:text-lg font-bold text-slate-900 flex items-center gap-2">
                    <FolderSync className="w-5 h-5 text-sky-600" /> Evidence Source of Truth
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Reviewed local Markdown, with optional advanced source integrations
                  </p>
                </div>

                <button
                  onClick={handleSyncNow}
                  disabled={isSyncing}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs transition-colors disabled:opacity-50 cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                  {isSyncing ? "Syncing..." : "Sync Now"}
                </button>
              </div>

              {/* PRE-PUBLICATION SECURITY & PRIVACY AUDIT SCREEN */}
              <div className="p-4 bg-sky-50/70 border border-sky-200 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 text-sky-700" />
                    <h3 className="text-xs font-bold text-sky-950 uppercase tracking-wider">
                      Pre-Publication Security &amp; Privacy Audit
                    </h3>
                  </div>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-sky-100 text-sky-800 border border-sky-300">
                    Default-Internal Policy Active
                  </span>
                </div>
                <p className="text-xs text-sky-900 leading-relaxed">
                  Only documents explicitly verified and approved as <strong>PUBLIC</strong> are sent to the AI reasoning model during public recruiter queries. All newly discovered documents default to <strong>INTERNAL</strong> to prevent sensitive data exposure.
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1 text-xs">
                  <div className="p-2.5 bg-white rounded-lg border border-sky-100">
                    <span className="text-[10px] text-slate-500 block font-semibold">PUBLIC EXPOSED</span>
                    <span className="font-bold text-emerald-700">{publicDocs.length} of {documents.length} docs</span>
                  </div>
                  <div className="p-2.5 bg-white rounded-lg border border-sky-100">
                    <span className="text-[10px] text-slate-500 block font-semibold">INTERNAL PROTECTED</span>
                    <span className="font-bold text-slate-700">{internalDocs.length} docs</span>
                  </div>
                  <div className="p-2.5 bg-white rounded-lg border border-sky-100">
                    <span className="text-[10px] text-slate-500 block font-semibold">EXPOSED CHARACTERS</span>
                    <span className="font-bold text-slate-900">{totalPublicChars.toLocaleString()} chars</span>
                  </div>
                  <div className="p-2.5 bg-white rounded-lg border border-sky-100">
                    <span className="text-[10px] text-slate-500 block font-semibold">EST. TOKEN FOOTPRINT</span>
                    <span className="font-bold text-slate-900">~{estimatedTokens.toLocaleString()} tokens</span>
                  </div>
                </div>
              </div>

              {syncFeedback && (
                <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" /> {syncFeedback}
                </div>
              )}

              <div className="grid sm:grid-cols-2 gap-4">
                {documents.map((doc) => {
                  const isPublic = doc.classification === "public";
                  const isRemoved = doc.is_active === false;

                  return (
                    <div key={doc.id} className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-0.5">
                          <span className="font-bold text-xs sm:text-sm text-slate-900 block">{doc.title}</span>
                          <span className="text-xs text-slate-500 font-mono block truncate">{doc.filename}</span>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          {isRemoved ? (
                            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                              Removed From Drive
                            </span>
                          ) : (
                            <span
                              className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                                isPublic
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                  : "bg-amber-50 text-amber-700 border-amber-200"
                              }`}
                            >
                              {isPublic ? "Public (Approved)" : "Internal (Protected)"}
                            </span>
                          )}
                          <span className="text-[10px] font-mono text-slate-400">
                            hash: {doc.content_hash}
                          </span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200 text-[11px] text-slate-500">
                        <div className="space-x-2">
                          <span>{doc.character_count.toLocaleString()} chars</span>
                          <span>&bull; Synced {new Date(doc.last_synced).toLocaleDateString()}</span>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleToggleClassification(doc.id, doc.classification)}
                          className={`px-2.5 py-1 rounded-md font-semibold text-[11px] transition-colors cursor-pointer border ${
                            isPublic
                              ? "bg-slate-200 hover:bg-slate-300 text-slate-700 border-slate-300"
                              : "bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-600 shadow-xs"
                          }`}
                        >
                          {isPublic ? "Demote to Internal" : "Approve as Public"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}
      </div>

      {/* REBUILT CREATE APPLICATION MODAL */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-3 sm:p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[92vh] flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 my-auto">
            
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50 rounded-t-2xl">
              <div>
                <h3 className="font-bold text-slate-900 text-base">New Application Package</h3>
                <p className="text-[11px] text-slate-500">
                  Auto-tailor optimal CV &amp; personal letter from a job ad link, or upload manually
                </p>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Tab Bar (Default: From Job Link) */}
            {!createdResult && (
              <div
                role="tablist"
                aria-label="Application creation mode"
                className="px-6 pt-3 pb-0 bg-slate-50/70 border-b border-slate-200 flex items-center gap-2"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={createModalTab === "url"}
                  disabled={isStreamingUrl || isGeneratingCV}
                  onClick={() => setCreateModalTab("url")}
                  className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold rounded-t-xl border-b-2 transition-all cursor-pointer ${
                    createModalTab === "url"
                      ? "bg-white text-sky-700 border-sky-600 shadow-2xs"
                      : "text-slate-500 hover:text-slate-800 border-transparent"
                  }`}
                >
                  <Globe className="w-3.5 h-3.5 text-sky-600" />
                  <span>From Job Link</span>
                  <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-sky-100 text-sky-800 font-semibold">
                    Default
                  </span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={createModalTab === "manual"}
                  disabled={isStreamingUrl || isGeneratingCV}
                  onClick={() => setCreateModalTab("manual")}
                  className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold rounded-t-xl border-b-2 transition-all cursor-pointer ${
                    createModalTab === "manual"
                      ? "bg-white text-sky-700 border-sky-600 shadow-2xs"
                      : "text-slate-500 hover:text-slate-800 border-transparent"
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Manual Form &amp; Upload</span>
                </button>
              </div>
            )}

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto space-y-5 flex-1">
              {createdResult ? (
                <div className="space-y-4 py-3 text-center">
                  <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto shadow-xs">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <h4 className="font-bold text-slate-900 text-lg">Application Package Ready!</h4>
                  <p className="text-xs text-slate-600 max-w-md mx-auto">
                    {createdResult.company && createdResult.role ? (
                      <>
                        Tailored CV and Personal Letter created for{" "}
                        <b className="text-slate-900">{createdResult.role}</b> at{" "}
                        <b className="text-slate-900">{createdResult.company}</b>, digitally stamped with your verification link.
                      </>
                    ) : (
                      <>
                        Your CV has been digitally stamped with this application&apos;s unique verification tag. You can now send this link directly to the recruiter.
                      </>
                    )}
                  </p>

                  {/* If created from a job link, show the small screendump summary card */}
                  {urlScreendump && (
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center gap-3 text-left">
                      <img
                        src={urlScreendump.screenshot_data_url}
                        alt={`Screendump of ${urlScreendump.domain}`}
                        className="w-28 h-16 object-cover object-top rounded-lg border border-slate-300 shadow-2xs shrink-0 bg-white"
                      />
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-sky-100 text-sky-800">
                            {urlScreendump.domain}
                          </span>
                          {createdResult.language && (
                            <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                              {createdResult.language.toUpperCase()}
                            </span>
                          )}
                        </div>
                        <p className="text-xs font-bold text-slate-900 truncate">
                          {createdResult.role || urlScreendump.page_title} — {createdResult.company || urlScreendump.site_name}
                        </p>
                        <a
                          href={urlScreendump.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-sky-600 hover:underline truncate block"
                        >
                          {urlScreendump.url}
                        </a>
                      </div>
                    </div>
                  )}

                  <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-2 text-left">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      Recruiter Link to Send:
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={createdResult.profile_url}
                        className="w-full px-3 py-2 text-xs font-mono bg-white border border-slate-300 rounded-lg text-sky-900 select-all"
                      />
                      <button
                        type="button"
                        onClick={() => copyToClipboard(createdResult.profile_url, "created")}
                        className="px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1 cursor-pointer shrink-0"
                      >
                        {copiedToken === "created" ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedToken === "created" ? "Copied" : "Copy"}</span>
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-left text-xs pt-1">
                    <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="text-[10px] text-slate-400 block font-semibold">TAILORED CV</span>
                      <span className="font-bold text-slate-800">✓ Stamped PDF Ready</span>
                    </div>
                    <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="text-[10px] text-slate-400 block font-semibold">PERSONAL LETTER</span>
                      <span className="font-bold text-slate-800">
                        {createdResult.has_cover_letter ? "✓ Tailored PDF & Text" : "None"}
                      </span>
                    </div>
                    <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 col-span-2 sm:col-span-1">
                      <span className="text-[10px] text-slate-400 block font-semibold">POSITIONING</span>
                      <span className="font-bold text-slate-800 truncate block">
                        {createdResult.positioning_angle
                          ? createdResult.positioning_angle.split(":")[0]
                          : `${createdResult.additional_documents_count || 0} Extra Docs`}
                      </span>
                    </div>
                  </div>

                  {/* Generated Personal Letter & Tailored CV Preview */}
                  {(streamedClText || streamedCvText) && (
                    <div className="rounded-xl border border-slate-200 overflow-hidden bg-white text-left">
                      <div className="px-3.5 py-2 bg-slate-100 border-b border-slate-200 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => setStreamPreviewTab("cl")}
                            className={`px-2.5 py-1 rounded-md text-[11px] font-bold cursor-pointer transition-colors ${
                              streamPreviewTab === "cl"
                                ? "bg-emerald-700 text-white"
                                : "text-slate-600 hover:bg-slate-200"
                            }`}
                          >
                            Personal Letter ({streamedClText.length} chars)
                          </button>
                          <button
                            type="button"
                            onClick={() => setStreamPreviewTab("cv")}
                            className={`px-2.5 py-1 rounded-md text-[11px] font-bold cursor-pointer transition-colors ${
                              streamPreviewTab === "cv"
                                ? "bg-slate-900 text-white"
                                : "text-slate-600 hover:bg-slate-200"
                            }`}
                          >
                            Tailored CV ({streamedCvText.length} chars)
                          </button>
                        </div>
                        <span className="text-[10px] font-mono text-emerald-700 font-semibold">
                          ✓ Generated
                        </span>
                      </div>
                      <pre className="p-3.5 text-[11px] font-mono text-slate-700 bg-slate-50/60 max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                        {streamPreviewTab === "cl"
                          ? streamedClText || "No Personal Letter generated."
                          : streamedCvText || "No Tailored CV generated."}
                      </pre>
                    </div>
                  )}

                  <div className="flex flex-wrap justify-center gap-2.5 pt-3">
                    <button
                      type="button"
                      onClick={() =>
                        handleAuthenticatedDownload(
                          createdResult.pdf_download_url,
                          `CV_${candidateFileSlug}_${(createdResult.company || "Tailored").replace(/\s+/g, "_")}.pdf`
                        )
                      }
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs cursor-pointer"
                    >
                      <Download className="w-4 h-4" /> Download Stamped CV
                    </button>
                    {createdResult.has_cover_letter && (
                      <button
                        type="button"
                        onClick={() =>
                          handleAuthenticatedDownload(
                            createdResult.cover_letter_download_url ||
                              `/admin/applications/${createdResult.id}/cover-letter`,
                            createdResult.cover_letter_filename ||
                              `Personal_Letter_${candidateFileSlug}_${(createdResult.company || "Tailored").replace(/\s+/g, "_")}.pdf`
                          )
                        }
                        className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-xs cursor-pointer"
                      >
                        <BookOpen className="w-4 h-4" /> Download Personal Letter
                      </button>
                    )}
                    <a
                      href={createdResult.profile_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-200 text-xs font-semibold shadow-xs"
                    >
                      <ExternalLink className="w-4 h-4" /> Test Recruiter Page
                    </a>
                    <button
                      type="button"
                      onClick={() => {
                        setShowCreateModal(false);
                        resetForm();
                      }}
                      className="px-4 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold cursor-pointer"
                    >
                      Done
                    </button>
                  </div>
                </div>
              ) : createModalTab === "url" ? (
                /* TAB 1 (DEFAULT): FROM JOB AD LINK */
                <form onSubmit={handleCreateFromUrl} className="space-y-4">
                  <div className="p-4 bg-gradient-to-br from-sky-50/80 to-indigo-50/50 rounded-xl border border-sky-200/80 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <label className="block text-xs font-bold text-slate-900">
                          Paste Job Advertisement Link *
                        </label>
                        <p className="text-[11px] text-slate-600 mt-0.5">
                          Paste a link to any job ad webpage. The system will capture a screendump, analyze the role requirements, and stream an optimal tailored CV &amp; personal letter grounded strictly in your canonical evidence bank.
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-2">
                      <div className="relative flex-1">
                        <Globe className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                        <input
                          type="url"
                          required
                          disabled={isStreamingUrl}
                          value={jobUrl}
                          onChange={(e) => setJobUrl(e.target.value)}
                          placeholder="https://careers.company.com/jobs/chief-technology-officer"
                          className="w-full pl-9 pr-3 py-2 text-xs sm:text-sm bg-white rounded-lg border border-slate-300 focus:ring-2 focus:ring-sky-500 disabled:opacity-60"
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={isStreamingUrl || !jobUrl.trim()}
                        className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold disabled:opacity-50 transition-colors shadow-xs cursor-pointer shrink-0"
                      >
                        {isStreamingUrl ? (
                          <>
                            <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
                            <span>Tailoring Package...</span>
                          </>
                        ) : (
                          <>
                            <CheckCircle2 className="w-4 h-4" />
                            <span>Generate Optimal CV &amp; Letter</span>
                          </>
                        )}
                      </button>
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                        Optional Focus / Candidate Notes
                      </label>
                      <input
                        type="text"
                        disabled={isStreamingUrl}
                        value={jobUrlNotes}
                        onChange={(e) => setJobUrlNotes(e.target.value)}
                        placeholder="e.g. Emphasize B2B SaaS scaling, cybersecurity governance, and AI adoption"
                        className="w-full px-3 py-1.5 text-xs bg-white rounded-lg border border-slate-300 focus:ring-2 focus:ring-sky-500 disabled:opacity-60"
                      />
                    </div>
                  </div>

                  {/* LIVE SCREENDUMP + STREAMING STATUS PANEL */}
                  {streamStep !== "idle" && (
                    <div className="space-y-4 pt-1 animate-in fade-in">
                      {/* Small Screendump of Submitted Link + Extracted Job Summary */}
                      <div className="p-3.5 bg-slate-900 text-white rounded-xl border border-slate-800 shadow-sm">
                        <div className="flex flex-col sm:flex-row items-start gap-3.5">
                          {/* Small Screendump Preview */}
                          <div className="w-full sm:w-44 h-28 rounded-lg overflow-hidden border border-slate-700 bg-slate-950 shrink-0 relative flex items-center justify-center">
                            {urlScreendump ? (
                              <img
                                src={urlScreendump.screenshot_data_url}
                                alt={`Screendump of ${urlScreendump.domain}`}
                                className="w-full h-full object-cover object-top"
                              />
                            ) : (
                              <div className="flex flex-col items-center justify-center gap-1.5 p-2 text-center">
                                <div className="w-5 h-5 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
                                <span className="text-[10px] text-slate-400 font-mono truncate max-w-[140px]">
                                  Capturing screendump...
                                </span>
                              </div>
                            )}
                            <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-slate-950/85 text-[9px] font-mono text-sky-300 border border-slate-700">
                              SCREENDUMP
                            </span>
                          </div>

                          {/* Link Metadata & Detected Role Details */}
                          <div className="flex-1 min-w-0 space-y-1.5 w-full">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30">
                                {urlScreendump?.domain || "Fetching URL..."}
                              </span>
                              {analyzedJobInfo && (
                                <>
                                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                    {analyzedJobInfo.language === "sv" ? "Swedish (SV)" : "English (EN)"}
                                  </span>
                                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-purple-500/20 text-purple-200 border border-purple-500/30 truncate max-w-[220px]">
                                    {analyzedJobInfo.positioning_angle}
                                  </span>
                                </>
                              )}
                            </div>

                            <h5 className="text-xs sm:text-sm font-bold text-white truncate">
                              {analyzedJobInfo
                                ? `${analyzedJobInfo.role} — ${analyzedJobInfo.company}`
                                : urlScreendump?.page_title || jobUrl}
                            </h5>

                            <a
                              href={urlScreendump?.url || jobUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[11px] text-slate-400 hover:text-sky-300 truncate block font-mono"
                            >
                              {urlScreendump?.url || jobUrl}
                            </a>

                            {analyzedJobInfo?.key_requirements && analyzedJobInfo.key_requirements.length > 0 && (
                              <div className="pt-1 flex flex-wrap gap-1">
                                {analyzedJobInfo.key_requirements.slice(0, 3).map((req, i) => (
                                  <span
                                    key={i}
                                    className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700 truncate max-w-[240px]"
                                    title={req}
                                  >
                                    &bull; {req}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Streaming Progress Bar & Step Checklist */}
                      <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            {streamStep === "error" ? (
                              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                            ) : (
                              <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-sky-600 border-t-transparent rounded-full shrink-0" />
                            )}
                            <span className="text-xs font-bold text-slate-800 truncate">
                              {streamMessage || "Processing job link..."}
                            </span>
                          </div>
                          <span className="text-xs font-mono font-bold text-sky-700 shrink-0">
                            {streamProgress}%
                          </span>
                        </div>

                        <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-300 rounded-full ${
                              streamStep === "error" ? "bg-rose-500" : "bg-sky-600"
                            }`}
                            style={{ width: `${Math.max(5, streamProgress)}%` }}
                          />
                        </div>

                        {/* 4-Stage Status Pills for Page, Analysis, CV, and Personal Letter */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                          {[
                            { key: "fetching_page", label: "1. Screendump & Page", threshold: 24 },
                            { key: "analyzing_job", label: "2. Role Analysis", threshold: 44 },
                            { key: "generating_cv", label: "3. Tailored CV", threshold: 73 },
                            { key: "generating_cover_letter", label: "4. Personal Letter", threshold: 93 },
                          ].map((st) => {
                            const isDone = streamProgress >= st.threshold;
                            const isCurrent = streamStep === st.key;
                            return (
                              <div
                                key={st.key}
                                className={`px-2.5 py-1.5 rounded-lg border text-[11px] font-semibold flex items-center gap-1.5 ${
                                  isDone
                                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                                    : isCurrent
                                    ? "bg-sky-50 border-sky-300 text-sky-900 ring-1 ring-sky-400/40"
                                    : "bg-white border-slate-200 text-slate-400"
                                }`}
                              >
                                {isDone ? (
                                  <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                                ) : isCurrent ? (
                                  <span className="w-2 h-2 rounded-full bg-sky-600 animate-ping shrink-0" />
                                ) : (
                                  <span className="w-2 h-2 rounded-full bg-slate-300 shrink-0" />
                                )}
                                <span className="truncate">{st.label}</span>
                              </div>
                            );
                          })}
                        </div>

                        {streamError && (
                          <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 font-medium">
                            {streamError}
                          </div>
                        )}
                      </div>

                      {/* Live Stream Output Preview for CV and Personal Letter */}
                      {(streamedCvText || streamedClText) && (
                        <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
                          <div className="px-3.5 py-2 bg-slate-100 border-b border-slate-200 flex items-center justify-between gap-2">
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => setStreamPreviewTab("cv")}
                                className={`px-2.5 py-1 rounded-md text-[11px] font-bold cursor-pointer transition-colors ${
                                  streamPreviewTab === "cv"
                                    ? "bg-slate-900 text-white"
                                    : "text-slate-600 hover:bg-slate-200"
                                }`}
                              >
                                Tailored CV Stream ({streamedCvText.length} chars)
                              </button>
                              <button
                                type="button"
                                onClick={() => setStreamPreviewTab("cl")}
                                className={`px-2.5 py-1 rounded-md text-[11px] font-bold cursor-pointer transition-colors ${
                                  streamPreviewTab === "cl"
                                    ? "bg-emerald-700 text-white"
                                    : "text-slate-600 hover:bg-slate-200"
                                }`}
                              >
                                Personal Letter Stream ({streamedClText.length} chars)
                              </button>
                            </div>
                            {streamedCvSection && streamPreviewTab === "cv" && (
                              <span className="text-[10px] font-mono text-slate-500 truncate">
                                Section: {streamedCvSection}
                              </span>
                            )}
                          </div>
                          <pre className="p-3.5 text-[11px] font-mono text-slate-700 bg-slate-50/60 max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                            {streamPreviewTab === "cv"
                              ? streamedCvText || "Waiting for CV stream..."
                              : streamedClText || "Waiting for Personal Letter stream..."}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                    <button
                      type="button"
                      disabled={isStreamingUrl}
                      onClick={() => setShowCreateModal(false)}
                      className="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 hover:bg-slate-100 cursor-pointer disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                /* TAB 2: MANUAL UPLOAD & FORM */
                <form onSubmit={handleCreateApplication} className="space-y-5">
                  
                  {/* STEP 1: TARGET ROLE & COMPANY */}
                  <div className="space-y-3">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <Briefcase className="w-3.5 h-3.5 text-sky-600" /> 1. Opportunity Details
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">Company Name *</label>
                        <input
                          type="text"
                          required
                          value={newCompany}
                          onChange={(e) => setNewCompany(e.target.value)}
                          placeholder="e.g. Nordic Enterprise Bank"
                          className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">Target Role Title *</label>
                        <input
                          type="text"
                          required
                          value={newRole}
                          onChange={(e) => setNewRole(e.target.value)}
                          placeholder="e.g. Chief Technology Officer"
                          className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Job Description / Requirements *
                      </label>
                      <textarea
                        required
                        rows={3}
                        value={newJD}
                        onChange={(e) => setNewJD(e.target.value)}
                        placeholder="Paste the key responsibilities or criteria. Used solely to prioritize relevant evidence without hallucinating facts."
                        className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-sky-500"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Internal Candidate Notes (optional)
                      </label>
                      <input
                        type="text"
                        value={newNotes}
                        onChange={(e) => setNewNotes(e.target.value)}
                        placeholder="e.g. Recruiter: Sarah Jenkins. Highlight DORA and scale experience."
                        className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-sky-500"
                      />
                    </div>
                  </div>

                  {/* STEP 2: CV UPLOAD (GETS THE TAG) */}
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-sky-600" /> 2. CV Upload (Automatically Tagged)
                    </h4>
                    <div className="p-3.5 bg-sky-50/50 rounded-xl border border-dashed border-sky-300 space-y-2">
                      <p className="text-[11px] text-slate-600 leading-relaxed">
                        Upload your PDF CV. The system will <b>automatically stamp the unique verified URL tag</b> into the footer and inject AI discovery metadata into the PDF.
                      </p>
                      <input
                        type="file"
                        accept=".pdf,application/pdf"
                        onChange={(e) => {
                          if (e.target.files && e.target.files[0]) {
                            setAttachedFile(e.target.files[0]);
                          }
                        }}
                        className="text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-sky-100 file:text-sky-800 hover:file:bg-sky-200 cursor-pointer"
                      />
                      {attachedFile ? (
                        <div className="text-[11px] font-semibold text-emerald-700 flex items-center gap-1">
                          <Check className="w-3.5 h-3.5" /> Selected: {attachedFile.name} ({formatBytes(attachedFile.size)})
                        </div>
                      ) : (
                        <span className="text-[10px] text-slate-400 block italic">
                          If left blank, an executive PDF CV will be generated from canonical knowledge.
                        </span>
                      )}
                    </div>
                  </div>

                  {/* STEP 3: COVER LETTER */}
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <BookOpen className="w-3.5 h-3.5 text-sky-600" /> 3. Cover Letter (Optional)
                      </h4>
                      <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg text-xs">
                        <button
                          type="button"
                          onClick={() => setCoverLetterMode("file")}
                          className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors cursor-pointer ${
                            coverLetterMode === "file" ? "bg-white text-slate-900 shadow-2xs" : "text-slate-500"
                          }`}
                        >
                          Upload File
                        </button>
                        <button
                          type="button"
                          onClick={() => setCoverLetterMode("text")}
                          className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors cursor-pointer ${
                            coverLetterMode === "text" ? "bg-white text-slate-900 shadow-2xs" : "text-slate-500"
                          }`}
                        >
                          Write / Paste
                        </button>
                      </div>
                    </div>

                    {coverLetterMode === "file" ? (
                      <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                        <input
                          type="file"
                          accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                          onChange={(e) => {
                            if (e.target.files && e.target.files[0]) {
                              setCoverLetterFile(e.target.files[0]);
                            }
                          }}
                          className="text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-slate-200 file:text-slate-800 hover:file:bg-slate-300 cursor-pointer"
                        />
                        {coverLetterFile && (
                          <span className="text-[11px] font-semibold text-emerald-700 block">
                            ✓ Cover letter: {coverLetterFile.name} ({formatBytes(coverLetterFile.size)})
                          </span>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <textarea
                          rows={4}
                          value={coverLetterText}
                          onChange={(e) => setCoverLetterText(e.target.value)}
                          placeholder="Write or paste your personalized cover letter here. Recruiters can view it inline or download it."
                          className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-sky-500"
                        />
                      </div>
                    )}
                  </div>

                  {/* STEP 4: ADDITIONAL REQUESTED DOCUMENTS */}
                  <div className="space-y-3 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Paperclip className="w-3.5 h-3.5 text-sky-600" /> 4. Additional Documents (Certificates, References, etc.)
                      </h4>
                      <button
                        type="button"
                        onClick={addDocRow}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs transition-colors cursor-pointer"
                      >
                        <Plus className="w-3 h-3 text-sky-600" /> Add Document
                      </button>
                    </div>

                    {additionalDocs.length === 0 ? (
                      <p className="text-xs text-slate-400 italic bg-slate-50 p-3 rounded-xl border border-slate-200">
                        No additional documents added. Click &ldquo;Add Document&rdquo; if you need to attach recommendation letters, certificates, diplomas, or project samples.
                      </p>
                    ) : (
                      <div className="space-y-2.5">
                        {additionalDocs.map((docItem, idx) => (
                          <div
                            key={docItem.id}
                            className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex flex-col sm:flex-row items-stretch sm:items-center gap-2"
                          >
                            <input
                              type="text"
                              value={docItem.title}
                              onChange={(e) => updateDocRow(docItem.id, "title", e.target.value)}
                              placeholder={`Document Title (e.g. Reference Letter ${idx + 1})`}
                              className="flex-1 px-2.5 py-1.5 text-xs bg-white rounded-md border border-slate-300 focus:ring-2 focus:ring-sky-500"
                            />
                            <input
                              type="file"
                              onChange={(e) => {
                                if (e.target.files && e.target.files[0]) {
                                  updateDocRow(docItem.id, "file", e.target.files[0]);
                                  if (!docItem.title) {
                                    updateDocRow(docItem.id, "title", e.target.files[0].name.replace(/\.[^/.]+$/, ""));
                                  }
                                }
                              }}
                              className="text-[11px] text-slate-600 file:mr-2 file:py-1 file:px-2.5 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-slate-200 file:text-slate-800 hover:file:bg-slate-300 cursor-pointer max-w-xs"
                            />
                            <button
                              type="button"
                              onClick={() => removeDocRow(docItem.id)}
                              className="p-1.5 text-rose-500 hover:text-rose-700 hover:bg-rose-50 rounded-md transition-colors cursor-pointer self-end sm:self-auto"
                              title="Remove"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Submission Buttons */}
                  <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-100">
                    <button
                      type="button"
                      onClick={() => setShowCreateModal(false)}
                      className="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 hover:bg-slate-100 cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isGeneratingCV}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold disabled:opacity-50 transition-colors shadow-sm cursor-pointer"
                    >
                      {isGeneratingCV ? (
                        <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4" />
                      )}
                      <span>{isGeneratingCV ? "Creating & Stamping CV..." : "Create Application Package"}</span>
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AdminDashboardPage() {
  return (
    <EntraAuthProvider>
      <AdminDashboardContent />
    </EntraAuthProvider>
  );
}

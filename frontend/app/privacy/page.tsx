import Link from "next/link";
import { ArrowLeft, ShieldCheck, Lock, Eye, Trash2, Mail, Info, FileText } from "lucide-react";
import { PublicFooter } from "../components/PublicFooter";

export const metadata = {
  title: "Privacy & Telemetry Transparency | Interactive CV",
  description: "Information regarding operational telemetry, quality assurance tracking, visitor consent, and data lifecycle management on the interactive CV platform.",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col justify-between">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-10 sm:py-16 w-full space-y-10">
        {/* Navigation & Header */}
        <div className="space-y-4">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Home</span>
          </Link>
          <div className="border-b border-slate-200 pb-6 space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sky-50 text-sky-700 text-xs font-semibold border border-sky-200/60">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Transparency & Data Governance</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
              Privacy, Telemetry &amp; Quality Assurance Notice
            </h1>
            <p className="text-sm sm:text-base text-slate-600">
              Information on what data is processed, why it is collected, visitor consent, and automated data deletion when a job application is closed.
            </p>
          </div>
        </div>

        {/* Content Sections */}
        <div className="space-y-8 text-sm leading-relaxed text-slate-700">
          {/* Section 1: Main Purpose */}
          <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-slate-900 font-semibold text-base">
              <div className="p-2 rounded-lg bg-sky-50 text-sky-600">
                <Eye className="w-4 h-4" />
              </div>
              <h2>1. Primary Purpose of Telemetry &amp; Tracking</h2>
            </div>
            <p>
              The primary purpose of logging visitor and interaction telemetry on this platform is to <strong>ensure technical quality, system stability, and factual correctness</strong> throughout the recruitment and candidate screening process.
            </p>
            <p>
              By observing how recruiters, hiring teams, and AI evaluation agents interact with the profile, the platform verifies that questions are answered factually, documents are delivered reliably, and potential misunderstandings or technical anomalies are promptly diagnosed.
            </p>
          </div>

          {/* Section 2: What Data is Collected */}
          <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
            <div className="flex items-center gap-2.5 text-slate-900 font-semibold text-base">
              <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
                <FileText className="w-4 h-4" />
              </div>
              <h2>2. Information Collected</h2>
            </div>
            <p>
              When an application-specific link (<code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">/a/[token]</code>) is visited, the platform collects:
            </p>
            <ul className="list-disc pl-5 space-y-2 text-slate-600">
              <li>
                <strong>Network &amp; Connectivity Data:</strong> Linkable IP address, reverse DNS hostname, approximate geographic location (city, country, region), and autonomous system network / ISP.
              </li>
              <li>
                <strong>Device &amp; Client Metadata:</strong> Browser user-agent (including AI agent identification such as ChatGPT-User or ClaudeBot), display parameters, GPU renderer, logical CPU cores, approximate device memory, preferred language, and timezone.
              </li>
              <li>
                <strong>Recruiter &amp; Screening Interactions:</strong> Profile view timestamps, questions submitted to the AI assistant, synthesized factual answers, document download events (CV, Cover Letter, and supporting materials), and session dwell time.
              </li>
            </ul>
          </div>

          {/* Section 3: Consent by Use */}
          <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-slate-900 font-semibold text-base">
              <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
                <Lock className="w-4 h-4" />
              </div>
              <h2>3. Consent by Use</h2>
            </div>
            <p>
              By accessing this interactive CV platform, browsing its sections, downloading attached documents, or submitting questions to the AI assistant, <strong>you consent to the processing of your interaction telemetry</strong> as described in this notice.
            </p>
            <p className="text-xs text-slate-500 bg-slate-50 p-3 rounded-lg border border-slate-200/60">
              If you prefer that no interaction telemetry be processed, you may refrain from querying the interactive AI assistant or request traditional static PDF copies directly.
            </p>
          </div>

          {/* Section 4: Data Retention & Automated Deletion */}
          <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-slate-900 font-semibold text-base">
              <div className="p-2 rounded-lg bg-rose-50 text-rose-600">
                <Trash2 className="w-4 h-4" />
              </div>
              <h2>4. Retention Period &amp; Automated Deletion</h2>
            </div>
            <p>
              Visitor telemetry is strictly temporary and strictly tied to the lifecycle of the specific job application:
            </p>
            <ul className="list-disc pl-5 space-y-2 text-slate-600">
              <li>
                <strong>Immediate Purge on Revocation:</strong> As soon as an application is marked inactive, revoked, or closed by the user, all associated visitor interaction telemetry, IP records, questions, and device logs are <strong>permanently deleted</strong> from the database.
              </li>
              <li>
                <strong>Maximum Retention Limit:</strong> Any application that remains untouched is automatically scheduled for complete purging after 90 days of inactivity.
              </li>
              <li>
                <strong>No Third-Party Analytics Sharing:</strong> Telemetry is processed self-hosted within the application infrastructure on secure European servers and is never shared, sold, or synced to external advertising or analytics networks.
              </li>
            </ul>
          </div>

          {/* Section 5: Data Controller & Contact */}
          <div className="bg-white p-6 sm:p-8 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
            <div className="flex items-center gap-2.5 text-slate-900 font-semibold text-base">
              <div className="p-2 rounded-lg bg-amber-50 text-amber-600">
                <Mail className="w-4 h-4" />
              </div>
              <h2>5. Data Controller &amp; Inquiries</h2>
            </div>
            <p>
              The operator responsible for the self-hosted deployment of this platform:
            </p>
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-1 text-xs">
              <p className="font-semibold text-slate-800">{process.env.NEXT_PUBLIC_RESPONSIBLE_EDITOR || process.env.NEXT_PUBLIC_CANDIDATE_NAME || "Self-Hosted Operator"}</p>
              <p className="text-slate-600">{process.env.NEXT_PUBLIC_ORGANIZATION_NAME || "Self-Hosted Interactive CV Platform"}</p>
              {process.env.NEXT_PUBLIC_CONTACT_EMAIL && (
                <p className="text-slate-600">
                  Direct Contact:{" "}
                  <a
                    href={`mailto:${process.env.NEXT_PUBLIC_CONTACT_EMAIL}`}
                    className="font-medium text-sky-600 hover:text-sky-700 underline"
                  >
                    {process.env.NEXT_PUBLIC_CONTACT_EMAIL}
                  </a>
                </p>
              )}
            </div>
            <p>
              Any inquiries, deletion requests, or questions regarding data processing or quality tracking can be directed to the operator.
            </p>
          </div>

          {/* Section 6: Governance Notice */}
          <div className="bg-slate-50 p-6 rounded-2xl border border-slate-200 text-xs text-slate-500 space-y-2">
            <div className="flex items-center gap-2 font-semibold text-slate-700">
              <Info className="w-4 h-4 text-slate-400" />
              <span>Governance &amp; Privacy Notice</span>
            </div>
            <p>
              This self-hosted platform is designed to uphold European data protection standards (GDPR) and provide candidate-level transparency for interactions with screening systems and human recruiters.
            </p>
          </div>
        </div>
      </main>

      <PublicFooter className="mt-12" />
    </div>
  );
}

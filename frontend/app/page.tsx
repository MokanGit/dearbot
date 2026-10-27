import Link from "next/link";
import { ArrowRight, Bot, FileCheck2, SearchCheck } from "lucide-react";
import { PublicFooter } from "./components/PublicFooter";

export default function HomePage() {
  const candidateName = process.env.NEXT_PUBLIC_CANDIDATE_NAME;
  const candidateHeadline = process.env.NEXT_PUBLIC_CANDIDATE_HEADLINE;
  const orgUrl = process.env.NEXT_PUBLIC_ORGANIZATION_URL;

  return (
    <div className="dearbot-site min-h-screen">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="dearbot-nav">
        <Link className="dearbot-brand" href="/" aria-label="DearBot home">
          <span className="dearbot-mark" aria-hidden="true">D<span>B</span></span>
          <span>DearBot</span>
        </Link>
        <span className="dearbot-nav-label">Evidence-linked professional profiles</span>
        <Link className="dearbot-text-link" href="/privacy">Privacy</Link>
      </header>

      <main id="main-content">
        <section className="dearbot-home-hero">
          <div className="dearbot-kicker">
            <span className="dearbot-status-dot" aria-hidden="true" />
            Professional profile platform
          </div>
          <div className="dearbot-letter">
            <div className="dearbot-letter-meta" aria-hidden="true">
              <span>PROFILE / EVIDENCE-LINKED</span>
              <span>FORMAT / HUMAN + MACHINE</span>
            </div>
            <div className="dearbot-home-copy">
              <p className="dearbot-salutation">A clearer way to review professional experience.</p>
              <h1>
                Application material for people.<br />
                <em>Structured evidence for AI.</em>
              </h1>
              <p>
                DearBot brings together tailored documents, a focused role-fit summary and
                source-linked answers in one professional profile.
              </p>
              {candidateName && (
                <div className="dearbot-candidate-note">
                  <span>Profile owner</span>
                  <strong>{candidateName}</strong>
                  {candidateHeadline && <small>{candidateHeadline}</small>}
                </div>
              )}
            </div>
          </div>
          <div className="dearbot-home-actions">
            <p>Open the private application link you received to view the complete profile.</p>
            {orgUrl && (
              <a className="dearbot-button dearbot-button-dark" href={orgUrl} target="_blank" rel="noreferrer">
                About the profile owner <ArrowRight aria-hidden="true" />
              </a>
            )}
          </div>
        </section>

        <section className="dearbot-capability-strip" aria-label="Profile capabilities">
          <span>TAILORED DOCUMENTS</span><i aria-hidden="true">✳</i>
          <span>EVIDENCE-LINKED ANSWERS</span><i aria-hidden="true">✳</i>
          <span>MACHINE-READABLE PROFILE</span>
        </section>

        <section className="dearbot-overview" aria-labelledby="overview-title">
          <div className="dearbot-section-label">01 / What is included</div>
          <div className="dearbot-overview-heading">
            <h2 id="overview-title">One application.<br /><em>Three useful views.</em></h2>
            <p>
              Each shared profile is scoped to a specific opportunity and keeps the original
              documents close to the claims made about them.
            </p>
          </div>
          <div className="dearbot-feature-grid">
            <article>
              <span className="dearbot-feature-number">01</span>
              <FileCheck2 aria-hidden="true" />
              <h3>Application package</h3>
              <p>Tailored CV, cover letter and supporting documents in one place.</p>
            </article>
            <article>
              <span className="dearbot-feature-number">02</span>
              <SearchCheck aria-hidden="true" />
              <h3>Role-fit summary</h3>
              <p>A concise view of relevant qualifications, clearly separated from source material.</p>
            </article>
            <article>
              <span className="dearbot-feature-number">03</span>
              <Bot aria-hidden="true" />
              <h3>Evidence-linked Q&amp;A</h3>
              <p>Ask about experience and inspect the supporting excerpts behind each answer.</p>
            </article>
          </div>
        </section>
      </main>
      <PublicFooter candidateName={candidateName} />
    </div>
  );
}

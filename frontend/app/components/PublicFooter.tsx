import Link from "next/link";
import { ExternalLink } from "lucide-react";

type PublicFooterProps = {
  candidateName?: string;
  cvHref?: string;
  className?: string;
};

export function PublicFooter({ candidateName, cvHref, className = "" }: PublicFooterProps) {
  const resolvedName = candidateName || process.env.NEXT_PUBLIC_CANDIDATE_NAME;
  const orgUrl = process.env.NEXT_PUBLIC_ORGANIZATION_URL;

  return (
    <footer className={`dearbot-footer ${className}`}>
      <div className="dearbot-footer-inner">
        <div>
          <p className="dearbot-footer-title">
            &copy; {new Date().getFullYear()} {resolvedName || "DearBot"}
          </p>
          <p>Interactive application profile · Evidence-linked AI answers</p>
        </div>
        <nav aria-label="Footer navigation">
          {cvHref && <a href={cvHref} download>Download CV</a>}
          <Link href="/privacy">Privacy</Link>
          {orgUrl && (
            <a href={orgUrl} target="_blank" rel="noopener noreferrer">
              Profile owner <ExternalLink aria-hidden="true" />
            </a>
          )}
        </nav>
      </div>
      <div className="dearbot-footer-signature">
        <span className="dearbot-mark" aria-hidden="true">D<span>B</span></span>
        <span>Powered by DearBot · Open-source, self-hosted CV technology</span>
      </div>
    </footer>
  );
}

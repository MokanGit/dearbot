"use client";

import { useEffect, useRef, useState } from "react";
import { Maximize2, X } from "lucide-react";
import QRCode from "qrcode";

export function DemoQrCode({ targetUrl }: { targetUrl: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [qrImage, setQrImage] = useState("");
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let isCurrent = true;

    QRCode.toDataURL(targetUrl, {
      errorCorrectionLevel: "M",
      margin: 2,
      width: 768,
      color: {
        dark: "#11110f",
        light: "#ffffff",
      },
    }).then((image) => {
      if (isCurrent) setQrImage(image);
    });

    return () => {
      isCurrent = false;
    };
  }, [targetUrl]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);
    closeButtonRef.current?.focus();
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen]);

  return (
    <>
      <button
        type="button"
        className="dearbot-qr-trigger"
        onClick={() => setIsOpen(true)}
        aria-haspopup="dialog"
        disabled={!qrImage}
      >
        <span className="dearbot-qr-frame">
          {qrImage ? (
            <img src={qrImage} alt={`QR code linking to ${targetUrl}`} width="256" height="256" />
          ) : (
            <span className="dearbot-qr-loading" role="status">Generating QR code…</span>
          )}
        </span>
        <span>Enlarge for scanning <Maximize2 aria-hidden="true" /></span>
      </button>

      {isOpen && (
        <div className="dearbot-qr-backdrop" onMouseDown={() => setIsOpen(false)}>
          <div
            className="dearbot-qr-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="qr-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button
              ref={closeButtonRef}
              type="button"
              className="dearbot-qr-close"
              onClick={() => setIsOpen(false)}
              aria-label="Close enlarged QR code"
            >
              <X aria-hidden="true" />
            </button>
            <div className="dearbot-qr-dialog-copy">
              <span>DEARBOT / LIVE DEMO</span>
              <h2 id="qr-dialog-title">Scan to open the profile</h2>
              <p>Point your phone camera at the code. No app is required.</p>
            </div>
            <div className="dearbot-qr-dialog-image">
              <img src={qrImage} alt={`QR code linking to ${targetUrl}`} width="768" height="768" />
            </div>
            <a href={targetUrl} target="_blank" rel="noreferrer">{targetUrl}</a>
          </div>
        </div>
      )}
    </>
  );
}

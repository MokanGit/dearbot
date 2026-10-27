import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "DearBot — Evidence-linked professional profiles",
    template: "%s · DearBot",
  },
  description: "Interactive application profiles with tailored documents and evidence-linked AI answers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased flex flex-col">
        {children}
      </body>
    </html>
  );
}

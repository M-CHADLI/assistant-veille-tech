import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nauda Palisse — Veille Tech",
  description: "Assistant de veille technologique interne.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}

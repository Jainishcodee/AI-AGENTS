import type { Metadata, Viewport } from "next";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cognitive OS",
  description:
    "Six thinking engines analyse one decision, attack each other's reasoning, and commit to one recommendation with the dissent left intact.",
};

export const viewport: Viewport = {
  themeColor: "#08080a",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh antialiased">
        <Nav />
        {children}
      </body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Noir City",
  description:
    "A detective game set in Backlund, 1984. Work the case alone or with five others, on one shared clock.",
};

// Next injects `width=device-width, initial-scale=1` already; this is here for
// the phone browser chrome, which otherwise frames a very dark game in white.
// Zoom is deliberately left alone - pinching a map is the whole point.
export const viewport: Viewport = {
  themeColor: "#08090b",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* overscroll-none: dragging the map on a phone must not pull-to-refresh
          the page out from under the case. */}
      <body className="flex min-h-full flex-col overscroll-none">{children}</body>
    </html>
  );
}

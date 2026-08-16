import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { AuthProvider } from "@/features/auth/AuthProvider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AfyaCall Campaign Engine",
  description: "Campaign management and execution control plane",
  icons: { icon: "/afyacall-logo.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { TrendColorProvider } from "@/components/providers/TrendColorProvider";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Q-Agents",
  description: "Multi-agent financial analysis system",
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
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem('trend-color-mode')==='chinese')document.documentElement.classList.add('cn-mode')}catch(e){}`,
          }}
        />
      </head>
      <body className="flex min-h-full flex-col">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          storageKey="finance-agent-theme"
          disableTransitionOnChange={false}
        >
          <TrendColorProvider>
            <Navbar />
            <main className="container mx-auto flex-1 px-4 py-8">
              {children}
            </main>
            <Toaster />
          </TrendColorProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

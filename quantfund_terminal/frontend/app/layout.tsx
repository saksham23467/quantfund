import "./globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";
import { NavSidebar } from "@/components/NavSidebar";

export const metadata: Metadata = {
  title: "QuantFund Research Terminal",
  description: "Institutional quant research terminal for Indian markets",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <NavSidebar />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}

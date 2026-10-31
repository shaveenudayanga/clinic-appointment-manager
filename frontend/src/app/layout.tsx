import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Appointment book",
  description: "Appointment book for a specialist clinic",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-AU" className="h-full">
      <body className="h-full antialiased">{children}</body>
    </html>
  );
}

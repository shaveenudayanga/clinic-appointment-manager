import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Appointment book",
  description: "Appointment book for a specialist clinic",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-AU" className="h-full">
      {/* Browser extensions and the VS Code browser add attributes to <body>
          (e.g. class="vsc-initialized") before React hydrates. That is not a
          bug in this app, so ignore attribute mismatches on <body> only. */}
      <body className="h-full antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}

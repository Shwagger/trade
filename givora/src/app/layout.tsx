import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Givora — ideias de presente em 30 segundos",
  description:
    "Conte quem é a pessoa e a gente sugere três presentes que fazem sentido. Sem cadastro.",
};

export const viewport: Viewport = {
  themeColor: "#FFF8F2",
  width: "device-width",
  initialScale: 1,
  // Pas de maximumScale : bloquer le zoom sur un site public, c'est un
  // problème d'accessibilité, pas une optimisation mobile.
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <div className="mx-auto flex min-h-screen w-full max-w-lg flex-col px-5">
          {children}
        </div>
      </body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import { Archivo } from "next/font/google";
import { SessionBeacon } from "@/components/SessionBeacon";
import "./globals.css";

// Archivo (Omnibus-Type, Buenos Aires) : une grotesque dessinée pour les
// langues latino-américaines, avec un axe de largeur. La version large
// porte les questions, la normale le reste. system-ui ne choisissait rien.
const archivo = Archivo({
  subsets: ["latin", "latin-ext"],
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Givora — ideias de presente em 30 segundos",
  description:
    "Conte quem é a pessoa e a gente sugere três presentes que fazem sentido. Sem cadastro.",
  appleWebApp: {
    // Sur iOS c'est cette balise, pas le manifeste, qui décide de
    // l'affichage plein écran depuis l'écran d'accueil.
    capable: true,
    title: "Givora",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: "#FFF8F2",
  width: "device-width",
  initialScale: 1,
  // Le contenu passe sous l'encoche et la barre du bas : sans ça, une
  // app en standalone garde deux bandes blanches qui la trahissent.
  viewportFit: "cover",
  // Pas de maximumScale : bloquer le zoom sur un site public, c'est un
  // problème d'accessibilité, pas une optimisation mobile.
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={archivo.variable}>
      <body>
        <div className="mx-auto flex min-h-screen w-full max-w-lg flex-col px-5">
          {children}
        </div>
        <SessionBeacon />
      </body>
    </html>
  );
}

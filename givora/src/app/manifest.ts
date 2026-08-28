import type { MetadataRoute } from "next";

// Le manifeste transforme le site en application installable : « ajouter
// à l'écran d'accueil » donne une icône, un écran de lancement, et un
// affichage sans barre de navigateur. C'est la différence entre « un site
// que j'ai ouvert » et « une app que j'ai ».
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Givora — ideias de presente",
    short_name: "Givora",
    description: "Três ideias de presente em 30 segundos. Sem cadastro.",
    lang: "pt-BR",
    start_url: "/",
    // standalone : lancée depuis l'écran d'accueil, elle s'ouvre sans
    // barre d'URL. C'est ce qui change tout sur la perception.
    display: "standalone",
    orientation: "portrait",
    background_color: "#FFF8F2",
    theme_color: "#FFF8F2",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}

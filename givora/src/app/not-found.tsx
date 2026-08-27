import Link from "next/link";

// Sert aussi bien un /resultado/<id inconnu> qu'une URL tapée de travers.
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 text-center">
      <p className="text-5xl" aria-hidden>
        🎁
      </p>
      <p className="text-2xl font-bold">Não achamos esse pedido</p>
      <p className="text-base text-ink/60">
        O link pode ter expirado. É rápido refazer: são quatro toques.
      </p>
      <Link href="/" className="primary-btn mt-2 max-w-xs">
        Começar de novo
      </Link>
    </div>
  );
}

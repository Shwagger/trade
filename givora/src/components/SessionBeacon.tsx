"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

// Une requête par page vue, pour alimenter le dénominateur du taux de
// clic. Volontairement muette : si elle échoue, l'utilisateur ne doit
// rien voir — c'est de la mesure, pas du produit.
export function SessionBeacon() {
  const pathname = usePathname();

  useEffect(() => {
    void fetch("/api/session", { method: "POST", keepalive: true }).catch(() => {});
  }, [pathname]);

  return null;
}

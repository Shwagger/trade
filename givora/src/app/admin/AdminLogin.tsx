"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function AdminLogin({ configured }: { configured: boolean }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!configured) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 text-center">
        <p className="text-xl font-bold">Painel desativado</p>
        <p className="max-w-xs text-base text-ink/60">
          Defina <code className="rounded bg-ink/5 px-1">ADMIN_PASSWORD</code> nas
          variáveis de ambiente para liberar o acesso.
        </p>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await fetch("/api/admin-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (res.ok) router.refresh();
    else setError("Senha incorreta.");
  }

  return (
    <form onSubmit={submit} className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-bold">Painel</h1>
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Senha"
        autoComplete="current-password"
        className="w-full max-w-xs rounded-2xl border-2 border-ink/10 bg-white p-4 text-base outline-none focus:border-coral"
      />
      <button type="submit" className="primary-btn max-w-xs">
        Entrar
      </button>
      {error ? (
        <p className="text-base text-coral-dark" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

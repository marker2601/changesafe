import { History, ShieldCheck } from "lucide-react";

import type { PublicConfig } from "../types";

interface HeaderProps {
  config: PublicConfig | null;
}

export function Header({ config }: HeaderProps) {
  const replay = !config || config.mode === "replay";
  return (
    <header className="app-header">
      <a className="brand" href="#main-content" aria-label="ChangeSafe home">
        <ShieldCheck aria-hidden="true" strokeWidth={1.8} />
        <span>ChangeSafe</span>
      </a>
      <div className="environment-status" aria-label="Runtime mode">
        <span>
          <History aria-hidden="true" />
          {replay ? "Snapshot replay" : "Live DataHub"}
        </span>
        <span>
          <ShieldCheck aria-hidden="true" />
          {replay ? "No credentials required" : "Owner-gated publishing"}
        </span>
      </div>
    </header>
  );
}

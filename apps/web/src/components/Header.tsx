import { Activity, Network } from "lucide-react";

interface HeaderProps {
  reviewActivityAvailable: boolean;
  onOpenReviewActivity?: () => void;
}

export function Header({
  reviewActivityAvailable,
  onOpenReviewActivity,
}: HeaderProps) {
  return (
    <header className="app-header">
      <a className="brand" href="#main-content" aria-label="ChangeSafe home">
        <span className="brand-mark">
          <Network aria-hidden="true" />
        </span>
        <span>ChangeSafe</span>
      </a>
      {reviewActivityAvailable && onOpenReviewActivity ? (
        <button
          className="owner-activity-trigger"
          onClick={onOpenReviewActivity}
          type="button"
        >
          <Activity aria-hidden="true" />
          Review activity
        </button>
      ) : null}
    </header>
  );
}

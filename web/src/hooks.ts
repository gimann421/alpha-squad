import { useEffect, useState } from "react";
import { api } from "./api";

type LatestSeasonKey = "uncertainty" | "weekly" | "edge" | "evidence";

// D48: several views defaulted to a hardcoded season, the same failure mode D40 already fixed
// once for the rookie-class default (an already-played season silently looking current forever).
// One shared hook instead of six components independently re-implementing the same
// fetch-on-mount-with-fallback -- initializes to `fallback` and swaps to the real latest season
// for `key` as soon as `/seasons/latest` resolves, or stays on `fallback` if that table is
// empty or the request fails.
export function useLatestSeason(key: LatestSeasonKey, fallback: number): number {
  const [season, setSeason] = useState(fallback);

  useEffect(() => {
    api
      .getLatestSeasons()
      .then((latest) => {
        const value = latest[key];
        if (value != null) setSeason(value);
      })
      .catch(() => {
        // Per-view season input still works with `fallback`; this is a convenience default,
        // not a hard dependency, so a fetch failure here must not become a page-level error.
      });
    // Runs once on mount only -- the season input remains user-editable afterward.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return season;
}

import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router";
import { ExplanationContent } from "../components/ExplanationContent";
import { Header } from "../components/Header";
import { PatchOverlay } from "../components/PatchOverlay";
import { Button } from "../components/ui/button";
import { Loader2 } from "lucide-react";
import type { AnalysisResult } from "../types";
import {
  getAnalysisVerdict,
  isInferenceFailed,
  resolveDisplayedExplanation,
} from "../lib/analysisDisplay";

function formatReportDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, { dateStyle: "long", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function ResultsPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [explanation, setExplanation] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("artguard_latest_result");
    if (!stored) {
      navigate("/upload");
      return;
    }

    try {
      const parsed = JSON.parse(stored) as AnalysisResult;
      setResult(parsed);

      setExplanation(resolveDisplayedExplanation(parsed));
    } catch {
      navigate("/upload");
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  if (isLoading || !result) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="size-6 animate-spin" />
      </div>
    );
  }

  const failed = isInferenceFailed(result);
  const scorePercent = failed ? null : Math.round(result.score * 100);
  const verdict = getAnalysisVerdict(result);

  return (
    <div className="min-h-screen bg-background print:bg-white">
      <div className="print:hidden">
        <Header />
      </div>

      <main className="mx-auto max-w-2xl px-6 py-16 text-center print:max-w-none print:px-10 print:py-8 print:text-left">
        {/* Print-only cover: metadata + structure for PDF / print */}
        <div className="mb-10 hidden border-b border-border pb-8 print:mb-10 print:block print:border-neutral-300">
          <h1 className="font-serif text-3xl font-normal text-foreground">ArtGuard</h1>
          <p className="mt-1 font-sans text-sm text-muted-foreground">Analysis report</p>
          <dl className="mt-8 grid gap-1 font-sans text-sm">
            <div className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-2">
              <dt className="text-muted-foreground">Artist</dt>
              <dd className="min-w-0 text-foreground">
                {result.artistName.trim() || "-"}
              </dd>
              <dt className="text-muted-foreground">Artwork</dt>
              <dd className="min-w-0 text-foreground">
                {result.artworkName.trim() || "-"}
              </dd>
              <dt className="text-muted-foreground">File</dt>
              <dd className="min-w-0 break-all text-foreground">
                {result.fileName || "-"}
              </dd>
              <dt className="text-muted-foreground">Generated</dt>
              <dd className="text-foreground">{formatReportDate(result.timestamp)}</dd>
            </div>
          </dl>
        </div>

        {/* Image */}
        <div className="mb-10 print:mb-8 print:break-inside-avoid">
          {result.image && (
            <div className="relative inline-block print:max-w-md">
              {result.patchData?.length ? (
                <PatchOverlay
                  imageSrc={result.image}
                  patchData={result.patchData}
                  imageWidth={result.imageWidth}
                  imageHeight={result.imageHeight}
                />
              ) : (
                <img
                  src={result.image}
                  alt=""
                  className="mx-auto max-h-[320px] object-contain rounded"
                />
              )}
            </div>
          )}
        </div>

        {/* Score: mean of per-patch authenticity probabilities */}
        <div className="mb-6 print:mb-8">
          <div className="text-6xl font-serif tabular-nums text-foreground print:text-5xl">
            {scorePercent !== null ? `${scorePercent}%` : "-"}
          </div>

          {/* Scientific progress bar */}
          <div className="mt-4 mx-auto w-full max-w-md">
            <div className="h-[2px] bg-border relative">
              <div
                className="absolute top-0 left-0 h-full bg-foreground/80 transition-all"
                style={{
                  width: scorePercent !== null ? `${scorePercent}%` : "0%",
                }}
              />
            </div>
          </div>

          <p className="mt-3 text-xs text-muted-foreground tracking-wide print:text-left">
            AUTHENTICITY CONFIDENCE
          </p>
          <p className="mt-2 text-xs text-muted-foreground/80 max-w-md mx-auto leading-relaxed print:mx-0 print:text-left">
            Mean of per-patch authenticity scores
          </p>
        </div>

        {/* Verdict */}
        <div className="mb-8 print:mb-6">
          <p className={`text-lg font-medium ${verdict.color}`}>
            {verdict.text}
          </p>
        </div>

        {/* Explanation (structured: prose + per-patch evidence lines from RAG) */}
        <section
          aria-label="Explanation"
          className="mb-12 max-w-xl mx-auto text-left print:mx-0 print:mb-10 print:max-w-none"
        >
          <h2 className="mb-4 hidden font-serif text-xl font-normal text-foreground print:block">
            Explanation
          </h2>
          <ExplanationContent text={explanation} />
        </section>

        {/* Actions */}
        <div className="space-y-3 print:hidden">
          <Button asChild className="w-full">
            <Link to="/upload">Analyze another artwork</Link>
          </Button>

          <Button variant="outline" className="w-full" type="button" onClick={() => window.print()}>
            Download
          </Button>
        </div>
      </main>
    </div>
  );
}

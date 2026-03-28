import type { ReactNode } from "react";
import { Link } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Header } from "../components/Header";
import { cn } from "../components/ui/utils";
import { artAsset } from "../lib/artAssets";

const ARTWORKS = [
  {
    src: artAsset("starry-night.jpg"),
    artist: "Vincent van Gogh",
    title: "The Starry Night",
    year: "1889",
  },
  {
    src: artAsset("girl-with-pearl-earring.jpg"),
    artist: "Johannes Vermeer",
    title: "Girl with a Pearl Earring",
    year: "c. 1665",
  },
  {
    src: artAsset("mona-lisa.jpg"),
    artist: "Leonardo da Vinci",
    title: "Mona Lisa",
    year: "c. 1503–1519",
  },
  {
    src: artAsset("rembrandt-self-portrait.jpg"),
    artist: "Rembrandt",
    title: "Self-Portrait",
    year: "c. 1660",
  },
] as const;

const PIPELINE_LINES = [
  "Upload — image with artist name and title for retrieval.",
  "Patches — 224 × 224 px grid per Schaerf et al. (2023).",
  "Swin Transformer — per-patch scores, mean-pooled to a painting-level signal.",
  "Explanation — RAG-grounded narrative where enabled (Claude, Bedrock, OpenSearch).",
] as const;

/** Full-bleed image cell: no gap, credits overlaid at top. */
function MosaicImage({
  art,
  className,
}: {
  art: (typeof ARTWORKS)[number];
  className?: string;
}) {
  return (
    <figure
      className={cn(
        "relative isolate min-h-[min(44vh,260px)] w-full overflow-hidden bg-neutral-900 md:min-h-0 md:h-full",
        className,
      )}
    >
      <img
        src={art.src}
        alt=""
        className="absolute inset-0 h-full w-full object-cover"
        loading="lazy"
        decoding="async"
      />
      <figcaption className="pointer-events-none absolute inset-x-0 top-0 z-10 bg-gradient-to-b from-black/80 via-black/35 to-transparent px-5 pt-5 pb-16 md:px-8 md:pt-8 md:pb-20">
        <p className="font-serif text-xs text-white/95 md:text-sm">
          {art.artist}
        </p>
        <p className="mt-1 font-sans text-[10px] text-white/75 md:text-xs">
          {art.title}, {art.year}
        </p>
      </figcaption>
    </figure>
  );
}

function MosaicTextTile({
  className,
  title,
  children,
}: {
  className?: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex min-h-[min(40vh,240px)] flex-col justify-center px-8 py-12 md:min-h-0 md:h-full md:px-10 lg:px-12 lg:py-14",
        className,
      )}
    >
      <h2 className="font-serif text-xl font-normal text-foreground md:text-2xl lg:text-[1.65rem]">
        {title}
      </h2>
      <div className="mt-5 font-sans text-sm leading-relaxed text-muted-foreground md:text-[0.9375rem] lg:mt-6">
        {children}
      </div>
    </div>
  );
}

/** One mosaic row: 4 columns on md+, gapless. */
function MosaicRow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 md:grid-cols-4 md:gap-0",
        "md:min-h-[min(50vh,500px)] lg:min-h-[min(60vh,600px)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function HomePage() {
  const { isAuthenticated } = useAuth();

  const primaryHref = isAuthenticated ? "/upload" : "/signup";
  const secondaryHref = isAuthenticated ? "/history" : "/login";
  const secondaryLabel = isAuthenticated ? "History" : "Log in";

  return (
    <div className="min-h-screen bg-background text-foreground antialiased">
      <Header
        showAuthLinks={!isAuthenticated}
        authLinkText="Log In"
        authLinkTo="/login"
      />

      {/* Editorial title — generous whitespace, reference-style tracking */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-4xl px-6 py-20 md:py-28 lg:py-36">
          <h1 className="text-center font-serif text-[1.65rem] font-normal uppercase leading-[1.2] tracking-[0.14em] text-foreground md:text-3xl lg:text-4xl">
            Shaping tomorrow&apos;s art authentication with AI
          </h1>
          <p className="mx-auto mt-12 max-w-md text-center font-sans text-sm leading-relaxed text-muted-foreground md:mt-14 md:text-base">
            Patch-level vision scoring and grounded explanations — a transparent
            layer between images and expert judgment.
          </p>
          <p className="mt-10 text-center font-sans text-sm text-muted-foreground">
            <Link
              to={primaryHref}
              className="text-foreground underline decoration-border underline-offset-[6px]"
            >
              {isAuthenticated ? "Analyze artwork" : "Get started"}
            </Link>
            <span className="mx-3 text-border" aria-hidden>
              |
            </span>
            <Link
              to={secondaryHref}
              className="underline decoration-border underline-offset-[6px]"
            >
              {secondaryLabel}
            </Link>
          </p>
        </div>
      </section>

      {/* Gapless 4-column mosaic — B&W tile backgrounds */}
      <section className="w-full border-b border-border">
        {/* Row 1: image | image — text spans half grid (2 cols) */}
        <MosaicRow>
          <MosaicImage art={ARTWORKS[0]} className="md:col-span-2" />
          <MosaicTextTile
            title="ArtGuard"
            className="bg-neutral-100 md:col-span-2"
          >
            <p>
              Our system evaluates authenticity using proprietary patch-level
              models and retrieval-grounded explanations — published methods,
              structured outputs, and no substitute for connoisseurship.
            </p>
          </MosaicTextTile>
        </MosaicRow>

        {/* Row 2: two text tiles | wide image */}
        <MosaicRow>
          <MosaicTextTile
            title="Digital workflow"
            className="border-t border-border bg-background md:col-span-1 md:border-t-0 md:border-r md:border-border"
          >
            <p>
              Upload photographs with metadata, run analyses, and keep a
              searchable history for catalogues and due diligence.
            </p>
          </MosaicTextTile>
          <MosaicTextTile
            title="Fast, objective signal"
            className="border-t border-border bg-neutral-200 md:col-span-1 md:border-t-0 md:border-r md:border-border"
          >
            <p>
              Receive model-driven scores and narratives without shipping
              physical works — then pair results with qualified experts where it
              matters.
            </p>
          </MosaicTextTile>
          <MosaicImage
            art={ARTWORKS[1]}
            className="border-t border-border md:col-span-2 md:border-t-0"
          />
        </MosaicRow>

        {/* Row 3: wide image | two text tiles */}
        <MosaicRow>
          <MosaicImage
            art={ARTWORKS[2]}
            className="border-t border-border md:col-span-2 md:border-t-0 md:border-r md:border-border"
          />
          <MosaicTextTile
            title="Workflow"
            className="border-t border-border bg-background md:col-span-1 md:border-t-0 md:border-r md:border-border"
          >
            <p>
              Upload, analyze at patch resolution, and review reports with
              scores, context, and explanation where enabled.
            </p>
          </MosaicTextTile>
          <MosaicTextTile
            title="Use & limitations"
            className="border-t border-border bg-neutral-300/60 md:col-span-1 md:border-t-0"
          >
            <p>
              Outputs support decisions; they are not certificates of
              authenticity.
              .
            </p>
          </MosaicTextTile>
        </MosaicRow>


      </section>

      <footer className="border-t border-border">
        <div className="mx-auto max-w-6xl px-6 py-10 md:py-12">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <p className="font-serif text-base text-foreground">ArtGuard</p>

            <nav className="flex flex-row flex-wrap gap-4 font-sans text-sm text-muted-foreground md:justify-end">
              <Link to="/upload" className="hover:text-foreground">
                Analyze
              </Link>
              <Link to="/history" className="hover:text-foreground">
                History
              </Link>
              {isAuthenticated ? (
                <Link to="/profile" className="hover:text-foreground">
                  Profile
                </Link>
              ) : (
                <>
                  <Link to="/login" className="hover:text-foreground">
                    Log in
                  </Link>
                  <Link to="/signup" className="hover:text-foreground">
                    Sign up
                  </Link>
                </>
              )}
            </nav>
          </div>

          <div className="mt-8 flex flex-col gap-2 text-xs text-muted-foreground md:flex-row md:justify-between">
            <p>Results are AI-assisted estimates. Consult qualified experts.</p>
            <p>© {new Date().getFullYear()} ArtGuard</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

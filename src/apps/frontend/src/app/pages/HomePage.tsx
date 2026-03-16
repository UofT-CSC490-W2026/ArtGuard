import { Link } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import {
  Upload,
  Brain,
  History,
  ArrowRight,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";

export function HomePage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen bg-background">
      <Header
        showAuthLinks={!isAuthenticated}
        authLinkText="Log In"
        authLinkTo="/login"
      />

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border bg-card">
        <div className="container mx-auto px-4 py-20 md:py-28">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="font-serif text-4xl md:text-5xl lg:text-6xl font-semibold text-foreground tracking-tight mb-6">
              Know what you&apos;re buying with{" "}
              <span className="text-accent-warm">Confidence</span>.
            </h1>

            <p className="font-sans text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed">
              ArtGuard uses state-of-the-art machine learning to analyze artwork
              and flag potential forgeries — for collectors, galleries, and institutions.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              {isAuthenticated ? (
                <>
                  <Button asChild size="lg" className="text-base px-8 font-sans rounded-md">
                    <Link to="/upload">
                      <Upload className="size-5 mr-2" />
                      Analyze artwork
                    </Link>
                  </Button>
                  <Button
                    asChild
                    size="lg"
                    variant="outline"
                    className="text-base px-8 font-sans rounded-md border-border"
                  >
                    <Link to="/history">
                      <History className="size-5 mr-2" />
                      History
                    </Link>
                  </Button>
                </>
              ) : (
                <>
                  <Button asChild size="lg" className="text-base px-8 font-sans rounded-md">
                    <Link to="/signup">
                      Get started
                      <ArrowRight className="size-5 ml-2" />
                    </Link>
                  </Button>
                  <Button
                    asChild
                    size="lg"
                    variant="outline"
                    className="text-base px-8 font-sans rounded-md border-border"
                  >
                    <Link to="/login">Log in</Link>
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="text-center mb-14">
            <h2 className="font-serif text-3xl font-semibold text-foreground mb-4">
              How it works
            </h2>
            <p className="font-sans text-muted-foreground max-w-xl mx-auto">
              Three simple steps to verify artwork authenticity
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            {[
              {
                step: "01",
                icon: Upload,
                title: "Upload",
                description:
                  "Send an image and artist or artwork name.",
              },
              {
                step: "02",
                icon: Brain,
                title: "Analyze",
                description:
                  "The model checks for patterns associated with forgeries.",
              },
              {
                step: "03",
                icon: ShieldCheck,
                title: "Results",
                description:
                  "You get a score and a plain-language explanation.",
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="inline-flex items-center justify-center size-14 rounded-md bg-muted border border-border text-foreground mb-5 font-mono text-xs font-medium">
                  {item.step}
                </div>
                <div className="relative inline-flex items-center justify-center size-12 rounded-md bg-accent-warm-muted text-accent-warm border border-amber-200/60 mb-4">
                  <item.icon className="size-6" strokeWidth={1.5} />
                </div>
                <h3 className="font-serif text-xl font-semibold text-foreground mb-2">
                  {item.title}
                </h3>
                <p className="font-sans text-muted-foreground leading-relaxed text-sm">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 bg-card border-y border-border">
        <div className="container mx-auto px-4">
          <div className="text-center mb-14">
            <h2 className="font-serif text-3xl font-semibold text-foreground mb-4">
              Built for serious use
            </h2>
            <p className="font-sans text-muted-foreground max-w-xl mx-auto">
              Everything you need for artwork authentication
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {[
              {
                icon: ScanSearch,
                title: "Forgery scoring",
                description:
                  "A 0–1 score from authentic to forged, with clear interpretation.",
              },
              {
                icon: ShieldCheck,
                title: "Explanations",
                description:
                  "Human-readable reasoning for every result, not just a number.",
              },
              {
                icon: Upload,
                title: "Batch and history",
                description:
                  "Run multiple analyses and keep a searchable record.",
              },
            ].map((feature) => (
              <Card
                key={feature.title}
                className="border border-border hover:border-accent-warm/30 transition-colors rounded-md overflow-hidden"
              >
                <CardContent className="pt-6 pl-6 border-l-2 border-l-accent-warm/50">
                  <div className="size-10 rounded-md bg-accent-warm-muted text-accent-warm flex items-center justify-center mb-4 border border-amber-200/60">
                    <feature.icon className="size-5" strokeWidth={1.5} />
                  </div>
                  <h3 className="font-serif font-semibold text-foreground mb-2">
                    {feature.title}
                  </h3>
                  <p className="font-sans text-sm text-muted-foreground leading-relaxed">
                    {feature.description}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="max-w-2xl mx-auto text-center">
            <h2 className="font-serif text-3xl font-semibold text-foreground mb-4">
              Ready to authenticate?
            </h2>
            <p className="font-sans text-muted-foreground mb-8">
              No art expertise required. Start with a single image.
            </p>
            <Button asChild size="lg" className="text-base px-8 font-sans rounded-md">
              <Link to={isAuthenticated ? "/upload" : "/signup"}>
                {isAuthenticated ? "Upload artwork" : "Create account"}
                <ArrowRight className="size-5 ml-2" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-card py-8">
        <div className="container mx-auto px-4 text-center">
          <p className="font-serif text-foreground font-semibold">
            ArtGuard
          </p>
          <p className="font-sans text-sm text-muted-foreground mt-1">
            Art forgery detection
          </p>
        </div>
      </footer>
    </div>
  );
}

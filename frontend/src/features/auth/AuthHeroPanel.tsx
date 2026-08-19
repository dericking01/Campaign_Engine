import Image from "next/image";
import { Activity, ShieldCheck, Zap } from "lucide-react";

const STATS = [
  { icon: Activity, label: "Customers reachable", value: "17M+" },
  { icon: Zap, label: "Dispatch throughput", value: "200 TPS" },
  { icon: ShieldCheck, label: "DND & consent", value: "Always enforced" },
];

/** Left-side hero of the split-screen login layout. The logo's "afya"
 * wordmark is dark teal, which would disappear directly on this dark
 * background - so it sits in a small white card instead, exactly as it
 * would on any light surface, while the panel itself carries the brand
 * through color, not the raster logo. */
export function AuthHeroPanel() {
  return (
    <div className="relative hidden h-full flex-col justify-between overflow-hidden bg-brand-900 px-12 py-12 text-white lg:flex xl:px-16">
      {/* Decorative depth: soft radial glows + a faint dotted grid. Restrained
          on purpose - texture, not noise. */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 -top-24 h-[420px] w-[420px] rounded-full bg-lime-400/20 blur-[110px]" />
        <div className="absolute -bottom-32 -right-16 h-[380px] w-[380px] rounded-full bg-brand-500/30 blur-[100px]" />
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      <div className="relative animate-fade-in">
        <div className="inline-flex items-center rounded-xl bg-white px-4 py-2.5 shadow-lifted">
          <Image src="/afyacall-logo.png" alt="AfyaCall" width={140} height={53} priority className="h-8 w-auto" />
        </div>
      </div>

      <div className="relative max-w-md animate-slide-up">
        <p className="mb-3 text-[13px] font-medium uppercase tracking-[0.14em] text-lime-300">
          Campaign Engine
        </p>
        <h1 className="text-[34px] font-semibold leading-[1.15] tracking-tight xl:text-[40px]">
          Reach the right patients, at the right scale.
        </h1>
        <p className="mt-4 text-[15px] leading-relaxed text-white/70">
          One platform to import, validate, and run SMS, IVR, and Doctor campaigns across
          millions of customers - with DND, consent, and delivery rate under full control.
        </p>

        <dl className="mt-10 grid grid-cols-1 gap-3.5 sm:grid-cols-3">
          {STATS.map(({ icon: Icon, label, value }) => (
            <div
              key={label}
              className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3.5 backdrop-blur-sm"
            >
              <Icon className="mb-2 h-4 w-4 text-lime-300" aria-hidden="true" />
              <dd className="text-[17px] font-semibold leading-none">{value}</dd>
              <dt className="mt-1.5 text-[12px] leading-tight text-white/55">{label}</dt>
            </div>
          ))}
        </dl>
      </div>

      <p className="relative text-[12.5px] text-white/40">
        &copy; {new Date().getFullYear()} AfyaCall · Daktari Kiganjani
      </p>
    </div>
  );
}

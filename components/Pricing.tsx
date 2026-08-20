import React from 'react';

type ProductKey =
  | 'starter'
  | 'professional'
  | 'pro'
  | 'premium'
  | 'premium_full'
  | 'audit_500'
  | 'founder_997'
  | 'hipaa_1500';

const handleCheckout = (product: ProductKey) => {
  window.location.href = `/api/checkout?product=${encodeURIComponent(product)}`;
};

export default function PricingSection() {
  return (
    <section className="bg-slate-950 text-white py-16 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">

        {/* Emergency Response */}
        <div className="mb-12 border-2 border-red-600 bg-red-950/40 rounded-2xl p-6 sm:p-8 shadow-2xl shadow-red-900/20 backdrop-blur-md relative overflow-hidden">
          <div className="absolute top-0 right-0 bg-red-600 text-white font-bold text-xs uppercase tracking-widest px-4 py-1 rounded-bl-lg">
            Immediate Dispatch
          </div>

          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div className="space-y-2">
              <span className="inline-block bg-red-500/20 text-red-400 text-xs font-semibold px-3 py-1 rounded-full uppercase tracking-wider">
                Active Breach / Incident Response
              </span>

              <h2 className="text-2xl sm:text-3xl font-extrabold text-white">
                4-Hour Rapid Emergency Response & Remediation
              </h2>

              <p className="text-slate-300 max-w-2xl text-sm sm:text-base">
                Facing an active breach, ransomware threat, or urgent compliance
                audit failure? Our rapid response service provides immediate
                breach isolation, threat remediation, and audit-defense support.
              </p>
            </div>

            <div className="w-full md:w-auto flex flex-col sm:flex-row md:flex-col items-stretch md:items-end gap-3 min-w-[220px]">
              <div className="text-left md:text-right">
                <span className="text-3xl font-bold text-white">$1,499</span>
                <span className="text-slate-400 text-sm"> / emergency event</span>
              </div>

              <button
                type="button"
                onClick={() => handleCheckout('emergency_1499')}
                className="w-full bg-red-600 hover:bg-red-500 text-white font-bold py-3 px-6 rounded-xl transition duration-200 shadow-lg shadow-red-600/30 text-center"
              >
                Dispatch Response Team
              </button>
            </div>
          </div>
        </div>

        {/* Subscription Header */}
        <div className="text-center mb-12">
          <h2 className="text-3xl font-extrabold text-white sm:text-4xl">
            Continuous Security Sentinel Plans
          </h2>

          <p className="mt-3 text-slate-400 max-w-2xl mx-auto">
            Proactive threat detection, vulnerability management, compliance
            reporting, and continuous security operations.
          </p>
        </div>

        {/* Subscription Plans */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">

          {/* Starter */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between hover:border-slate-700 transition">
            <div>
              <h3 className="text-xl font-bold text-slate-200">
                Starter
              </h3>

              <p className="text-slate-400 text-sm mt-2">
                Essential endpoint security monitoring and threat detection.
              </p>

              <div className="my-6">
                <span className="text-4xl font-extrabold text-white">$99</span>
                <span className="text-slate-400 text-sm">/month</span>
              </div>

              <ul className="space-y-3 text-sm text-slate-300 mb-8">
                <li>✓ Essential endpoint monitoring</li>
                <li>✓ Threat detection</li>
                <li>✓ Automated security monitoring</li>
                <li>✓ Security event collection</li>
              </ul>
            </div>

            <button
              type="button"
              onClick={() => handleCheckout('starter')}
              className="w-full bg-slate-800 hover:bg-slate-700 text-white font-semibold py-3 px-4 rounded-xl transition"
            >
              Start Starter
            </button>
          </div>

          {/* Professional */}
          <div className="bg-slate-900 border-2 border-blue-500/50 rounded-2xl p-6 flex flex-col justify-between relative hover:border-blue-500 transition shadow-xl shadow-blue-500/10">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
              Most Popular
            </div>

            <div>
              <h3 className="text-xl font-bold text-slate-200">
                Professional
              </h3>

              <p className="text-slate-400 text-sm mt-2">
                Advanced autonomous threat defense, custom rules, and compliance reporting.
              </p>

              <div className="my-6">
                <span className="text-4xl font-extrabold text-white">$299</span>
                <span className="text-slate-400 text-sm">/month</span>
              </div>

              <ul className="space-y-3 text-sm text-slate-300 mb-8">
                <li>✓ Advanced autonomous threat defense</li>
                <li>✓ Custom security rules</li>
                <li>✓ Compliance reporting</li>
                <li>✓ Continuous monitoring</li>
                <li>✓ Automated threat detection</li>
              </ul>
            </div>

            <button
              type="button"
              onClick={() => handleCheckout('professional')}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3 px-4 rounded-xl transition"
            >
              Start Professional
            </button>
          </div>

          {/* Pro */}
          <div className="bg-slate-900 border border-emerald-500/40 rounded-2xl p-6 flex flex-col justify-between hover:border-emerald-500 transition">
            <div>
              <h3 className="text-xl font-bold text-slate-200">
                Pro
              </h3>

              <p className="text-slate-400 text-sm mt-2">
                10,000 Singularity Credits with advanced autonomous security operations.
              </p>

              <div className="my-6">
                <span className="text-4xl font-extrabold text-white">$499</span>
                <span className="text-slate-400 text-sm">/month</span>
              </div>

              <ul className="space-y-3 text-sm text-slate-300 mb-8">
                <li>✓ 10,000 Singularity Credits/month</li>
                <li>✓ Advanced autonomous security operations</li>
                <li>✓ Threat detection and response</li>
                <li>✓ Security automation</li>
                <li>✓ Expanded operational capacity</li>
              </ul>
            </div>

            <button
              type="button"
              onClick={() => handleCheckout('pro')}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-3 px-4 rounded-xl transition"
            >
              Start Pro
            </button>
          </div>
        </div>

        {/* Premium Plans */}
        <div className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-8">

          {/* Premium Tier */}
          <div className="bg-slate-900 border border-purple-500/40 rounded-2xl p-6 flex flex-col justify-between">
            <div>
              <h3 className="text-xl font-bold text-white">
                Security Sentinel Premium Tier
              </h3>

              <p className="text-slate-400 text-sm mt-2">
                Enterprise-grade security operations integration and priority support.
              </p>

              <div className="my-6">
                <span className="text-4xl font-extrabold text-white">$799</span>
                <span className="text-slate-400 text-sm">/month</span>
              </div>

              <ul className="space-y-3 text-sm text-slate-300 mb-8">
                <li>✓ Enterprise security operations integration</li>
                <li>✓ Priority support</li>
                <li>✓ Advanced monitoring</li>
                <li>✓ Security operations automation</li>
              </ul>
            </div>

            <button
              type="button"
              onClick={() => handleCheckout('premium')}
              className="w-full bg-purple-600 hover:bg-purple-500 text-white font-semibold py-3 px-4 rounded-xl transition"
            >
              Start Premium
            </button>
          </div>

          {/* Premium Full */}
          <div className="bg-slate-900 border border-amber-500/40 rounded-2xl p-6 flex flex-col justify-between">
            <div>
              <h3 className="text-xl font-bold text-white">
                Security Sentinel Premium
              </h3>

              <p className="text-slate-400 text-sm mt-2">
                Full-scope defense with priority incident response and quarterly security posture audits.
              </p>

              <div className="my-6">
                <span className="text-4xl font-extrabold text-white">$1,299</span>
                <span className="text-slate-400 text-sm">/month</span>
              </div>

              <ul className="space-y-3 text-sm text-slate-300 mb-8">
                <li>✓ Full-scope security defense</li>
                <li>✓ Priority incident response support</li>
                <li>✓ Quarterly security posture audits</li>
                <li>✓ Advanced security operations</li>
                <li>✓ Comprehensive monitoring</li>
              </ul>
            </div>

            <button
              type="button"
              onClick={() => handleCheckout('premium_full')}
              className="w-full bg-amber-600 hover:bg-amber-500 text-white font-semibold py-3 px-4 rounded-xl transition"
            >
              Start Premium Full
            </button>
          </div>
        </div>

        {/* One-Time Services */}
        <div className="mt-16">
          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold text-white">
              Security Audits & One-Time Services
            </h2>

            <p className="mt-2 text-slate-400">
              Purchase targeted assessments without a recurring subscription.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">

            {/* $500 Audit */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">
                  Nomadik Security Audit
                </h3>

                <p className="text-slate-400 text-sm mt-2">
                  Comprehensive active-defense security audit.
                </p>

                <div className="my-6">
                  <span className="text-4xl font-extrabold text-white">$500</span>
                  <span className="text-slate-400 text-sm"> one-time</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleCheckout('report_9')}
                className="w-full bg-slate-800 hover:bg-slate-700 text-white font-semibold py-3 px-4 rounded-xl transition"
              >
                Purchase Audit
              </button>
            </div>

            {/* Founder */}
            <div className="bg-slate-900 border-2 border-emerald-500/50 rounded-2xl p-6 flex flex-col justify-between relative">
              <div className="absolute -top-3 left-6 bg-emerald-600 text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
                Founder Launch
              </div>

              <div>
                <h3 className="text-lg font-bold text-white">
                  Security Sentinel Founder Bundle
                </h3>

                <p className="text-slate-400 text-sm mt-2">
                  Full Active Defense & Compliance Engine with Docker deployment,
                  compliance templates, log-noise automation, and incident-response playbooks.
                </p>

                <div className="my-6">
                  <span className="text-4xl font-extrabold text-white">$997</span>
                  <span className="text-slate-400 text-sm"> one-time</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleCheckout('founder_997')}
                className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-3 px-4 rounded-xl transition"
              >
                Get Founder Bundle
              </button>
            </div>

            {/* HIPAA */}
            <div className="bg-slate-900 border border-cyan-500/40 rounded-2xl p-6 flex flex-col justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">
                  HIPAA Compliance Gap Analysis
                </h3>

                <p className="text-slate-400 text-sm mt-2">
                  Automated vulnerability assessment and prioritized HIPAA security gap analysis.
                </p>

                <div className="my-6">
                  <span className="text-4xl font-extrabold text-white">$1,500</span>
                  <span className="text-slate-400 text-sm"> one-time</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleCheckout('hipaa_1500')}
                className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-3 px-4 rounded-xl transition"
              >
                Purchase HIPAA Audit
              </button>
            </div>

          </div>
        </div>

      </div>
    </section>
  );
}

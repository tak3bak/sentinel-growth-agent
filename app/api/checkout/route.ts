import { NextResponse } from 'next/server';
import Stripe from 'stripe';

const apiKey = process.env.STRIPE_SECRET_KEY;

if (!apiKey) {
  console.error('[CRITICAL] STRIPE_SECRET_KEY is missing from environment variables.');
}

const stripe = new Stripe(apiKey || '', {
  apiVersion: '2023-10-16',
});

/*
 * SERVER-SIDE STRIPE PRICE ALLOWLIST
 *
 * Clients submit a product key, never a Stripe Price ID.
 * This prevents arbitrary price selection/manipulation.
 */
const PRODUCTS = {
  starter: {
    name: 'Nomadik Security Operations - Starter',
    priceId: 'price_1U0Tq5D5LVILsj0FT4LoDMPq',
    mode: 'subscription' as const,
  },

  professional: {
    name: 'Nomadik Security Operations - Professional',
    priceId: 'price_1U0Tq6D5LVILsj0FzgyT0oM5',
    mode: 'subscription' as const,
  },

  pro: {
    name: 'Nomadik Security Operations - Pro',
    priceId: 'price_1U3NqHD5LVILsj0FiKwIGYwU',
    mode: 'subscription' as const,
  },

  premium: {
    name: 'Security Sentinel - Premium Tier',
    priceId: 'price_1TvgHDD5LVILsj0F8wInaKR3',
    mode: 'subscription' as const,
  },

  premium_full: {
    name: 'Security Sentinel - Premium',
    priceId: 'price_1U2K4gD5LVILsj0F1S5QbgUI',
    mode: 'subscription' as const,
  },

  report_9: {
    name: 'Nomadik Security Sentinel Tier',
    priceId: 'price_1Txm9pD5LVILsj0FwTzQP3cQ',
    mode: 'payment' as const,
  },

  emergency_1499: {
    name: '4-Hour Rapid Emergency Response & Remediation',
    priceId: 'price_1TwgHMD5LVILsj0FdCUQpuWt',
    mode: 'payment' as const,
  },

  audit_500: {
    name: 'Nomadik Security Audit',
    priceId: 'price_1U3h6LD5LVILsj0FbJAxNjE6',
    mode: 'payment' as const,
  },

  founder_997: {
    name: 'Nomadik Security Sentinel — Founder Launch Bundle',
    priceId: 'price_1U3KrLD5LVILsj0F0NPrPfKP',
    mode: 'payment' as const,
  },

  hipaa_1500: {
    name: 'HIPAA Compliance Gap Analysis & Security Audit',
    priceId: 'price_1U2K38D5LVILsj0FhBWFwl7L',
    mode: 'payment' as const,
  },
} as const;

type ProductKey = keyof typeof PRODUCTS;

function getProduct(value: string | null) {
  if (!value) {
    return null;
  }

  if (!(value in PRODUCTS)) {
    return null;
  }

  return PRODUCTS[value as ProductKey];
}

async function createCheckoutSession(
  request: Request,
  productKey: string | null,
) {
  if (!process.env.STRIPE_SECRET_KEY) {
    return NextResponse.json(
      { error: 'Stripe configuration error on server.' },
      { status: 500 },
    );
  }

  const product = getProduct(productKey);

  if (!product) {
    return NextResponse.json(
      {
        error: 'Invalid product.',
        allowed_products: Object.keys(PRODUCTS),
      },
      { status: 400 },
    );
  }

  try {
    const session = await stripe.checkout.sessions.create({
      mode: product.mode,

      line_items: [
        {
          price: product.priceId,
          quantity: 1,
        },
      ],

      success_url:
        'https://nomadik.site/success?session_id={CHECKOUT_SESSION_ID}',

      cancel_url: 'https://nomadik.site',

      allow_promotion_codes: true,

      metadata: {
        product_key: productKey!,
        product_name: product.name,
      },
    });

    if (!session.url) {
      return NextResponse.json(
        { error: 'Failed to generate Stripe checkout URL.' },
        { status: 500 },
      );
    }

    return NextResponse.redirect(session.url, 303);
  } catch (err: unknown) {
    const message =
      err instanceof Error ? err.message : 'Internal Stripe error';

    console.error('[STRIPE CHECKOUT ERROR]', message);

    return NextResponse.json(
      { error: message },
      { status: 500 },
    );
  }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);

  return createCheckoutSession(
    request,
    searchParams.get('product'),
  );
}

export async function POST(request: Request) {
  try {
    const body = await request.json();

    return createCheckoutSession(
      request,
      typeof body?.product === 'string'
        ? body.product
        : null,
    );
  } catch {
    return NextResponse.json(
      { error: 'Invalid JSON request body.' },
      { status: 400 },
    );
  }
}

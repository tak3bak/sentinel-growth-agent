import { NextResponse } from 'next/server';
import Stripe from 'stripe';

const apiKey = process.env.STRIPE_SECRET_KEY;

if (!apiKey) {
  console.error('[CRITICAL] STRIPE_SECRET_KEY is missing from environment variables.');
}

const stripe = new Stripe(apiKey || '', {
  apiVersion: '2023-10-16',
});

export async function GET(request: Request) {
  if (!process.env.STRIPE_SECRET_KEY) {
    return NextResponse.json(
      { error: 'Stripe configuration error on server.' },
      { status: 500 }
    );
  }

  const { searchParams } = new URL(request.url);
  const priceId = searchParams.get('priceId');

  if (!priceId) {
    return NextResponse.json({ error: 'Missing priceId parameter' }, { status: 400 });
  }

  try {
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      line_items: [{ price: priceId, quantity: 1 }],
      mode: 'payment',
      success_url: 'https://nomadik.site/success',
      cancel_url: 'https://nomadik.site',
    });

    if (!session.url) {
      return NextResponse.json(
        { error: 'Failed to generate Stripe checkout URL' },
        { status: 500 }
      );
    }

    return NextResponse.redirect(session.url, 303);
  } catch (err: any) {
    console.error('Stripe Checkout GET Error:', err?.message || err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  if (!process.env.STRIPE_SECRET_KEY) {
    return NextResponse.json(
      { error: 'Stripe configuration error on server.' },
      { status: 500 }
    );
  }

  try {
    const body = await request.json();
    const { priceId } = body;

    if (!priceId) {
      return NextResponse.json({ error: 'Missing priceId parameter' }, { status: 400 });
    }

    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      line_items: [{ price: priceId, quantity: 1 }],
      mode: 'payment',
      success_url: 'https://nomadik.site/success',
      cancel_url: 'https://nomadik.site',
    });

    return NextResponse.json({ url: session.url });
  } catch (err: any) {
    console.error('Stripe Checkout POST Error:', err?.message || err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

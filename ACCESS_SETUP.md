# Prop+ sharing and future access control

## Current deployment
The NBA, NFL, and college football dashboards are responsive and shareable by URL. Tables scroll horizontally on narrow phones; navigation and filters adapt to small screens. Existing data files remain public on the deployed site.

## Future invite-code access
Do not implement a password or access code solely in browser JavaScript. Client-side checks do not protect HTML, CSV, or API endpoints.

For secure access, implement server-side authentication using a hosted identity provider (e.g. Auth.js or Clerk), and enforce authorization at the server/edge before serving protected pages **and data endpoints**. Store invite-code hashes and their redemption limits server-side. A one-time code should redeem to a user account/session; never place a shared secret in HTML or GitHub.

## Future subscriptions
Use a billing provider such as Stripe Checkout and webhooks to manage subscription entitlements. After verifying webhook signatures, update a server-side entitlement record. Every protected data request must validate a signed-in session and an active entitlement. Provide subscription cancellation, billing management, and a grace-period policy.

## Deployment caution
GitHub Pages or a static Vercel deployment does not itself make files private. Before charging for access, move restricted datasets to a protected backend or private object store. Set up environment variables in deployment settings rather than committing keys. Test access controls in an incognito browser and by requesting raw CSV URLs without signing in.

## Suggested phases
1. Responsive public preview (implemented).
2. Private invite-code beta with server-side authentication.
3. Subscription plans and billing integration.
4. Usage monitoring and support.

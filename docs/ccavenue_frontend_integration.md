# CCAvenue Frontend Integration

The React app must never encrypt CCAvenue payloads and must never receive the Working Key.

## Create Payment

Call the backend with the logged-in user's JWT:

```bash
curl -X POST "https://backend.dealskb.com/api/payments/ccavenue/create" \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"payment_type":"SELLER_LISTING","listing_id":"prod_xxxxxx"}'
```

Supported request bodies:

```json
{ "payment_type": "SELLER_LISTING", "listing_id": "prod_xxxxxx" }
```

```json
{ "payment_type": "BUYER_PASS", "plan_id": "buyer_car_day" }
```

```json
{ "payment_type": "DEALER_PLAN", "plan_id": "dealer_monthly" }
```

Available plan IDs are returned by:

```bash
curl "https://backend.dealskb.com/api/payments/plans" \
  -H "Authorization: Bearer <jwt>"
```

The logged-in user's active paid plans are returned by:

```bash
curl "https://backend.dealskb.com/api/payments/plans/my" \
  -H "Authorization: Bearer <jwt>"
```

The response contains only:

```json
{
  "order_id": "DKB-...",
  "gateway_url": "https://...",
  "enc_request": "...",
  "access_code": "..."
}
```

Submit a browser form to CCAvenue:

```html
<form method="POST" action="{gateway_url}">
  <input type="hidden" name="encRequest" value="{enc_request}" />
  <input type="hidden" name="access_code" value="{access_code}" />
</form>
```

Programmatically submit the form after appending it to the document.

## Verified Status

After CCAvenue redirects the browser to `https://dealskb.com/payment-result?order_id=...&status=...`, the frontend must call:

```bash
curl "https://backend.dealskb.com/api/payments/DKB-xxxx/status" \
  -H "Authorization: Bearer <jwt>"
```

The query-string status is display-only. The backend status endpoint is authoritative.

## CCAvenue Dashboard URLs

Whitelist or configure these backend URLs in CCAvenue:

- Redirect URL: `https://backend.dealskb.com/api/payments/ccavenue/callback`
- Cancel URL: `https://backend.dealskb.com/api/payments/ccavenue/cancel`

## Nginx / Deployment Checks

- Forward POST requests to `/api/payments/ccavenue/callback` and `/api/payments/ccavenue/cancel` to FastAPI.
- Preserve `application/x-www-form-urlencoded` request bodies.
- Do not rewrite POST callbacks into GET during HTTP-to-HTTPS redirects.
- Ensure HTTPS is valid for `backend.dealskb.com`.
- Ensure `python-multipart` is installed so FastAPI can read form fields.

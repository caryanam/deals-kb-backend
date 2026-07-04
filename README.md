# DealsKB Backend

Standalone FastAPI backend for the DealsKB multi-product AutoBid web app.

## Requirements

- Python 3.10+
- MySQL running locally or a reachable MySQL connection string

## Setup

```powershell
cd "C:\Users\Laptop On Rent 248\Downloads\DealsKB-backend"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create the database before starting the backend:

```sql
CREATE DATABASE dealskb;
```

Configure `.env`:

```env
DATABASE_URL=mysql+pymysql://root:your_password@localhost:3306/dealskb
MAX_REQUEST_SIZE_MB=50
```

For MySQL, keep `photos`, `documents`, and `specifications` as JSON fields. If you are sending base64 payloads, also raise MySQL packet size in your MySQL config:

```ini
max_allowed_packet=64M
```

If deploying behind Nginx, match the backend request limit:

```nginx
client_max_body_size 50M;
```

If PowerShell blocks virtual environment activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## Run

```powershell
python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

Open:

```txt
http://localhost:8000/api/
```

Expected response:

```json
{
  "app": "DealsKB Multi-Product AutoBid Backend",
  "status": "ok"
}
```

## React Web App API URL

Use this in your frontend environment:

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

## Default Admin Login

```txt
9123456789
admin@123
```

## Main Features

- Buyer, Seller, and Admin authentication
- Product listing creation for cars, bikes, laptops, and mobiles
- Admin approval and rejection
- 30-second live auctions
- Real-time WebSocket bid updates
- Bid history
- User wins
- In-app notifications
- Admin users and analytics APIs

## Product APIs

Swagger docs are available at:

```txt
http://localhost:8000/docs
```

The main listing APIs are now under:

```txt
/api/products
/api/products/{product_id}
/api/products/{product_id}/review
/api/products/{product_id}/start-auction
/api/products/{product_id}/bid
/api/products/{product_id}/bids
/api/products/{product_id}/seller-contact
/api/ws/auction/{product_id}
```

## Auth OTP APIs

```txt
/api/auth/send-registration-otp
/api/auth/verify-registration-otp
/api/auth/forgot-password/send-otp
/api/auth/forgot-password/verify-otp
/api/auth/forgot-password/reset
```

In development, OTP responses include `dev_otp`. Set `APP_ENV=production` to hide OTP values from responses.

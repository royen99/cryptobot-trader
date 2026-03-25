import requests

COINS = [
    "AVAX", "AAVE", "BONK", "CRO", "ETH", "FET", "GODS", "HBAR",
    "LINK", "LTC", "PEPE", "ONDO", "RENDER", "SEI", "SHIB", "SOL",
    "SUI", "UNI", "XCN", "XLM", "XRP",
]

BASE_URL = "https://api.coinbase.com/api/v3/brokerage/market/products/"

def check_public_usd_pairs():
    for coin in COINS:
        product = f"{coin}-USD"
        url = BASE_URL + product

        try:
            r = requests.get(url)
            data = r.json()
        except Exception as e:
            print(f"[{product}] ERROR: {e}")
            continue

        # Pair does not exist
        if "product_id" not in data:
            print(f"[{product}] ❌ No USD market")
            continue

        # Pair exists
        price = data.get("price", "n/a")
        status = data.get("status", "unknown")
        volume = data.get("volume_24h", "n/a")
        print(f"[{product}] ✅ Exists | status={status} | price={price} | volume={volume}")

if __name__ == "__main__":
    check_public_usd_pairs()

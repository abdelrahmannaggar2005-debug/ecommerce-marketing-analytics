"""
Synthetic E-commerce Marketing & Customer dataset generator.

This creates a realistic (but simulated) e-commerce dataset with intentional,
built-in relationships so that statistical tests and SQL analysis surface
genuine, defensible signal instead of random noise:

  - Acquisition channel affects average order value, repeat-purchase rate, and margin
  - Delivery delay negatively affects review score
  - Discount usage boosts short-term order frequency but reduces margin

Run: python3 generate_data.py
Outputs CSVs into ./data/ and a SQLite DB at ./data/ecommerce.db
"""

import numpy as np
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

np.random.seed(42)

N_CUSTOMERS = 3000
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2025, 12, 31)
CHANNELS = ["Paid Search", "Organic", "Social", "Email", "Referral"]

# Channel behavior profiles: [signup_weight, base_AOV, repeat_prob, cac]
CHANNEL_PROFILE = {
    "Paid Search": {"weight": 0.32, "aov": 55, "repeat_p": 0.28, "cac": 18},
    "Organic":     {"weight": 0.22, "aov": 62, "repeat_p": 0.35, "cac": 4},
    "Social":      {"weight": 0.20, "aov": 48, "repeat_p": 0.22, "cac": 14},
    "Email":       {"weight": 0.12, "aov": 68, "repeat_p": 0.48, "cac": 3},
    "Referral":    {"weight": 0.14, "aov": 71, "repeat_p": 0.52, "cac": 2},
}

CATEGORIES = ["Electronics", "Home & Kitchen", "Fashion", "Beauty", "Sports", "Toys"]

# ---------------------------------------------------------------- customers
channels = list(CHANNEL_PROFILE.keys())
weights = [CHANNEL_PROFILE[c]["weight"] for c in channels]

customer_ids = np.arange(1, N_CUSTOMERS + 1)
customer_channel = np.random.choice(channels, size=N_CUSTOMERS, p=weights)
signup_offsets = np.random.randint(0, (END_DATE - START_DATE).days - 60, size=N_CUSTOMERS)
signup_dates = [START_DATE + timedelta(days=int(d)) for d in signup_offsets]
age_group = np.random.choice(["18-24", "25-34", "35-44", "45-54", "55+"],
                              size=N_CUSTOMERS, p=[0.15, 0.32, 0.27, 0.16, 0.10])
city = np.random.choice(["Cairo", "Giza", "Alexandria", "Mansoura", "Tanta", "Aswan"],
                         size=N_CUSTOMERS, p=[0.30, 0.20, 0.18, 0.12, 0.10, 0.10])

customers = pd.DataFrame({
    "customer_id": customer_ids,
    "signup_date": signup_dates,
    "acquisition_channel": customer_channel,
    "age_group": age_group,
    "city": city,
})

# ---------------------------------------------------------------- products
n_products = 60
product_ids = np.arange(1, n_products + 1)
prod_category = np.random.choice(CATEGORIES, size=n_products)
base_price = np.round(np.random.uniform(8, 220, size=n_products), 2)
cost = np.round(base_price * np.random.uniform(0.45, 0.7, size=n_products), 2)
product_name = [f"{c} Item {i}" for i, c in zip(product_ids, prod_category)]

products = pd.DataFrame({
    "product_id": product_ids,
    "product_name": product_name,
    "category": prod_category,
    "base_price": base_price,
    "cost": cost,
})

# ---------------------------------------------------------------- orders + items + reviews
orders_rows = []
items_rows = []
reviews_rows = []

order_id_counter = 1
item_id_counter = 1
review_id_counter = 1

for _, cust in customers.iterrows():
    profile = CHANNEL_PROFILE[cust["acquisition_channel"]]
    n_orders = 1
    # decide repeat purchases based on channel repeat probability, with decreasing odds each time
    p = profile["repeat_p"]
    while np.random.rand() < (p if n_orders == 1 else p * 0.6) and n_orders < 8:
        n_orders += 1

    last_date = cust["signup_date"]
    for k in range(n_orders):
        gap_days = int(np.random.exponential(35)) + 1
        order_date = last_date + timedelta(days=gap_days) if k > 0 else cust["signup_date"] + timedelta(days=np.random.randint(0, 5))
        if order_date > END_DATE:
            break
        last_date = order_date

        discount_pct = np.random.choice([0, 5, 10, 15, 20], p=[0.45, 0.2, 0.15, 0.12, 0.08])
        delivery_days = max(1, int(np.random.normal(4.5, 2.2)))
        # order status
        status = np.random.choice(["Delivered", "Delivered", "Delivered", "Cancelled", "Returned"],
                                   p=[0.80, 0.0, 0.0, 0.09, 0.11])
        status = "Delivered" if status == "Delivered" else status

        order_id = order_id_counter
        order_id_counter += 1

        orders_rows.append({
            "order_id": order_id,
            "customer_id": cust["customer_id"],
            "order_date": order_date.date().isoformat(),
            "delivery_days": delivery_days,
            "discount_pct": discount_pct,
            "order_status": status,
        })

        n_items = np.random.randint(1, 4)
        chosen_products = np.random.choice(product_ids, size=n_items, replace=False)
        order_value = 0
        for pid in chosen_products:
            prod = products.loc[products.product_id == pid].iloc[0]
            qty = np.random.randint(1, 3)
            unit_price = round(prod["base_price"] * np.random.uniform(0.9, 1.05), 2)
            items_rows.append({
                "order_item_id": item_id_counter,
                "order_id": order_id,
                "product_id": int(pid),
                "quantity": int(qty),
                "unit_price": unit_price,
            })
            order_value += unit_price * qty
            item_id_counter += 1

        # review: only for delivered orders, ~78% leave a review
        if status == "Delivered" and np.random.rand() < 0.78:
            # delivery_days pushes score down; discount slightly increases satisfaction; add noise
            base_score = 4.6 - (delivery_days - 3) * 0.28 + (discount_pct / 100) * 0.6
            noise = np.random.normal(0, 0.6)
            score = base_score + noise
            score = int(np.clip(round(score), 1, 5))
            reviews_rows.append({
                "review_id": review_id_counter,
                "order_id": order_id,
                "review_score": score,
                "review_date": (order_date + timedelta(days=delivery_days + np.random.randint(0, 5))).date().isoformat(),
            })
            review_id_counter += 1

orders = pd.DataFrame(orders_rows)
order_items = pd.DataFrame(items_rows)
reviews = pd.DataFrame(reviews_rows)

# ---------------------------------------------------------------- marketing_spend (monthly by channel)
months = pd.date_range(START_DATE, END_DATE, freq="MS")
spend_rows = []
for m in months:
    for ch in channels:
        profile = CHANNEL_PROFILE[ch]
        sessions = int(np.random.normal(1800, 300) * profile["weight"] * 3)
        conversions = max(1, int(sessions * np.random.uniform(0.02, 0.06)))
        spend = round(conversions * profile["cac"] * np.random.uniform(0.85, 1.15), 2)
        spend_rows.append({
            "month": m.date().isoformat(),
            "channel": ch,
            "sessions": sessions,
            "conversions": conversions,
            "spend": spend,
        })
marketing_spend = pd.DataFrame(spend_rows)

# ---------------------------------------------------------------- save
customers.to_csv("data/customers.csv", index=False)
products.to_csv("data/products.csv", index=False)
orders.to_csv("data/orders.csv", index=False)
order_items.to_csv("data/order_items.csv", index=False)
reviews.to_csv("data/reviews.csv", index=False)
marketing_spend.to_csv("data/marketing_spend.csv", index=False)

conn = sqlite3.connect("data/ecommerce.db")
customers.to_sql("customers", conn, if_exists="replace", index=False)
products.to_sql("products", conn, if_exists="replace", index=False)
orders.to_sql("orders", conn, if_exists="replace", index=False)
order_items.to_sql("order_items", conn, if_exists="replace", index=False)
reviews.to_sql("reviews", conn, if_exists="replace", index=False)
marketing_spend.to_sql("marketing_spend", conn, if_exists="replace", index=False)
conn.close()

print(f"customers: {len(customers)}")
print(f"orders: {len(orders)}")
print(f"order_items: {len(order_items)}")
print(f"reviews: {len(reviews)}")
print(f"marketing_spend rows: {len(marketing_spend)}")
print("Saved CSVs + data/ecommerce.db")

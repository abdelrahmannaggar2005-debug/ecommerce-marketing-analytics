"""
Statistical Analysis — E-commerce Marketing & Customer dataset
================================================================
Answers 4 business questions with real hypothesis tests, not just
descriptive dashboards:

  1. Does delivery delay actually hurt review scores, or is it noise?
     -> Pearson correlation + significance test
  2. Is the AOV gap between Referral/Email vs Paid Search customers real?
     -> Independent two-sample t-test
  3. Is acquisition channel actually associated with repeat-purchase
     behavior, or could the pattern be due to chance?
     -> Chi-square test of independence
  4. Can we predict whether a customer will become a repeat buyer from
     their first order (channel, first order value, delivery delay)?
     -> Logistic regression

Run: python3 statistical_analysis.py
"""

import sqlite3
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.preprocessing import StandardScaler
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

conn = sqlite3.connect("../data/ecommerce.db")

orders = pd.read_sql("SELECT * FROM orders", conn)
items = pd.read_sql("SELECT * FROM order_items", conn)
customers = pd.read_sql("SELECT * FROM customers", conn)
reviews = pd.read_sql("SELECT * FROM reviews", conn)

order_value = (items.groupby("order_id")
               .apply(lambda d: (d.quantity * d.unit_price).sum())
               .rename("order_value").reset_index())

orders_full = orders.merge(order_value, on="order_id").merge(customers, on="customer_id")

print("=" * 65)
print("1) DELIVERY DELAY vs REVIEW SCORE — Pearson correlation")
print("=" * 65)
rev = reviews.merge(orders[["order_id", "delivery_days"]], on="order_id")
r, p = stats.pearsonr(rev["delivery_days"], rev["review_score"])
print(f"n = {len(rev)}")
print(f"Pearson r = {r:.3f}, p-value = {p:.2e}")
print("-> " + ("Statistically significant negative correlation." if p < 0.05 and r < 0
      else "No significant relationship found."))
print(f"Interpretation: each extra delivery day is associated with roughly "
      f"{abs(r)*100:.1f}% of a standard deviation drop in review score.\n")

print("=" * 65)
print("2) AOV: Referral+Email vs Paid Search — Independent t-test")
print("=" * 65)
delivered = orders_full[orders_full.order_status == "Delivered"]
group_a = delivered[delivered.acquisition_channel.isin(["Referral", "Email"])]["order_value"]
group_b = delivered[delivered.acquisition_channel == "Paid Search"]["order_value"]
t_stat, p_val = stats.ttest_ind(group_a, group_b, equal_var=False)
print(f"Referral/Email mean AOV = {group_a.mean():.2f} (n={len(group_a)})")
print(f"Paid Search mean AOV    = {group_b.mean():.2f} (n={len(group_b)})")
print(f"t-statistic = {t_stat:.3f}, p-value = {p_val:.2e}")
print("-> " + ("Difference is statistically significant." if p_val < 0.05
      else "Difference is not statistically significant.") + "\n")

print("=" * 65)
print("3) ACQUISITION CHANNEL vs REPEAT-PURCHASE — Chi-square test")
print("=" * 65)
order_counts = orders[orders.order_status == "Delivered"].groupby("customer_id").size().rename("n_orders")
cust_repeat = customers.set_index("customer_id").join(order_counts).fillna(0)
cust_repeat["is_repeat"] = cust_repeat["n_orders"] >= 2
contingency = pd.crosstab(cust_repeat["acquisition_channel"], cust_repeat["is_repeat"])
chi2, p_chi, dof, expected = stats.chi2_contingency(contingency)
print(contingency)
print(f"\nChi2 = {chi2:.2f}, dof = {dof}, p-value = {p_chi:.2e}")
print("-> " + ("Channel and repeat-purchase behavior are significantly associated."
      if p_chi < 0.05 else "No significant association found.") + "\n")

print("=" * 65)
print("4) LOGISTIC REGRESSION — Predicting repeat-purchase from 1st order")
print("=" * 65)
first_orders = (orders_full[orders_full.order_status == "Delivered"]
                 .sort_values("order_date")
                 .groupby("customer_id").first().reset_index())
first_orders = first_orders.merge(cust_repeat[["is_repeat"]], on="customer_id")

X = pd.get_dummies(first_orders[["acquisition_channel", "order_value", "delivery_days"]],
                    columns=["acquisition_channel"], drop_first=True)
y = first_orders["is_repeat"].astype(int)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
scaler = StandardScaler()
num_cols = ["order_value", "delivery_days"]
X_train_s, X_test_s = X_train.copy(), X_test.copy()
X_train_s[num_cols] = scaler.fit_transform(X_train[num_cols])
X_test_s[num_cols] = scaler.transform(X_test[num_cols])

model = LogisticRegression(max_iter=1000, class_weight="balanced")
model.fit(X_train_s, y_train)
y_pred = model.predict(X_test_s)
y_prob = model.predict_proba(X_test_s)[:, 1]

print(classification_report(y_test, y_pred, digits=3))
print(f"ROC-AUC: {roc_auc_score(y_test, y_prob):.3f}\n")

print("Feature coefficients (standardized numeric features):")
for feat, coef in sorted(zip(X_train_s.columns, model.coef_[0]), key=lambda x: -abs(x[1])):
    print(f"  {feat:30s} {coef:+.3f}")

# ----------------------------------------------------------- charts
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

axes[0].scatter(rev["delivery_days"], rev["review_score"] + np.random.uniform(-0.1, 0.1, len(rev)),
                alpha=0.15, s=12, color="#3b82f6")
z = np.polyfit(rev["delivery_days"], rev["review_score"], 1)
xline = np.linspace(rev["delivery_days"].min(), rev["delivery_days"].max(), 50)
axes[0].plot(xline, np.polyval(z, xline), color="#ef4444", linewidth=2)
axes[0].set_xlabel("Delivery Days")
axes[0].set_ylabel("Review Score")
axes[0].set_title(f"Delivery Delay vs Review Score (r={r:.2f}, p<0.001)")

channel_repeat = cust_repeat.groupby("acquisition_channel")["is_repeat"].mean().sort_values(ascending=False) * 100
axes[1].bar(channel_repeat.index, channel_repeat.values, color="#60a5fa")
axes[1].set_ylabel("Repeat Purchase Rate (%)")
axes[1].set_title("Repeat Rate by Acquisition Channel")
axes[1].tick_params(axis='x', rotation=30)

plt.tight_layout()
plt.savefig("../assets/stats_summary.png", dpi=150)
print("\nSaved chart -> assets/stats_summary.png")

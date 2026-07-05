-- =========================================================
-- E-commerce Marketing & Customer Analytics — SQL Analysis
-- DB: data/ecommerce.db (SQLite)
-- =========================================================

-- ---------------------------------------------------------
-- 1) Monthly Revenue Trend + Month-over-Month % Change
--    (CTE + window function LAG)
-- ---------------------------------------------------------
WITH monthly_revenue AS (
    SELECT
        strftime('%Y-%m', o.order_date)              AS month,
        ROUND(SUM(oi.quantity * oi.unit_price), 2)    AS revenue,
        COUNT(DISTINCT o.order_id)                    AS orders
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
    GROUP BY 1
)
SELECT
    month,
    revenue,
    orders,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
        / LAG(revenue) OVER (ORDER BY month), 1
    ) AS mom_pct_change
FROM monthly_revenue
ORDER BY month;


-- ---------------------------------------------------------
-- 2) RFM Segmentation (Recency, Frequency, Monetary)
--    (CTE + NTILE window function to score each dimension 1-4)
-- ---------------------------------------------------------
WITH order_value AS (
    SELECT o.order_id, o.customer_id, o.order_date,
           SUM(oi.quantity * oi.unit_price) AS order_total
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
    GROUP BY o.order_id
),
customer_rfm AS (
    SELECT
        customer_id,
        JULIANDAY('2026-01-01') - JULIANDAY(MAX(order_date)) AS recency_days,
        COUNT(*)                                              AS frequency,
        ROUND(SUM(order_total), 2)                            AS monetary
    FROM order_value
    GROUP BY customer_id
),
scored AS (
    SELECT
        customer_id, recency_days, frequency, monetary,
        NTILE(4) OVER (ORDER BY recency_days DESC) AS r_score,   -- lower recency_days = better
        NTILE(4) OVER (ORDER BY frequency ASC)     AS f_score,
        NTILE(4) OVER (ORDER BY monetary ASC)      AS m_score
    FROM customer_rfm
)
SELECT
    customer_id, recency_days, frequency, monetary,
    r_score, f_score, m_score,
    (r_score + f_score + m_score) AS rfm_total,
    CASE
        WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Champions'
        WHEN r_score >= 3 AND f_score <= 2                  THEN 'New / Promising'
        WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN 'At Risk (High Value)'
        WHEN r_score <= 2 AND f_score <= 2                  THEN 'Lost'
        ELSE 'Needs Attention'
    END AS segment
FROM scored
ORDER BY rfm_total DESC;


-- ---------------------------------------------------------
-- 3) Monthly Acquisition Cohort Retention
--    (self-join on customer's order months vs signup month)
-- ---------------------------------------------------------
WITH first_order AS (
    SELECT customer_id, MIN(order_date) AS first_order_date
    FROM orders WHERE order_status = 'Delivered'
    GROUP BY customer_id
),
cohort AS (
    SELECT
        fo.customer_id,
        strftime('%Y-%m', fo.first_order_date) AS cohort_month,
        strftime('%Y-%m', o.order_date)         AS order_month
    FROM first_order fo
    JOIN orders o ON o.customer_id = fo.customer_id AND o.order_status = 'Delivered'
),
cohort_index AS (
    SELECT
        cohort_month,
        order_month,
        customer_id,
        (
            (CAST(strftime('%Y', order_month || '-01') AS INT) - CAST(strftime('%Y', cohort_month || '-01') AS INT)) * 12
            + (CAST(strftime('%m', order_month || '-01') AS INT) - CAST(strftime('%m', cohort_month || '-01') AS INT))
        ) AS month_index
    FROM cohort
)
SELECT
    cohort_month,
    month_index,
    COUNT(DISTINCT customer_id) AS active_customers
FROM cohort_index
GROUP BY cohort_month, month_index
ORDER BY cohort_month, month_index;


-- ---------------------------------------------------------
-- 4) Marketing Channel ROI Ranking
--    (join orders+customers to marketing_spend, RANK() window function)
-- ---------------------------------------------------------
WITH channel_revenue AS (
    SELECT
        c.acquisition_channel AS channel,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
    FROM customers c
    JOIN orders o      ON o.customer_id = c.customer_id AND o.order_status = 'Delivered'
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY c.acquisition_channel
),
channel_spend AS (
    SELECT channel, ROUND(SUM(spend), 2) AS total_spend
    FROM marketing_spend
    GROUP BY channel
)
SELECT
    cr.channel,
    cr.revenue,
    cs.total_spend,
    ROUND(cr.revenue / cs.total_spend, 2) AS roi_multiplier,
    RANK() OVER (ORDER BY (cr.revenue / cs.total_spend) DESC) AS roi_rank
FROM channel_revenue cr
JOIN channel_spend cs ON cs.channel = cr.channel
ORDER BY roi_rank;


-- ---------------------------------------------------------
-- 5) Top 10 Customers by Lifetime Value
--    (DENSE_RANK + running total of company revenue)
-- ---------------------------------------------------------
WITH customer_ltv AS (
    SELECT
        c.customer_id,
        c.acquisition_channel,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS ltv
    FROM customers c
    JOIN orders o       ON o.customer_id = c.customer_id AND o.order_status = 'Delivered'
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY c.customer_id
)
SELECT
    customer_id,
    acquisition_channel,
    ltv,
    DENSE_RANK() OVER (ORDER BY ltv DESC) AS ltv_rank,
    ROUND(SUM(ltv) OVER (ORDER BY ltv DESC), 2) AS running_total_ltv
FROM customer_ltv
ORDER BY ltv DESC
LIMIT 10;


-- ---------------------------------------------------------
-- 6) Delivery Delay Bucket vs Average Review Score
-- ---------------------------------------------------------
SELECT
    CASE
        WHEN o.delivery_days <= 2 THEN '0-2 days'
        WHEN o.delivery_days <= 4 THEN '3-4 days'
        WHEN o.delivery_days <= 6 THEN '5-6 days'
        ELSE '7+ days'
    END AS delivery_bucket,
    COUNT(*)                          AS n_orders,
    ROUND(AVG(r.review_score), 2)     AS avg_review_score
FROM orders o
JOIN reviews r ON r.order_id = o.order_id
GROUP BY delivery_bucket
ORDER BY MIN(o.delivery_days);


-- ---------------------------------------------------------
-- 7) Repeat Purchase Rate by Acquisition Channel
--    (self-join to find customers with 2+ orders)
-- ---------------------------------------------------------
WITH order_counts AS (
    SELECT customer_id, COUNT(*) AS n_orders
    FROM orders
    WHERE order_status = 'Delivered'
    GROUP BY customer_id
)
SELECT
    c.acquisition_channel,
    COUNT(*)                                              AS total_customers,
    SUM(CASE WHEN oc.n_orders >= 2 THEN 1 ELSE 0 END)      AS repeat_customers,
    ROUND(100.0 * SUM(CASE WHEN oc.n_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS repeat_rate_pct
FROM customers c
JOIN order_counts oc ON oc.customer_id = c.customer_id
GROUP BY c.acquisition_channel
ORDER BY repeat_rate_pct DESC;


-- ---------------------------------------------------------
-- 8) Category Profit Margin Analysis
--    (join products to order_items, compute margin %)
-- ---------------------------------------------------------
SELECT
    p.category,
    ROUND(SUM(oi.quantity * oi.unit_price), 2)                         AS revenue,
    ROUND(SUM(oi.quantity * p.cost), 2)                                AS cost,
    ROUND(SUM(oi.quantity * (oi.unit_price - p.cost)), 2)              AS profit,
    ROUND(100.0 * SUM(oi.quantity * (oi.unit_price - p.cost)) / SUM(oi.quantity * oi.unit_price), 1) AS margin_pct
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
JOIN orders o   ON o.order_id = oi.order_id AND o.order_status = 'Delivered'
GROUP BY p.category
ORDER BY margin_pct DESC;

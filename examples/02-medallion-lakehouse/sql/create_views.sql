-- Gold layer SQL views for the analytics warehouse
-- These views are created on deploy via fab-bundle

CREATE OR ALTER VIEW gold_order_summary AS
SELECT
    order_date,
    total_orders,
    revenue,
    avg_order_value,
    revenue / NULLIF(total_orders, 0) AS revenue_per_order
FROM gold.daily_order_summary;

CREATE OR ALTER VIEW gold_customer_360 AS
SELECT
    customer_id,
    customer_email,
    COUNT(DISTINCT order_id) AS lifetime_orders,
    SUM(total_amount) AS lifetime_value,
    MIN(order_date) AS first_order,
    MAX(order_date) AS last_order
FROM silver.orders
GROUP BY customer_id, customer_email;
